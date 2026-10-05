"""Test bước kiểm khởi động #11 và #13 — B2. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_checks_config -v"""
from __future__ import annotations

import unittest
from pathlib import Path

from bo19.config.settings import load_settings
from bo19.startup.checks_config import step_11, step_13
from bo19.startup.model import Context, Entry

BASE = {"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": "x", "BO19_SESSION_SECRET": "y" * 32}


def run(step, entry: Entry, **env):
    return step(Context(entry, load_settings({**BASE, **env}), {}, None, Path("."))).codes


class Buoc11Api(unittest.TestCase):
    """api: hạn chót lượt + biên ≤ shutdown delay (WV-02 + WV-03 ≤ WV-01)."""

    def test_mac_dinh_dat_20_cong_10_bang_30(self):
        self.assertEqual(run(step_11, Entry.API), ())

    def test_vuot_la_chan(self):
        self.assertEqual(run(step_11, Entry.API, BO19_TURN_DEADLINE_SECONDS="21"), ("STARTUP_11_TURN_DEADLINE_EXCEEDS_SHUTDOWN_DELAY",))
        self.assertEqual(run(step_11, Entry.API, BO19_SHUTDOWN_DELAY_SECONDS="29"), ("STARTUP_11_TURN_DEADLINE_EXCEEDS_SHUTDOWN_DELAY",))
        self.assertEqual(run(step_11, Entry.API, BO19_TURN_DEADLINE_MARGIN_SECONDS="11"), ("STARTUP_11_TURN_DEADLINE_EXCEEDS_SHUTDOWN_DELAY",))

    def test_bang_nhau_la_dat(self):  # "không dài hơn" — bằng là được
        self.assertEqual(run(step_11, Entry.API, BO19_TURN_DEADLINE_SECONDS="25", BO19_TURN_DEADLINE_MARGIN_SECONDS="5"), ())

    def test_gia_tri_khong_hop_le_la_ma_rieng_va_khong_so_sanh(self):
        self.assertEqual(run(step_11, Entry.API, BO19_TURN_DEADLINE_SECONDS="abc"), ("STARTUP_11_TURN_DEADLINE_SECONDS_INVALID",))
        got = run(step_11, Entry.API, BO19_SHUTDOWN_DELAY_SECONDS="0", BO19_TURN_DEADLINE_MARGIN_SECONDS="-1")
        self.assertEqual(got, ("STARTUP_11_SHUTDOWN_DELAY_SECONDS_INVALID", "STARTUP_11_TURN_DEADLINE_MARGIN_SECONDS_INVALID"))

    def test_chi_so_sanh_gia_tri_cau_hinh_khong_do_render(self):
        """S4 đo shutdown delay thực ≈ 5 s trên gói free; bước kiểm vẫn đạt — nó chỉ so cấu hình (PO, 2026-10-05)."""
        self.assertEqual(run(step_11, Entry.API), ())

    def test_bien_cua_worker_khong_anh_huong_api(self):
        self.assertEqual(run(step_11, Entry.API, BO19_STORED_OBJECT_LEASE_SECONDS="1"), ())


class Buoc11Worker(unittest.TestCase):
    """worker: lease của stored_object dài hơn hẳn timeout chạm object_storage (WV-10 > WV-08)."""

    def test_mac_dinh_dat_120_lon_hon_30(self):
        self.assertEqual(run(step_11, Entry.WORKER), ())

    def test_bang_hoac_nho_hon_la_chan(self):
        self.assertEqual(run(step_11, Entry.WORKER, BO19_STORED_OBJECT_LEASE_SECONDS="30"), ("STARTUP_11_LEASE_NOT_ABOVE_STORAGE_TIMEOUT",))
        self.assertEqual(run(step_11, Entry.WORKER, BO19_STORED_OBJECT_LEASE_SECONDS="29"), ("STARTUP_11_LEASE_NOT_ABOVE_STORAGE_TIMEOUT",))
        self.assertEqual(run(step_11, Entry.WORKER, BO19_OBJECT_STORAGE_TIMEOUT_SECONDS="120"), ("STARTUP_11_LEASE_NOT_ABOVE_STORAGE_TIMEOUT",))
        self.assertEqual(run(step_11, Entry.WORKER, BO19_STORED_OBJECT_LEASE_SECONDS="31"), ())

    def test_khong_hop_le(self):
        self.assertEqual(run(step_11, Entry.WORKER, BO19_STORED_OBJECT_LEASE_SECONDS="x"), ("STARTUP_11_STORED_OBJECT_LEASE_SECONDS_INVALID",))

    def test_bien_cua_api_khong_anh_huong_worker(self):
        self.assertEqual(run(step_11, Entry.WORKER, BO19_TURN_DEADLINE_SECONDS="999"), ())


class Buoc11Combined(unittest.TestCase):
    def test_combined_kiem_ca_hai_ve(self):
        got = run(step_11, Entry.COMBINED, BO19_TURN_DEADLINE_SECONDS="99", BO19_STORED_OBJECT_LEASE_SECONDS="1")
        self.assertEqual(got, ("STARTUP_11_TURN_DEADLINE_EXCEEDS_SHUTDOWN_DELAY", "STARTUP_11_LEASE_NOT_ABOVE_STORAGE_TIMEOUT"))


class Buoc13(unittest.TestCase):
    def test_mac_dinh_la_a041_va_dat(self):
        for entry in (Entry.API, Entry.WORKER, Entry.CRON):
            self.assertEqual(run(step_13, entry), (), entry)

    def test_gia_tri_a041_dat(self):
        self.assertEqual(run(step_13, Entry.API, BO19_ORG_TIMEZONE="Asia/Ho_Chi_Minh"), ())

    def test_gia_tri_khac_la_chan_vi_issued_date_va_ky_danh_so_phu_thuoc(self):
        for bad in ("UTC", "Asia/Bangkok", "Europe/Paris", "asia/ho_chi_minh"):
            self.assertEqual(run(step_13, Entry.API, BO19_ORG_TIMEZONE=bad), ("STARTUP_13_ORG_TIMEZONE_INVALID",), bad)


if __name__ == "__main__":
    unittest.main()
