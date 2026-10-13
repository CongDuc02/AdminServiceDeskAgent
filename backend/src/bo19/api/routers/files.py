"""Router files — hai endpoint tải file của mục Tải file của 05-api.md (ADR-014; `operationId` `downloadRender`, `downloadTemplateSource`; thao tác `stored_file_fetch`, `SYNC_OBJECT_STORAGE`):

`GET /documents/{document_id}/renders/{render_id}/file?format=pdf|docx` · `GET /templates/{template_id}/versions/{template_version_id}/source`.

Quyền và so checksum nằm ở `tool_layer.endpoint_ops.files` — router chỉ dịch mã lỗi nội bộ sang `error_code` và dựng response. Mọi response: `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`,
`Content-Disposition: attachment` với tên file chỉ gồm id (không tên người, không giá trị biến). Lệch checksum, mất object, quá trần kích thước, storage không với tới, hay storage chưa cấu hình → cùng `FILE_UNAVAILABLE` (503):
client không phân biệt được; lý do chi tiết chỉ ở log và `audit_event` (mã).
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from bo19.api.deps.session import current_employee
from bo19.api.deps.state import AppState, get_state
from bo19.api.errors import ApiError
from bo19.api.queries.auth import SessionEmployee
from bo19.observability.log import get_logger
from bo19.observability.trace import current_trace_id
from bo19.tool_layer.endpoint_ops import files as ops
from bo19.tool_layer.kernel.permission import PermissionDenied, employee_context
from bo19.tool_layer.storage import FileUnavailable

router = APIRouter(tags=["files"])
log = get_logger("bo19.api")


def _response(file: ops.FetchedFile) -> Response:
    return Response(file.data, media_type=file.content_type, headers={"Content-Disposition": f'attachment; filename="{file.filename}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def _fetch(state: AppState, employee: SessionEmployee, call) -> Response:
    if state.storage is None:
        log.warning("FILE_FETCH_FAILED", reason="STORAGE_NOT_CONFIGURED")
        raise ApiError("FILE_UNAVAILABLE")
    with state.pool.acquire() as conn:
        ctx = employee_context(conn, employee.id, current_trace_id())
    try:
        return _response(call(ctx))
    except PermissionDenied as e:
        raise ApiError("PERMISSION_DENIED", {"permission": e.detail} if e.detail else None) from None
    except (ops.RenderNotFound, ops.TemplateVersionNotFound):
        raise ApiError("NOT_FOUND") from None
    except FileUnavailable:
        raise ApiError("FILE_UNAVAILABLE") from None


@router.get("/documents/{document_id}/renders/{render_id}/file")
def download_render(document_id: uuid.UUID, render_id: uuid.UUID, format: Literal["pdf", "docx"] = Query(...), employee: SessionEmployee = Depends(current_employee),
                    state: AppState = Depends(get_state)) -> Response:
    return _fetch(state, employee, lambda ctx: ops.render_file_fetch(state.pool, state.storage, ctx, document_id=document_id, render_id=render_id, fmt=format))


@router.get("/templates/{template_id}/versions/{template_version_id}/source")
def download_template_source(template_id: uuid.UUID, template_version_id: uuid.UUID, employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> Response:
    return _fetch(state, employee, lambda ctx: ops.template_source_fetch(state.pool, state.storage, ctx, template_id=template_id, template_version_id=template_version_id))
