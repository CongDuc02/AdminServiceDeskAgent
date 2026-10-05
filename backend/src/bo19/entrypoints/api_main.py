"""Web Service — REST + 2 stream SSE + phục vụ client (06-structure.md mục Tiến trình) — composition root, không ai import entrypoints.

Bước đầu tiên của mọi entrypoint: cài handler log mask duy nhất (`observability`), rồi chạy bộ bước kiểm khởi động của `bo19.startup`.
Trượt bước Chặn nào thì danh sách mã trượt đã được ghi ra log; tiến trình thoát mã 1 và không phục vụ request nào (mục Bước kiểm khởi động
của 06-structure.md). Không bao giờ ghi DSN, secret hay giá trị biến ra log.

`uvicorn.run(log_config=None)`: uvicorn không tự cài handler riêng — mọi bản ghi của nó đi qua handler mask duy nhất, bị rút về tên logger,
mức và kiểu lỗi (mục Nghĩa vụ kế thừa của 06-structure.md). Import fastapi/uvicorn ở đầu file, trước bước kiểm #10, để nếu thư viện nào
tự gắn handler vào root logger lúc import thì bước kiểm #10 thấy.
"""
from __future__ import annotations

import os
import sys

import uvicorn
from fastapi import FastAPI

from bo19.config.settings import load_settings
from bo19.observability.log import configure_logging
from bo19.startup.model import Entry
from bo19.startup.runner import run


def build_app() -> FastAPI:
    app = FastAPI(title="bo19", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        # Tiến trình chỉ phục vụ sau khi bước kiểm khởi động đạt; healthz chỉ báo "đang sống".
        return {"status": "ok"}

    return app


def main() -> None:
    configure_logging()
    settings = load_settings()
    if not run(Entry.API, settings, os.environ).ok:
        sys.exit(1)
    uvicorn.run(build_app(), host="0.0.0.0", port=settings.port, log_config=None, log_level="info")


if __name__ == "__main__":
    main()
