"""`request_slot_confirm` — nhân viên xác nhận TỪNG giá trị slot đang `PROPOSED` (mục 5.4 của 03-agents.md; RISK-06, D-002).

Là thao tác riêng, không phải một nhánh của `request_slots_write`: xác nhận ghi `CONFIRMED` và `confirmed_at`, không có bằng chứng nào để kiểm; và nó không đi qua lượt chat — nhân viên gõ
"đúng rồi" trong chat thì không có gì được xác nhận. **`row_version` gắn lần xác nhận vào đúng giá trị nhân viên đã nhìn thấy:** giá trị đổi giữa lúc hiển thị và lúc bấm thì xác nhận hỏng
(`STALE_VALUE`), không trượt sang giá trị mới.

Tất cả hoặc không gì: một mục lỗi làm cả lời gọi lỗi và giao dịch lăn. Slot đã `CONFIRMED` thì không làm gì. Sau khi xác nhận, chạy lại **đúng hàm** "đủ điều kiện xử lý" mà `check_completeness` và
`request_submit` dùng; `request` đang `NEEDS_INFO` mà đạt thì `NEEDS_INFO → DRAFT` — cạnh "nhân viên bổ sung" của máy trạng thái. `audit_event` chỉ mang tên slot.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.checks.eligibility import check_request
from bo19.tool_layer.kernel import audit
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require
from bo19.tool_layer.kernel.transition import transition
from bo19.tool_layer.tools._common import ToolError, load_own_request, require_editable


class NotProposed(ToolError):
    code = "NOT_PROPOSED"


class StaleValue(ToolError):
    code = "STALE_VALUE"


@dataclass(frozen=True)
class Confirmation:
    slot_name: str
    row_version: int  # bản nhân viên đang nhìn


@dataclass(frozen=True)
class ConfirmResult:
    confirmed: tuple[str, ...]
    unchanged: tuple[str, ...]
    status: str  # trạng thái `request` sau lời gọi
    eligible: bool


def request_slot_confirm(pool: Pool, ctx: ToolContext, *, request_id: uuid.UUID, items: list[Confirmation]) -> ConfirmResult:
    require(ctx, "request.supply_info")
    with pool.acquire() as conn, unit_of_work(conn):
        row = load_own_request(conn, ctx, request_id)
        require_editable(row)
        confirmed: list[str] = []
        unchanged: list[str] = []
        for item in items:
            slot = conn.execute("SELECT value_status, row_version FROM request_slot WHERE request_id = %s AND slot_name = %s FOR UPDATE", (request_id, item.slot_name)).fetchone()
            if slot is None:
                raise NotProposed(item.slot_name)
            if slot[0] == "CONFIRMED":
                unchanged.append(item.slot_name)
                continue
            if slot[0] != "PROPOSED":
                raise NotProposed(item.slot_name)
            if slot[1] != item.row_version:
                raise StaleValue(item.slot_name)
            conn.execute("UPDATE request_slot SET value_status = 'CONFIRMED', confirmed_at = now(), row_version = row_version + 1, updated_at = now() WHERE request_id = %s AND slot_name = %s",
                         (request_id, item.slot_name))
            confirmed.append(item.slot_name)
        check = check_request(conn, request_id)
        status = row.status
        if row.status == "NEEDS_INFO" and check.eligible:
            transition(conn, "request", request_id, to="DRAFT", expected_from="NEEDS_INFO")
            status = "DRAFT"
        if confirmed:
            audit.record(conn, ctx, action="request.slot_confirm", entity_type="request", entity_id=request_id, request_id=request_id,
                         payload={"confirmed": confirmed, "status_to": status})
        return ConfirmResult(tuple(confirmed), tuple(unchanged), status, check.eligible)
