"""Truy vấn của nhóm Hội thoại — chỉ qua `persistence.read` (mọi giao dịch `READ ONLY`). Mục Hội thoại của 05-api.md; mục Phân trang (keyset theo `seq` giảm dần, index `uq_chat_message_seq`).

Mọi hàm nhận `employee_id` của người đang đăng nhập và chỉ trả dòng của **chính phiên của họ**: phiên không tồn tại và phiên của người khác cho cùng kết quả `None` — không lộ sự tồn tại (`NOT_FOUND`).
`body` là `RES` (mục `chat_message` của 04-data.md): trả `None` khi đã bị xoá theo luật, kèm `content_erased`.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg

from bo19.domain.status_labels import request_status_label
from bo19.persistence.read import read_only


@dataclass(frozen=True)
class SessionRow:
    id: uuid.UUID
    status: str
    opened_at: dt.datetime
    last_message_at: dt.datetime
    closed_at: dt.datetime | None
    close_reason: str | None


@dataclass(frozen=True)
class MessageRow:
    id: uuid.UUID
    seq: int
    author: str
    request_id: uuid.UUID | None
    body: str | None = field(repr=False)  # RES
    content_erased: bool
    reply_template_id: str | None
    created_at: dt.datetime


class BadCursor(Exception):
    code = "BAD_CURSOR"


_SESSION = "SELECT id, status, opened_at, last_message_at, closed_at, close_reason FROM chat_session WHERE id = %s AND employee_id = %s"
_MESSAGE = "SELECT id, seq, author, request_id, body, content_erased_at IS NOT NULL, reply_template_id, created_at FROM chat_message"


def get_session(conn: psycopg.Connection, session_id: uuid.UUID, employee_id: uuid.UUID) -> SessionRow | None:
    with read_only(conn):
        row = conn.execute(_SESSION, (session_id, employee_id)).fetchone()
    return SessionRow(*row) if row else None


def get_message(conn: psycopg.Connection, session_id: uuid.UUID, message_id: uuid.UUID) -> MessageRow | None:
    with read_only(conn):
        row = conn.execute(_MESSAGE + " WHERE id = %s AND chat_session_id = %s", (message_id, session_id)).fetchone()
    return MessageRow(*row) if row else None


def encode_cursor(session_id: uuid.UUID, seq: int) -> str:
    """Cursor mờ: bộ khoá của dòng cuối (`seq`) cộng bộ lọc đã dùng (phiên) — dùng với phiên khác thì `BadCursor` (mục Phân trang của 05-api.md)."""
    return base64.urlsafe_b64encode(json.dumps({"s": str(session_id), "q": seq}, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(cursor: str, session_id: uuid.UUID) -> int:
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if raw["s"] != str(session_id) or not isinstance(raw["q"], int) or isinstance(raw["q"], bool) or raw["q"] < 1:
            raise BadCursor
        return raw["q"]
    except (ValueError, KeyError, TypeError):
        raise BadCursor from None


def list_messages(conn: psycopg.Connection, session_id: uuid.UUID, employee_id: uuid.UUID, *, limit: int, cursor: str | None) -> tuple[list[MessageRow], str | None] | None:
    """Tin nhắn mới nhất trước. `None` nếu phiên không phải của người này. `next_cursor` là `None` khi hết."""
    before = decode_cursor(cursor, session_id) if cursor else None
    with read_only(conn):
        if conn.execute("SELECT 1 FROM chat_session WHERE id = %s AND employee_id = %s", (session_id, employee_id)).fetchone() is None:
            return None
        rows = conn.execute(_MESSAGE + " WHERE chat_session_id = %s" + (" AND seq < %s" if before else "") + " ORDER BY seq DESC LIMIT %s",
                            (session_id, *([before] if before else []), limit + 1)).fetchall()
    items = [MessageRow(*r) for r in rows[:limit]]
    return items, (encode_cursor(session_id, items[-1].seq) if len(rows) > limit else None)


def request_summary(conn: psycopg.Connection, request_id: uuid.UUID) -> dict[str, Any] | None:
    """`RequestSummary` rút gọn của Sprint 1 (mục Triển khai ở B6b của 05-api.md): `artifacts` luôn `[]` vì chưa có `document`; `expires_at` và `submitted_at` theo cột của `request`.
    Chỉ gọi cho `request` mà lượt chat của chính người này đã mở/đụng tới — không phải đường đọc request tuỳ ý."""
    with read_only(conn):
        row = conn.execute(
            "SELECT r.id, r.request_type_code, t.name_vi, r.status, r.status_changed_at, r.created_at, r.created_by_employee_id, r.chat_session_id, r.row_version, "
            "b.id, b.employee_code, b.full_name, r.submitted_at, r.expires_at "
            "FROM request r JOIN request_type t ON t.code = r.request_type_code JOIN employee b ON b.id = r.beneficiary_employee_id WHERE r.id = %s", (request_id,)).fetchone()
    if row is None:
        return None
    (rid, type_code, type_name, status, changed, created, creator, session, version, b_id, b_code, b_name, submitted, expires) = row
    return {"id": str(rid), "request_type_code": type_code, "request_type_name": type_name, "status": status, "status_label": request_status_label(status),
            "status_changed_at": changed, "created_at": created, "created_by_employee_id": str(creator), "beneficiary": {"id": str(b_id), "employee_code": b_code, "full_name": b_name},
            "chat_session_id": str(session) if session else None, "submitted_at": submitted, "expires_at": expires, "row_version": version, "artifacts": []}
