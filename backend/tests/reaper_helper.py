"""Tiến trình trợ giúp cho `test_reaper`: đóng vai PID 1 của container bằng `PR_SET_CHILD_SUBREAPER` (Linux) — tiến trình mồ côi của con nó được nhận làm con của chính nó, như PID 1.

Chạy: `python -m tests.reaper_helper` từ backend/. In MỘT dòng JSON ra stdout. Không chạy gì khi bị import.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time

PR_SET_CHILD_SUBREAPER = 36


def main() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        print(json.dumps({"error": "prctl"}))
        return
    from bo19.observability import reaper

    out: dict = {}
    # 1) mồ côi: `sh` sinh một `sleep` chạy nền rồi thoát ngay → `sleep` thành con của ta; hết hạn thì thành zombie
    subprocess.run(["sh", "-c", "sleep 0.3 &"], check=True)
    time.sleep(0.6)
    before = [c for c in reaper.children() if c.state == "Z"]
    r = reaper.Reaper(interval_s=0.05)
    out["zombies_before"] = len(before)
    out["first_sweep_reaped"] = r.sweep()      # lần quét đầu: thấy, chưa dọn (luật hai lần quét)
    out["second_sweep_reaped"] = r.sweep()     # lần hai: dọn
    out["zombies_after"] = len([c for c in reaper.children() if c.state == "Z"])

    # 2) con do mã của ta sinh ra và được bảo vệ: bộ dọn không được cướp mã thoát của nó
    proc = subprocess.Popen(["sh", "-c", "exit 7"])
    time.sleep(0.3)  # đã chết, đang là zombie chờ ta `wait`
    r2 = reaper.Reaper(lambda: {proc.pid})
    r2.sweep()
    r2.sweep()
    r2.sweep(final=True)
    out["protected_exit_code"] = proc.wait()

    # 3) `final=True` dọn ngay không đợi lần quét thứ hai
    subprocess.run(["sh", "-c", "sleep 0.2 &"], check=True)
    time.sleep(0.5)
    r3 = reaper.Reaper()
    out["final_reaped"] = r3.sweep(final=True)
    out["zombies_end"] = len([c for c in reaper.children() if c.state == "Z"])
    print(json.dumps(out))


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    main()
