"""Xác thực `bo19_session` cho mọi endpoint đã đăng nhập (mục Xác thực và chống CSRF của 05-api.md; ADR-013).

Thứ tự: (1) kiểm chữ ký và hạn của token — không chạm DB nếu token hỏng; (2) **đọc lại từ DB** — nhân viên còn tồn tại và `is_active`.
Mọi lý do thất bại cho cùng một lỗi `UNAUTHENTICATED`: không nói token hỏng hay nhân viên đã bị tắt.
"""
from __future__ import annotations

from fastapi import Depends, Request

from bo19.api.auth.token import COOKIE_NAME, verify
from bo19.api.deps.state import AppState, get_state
from bo19.api.errors import ApiError
from bo19.api.queries.auth import SessionEmployee, load_active_employee


def current_employee(request: Request, state: AppState = Depends(get_state)) -> SessionEmployee:
    token = request.cookies.get(COOKIE_NAME)
    employee_id = verify(state.session_secret, token) if token else None
    if employee_id is None:
        raise ApiError("UNAUTHENTICATED")
    with state.pool.acquire() as conn:
        employee = load_active_employee(conn, employee_id)
    if employee is None:
        raise ApiError("UNAUTHENTICATED")
    return employee
