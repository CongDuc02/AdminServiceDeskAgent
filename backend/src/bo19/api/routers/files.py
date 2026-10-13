"""Router files — hai endpoint tải file của mục Tải file của 05-api.md (ADR-014; `operationId` `downloadRender`, `downloadTemplateSource`; thao tác `stored_file_fetch`, `SYNC_OBJECT_STORAGE`):

`GET /documents/{document_id}/renders/{render_id}/file?format=pdf|docx` · `GET /templates/{template_id}/versions/{template_version_id}/source`.

Quyền và so checksum nằm ở `tool_layer.endpoint_ops.files` — router chỉ dịch mã lỗi nội bộ sang `error_code` và dựng response. **B8c (PO, 2026-10-13, O1-18):** endpoint `async`; chờ một chỗ ở `FileGate` (WV-27 lượt đồng thời, chờ tối đa WV-28),
rồi phần nặng chạy ở threadpool — tải về tệp tạm, băm, kiểm checksum, ghi `audit_event` — và stream từ tệp tạm trong `DeadlineStreamingResponse` (hạn chót tổng WV-29 bao cả pha stream). Chỗ được nhả và tệp được đóng **ở mọi lối thoát**: lỗi,
hết hạn, client ngắt. Mọi response: `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Content-Disposition: attachment` với tên file chỉ gồm id.

**`FILE_UNAVAILABLE` (503) có hai dạng, phân biệt bằng header, không lộ chi tiết:** hết chờ chỗ — **có** `Retry-After: <giây>` ("bận, thử lại"); lệch checksum, mất object, quá trần kích thước, storage không với tới, storage chưa cấu hình, hết hạn chót
trước khi gửi byte đầu tiên — **không** có `Retry-After`. Lý do chi tiết chỉ ở log và `audit_event` (mã).
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Literal

import anyio.to_thread
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from bo19.api.deps.session import current_employee
from bo19.api.deps.state import AppState, get_state
from bo19.api.errors import ApiError
from bo19.api.files_gate import Busy, DeadlineStreamingResponse, FileGate
from bo19.api.queries.auth import SessionEmployee
from bo19.observability.log import get_logger
from bo19.observability.trace import current_trace_id
from bo19.tool_layer.endpoint_ops import files as ops
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import PermissionDenied, employee_context
from bo19.tool_layer.storage import FileUnavailable

router = APIRouter(tags=["files"])
log = get_logger("bo19.api")


def _open(state: AppState, employee: SessionEmployee, call: Callable[[ToolContext, float], ops.FetchedStream], deadline: float) -> ops.FetchedStream:
    """Chạy ở threadpool: ngữ cảnh người dùng, kiểm quyền, tải về tệp tạm, kiểm checksum, audit. Lỗi nội bộ → `ApiError`; không lỗi thì người gọi sở hữu tệp."""
    with state.pool.acquire() as conn:
        ctx = employee_context(conn, employee.id, current_trace_id())
    try:
        return call(ctx, deadline)
    except PermissionDenied as e:
        raise ApiError("PERMISSION_DENIED", {"permission": e.detail} if e.detail else None) from None
    except (ops.RenderNotFound, ops.TemplateVersionNotFound):
        raise ApiError("NOT_FOUND") from None
    except FileUnavailable:
        raise ApiError("FILE_UNAVAILABLE") from None  # không Retry-After: file hỏng/mất/quá lớn/hết hạn, không phải "bận"


async def _serve(request: Request, state: AppState, employee: SessionEmployee, call: Callable[[ToolContext, float], ops.FetchedStream]) -> Response:
    if state.storage is None:
        log.warning("FILE_FETCH_FAILED", reason="STORAGE_NOT_CONFIGURED")
        raise ApiError("FILE_UNAVAILABLE")
    gate: FileGate = request.app.state.file_gate
    try:
        deadline = await gate.acquire()
    except Busy:
        raise ApiError("FILE_UNAVAILABLE", headers={"Retry-After": str(gate.limits.retry_after_s)}) from None
    handed_over = False
    try:
        stream = await anyio.to_thread.run_sync(_open, state, employee, call, deadline)
        try:
            if time.monotonic() >= deadline:  # tải xong đúng lúc hết hạn: không bắt đầu một response sẽ bị cắt ngay
                log.warning("FILE_FETCH_FAILED", reason="DEADLINE")
                raise ApiError("FILE_UNAVAILABLE")
            response = DeadlineStreamingResponse(stream.file, size=stream.size, media_type=stream.content_type, deadline=deadline, chunk_bytes=gate.limits.chunk_bytes, gate=gate,
                                                 headers={"Content-Disposition": f'attachment; filename="{stream.filename}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
        except BaseException:
            stream.file.close()
            raise
        handed_over = True  # từ đây `DeadlineStreamingResponse` đóng tệp và nhả chỗ
        return response
    finally:
        if not handed_over:
            gate.release()


@router.get("/documents/{document_id}/renders/{render_id}/file")
async def download_render(request: Request, document_id: uuid.UUID, render_id: uuid.UUID, format: Literal["pdf", "docx"] = Query(...),
                          employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> Response:
    return await _serve(request, state, employee, lambda ctx, deadline: ops.render_file_open(state.pool, state.storage, ctx, document_id=document_id, render_id=render_id, fmt=format, deadline=deadline))


@router.get("/templates/{template_id}/versions/{template_version_id}/source")
async def download_template_source(request: Request, template_id: uuid.UUID, template_version_id: uuid.UUID, employee: SessionEmployee = Depends(current_employee),
                                   state: AppState = Depends(get_state)) -> Response:
    return await _serve(request, state, employee, lambda ctx, deadline: ops.template_source_open(state.pool, state.storage, ctx, template_id=template_id, template_version_id=template_version_id, deadline=deadline))
