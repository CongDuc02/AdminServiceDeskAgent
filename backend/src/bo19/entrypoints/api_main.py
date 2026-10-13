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

import uvicorn

from bo19.api.app import create_app
from bo19.api.auth.hasher import PasswordVerifier
from bo19.ai_gateway.gateway import build_gateway
from bo19.api.deps.state import AppState
from bo19.api.turns import TurnSupervisor
from bo19.config.settings import load_settings
from bo19.observability.log import configure_logging
from bo19.observability.shutdown import ShutdownLog
from bo19.orchestrator.runner import IntakeRunner
from bo19.persistence.pool import Pool
from bo19.startup.model import Entry
from bo19.startup.runner import run


class _Server(uvicorn.Server):
    """`uvicorn.Server` với log tín hiệu (O1-5): `handle_exit` là bộ xử lý mà uvicorn cài cho `SIGINT`/`SIGTERM`; ghi log rồi để uvicorn làm phần của nó (ngừng nhận kết nối, `lifespan` đóng êm)."""

    def __init__(self, config: uvicorn.Config, shutdown: ShutdownLog) -> None:
        super().__init__(config)
        self._shutdown = shutdown

    def handle_exit(self, sig: int, frame: object) -> None:
        self._shutdown.received(sig)
        super().handle_exit(sig, frame)


def serve(shutdown: ShutdownLog) -> int:
    settings = load_settings()
    if not run(Entry.API, settings, os.environ).ok:
        return 1
    pool = Pool(settings.database_url, application_name="bo19-api")
    pool.open()
    runner = IntakeRunner.open(pool=pool, gateway=build_gateway(settings, pool), dsn=settings.database_url)  # khuôn đã qua #23, khoá API đã qua #22; checkpointer không `setup()`
    try:
        supervisor = TurnSupervisor(runner, pool, deadline_s=settings.turn_deadline_s)
        app = create_app(AppState(pool=pool, session_secret=settings.session_secret, verifier=PasswordVerifier.from_settings(settings), supervisor=supervisor,
                                  turn_deadline_s=settings.turn_deadline_s, turn_margin_s=settings.turn_margin_s, drain_s=float(settings.shutdown_delay_s)))
        # `proxy_headers=False`: uvicorn không được tự đọc X-Forwarded-For. IP của rate limit đọc ở đúng một hàm, `bo19.api.auth.client_ip` (A-062, cổng 2.7).
        # Bộ xử lý GỐC của SIGTERM/SIGINT: sau khi tắt xong, uvicorn khôi phục bộ xử lý gốc rồi BẮN LẠI tín hiệu đã bắt (`capture_signals`). Để mặc định thì tiến trình chết `-15` trước khi kịp ghi `PROCESS_EXIT`
        # (chỉ PID 1 trong container thoát mã 0 — S4). Bộ xử lý này không làm gì thêm, trừ khi tín hiệu tới TRƯỚC khi uvicorn cài bộ xử lý của nó (lúc khởi động) — khi đó chỉ ghi log.
        def original(sig: int, _frame: object) -> None:
            if not shutdown.signals:
                shutdown.received(sig)

        signal.signal(signal.SIGTERM, original)
        signal.signal(signal.SIGINT, original)
        _Server(uvicorn.Config(app, host="0.0.0.0", port=settings.port, log_config=None, log_level="info", proxy_headers=False), shutdown).run()
        return 0
    finally:
        runner.close()
        pool.close()


def main() -> None:
    configure_logging()
    shutdown = ShutdownLog("bo19.api")
    code = serve(shutdown)
    shutdown.exited(code)
    sys.exit(code)


if __name__ == "__main__":
    main()
