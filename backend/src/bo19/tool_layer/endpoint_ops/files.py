"""`stored_file_fetch` — tải bản render và bản gốc template qua API (mục Tải file của 05-api.md; ADR-014; mục Tool Registry của 03-agents.md, nơi nó là thao tác **đọc duy nhất** sinh `audit_event`).

Hai thao tác do endpoint gọi, cùng một đường: kiểm quyền → `storage.fetch_verified` (**tải theo khối vào tệp tạm vô danh, băm khi tải, so checksum — chỉ khi khớp mới trả tệp**; trần kích thước WV-24; B8c, O1-18) → ghi `audit_event` của lần tải → trả tệp đã tua về đầu.
Người nhận `FetchedStream` **phải đóng `file`** ở mọi lối thoát (router giao việc đó cho `DeadlineStreamingResponse`); bộ nhớ không theo kích thước file.

**Quyền xem `document_render` đi theo quyền xem `document` của nó** (mục Bảo vệ dữ liệu của 09-security.md — không có permission riêng, không có ngoại lệ "bản nháp thì lỏng hơn"):
- `request.read_all`: mọi bản, cả hai định dạng;
- `request.read_assigned`: mọi bản, cả hai định dạng, **khi có một `approval_step` giao cho chính mình trên văn bản đó** (`OPEN` hoặc `DECIDED`; bước `CANCELLED` không còn là việc được giao — diễn giải của B8b, ghi ở 05-api.md). Uỷ quyền `[Should]` chưa tính;
- người tạo yêu cầu (`request.read_own`): **chỉ bản `FINAL`, chỉ `pdf`, chỉ khi `document` đã `ISSUED` hoặc ở trạng thái sau đó, và chỉ bản mà `document.final_render_id` trỏ tới** (một dòng `FINAL` rơi rớt của lần phát hành bỏ cuộc không ra được). Sai điều nào là `PermissionDenied`
  (AC-1.3: "tải `docx` hay bản nháp trả lỗi quyền");
- người không có quan hệ nào với văn bản: `RenderNotFound` — cùng mã với "không tồn tại", không lộ sự tồn tại.

**Lỗi tải gộp một mã** (`FILE_UNAVAILABLE`): mất object, lệch checksum, quá trần, storage không với tới — client không phân biệt được. Lần tải hỏng vẫn để lại một `audit_event` mức `WARNING` (`outcome = FILE_UNAVAILABLE`, không kèm lý do chi tiết:
lý do chỉ ở log). `audit_event` chỉ mang mã và tham chiếu — không tên file, không byte, không giá trị biến.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import IO

from bo19.config import working_values as wv
from bo19.tool_layer.storage import ObjectStorage  # tên được tool_layer.storage mang ra: tool chỉ chạm object_storage qua module lưu trữ (contract object-storage)
from bo19.observability.log import get_logger
from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
from bo19.persistence.write import unit_of_work
from bo19.tool_layer import storage as store
from bo19.tool_layer.kernel import audit
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import PermissionDenied, require
from bo19.tool_layer.tools._common import ToolError

log = get_logger("bo19.files")

READ_ALL, READ_ASSIGNED, READ_OWN, TEMPLATE_MANAGE = "request.read_all", "request.read_assigned", "request.read_own", "template.manage"
FORMATS = ("pdf", "docx")
AFTER_ISSUE = ("ISSUED", "REVOKED", "SUPERSEDED", "ARCHIVED")  # "ISSUED hoặc ở trạng thái sau đó" (mục Tải file của 05-api.md)
CONTENT_TYPES = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


class RenderNotFound(ToolError):
    code = "RENDER_NOT_FOUND"  # không tồn tại và "không có quan hệ" cùng một mã


class TemplateVersionNotFound(ToolError):
    code = "TEMPLATE_VERSION_NOT_FOUND"


@dataclass(frozen=True)
class FetchedStream:
    file: IO[bytes]  # đã kiểm checksum, đã tua về đầu; người nhận đóng
    size: int
    content_type: str
    filename: str  # chỉ mã và id — không tên người, không giá trị slot


_RENDER = ("SELECT r.render_kind, r.docx_object_key, r.pdf_object_key, d.status, d.final_render_id, q.created_by_employee_id FROM document_render r "
           "JOIN document d ON d.id = r.document_id JOIN request q ON q.id = d.request_id WHERE r.id = %s AND r.document_id = %s")
_ASSIGNED = "SELECT EXISTS (SELECT 1 FROM approval_step WHERE document_id = %s AND assignee_employee_id = %s AND status <> 'CANCELLED')"


def _employee(ctx: ToolContext) -> uuid.UUID:
    if ctx.actor.employee_id is None:
        raise PermissionDenied  # tải file là việc của người thật; tác nhân hệ thống đọc qua `storage.fetch`
    return ctx.actor.employee_id


def _audit(pool: Pool, ctx: ToolContext, *, entity_type: str, entity_id: uuid.UUID, document_id: uuid.UUID | None, payload: dict, severity: str = "INFO") -> None:
    with pool.acquire() as conn, unit_of_work(conn):
        audit.record(conn, ctx, action="document.file_fetch" if entity_type == "document_render" else "template_version.source_fetch", entity_type=entity_type, entity_id=entity_id,
                     document_id=document_id, payload=payload, severity=severity)


def _fetch_audited(pool: Pool, storage: ObjectStorage, ctx: ToolContext, key: str, *, entity_type: str, entity_id: uuid.UUID, document_id: uuid.UUID | None, payload: dict,
                   deadline: float | None) -> tuple[IO[bytes], int]:
    try:
        spool, size = store.fetch_verified(pool, storage, key, max_bytes=wv.FILE_FETCH_MAX_BYTES, chunk_bytes=wv.FILE_FETCH_CHUNK_BYTES, deadline=deadline)
    except store.FileUnavailable as e:
        log.warning("FILE_FETCH_FAILED", entity_type=entity_type, entity_id=str(entity_id), reason=e.reason)  # lý do chỉ ở log
        _audit(pool, ctx, entity_type=entity_type, entity_id=entity_id, document_id=document_id, payload={**payload, "outcome": "FILE_UNAVAILABLE"}, severity="WARNING")
        raise
    try:
        _audit(pool, ctx, entity_type=entity_type, entity_id=entity_id, document_id=document_id, payload={**payload, "outcome": "OK", "size_bytes": size})
    except BaseException:
        spool.close()  # không ghi được dấu vết thì không giao file — và không để lại tệp
        raise
    return spool, size


def render_file_open(pool: Pool, storage: ObjectStorage, ctx: ToolContext, *, document_id: uuid.UUID, render_id: uuid.UUID, fmt: str, deadline: float | None = None) -> FetchedStream:
    if fmt not in FORMATS:
        raise ValueError("format")
    me = _employee(ctx)
    with pool.acquire() as conn, read_only(conn):
        row = conn.execute(_RENDER, (render_id, document_id)).fetchone()
        if row is None:
            raise RenderNotFound
        kind, docx_key, pdf_key, doc_status, final_render_id, creator = row
        assigned = READ_ASSIGNED in ctx.actor.permissions and conn.execute(_ASSIGNED, (document_id, me)).fetchone()[0]
    perms = ctx.actor.permissions
    if READ_ALL in perms or assigned:
        pass
    elif READ_OWN in perms and creator == me:
        if not (kind == "FINAL" and fmt == "pdf" and doc_status in AFTER_ISSUE and final_render_id == render_id):
            raise PermissionDenied
    else:
        raise RenderNotFound
    spool, size = _fetch_audited(pool, storage, ctx, pdf_key if fmt == "pdf" else docx_key, entity_type="document_render", entity_id=render_id, document_id=document_id,
                                 payload={"format": fmt, "render_kind": kind}, deadline=deadline)
    return FetchedStream(spool, size, CONTENT_TYPES[fmt], f"{document_id}-{kind.lower()}.{fmt}")


def template_source_open(pool: Pool, storage: ObjectStorage, ctx: ToolContext, *, template_id: uuid.UUID, template_version_id: uuid.UUID, deadline: float | None = None) -> FetchedStream:
    _employee(ctx)
    require(ctx, TEMPLATE_MANAGE)
    with pool.acquire() as conn, read_only(conn):
        row = conn.execute("SELECT source_object_key, version_no FROM template_version WHERE id = %s AND template_id = %s", (template_version_id, template_id)).fetchone()
    if row is None:
        raise TemplateVersionNotFound
    key, version_no = row
    spool, size = _fetch_audited(pool, storage, ctx, key, entity_type="template_version", entity_id=template_version_id, document_id=None,
                                 payload={"template_id": template_id, "version_no": version_no}, deadline=deadline)
    return FetchedStream(spool, size, CONTENT_TYPES["docx"], f"{template_id}-v{version_no}.docx")
