"""Router nhóm Hội thoại — bốn endpoint của mục Hội thoại của 05-api.md: `POST /chat-sessions`, `GET /chat-sessions/{id}`, `GET …/messages`, `POST …/turns` (SSE).

Quyền: người đăng nhập (đọc lại từ DB mỗi request — ADR-013) và **chủ phiên** — phiên không tồn tại và phiên của người khác cùng trả `NOT_FOUND`. Mọi ghi đi qua `tool_layer.endpoint_ops.chat`.
`POST …/turns`: ghi tin nhân viên và kiểm "lượt trước còn chạy" trong CÙNG một giao dịch dưới khoá phiên (`turn_guard_s`); rồi giao lượt cho bộ giám sát (`api/turns`, ADR-016) và trả stream — handler không chạy graph.
Lỗi **trước** khi stream bắt đầu trả JSON `ErrorEnvelope`; sau đó đi thành sự kiện `turn.error`.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from bo19.api import sse
from bo19.api.deps.session import current_employee
from bo19.api.deps.state import AppState, get_state
from bo19.api.errors import ApiError
from bo19.api.queries import chat as queries
from bo19.api.queries.auth import SessionEmployee
from bo19.api.schemas.chat import ChatMessagePageOut, ChatSessionOut, TurnBody, jsonable, message_out, session_out
from bo19.config import working_values as wv
from bo19.observability.trace import current_trace_id, new_trace_id
from bo19.tool_layer.endpoint_ops import chat as ops
from bo19.tool_layer.kernel.permission import PermissionDenied, employee_context

router = APIRouter(tags=["chat"])


def idempotency_key(value: str | None) -> uuid.UUID:
    if value is None or not value.strip():
        raise ApiError("IDEMPOTENCY_KEY_REQUIRED")
    try:
        return uuid.UUID(value.strip())
    except ValueError:
        raise ApiError("VALIDATION_FAILED", {"fields": [{"field": "Idempotency-Key", "code": "INVALID_FORMAT"}]}) from None


def _ctx(state: AppState, employee: SessionEmployee):
    with state.pool.acquire() as conn:
        return employee_context(conn, employee.id, current_trace_id())


def _denied(e: PermissionDenied) -> ApiError:
    return ApiError("PERMISSION_DENIED", {"permission": e.detail} if e.detail else None)


def _closed(state: AppState, employee: SessionEmployee, session_id: uuid.UUID) -> ApiError:
    with state.pool.acquire() as conn:
        row = queries.get_session(conn, session_id, employee.id)
    return ApiError("CHAT_SESSION_CLOSED", {"close_reason": row.close_reason} if row and row.close_reason else None)


@router.post("/chat-sessions")
def open_chat_session(idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"), employee: SessionEmployee = Depends(current_employee),
                      state: AppState = Depends(get_state)) -> Any:
    key = idempotency_key(idempotency_key_header)
    ctx = _ctx(state, employee)
    try:
        opened = ops.chat_session_open(state.pool, ctx, session_id=key)
    except PermissionDenied as e:
        raise _denied(e) from None
    except ops.SessionIdConflict:
        raise ApiError("IDEMPOTENCY_KEY_CONFLICT") from None
    with state.pool.acquire() as conn:
        row = queries.get_session(conn, opened.chat_session_id, employee.id)
    out = jsonable(session_out(row))
    status = 201 if opened.created or opened.replayed else 200  # lặp lại giữ mã HTTP của lần tạo đầu (mục 1.8 của 05-api.md)
    headers = {"Idempotent-Replayed": "true"} if opened.replayed else {}
    return JSONResponse(out, status_code=status, headers=headers)


@router.get("/chat-sessions/{chat_session_id}", response_model=ChatSessionOut)
def get_chat_session(chat_session_id: uuid.UUID, employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> ChatSessionOut:
    with state.pool.acquire() as conn:
        row = queries.get_session(conn, chat_session_id, employee.id)
    if row is None:
        raise ApiError("NOT_FOUND")
    return session_out(row)


@router.get("/chat-sessions/{chat_session_id}/messages", response_model=ChatMessagePageOut)
def list_chat_messages(chat_session_id: uuid.UUID, cursor: str | None = Query(None), limit: int = Query(wv.PAGE_LIMIT_DEFAULT, ge=1, le=wv.PAGE_LIMIT_MAX),
                       employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> ChatMessagePageOut:
    try:
        with state.pool.acquire() as conn:
            page = queries.list_messages(conn, chat_session_id, employee.id, limit=limit, cursor=cursor)
    except queries.BadCursor:
        raise ApiError("VALIDATION_FAILED", {"fields": [{"field": "cursor", "code": "INVALID_FORMAT"}]}) from None
    if page is None:
        raise ApiError("NOT_FOUND")
    items, next_cursor = page
    return ChatMessagePageOut(items=[message_out(m) for m in items], next_cursor=next_cursor)


# ----------------------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Accepted:
    started: bool  # true: lượt mới — giao cho bộ giám sát; false: lặp lại — đọc tin đã có từ DB
    reply_message_id: uuid.UUID | None


def accept_turn(state: AppState, employee: SessionEmployee, session_id: uuid.UUID, key: uuid.UUID, text: str) -> Accepted:
    """Phần đồng bộ của `POST …/turns`, chạy trong thread: ghi tin nhân viên (idempotent theo `key`), kiểm lượt trước, quyết lượt mới hay lặp lại."""
    guard_s = float(state.turn_deadline_s + state.turn_margin_s)  # hạn chót cộng biên an toàn (mục SSE của 05-api.md)
    ctx = _ctx(state, employee)
    try:
        appended = ops.chat_message_append(state.pool, ctx, chat_session_id=session_id, message_id=key, author="EMPLOYEE", body=text, turn_guard_s=guard_s)
    except PermissionDenied as e:
        raise _denied(e) from None
    except ops.ChatSessionNotFound:
        raise ApiError("NOT_FOUND") from None
    except ops.ChatSessionClosed:
        raise _closed(state, employee, session_id) from None
    except ops.MessageIdConflict:
        raise ApiError("IDEMPOTENCY_KEY_CONFLICT") from None
    except ops.TurnInProgress as e:
        raise ApiError("TURN_IN_PROGRESS", {"retry_after_seconds": e.retry_after_seconds}, {"Retry-After": str(e.retry_after_seconds)}) from None
    except ops.MessageInvalid:
        raise ApiError("VALIDATION_FAILED", {"fields": [{"field": "text", "code": "BLANK"}]}) from None
    if appended.created:
        return Accepted(True, None)
    status = ops.chat_turn_status(state.pool, ctx, chat_session_id=session_id, message_id=key)  # gửi lại cùng khoá
    if status.reply_message_id is not None:
        return Accepted(False, status.reply_message_id)
    abandoned = status.age_seconds > guard_s
    retry = max(1, int(guard_s - status.age_seconds) + 1)
    details = {"message_saved": True, "turn_abandoned": abandoned, **({} if abandoned else {"retry_after_seconds": retry})}
    raise ApiError("TURN_NOT_FINISHED", details, None if abandoned else {"Retry-After": str(retry)}, variant="abandoned" if abandoned else None)


@router.post("/chat-sessions/{chat_session_id}/turns")
async def post_chat_turn(chat_session_id: uuid.UUID, body: TurnBody, request: Request, idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
                         employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> StreamingResponse:
    if "text/event-stream" not in request.headers.get("accept", ""):
        raise ApiError("NOT_ACCEPTABLE")
    key = idempotency_key(idempotency_key_header)
    trace_id = current_trace_id() or new_trace_id()
    accepted = await asyncio.to_thread(accept_turn, state, employee, chat_session_id, key, body.text)
    if accepted.started:
        message = await asyncio.to_thread(_load_message, state.pool, chat_session_id, key)
        handle = state.supervisor.start(chat_session_id=chat_session_id, message_id=key, actor_employee_id=employee.id, trace_id=trace_id)
        stream = sse.relay(handle, [("turn.accepted", {"message": jsonable(message_out(message))})])
        return StreamingResponse(stream, media_type="text/event-stream", headers=sse.HEADERS)
    events = await asyncio.to_thread(_replayed_events, state, chat_session_id, key, accepted.reply_message_id, trace_id)
    return StreamingResponse(sse.replay(events), media_type="text/event-stream", headers={**sse.HEADERS, "Idempotent-Replayed": "true"})


def _load_message(pool: Any, session_id: uuid.UUID, message_id: uuid.UUID) -> queries.MessageRow:
    with pool.acquire() as conn:
        return queries.get_message(conn, session_id, message_id)


def _replayed_events(state: AppState, session_id: uuid.UUID, key: uuid.UUID, reply_id: uuid.UUID, trace_id: str) -> list[tuple[str, Any]]:
    """`turn.accepted` và `turn.reply` đọc từ DB. `active_request` và `pending_question` là tiện ích, không phải sự thật — không dựng lại được từ tin nhắn, nên `null` (mục SSE của 05-api.md)."""
    with state.pool.acquire() as conn:
        asked, reply = queries.get_message(conn, session_id, key), queries.get_message(conn, session_id, reply_id)
        request_id = reply.request_id or asked.request_id
        active = queries.request_summary(conn, request_id) if request_id else None
    return [("turn.accepted", {"message": jsonable(message_out(asked))}), ("turn.reply", {"message": jsonable(message_out(reply)), "active_request": active, "pending_question": None})]
