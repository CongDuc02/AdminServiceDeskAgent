"""`request_slots_propose` — ghi giá trị slot ở trạng thái `PROPOSED` (G1, PO duyệt 2026-10-09; mục Tool Registry của 03-agents.md).

**Tool tự đọc nguồn; người gọi không truyền giá trị.** Hai nguồn, cả hai chỉ của CHÍNH người yêu cầu:

- `HR_PROFILE` — hàng `employee` của chính người đang chat (không phải của ai khác), **chỉ các slot bắt buộc** (tối thiểu hoá dữ liệu);
- `PRIOR_ATTEMPT` — giá trị `INT`/`PER` còn giữ trên `request` `EXPIRED` gần nhất của chính họ (`prior_attempt_lookup`, A-014).

Vì không nhận giá trị và chỉ đọc hồ sơ của người gọi, tool **không thể thành đường vòng để đọc hồ sơ người khác** (EC-IL-01): `request` lập hộ người khác (người thụ hưởng ≠ người tạo) bị từ chối
(`BENEFICIARY_NOT_SELF`); tra hồ sơ người thứ ba chỉ qua `employee_lookup` với `request.create_on_behalf`. Không đè slot đã `PROVIDED` hay `CONFIRMED` (và không đè giá trị `PROPOSED` y hệt).
Giá trị không còn qua rule hiện hành thì không đề xuất. Kết quả và `audit_event` chỉ mang tên slot và mã — **không giá trị**. Nhân viên xác nhận từng giá trị qua `request_slot_confirm`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from bo19.domain import slot_rules
from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.checks.eligibility import load_definitions
from bo19.tool_layer.kernel import audit
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require
from bo19.tool_layer.tools._common import ToolError, jsonb, load_own_request, require_editable
from bo19.tool_layer.tools.employee_lookup import HR_COLUMNS, hr_value
from bo19.tool_layer.tools.prior_attempt_lookup import BeneficiaryNotSelf, prior_values

ORIGINS = ("HR_PROFILE", "PRIOR_ATTEMPT")
ALREADY_SET, NO_SOURCE_VALUE, RULE_NO_LONGER_PASSES = "ALREADY_SET", "NO_SOURCE_VALUE", "RULE_NO_LONGER_PASSES"


class UnknownOrigin(ToolError):
    code = "UNKNOWN_ORIGIN"


@dataclass(frozen=True)
class ProposeResult:
    written: tuple[str, ...]
    skipped: tuple[tuple[str, str], ...]  # (tên slot, mã lý do) — không giá trị


def request_slots_propose(pool: Pool, ctx: ToolContext, *, request_id: uuid.UUID, origin: str) -> ProposeResult:
    if origin not in ORIGINS:
        raise UnknownOrigin(origin[:30])
    require(ctx, "request.supply_info")
    with pool.acquire() as conn, unit_of_work(conn):
        row = load_own_request(conn, ctx, request_id)
        if row.beneficiary_employee_id != row.created_by_employee_id:
            raise BeneficiaryNotSelf  # hồ sơ chỉ của chính người yêu cầu — không đọc cho request lập hộ
        require_editable(row)
        definitions = {d.name: d for d in load_definitions(conn, row.request_type_code)}
        existing = {r[0]: r[1:] for r in conn.execute("SELECT slot_name, value_status, value, provenance_source, provenance_synced_at FROM request_slot WHERE request_id = %s FOR UPDATE", (request_id,)).fetchall()}
        written: list[str] = []
        skipped: list[tuple[str, str]] = []

        def propose(name: str, value, *, source=None, synced_at=None, from_request=None) -> None:
            d = definitions[name]
            if slot_rules.check_value(d.data_type, d.rules, value):
                skipped.append((name, RULE_NO_LONGER_PASSES))
                return
            current = existing.get(name)
            if current is not None and current[0] != "PROPOSED":
                skipped.append((name, ALREADY_SET))  # PROVIDED, CONFIRMED, SYSTEM_SET: không đè
                return
            if current is not None and current[1] == value and current[2] == source and current[3] == synced_at:
                skipped.append((name, ALREADY_SET))  # đề xuất y hệt đã có: idempotent
                return
            if current is None:
                conn.execute("INSERT INTO request_slot (request_id, request_type_code, slot_name, value, value_status, provenance_source, provenance_synced_at, proposed_from_request_id) "
                             "VALUES (%s, %s, %s, %s, 'PROPOSED', %s, %s, %s)", (request_id, row.request_type_code, name, jsonb(value), source, synced_at, from_request))
            else:
                conn.execute("UPDATE request_slot SET value = %s, provenance_source = %s, provenance_synced_at = %s, proposed_from_request_id = %s, row_version = row_version + 1, updated_at = now() "
                             "WHERE request_id = %s AND slot_name = %s", (jsonb(value), source, synced_at, from_request, request_id, name))
            written.append(name)

        if origin == "HR_PROFILE":
            # Tối thiểu hoá dữ liệu: chỉ slot HR_PROFILE BẮT BUỘC. Slot tuỳ chọn (ngày sinh, số định danh, ngày nghỉ việc) không tự vào hồ sơ yêu cầu — nhân viên sẽ phải xác nhận từng cái
            # dù văn bản chưa cần. Slot tuỳ chọn mà template cần (EC-WC-02) được đề xuất khi vòng đời `document` có mặt.
            hr_slots = [n for n in definitions if definitions[n].source == "HR_PROFILE" and definitions[n].is_required and n in HR_COLUMNS]
            if hr_slots:
                cols = ", ".join(hr_slots)  # tên cột đã nằm trong HR_COLUMNS ∩ slot schema: không chuỗi lạ nào vào SQL
                emp = conn.execute(f"SELECT source, synced_at, {cols} FROM employee WHERE id = %s AND is_active", (row.created_by_employee_id,)).fetchone()  # noqa: S608
                if emp is not None:
                    for name, raw in zip(hr_slots, emp[2:]):
                        if raw is None:
                            skipped.append((name, NO_SOURCE_VALUE))
                        else:
                            propose(name, hr_value(raw), source=emp[0], synced_at=emp[1])
        else:
            for pv in prior_values(conn, row.created_by_employee_id, row.request_type_code):
                if pv.slot_name in definitions:
                    propose(pv.slot_name, pv.value, from_request=pv.source_request_id)
        if written:
            audit.record(conn, ctx, action="request.slots_propose", entity_type="request", entity_id=request_id, request_id=request_id,
                         payload={"origin": origin, "written": written, "skipped": [f"{n}:{c}" for n, c in skipped]})
        return ProposeResult(tuple(written), tuple(skipped))
