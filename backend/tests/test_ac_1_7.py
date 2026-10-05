"""AC-1.7 (12-roadmap.md, Sprint 1): bộ chạy bước kiểm khởi động trên một PostgreSQL thật đã `migrate_main` xong.

- `api` khởi động bằng credential của `bo19_migrator` bị chặn ở bước #2;
- thiếu `BO19_ENVIRONMENT` bị chặn ở #16;
- DB có `operating_mode` hiện hành là `PRODUCTION` với `BO19_ENVIRONMENT = dev` bị chặn ở #17;
- khởi động bằng `bo19_app` với cấu hình đúng qua đủ các bước.

"Đủ các bước" nghĩa là đủ các bước ĐÃ CÓ CODE ở B2; các bước chưa làm hiện trong `report.pending` và bị khoá bởi `DECLARED_PENDING` ở
`test_startup_runner.py` — AC-1.7 không được tính là đạt cho bước chưa làm.

Cần BO19_TEST_PG_SUPERUSER_DSN (PostgreSQL mới, ví dụ pgvector/pgvector:0.8.1-pg18 — ADR-033). Chạy từ backend/:
  PYTHONPATH=src python -m unittest tests.test_ac_1_7 -v
"""
from __future__ import annotations

import io
import json
import logging
import os
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from bo19.config.settings import load_settings
from bo19.entrypoints import migrate_main as mm
from bo19.observability.log import configure_logging
from bo19.startup import runner
from bo19.startup.model import Entry

SECRET = "BI_MAT_PHIEN_KHONG_DUOC_LOT_RA_LOG"


