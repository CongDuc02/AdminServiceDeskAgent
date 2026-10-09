"""`request_open` — tạo `request` ở `DRAFT` khi đã rõ `request_type` loại được hỗ trợ (mục Tool Registry của 03-agents.md).

Nếu đổi loại giữa chừng (EC-CV-02: `replaces_request_id`) thì `request` cũ — phải còn `DRAFT` — chuyển sang `CANCELLED` trong CÙNG giao dịch; đã `SUBMITTED` thì không huỷ ngầm
(`REPLACED_NOT_DRAFT`). Idempotent theo (`chat_session_id`, tin nhắn của lượt): `request.opened_by_message_id` là `UNIQUE`; gửi lại cùng tin nhắn trả lại đúng `request` đã mở.

Cùng giao dịch: ghi các slot nguồn `SYSTEM` mà hệ thống biết ngay lúc mở (`requester_employee_code`, `beneficiary_employee_id`) ở `SYSTEM_SET`, và gắn `chat_message.request_id` cho tin mở.
Khoá hàng `chat_session` ở đầu giao dịch nên hai lượt đồng thời trên một phiên không mở hai `request` cho một tin nhắn.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.kernel import audit
from bo19.tool_layer.kernel.permission import require, require_any
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.transition import transition
from bo19.tool_layer.tools._common import NotOwnRequest, ToolError, actor_id, jsonb

# Slot nguồn SYSTEM mà hệ thống đặt ngay lúc mở: tên slot → cách lấy giá trị.
OPEN_TIME_SYSTEM_SLOTS = ("requester_employee_code", "beneficiary_employee_id")


class TypeNotSupported(ToolError):
    code = "TYPE_NOT_SUPPORTED"


class ReplacedNotDraft(ToolError):
    code = "REPLACED_NOT_DRAFT"


class ChatSessionInvalid(ToolError):
    code = "CHAT_SESSION_INVALID"


class MessageInvalid(ToolError):
    code = "MESSAGE_INVALID"


class BeneficiaryNotFound(ToolError):
    code = "BENEFICIARY_NOT_FOUND"


@dataclass(frozen=True)
class OpenResult:
    request_id: uuid.UUID
    created: bool
    replaced_request_id: uuid.UUID | None


def request_open(pool: Pool, ctx: ToolContext, *, chat_session_id: uuid.UUID, request_type: str, beneficiary_employee_id: uuid.UUID,
                 opened_by_message_id: uuid.UUID, replaces_request_id: uuid.UUID | None = None) -> OpenResult:
    me = actor_id(ctx)
    if beneficiary_employee_id == me:
        require_any(ctx, ("request.create", "request.create_on_behalf"))
    else:
        require(ctx, "request.create_on_behalf")
    with pool.acquire() as conn, unit_of_work(conn):
        session = conn.execute("SELECT employee_id, status FROM chat_session WHERE id = %s FOR UPDATE", (chat_session_id,)).fetchone()
        if session is None or session[0] != me or session[1] != "OPEN":
            raise ChatSessionInvalid
        message = conn.execute("SELECT chat_session_id, author FROM chat_message WHERE id = %s", (opened_by_message_id,)).fetchone()
        if message is None or message[0] != chat_session_id or message[1] != "EMPLOYEE":
            raise MessageInvalid
        existing = conn.execute("SELECT id, created_by_employee_id, request_type_code, replaces_request_id FROM request WHERE opened_by_message_id = %s", (opened_by_message_id,)).fetchone()
        if existing is not None:
            if existing[1] != me:
                raise NotOwnRequest
            return OpenResult(existing[0], False, existing[3])  # gửi lại cùng tin nhắn: trả đúng request đã mở, không làm gì thêm
        type_row = conn.execute("SELECT support_status FROM request_type WHERE code = %s", (request_type,)).fetchone()
        if type_row is None or type_row[0] != "SUPPORTED":
            raise TypeNotSupported(request_type[:40])
        beneficiary = conn.execute("SELECT employee_code FROM employee WHERE id = %s AND is_active", (beneficiary_employee_id,)).fetchone()
        if beneficiary is None:
            raise BeneficiaryNotFound
        replaced = None
        if replaces_request_id is not None:
            old = conn.execute("SELECT created_by_employee_id, status FROM request WHERE id = %s FOR UPDATE", (replaces_request_id,)).fetchone()
            if old is None or old[0] != me:
                raise NotOwnRequest
            if old[1] != "DRAFT":
                raise ReplacedNotDraft(old[1])
            transition(conn, "request", replaces_request_id, to="CANCELLED", expected_from="DRAFT")
            audit.record(conn, ctx, action="request.cancel", entity_type="request", entity_id=replaces_request_id, request_id=replaces_request_id,
                         payload={"reason": "REPLACED_BY_NEW_TYPE"})
            replaced = replaces_request_id
        request_id = uuid.uuid4()
        conn.execute("INSERT INTO request (id, request_type_code, status, chat_session_id, created_by_employee_id, beneficiary_employee_id, replaces_request_id, opened_by_message_id) "
                     "VALUES (%s, %s, 'DRAFT', %s, %s, %s, %s, %s)", (request_id, request_type, chat_session_id, me, beneficiary_employee_id, replaced, opened_by_message_id))
        actor_code = conn.execute("SELECT employee_code FROM employee WHERE id = %s", (me,)).fetchone()[0]
        defined = {r[0] for r in conn.execute("SELECT slot_name FROM slot_definition WHERE request_type_code = %s AND source = 'SYSTEM'", (request_type,)).fetchall()}
        system_values = {"requester_employee_code": actor_code, "beneficiary_employee_id": str(beneficiary_employee_id)}
        for name in OPEN_TIME_SYSTEM_SLOTS:
            if name in defined:
                conn.execute("INSERT INTO request_slot (request_id, request_type_code, slot_name, value, value_status) VALUES (%s, %s, %s, %s, 'SYSTEM_SET')",
                             (request_id, request_type, name, jsonb(system_values[name])))
        conn.execute("UPDATE chat_message SET request_id = %s WHERE id = %s", (request_id, opened_by_message_id))
        audit.record(conn, ctx, action="request.open", entity_type="request", entity_id=request_id, request_id=request_id,
                     payload={"request_type": request_type, "on_behalf": beneficiary_employee_id != me, "replaced": replaced is not None})
        return OpenResult(request_id, True, replaced)
