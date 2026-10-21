"""Phục vụ bản build client và luật 404 phía `api` (mục 10.4 của 06-structure.md; ADR-013, ADR-018; O1-8).

| Yêu cầu | Trả |
|---|---|
| Đường dẫn khớp một endpoint dưới `/api/v1` | Endpoint đó (không qua file này) |
| Đường dẫn lạ **thuộc** `/api` | `ErrorEnvelope` `NOT_FOUND` 404 — **không bao giờ** `index.html` |
| File lạ dưới thư mục asset (`/assets/…`) | 404 (`ErrorEnvelope`), **không** `index.html` |
| File có thật ở gốc bản build (ví dụ `favicon.ico`) | File đó |
| Mọi GET lạ còn lại | `index.html` (SPA tự dựng trang "không tìm thấy" cho tuyến lạ) |

Nuốt 404 của API thành một trang HTML là lỗi rất khó truy: client nhận mã 200 kèm HTML ở chỗ chờ JSON (ADR-018). Cache: asset đã băm tên (`/assets/*`, Vite) cache một năm, `immutable`;
`index.html` và file khác không cache — đổi bản build thì trình duyệt thấy ngay. Đường dẫn được `resolve()` rồi kiểm nằm trong thư mục build: `..` và liên kết biểu tượng không thoát ra ngoài.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from bo19.api.errors import error_response, is_api_path

ASSETS_PREFIX = "assets/"
IMMUTABLE = "public, max-age=31536000, immutable"
NO_STORE = "no-store"


def install_static(app: FastAPI, static_dir: Path) -> None:
    root = static_dir.resolve()
    index = root / "index.html"

    def inside(candidate: str) -> Path | None:
        try:
            target = (root / candidate).resolve()
        except (OSError, ValueError):
            return None
        return target if target.is_file() and target.is_relative_to(root) else None

    def serve(file: Path, cache: str) -> Response:
        return FileResponse(file, headers={"Cache-Control": cache, "X-Content-Type-Options": "nosniff"})

    async def spa(request: Request, path: str) -> Response:
        if is_api_path(request.url.path):
            raise StarletteHTTPException(404)  # → bộ xử lý lỗi của `api`: ErrorEnvelope NOT_FOUND
        if path.startswith(ASSETS_PREFIX):
            file = inside(path)
            return serve(file, IMMUTABLE) if file is not None else error_response(request, "NOT_FOUND")
        if path and path != "index.html":
            file = inside(path)
            if file is not None:
                return serve(file, NO_STORE)
        return serve(index, NO_STORE)

    app.add_api_route("/{path:path}", spa, methods=["GET", "HEAD"], include_in_schema=False)
