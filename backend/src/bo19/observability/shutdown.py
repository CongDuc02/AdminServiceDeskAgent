"""Log tắt tiến trình — O1-5 (mục Tắt tiến trình êm của 06-structure.md; S4 của Spike 1): ghi **mọi tín hiệu nhận được** và **thời gian từ `SIGTERM` tới lúc thoát**, theo log JSON của mục Log schema của 11-ops.md.

Sự kiện: `SIGTERM_RECEIVED` (tín hiệu `SIGTERM`), `SIGNAL_RECEIVED` (tín hiệu khác, ví dụ `SIGINT`), `PROCESS_EXIT` (mã thoát, `seconds_since_sigterm` — `null` nếu chưa nhận `SIGTERM`). Giờ UTC là trường `timestamp` có sẵn
của mọi dòng log. Chỉ mã, tên tín hiệu và số — không giá trị nào khác. Dùng chung cho `api_main` và `worker_main`; entrypoint tương lai (`combined_main`) cũng gọi đúng hai hàm này.

`received` được gọi từ bộ xử lý tín hiệu (luồng chính): chỉ ghi log và đặt mốc — không chờ, không khoá nào ngoài khoá của `logging`.
"""
from __future__ import annotations

import signal
import time

from bo19.observability.log import get_logger


class ShutdownLog:
    def __init__(self, component: str) -> None:
        self._log = get_logger(component)
        self._sigterm_at: float | None = None
        self.signals: list[str] = []

    def received(self, sig: int) -> None:
        name = signal.Signals(sig).name
        self.signals.append(name)
        if sig == signal.SIGTERM:
            if self._sigterm_at is None:
                self._sigterm_at = time.monotonic()
            self._log.info("SIGTERM_RECEIVED", signal=name)
        else:
            self._log.info("SIGNAL_RECEIVED", signal=name)

    def exited(self, exit_code: int) -> None:
        since = None if self._sigterm_at is None else round(time.monotonic() - self._sigterm_at, 3)
        self._log.info("PROCESS_EXIT", exit_code=exit_code, seconds_since_sigterm=since, signals=",".join(self.signals) or None)
