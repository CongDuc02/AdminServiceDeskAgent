"""Hàm "Yêu cầu đủ điều kiện xử lý" (F1, `01-prd.md`) — thuần, không IO.

MỘT hàm cho ba nơi: `check_completeness` của `intake_graph`, `request_slot_confirm` (khi `NEEDS_INFO` có thể về `DRAFT`) và `request_submit` (`tool_layer.checks` nạp dữ liệu một lần;
mục Cây backend của 06-structure.md). `request_submit` chạy lại chứ không tin kết quả của graph.

Bốn điều kiện:

1. Mọi slot bắt buộc nguồn `USER_INPUT` có giá trị **do người dùng cung cấp** (`PROVIDED`), hoặc giá trị đề xuất lại từ lần thử `EXPIRED` mà nhân viên đã xác nhận (`CONFIRMED`).
   Một giá trị `PROPOSED` — dù hiển nhiên đúng — chưa được tính.
2. Mọi slot bắt buộc nguồn `HR_PROFILE` đã `CONFIRMED` từng giá trị (D-002 ràng buộc 1 và 2). Slot `SYSTEM` bắt buộc phải do hệ thống đặt (`SYSTEM_SET`).
3. Mọi giá trị đang có đều qua `validation_rules` (`domain.slot_rules`) của slot, **theo cấu hình hiện hành**.
4. `beneficiary_employee_id` đã xác định; khác người tạo thì người tạo có `request.create_on_behalf`. (Vế `delegation` cắt khỏi Sprint đầu — AUD-15.)

Ngoài ra **bất kỳ slot nào đang `PROPOSED` đều chặn**, kể cả slot tuỳ chọn: một giá trị agent đề xuất mà nhân viên chưa xác nhận không được đi tiếp trong hồ sơ.

Kết quả là danh sách `Reason(code, slot_name)` — chỉ mã và tên slot, **không giá trị** (`purpose` là `RES`). Rỗng nghĩa là đủ điều kiện.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bo19.domain import slot_rules

SLOT_MISSING = "SLOT_MISSING"
SLOT_UNCONFIRMED = "SLOT_UNCONFIRMED"
BENEFICIARY_UNKNOWN = "BENEFICIARY_UNKNOWN"
ON_BEHALF_FORBIDDEN = "ON_BEHALF_FORBIDDEN"

PROVIDED, PROPOSED, CONFIRMED, SYSTEM_SET, ERASED = "PROVIDED", "PROPOSED", "CONFIRMED", "SYSTEM_SET", "ERASED"
# Trạng thái làm một giá trị "đã có" theo từng nguồn — nguồn nào không liệt kê thì dùng `_OTHER`.
_ACCEPTED = {"USER_INPUT": frozenset({PROVIDED, CONFIRMED}), "HR_PROFILE": frozenset({CONFIRMED}), "SYSTEM": frozenset({SYSTEM_SET})}
_OTHER = frozenset({PROVIDED, CONFIRMED, SYSTEM_SET})


@dataclass(frozen=True)
class SlotDef:
    name: str
    data_type: str
    source: str
    is_required: bool
    rules: dict[str, Any]


@dataclass(frozen=True)
class SlotState:
    name: str
    status: str
    value: Any = None  # có thể `None` khi `ERASED`

    def __repr__(self) -> str:
        return f"SlotState(name={self.name!r}, status={self.status!r}, value=<ẩn>)"  # giá trị có thể là RES — không vào repr/log


@dataclass(frozen=True)
class Header:
    created_by_employee_id: Any
    beneficiary_employee_id: Any


@dataclass(frozen=True)
class Reason:
    code: str
    slot_name: str | None = None


def evaluate(header: Header, definitions: list[SlotDef], slots: list[SlotState], *, creator_can_create_on_behalf: bool) -> tuple[Reason, ...]:
    by_name = {s.name: s for s in slots if s.status != ERASED and s.value is not None}
    reasons: list[Reason] = []
    for d in sorted(definitions, key=lambda x: x.name):
        state = by_name.get(d.name)
        if state is None:
            if d.is_required:
                reasons.append(Reason(SLOT_MISSING, d.name))
            continue
        if state.status == PROPOSED:
            reasons.append(Reason(SLOT_UNCONFIRMED, d.name))
            continue
        if d.is_required and state.status not in _ACCEPTED.get(d.source, _OTHER):
            reasons.append(Reason(SLOT_MISSING, d.name))  # có giá trị nhưng không do nguồn hợp lệ cung cấp: coi như chưa có
            continue
        failed = slot_rules.check_value(d.data_type, d.rules, state.value)
        reasons.extend(Reason(code, d.name) for code in failed)
    if header.beneficiary_employee_id is None:
        reasons.append(Reason(BENEFICIARY_UNKNOWN))
    elif header.beneficiary_employee_id != header.created_by_employee_id and not creator_can_create_on_behalf:
        reasons.append(Reason(ON_BEHALF_FORBIDDEN))
    return tuple(reasons)


def is_eligible(header: Header, definitions: list[SlotDef], slots: list[SlotState], *, creator_can_create_on_behalf: bool) -> bool:
    return not evaluate(header, definitions, slots, creator_can_create_on_behalf=creator_can_create_on_behalf)
