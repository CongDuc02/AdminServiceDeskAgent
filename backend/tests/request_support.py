"""Dựng một `request` `WORK_CONFIRMATION` qua đúng các tool của `intake_agent` (B7) — cho test của `request_submit` và nhóm endpoint Request. Không có test nào ở đây.

Mọi giá trị là dữ liệu giả của test; `purpose` mang dấu `RES` để test kiểm nó không lọt ra ngoài `request_slot`.
"""
from __future__ import annotations

import uuid

from bo19.persistence.pool import Pool
from bo19.tool_layer.employee_ops.request_slot_confirm import Confirmation, request_slot_confirm
from bo19.tool_layer.endpoint_ops.chat import chat_message_append, chat_session_open
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.tools.request_open import request_open
from bo19.tool_layer.tools.request_slots_propose import request_slots_propose
from bo19.tool_layer.tools.request_slots_write import SlotWrite, request_slots_write
from tests.tool_support import RES

HR_REQUIRED = ("contract_type", "department_name", "employment_start_date", "full_name", "job_title")
RECIPIENT = "Ngân hàng GIẢ ABC"
PURPOSE = f"bổ sung hồ sơ vay vốn {RES}"
TEXT = f"xin giấy xác nhận công tác gửi tới {RECIPIENT}, mục đích {PURPOSE}"


def slot_versions(db, request_id: uuid.UUID) -> dict[str, tuple[str, int]]:
    """{tên slot: (value_status, row_version)} — đọc bằng chủ bảng."""
    with db.connect("bo19_migrator") as c:
        return {r[0]: (r[1], r[2]) for r in c.execute("select slot_name, value_status, row_version from request_slot where request_id = %s", (request_id,)).fetchall()}


def build_request(pool: Pool, db, employee_id: uuid.UUID, ctx: ToolContext, *, leave_unconfirmed: tuple[str, ...] = (), confirm: bool = True) -> uuid.UUID:
    """Mở `request`, ghi hai slot `USER_INPUT` có bằng chứng, đề xuất hồ sơ, rồi (nếu `confirm`) xác nhận mọi slot `HR_PROFILE` bắt buộc trừ `leave_unconfirmed`."""
    sid = chat_session_open(pool, ctx).chat_session_id
    opener = uuid.uuid4()
    chat_message_append(pool, ctx, chat_session_id=sid, message_id=opener, author="EMPLOYEE", body="xin giấy xác nhận công tác")
    rid = request_open(pool, ctx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=employee_id, opened_by_message_id=opener).request_id
    mid = uuid.uuid4()
    chat_message_append(pool, ctx, chat_session_id=sid, message_id=mid, author="EMPLOYEE", body=TEXT)
    written = request_slots_write(pool, ctx, request_id=rid, items=[SlotWrite("recipient_org", RECIPIENT, mid, RECIPIENT), SlotWrite("purpose", PURPOSE, mid, PURPOSE)])
    if len(written.written) != 2:
        raise AssertionError(f"dựng request hỏng: {written}")
    request_slots_propose(pool, ctx, request_id=rid, origin="HR_PROFILE")
    if confirm:
        versions = slot_versions(db, rid)
        request_slot_confirm(pool, ctx, request_id=rid, items=[Confirmation(n, versions[n][1]) for n in HR_REQUIRED if n not in leave_unconfirmed])
    return rid
