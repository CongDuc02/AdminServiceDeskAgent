"""Test bước kiểm khởi động #15, #16, #17 — B2 (ADR-023, lớp 2).

Phần thuần chạy luôn. Phần `OperatingModeTrenPostgres` cần BO19_TEST_PG_SUPERUSER_DSN (PostgreSQL mới) — kiểm câu đọc `operating_mode`
trên bảng thật. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_checks_environment -v
"""
from __future__ import annotations

import io
import json
import logging
import os
import unittest
import uuid
from pathlib import Path
from unittest import mock

from bo19.config.settings import load_settings
from bo19.observability.log import configure_logging
from bo19.persistence import read
from bo19.startup import runner
from bo19.startup.checks_environment import step_15, step_16, step_17
from bo19.startup.model import Context, Entry

BASE = {"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": "x", "BO19_SESSION_SECRET": "y"}
NONPROD = read.OperatingModeRead(read.NON_PRODUCTION, True)
NONPROD_DEFAULT = read.OperatingModeRead(read.NON_PRODUCTION, False)
PROD = read.OperatingModeRead(read.PRODUCTION, True)


def ctx(entry: Entry = Entry.API, mode=NONPROD, **env) -> Context:
    c = Context(entry, load_settings({**BASE, **env}), {}, None, Path("."))
    if mode is not None:
        c.cache["operating_mode"] = mode
    return c


class Buoc16(unittest.TestCase):
    def test_ba_gia_tri_hop_le_dat(self):
        for v in ("dev", "staging", "prod"):
            for entry in (Entry.API, Entry.WORKER, Entry.CRON):
                self.assertEqual(step_16(ctx(entry, BO19_ENVIRONMENT=v)).codes, (), (v, entry))

    def test_thieu_la_chan_khong_mac_dinh_prod(self):
        env = {k: v for k, v in BASE.items() if k != "BO19_ENVIRONMENT"}
        c = Context(Entry.API, load_settings(env), {}, None, Path("."))
        self.assertEqual(step_16(c).codes, ("STARTUP_16_ENVIRONMENT_MISSING",))

    def test_rong_la_thieu(self):
        self.assertEqual(step_16(ctx(BO19_ENVIRONMENT="  ")).codes, ("STARTUP_16_ENVIRONMENT_MISSING",))

    def test_gia_tri_la_chan(self):
        for bad in ("Dev", "production", "test", "PROD", "local"):
            self.assertEqual(step_16(ctx(BO19_ENVIRONMENT=bad)).codes, ("STARTUP_16_ENVIRONMENT_INVALID",), bad)


class Buoc17(unittest.TestCase):
    def test_ngoai_prod_phai_la_non_production(self):
        for env in ("dev", "staging"):
            self.assertEqual(step_17(ctx(mode=NONPROD, BO19_ENVIRONMENT=env)).codes, (), env)
            self.assertEqual(step_17(ctx(mode=NONPROD_DEFAULT, BO19_ENVIRONMENT=env)).codes, (), env)  # D-009: chưa có dòng nào
            self.assertEqual(step_17(ctx(mode=PROD, BO19_ENVIRONMENT=env)).codes, ("STARTUP_17_OPERATING_MODE_MISMATCH",), env)

    def test_prod_luon_qua_bat_ke_operating_mode(self):
        for mode in (PROD, NONPROD, NONPROD_DEFAULT):
            self.assertEqual(step_17(ctx(mode=mode, BO19_ENVIRONMENT="prod")).codes, (), mode)

    def test_prod_moi_dung_chua_co_dong_nao_van_khoi_dong(self):
        self.assertEqual(step_17(ctx(mode=NONPROD_DEFAULT, BO19_ENVIRONMENT="prod")).codes, ())

    def test_bien_khong_doc_duoc_thi_bo_qua_va_khong_bao_trung_voi_16(self):
        env = {k: v for k, v in BASE.items() if k != "BO19_ENVIRONMENT"}
        for mode in (PROD, NONPROD):
            c = Context(Entry.API, load_settings(env), {}, None, Path("."))
            c.cache["operating_mode"] = mode
            self.assertEqual(step_17(c).codes, ())
        self.assertEqual(step_17(ctx(mode=PROD, BO19_ENVIRONMENT="Dev")).codes, ())  # sai giá trị cũng vậy — #16 đã bắt

    def test_khong_doc_duoc_operating_mode_ngoai_prod_la_chan_fail_closed(self):
        err = RuntimeError("bảng chưa có")
        self.assertEqual(step_17(ctx(mode=err, BO19_ENVIRONMENT="dev")).codes, ("STARTUP_17_OPERATING_MODE_UNREADABLE",))
        self.assertEqual(step_17(ctx(mode=err, BO19_ENVIRONMENT="prod")).codes, ())


