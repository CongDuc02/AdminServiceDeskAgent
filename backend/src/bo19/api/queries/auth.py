"""Truy vấn của nhóm Phiên đăng nhập — chỉ qua `persistence.read` (mọi giao dịch `READ ONLY`). Mục Cây backend của 06-structure.md.

Mỗi request đã đăng nhập đọc lại `employee.is_active` và permission hiệu lực từ DB (ADR-013): token không mang permission, nên thu quyền hay nghỉ việc
có hiệu lực ở request kế tiếp.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import psycopg

from bo19.persistence.read import read_only


@dataclass(frozen=True)
class LoginCandidate:
    employee_id: uuid.UUID
    password_hash: str = field(repr=False)  # secret — không vào repr hay log
    hash_algorithm: str
    is_active: bool


@dataclass(frozen=True)
class SessionEmployee:
    id: uuid.UUID
    employee_code: str
    full_name: str
    department_code: str
    department_name: str
    job_title: str


def find_login_candidate(conn: psycopg.Connection, employee_code: str) -> LoginCandidate | None:
    """Nhân viên và credential theo mã. Không có nhân viên, hoặc có mà thiếu dòng credential, đều trả `None`."""
    with read_only(conn):
        row = conn.execute(
            "SELECT e.id, c.password_hash, c.hash_algorithm, e.is_active "
            "FROM employee e JOIN employee_credential c ON c.employee_id = e.id WHERE e.employee_code = %s",
            (employee_code,),
        ).fetchone()
    return LoginCandidate(*row) if row else None


def load_active_employee(conn: psycopg.Connection, employee_id: uuid.UUID) -> SessionEmployee | None:
    """Hồ sơ của nhân viên **đang hoạt động**; không tồn tại hay `is_active = false` đều trả `None`."""
    with read_only(conn):
        row = conn.execute(
            "SELECT id, employee_code, full_name, department_code, department_name, job_title "
            "FROM employee WHERE id = %s AND is_active",
            (employee_id,),
        ).fetchone()
    return SessionEmployee(*row) if row else None


def effective_permissions(conn: psycopg.Connection, employee_id: uuid.UUID) -> list[str]:
    """Gói permission của các vai trò, cộng quyền cấp lẻ chưa thu hồi (mục Permission và vai trò của 00-domain.md). Uỷ quyền `[Should]` chưa tính."""
    with read_only(conn):
        rows = conn.execute(
            "SELECT rp.permission_code FROM employee_role er JOIN role_permission rp ON rp.role_code = er.role_code "
            "WHERE er.employee_id = %(id)s "
            "UNION "
            "SELECT g.permission_code FROM employee_permission_grant g "
            "WHERE g.employee_id = %(id)s AND g.revoked_at IS NULL AND g.granted_at <= now() "
            "ORDER BY 1",
            {"id": employee_id},
        ).fetchall()
    return [r[0] for r in rows]
