"""app factory — mount `/api/v1`, luật 404, middleware trace (mục Cây backend của 06-structure.md, bo19.api; mục Phục vụ tĩnh và luật 404 — phía api).

Không chứa business logic. Router thật nằm ở `api/routers/`. Luật phía `/api` (B3): đường lạ thuộc `/api` trả `ErrorEnvelope` `NOT_FOUND` (O1-8). **B10a:** khi `AppState.static_dir` có giá trị, `api.static` phục vụ bản build client — asset thật, file lạ dưới `/assets` → 404,
mọi GET lạ còn lại → `index.html`; bước kiểm khởi động #8 bảo đảm bản build có mặt.
"""
from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI

from bo19.api.body_limit import BodyLimitMiddleware
from bo19.api.deps.csrf import require_csrf_header
from bo19.api.deps.state import AppState
from bo19.api.errors import install_exception_handlers
from bo19.api.files_gate import FileGate
from bo19.api.routers import auth, chat, documents, files, requests
from bo19.api.static import install_static
from bo19.api.trace import TraceMiddleware
from bo19.config import working_values as wv

API_PREFIX = "/api/v1"
BODY_LIMITS = {
    ("POST", f"{API_PREFIX}/auth/session"): wv.LOGIN_BODY_MAX_BYTES,  # O1-10: endpoint công khai duy nhất
    ("POST", re.compile(re.escape(f"{API_PREFIX}/chat-sessions/") + r"[^/]+/turns")): wv.TURN_BODY_MAX_BYTES,  # B6b (PO 2026-10-12): `{id}` là một đoạn bất kỳ — id hỏng cũng bị chặn trước khi đọc body
}


def default_routers() -> list[APIRouter]:
    return [auth.router, chat.router, requests.router, documents.router, files.router]


def create_app(state: AppState, *, routers: Sequence[APIRouter] | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if state.supervisor is not None:  # SIGTERM: chờ lượt đang chạy trong cửa sổ drain, rồi huỷ hợp tác phần còn lại (ADR-016, hệ quả 2)
            await state.supervisor.aclose(state.drain_s)

    app = FastAPI(title="bo19", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.bo19 = state
    app.state.file_gate = FileGate(state.file_fetch)  # một cho cả tiến trình: trần số lượt tải file đồng thời (WV-27)
    app.add_middleware(BodyLimitMiddleware, limits=BODY_LIMITS)  # thêm trước Trace: Trace là lớp ngoài, nên 413 cũng mang trace_id
    app.add_middleware(TraceMiddleware)
    install_exception_handlers(app)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        # Tiến trình chỉ phục vụ sau khi bước kiểm khởi động đạt; healthz chỉ báo "đang sống".
        return {"status": "ok"}

    v1 = APIRouter(prefix=API_PREFIX, dependencies=[Depends(require_csrf_header)])
    for router in default_routers() if routers is None else routers:
        v1.include_router(router)
    app.include_router(v1)
    if state.static_dir is not None:
        install_static(app, state.static_dir)  # SAU CÙNG: catch-all GET chỉ nhận cái các tuyến trên không nhận
    return app