class Buoc15(unittest.TestCase):
    def test_chi_ghi_log_khong_bao_gio_chan(self):
        for mode in (NONPROD, NONPROD_DEFAULT, PROD, RuntimeError("x")):
            self.assertEqual(step_15(ctx(mode=mode)).codes, (), mode)

    def test_thong_tin_ghi_log(self):
        self.assertEqual(dict(step_15(ctx(mode=NONPROD_DEFAULT)).info), {"mode": "NON_PRODUCTION", "source": "DEFAULT_NO_ROW"})
        self.assertEqual(dict(step_15(ctx(mode=PROD)).info), {"mode": "PRODUCTION", "source": "ROW"})
        self.assertEqual(dict(step_15(ctx(mode=LookupError("x"))).info),
                         {"mode": "UNREADABLE", "source": "READ_ERROR", "read_error_type": "LookupError"})


class MotLanDoc(unittest.TestCase):
    def test_15_va_17_chi_doc_mot_lan(self):
        with mock.patch.object(read, "current_operating_mode", return_value=NONPROD) as reader:
            c = ctx(mode=None)
            step_15(c)
            step_17(c)
            step_17(c)
            self.assertEqual(reader.call_count, 1)

    def test_17_chay_truoc_15_van_chi_doc_mot_lan(self):
        with mock.patch.object(read, "current_operating_mode", return_value=NONPROD) as reader:
            c = ctx(mode=None)
            step_17(c)
            step_15(c)
            self.assertEqual(reader.call_count, 1)

    def test_loi_doc_cung_chi_doc_mot_lan(self):
        with mock.patch.object(read, "current_operating_mode", side_effect=RuntimeError("x")) as reader:
            c = ctx(mode=None)
            step_15(c)
            step_17(c)
            self.assertEqual(reader.call_count, 1)


class QuaBoChay(unittest.TestCase):
    """#17 vẫn chạy khi #16 trượt (chạy hết rồi gom), và không báo trùng."""

    class Conn:
        closed = False

        def rollback(self):
            pass

        def close(self):
            self.closed = True

    def setUp(self):
        self.out = io.StringIO()
        h = configure_logging(self.out)
        self.addCleanup(logging.getLogger().removeHandler, h)

    def run_env(self, env, mode):
        steps = [s for s in runner.MATRIX if s.number in ("15", "16", "17")]
        registry = {k: v for k, v in runner.REGISTRY.items() if k in ("15", "16", "17")}
        with mock.patch.object(read, "current_operating_mode", return_value=mode):
            return runner.run(Entry.API, load_settings(env), env, steps=steps, registry=registry, connector=lambda d, a: self.Conn())

    def test_thieu_environment_chi_co_ma_cua_16(self):
        env = {k: v for k, v in BASE.items() if k != "BO19_ENVIRONMENT"}
        report = self.run_env(env, PROD)
        self.assertEqual(report.failures, ("STARTUP_16_ENVIRONMENT_MISSING",))

    def test_dev_cung_operating_mode_production_chi_co_ma_cua_17(self):
        self.assertEqual(self.run_env(BASE, PROD).failures, ("STARTUP_17_OPERATING_MODE_MISMATCH",))

    def test_dev_cung_non_production_dat_va_log_chi_co_thong_tin_15(self):
        report = self.run_env(BASE, NONPROD_DEFAULT)
        self.assertTrue(report.ok)
        info = [json.loads(x) for x in self.out.getvalue().splitlines() if '"STARTUP_CHECK_INFO"' in x]
        self.assertEqual([(i["step"], i["mode"], i["source"]) for i in info], [("15", "NON_PRODUCTION", "DEFAULT_NO_ROW")])


