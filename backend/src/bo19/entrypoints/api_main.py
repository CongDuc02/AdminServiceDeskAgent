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
import signal
import sys
import threading
from pathlib import Path
from collections.abc import Callable

import uvicorn
from fastapi import FastAPI

from bo19.api.app import create_app
from bo19.api.auth.hasher import PasswordVerifier
from bo19.ai_gateway.gateway import build_gateway
from bo19.api.deps.state import AppState
from bo19.api.turns import TurnSupervisor
from bo19.config.settings import Settings, load_settings
from bo19.observability import reaper
from bo19.observability.log import configure_logging
from bo19.observability.shutdown import ShutdownLog
from bo19.orchestrator.runner import IntakeRunner
from bo19.persistence.pool import Pool
from bo19.startup.model import Entry
from bo19.startup.runner import run
from bo19.tool_layer.storage import from_settings as storage_from_settings


class _Server(uvicorn.Server):
    """`uvicorn.Server` với log tín hiệu (O1-5): `handle_exit` là bộ xử lý mà uvicorn cài cho `SIGINT`/`SIGTERM`; ghi log rồi để uvicorn làm phần của nó (ngừng nhận kết nối, `lifespan` đóng êm)."""

    def __init__(self, config: uvicorn.Config, shutdown: ShutdownLog, on_exit: Callable[[], object] | None = None) -> None:
        super().__init__(config)
        self._shutdown = shutdown
        self._on_exit = on_exit  # `combined_main`: dừng vòng poll job cùng lúc uvicorn bắt đầu drain

    def handle_exit(self, sig: int, frame: object) -> None:
        self._shutdown.received(sig)
        if self._on_exit is not None:
            self._on_exit()
        super().handle_exit(sig, frame)


def open_api(settings: Settings, pool: Pool) -> tuple[IntakeRunner, FastAPI]:
    """`IntakeRunner` và app FastAPI từ cấu hình đã qua bước kiểm khởi động — dùng chung với `combined_main` (ADR-033: chỉ ghép hàm có sẵn)."""
    runner = IntakeRunner.open(pool=pool, gateway=build_gateway(settings, pool), dsn=settings.database_url)  # khuôn đã qua #23, khoá API đã qua #22; checkpointer không `setup()`
    supervisor = TurnSupervisor(runner, pool, deadline_s=settings.turn_deadline_s)
    app = create_app(AppState(pool=pool, session_secret=settings.session_secret, verifier=PasswordVerifier.from_settings(settings), supervisor=supervisor,
                              turn_deadline_s=settings.turn_deadline_s, turn_margin_s=settings.turn_margin_s, drain_s=float(settings.shutdown_delay_s),
                              storage=storage_from_settings(settings), static_dir=Path(settings.static_dir)))
    return runner, app


def install_original_signal_handlers(shutdown: ShutdownLog) -> None:
    """Bộ xử lý GỐC của SIGTERM/SIGINT: sau khi tắt xong, uvicorn khôi phục bộ xử lý gốc rồi BẮN LẠI tín hiệu đã bắt (`capture_signals`). Để mặc định thì tiến trình chết `-15` trừ khi nó là PID 1 (S4);
    bộ xử lý này không làm gì thêm, trừ khi tín hiệu tới TRƯỚC khi uvicorn cài bộ xử lý của nó (lúc khởi động) — khi đó chỉ ghi log."""
    def original(sig: int, _frame: object) -> None:
        if not shutdown.signals:
            shutdown.received(sig)

    signal.signal(signal.SIGTERM, original)
    signal.signal(signal.SIGINT, original)


def watch_for_signal(shutdown: ShutdownLog, server: uvicorn.Server, finished: threading.Event, interval_s: float = 0.05) -> None:
    """Cầu nối cho tín hiệu tới TRONG KHOẢNG từ lúc bộ xử lý gốc được cài tới lúc uvicorn cài bộ xử lý của nó (dựng event loop, nạp cấu hình — hàng trăm ms ở 0,1 CPU): uvicorn không biết gì về nó và sẽ chạy mãi.
    Thấy `shutdown.signals` thì đặt `should_exit` — đúng việc `handle_exit` của uvicorn làm. (B9a2: tìm ra ở `combined_main`; `api_main` — thứ Render đang chạy — có cùng khoảng hở.)"""
    while not finished.wait(interval_s):
        if shutdown.signals:
            server.should_exit = True
            return


def run_server(server: uvicorn.Server, shutdown: ShutdownLog) -> None:
    """Chạy uvicorn với cầu nối tín hiệu; không chạy gì nếu tín hiệu đã tới trong lúc dựng."""
    finished = threading.Event()
    threading.Thread(target=watch_for_signal, args=(shutdown, server, finished), name="signal-watch", daemon=True).start()
    try:
        if not shutdown.signals:
            server.run()
    finally:
        finished.set()


def serve(shutdown: ShutdownLog) -> int:
    settings = load_settings()
    if not run(Entry.API, settings, os.environ).ok:
        return 1
    pool = Pool(settings.database_url, application_name="bo19-api")
    pool.open()
    runner, app = open_api(settings, pool)
    reap = reaper.start_if_init()  # PID 1 của container: dọn zombie mồ côi (B9a2); api không sinh tiến trình con nhưng là PID 1 trên Render
    try:
        # `proxy_headers=False`: uvicorn không được tự đọc X-Forwarded-For. IP của rate limit đọc ở đúng một hàm, `bo19.api.auth.client_ip` (A-062, cổng 2.7).
        run_server(_Server(uvicorn.Config(app, host="0.0.0.0", port=settings.port, log_config=None, log_level="info", proxy_headers=False), shutdown), shutdown)
        return 0
    finally:
        if reap is not None:
            reap.stop()
        runner.close()
        pool.close()


def main() -> None:
    configure_logging()
    shutdown = ShutdownLog("bo19.api")
    install_original_signal_handlers(shutdown)  # NGAY từ đầu: SIGTERM tới trong lúc bước kiểm/dựng app không được giết tiến trình bằng hành vi mặc định (-15, không log) — `run_server` thấy tín hiệu đã ghi và không chạy uvicorn
    code = serve(shutdown)
    shutdown.exited(code)
    sys.exit(code)


if __name__ == "__main__":
    main()
