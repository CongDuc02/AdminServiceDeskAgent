"""Đo bộ nhớ của việc chuyển `.docx` → `.pdf` (B8b; PO 2026-10-13: "đo RSS đỉnh của soffice và của cả tiến trình") — chạy BÊN TRONG container giới hạn bộ nhớ.

Cách dùng (từ thư mục gốc repo, image target `test`):
    docker run --rm --memory=512m --memory-swap=512m --cpus=0.1 -v "$PWD":/repo -w /repo/backend -e PYTHONPATH=src \
        --entrypoint python bo19-test /repo/tools/mem-probe/measure_convert.py [--pages N] [--concurrent K] [--rounds R]

In MỘT dòng JSON ở cuối. Đo:
- `baseline_rss_mib` — RSS của tiến trình Python (worker) sau khi import đúng các module mà worker dùng để render (docx_fill, convert, storage, fonts), trước khi chuyển đổi;
- `peak_total_rss_mib` — đỉnh của TỔNG RSS mọi tiến trình trong container (python + soffice + soffice.bin + …), lấy mẫu 20 ms một lần từ /proc;
- `peak_soffice_rss_mib` — đỉnh RSS của MỘT tiến trình `soffice.bin`;
- `python_peak_rss_mib` — `VmHWM` của tiến trình Python;
- `cgroup_memory_peak_mib`, `cgroup_memory_max_mib`, `oom_kill` — của cgroup (v2): `memory.peak` tính cả page cache nên LỚN HƠN RSS; điều quyết định là `oom_kill` và việc lần chuyển đổi có xong;
- `seconds` mỗi lần chuyển đổi, và `ok`/`error` mỗi lần.

Không có dữ liệu thật: văn bản giả, tiếng Việt đủ dấu, `--pages` đoạn dài để ép nhiều trang.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from pathlib import Path


def rss_kib(pid: str) -> tuple[str, int] | None:
    try:
        text = Path(f"/proc/{pid}/status").read_text()
    except OSError:
        return None
    name, rss = "", 0
    for line in text.splitlines():
        if line.startswith("Name:"):
            name = line.split()[1]
        elif line.startswith("VmRSS:"):
            rss = int(line.split()[1])
    return name, rss


class Sampler(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.peak_total = 0
        self.peak_by_name: dict[str, int] = {}

    def run(self) -> None:
        while not self.stop.is_set():
            total = 0
            for pid in os.listdir("/proc"):
                if not pid.isdigit():
                    continue
                got = rss_kib(pid)
                if got is None:
                    continue
                name, rss = got
                total += rss
                if rss > self.peak_by_name.get(name, 0):
                    self.peak_by_name[name] = rss
            self.peak_total = max(self.peak_total, total)
            time.sleep(0.02)


def cgroup(name: str) -> str | None:
    for base in ("/sys/fs/cgroup", "/sys/fs/cgroup/memory"):
        try:
            return Path(base, name).read_text().strip()
        except OSError:
            continue
    return None


def oom_kills() -> int | None:
    text = cgroup("memory.events")
    if text is None:
        return None
    return next((int(line.split()[1]) for line in text.splitlines() if line.startswith("oom_kill ")), 0)


def mib(kib: int) -> float:
    return round(kib / 1024, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=1, help="số đoạn dài ghép thêm vào văn bản để ép nhiều trang")
    ap.add_argument("--concurrent", type=int, default=1)
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()

    from bo19.tool_layer.rendering import convert, docx_fill, fonts  # noqa: F401 — đúng các module worker dùng để render
    from bo19.tool_layer import storage  # noqa: F401
    from tests.render_support import DECLARED, VALUES, VIETNAMESE, build_template

    values = {**VALUES, "noi_dung": "\n".join([VIETNAMESE * 6] * args.pages)}
    docx = docx_fill.fill_docx(build_template(), values, declared=DECLARED, operating_mode="NON_PRODUCTION")
    baseline = rss_kib(str(os.getpid()))[1]
    oom_before = oom_kills()
    sampler = Sampler()
    sampler.start()
    runs: list[dict] = []
    lock = threading.Lock()

    def one() -> None:
        t = time.monotonic()
        try:
            pdf = convert.convert_to_pdf(docx, timeout_s=900)
            result = {"ok": True, "pdf_bytes": len(pdf)}
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "error": getattr(e, "code", type(e).__name__)}
        result["seconds"] = round(time.monotonic() - t, 1)
        with lock:
            runs.append(result)

    for _ in range(args.rounds):
        threads = [threading.Thread(target=one) for _ in range(args.concurrent)]
        [t.start() for t in threads]
        [t.join() for t in threads]
    sampler.stop.set()
    sampler.join()
    hwm = next((int(line.split()[1]) for line in Path("/proc/self/status").read_text().splitlines() if line.startswith("VmHWM:")), 0)
    peak = cgroup("memory.peak")
    limit = cgroup("memory.max")
    print(json.dumps({
        "docx_bytes": len(docx), "pages_arg": args.pages, "concurrent": args.concurrent, "rounds": args.rounds,
        "baseline_rss_mib": mib(baseline), "python_peak_rss_mib": mib(hwm), "peak_total_rss_mib": mib(sampler.peak_total),
        "peak_soffice_rss_mib": mib(sampler.peak_by_name.get("soffice.bin", 0)), "peak_by_process_mib": {k: mib(v) for k, v in sorted(sampler.peak_by_name.items(), key=lambda kv: -kv[1])[:5]},
        "cgroup_memory_peak_mib": round(int(peak) / 1048576, 1) if peak and peak.isdigit() else peak,
        "cgroup_memory_max_mib": round(int(limit) / 1048576, 1) if limit and limit.isdigit() else limit,
        "oom_kill": None if oom_before is None else oom_kills() - oom_before, "runs": runs}, ensure_ascii=False))


if __name__ == "__main__":
    main()
