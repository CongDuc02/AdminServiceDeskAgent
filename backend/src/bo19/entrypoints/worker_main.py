"""Background Worker — vòng poll SKIP LOCKED (06-structure.md mục Tiến trình) — composition root, không ai import entrypoints.

Cùng khuôn `api_main`: cài handler log mask trước, chạy bộ bước kiểm khởi động của cột `worker` (trượt bước Chặn thì thoát mã 1, không giành job nào), mở pool `bo19_app`, rồi chạy `queue_worker.dispatcher`.
**Chỉ giành loại job có handler** — ở B8a production **chưa đăng ký handler nào** (`render_document` thuộc B9a), nên job `render_document` do `request_submit` đưa vào hàng đợi vẫn `QUEUED`.

Tắt êm (mục Tắt tiến trình êm của 06-structure.md): `SIGTERM`/`SIGINT` → ghi log (O1-5: `SIGTERM_RECEIVED`/`SIGNAL_RECEIVED`, `PROCESS_EXIT` kèm thời gian từ `SIGTERM`), ngừng giành job mới, chờ job đang chạy tới
`BO19_SHUTDOWN_DELAY_SECONDS`, job chưa xong thì `release` (không tiêu lượt thử). Không bao giờ ghi DSN, secret hay giá trị biến ra log.
"""
from __future__ import annotations

import os
import signal
import sys

from bo19.config.settings import load_settings
from bo19.observability.log import configure_logging, get_logger
from bo19.observability.shutdown import ShutdownLog
from bo19.persistence.pool import Pool
from bo19.queue_worker.dispatcher import Dispatcher
from bo19.queue_worker.handlers import DEFAULT_HANDLERS
from bo19.startup.model import Entry
from bo19.startup.runner import run


def serve(shutdown: ShutdownLog) -> int:
    """Mã thoát: 0 sau tắt êm, 1 khi bước kiểm khởi động trượt hay tiến trình sập. Ngoại lệ chỉ ghi kiểu — thông điệp có thể mang giá trị."""
    log = get_logger("bo19.worker")
    try:
        settings = load_settings()
        if not run(Entry.WORKER, settings, os.environ).ok:
            return 1
        pool = Pool(settings.database_url, application_name="bo19-worker", max_size=4)  # một job một lúc + heartbeat + thu hồi lease
        pool.open()
        try:
            dispatcher = Dispatcher(pool, DEFAULT_HANDLERS, drain_s=float(settings.shutdown_delay_s))

            def on_signal(sig: int, _frame: object) -> None:
                shutdown.received(sig)
                dispatcher.stop()

            signal.signal(signal.SIGTERM, on_signal)
            signal.signal(signal.SIGINT, on_signal)
            dispatcher.run_forever()
            return 0
        finally:
            pool.close()
    except Exception as e:  # noqa: BLE001
        log.critical("WORKER_CRASHED", exc=e)
        return 1


def main() -> None:
    configure_logging()
    shutdown = ShutdownLog("bo19.worker")
    code = serve(shutdown)
    shutdown.exited(code)
    sys.exit(code)


if __name__ == "__main__":
    main()
