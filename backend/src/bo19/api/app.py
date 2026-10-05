"""app factory — mount `/api/v1`, luật 404, middleware trace (mục Cây backend của 06-structure.md, bo19.api; mục Phục vụ tĩnh và luật 404 — phía api).

Không chứa business logic. Router thật nằm ở `api/routers/`. B3 chưa phục vụ bản build client (chưa có bản build; bước kiểm khởi động #8 chưa làm):
chỉ có luật phía `/api` — đường lạ thuộc `/api` trả `ErrorEnvelope` `NOT_FOUND` (O1-8). Phần "mọi GET lạ còn lại → index.html" thêm khi có client.
"""
from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, Depends, FastAPI

from bo19.api.deps.csrf import require_csrf_header
from bo19.api.deps.state import AppState
from bo19.api.errors import install_exception_handlers
from bo19.api.trace import TraceMiddleware

API_PREFIX = "/api/v1"


def default_routers() -> list[APIRouter]:
    return []


def create_app(state: AppState, *, routers: Sequence[APIRouter] | None = None) -> FastAPI:
    app = FastAPI(title="bo19", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.bo19 = state
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
    return app
