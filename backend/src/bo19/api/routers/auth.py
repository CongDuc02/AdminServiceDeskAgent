"""Router nhóm Phiên đăng nhập — `POST` và `DELETE /auth/session`, `GET /me` (mục 2.2 của 05-api.md).

Đăng nhập: sai mã nhân viên và sai mật khẩu cùng trả `INVALID_CREDENTIALS`; mật khẩu luôn qua đúng một lần verify (xem `api/auth/hasher.py`).
Phiên không lưu DB: phát token chỉ là đặt cookie; đăng xuất chỉ xoá cookie ở trình duyệt này, token đã phát không bị thu hồi trước hạn (A-048).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from bo19.api.auth.hasher import ALGORITHM as HASH_ALGORITHM
from bo19.api.auth.token import COOKIE_NAME, issue
from bo19.api.deps.session import current_employee
from bo19.api.deps.state import AppState, get_state
from bo19.api.errors import ApiError
from bo19.api.queries.auth import SessionEmployee, effective_permissions, find_login_candidate
from bo19.api.schemas.auth import LoginBody, Me, MeEmployee
from bo19.config import working_values as wv
from bo19.observability.log import get_logger
from bo19.persistence.read import current_operating_mode

router = APIRouter(tags=["auth"])
log = get_logger("bo19.api.auth")

COOKIE_PATH = "/api"


@router.post("/auth/session", status_code=204)
def create_session(body: LoginBody, state: AppState = Depends(get_state)) -> Response:
    with state.pool.acquire() as conn:
        candidate = find_login_candidate(conn, body.employee_code)
    # Verify chạy ngoài `with`: nó không giữ connection của pool. Không có hash dùng được (không có nhân viên, bị tắt, thiếu credential, thuật toán lạ)
    # thì `stored` là None và verify so với hash giả — thời gian không phân biệt hai ca sai.
    usable = candidate is not None and candidate.is_active and candidate.hash_algorithm == HASH_ALGORITHM
    stored = candidate.password_hash if usable else None
    if not state.verifier.verify(stored, body.password.get_secret_value()):
        log.info("AUTH_LOGIN_FAILED")
        raise ApiError("INVALID_CREDENTIALS")
    log.info("AUTH_LOGIN_SUCCEEDED", employee_id=str(candidate.employee_id))
    response = Response(status_code=204)
    response.set_cookie(COOKIE_NAME, issue(state.session_secret, candidate.employee_id), max_age=wv.SESSION_TOKEN_TTL_SECONDS,
                        path=COOKIE_PATH, secure=True, httponly=True, samesite="strict")
    return response


@router.delete("/auth/session", status_code=204)
def delete_session(_: SessionEmployee = Depends(current_employee)) -> Response:
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH, secure=True, httponly=True, samesite="strict")
    return response


@router.get("/me", response_model=Me)
def get_me(employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> Me:
    with state.pool.acquire() as conn:
        permissions = effective_permissions(conn, employee.id)
        mode = current_operating_mode(conn).mode
    return Me(employee=MeEmployee(**employee.__dict__), permissions=permissions, operating_mode=mode)