@unittest.skipUnless(os.environ.get("BO19_TEST_PG_SUPERUSER_DSN"), "cần BO19_TEST_PG_SUPERUSER_DSN")
class AC17(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        cls.psycopg = psycopg
        cls.su = os.environ["BO19_TEST_PG_SUPERUSER_DSN"]
        cls.db = f"t_ac17_{uuid.uuid4().hex[:8]}"
        with psycopg.connect(cls.su, autocommit=True) as c:
            for r in ("bo19_migrator", "bo19_app"):
                if not c.execute("select 1 from pg_roles where rolname = %s", (r,)).fetchone():
                    c.execute(f"create role {r} login")
            c.execute(f"create database {cls.db}")
        d = conninfo_to_dict(cls.su)

        def dsn(user=None):
            dd = {**d, "dbname": cls.db}
            if user:
                dd["user"] = user
                dd.pop("password", None)
            return make_conninfo(**dd)
        cls.dsn = staticmethod(dsn)
        with psycopg.connect(dsn(), autocommit=True) as c:  # bước 0 như runbook, bằng role mạnh
            c.execute("create extension if not exists vector")
            c.execute("grant create on schema public to bo19_migrator")
        cls.root = Path(tempfile.mkdtemp(prefix="bo19-ac17-"))
        shutil.copytree(mm.MIGRATIONS_DIR, cls.root / "m")
        logging.disable(logging.CRITICAL)
        try:
            mm.run(dsn("bo19_migrator"), cls.root / "m")
        finally:
            logging.disable(logging.NOTSET)

    @classmethod
    def tearDownClass(cls):
        with cls.psycopg.connect(cls.su, autocommit=True) as c:
            c.execute(f"drop database if exists {cls.db} with (force)")
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        self.out = io.StringIO()
        h = configure_logging(self.out)
        self.addCleanup(logging.getLogger().removeHandler, h)

    def start(self, user: str, entry: Entry = Entry.API, **over):
        env = {"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": self.dsn(user), "BO19_SESSION_SECRET": SECRET}
        env = {**env, **over}
        env = {k: v for k, v in env.items() if v is not None}
        return runner.run(entry, load_settings(env), env, migrations_root=self.root / "m")

    def set_operating_mode(self, to_mode: str | None):
        """Chèn (hay xoá) một dòng `operating_mode_change` bằng superuser. `session_replication_role = replica` tắt kiểm khoá ngoại tới `employee`
        — fixture không cần dựng một nhân viên chỉ để có một dòng quyết định."""
        with self.psycopg.connect(self.dsn(), autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("delete from operating_mode_change")
            if to_mode:
                c.execute("insert into operating_mode_change (id, from_mode, to_mode, decided_by_employee_id, decision_reference, effective_at) "
                          "values (%s, %s, %s, %s, 'FIXTURE AC-1.7', now() - interval '1 hour')",
                          (uuid.uuid4(), "NON_PRODUCTION" if to_mode == "PRODUCTION" else "PRODUCTION", to_mode, uuid.uuid4()))

    # --- bốn vế của AC-1.7 ---------------------------------------------------------------------------------------------------------

    def test_a_credential_cua_migrator_bi_chan_o_buoc_2(self):
        report = self.start("bo19_migrator")
        self.assertFalse(report.ok)
        self.assertIn("STARTUP_02_OWNS_TABLES", report.failures)  # migrator sở hữu mọi bảng
        self.assertTrue(all(c.startswith("STARTUP_02_") for c in report.failures), report.failures)  # và chỉ trượt ở #2
        self.assertNotIn("2", report.passed)

    def test_b_thieu_bo19_environment_bi_chan_o_buoc_16(self):
        report = self.start("bo19_app", BO19_ENVIRONMENT=None)
        self.assertEqual(report.failures, ("STARTUP_16_ENVIRONMENT_MISSING",))  # đúng một mã: #17 không báo trùng

    def test_c_operating_mode_production_voi_environment_dev_bi_chan_o_buoc_17(self):
        self.set_operating_mode("PRODUCTION")
        self.addCleanup(self.set_operating_mode, None)
        report = self.start("bo19_app")
        self.assertEqual(report.failures, ("STARTUP_17_OPERATING_MODE_MISMATCH",))
        # cùng DB, cùng operating_mode, BO19_ENVIRONMENT = prod: điều kiện không kích hoạt — luôn qua
        self.assertTrue(self.start("bo19_app", BO19_ENVIRONMENT="prod").ok)

    def test_d_bo19_app_voi_cau_hinh_dung_qua_du_cac_buoc_da_co_code(self):
        self.set_operating_mode(None)  # chưa có dòng nào — D-009
        report = self.start("bo19_app")
        self.assertTrue(report.ok, report.failures)
        self.assertEqual(report.passed, ("1", "2", "10", "11", "12", "13", "15", "16", "17", "19", "20"))
        self.assertEqual(report.pending, ("3", "4a", "4b", "4c", "5", "8", "9", "14", "21"))  # chưa làm — không tính là đạt
        self.assertEqual(report.skipped, ())
        info = [json.loads(x) for x in self.out.getvalue().splitlines() if '"STARTUP_CHECK_INFO"' in x]
        self.assertEqual([(i["step"], i["mode"], i["source"]) for i in info], [("15", "NON_PRODUCTION", "DEFAULT_NO_ROW")])

    # --- chiều rộng: các entrypoint khác, và không lộ giá trị ----------------------------------------------------------------------

    def test_worker_va_cron_chay_dung_cot_cua_bang(self):
        self.set_operating_mode(None)
        worker = self.start("bo19_app", Entry.WORKER)
        self.assertEqual(worker.passed, ("1", "2", "10", "11", "13", "15", "16", "17", "19"))  # không có #12, #20: chỉ cột api
        cron = self.start("bo19_app", Entry.CRON)
        self.assertEqual(cron.passed, ("1", "2", "10", "13", "16", "19"))  # cron không có #11, #15, #17

    def test_khong_lo_dsn_hay_secret_ra_log(self):
        self.start("bo19_migrator")
        self.start("bo19_app", BO19_ENVIRONMENT=None)
        text = self.out.getvalue()
        self.assertNotIn(SECRET, text)
        self.assertNotIn(self.db, text)  # tên database nằm trong DSN
        self.assertNotIn("postgresql://", text)

    def test_ket_noi_tung_buoc_khong_de_giao_dich_do_dang(self):
        """Mọi bước dùng chung một kết nối; mỗi bước phải trả giao dịch sạch. Nếu một bước để lại giao dịch bị lỗi, bước sau sẽ vỡ
        bằng `current transaction is aborted` — chạy bốn lần liên tiếp phải cho cùng một kết quả."""
        self.set_operating_mode(None)
        results = {self.start("bo19_app").passed for _ in range(4)}
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
