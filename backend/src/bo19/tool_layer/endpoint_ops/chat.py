"""`chat_session_open` và `chat_message_append` — hai thao tác do endpoint gọi (mục 5.7 của 03-agents.md; `POST /chat-sessions`, `POST /chat-sessions/{id}/turns`).

Cả hai thuộc danh sách **miễn `audit_event`** (A-055, loại "hội thoại"): mở phiên không đổi dữ liệu nghiệp vụ; nội dung tin nhắn có bảng và thời hạn lưu riêng (A-010) — việc nghiệp vụ bắt đầu ở
`request_open`, vẫn sinh `audit_event`.

`chat_session_open`: trả phiên `OPEN` của nhân viên nếu có, không thì tạo; khoá hàng `employee` để hai lời gọi đồng thời không tạo hai phiên.
`chat_message_append`: `id` do người gọi cấp (= `Idempotency-Key` của lượt) nên gọi lại là không làm gì; `seq` cấp dưới khoá hàng `chat_session`; `body` lưu dạng **NFC**. Tin của nhân viên do chủ phiên
ghi; tin của agent do tác nhân hệ thống ghi, **bắt buộc** mang mã khuôn (`reply_template_id`) và tin của nhân viên **không được** mang — khớp `ck_chat_message_template_only_agent`.
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass

from bo19.config import working_values as wv
from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_any, require_system
from bo19.tool_layer.tools._common import ToolError, actor_id

_TEMPLATE_ID = re.compile(r"^[A-Z][A-Z0-9_]*$")


class ChatSessionNotFound(ToolError):
    code = "CHAT_SESSION_NOT_FOUND"  # không tồn tại và của người khác cùng một mã


class ChatSessionClosed(ToolError):
    code = "CHAT_SESSION_CLOSED"


class MessageInvalid(ToolError):
    code = "MESSAGE_INVALID"


class MessageIdConflict(ToolError):
    code = "MESSAGE_ID_CONFLICT"


@dataclass(frozen=True)
class SessionOpen:
    chat_session_id: uuid.UUID
    created: bool


@dataclass(frozen=True)
class Appended:
    message_id: uuid.UUID
    seq: int
    created: bool


def chat_session_open(pool: Pool, ctx: ToolContext) -> SessionOpen:
    me = actor_id(ctx)
    require_any(ctx, ("request.create", "request.create_on_behalf"))
    with pool.acquire() as conn, unit_of_work(conn):
        conn.execute("SELECT id FROM employee WHERE id = %s FOR UPDATE", (me,))
        row = conn.execute("SELECT id FROM chat_session WHERE employee_id = %s AND status = 'OPEN' ORDER BY opened_at DESC LIMIT 1", (me,)).fetchone()
        if row is not None:
            return SessionOpen(row[0], False)
        session_id = uuid.uuid4()
        conn.execute("INSERT INTO chat_session (id, employee_id) VALUES (%s, %s)", (session_id, me))
        return SessionOpen(session_id, True)


def chat_message_append(pool: Pool, ctx: ToolContext, *, chat_session_id: uuid.UUID, message_id: uuid.UUID, author: str, body: str, reply_template_id: str | None = None,
                        request_id: uuid.UUID | None = None) -> Appended:
    if author == "EMPLOYEE":
        me = actor_id(ctx)
        require_any(ctx, ("request.create", "request.create_on_behalf"))
        if reply_template_id is not None:
            raise MessageInvalid("template")
    elif author == "AGENT":
        require_system(ctx)
        if reply_template_id is None or not _TEMPLATE_ID.match(reply_template_id):
            raise MessageInvalid("template")
        me = None
    else:
        raise MessageInvalid("author")
    text = unicodedata.normalize("NFC", body)
    if not text.strip() or len(text) > wv.CHAT_MESSAGE_MAX_CHARS:
        raise MessageInvalid("body")
    with pool.acquire() as conn, unit_of_work(conn):
        session = conn.execute("SELECT employee_id, status FROM chat_session WHERE id = %s FOR UPDATE", (chat_session_id,)).fetchone()
        if session is None or (author == "EMPLOYEE" and session[0] != me):
            raise ChatSessionNotFound
        existing = conn.execute("SELECT chat_session_id, author, seq FROM chat_message WHERE id = %s", (message_id,)).fetchone()
        if existing is not None:
            if existing[0] != chat_session_id or existing[1] != author:
                raise MessageIdConflict
            return Appended(message_id, existing[2], False)
        if session[1] != "OPEN":
            raise ChatSessionClosed
        seq = conn.execute("SELECT coalesce(max(seq), 0) + 1 FROM chat_message WHERE chat_session_id = %s", (chat_session_id,)).fetchone()[0]
        conn.execute("INSERT INTO chat_message (id, chat_session_id, seq, author, request_id, body, reply_template_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                     (message_id, chat_session_id, seq, author, request_id, text, reply_template_id))
        conn.execute("UPDATE chat_session SET last_message_at = now(), updated_at = now(), row_version = row_version + 1 WHERE id = %s", (chat_session_id,))
        return Appended(message_id, seq, True)
