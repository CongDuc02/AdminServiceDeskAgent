"""Tool `render_integrity_check` — kiểm **toàn vẹn byte** của một bản render, ngay trước người hay bước đầu tiên dựa vào byte của nó (mục Tool Registry của 03-agents.md; mục 5.4 của 04-data.md; ADR-040).

Đọc lại **cả hai** object (`.docx` và `.pdf`) của `document_render` và so với checksum đã commit ở `stored_object_commit` — `storage.fetch_verified`: tải theo khối vào tệp tạm, băm khi tải, đóng ngay; không giữ object trong bộ nhớ.
Gọi ở `route_signing` trên **bản đã duyệt nội dung**, trước `signing_route` (người ký là người đầu tiên dựa vào byte); `finalize_issue` gọi lại trên bản cuối (B9b2). Chỉ tác nhân hệ thống; **chỉ đọc**, không `audit_event`.

Lỗi (mã nội bộ, không ra `error_code` của 05-api.md): `RENDER_CHECKSUM_MISMATCH` (byte đọc lại không khớp checksum đã commit) · `RENDER_OBJECT_MISSING` (object mất, chưa commit, hay storage không với tới — lý do chi tiết
chỉ ở log của `storage`). Cả hai là lỗi tạm theo `failure.classify`: khôi phục byte rồi thử lại (mục Sau khi trượt kiểm của 04-data.md).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from bo19.config import working_values as wv
from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
from bo19.tool_layer import storage as store
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_system
from bo19.tool_layer.storage import ObjectStorage  # tên được tool_layer.storage mang ra: tool chỉ chạm object_storage qua module lưu trữ (contract object-storage)
from bo19.tool_layer.tools._common import ToolError


class RenderNotFound(ToolError):
    code = "RENDER_NOT_FOUND"


class RenderChecksumMismatch(ToolError):
    code = "RENDER_CHECKSUM_MISMATCH"


class RenderObjectMissing(ToolError):
    code = "RENDER_OBJECT_MISSING"


@dataclass(frozen=True)
class IntegrityChecked:
    render_id: uuid.UUID
    objects: int  # số object đã đọc lại và khớp (luôn 2: `.docx` và `.pdf`)


def render_integrity_check(pool: Pool, storage: ObjectStorage, ctx: ToolContext, *, render_id: uuid.UUID) -> IntegrityChecked:
    require_system(ctx)
    with pool.acquire() as conn, read_only(conn):
        row = conn.execute("SELECT docx_object_key, pdf_object_key FROM document_render WHERE id = %s", (render_id,)).fetchone()
    if row is None:
        raise RenderNotFound
    checked = 0
    for key in row:
        try:
            spool, _ = store.fetch_verified(pool, storage, key, max_bytes=wv.FILE_FETCH_MAX_BYTES)
        except store.FileUnavailable as e:
            raise (RenderChecksumMismatch if e.reason == "CHECKSUM_MISMATCH" else RenderObjectMissing) from None
        spool.close()
        checked += 1
    return IntegrityChecked(render_id, checked)
