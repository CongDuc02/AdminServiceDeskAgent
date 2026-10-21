"""ĐIỂM GHI DUY NHẤT của cột `status` (mục Nghĩa vụ kế thừa của 06-structure.md): hàm duy nhất sinh câu `UPDATE` đổi `status`.

Một câu `UPDATE` luôn ghi `status`, `row_version + 1`, `updated_at` và — ở bảng có cột này — `status_changed_at = now()`, với điều kiện trạng thái hiện tại và `row_version`. Hàng bị khoá
(`SELECT … FOR UPDATE`) trước khi quyết, nên hai giao dịch đồng thời cùng chuyển một hàng không cùng thành công.

**Bất biến thực thi bằng hai lớp:** (1) cạnh phải có trong máy trạng thái của `bo19.domain` — `IllegalTransition` nếu không; (2) CI quét văn bản — câu SQL gán `status` của `request`, `document`,
`approval_step`, `room_booking` ngoài file này làm `tests/test_kernel_transition.py` đỏ. **Chỗ hở còn lại:** SQL dựng động lách được phép quét — chỗ đó chỉ còn review. Không phải bất biến DB:
một `CHECK` không so được giá trị cũ với giá trị mới và `schema.sql` không dùng trigger.

**Phạm vi:** `request` (B5), `document` (B9a, ADR-039) và `approval_step` (B9b1, ADR-040) có máy trạng thái đăng ký. `room_booking` đăng ký khi vòng đời của nó được dựng (`NoStateMachine` cho tới lúc đó) — không đoán cạnh.
`document`: bảng cạnh đủ mười ba trạng thái. **Cột đi kèm của cạnh** (`set_values`, B9b1): `ck_document_approved_complete` và `ck_document_signer_assigned` đòi `approved_*` / `signer_employee_id` có mặt **trong cùng câu `UPDATE`**
đổi sang `APPROVED` / `PENDING_SIGNATURE`, nên cạnh đó nhận cột qua `set_values` — chỉ cột trong `TableSpec.value_columns` của trạng thái đích, và trạng thái đích có danh sách thì phải đủ đúng danh sách đó. Các cạnh sau (`issued_*`, `archived_*`)
vẫn chờ lát dùng chúng mở rộng `TableSpec` — `CHECK` của DB từ chối cạnh đó nếu chưa.
`status_changed_at` chỉ có ở `request` và `document` trong schema; 06-structure.md nói bốn bảng — chênh lệch đã ghi ở CHANGELOG.md (B5).
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import psycopg

from bo19.domain.approval_step_machine import APPROVAL_STEP_TERMINAL, APPROVAL_STEP_TRANSITIONS
from bo19.domain.document_machine import DOCUMENT_TERMINAL, DOCUMENT_TRANSITIONS
from bo19.domain.request_machine import REQUEST_TERMINAL, REQUEST_TRANSITIONS
from bo19.tool_layer.kernel.context import KernelError, require_transaction

# Bốn bảng có `status` mà chỉ kernel được đổi (06-structure.md). Tên bảng đi vào câu SQL CHỈ qua danh sách này.
STATUS_TABLES = ("request", "document", "approval_step", "room_booking")


class NoStateMachine(KernelError):
    code = "NO_STATE_MACHINE"  # bảng có `status` nhưng vòng đời chưa được đăng ký ở B5


class RowNotFound(KernelError):
    code = "ROW_NOT_FOUND"


class IllegalTransition(KernelError):
    code = "ILLEGAL_TRANSITION"


class StaleStatus(KernelError):
    code = "STALE_STATUS"  # trạng thái hiện tại khác trạng thái người gọi mong đợi


class StaleVersion(KernelError):
    code = "STALE_VERSION"  # `row_version` lệch bản người gọi đang nhìn


class ExtraColumnNotAllowed(KernelError):
    code = "EXTRA_COLUMN_NOT_ALLOWED"


class SetValuesIncomplete(KernelError):
    code = "SET_VALUES_INCOMPLETE"  # trạng thái đích đòi cột đi kèm (CHECK của DB) mà thao tác không đưa đủ


@dataclass(frozen=True)
class TableSpec:
    machine: Mapping[str, frozenset[str]]
    has_status_changed_at: bool
    terminal: frozenset[str] = field(default_factory=frozenset)
    close_column: str | None = None  # đặt = now() khi vào trạng thái cuối (ràng buộc `closed_iff_terminal`)
    on_enter_now: Mapping[str, str] = field(default_factory=dict)  # trạng thái → cột mốc đặt = now() khi vào (ràng buộc bắt buộc của DB)
    extra_now_allowed: frozenset[str] = field(default_factory=frozenset)  # cột mốc thêm mà thao tác gọi được xin đặt = now()
    value_columns: Mapping[str, frozenset[str]] = field(default_factory=dict)  # trạng thái đích → cột đi kèm ĐÚNG tập này, ghi cùng câu UPDATE (B9b1, ADR-040) — `set_values` của thao tác


SPECS: dict[str, TableSpec] = {
    "request": TableSpec(REQUEST_TRANSITIONS, True, REQUEST_TERMINAL, "closed_at", {"NEEDS_INFO": "needs_info_asked_at"}, frozenset({"submitted_at"})),
    "document": TableSpec(DOCUMENT_TRANSITIONS, True, DOCUMENT_TERMINAL, value_columns={
        "APPROVED": frozenset({"approved_content_hash", "approved_decision_id", "approved_render_id"}),
        "PENDING_SIGNATURE": frozenset({"signer_employee_id"}),
    }),
    "approval_step": TableSpec(APPROVAL_STEP_TRANSITIONS, False, APPROVAL_STEP_TERMINAL, "closed_at"),  # B9b1: `status_changed_at` không có ở bảng này; `closed_at` đặt khi rời `OPEN`
}


@dataclass(frozen=True)
class TransitionResult:
    status: str
    row_version: int
    changed: bool  # False: hàng đã ở trạng thái đích — không làm gì (idempotent)


def transition(conn: psycopg.Connection, table: str, row_id: uuid.UUID, *, to: str, expected_from: str | None = None, expected_row_version: int | None = None,
               extra_now: tuple[str, ...] = (), set_values: Mapping[str, Any] | None = None) -> TransitionResult:
    """Chuyển `status` của một hàng sang `to`. Đã ở `to` thì trả `changed=False` mà không ghi gì (và không đụng `set_values`). Phải gọi trong giao dịch của thao tác (`unit_of_work`).

    `set_values`: cột đi kèm của cạnh (xem đầu file) — tên cột đi vào câu SQL **chỉ** qua `TableSpec.value_columns`, giá trị qua tham số."""
    require_transaction(conn)
    spec = SPECS.get(table)
    if spec is None:
        raise NoStateMachine(table)  # tên bảng chỉ vào SQL khi là khoá của SPECS (tập con của STATUS_TABLES): tên lạ hay bảng chưa có máy đều dừng ở đây
    bad = [c for c in extra_now if c not in spec.extra_now_allowed]
    if bad:
        raise ExtraColumnNotAllowed(bad[0])
    values = dict(set_values or {})
    allowed = spec.value_columns.get(to, frozenset())
    extra_cols = sorted(c for c in values if c not in allowed)
    if extra_cols:
        raise ExtraColumnNotAllowed(extra_cols[0])
    if allowed and set(values) != allowed:
        raise SetValuesIncomplete(to)
    row = conn.execute(f"SELECT status, row_version FROM {table} WHERE id = %s FOR UPDATE", (row_id,)).fetchone()  # noqa: S608 — `table` thuộc STATUS_TABLES
    if row is None:
        raise RowNotFound(table)
    current, version = row
    if expected_row_version is not None and version != expected_row_version:
        raise StaleVersion(table)
    if current == to:
        return TransitionResult(current, version, False)
    if expected_from is not None and current != expected_from:
        raise StaleStatus(table)
    if to not in spec.machine.get(current, frozenset()):
        raise IllegalTransition(f"{current}>{to}")
    sets = ["status = %s", "row_version = row_version + 1", "updated_at = now()"]
    if spec.has_status_changed_at:
        sets.append("status_changed_at = now()")
    if spec.close_column and to in spec.terminal:
        sets.append(f"{spec.close_column} = now()")
    if to in spec.on_enter_now:
        sets.append(f"{spec.on_enter_now[to]} = now()")
    sets.extend(f"{c} = now()" for c in extra_now if c not in (spec.close_column, spec.on_enter_now.get(to)))
    ordered = sorted(values)  # đã kiểm thuộc `value_columns[to]` ở trên
    sets.extend(f"{c} = %s" for c in ordered)
    new = conn.execute(f"UPDATE {table} SET {', '.join(sets)} WHERE id = %s AND status = %s AND row_version = %s RETURNING row_version",  # noqa: S608
                       (to, *(values[c] for c in ordered), row_id, current, version)).fetchone()
    if new is None:  # đã khoá hàng nên không xảy ra; nếu xảy ra thì dừng chứ không đoán
        raise StaleStatus(table)
    return TransitionResult(to, new[0], True)
