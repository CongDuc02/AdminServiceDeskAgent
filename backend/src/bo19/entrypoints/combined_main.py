"""Entrypoint gộp cho Render gói free (ADR-033) — `api` và vòng poll job của `worker` trong MỘT tiến trình; chỉ chạy ở BO19_ENVIRONMENT = dev (bước kiểm khởi động #18, 06-structure.md mục Tiến trình) —
composition root, không ai import entrypoints.

Không có nhánh mã riêng: chỉ ghép hàm khởi chạy sẵn có của `api_main` (`open_api`, `_Server`) và `worker_main` (`open_document_runner`) với `Dispatcher`. Bước kiểm khởi động chạy HỢP mọi bước có ✔ ở bất kỳ cột nào, cộng #18.
Vòng poll chạy ở một luồng riêng: **một job một lúc** (WV-22) và LibreOffice tối đa **một** chuyển đổi một lúc (ADR-033). Một pool kết nối dùng chung.

**Tắt êm (B9a2; PO 2026-10-16)** — `SIGTERM` tới lúc `soffice` đang chuyển đổi (32–88 s ở 0,1 CPU) vẫn phải thoát trong ≈ 5 s của Render (A-031, S4): uvicorn bắt đầu drain lượt chat và vòng poll ngừng giành job ĐỒNG THỜI
(`_Server.on_exit` → `Dispatcher.stop`); job đang chạy được `COMBINED_JOB_DRAIN_S` (WV-32) để xong; chưa xong thì `convert.abort_all` giết nhóm tiến trình `soffice`, job được `release` (không tiêu lượt thử — lần thử sau tiếp từ checkpoint, ADR-039)
rồi tiến trình thoát. Cuối cùng bộ dọn zombie ghi `PROCESS_TABLE_AT_EXIT` (số con còn lại, số zombie, tên tiến trình còn sống) — thấy `soffice` mồ côi hay zombie ở đó là lỗi. Bộ dọn zombie chạy khi tiến trình là PID 1.
Bộ hẹn giờ cron CHƯA có ở đây: chưa có thao tác cron nào để gọi (PO 2026-10-16) — nó đi cùng thao tác cron đầu tiên.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from collections.abc import Callable

import uvicorn

from bo19.config import working_values as wv
from bo19.config.settings import load_settings
from bo19.entrypoints.api_main import _Server, install_original_signal_handlers, open_api, run_server
from bo19.entrypoints.worker_main import open_document_runner
from bo19.observability import reaper
from bo19.observability.log import configure_logging, get_logger
from bo19.observability.shutdown import ShutdownLog
from bo19.persistence.pool import Pool
from bo19.queue_worker.dispatcher import Dispatcher
from bo19.queue_worker.handlers import build_handlers
from bo19.startup.model import Entry
from bo19.startup.runner import run
from bo19.tool_layer.rendering import convert

POOL_EXTRA = 3  # cho vòng poll: giành job, heartbeat, tool của handler — thêm vào cỡ pool của api


def make_signal_handler(shutdown: ShutdownLog, dispatcher: Dispatcher) -> Callable[[int, object], None]:
    """Bộ xử lý GỐC của SIGTERM/SIGINT (xem `api_main.install_original_signal_handlers`) — nhưng ở đây còn PHẢI dừng vòng poll. Tín hiệu tới trước khi uvicorn cài bộ xử lý của nó (lúc khởi động) không được mất:
    bản đầu chỉ ghi log, nên tiến trình không bao giờ thoát (test `test_sigterm_khi_roi_khong_co_job_thoat_nhanh` treo ở 30 s dưới tải). `serve` còn kiểm `shutdown.signals` trước khi chạy uvicorn."""
    def handler(sig: int, _frame: object) -> None:
        if not shutdown.signals:
            shutdown.received(sig)
        dispatcher.stop()

    return handler


def serve(shutdown: ShutdownLog) -> int:
    """Mã thoát: 0 sau tắt êm, 1 khi bước kiểm khởi động trượt hay tiến trình sập. Ngoại lệ chỉ ghi kiểu — thông điệp có thể mang giá trị."""
    log = get_logger("bo19.combined")
    try:
        settings = load_settings()
        if not run(Entry.COMBINED, settings, os.environ).ok:
            return 1
        pool = Pool(settings.database_url, application_name="bo19-combined", max_size=wv.POOL_MAX_SIZE + POOL_EXTRA)
        pool.open()
        api_runner, app = open_api(settings, pool)
        doc_runner = open_document_runner(settings, pool)
        reap = reaper.start_if_init(convert.live_pids)
        dispatcher = Dispatcher(pool, build_handlers(document_runner=doc_runner), drain_s=min(float(settings.shutdown_delay_s), wv.COMBINED_JOB_DRAIN_S), on_drain_expired=convert.abort_all)
        poller = threading.Thread(target=dispatcher.run_forever, name="job-poll")
        try:
            handler = make_signal_handler(shutdown, dispatcher)
            signal.signal(signal.SIGTERM, handler)
            signal.signal(signal.SIGINT, handler)
            if shutdown.signals:  # tín hiệu đã tới trong lúc bước kiểm/dựng: vòng poll không được chạy
                dispatcher.stop()
            poller.start()
            run_server(_Server(uvicorn.Config(app, host="0.0.0.0", port=settings.port, log_config=None, log_level="info", proxy_headers=False), shutdown, on_exit=dispatcher.stop), shutdown)
            dispatcher.stop()  # uvicorn thoát vì lý do khác tín hiệu (lỗi bind cổng): vòng poll cũng phải dừng
            poller.join(timeout=float(settings.shutdown_delay_s))
            if poller.is_alive():
                log.error("JOB_POLL_NOT_STOPPED")
            return 0
        finally:
            convert.abort_all()  # không để lại `soffice` nào sau khi tiến trình đã quyết định thoát
            convert.wait_idle(2.0)  # chủ của chuyển đổi thu xác con trực tiếp trước khi bộ dọn quét lần cuối
            if doc_runner is not None:
                doc_runner.close()
            api_runner.close()
            pool.close()
            if reap is not None:
                reap.stop()
    except Exception as e:  # noqa: BLE001
        log.critical("COMBINED_CRASHED", exc=e)
        return 1


def main() -> None:
    configure_logging()
    shutdown = ShutdownLog("bo19.combined")
    install_original_signal_handlers(shutdown)  # NGAY từ đầu (xem api_main.main); `serve` thay bằng bộ xử lý biết dừng vòng poll khi đã dựng xong
    code = serve(shutdown)
    shutdown.exited(code)
    # Thoát CỨNG sau khi mọi thứ đã đóng tường minh: `sys.exit` còn chờ tiến trình hoàn tất interpreter (nối luồng nền của thư viện, giải phóng module) — đo ở B9a2 trong cgroup 0,1 CPU:
    # `PROCESS_EXIT` ghi lúc 1,3 s sau SIGTERM nhưng container chỉ dừng lúc ≈ 10 s, quá hạn ≈ 5 s của Render. Log đã được xả trước khi `os._exit`.
    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    main()
