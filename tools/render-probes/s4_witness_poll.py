#!/usr/bin/env python3
"""S4 của Spike 1 (A-031) — poll pg_stat_activity để đọc kết nối nhân chứng của api_main, độc lập với đường log.

api_main (khối SPIKE S4) mở lúc khởi động một kết nối PostgreSQL có application_name = 's4 boot=<boot_utc> n=0' và, trong vòng giữ sau
SIGTERM, đặt n=<k> mỗi giây. Script này, chạy từ MÁY NGƯỜI TRIỂN KHAI, hỏi pg_stat_activity mỗi 0.25 s và ghi mỗi lần hỏi một dòng JSON.
Số đo là hai số, báo riêng: (a) n cuối đọc được; (b) lúc kết nối biến mất.

Cách dùng (credential `bo19_app` CHỈ qua biến môi trường, không bao giờ trên dòng lệnh, không in):
  BO19_S4_POLL_DSN=...  python s4_witness_poll.py --duration 900 > poll.jsonl
  python s4_witness_poll.py --analyze poll.jsonl [--sigterm 2026-10-05T06:57:36.634]

Mỗi dòng: {"t": giờ máy lúc hỏi, "rtt": thời gian một lần hỏi, "rows": [{"pid","app","state"}...]} hoặc {"t","error": tên lớp lỗi}. Không ghi
client_addr, DSN hay thông điệp lỗi (có thể mang host). Chỉ dòng có application_name LIKE 's4 boot=%'.

Không phải phần mềm — thuộc S4; gỡ cùng khối SPIKE S4 khi S4 xong, hoặc giữ làm công cụ đo ở Sprint 4 (A-086) nếu PO quyết.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

APP_RE = re.compile(r"^s4 boot=(\S+) n=(\d+)$")


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def poll(duration: float, interval: float, like: str) -> int:
    import psycopg

    dsn = os.environ.get("BO19_S4_POLL_DSN", "")
    if not dsn:
        print("THIẾU BO19_S4_POLL_DSN", file=sys.stderr)
        return 2
    conn = None
    t_end = time.perf_counter() + duration
    next_tick = time.perf_counter()
    while time.perf_counter() < t_end:
        t = utc()
        m0 = time.perf_counter()
        try:
            if conn is None:
                conn = psycopg.connect(dsn, autocommit=True, connect_timeout=5, application_name="s4-poller")
            rows = conn.execute("SELECT pid, application_name, state FROM pg_stat_activity WHERE application_name LIKE %s ORDER BY application_name", (like,)).fetchall()
            rec = {"t": t, "rtt": round(time.perf_counter() - m0, 4), "rows": [{"pid": r[0], "app": r[1], "state": r[2]} for r in rows]}
        except Exception as e:  # noqa: BLE001 — chỉ tên lớp lỗi
            rec = {"t": t, "error": type(e).__name__}
            conn = None
        print(json.dumps(rec, separators=(",", ":")), flush=True)
        next_tick += interval
        time.sleep(max(0.0, next_tick - time.perf_counter()))
    return 0


def ts(s: str) -> float:
    return datetime.fromisoformat(s).timestamp()


def summarize_polls(polls: list[dict]) -> tuple[dict[str, dict], list[tuple[str, float]]]:
    """Với mỗi boot: lúc thấy đầu, n cuối đọc được và lúc đổi n cuối, lúc kết nối biến mất (lần hỏi đầu tiên không còn dòng sau khi đã thấy)."""
    boots: dict[str, dict] = {}
    gaps = []
    prev_t = None
    for p in polls:
        t = ts(p["t"])
        if prev_t is not None and t - prev_t > 1.0:
            gaps.append((p["t"], round(t - prev_t, 3)))
        prev_t = t
        if "error" in p:
            continue
        seen = {}
        for r in p["rows"]:
            m = APP_RE.match(r["app"])
            if not m:
                continue
            boot, n = m.group(1), int(m.group(2))
            seen[boot] = (n, r["state"], r["pid"])
        for boot, (n, state, pid) in seen.items():
            b = boots.setdefault(boot, {"first": t, "n_by_first_seen": {}, "last_seen": t, "n_last": n, "t_n_last": t, "states": set(), "pid": pid, "gone": None})
            b["last_seen"], b["gone"] = t, None
            b["states"].add(state)
            if n != b["n_last"]:
                b["n_last"], b["t_n_last"] = n, t
            b["n_by_first_seen"].setdefault(n, t)
        for boot, b in boots.items():
            if boot not in seen and b["gone"] is None:
                b["gone"] = t  # lần hỏi đầu tiên không còn dòng
    return boots, gaps


def analyze(path: str, sigterm: str | None) -> int:
    polls = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    boots, gaps = summarize_polls(polls)
    print(f"số lần hỏi: {len(polls)}; lỗi: {sum('error' in p for p in polls)}; khoảng cách giữa hai lần hỏi > 1 s: {gaps or 'không'}")
    t_sig = ts(sigterm) if sigterm else None
    for boot, b in sorted(boots.items(), key=lambda kv: kv[1]["first"]):
        print(f"\nboot={boot} pid={b['pid']}")
        print(f"  thấy đầu tiên lúc {datetime.fromtimestamp(b['first'], timezone.utc).isoformat(timespec='milliseconds')}; trạng thái đã thấy: {sorted(b['states'])}")
        print(f"  (a) n cuối đọc được = {b['n_last']}, lần đổi n cuối thấy lúc {datetime.fromtimestamp(b['t_n_last'], timezone.utc).isoformat(timespec='milliseconds')}")
        if b["gone"] is None:
            print(f"  (b) kết nối CÒN ở lần hỏi cuối ({datetime.fromtimestamp(b['last_seen'], timezone.utc).isoformat(timespec='milliseconds')}) — chưa biến mất")
        else:
            print(f"  (b) kết nối biến mất lúc {datetime.fromtimestamp(b['gone'], timezone.utc).isoformat(timespec='milliseconds')} (lần thấy cuối {datetime.fromtimestamp(b['last_seen'], timezone.utc).isoformat(timespec='milliseconds')}); sau lần đổi n cuối {b['gone'] - b['t_n_last']:.3f} s")
        if 1 in b["n_by_first_seen"]:
            t1 = b["n_by_first_seen"][1]
            print(f"  mốc tương đối (không phụ thuộc lệch đồng hồ giữa máy và instance): n=1 thấy lúc T1; n cuối thấy sau T1 {b['t_n_last'] - t1:.3f} s" + (f"; biến mất sau T1 {b['gone'] - t1:.3f} s" if b["gone"] else ""))
        if t_sig is not None and b["n_by_first_seen"]:
            print(f"  so với SIGTERM_RECEIVED trong log: n cuối thấy sau SIGTERM {b['t_n_last'] - t_sig:.3f} s" + (f"; biến mất sau SIGTERM {b['gone'] - t_sig:.3f} s" if b["gone"] else "") + "  (cộng sai số đồng hồ hai máy)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="S4 của Spike 1 — đọc kết nối nhân chứng qua pg_stat_activity")
    ap.add_argument("--duration", type=float, default=900.0)
    ap.add_argument("--interval", type=float, default=0.25)
    ap.add_argument("--like", default="s4 boot=%")
    ap.add_argument("--analyze", metavar="FILE")
    ap.add_argument("--sigterm", help="giờ SIGTERM_RECEIVED trong log (ISO UTC), để in mốc so với SIGTERM")
    a = ap.parse_args()
    if a.analyze:
        return analyze(a.analyze, a.sigterm)
    return poll(a.duration, a.interval, a.like)


if __name__ == "__main__":
    sys.exit(main())
