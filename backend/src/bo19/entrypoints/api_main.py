"""Web Service — REST + 2 stream SSE + phục vụ client (06-structure.md mục Tiến trình) — composition root, không ai import entrypoints.

Bản S2 của Spike 1: chỉ bước kiểm khởi động #1, #2 và `GET /healthz`. Trượt bước kiểm nào thì ghi danh sách
mã trượt ra log rồi thoát mã 1 — không phục vụ request nào (mục Bước kiểm khởi động của 06-structure.md).
Không bao giờ ghi DSN hay mật khẩu ra log.
"""
from __future__ import annotations

import logging
import sys

import psycopg

from bo19.config.settings import ConfigError, load_settings
from bo19.startup.checks import run_s2_checks

log = logging.getLogger("bo19.startup")


def _startup() -> int | None:
    """Trả cổng để phục vụ, hoặc None khi trượt."""
    try:
        settings = load_settings()
    except ConfigError as e:
        log.error("STARTUP_FAIL %s", e)
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


# ===== SPIKE S4 (A-031, A-086) — GỠ HẲN ở bước dọn: khối này và các dòng "SPIKE S4" trong main() =====
# Đo shutdown delay thật của Web Service free: khi nhận SIGTERM, KHÔNG thoát — mỗi giây ghi một dòng có giờ UTC của chính app
# tới khi bị SIGKILL (mốc kill = dòng cuối thấy được) hoặc tới trần BO19_S4_HOLD_S. Chỉ bật khi biến đó được đặt; thiếu thì api_main
# chạy như bản S2. Mọi dòng in bằng print(flush=True): uvicorn không ghi giờ vào log, và dòng cuối trước SIGKILL phải còn trong log.
import asyncio  # noqa: E402
import contextlib  # noqa: E402
import copy  # noqa: E402
import os  # noqa: E402
import signal  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

import uvicorn  # noqa: E402

_S4 = {"t_sigterm": None, "boot_utc": None}  # t_sigterm: time.monotonic() lúc nhận SIGTERM


def _s4_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


_S4["boot_utc"] = _s4_utc()


def _s4_emit(line: str) -> None:
    print(line, flush=True)


def _s4_log_config() -> dict:
    """Log của uvicorn (gồm access log) mang giờ UTC — để đọc được giờ của request cuối và của 'Shutting down'."""
    cfg = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    for name in ("default", "access"):
        cfg["formatters"][name]["fmt"] = "%(asctime)sZ " + cfg["formatters"][name]["fmt"]
    logging.Formatter.converter = time.gmtime
    return cfg


class _S4Server(uvicorn.Server):
    def handle_exit(self, sig, frame) -> None:  # noqa: ANN001
        if sig == signal.SIGTERM and _S4["t_sigterm"] is None:
            _S4["t_sigterm"] = time.monotonic()
            _s4_emit(f"SIGTERM_RECEIVED utc={_s4_utc()} pid={os.getpid()} boot_utc={_S4['boot_utc']}")
        super().handle_exit(sig, frame)


@contextlib.asynccontextmanager
async def _s4_lifespan(app):  # noqa: ANN001
    yield
    cap_raw = os.environ.get("BO19_S4_HOLD_S")
    if not cap_raw:
        return
    cap, t0, n = float(cap_raw), time.monotonic(), 0
    base = _S4["t_sigterm"] if _S4["t_sigterm"] is not None else t0
    while time.monotonic() - t0 < cap:
        n += 1
        _s4_emit(f"SHUTDOWN_HOLD n={n} utc={_s4_utc()} since_sigterm={time.monotonic() - base:.3f}")
        await asyncio.sleep(max(0.0, t0 + n - time.monotonic()))
    _s4_emit(f"HOLD_CAP_REACHED n={n} utc={_s4_utc()} since_sigterm={time.monotonic() - base:.3f}")
    # uvicorn 0.34.2: sau shutdown êm, capture_signals gọi lại signal.raise_signal với handler gốc. Ngoài container, tiến trình sẽ chết
    # vì SIGTERM (không phải mã 0); trong container api_main là PID 1 nên tín hiệu bị bỏ qua và thoát mã 0 (đã thấy ở đối chứng local).
    # PROCESS_EXIT vì vậy phải ghi ở đây, trước lúc đó.
    _s4_emit(f"PROCESS_EXIT utc={_s4_utc()} since_sigterm={time.monotonic() - base:.3f}")


# ===== hết khối SPIKE S4 =====


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    port = _startup()
    if port is None:
        sys.exit(1)

    import uvicorn
    from fastapi import FastAPI

    app = FastAPI(title="bo19", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_s4_lifespan)  # SPIKE S4: bỏ lifespan=

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        # Tiến trình chỉ phục vụ sau khi bước kiểm khởi động đạt; healthz chỉ báo "đang sống".
        return {"status": "ok"}

    if os.environ.get("BO19_S4_HOLD_S"):  # SPIKE S4: gỡ cả nhánh if, giữ nhánh else
        _s4_emit(f"S4_ARMED utc={_s4_utc()} cap_s={os.environ['BO19_S4_HOLD_S']} pid={os.getpid()} boot_utc={_S4['boot_utc']}")
        _S4Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info", log_config=_s4_log_config())).run()
    else:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
