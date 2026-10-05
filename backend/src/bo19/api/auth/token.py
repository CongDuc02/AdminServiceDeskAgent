"""Token phiên — JWT ký HMAC bằng `PyJWT` (ADR-013, ADR-028; thuật toán `HS256`, ghi ở mục Cập nhật B3 của ADR-028).

Nội dung đúng hai claim: `sub` (id nhân viên, uuid) và `exp` (lúc cấp + 8 giờ, tuyệt đối — WV-17). Không permission, không claim nào khác.

**Kiểm token ghim thuật toán.** `ALGORITHMS` là danh sách cố định trong code; `alg` trong header của token **không bao giờ** được dùng để chọn thuật toán.
Token `alg=none` và token ký bằng thuật toán khác bị từ chối, và `PyJWT` được dựng với `enforce_minimum_key_length` — khoá HMAC ngắn hơn 32 byte
không ký, không kiểm được (A-088, `docs/reference/pyjwt-hmac-key-length.md`), dù bước kiểm khởi động #12 bị bỏ qua.

`verify` trả `None` cho **mọi** lý do hỏng (chữ ký, hạn, thiếu claim, `sub` không phải uuid, khoá không dùng được) — `api` chỉ có một câu trả lời: `UNAUTHENTICATED`.
"""
from __future__ import annotations

import datetime as dt
import uuid

import jwt

from bo19.config import working_values as wv

ALGORITHM = "HS256"
ALGORITHMS = [ALGORITHM]  # danh sách ghim cho decode — không đọc từ token
COOKIE_NAME = "bo19_session"

_JWT = jwt.PyJWT(options={"enforce_minimum_key_length": True})


def issue(secret: str, employee_id: uuid.UUID, *, issued_at: dt.datetime | None = None, ttl_seconds: int = wv.SESSION_TOKEN_TTL_SECONDS) -> str:
    now = issued_at or dt.datetime.now(dt.timezone.utc)
    return _JWT.encode({"sub": str(employee_id), "exp": int(now.timestamp()) + ttl_seconds}, secret, algorithm=ALGORITHM)


def verify(secret: str, token: str) -> uuid.UUID | None:
    try:
        claims = _JWT.decode(token, secret, algorithms=ALGORITHMS, options={"require": ["sub", "exp"]})
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        return None
