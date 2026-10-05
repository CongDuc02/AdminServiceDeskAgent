"""Hasher `argon2id` — `bo19.api.auth.hasher` (ADR-021, ADR-034): mọi ca đều chạy đúng một lần verify, và trần verify đồng thời (WV-16b).

Tham số rẻ (`time_cost=1`, `memory_cost=8` KiB) — test tự dựng `PasswordVerifier` riêng, không hạ cấu hình của ứng dụng (bước kiểm khởi động #20).
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_password_verifier -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import threading
import time
import unittest
from unittest import mock

import argon2

from bo19.api.auth.hasher import ALGORITHM, PasswordVerifier
from bo19.config import working_values as wv
from bo19.config.settings import load_settings

CHEAP = dict(time_cost=1, memory_cost_kib=8, parallelism=1)


def cheap(**over) -> PasswordVerifier:
    return PasswordVerifier(**{**CHEAP, **over})


class DungSai(unittest.TestCase):
    def setUp(self):
        self.v = cheap()
        self.good = self.v.hash("mat-khau-gia-1")

    def test_hash_la_argon2id_va_verify_dung(self):
        self.assertTrue(self.good.startswith("$argon2id$"))
        self.assertEqual(ALGORITHM, "argon2id")
        self.assertTrue(self.v.verify(self.good, "mat-khau-gia-1"))

    def test_sai_mat_khau(self):
        self.assertFalse(self.v.verify(self.good, "mat-khau-gia-2"))
        self.assertFalse(self.v.verify(self.good, ""))

    def test_tieng_viet_co_dau(self):
        h = self.v.hash("Mật-khẩu-giả-Đặng")
        self.assertTrue(self.v.verify(h, "Mật-khẩu-giả-Đặng"))
        self.assertFalse(self.v.verify(h, "Mat-khau-gia-Dang"))

    def test_hash_do_thu_vien_doc_lap_kiem_duoc(self):
        argon2.PasswordHasher().verify(self.good, "mat-khau-gia-1")  # không ném

    def test_hash_hong_hoac_khong_phai_argon2_la_false(self):
        for stored in ("", "khong-phai-hash", "$2b$12$abcdefghijklmnopqrstuuABCDEFGHIJKLMNOPQRSTUVWXYZ012345", "$argon2id$v=19$m=8,t=1,p=1$x$y"):
            self.assertFalse(self.v.verify(stored, "mat-khau-gia-1"), stored)

    def test_none_la_false(self):
        self.assertFalse(self.v.verify(None, "bat-ky"))

    def test_hash_gia_cung_tham_so_voi_hasher(self):
        params = argon2.extract_parameters(self.v._dummy_hash)
        self.assertEqual((params.type, params.time_cost, params.memory_cost, params.parallelism),
                         (argon2.Type.ID, CHEAP["time_cost"], CHEAP["memory_cost_kib"], CHEAP["parallelism"]))
        self.assertFalse(self.v.verify(self.v._dummy_hash, "bat-ky"))  # mật khẩu của hash giả là chuỗi ngẫu nhiên đã vứt

    def test_tham_so_lay_tu_settings(self):
        s = load_settings({"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": "x", "BO19_SESSION_SECRET": "y" * 32,
                           "BO19_ARGON2_TIME_COST": "1", "BO19_ARGON2_MEMORY_COST_KIB": "16", "BO19_ARGON2_PARALLELISM": "1"})
        v = PasswordVerifier.from_settings(s)
        p = argon2.extract_parameters(v.hash("x"))
        self.assertEqual((p.time_cost, p.memory_cost, p.parallelism), (1, 16, 1))


class MoiCaDeuChayMotLanVerify(unittest.TestCase):
    """Yêu cầu của PO: mã nhân viên không tồn tại vẫn chạy một lần verify argon2id với hash giả — hai nhánh đều gọi verify."""

    def setUp(self):
        self.v = cheap()
        self.good = self.v.hash("dung")

    def spy(self):
        return mock.patch.object(self.v, "_argon_verify", wraps=self.v._argon_verify)

    def test_nhanh_co_hash_that_mot_lan(self):
        with self.spy() as spy:
            self.assertFalse(self.v.verify(self.good, "sai"))
        self.assertEqual([c.args[0] for c in spy.call_args_list], [self.good])

    def test_nhanh_khong_co_hash_mot_lan_voi_hash_gia(self):
        with self.spy() as spy:
            self.assertFalse(self.v.verify(None, "sai"))
        self.assertEqual([c.args[0] for c in spy.call_args_list], [self.v._dummy_hash])

    def test_hai_nhanh_cung_so_lan_goi(self):
        with self.spy() as with_hash:
            self.v.verify(self.good, "sai")
        with self.spy() as without_hash:
            self.v.verify(None, "sai")
        self.assertEqual(with_hash.call_count, without_hash.call_count)
        self.assertEqual(with_hash.call_count, 1)

    def test_mat_khau_dung_cua_nhan_vien_khong_con_hoat_dong_van_mot_lan(self):
        # `api` truyền None khi nhân viên bị tắt: mật khẩu đúng cũng không qua, và vẫn đúng một lần verify
        with self.spy() as spy:
            self.assertFalse(self.v.verify(None, "dung"))
        self.assertEqual(spy.call_count, 1)

    def test_hash_hong_chay_verify_gia_de_bu_thoi_gian(self):
        with self.spy() as spy:
            self.assertFalse(self.v.verify("khong-phai-hash", "sai"))
        self.assertEqual([c.args[0] for c in spy.call_args_list], ["khong-phai-hash", self.v._dummy_hash])  # lần đầu ném InvalidHashError, lần hai là verify giả


class TranVerifyDongThoi(unittest.TestCase):
    """WV-16b: trần 4 lần verify đồng thời trong một tiến trình; lần thứ năm chờ."""

    class Slow:
        def __init__(self):
            self.lock, self.active, self.peak, self.calls = threading.Lock(), 0, 0, 0

        def verify(self, stored, password):
            with self.lock:
                self.active += 1
                self.calls += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.15)
            with self.lock:
                self.active -= 1
            return True

        def hash(self, password):
            return "x"

    def run_threads(self, v: PasswordVerifier, n: int) -> "TranVerifyDongThoi.Slow":
        slow = self.Slow()
        v._ph = slow  # type: ignore[assignment]
        threads = [threading.Thread(target=v.verify, args=("$argon2id$gia", "p")) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        return slow

    def test_mac_dinh_la_bon_va_lan_thu_nam_cho(self):
        self.assertEqual(wv.ARGON2_MAX_CONCURRENT_VERIFY, 4)
        slow = self.run_threads(cheap(), 10)
        self.assertEqual(slow.peak, 4)  # chạm trần nhưng không vượt
        self.assertEqual(slow.calls, 10)  # không ai bị bỏ — người thứ năm chờ rồi chạy

    def test_tran_do_cau_hinh_duoc_cho_test(self):
        self.assertEqual(self.run_threads(cheap(max_concurrent=2), 6).peak, 2)

    def test_hash_dung_chung_tran_voi_verify(self):
        v = cheap(max_concurrent=1)
        slow = self.Slow()
        v._ph = slow  # type: ignore[assignment]
        t0 = time.monotonic()
        threads = [threading.Thread(target=v.verify, args=("$argon2id$gia", "p")) for _ in range(3)]
        [t.start() for t in threads]
        [t.join(10) for t in threads]
        self.assertEqual(slow.peak, 1)
        self.assertGreaterEqual(time.monotonic() - t0, 0.4)  # ba lần xếp hàng, mỗi lần 0.15 s


if __name__ == "__main__":
    unittest.main()
