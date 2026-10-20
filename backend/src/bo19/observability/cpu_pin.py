"""Ghim tiến trình vào MỘT CPU khi hạn mức CPU của cgroup nhỏ hơn một CPU (B9a2; PO 2026-10-20; WV-34).

Lý do (đo ở B9a2, `docs/reference/combined-main-b9a2.md`, mục Hạ ưu tiên): trong cgroup `--cpus=0.1` mà máy thấy nhiều CPU, `api` và `soffice` nằm ở hai CPU khác nhau nên không tranh nhau — trọng số `nice` của `soffice` không có chỗ tác dụng
(trung vị lượt chat khi `soffice` chạy 11,7 → 11,8 s). Ghim cả tiến trình (con thừa hưởng, kể cả `soffice`) vào một CPU thì chung một runqueue và `nice` 19 mới thắng (lớn nhất 21,1 → 9,9 s ở thử nghiệm `--cpuset-cpus`).

Chỉ ghim khi `cpu.max` (cgroup v2; v1: `cpu.cfs_quota_us` / `cpu.cfs_period_us`) cho hạn mức < `wv.PIN_CPU_WHEN_QUOTA_BELOW` CPU, và tập affinity hiện có có hơn một CPU. Chọn CPU **đầu tiên** của tập affinity hiện có.
Phải gọi **trước khi tạo luồng nào** (`sched_setaffinity(0, …)` đặt cho luồng gọi; luồng và tiến trình con tạo sau thừa hưởng) — đầu `main()` của entrypoint, ngay sau khi cài log.
Không bao giờ ném: mọi lỗi thành `CPU_PIN_SKIPPED` kèm lý do. Log chỉ mang số.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from bo19.config import working_values as wv
from bo19.observability.log import get_logger

log = get_logger("bo19.cpu_pin")
CPU_MAX_V2 = "/sys/fs/cgroup/cpu.max"
CFS_QUOTA_V1 = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
CFS_PERIOD_V1 = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"


@dataclass(frozen=True)
class PinResult:
    pinned: bool
    reason: str          # PINNED | NO_LIMIT | NOT_BELOW | SINGLE_CPU | UNSUPPORTED | ERROR
    cpu: int | None = None
    limit: float | None = None
    allowed: int | None = None


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def cgroup_cpu_limit(v2_path: str = CPU_MAX_V2, v1_quota: str = CFS_QUOTA_V1, v1_period: str = CFS_PERIOD_V1) -> float | None:
    """Hạn mức CPU của cgroup theo đơn vị CPU (0,1 = 10 % một lõi); `None` nếu không giới hạn hay không đọc được."""
    v2 = _read(v2_path)
    if v2 is not None:
        parts = v2.split()
        if len(parts) == 2 and parts[0] != "max":
            try:
                quota, period = int(parts[0]), int(parts[1])
            except ValueError:
                return None
            return quota / period if quota > 0 and period > 0 else None
        return None
    quota_s, period_s = _read(v1_quota), _read(v1_period)
    if quota_s is None or period_s is None:
        return None
    try:
        quota, period = int(quota_s), int(period_s)
    except ValueError:
        return None
    return quota / period if quota > 0 and period > 0 else None  # v1: quota -1 = không giới hạn


def pin_if_limited(*, below: float = wv.PIN_CPU_WHEN_QUOTA_BELOW, v2_path: str = CPU_MAX_V2, v1_quota: str = CFS_QUOTA_V1, v1_period: str = CFS_PERIOD_V1,
                   getaffinity: Callable[[int], set[int]] | None = None, setaffinity: Callable[[int, set[int]], None] | None = None) -> PinResult:
    getaffinity = getaffinity or getattr(os, "sched_getaffinity", None)
    setaffinity = setaffinity or getattr(os, "sched_setaffinity", None)
    if getaffinity is None or setaffinity is None:
        return _done(PinResult(False, "UNSUPPORTED"))
    limit = cgroup_cpu_limit(v2_path, v1_quota, v1_period)
    if limit is None:
        return _done(PinResult(False, "NO_LIMIT"))
    if limit >= below:
        return _done(PinResult(False, "NOT_BELOW", limit=limit))
    try:
        allowed = sorted(getaffinity(0))
        if len(allowed) <= 1:
            return _done(PinResult(False, "SINGLE_CPU", cpu=allowed[0] if allowed else None, limit=limit, allowed=len(allowed)))
        setaffinity(0, {allowed[0]})
        return _done(PinResult(True, "PINNED", cpu=allowed[0], limit=limit, allowed=len(allowed)))
    except Exception as e:  # noqa: BLE001 — ghim là tối ưu, không phải điều kiện để chạy
        log.warning("CPU_PIN_FAILED", exc=e)
        return _done(PinResult(False, "ERROR", limit=limit))


def _done(r: PinResult) -> PinResult:
    if r.pinned:
        log.info("CPU_PINNED", cpu=r.cpu, cpu_limit=round(r.limit, 3), cpus_allowed_before=r.allowed)
    else:
        log.info("CPU_PIN_SKIPPED", reason=r.reason, cpu_limit=None if r.limit is None else round(r.limit, 3), cpus_allowed=r.allowed)
    return r
