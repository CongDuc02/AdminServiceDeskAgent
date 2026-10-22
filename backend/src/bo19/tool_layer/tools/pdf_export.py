"""Tool `pdf_export` — chuyển `.docx` đã ghi sang `.pdf`, ghi một lần, rồi thêm dòng `document_render` (mục Tool Registry của 03-agents.md; ADR-015; mục 5.3 của 04-data.md).

Chỉ **tác nhân hệ thống**. Đầu vào là kết quả của `docx_render` (`DocxRender`). **Thứ tự bên trong một lần render — chốt ở ADR-015:** kiểm khoá `.pdf` đã commit chưa → (chưa) kiểm font → đọc `.docx` (kiểm checksum) → chuyển đổi
vào thư mục tạm → **rồi mới** giành khoá → upload → commit. Nhờ vậy lease của `stored_object` chỉ phủ **thời lượng upload**; một lần chuyển đổi chậm chỉ lãng phí công. Byte PDF khác nhau giữa hai lần chuyển đổi
(ADR-015 không giả định PDF tất định) không bao giờ tới `object_storage`: khoá đã có commit thì dùng object của lần ghi đầu (`reused`).

`FONT_MISSING` (mã nội bộ của tool, **không** vào danh mục `error_code` của 05-api.md): một họ trong `required_fonts` của phiên bản template không có mặt trong image — kiểm **trước** khi gọi `soffice`, không để bộ
chuyển đổi tự thay font (ADR-015 chốt 3; "có mặt" theo ADR-036). Lớp phòng thủ thêm chừng nào `api` và `queue_worker` dùng chung image; **bắt buộc** nếu tách image.

Dòng `document_render` chỉ thêm khi cả `.docx` lẫn `.pdf` đã commit (khoá ngoại tới `stored_object_commit` giữ điều đó); `UNIQUE (document_id, render_kind, input_hash)` làm việc thêm idempotent — gọi lại trả chính dòng cũ.
`watermark_text` của dòng `document_render` = chuỗi đã nằm trong input của lần render (đi theo `DocxRender`; ADR-038) — **lời khai của tool, không phải kết quả đọc lại PDF**: runtime không đọc lại PDF. Việc kiểm `/Subject` bằng `pdfinfo` ở CI và
ở phép kiểm sau UAT (`tools/render-audit/`, mục 18 của 11-ops.md).

`object_metadata` (B9b2, ADR-041 mục 2): như ở `docx_render` — ba trường của bản ghim `ISSUED` trong cùng lệnh `PUT` của `.pdf`.

`audit_event`: `document.pdf_export`, cùng giao dịch với dòng `document_render`.
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from bo19.config import working_values as wv
from bo19.tool_layer.storage import ObjectStorage  # tên được tool_layer.storage mang ra: tool chỉ chạm object_storage qua module lưu trữ (contract object-storage)
from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
from bo19.persistence.write import unit_of_work
from bo19.tool_layer import storage as store
from bo19.tool_layer.kernel import audit
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_system
from bo19.tool_layer.rendering import convert, fonts
from bo19.tool_layer.tools._common import ToolError
from bo19.tool_layer.tools.docx_render import DocxRender, render_key

PDF_CONTENT_TYPE = "application/pdf"


class FontMissing(ToolError):
    code = "FONT_MISSING"

    def __init__(self, families: list[str]) -> None:
        super().__init__(",".join(families))
        self.families = tuple(families)  # tên họ font (không phải dữ liệu người dùng)


@dataclass(frozen=True)
class PdfExport:
    render_id: uuid.UUID
    docx_key: str
    pdf_key: str
    pdf_checksum: bytes
    reused: bool  # True: `.pdf` đã commit từ trước — không chuyển đổi lại


def pdf_export(pool: Pool, storage: ObjectStorage, ctx: ToolContext, docx: DocxRender, *, lease_s: float = 120, timeout_s: float = wv.RENDER_CONVERT_TIMEOUT_S,
               object_metadata: Mapping[str, str] | None = None) -> PdfExport:
    require_system(ctx)
    pdf_key = render_key(docx.document_id, docx.input_hash, "pdf")
    done = store.committed(pool, pdf_key)
    if done is not None:
        stored = done
    else:
        with pool.acquire() as conn, read_only(conn):
            row = conn.execute("SELECT required_fonts FROM template_version WHERE id = %s", (docx.template_version_id,)).fetchone()
        required = list(row[0]) if row else []
        lacking = fonts.missing(required)
        if lacking:
            raise FontMissing(lacking)  # TRƯỚC khi gọi soffice
        source = store.fetch(pool, storage, docx.docx_key, max_bytes=wv.FILE_FETCH_MAX_BYTES)
        pdf = convert.convert_to_pdf(source, timeout_s=timeout_s)  # chuyển đổi xong RỒI MỚI giành khoá
        stored = store.put_once(pool, storage, object_key=pdf_key, purpose="RENDER_PDF", content_type=PDF_CONTENT_TYPE, data=pdf, lease_s=lease_s, metadata=dict(object_metadata) if object_metadata else None)
    with pool.acquire() as conn, unit_of_work(conn):
        row = conn.execute("INSERT INTO document_render (id, document_id, operating_mode, render_kind, input_hash, template_version_id, revision_round, docx_object_key, pdf_object_key, watermark_text) "
                           "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (document_id, render_kind, input_hash) DO NOTHING RETURNING id",
                           (uuid.uuid4(), docx.document_id, docx.operating_mode, docx.render_kind, docx.input_hash, docx.template_version_id, docx.revision_round, docx.docx_key, pdf_key, docx.watermark_text)).fetchone()
        created = row is not None
        if row is None:
            row = conn.execute("SELECT id FROM document_render WHERE document_id = %s AND render_kind = %s AND input_hash = %s", (docx.document_id, docx.render_kind, docx.input_hash)).fetchone()
        render_id = row[0]
        audit.record(conn, ctx, action="document.pdf_export", entity_type="document", entity_id=docx.document_id, document_id=docx.document_id,
                     payload={"render_id": render_id, "render_kind": docx.render_kind, "revision_round": docx.revision_round, "created": created, "reused": stored.reused})
    return PdfExport(render_id, docx.docx_key, pdf_key, stored.checksum_sha256, reused=stored.reused)
