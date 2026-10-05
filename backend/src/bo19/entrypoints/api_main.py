"""Web Service — REST + 2 stream SSE + phục vụ client (06-structure.md mục Tiến trình) — composition root, không ai import entrypoints.

Bản S2 của Spike 1: chỉ bước kiểm khởi động #1, #2 và `GET /healthz`. Trượt bước kiểm nào thì ghi danh sách
mã trượt ra log rồi thoát mã 1 — không phục vụ request nào (mục Bước kiểm khởi động của 06-structure.md).
Không bao giờ ghi DSN hay mật khẩu ra log.
"""
from __future__ import annotations

import logging
import sys

import psycopg

from bo19.config.settings import load_settings
from bo19.startup.checks import run_s2_checks

log = logging.getLogger("bo19.startup")


def _startup() -> int | None:
    """Trả cổng để phục vụ, hoặc None khi trượt."""
    settings = load_settings()
    if settings.problems:  # tạm thời giữ hành vi cũ — thay bằng bộ chạy bước kiểm ở commit tích hợp
        for _, code in settings.problems:
            log.error("STARTUP_FAIL %s", code)
        return None
    try:
        with psycopg.connect(settings.database_url, connect_timeout=10, application_name="bo19-api-startup") as conn:
            fails = run_s2_checks(conn)
    except psycopg.Error as e:
        # Thông điệp của driver có thể mang host — chỉ ghi lớp lỗi và SQLSTATE.
        log.error("STARTUP_FAIL STARTUP_DB_CONNECT_FAILED class=%s sqlstate=%s", type(e).__name__, e.sqlstate)
        return None
    if fails:
        for code in fails:
            log.error("STARTUP_FAIL %s", code)
        log.error("STARTUP_ABORT %d bước kiểm trượt — thoát mã 1", len(fails))
        return None
    log.info("STARTUP_OK bước kiểm #1, #2 đạt")
    return settings.port


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    port = _startup()
    if port is None:
        sys.exit(1)

    import uvicorn
    from fastapi import FastAPI

    app = FastAPI(title="bo19", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        # Tiến trình chỉ phục vụ sau khi bước kiểm khởi động đạt; healthz chỉ báo "đang sống".
        return {"status": "ok"}

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
