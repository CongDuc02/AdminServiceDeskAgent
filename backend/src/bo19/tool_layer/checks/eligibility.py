"""Một lối nạp dữ liệu cho hàm "đủ điều kiện xử lý" (F1) — dùng chung cho `check_completeness`, `request_slot_confirm` và `request_submit` (mục Cây backend của 06-structure.md).

Hàm kiểm là `bo19.domain.eligibility` (thuần); module này chỉ ĐỌC từ DB rồi gọi nó. Chạy bằng truy vấn thường, **không** mở giao dịch: gọi được bên trong `unit_of_work` của thao tác
(`request_slot_confirm`) lẫn ngoài (`check_completeness`, bọc `read_only` ở chỗ gọi). Cấu hình `slot_definition` được đọc **hiện hành** tại lúc kiểm (04-data.md: rule không version).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import psycopg

from bo19.domain import eligibility as el
from bo19.domain.eligibility import Header, Reason, SlotDef, SlotState
from bo19.tool_layer.kernel.permission import effective_permissions

CREATE_ON_BEHALF = "request.create_on_behalf"


class RequestNotFound(Exception):
    code = "REQUEST_NOT_FOUND"


@dataclass(frozen=True)
class RequestCheck:
    request_id: uuid.UUID
    request_type_code: str
    status: str
    reasons: tuple[Reason, ...]

    @property
    def eligible(self) -> bool:
        return not self.reasons


def load_definitions(conn: psycopg.Connection, request_type_code: str) -> list[SlotDef]:
    rows = conn.execute("SELECT slot_name, data_type, source, is_required, validation_rules FROM slot_definition WHERE request_type_code = %s ORDER BY display_order, slot_name",
                        (request_type_code,)).fetchall()
    return [SlotDef(*r) for r in rows]


def load_slots(conn: psycopg.Connection, request_id: uuid.UUID) -> list[SlotState]:
    rows = conn.execute("SELECT slot_name, value_status, value FROM request_slot WHERE request_id = %s ORDER BY slot_name", (request_id,)).fetchall()
    return [SlotState(*r) for r in rows]


def check_request(conn: psycopg.Connection, request_id: uuid.UUID) -> RequestCheck:
    row = conn.execute("SELECT request_type_code, status, created_by_employee_id, beneficiary_employee_id FROM request WHERE id = %s", (request_id,)).fetchone()
    if row is None:
        raise RequestNotFound
    type_code, status, creator, beneficiary = row
    reasons = el.evaluate(Header(creator, beneficiary), load_definitions(conn, type_code), load_slots(conn, request_id),
                          creator_can_create_on_behalf=CREATE_ON_BEHALF in effective_permissions(conn, creator))
    return RequestCheck(request_id, type_code, status, reasons)
