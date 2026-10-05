"""Web Service — REST + 2 stream SSE + phục vụ client (06-structure.md mục Tiến trình) — composition root, không ai import entrypoints.

Bước đầu tiên của mọi entrypoint: cài handler log mask duy nhất (`observability`), rồi chạy bộ bước kiểm khởi động của `bo19.startup`.
Trượt bước Chặn nào thì danh sách mã trượt đã được ghi ra log; tiến trình thoát mã 1 và không phục vụ request nào (mục Bước kiểm khởi động
của 06-structure.md). Không bao giờ ghi DSN, secret hay giá trị biến ra log.

`uvicorn.run(log_config=None)`: uvicorn không tự cài handler riêng — mọi bản ghi của nó đi qua handler mask duy nhất, bị rút về tên logger,
mức và kiểu lỗi (mục Nghĩa vụ kế thừa của 06-structure.md). Import fastapi/uvicorn ở đầu file, trước bước kiểm #10, để nếu thư viện nào
tự gắn handler vào root logger lúc import thì bước kiểm #10 thấy.

Sau bước kiểm: mở pool kết nối `bo19_app` (`persistence.pool`), dựng app bằng `bo19.api.app.create_app`, đóng pool khi uvicorn thoát (B3).
"""
from __future__ import annotations

import os
import sys

import uvicorn

from bo19.api.app import create_app
from bo19.api.auth.hasher import PasswordVerifier
from bo19.api.deps.state import AppState
from bo19.config.settings import load_settings
from bo19.observability.log import configure_logging
from bo19.persistence.pool import Pool
from bo19.startup.model import Entry
from bo19.startup.runner import run


def main() -> None:
    configure_logging()
    settings = load_settings()
    if not run(Entry.API, settings, os.environ).ok:
        sys.exit(1)
    pool = Pool(settings.database_url, application_name="bo19-api")
    pool.open()
    try:
        app = create_app(AppState(pool=pool, session_secret=settings.session_secret, verifier=PasswordVerifier.from_settings(settings)))
        # `proxy_headers=False`: uvicorn không được tự đọc X-Forwarded-For. IP của rate limit đọc ở đúng một hàm, `bo19.api.auth.client_ip` (A-062, cổng 2.7).
        uvicorn.run(app, host="0.0.0.0", port=settings.port, log_config=None, log_level="info", proxy_headers=False)
    finally:
        pool.close()


if __name__ == "__main__":
    main()