@unittest.skipUnless(os.environ.get("BO19_TEST_PG_SUPERUSER_DSN"), "cần BO19_TEST_PG_SUPERUSER_DSN")
class OperatingModeTrenPostgres(unittest.TestCase):
    """Câu đọc `operating_mode` trên một bảng `operating_mode_change` thật (DDL rút gọn: chỉ cột mà câu đọc dùng)."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        cls.psycopg = psycopg
        cls.su = os.environ["BO19_TEST_PG_SUPERUSER_DSN"]
        cls.db = f"t_opm_{uuid.uuid4().hex[:8]}"
        with psycopg.connect(cls.su, autocommit=True) as c:
            c.execute(f"create database {cls.db}")
        cls.dsn = make_conninfo(**{**conninfo_to_dict(cls.su), "dbname": cls.db})
        with psycopg.connect(cls.dsn, autocommit=True) as c:
            c.execute("create table operating_mode_change (id uuid primary key default gen_random_uuid(), from_mode text, to_mode text not null, "
                      "effective_at timestamptz not null unique)")

    @classmethod
    def tearDownClass(cls):
        with cls.psycopg.connect(cls.su, autocommit=True) as c:
            c.execute(f"drop database if exists {cls.db} with (force)")

    def setUp(self):
        with self.psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute("truncate operating_mode_change")

    def insert(self, to_mode: str, when_sql: str):
        with self.psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute(f"insert into operating_mode_change (from_mode, to_mode, effective_at) values ('x', %s, {when_sql})", (to_mode,))

    def current(self):
        with self.psycopg.connect(self.dsn) as c:
            got = read.current_operating_mode(c)
            from psycopg.pq import TransactionStatus
            self.assertEqual(c.info.transaction_status, TransactionStatus.IDLE)  # giao dịch đã đóng sạch
            return got

    def test_chua_co_dong_nao_la_non_production_mac_dinh(self):
        self.assertEqual(self.current(), read.OperatingModeRead("NON_PRODUCTION", False))

    def test_dong_da_toi_thi_dung(self):
        self.insert("PRODUCTION", "now() - interval '1 hour'")
        self.assertEqual(self.current(), read.OperatingModeRead("PRODUCTION", True))

    def test_dong_chua_toi_bi_bo_qua(self):
        self.insert("PRODUCTION", "now() + interval '1 hour'")
        self.assertEqual(self.current(), read.OperatingModeRead("NON_PRODUCTION", False))

    def test_dong_effective_at_lon_nhat_da_toi_thang(self):
        self.insert("PRODUCTION", "now() - interval '2 hour'")
        self.insert("NON_PRODUCTION", "now() - interval '1 hour'")
        self.insert("PRODUCTION", "now() + interval '1 hour'")
        self.assertEqual(self.current(), read.OperatingModeRead("NON_PRODUCTION", True))

    def test_giao_dich_doc_chi_doc_ghi_bi_tu_choi(self):
        """Lối đọc mở READ ONLY — một câu ghi trong cùng giao dịch bị PostgreSQL từ chối."""
        with self.psycopg.connect(self.dsn) as c:
            with self.assertRaises(self.psycopg.errors.ReadOnlySqlTransaction):
                with c.transaction():
                    c.execute("SET TRANSACTION READ ONLY")
                    c.execute("insert into operating_mode_change (to_mode, effective_at) values ('PRODUCTION', now())")

    def test_chay_duoc_khi_ket_noi_dang_o_giua_giao_dich(self):
        self.insert("PRODUCTION", "now() - interval '1 hour'")
        with self.psycopg.connect(self.dsn) as c:
            c.execute("select 1")  # mở sẵn một giao dịch như một bước trước để lại
            self.assertEqual(read.current_operating_mode(c), read.OperatingModeRead("PRODUCTION", True))

    def test_bang_chua_co_la_loi_de_buoc_kiem_tu_quyet(self):
        with self.psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute("alter table operating_mode_change rename to omc_tmp")
        try:
            with self.psycopg.connect(self.dsn) as c:
                with self.assertRaises(self.psycopg.errors.UndefinedTable):
                    read.current_operating_mode(c)
        finally:
            with self.psycopg.connect(self.dsn, autocommit=True) as c:
                c.execute("alter table omc_tmp rename to operating_mode_change")


if __name__ == "__main__":
    unittest.main()
