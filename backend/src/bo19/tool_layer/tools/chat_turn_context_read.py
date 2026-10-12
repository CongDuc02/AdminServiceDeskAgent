"""`chat_turn_context_read` — cho `load_turn` đọc thứ mà state **không** được giữ (ADR-008): văn bản tin nhắn của lượt (`RES`) và `request` đang gắn với phiên (mục Tool Registry của 03-agents.md;
PO duyệt Q2, B6b).

**Chỉ tin `EMPLOYEE` của chính phiên, chủ phiên mới đọc.** Tin của agent, tin phiên khác và tin không tồn tại cho cùng một mã `MESSAGE_NOT_FOUND`; phiên không tồn tại và phiên của người khác cùng
`CHAT_SESSION_NOT_FOUND` — không lộ sự tồn tại. Lỗi không mang văn bản. Chỉ đọc: không `audit_event` (A-055 không áp cho thao tác đọc), giao dịch `READ ONLY`.

`request` gắn với phiên là cái **mới nhất** (`ix_request_chat_session`) ở **bất kỳ** trạng thái nào — `request` không bị gỡ khỏi phiên khi rời giai đoạn thu thập, để lần đổi trạng thái sau của nó
vẫn được báo qua `resume_context` (mục `intake_graph` của 03-agents.md). Văn bản đã bị xoá theo luật (`content_erased_at`) thì `body` là `None`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
from bo19.tool_layer.endpoint_ops.chat import ChatSessionNotFound
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_any
from bo19.tool_layer.tools._common import ToolError, actor_id


class MessageNotFound(ToolError):
    code = "MESSAGE_NOT_FOUND"


@dataclass(frozen=True)
class ActiveRequest:
    request_id: uuid.UUID
    request_type_code: str
    status: str
    row_version: int


@dataclass(frozen=True)
class TurnContext:
    message_id: uuid.UUID
    body: str | None = field(repr=False)  # RES — không bao giờ vào repr, log hay lỗi
    active_request: ActiveRequest | None


def chat_turn_context_read(pool: Pool, ctx: ToolContext, *, chat_session_id: uuid.UUID, message_id: uuid.UUID) -> TurnContext:
    me = actor_id(ctx)
    require_any(ctx, ("request.create", "request.create_on_behalf"))
    with pool.acquire() as conn, read_only(conn):
        session = conn.execute("SELECT employee_id FROM chat_session WHERE id = %s", (chat_session_id,)).fetchone()
        if session is None or session[0] != me:
            raise ChatSessionNotFound
        message = conn.execute("SELECT body FROM chat_message WHERE id = %s AND chat_session_id = %s AND author = 'EMPLOYEE'", (message_id, chat_session_id)).fetchone()
        if message is None:
            raise MessageNotFound
        request = conn.execute("SELECT id, request_type_code, status, row_version FROM request WHERE chat_session_id = %s ORDER BY created_at DESC, id DESC LIMIT 1", (chat_session_id,)).fetchone()
    return TurnContext(message_id, message[0], None if request is None else ActiveRequest(*request))
