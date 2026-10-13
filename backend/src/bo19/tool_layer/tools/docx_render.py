"""Tool `docx_render` — điền bảng giá trị biến vào phiên bản template, ghi `.docx` một lần (mục Tool Registry của 03-agents.md, mục 5.6; ADR-001, ADR-003; mục Lưu trữ file và bất biến bản render của 04-data.md).

Chỉ **tác nhân hệ thống** (`require_system`). Đọc `operating_mode` và `template_version_id` **từ `document`** — không nhận từ người gọi, nên không có đường tắt watermark (`docx_fill`).

**Bảng giá trị biến là tham số** (`values`, B8b — PO duyệt kế hoạch 2026-10-13): việc DỰNG nó (giá trị `DIRECT_SLOT` từ slot đã xác nhận, `FREE_CONTENT` từ `document_free_content`, `SYSTEM` từ số văn bản, ngày, người ký)
thuộc lớp trên — `review_readiness_check` và `document_graph` ở B9a. Tool chỉ kiểm bảng ấy khớp phiên bản template (`MISSING_VARIABLE`, `UNKNOWN_VARIABLE`).

**Khoá object theo INPUT** (mục 5.6 của 03-agents.md): `renders/{document_id}/{input_hash}.docx`, `input_hash` = sha256 của JSON chuẩn tắc của (phiên bản template, bảng giá trị, `operating_mode`) — không phải của byte đầu ra, nên
timestamp hay metadata mà thư viện nhúng vào file không làm khoá lệch. Khoá đã có commit thì **không điền lại, không ghi lại** (ghi một lần; `reused = True`).

`TEMPLATE_NOT_ACTIVE`: bản `DRAFT` chỉ render từ phiên bản `ACTIVE`; bản `FINAL` còn render được từ phiên bản `RETIRED` (văn bản đã duyệt bằng phiên bản đó có thể đã bị thay từ lúc duyệt — `finalize_issue` render lại đúng nó,
ADR-015 chốt 3), nhưng không từ phiên bản `UPLOADED`.

`audit_event`: một dòng `document.docx_render` mỗi lần gọi (mã và tham chiếu, không giá trị). Lỗi chỉ mang mã và TÊN biến.
"""
from __future__ import annotations

import hashlib
import json
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
from bo19.tool_layer.rendering import docx_fill
from bo19.tool_layer.tools._common import ToolError

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
RENDER_KINDS = ("DRAFT", "FINAL")


class DocumentNotFound(ToolError):
    code = "DOCUMENT_NOT_FOUND"


class TemplateNotActive(ToolError):
    code = "TEMPLATE_NOT_ACTIVE"


@dataclass(frozen=True)
class DocxRender:
    document_id: uuid.UUID
    render_kind: str
    operating_mode: str
    template_version_id: uuid.UUID
    revision_round: int
    input_hash: bytes
    docx_key: str
    docx_checksum: bytes
    reused: bool


def input_hash(template_version_id: uuid.UUID, values: Mapping[str, str], operating_mode: str) -> bytes:
    canonical = json.dumps({"template_version_id": str(template_version_id), "values": dict(sorted(values.items())), "operating_mode": operating_mode},
                           ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).digest()


def render_key(document_id: uuid.UUID, digest: bytes, extension: str) -> str:
    return f"renders/{document_id}/{digest.hex()}.{extension}"


def docx_render(pool: Pool, storage: ObjectStorage, ctx: ToolContext, *, document_id: uuid.UUID, render_kind: str, values: Mapping[str, str],
                lease_s: float = 120) -> DocxRender:
    require_system(ctx)
    if render_kind not in RENDER_KINDS:
        raise ValueError("render_kind")
    with pool.acquire() as conn, read_only(conn):
        doc = conn.execute("SELECT d.operating_mode, d.template_version_id, d.revision_round, tv.status, tv.source_object_key FROM document d JOIN template_version tv ON tv.id = d.template_version_id "
                           "WHERE d.id = %s", (document_id,)).fetchone()
        if doc is None:
            raise DocumentNotFound
        mode, version_id, round_, tv_status, source_key = doc
        declared = [r[0] for r in conn.execute("SELECT variable_name FROM template_variable WHERE template_version_id = %s", (version_id,)).fetchall()]
    if tv_status not in (("ACTIVE",) if render_kind == "DRAFT" else ("ACTIVE", "RETIRED")):
        raise TemplateNotActive
    digest = input_hash(version_id, values, mode)
    key = render_key(document_id, digest, "docx")
    done = store.committed(pool, key)
    if done is not None:
        result = DocxRender(document_id, render_kind, mode, version_id, round_, digest, key, done.checksum_sha256, reused=True)
    else:
        template = store.fetch(pool, storage, source_key, max_bytes=wv.FILE_FETCH_MAX_BYTES)
        data = docx_fill.fill_docx(template, values, declared=declared, operating_mode=mode)
        stored = store.put_once(pool, storage, object_key=key, purpose="RENDER_DOCX", content_type=DOCX_CONTENT_TYPE, data=data, lease_s=lease_s)
        result = DocxRender(document_id, render_kind, mode, version_id, round_, digest, key, stored.checksum_sha256, reused=stored.reused)
    with pool.acquire() as conn, unit_of_work(conn):
        audit.record(conn, ctx, action="document.docx_render", entity_type="document", entity_id=document_id, document_id=document_id,
                     payload={"render_kind": render_kind, "revision_round": round_, "template_version_id": version_id, "operating_mode": mode, "input_hash": digest.hex(), "reused": result.reused})
    return result
