"""Background Worker — vòng poll SKIP LOCKED (06-structure.md mục Tiến trình) — composition root, không ai import entrypoints.

Cùng khuôn `api_main`: cài handler log mask trước, chạy bộ bước kiểm khởi động của cột `worker` (trượt bước Chặn thì thoát mã 1, không giành job nào), mở pool `bo19_app`, rồi chạy `queue_worker.dispatcher`.
**Chỉ giành loại job có handler.** Từ B9a `render_document` có handler (`DocumentRunner`: `document_graph` tới `await_content_review`) — đăng ký **khi có object storage, khoá LLM và khoá dấu vân tay render**; thiếu một trong ba thì không
đăng ký (log `RENDER_HANDLER_NOT_REGISTERED`, chỉ lý do dạng mã) và job `render_document` do `request_submit` đưa vào hàng đợi vẫn `QUEUED`, như ở B8a — không bị giành rồi `FAILED` vì thiếu cấu hình.

Tắt êm (mục Tắt tiến trình êm của 06-structure.md): `SIGTERM`/`SIGINT` → ghi log (O1-5: `SIGTERM_RECEIVED`/`SIGNAL_RECEIVED`, `PROCESS_EXIT` kèm thời gian từ `SIGTERM`), ngừng giành job mới, chờ job đang chạy tới
`BO19_SHUTDOWN_DELAY_SECONDS`, job chưa xong thì `release` (không tiêu lượt thử). Không bao giờ ghi DSN, secret hay giá trị biến ra log.
"""
from __future__ import annotations

import os
import signal
import sys

from bo19.ai_gateway.gateway import build_gateway
from bo19.config.settings import Settings, load_settings
from bo19.observability.log import configure_logging, get_logger
from bo19.observability.shutdown import ShutdownLog
from bo19.orchestrator.runner import DocumentRunner
from bo19.persistence.pool import Pool
from bo19.queue_worker.dispatcher import Dispatcher
from bo19.queue_worker.handlers import build_handlers
from bo19.startup.model import Entry
from bo19.startup.runner import run
from bo19.tool_layer import storage as store


def open_document_runner(settings: Settings, pool: Pool) -> DocumentRunner | None:
    """`DocumentRunner` cho handler `render_document`, hoặc `None` (kèm log mã lý do) khi thiếu object storage hay khoá LLM. Composition root: không module nào khác dựng gateway và storage."""
    log = get_logger("bo19.worker")
    storage = store.from_settings(settings)
    if storage is None:
        log.warning("RENDER_HANDLER_NOT_REGISTERED", reason="OBJECT_STORAGE_NOT_CONFIGURED")
        return None
    if not settings.llm_api_key:
        log.warning("RENDER_HANDLER_NOT_REGISTERED", reason="LLM_API_KEY_MISSING")
        return None
    if not settings.render_fingerprint_key:  # bước kiểm #24 đã chặn trước khi tới đây; giữ lại để hàm không tự dựng runner với khoá rỗng
        log.warning("RENDER_HANDLER_NOT_REGISTERED", reason="RENDER_FINGERPRINT_KEY_MISSING")
        return None
    return DocumentRunner.open(pool=pool, gateway=build_gateway(settings, pool), storage=storage, dsn=settings.database_url, fingerprint_key=settings.render_fingerprint_key)


def serve(shutdown: ShutdownLog) -> int:
    """Mã thoát: 0 sau tắt êm, 1 khi bước kiểm khởi động trượt hay tiến trình sập. Ngoại lệ chỉ ghi kiểu — thông điệp có thể mang giá trị."""
    log = get_logger("bo19.worker")
    try:
        settings = load_settings()
        if not run(Entry.WORKER, settings, os.environ).ok:
            return 1
        pool = Pool(settings.database_url, application_name="bo19-worker", max_size=4)  # một job một lúc + heartbeat + thu hồi lease
        pool.open()
        runner = open_document_runner(settings, pool)
        try:
            dispatcher = Dispatcher(pool, build_handlers(document_runner=runner), drain_s=float(settings.shutdown_delay_s))

            def on_signal(sig: int, _frame: object) -> None:
                shutdown.received(sig)
                dispatcher.stop()

            signal.signal(signal.SIGTERM, on_signal)
            signal.signal(signal.SIGINT, on_signal)
            dispatcher.run_forever()
            return 0
        finally:
            if runner is not None:
                runner.close()
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
