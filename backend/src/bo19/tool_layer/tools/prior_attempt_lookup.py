"""`prior_attempt_lookup` — giá trị slot `INT`/`PER` nguồn `USER_INPUT` còn giữ trên `request` `EXPIRED` gần nhất, để **đề xuất lại** (A-014, F1; mục Tool Registry của 03-agents.md).

Người thụ hưởng phải chính là người đang chat (`BENEFICIARY_NOT_SELF`). Không có lần thử nào → danh sách rỗng (`NONE` — nhánh được thiết kế, không phải lỗi). Chỉ đọc từ `EXPIRED`, không từ
`FULFILLED` (memory yêu cầu định kỳ, `[Could]`) và không từ `CANCELLED`. Độ nhạy lấy theo `slot_definition` **hiện hành** (04-data.md, luật xoá đọc cột này tại lúc xoá). Giá trị không còn qua rule hiện
hành — ví dụ một ngày đã ở quá khứ — thì không được đề xuất. Mọi mục trả về ở trạng thái **chưa xác nhận**; nhân viên xác nhận từng giá trị qua `request_slot_confirm`.

Trả GIÁ TRỊ cho người gọi — nên chỉ dùng khi người gọi cần chính giá trị; `request_slots_propose` tự đọc nguồn này và không trả giá trị.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg

from bo19.domain import slot_rules
from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.tools._common import ToolError, actor_id


class BeneficiaryNotSelf(ToolError):
    code = "BENEFICIARY_NOT_SELF"


@dataclass(frozen=True)
class PriorValue:
    slot_name: str
    value: Any = field(repr=False)  # có thể là RES/PER — không vào repr
    source_request_id: uuid.UUID = None  # type: ignore[assignment]


def prior_values(conn: psycopg.Connection, employee_id: uuid.UUID, request_type: str) -> list[PriorValue]:
    """Đọc thuần (không mở giao dịch). Gọi nội bộ bởi `request_slots_propose` trong giao dịch của nó."""
    prior = conn.execute("SELECT id FROM request WHERE beneficiary_employee_id = %s AND request_type_code = %s AND status = 'EXPIRED' AND retained_values_cleared_at IS NULL "
                         "ORDER BY closed_at DESC NULLS LAST, created_at DESC LIMIT 1", (employee_id, request_type)).fetchone()
    if prior is None:
        return []
    rows = conn.execute("SELECT s.slot_name, s.value, d.data_type, d.validation_rules FROM request_slot s JOIN slot_definition d ON d.request_type_code = s.request_type_code AND d.slot_name = s.slot_name "
                        "WHERE s.request_id = %s AND d.source = 'USER_INPUT' AND d.sensitivity IN ('INT', 'PER') AND s.value_status <> 'ERASED' AND s.value IS NOT NULL ORDER BY d.display_order, s.slot_name",
                        (prior[0],)).fetchall()
    return [PriorValue(name, value, prior[0]) for name, value, dtype, rules in rows if not slot_rules.check_value(dtype, rules, value)]


def prior_attempt_lookup(pool: Pool, ctx: ToolContext, *, beneficiary_employee_id: uuid.UUID, request_type: str) -> list[PriorValue]:
    if beneficiary_employee_id != actor_id(ctx):
        raise BeneficiaryNotSelf
    with pool.acquire() as conn, read_only(conn):
        return prior_values(conn, beneficiary_employee_id, request_type)
