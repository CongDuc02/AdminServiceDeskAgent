"""Kiểm permission — theo **permission hiệu lực**, không theo tên vai trò (D-005; mục Permission và vai trò của 00-domain.md).

Permission hiệu lực = gói permission của các vai trò cộng quyền cấp lẻ chưa thu hồi và đã tới hạn hiệu lực. Uỷ quyền (`delegation`, `[Should]`) chưa tính — cắt khỏi Sprint đầu (AUD-15).
Đọc lại từ DB mỗi lần dựng `ToolContext` (ADR-013): thu quyền có hiệu lực ở thao tác kế tiếp. Nhân viên không hoạt động thì không có ngữ cảnh.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable

import psycopg

from bo19.persistence.read import read_only
from bo19.tool_layer.kernel.context import Actor, KernelError, ToolContext


class PermissionDenied(KernelError):
    code = "PERMISSION_DENIED"


class ActorInactive(KernelError):
    code = "ACTOR_INACTIVE"


class SystemActorRequired(KernelError):
    code = "SYSTEM_ACTOR_REQUIRED"


_EFFECTIVE = (
    "SELECT rp.permission_code FROM employee_role er JOIN role_permission rp ON rp.role_code = er.role_code WHERE er.employee_id = %(id)s "
    "UNION "
    "SELECT g.permission_code FROM employee_permission_grant g WHERE g.employee_id = %(id)s AND g.revoked_at IS NULL AND g.granted_at <= now()"
)


def employee_context(conn: psycopg.Connection, employee_id: uuid.UUID, trace_id: str | None = None) -> ToolContext:
    """Ngữ cảnh của một nhân viên **đang hoạt động**, với permission hiệu lực đọc từ DB lúc này. Không tồn tại hay `is_active = false` → `ActorInactive`."""
    with read_only(conn):
        row = conn.execute("SELECT is_active FROM employee WHERE id = %s", (employee_id,)).fetchone()
        if row is None or not row[0]:
            raise ActorInactive
        permissions = frozenset(r[0] for r in conn.execute(_EFFECTIVE, {"id": employee_id}).fetchall())
    return ToolContext.create(Actor.employee(employee_id, permissions), trace_id)


def system_context(trace_id: str | None = None) -> ToolContext:
    return ToolContext.create(Actor.system(), trace_id)


def require(ctx: ToolContext, permission: str) -> None:
    """Người thật phải có đúng permission này. Tác nhân hệ thống **không** có permission nào — nó đi qua `require_system`."""
    if ctx.actor.kind != "EMPLOYEE" or permission not in ctx.actor.permissions:
        raise PermissionDenied(permission)


def require_any(ctx: ToolContext, permissions: Iterable[str]) -> None:
    """Any-of — như `x-bo19-permission` của `openapi.yaml`."""
    wanted = tuple(permissions)
    if ctx.actor.kind != "EMPLOYEE" or not any(p in ctx.actor.permissions for p in wanted):
        raise PermissionDenied("|".join(wanted))


def require_system(ctx: ToolContext) -> None:
    if ctx.actor.kind != "SYSTEM":
        raise SystemActorRequired
