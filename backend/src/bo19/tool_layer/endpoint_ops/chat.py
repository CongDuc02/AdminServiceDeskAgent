"""`chat_session_open` và `chat_message_append` — hai thao tác do endpoint gọi (mục 5.7 của 03-agents.md; `POST /chat-sessions`, `POST /chat-sessions/{id}/turns`).

Cả hai thuộc danh sách **miễn `audit_event`** (A-055, loại "hội thoại"): mở phiên không đổi dữ liệu nghiệp vụ; nội dung tin nhắn có bảng và thời hạn lưu riêng (A-010) — việc nghiệp vụ bắt đầu ở
`request_open`, vẫn sinh `audit_event`.

`chat_session_open`: trả phiên `OPEN` của nhân viên nếu có, không thì tạo; khoá hàng `employee` để hai lời gọi đồng thời không tạo hai phiên.
`chat_message_append`: `id` do người gọi cấp (= `Idempotency-Key` của lượt) nên gọi lại là không làm gì; `seq` cấp dưới khoá hàng `chat_session`; `body` lưu dạng **NFC**. Tin của nhân viên do chủ phiên
ghi; tin của agent do tác nhân hệ thống ghi, **bắt buộc** mang mã khuôn (`reply_template_id`) và tin của nhân viên **không được** mang — khớp `ck_chat_message_template_only_agent`.

**Một tin agent cho mỗi tin nhân viên (B6b, migration 0012):** tin agent có thể mang `in_reply_to_message_id` — tin `EMPLOYEE` của chính phiên (tool kiểm dưới khoá phiên; DB giữ "cùng phiên" bằng khoá
ngoại ghép). Đã có tin agent cho tin đó thì không ghi thêm: trả tin cũ (`created = False`). Nếu hai bên vẫn cùng chạm tới `INSERT` (chỉ khi có đường ghi vòng khoá phiên), `UNIQUE` từng phần của DB từ chối
một bên và tool trả tin đã có — "đúng một tin agent mỗi lượt" do DB giữ, không dựa vào thời điểm của cờ huỷ hay của bộ giám sát.
"""
from __future__ import annotations

import math
import re
import unicodedata
import uuid
from dataclasses import dataclass

import psycopg

from bo19.config import working_values as wv
from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
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


class SessionIdConflict(ToolError):
    code = "SESSION_ID_CONFLICT"  # `Idempotency-Key` của `POST /chat-sessions` đã là phiên của người khác


class TurnInProgress(ToolError):
    """Lượt trước chưa có câu trả lời và còn trong hạn chót (mục SSE của 05-api.md). `retry_after_seconds` — số nguyên ≥ 1, làm tròn lên."""

    code = "TURN_IN_PROGRESS"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__()
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class SessionOpen:
    chat_session_id: uuid.UUID
    created: bool  # phiên mới do lần gọi này tạo
    replayed: bool = False  # `session_id` (Idempotency-Key) đã là một phiên của chính người gọi — lặp lại hợp lệ của lần tạo trước


@dataclass(frozen=True)
class Appended:
    message_id: uuid.UUID
    seq: int
    created: bool


def chat_session_open(pool: Pool, ctx: ToolContext, *, session_id: uuid.UUID | None = None) -> SessionOpen:
    """`session_id` — `Idempotency-Key` của `POST /chat-sessions`: id của phiên MỚI nếu phải tạo (mục 1.8 của 05-api.md). Đã là phiên của chính người gọi thì đây là lặp lại: trả phiên đó, `replayed`.
    Của người khác thì `SessionIdConflict` — không trả gì về phiên đó."""
    me = actor_id(ctx)
    require_any(ctx, ("request.create", "request.create_on_behalf"))
    with pool.acquire() as conn, unit_of_work(conn):
        conn.execute("SELECT id FROM employee WHERE id = %s FOR UPDATE", (me,))
        if session_id is not None:
            keyed = conn.execute("SELECT employee_id FROM chat_session WHERE id = %s", (session_id,)).fetchone()
            if keyed is not None:
                if keyed[0] != me:
                    raise SessionIdConflict
                return SessionOpen(session_id, False, True)
        row = conn.execute("SELECT id FROM chat_session WHERE employee_id = %s AND status = 'OPEN' ORDER BY opened_at DESC LIMIT 1", (me,)).fetchone()
        if row is not None:
            return SessionOpen(row[0], False)
        new_id = session_id or uuid.uuid4()
        conn.execute("INSERT INTO chat_session (id, employee_id) VALUES (%s, %s)", (new_id, me))
        return SessionOpen(new_id, True)


@dataclass(frozen=True)
class TurnStatus:
    reply_message_id: uuid.UUID | None  # tin agent đã trả lời tin nhân viên này, nếu có
    age_seconds: float  # tuổi của tin nhân viên, đo bằng đồng hồ của DB


