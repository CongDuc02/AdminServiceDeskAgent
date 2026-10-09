"""Tác nhân và ngữ cảnh của một thao tác `tool_layer` (mục Cây backend của 06-structure.md; D-005).

`Actor` là người thật (kèm **permission hiệu lực**, không kèm tên vai trò) hoặc hệ thống. `ToolContext` thêm `trace_id` (ADR-024). Cả hai bất biến: một thao tác không đổi
quyền của chính nó giữa chừng.

Mọi hàm ghi của kernel đòi `conn` đang **trong một giao dịch** (`require_transaction`): audit, chuyển trạng thái và enqueue phải cùng giao dịch với thao tác gọi chúng
(ADR-004, ADR-010; luật `audit_event` ở mục Tool Registry của 03-agents.md). Gọi ngoài giao dịch là lỗi lập trình, không phải lỗi nghiệp vụ.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

import psycopg
from psycopg.pq import TransactionStatus

from bo19.observability.trace import current_trace_id, is_trace_id, new_trace_id


class KernelError(Exception):
    """Gốc của lỗi kernel. Chỉ mang mã — không thông điệp, không giá trị (lỗi có thể tới log và `audit_event`)."""

    code = "KERNEL_ERROR"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(f"{self.code}:{detail}" if detail else self.code)
        self.detail = detail  # tên (bảng, permission, trường) — không bao giờ giá trị dữ liệu


class NotInTransaction(KernelError):
    code = "KERNEL_NOT_IN_TRANSACTION"


@dataclass(frozen=True)
class Actor:
    kind: Literal["EMPLOYEE", "SYSTEM"]
    employee_id: uuid.UUID | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.kind == "EMPLOYEE":
            if self.employee_id is None:
                raise ValueError("EMPLOYEE cần employee_id")
        elif self.kind == "SYSTEM":
            if self.employee_id is not None or self.permissions:
                raise ValueError("SYSTEM không có employee_id và không có permission")  # khớp `ck_audit_event_actor`
        else:
            raise ValueError("actor.kind ngoài EMPLOYEE, SYSTEM")

    @classmethod
    def employee(cls, employee_id: uuid.UUID, permissions: frozenset[str] | set[str]) -> "Actor":
        return cls("EMPLOYEE", employee_id, frozenset(permissions))

    @classmethod
    def system(cls) -> "Actor":
        return cls("SYSTEM")


@dataclass(frozen=True)
class ToolContext:
    actor: Actor
    trace_id: str

    def __post_init__(self) -> None:
        if not is_trace_id(self.trace_id):
            raise ValueError("trace_id phải là UUID v4 chữ thường, có gạch nối (ADR-024)")

    @classmethod
    def create(cls, actor: Actor, trace_id: str | None = None) -> "ToolContext":
        """`trace_id` mặc định lấy từ ngữ cảnh trace hiện hành (request, job, cron); không có thì sinh mới."""
        return cls(actor, trace_id or current_trace_id() or new_trace_id())


def require_transaction(conn: psycopg.Connection) -> None:
    if conn.info.transaction_status != TransactionStatus.INTRANS:
        raise NotInTransaction
