"""Vòng poll của `queue_worker` (ADR-004, ADR-010, ADR-033; mục Retry của 11-ops.md; WV-20, WV-21, WV-22).

Mỗi vòng: `reclaim_expired` (job của worker đã chết) → `claim` (chỉ loại có handler) → chạy handler → `succeed`/`fail`. **Một job một lúc** (WV-22). Trong lúc handler chạy, một thread nền `heartbeat` mỗi `heartbeat_s`;
`heartbeat` trả `False` (mất lease) thì cờ huỷ của job được đặt — handler phải dừng, và mọi lệnh ghi muộn của nó bị hàng rào chủ lease của `tool_layer.jobs` từ chối.

**Tắt êm (`stop`):** ngừng giành job mới; job đang chạy được chờ tới `drain_s`; chưa xong thì đặt cờ huỷ, `release` (không tiêu lượt thử) rồi bỏ cuộc chờ. Thread của handler là daemon: tiến trình thoát thì nó chết theo — một
lệnh ghi muộn của nó không có chỗ đi nữa, và nếu nó kịp chạy thì hàng rào chủ lease từ chối. Drain thật trên gói free ≈ 5 s (R2-5): không kịp `release` thì lease hết hạn và mất một lượt thử.

**Handler** — `handler(job, ctx)`; trả về bình thường là thành công. Ném `JobFailure(code, retry_after_s)` là thất bại có mã (429 của provider mang `retry_after_s`); ngoại lệ khác là `HANDLER_CRASHED` — **chỉ mã**, không bao giờ thông điệp
của ngoại lệ (có thể mang giá trị slot). Handler dài phải kiểm `ctx.cancelled` định kỳ.
"""
from __future__ import annotations

import os
import socket
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from bo19.config import working_values as wv
from bo19.observability.log import get_logger
from bo19.persistence.pool import Pool
from bo19.tool_layer import jobs

log = get_logger("bo19.queue_worker")
CRASHED = "HANDLER_CRASHED"


class JobFailure(Exception):
    """Thất bại có mã của một lượt thử. `retry_after_s` — của 429 (mục Retry của 11-ops.md)."""

    def __init__(self, code: str, retry_after_s: int | None = None) -> None:
        super().__init__(code)
        self.code, self.retry_after_s = code, retry_after_s


@dataclass
class JobContext:
    """Thứ handler được biết ngoài `ClaimedJob`: cờ huỷ — đặt khi mất lease hoặc khi drain quá hạn."""

    cancel: threading.Event = field(default_factory=threading.Event)

    @property
    def cancelled(self) -> bool:
        return self.cancel.is_set()


Handler = Callable[[jobs.ClaimedJob, JobContext], None]


def new_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"


class Dispatcher:
    def __init__(self, pool: Pool, handlers: Mapping[str, Handler], *, worker_id: str | None = None, poll_s: float = wv.JOB_POLL_S, lease_s: float = wv.JOB_LEASE_S,
                 heartbeat_s: float = wv.JOB_HEARTBEAT_S, drain_s: float = 25.0) -> None:
        self.pool, self.handlers = pool, dict(handlers)
        self.worker_id = worker_id or new_worker_id()
        self.poll_s, self.lease_s, self.heartbeat_s, self.drain_s = poll_s, lease_s, heartbeat_s, drain_s
        self._stop = threading.Event()
        self._drain_deadline: float | None = None

    # ---- điều khiển -----------------------------------------------------------------------------------------------------------

    def stop(self) -> None:
        """Gọi được từ bộ xử lý tín hiệu: chỉ đặt cờ và mốc drain."""
        if self._drain_deadline is None:
            self._drain_deadline = time.monotonic() + self.drain_s
        self._stop.set()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    # ---- vòng poll -------------------------------------------------------------------------------------------------------------

    def run_forever(self) -> None:
        log.info("WORKER_LOOP_START", worker_id=self.worker_id, job_types=",".join(sorted(self.handlers)) or None)
        while not self.stopping:
            if not self.run_once():
                self._stop.wait(self.poll_s)
        log.info("WORKER_LOOP_STOP", worker_id=self.worker_id)

    def run_once(self) -> bool:
        """Một vòng: thu hồi lease hết hạn, giành một job, chạy nó tới khi xong. `True` nếu đã xử lý một job."""
        for r in jobs.reclaim_expired(self.pool):
            log.warning("JOB_LEASE_RECLAIMED", job_id=str(r.id), job_type=r.job_type, status=r.status)
        if self.stopping:
            return False  # đang drain: không giành job mới
        job = jobs.claim(self.pool, worker_id=self.worker_id, job_types=self.handlers.keys(), lease_s=self.lease_s)
        if job is None:
            return False
        self._execute(job)
        return True

    def _execute(self, job: jobs.ClaimedJob) -> None:
        ctx = JobContext()
        outcome: dict[str, BaseException | None] = {}
        done = threading.Event()
        log.info("JOB_START", job_id=str(job.id), job_type=job.job_type, attempt=job.attempts)

        def work() -> None:
            try:
                self.handlers[job.job_type](job, ctx)
                outcome["error"] = None
            except BaseException as e:  # noqa: BLE001 — mọi ngoại lệ của handler thành một lượt thử hỏng; chỉ lưu kiểu, không thông điệp
                outcome["error"] = e
            finally:
                done.set()

        beat_stop = threading.Event()

        def beat() -> None:
            while not beat_stop.wait(self.heartbeat_s):
                if not jobs.heartbeat(self.pool, job, lease_s=self.lease_s):
                    ctx.cancel.set()  # mất lease: handler phải dừng; lệnh ghi muộn của nó bị hàng rào từ chối
                    log.error("JOB_LEASE_LOST", job_id=str(job.id), job_type=job.job_type)
                    return

        worker = threading.Thread(target=work, name=f"job-{job.id}", daemon=True)
        heart = threading.Thread(target=beat, name=f"beat-{job.id}", daemon=True)
        worker.start()
        heart.start()
        try:
            while not done.wait(0.05):
                if self._drain_deadline is not None and time.monotonic() >= self._drain_deadline:
                    ctx.cancel.set()
                    beat_stop.set()
                    released = jobs.release(self.pool, job)  # không tiêu lượt thử
                    log.warning("JOB_RELEASED_ON_DRAIN", job_id=str(job.id), job_type=job.job_type, released=released)
                    return
        finally:
            beat_stop.set()
        error = outcome.get("error")
        if error is None:
            ok = jobs.succeed(self.pool, job)
            log.info("JOB_SUCCEEDED", job_id=str(job.id), job_type=job.job_type, recorded=ok)
        elif isinstance(error, JobFailure):
            result = jobs.fail(self.pool, job, error.code, retry_after_s=error.retry_after_s)
            log.warning("JOB_FAILED_ATTEMPT", job_id=str(job.id), job_type=job.job_type, code=error.code, status=result.status if result else None)
        else:
            result = jobs.fail(self.pool, job, CRASHED)
            log.error("JOB_HANDLER_CRASHED", job_id=str(job.id), job_type=job.job_type, exc=error, status=result.status if result else None)
