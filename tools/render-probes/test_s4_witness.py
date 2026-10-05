"""Test bộ phân tích của s4_witness_poll.py — ba kịch bản đã khai báo trước trong docs/reference/render-s4-nhat-ky-do.md, mục 5.

Chạy từ thư mục gốc repo:  python -m unittest discover -s tools/render-probes -p "test_s4_witness.py" -v
Chỉ thư viện chuẩn (không cần psycopg: chỉ hàm phân tích được nạp).
"""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# psycopg chỉ được import trong poll(); phân tích không cần.
sys.modules.setdefault("psycopg", types.ModuleType("psycopg"))
spec = importlib.util.spec_from_file_location("s4poll", Path(__file__).with_name("s4_witness_poll.py"))
s4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s4)

T0 = datetime(2026, 10, 5, 7, 0, 0, tzinfo=timezone.utc)
BOOT = "2026-10-05T06:57:28.483"


def iso(sec: float) -> str:
    return (T0 + timedelta(seconds=sec)).isoformat(timespec="milliseconds")


def row(n: int, state: str = "idle") -> dict:
    return {"pid": 4242, "app": f"s4 boot={BOOT} n={n}", "state": state}


def polls(n_at: dict[float, int], gone_at: float | None, end: float, step: float = 0.25) -> list[dict]:
    """Một lần hỏi mỗi `step` giây; n đổi theo n_at (giây → n); kết nối biến mất từ gone_at (None = còn tới hết)."""
    out, t, n = [], 0.0, 0
    while t <= end:
        n = max([v for k, v in n_at.items() if k <= t] or [0])
        out.append({"t": iso(t), "rtt": 0.05, "rows": [] if gone_at is not None and t >= gone_at else [row(n)]})
        t = round(t + step, 3)
    return out


class Kich(unittest.TestCase):
    def test_kill_5s_n_dung_o_5_va_ket_noi_bien_mat_ngay(self):
        n_at = {0.0: 0, **{k + 0.17: k for k in range(1, 6)}}  # n=1 ở 0.17 s ... n=5 ở 5.17 s
        boots, gaps = s4.summarize_polls(polls(n_at, gone_at=5.75, end=12))
        b = boots[BOOT]
        self.assertEqual(b["n_last"], 5)
        self.assertAlmostEqual(b["gone"] - b["t_n_last"], 0.5, delta=0.3)  # biến mất ≤ 2 s sau lần đổi n cuối
        self.assertEqual(gaps, [])

    def test_log_bi_cat_n_tiep_tuc_tang_toi_30(self):
        n_at = {0.0: 0, **{k + 0.17: k for k in range(1, 31)}}
        boots, _ = s4.summarize_polls(polls(n_at, gone_at=30.75, end=35))
        b = boots[BOOT]
        self.assertEqual(b["n_last"], 30)
        self.assertGreaterEqual(b["n_last"], 25)

    def test_treo_n_dung_o_5_ma_ket_noi_van_con(self):
        n_at = {0.0: 0, **{k + 0.17: k for k in range(1, 6)}}
        boots, _ = s4.summarize_polls(polls(n_at, gone_at=None, end=40))
        b = boots[BOOT]
        self.assertEqual(b["n_last"], 5)
        self.assertIsNone(b["gone"])  # còn ở lần hỏi cuối — thời gian treo = lần hỏi cuối − lần đổi n cuối
        self.assertGreater(b["last_seen"] - b["t_n_last"], 30)

    def test_treo_roi_bien_mat_do_thoi_gian_treo(self):
        n_at = {0.0: 0, **{k + 0.17: k for k in range(1, 6)}}
        boots, _ = s4.summarize_polls(polls(n_at, gone_at=25.0, end=30))
        b = boots[BOOT]
        self.assertAlmostEqual(b["gone"] - b["t_n_last"], 25.0 - 5.25, delta=0.3)

    def test_loi_va_khoang_trong_khong_bi_nham_voi_ket_noi_bien_mat(self):
        ps = polls({0.0: 0, 1.0: 1}, gone_at=None, end=10)
        # lần hỏi 4.0–6.0 s bị lỗi (poller mất kết nối): không phải "biến mất"
        ps = [({"t": p["t"], "error": "OperationalError"} if 4.0 <= (datetime.fromisoformat(p["t"]) - T0).total_seconds() <= 6.0 else p) for p in ps]
        boots, gaps = s4.summarize_polls(ps)
        self.assertIsNone(boots[BOOT]["gone"])
        self.assertEqual(gaps, [])  # lỗi vẫn có dòng mỗi 0.25 s nên không có khoảng cách > 1 s

    def test_khoang_cach_giua_hai_lan_hoi_lon_hon_1s_duoc_bao(self):
        ps = polls({0.0: 0}, gone_at=None, end=2)
        ps.append({"t": iso(5.0), "rtt": 0.05, "rows": [row(0)]})
        _, gaps = s4.summarize_polls(ps)
        self.assertEqual(len(gaps), 1)
        self.assertAlmostEqual(gaps[0][1], 3.0, delta=0.01)

    def test_ten_ung_dung_khac_bi_bo_qua(self):
        ps = [{"t": iso(0), "rtt": 0.05, "rows": [{"pid": 1, "app": "s4-poller", "state": "active"}, row(3)]}]
        boots, _ = s4.summarize_polls(ps)
        self.assertEqual(list(boots), [BOOT])


if __name__ == "__main__":
    unittest.main()
