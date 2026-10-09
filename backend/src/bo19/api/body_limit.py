"""Giới hạn kích thước body trước khi phân tích JSON — middleware ASGI thuần (O1-10, PO 2026-10-09; `proposals/login-body-limits.md`).

Vấn đề: uvicorn và FastAPI đọc và phân tích toàn bộ body **trước** khi request tới rate limit; một client chưa đăng nhập gửi body rất lớn tốn bộ nhớ và CPU mà bộ đếm không chặn được.
`POST /auth/session` là endpoint công khai duy nhất.

Cách làm: middleware **tự đọc** body (tối đa `limit + 1` byte) rồi mới giao cho ứng dụng — body hợp lệ được phát lại nguyên văn. Không tin `Content-Length`: header có thể thiếu
(chunked) hay nói dối; byte thực nhận mới là số đếm. `Content-Length` lớn quá trần chỉ giúp từ chối sớm, **không đọc gì**. Vượt trần → `PAYLOAD_TOO_LARGE` 413 trước khi chạm JSON,
trước rate limit (không tăng bộ đếm — như 403 và 422), trước argon2.
"""
from __future__ import annotations

from collections.abc import Mapping

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bo19.api.errors import error_response


def _declared_length(scope: Scope) -> int | None:
    """Giá trị lớn nhất của các header `Content-Length` hợp lệ; `None` nếu không có cái nào hợp lệ (chunked hay header hỏng — khi đó đếm byte thực)."""
    values = [int(v) for k, v in scope["headers"] if k == b"content-length" and v.isascii() and v.isdigit() and len(v) <= 12]
    return max(values) if values else None


class BodyLimitMiddleware:
    """`limits` — ánh xạ (phương thức, đường dẫn đầy đủ) → số byte tối đa của body. Đường không có trong ánh xạ đi thẳng qua."""

    def __init__(self, app: ASGIApp, limits: Mapping[tuple[str, str], int]) -> None:
        self.app = app
        self._limits = dict(limits)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = self._limits.get((scope["method"], scope["path"])) if scope["type"] == "http" else None
        if limit is None:
            await self.app(scope, receive, send)
            return
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await self._reject(scope, receive, send)  # từ chối sớm, không đọc byte nào
            return
        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return  # client đã bỏ đi: không còn ai để trả lời
            body = message.get("body", b"")
            total += len(body)
            if total > limit:
                await self._reject(scope, receive, send)  # dừng đọc ngay khi vượt, kể cả khi còn `more_body`
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()  # sau body chỉ còn `http.disconnect`

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        await error_response(Request(scope), "PAYLOAD_TOO_LARGE")(scope, receive, send)
