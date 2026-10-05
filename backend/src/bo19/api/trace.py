"""Middleware ASGI thuần: mỗi request HTTP là một đơn vị công việc có `trace_id` riêng (ADR-024; mục Log schema của 11-ops.md).

Không dùng `BaseHTTPMiddleware`: nó chạy phần còn lại trong một task khác, và bộ xử lý lỗi của lớp ngoài cùng (`ServerErrorMiddleware`)
chạy ngoài middleware người dùng nên không thấy contextvar. `trace_id` được đặt cả vào ASGI scope — dict dùng chung cho mọi lớp — để lỗi 500
cũng mang `trace_id` đúng (mục Lỗi chuẩn hoá của 05-api.md: "Có cả ở lỗi 500").
"""
from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from bo19.api.errors import TRACE_SCOPE_KEY
from bo19.observability.trace import trace_scope


class TraceMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with trace_scope() as trace_id:
            scope[TRACE_SCOPE_KEY] = trace_id
            await self.app(scope, receive, send)
