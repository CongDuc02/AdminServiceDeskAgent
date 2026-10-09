"""`employee_lookup` — tra giá trị `HR_PROFILE` để **đề xuất** (D-002), hoặc chỉ kiểm mã nhân viên có tồn tại (mục Tool Registry của 03-agents.md).

**Kiểm quyền TRƯỚC khi đọc hồ sơ người thứ ba (EC-IL-01):** người tra là chính người thụ hưởng, hoặc có `request.create_on_behalf`. Không đủ → `FORBIDDEN` — kể cả khi mã không tồn tại, nên tool
không cho biết một nhân viên khác có tồn tại hay không. `NOT_FOUND` chỉ ra sau khi quyền đã qua. `fields` là danh sách tên slot `HR_PROFILE` của loại đang mở; tên ngoài slot schema → `FIELD_NOT_ALLOWED`.
Rỗng thì chỉ kiểm tồn tại. Giá trị trả kèm `source`, `synced_at` (ràng buộc provenance 3 của D-002). Giá trị không tự vào `request_slot`: ghi đề xuất là việc của `request_slots_propose`.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.tools._common import ToolError, actor_id

# Slot HR_PROFILE → cột `employee` (tên trùng). Đóng: thêm slot HR mới là thêm một dòng ở đây cùng test.
HR_COLUMNS = ("full_name", "department_name", "job_title", "contract_type", "employment_start_date", "employment_end_date", "date_of_birth", "national_id")


class Forbidden(ToolError):
    code = "FORBIDDEN"


class NotFound(ToolError):
    code = "NOT_FOUND"


class FieldNotAllowed(ToolError):
    code = "FIELD_NOT_ALLOWED"


@dataclass(frozen=True)
class FieldValue:
    value: Any = field(repr=False)
    source: str = ""
    synced_at: dt.datetime | None = None


@dataclass(frozen=True)
class LookupResult:
    employee_id: uuid.UUID
    fields: dict[str, FieldValue]


def hr_value(raw: Any) -> Any:
    """Giá trị cột → dạng JSON của `request_slot.value` (ngày → ISO 8601)."""
    return raw.isoformat() if isinstance(raw, (dt.date, dt.datetime)) else raw


def employee_lookup(pool: Pool, ctx: ToolContext, *, employee_code: str, request_type: str, fields: list[str]) -> LookupResult:
    me = actor_id(ctx)
    with pool.acquire() as conn, read_only(conn):
        own_code = conn.execute("SELECT employee_code FROM employee WHERE id = %s", (me,)).fetchone()
        if own_code is None or (employee_code != own_code[0] and "request.create_on_behalf" not in ctx.actor.permissions):
            raise Forbidden  # TRƯỚC mọi lần đọc hồ sơ người khác
        allowed = {r[0] for r in conn.execute("SELECT slot_name FROM slot_definition WHERE request_type_code = %s AND source = 'HR_PROFILE'", (request_type,)).fetchall()} & set(HR_COLUMNS)
        bad = [f for f in fields if f not in allowed]
        if bad:
            raise FieldNotAllowed(bad[0])
        cols = ", ".join(dict.fromkeys(fields)) if fields else "id"  # `fields` đã nằm trong HR_COLUMNS ∩ slot schema: không bao giờ đưa chuỗi lạ vào SQL
        row = conn.execute(f"SELECT id, source, synced_at, {cols} FROM employee WHERE employee_code = %s AND is_active", (employee_code,)).fetchone()  # noqa: S608
        if row is None:
            raise NotFound
        names = list(dict.fromkeys(fields))
        return LookupResult(row[0], {n: FieldValue(hr_value(v), row[1], row[2]) for n, v in zip(names, row[3:])} if fields else {})
