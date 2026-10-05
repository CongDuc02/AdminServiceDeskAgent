"""`bo19.persistence` trên PostgreSQL thật đã migrate: lối đọc READ ONLY, unit of work, ánh xạ ràng buộc → mã, pool (acquire / try_acquire).

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_persistence -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import time
import unittest
import uuid

from psycopg import errors
from psycopg.pq import TransactionStatus

from bo19.persistence import errors as perr
from bo19.persistence.pool import Pool, PoolExhausted
from bo19.persistence.read import current_operating_mode, read_only
from bo19.persistence.write import unit_of_work
from tests import pg_support


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class PersistenceTrenPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.get_db()

    def app(self):
        return self.db.connect("bo19_app")

    # --- lối đọc ---------------------------------------------------------------------------------------------------------------

    def test_read_only_tu_choi_ghi(self):
        with self.app() as c:
            with self.assertRaises(errors.ReadOnlySqlTransaction):
                with read_only(c):
                    c.execute("insert into rate_limit_window (scope, window_start) values ('t', now())")

    def test_read_only_don_giao_dich_do_cua_lan_truoc(self):
        with self.app() as c:
            c.execute("select 1")  # mở giao dịch ngầm, để dở
            with read_only(c):
                self.assertEqual(c.execute("select 1").fetchone(), (1,))
            self.assertEqual(c.info.transaction_status, TransactionStatus.IDLE)

    def test_current_operating_mode_van_chay(self):
        with self.app() as c:
            self.assertEqual(current_operating_mode(c).mode, "NON_PRODUCTION")  # DB mới, chưa có dòng nào — D-009

    # --- unit of work ----------------------------------------------------------------------------------------------------------

    def test_unit_of_work_commit(self):
        scope = f"t:{uuid.uuid4()}"
        with self.app() as c:
            with unit_of_work(c):
                c.execute("insert into rate_limit_window (scope, window_start) values (%s, now())", (scope,))
        with self.app() as c:
            self.assertEqual(c.execute("select count(*) from rate_limit_window where scope = %s", (scope,)).fetchone(), (1,))

    def test_unit_of_work_rollback_khi_ngoai_le(self):
        scope = f"t:{uuid.uuid4()}"
        with self.app() as c:
            with self.assertRaises(RuntimeError):
                with unit_of_work(c):
                    c.execute("insert into rate_limit_window (scope, window_start) values (%s, now())", (scope,))
                    raise RuntimeError("giữa giao dịch")
            self.assertEqual(c.execute("select count(*) from rate_limit_window where scope = %s", (scope,)).fetchone(), (0,))

    def test_vi_pham_check_thanh_ma_theo_tien_to(self):
        with self.app() as c:
            with self.assertRaises(perr.IntegrityViolation) as cm:
                with unit_of_work(c):
                    c.execute("insert into rate_limit_window (scope, window_start, attempt_count) values (%s, now(), 0)", (f"t:{uuid.uuid4()}",))
        self.assertEqual(cm.exception.code, "CHECK_VIOLATION")  # ck_rate_limit_window_count_positive
        self.assertIsNone(cm.exception.__cause__)  # chuỗi nguyên nhân mang thông điệp PostgreSQL (tên bảng, cột) — không để lọt
        self.assertTrue(cm.exception.__suppress_context__)
        self.assertNotIn("rate_limit_window", str(cm.exception))

    def test_rang_buoc_khong_tien_to_roi_ve_ma_chung(self):
        scope = f"t:{uuid.uuid4()}"
        with self.app() as c:
            with unit_of_work(c):
                c.execute("insert into rate_limit_window (scope, window_start) values (%s, '2020-01-01')", (scope,))
            with self.assertRaises(perr.IntegrityViolation) as cm:
                with unit_of_work(c):
                    c.execute("insert into rate_limit_window (scope, window_start) values (%s, '2020-01-01')", (scope,))  # pk_… — không tiền tố
        self.assertEqual(cm.exception.code, perr.UNMAPPED)

    def test_ten_rang_buoc_da_dang_ky_thanh_ma_cua_tool(self):
        old = dict(perr.CONSTRAINT_CODES)
        self.addCleanup(lambda: (perr.CONSTRAINT_CODES.clear(), perr.CONSTRAINT_CODES.update(old)))
        perr.CONSTRAINT_CODES["ck_rate_limit_window_count_positive"] = "TEST_TOOL_CODE"
        with self.app() as c:
            with self.assertRaises(perr.IntegrityViolation) as cm:
                with unit_of_work(c):
                    c.execute("insert into rate_limit_window (scope, window_start, attempt_count) values (%s, now(), 0)", (f"t:{uuid.uuid4()}",))
        self.assertEqual(cm.exception.code, "TEST_TOOL_CODE")

    def test_loi_khong_phai_toan_ven_di_qua_nguyen_van(self):
        with self.app() as c:
            with self.assertRaises(errors.UndefinedTable):
                with unit_of_work(c):
                    c.execute("select * from bang_khong_ton_tai")

    def test_classify_khong_dung_vao_loi_khac(self):
        self.assertIsNone(perr.classify(errors.UndefinedTable()))

    # --- pool ------------------------------------------------------------------------------------------------------------------

    def make_pool(self, size: int, **kw) -> Pool:
        pool = Pool(self.db.dsn("bo19_app"), application_name="bo19-test", min_size=1, max_size=size, **kw)
        pool.open()
        self.addCleanup(pool.close)
        return pool

    def test_acquire_tra_connection_dung_duoc_va_ve_trang_thai_roi(self):
        pool = self.make_pool(1)
        with pool.acquire() as c:
            c.execute("select 1")  # để lại giao dịch dở
        with pool.acquire() as c:
            self.assertEqual(c.info.transaction_status, TransactionStatus.IDLE)  # đã rollback trước khi trả
            self.assertEqual(c.execute("select current_user").fetchone(), ("bo19_app",))

    def test_acquire_het_han_khi_pool_can(self):
        pool = self.make_pool(1)
        with pool.acquire():
            t = time.monotonic()
            with self.assertRaises(PoolExhausted) as cm:
                with pool.acquire(timeout=0.3):
                    pass
            self.assertGreaterEqual(time.monotonic() - t, 0.25)
            self.assertEqual(cm.exception.code, "POOL_EXHAUSTED")

    def test_try_acquire_tra_none_ngay_khi_pool_can_khong_cho(self):
        pool = self.make_pool(1, acquire_timeout_s=5)
        with pool.acquire():
            t = time.monotonic()
            with pool.try_acquire() as c:
                self.assertIsNone(c)
            self.assertLess(time.monotonic() - t, 0.5)  # không chờ hết timeout 5 s của acquire

    def test_try_acquire_tra_connection_khi_con_cho(self):
        pool = self.make_pool(2)
        with pool.try_acquire() as c:
            self.assertIsNotNone(c)
            self.assertEqual(c.execute("select 1").fetchone(), (1,))

    def test_connection_duoc_tra_ve_sau_khi_try_acquire_xong(self):
        pool = self.make_pool(1)
        with pool.try_acquire() as c:
            self.assertIsNotNone(c)
        with pool.try_acquire() as c:  # connection duy nhất đã về pool
            self.assertIsNotNone(c)


if __name__ == "__main__":
    unittest.main()
