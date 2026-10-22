"""Quan sát bộ nhớ của cgroup khi worker đang chạy một job (A-095, bước 4b của runbook Render; PO 2026-10-22, chỉ quan sát).

Lý do: gói Free của Render **không có biểu đồ Memory/CPU** (chỉ Network) nên không đọc được đỉnh bộ nhớ từ dashboard; tiến trình tự nói ra qua log. Nguồn file cgroup:
`docs/reference/linux-cgroup-bo-nho-do-trong-container.md` (tài liệu kernel, URL + sha256). Không đổi hành vi, không biến môi trường mới, không phải bước kiểm khởi động.

**Khi nào ghi:** CHỈ trong lúc một job chạy — một dòng `MEM_INFO` mỗi 5 s, và một dòng `MEM_JOB_DONE` khi job xong (đỉnh trong job). Rảnh thì không ghi gì.
`MEM_INFO`: `job_id`, `job_type`, `elapsed_s`, `current_mib`, `peak_mib` (đỉnh của cgroup từ lúc nó được tạo — `memory.peak`), `job_max_mib` (đỉnh lấy mẫu mỗi 1 s trong job — có thể bỏ sót đỉnh ngắn hơn 1 s),
`limit_mib`, `oom_kill` (bộ đếm tích luỹ của cgroup). `MEM_JOB_DONE`: thêm `job_oom_kill` (số `oom_kill` tăng thêm trong job) và `duration_s`.

Đọc cgroup v2 nếu có `memory.current`, ngược lại v1 (`memory/…`). Trường không đọc được là `null` — không bịa số. **Không bao giờ ném** và không chặn job: mọi lỗi nuốt thành `null`; luồng quan sát là daemon.
Không ghi vào `memory.peak` (ghi sẽ đặt lại đỉnh). Chỉ có số và id trong log.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bo19.observability.log import get_logger

log = get_logger("bo19.mem_info")
CGROUP_ROOT = "/sys/fs/cgroup"
LOG_INTERVAL_S = 5.0
SAMPLE_INTERVAL_S = 1.0
_MIB = 1024 * 1024
_NO_LIMIT = 1 << 60  # v1: không giới hạn đọc ra một số rất lớn


@dataclass(frozen=True)
class Reading:
    current: int | None = None
    peak: int | None = None
    limit: int | None = None
    oom_kill: int | None = None


def _int(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
        return int(text) if text.isdigit() else None  # "max" (v2, không giới hạn) → None
    except (OSError, ValueError):
        return None


def _flat_key(path: Path, key: str) -> int | None:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition(" ")
            if name == key and value.strip().isdigit():
                return int(value.strip())
    except (OSError, ValueError):
        pass
    return None


class CgroupReader:
    def __init__(self, root: str = CGROUP_ROOT) -> None:
        self.root = Path(root)

    def read(self) -> Reading:
        try:
            if (self.root / "memory.current").exists():  # cgroup v2
                return Reading(_int(self.root / "memory.current"), _int(self.root / "memory.peak"), _int(self.root / "memory.max"), _flat_key(self.root / "memory.events", "oom_kill"))
            v1 = self.root / "memory"
            if (v1 / "memory.usage_in_bytes").exists():  # cgroup v1
                limit = _int(v1 / "memory.limit_in_bytes")
                return Reading(_int(v1 / "memory.usage_in_bytes"), _int(v1 / "memory.max_usage_in_bytes"), None if limit is None or limit >= _NO_LIMIT else limit,
                               _flat_key(v1 / "memory.oom_control", "oom_kill"))
        except Exception:  # noqa: BLE001 — quan sát không bao giờ làm hỏng job
            pass
        return Reading()


def _mib(value: int | None) -> float | None:
    return None if value is None else round(value / _MIB, 1)


class JobMemWatch:
    """Một luồng daemon sống đúng thời gian của một job: lấy mẫu mỗi `sample_s`, ghi `MEM_INFO` mỗi `log_s`, và `MEM_JOB_DONE` ở `stop()`."""

    def __init__(self, job_id: str, job_type: str, *, reader: CgroupReader | None = None, log_s: float = LOG_INTERVAL_S, sample_s: float = SAMPLE_INTERVAL_S,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.job_id, self.job_type = job_id, job_type
        self.reader, self.log_s, self.sample_s, self.clock = reader or CgroupReader(), log_s, sample_s, clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._t0 = 0.0
        self._max: int | None = None
        self._oom0: int | None = None

    def start(self) -> None:
        try:
            self._t0 = self.clock()
            first = self.reader.read()
            self._oom0 = first.oom_kill
            self._max = first.current
            self._thread = threading.Thread(target=self._run, name=f"mem-{self.job_id}", daemon=True)
            self._thread.start()
        except Exception:  # noqa: BLE001
            self._thread = None

    def _sample(self) -> Reading:
        r = self.reader.read()
        if r.current is not None and (self._max is None or r.current > self._max):
            self._max = r.current
        return r

    def _run(self) -> None:
        last_log = self.clock()
        try:
            while not self._stop.wait(self.sample_s):
                r = self._sample()
                now = self.clock()
                if now - last_log >= self.log_s:
                    last_log = now
                    log.info("MEM_INFO", job_id=self.job_id, job_type=self.job_type, elapsed_s=round(now - self._t0, 1), current_mib=_mib(r.current), peak_mib=_mib(r.peak),
                             job_max_mib=_mib(self._max), limit_mib=_mib(r.limit), oom_kill=r.oom_kill)
        except Exception:  # noqa: BLE001
            return

    def stop(self) -> None:
        try:
            self._stop.set()
            if self._thread is not None:
                self._thread.join(timeout=2.0)
            r = self._sample()
            delta = None if r.oom_kill is None or self._oom0 is None else r.oom_kill - self._oom0
            log.info("MEM_JOB_DONE", job_id=self.job_id, job_type=self.job_type, duration_s=round(self.clock() - self._t0, 1), current_mib=_mib(r.current), peak_mib=_mib(r.peak),
                     job_max_mib=_mib(self._max), limit_mib=_mib(r.limit), oom_kill=r.oom_kill, job_oom_kill=delta)
        except Exception:  # noqa: BLE001
            return