def chat_turn_status(pool: Pool, ctx: ToolContext, *, chat_session_id: uuid.UUID, message_id: uuid.UUID) -> TurnStatus:
    """Chỉ đọc: lượt của tin nhân viên này đã có câu trả lời chưa, và tin đã được bao lâu — cho phát lại và `TURN_NOT_FINISHED` (mục SSE của 05-api.md). Chủ phiên mới đọc."""
    me = actor_id(ctx)
    require_any(ctx, ("request.create", "request.create_on_behalf"))
    with pool.acquire() as conn, read_only(conn):
        row = conn.execute("SELECT s.employee_id, m.author, extract(epoch FROM now() - m.created_at), "
                           "(SELECT a.id FROM chat_message a WHERE a.in_reply_to_message_id = m.id AND a.author = 'AGENT') "
                           "FROM chat_session s JOIN chat_message m ON m.chat_session_id = s.id WHERE s.id = %s AND m.id = %s", (chat_session_id, message_id)).fetchone()
    if row is None or row[0] != me or row[1] != "EMPLOYEE":
        raise ChatSessionNotFound
    return TurnStatus(row[3], float(row[2]))


def _agent_reply(conn: psycopg.Connection, employee_message_id: uuid.UUID) -> tuple[uuid.UUID, int] | None:
    """(id, seq) của tin agent đã trả lời tin nhân viên này, nếu có."""
    row = conn.execute("SELECT id, seq FROM chat_message WHERE in_reply_to_message_id = %s AND author = 'AGENT'", (employee_message_id,)).fetchone()
    return None if row is None else (row[0], row[1])


def chat_message_append(pool: Pool, ctx: ToolContext, *, chat_session_id: uuid.UUID, message_id: uuid.UUID, author: str, body: str, reply_template_id: str | None = None,
                        request_id: uuid.UUID | None = None, in_reply_to_message_id: uuid.UUID | None = None, turn_guard_s: float | None = None) -> Appended:
    if author == "EMPLOYEE":
        me = actor_id(ctx)
        require_any(ctx, ("request.create", "request.create_on_behalf"))
        if reply_template_id is not None or in_reply_to_message_id is not None:
            raise MessageInvalid("template" if reply_template_id is not None else "reply_to")
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
        if in_reply_to_message_id is not None:
            target = conn.execute("SELECT author FROM chat_message WHERE id = %s AND chat_session_id = %s", (in_reply_to_message_id, chat_session_id)).fetchone()
            if target is None or target[0] != "EMPLOYEE":
                raise MessageInvalid("reply_to")  # chỉ trả lời tin của nhân viên, trong chính phiên này
            answered = _agent_reply(conn, in_reply_to_message_id)
            if answered is not None:
                return Appended(answered[0], answered[1], False)  # đã có câu trả lời: không ghi thêm, trả tin cũ
        if session[1] != "OPEN":
            raise ChatSessionClosed
        if turn_guard_s is not None and author == "EMPLOYEE":
            pending = conn.execute("SELECT extract(epoch FROM now() - m.created_at) FROM chat_message m WHERE m.chat_session_id = %s AND m.author = 'EMPLOYEE' "
                                   "AND NOT EXISTS (SELECT 1 FROM chat_message a WHERE a.in_reply_to_message_id = m.id AND a.author = 'AGENT') ORDER BY m.seq DESC LIMIT 1", (chat_session_id,)).fetchone()
            if pending is not None and float(pending[0]) <= turn_guard_s:
                raise TurnInProgress(max(1, math.ceil(turn_guard_s - float(pending[0]))))  # lượt trước còn trong hạn chót: không nhận lượt mới (kiểm và ghi cùng một giao dịch dưới khoá phiên)
        seq = conn.execute("SELECT coalesce(max(seq), 0) + 1 FROM chat_message WHERE chat_session_id = %s", (chat_session_id,)).fetchone()[0]
        try:
            with conn.transaction():  # savepoint: unique_violation không làm hỏng giao dịch ngoài
                conn.execute("INSERT INTO chat_message (id, chat_session_id, seq, author, request_id, body, reply_template_id, in_reply_to_message_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                             (message_id, chat_session_id, seq, author, request_id, text, reply_template_id, in_reply_to_message_id))
        except psycopg.errors.UniqueViolation:
            answered = _agent_reply(conn, in_reply_to_message_id) if in_reply_to_message_id is not None else None
            if answered is None:
                raise  # trùng khoá khác (id, seq) — không phải ca "đã có câu trả lời"
            return Appended(answered[0], answered[1], False)
        conn.execute("UPDATE chat_session SET last_message_at = now(), updated_at = now(), row_version = row_version + 1 WHERE id = %s", (chat_session_id,))
        return Appended(message_id, seq, True)
