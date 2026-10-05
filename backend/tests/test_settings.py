"""Test cấu hình có kiểu — B2. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_settings -v"""
from __future__ import annotations

import unittest

from bo19.config.settings import ENV_NAMES, ORG_TIMEZONE, Environment, load_settings

GOOD = {"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": "postgresql://u:BI_MAT_DSN@h/db", "BO19_SESSION_SECRET": "BI_MAT_SESSION"}


def env(**over) -> dict:
    d = dict(GOOD)
    for k, v in over.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    return d


class Defaults(unittest.TestCase):
    def test_du_cau_hinh_thi_khong_co_van_de_va_mac_dinh_la_gia_tri_wv(self):
        s = load_settings(GOOD)
        self.assertEqual(s.problems, ())
        self.assertEqual((s.environment, s.port, s.timezone), (Environment.DEV, 10000, ORG_TIMEZONE))
        self.assertEqual((s.shutdown_delay_s, s.turn_deadline_s, s.turn_margin_s), (30, 20, 10))  # WV-01, WV-02, WV-03
        self.assertEqual((s.object_storage_timeout_s, s.stored_object_lease_s), (30, 120))  # WV-08, WV-10
        self.assertEqual((s.argon2_time_cost, s.argon2_memory_cost_kib, s.argon2_parallelism), (2, 19456, 1))  # WV-16

    def test_moi_truong_co_ten_bien(self):
        s = load_settings(GOOD)
        for f in ENV_NAMES:
            self.assertTrue(hasattr(s, f), f)


class Environment16(unittest.TestCase):
    def test_thieu_la_van_de_khong_mac_dinh_thanh_prod(self):
        s = load_settings(env(BO19_ENVIRONMENT=None))
        self.assertIsNone(s.environment)
        self.assertEqual(s.problem("environment"), "CONFIG_ENVIRONMENT_MISSING")

    def test_rong_hoac_khoang_trang_la_thieu(self):
        for v in ("", "   "):
            self.assertEqual(load_settings(env(BO19_ENVIRONMENT=v)).problem("environment"), "CONFIG_ENVIRONMENT_MISSING", repr(v))

    def test_ba_gia_tri_hop_le(self):
        for v, e in (("dev", Environment.DEV), ("staging", Environment.STAGING), ("prod", Environment.PROD)):
            s = load_settings(env(BO19_ENVIRONMENT=v))
            self.assertEqual((s.environment, s.problem("environment")), (e, None))

    def test_gia_tri_la_khong_doan(self):
        for v in ("Dev", "PROD", "production", "development", "test", "prod,dev"):
            s = load_settings(env(BO19_ENVIRONMENT=v))
            self.assertIsNone(s.environment, v)
            self.assertEqual(s.problem("environment"), "CONFIG_ENVIRONMENT_INVALID", v)


class SecretVaDsn(unittest.TestCase):
    def test_thieu_tung_cai(self):
        self.assertEqual(load_settings(env(BO19_DATABASE_URL=None)).problem("database_url"), "CONFIG_DATABASE_URL_MISSING")
        self.assertEqual(load_settings(env(BO19_SESSION_SECRET=None)).problem("session_secret"), "CONFIG_SESSION_SECRET_MISSING")
        self.assertEqual(load_settings(env(BO19_SESSION_SECRET="  ")).problem("session_secret"), "CONFIG_SESSION_SECRET_MISSING")

    def test_repr_va_problems_khong_lo_gia_tri(self):
        s = load_settings(env(BO19_SHUTDOWN_DELAY_SECONDS="BI_MAT_SO"))
        text = repr(s) + repr(s.problems)
        for secret in ("BI_MAT_DSN", "BI_MAT_SESSION", "BI_MAT_SO"):
            self.assertNotIn(secret, text)

    def test_nhieu_van_de_cung_luc_duoc_gom_het(self):
        s = load_settings({})
        self.assertEqual({f for f, _ in s.problems}, {"environment", "database_url", "session_secret"})


class SoNguyenDuong(unittest.TestCase):
    def test_gia_tri_hop_le_duoc_dung(self):
        s = load_settings(env(BO19_SHUTDOWN_DELAY_SECONDS="45", BO19_ARGON2_MEMORY_COST_KIB="65536", PORT="8080"))
        self.assertEqual((s.shutdown_delay_s, s.argon2_memory_cost_kib, s.port), (45, 65536, 8080))

    def test_gia_tri_khong_phai_so_nguyen_duong_la_van_de(self):
        for name, field in (("BO19_SHUTDOWN_DELAY_SECONDS", "shutdown_delay_s"), ("BO19_TURN_DEADLINE_SECONDS", "turn_deadline_s"),
                            ("BO19_ARGON2_TIME_COST", "argon2_time_cost"), ("BO19_STORED_OBJECT_LEASE_SECONDS", "stored_object_lease_s")):
            for bad in ("0", "-1", "1.5", "abc", "1e3", "٣", "1" * 10):  # kể cả chữ số không phải ASCII và số quá dài
                s = load_settings(env(**{name: bad}))
                self.assertIsNone(getattr(s, field), (name, bad))
                self.assertEqual(s.problem(field), f"CONFIG_{name.removeprefix('BO19_')}_INVALID", (name, bad))

    def test_port(self):
        for bad in ("0", "65536", "abc", "-5"):
            self.assertEqual(load_settings(env(PORT=bad)).problem("port"), "CONFIG_PORT_INVALID", bad)
        self.assertEqual(load_settings(env(PORT="65535")).port, 65535)


class MuiGio(unittest.TestCase):
    def test_chi_nhan_gia_tri_a041(self):  # A-041 `Đã chốt`
        self.assertEqual(load_settings(env(BO19_ORG_TIMEZONE="Asia/Ho_Chi_Minh")).problem("timezone"), None)
        for bad in ("UTC", "Asia/Bangkok", "asia/ho_chi_minh", "Asia/Saigon"):
            s = load_settings(env(BO19_ORG_TIMEZONE=bad))
            self.assertEqual(s.problem("timezone"), "CONFIG_ORG_TIMEZONE_INVALID", bad)


if __name__ == "__main__":
    unittest.main()
