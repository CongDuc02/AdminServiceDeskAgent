"""Test trình chạy migration (ADR-017).

Ca thuần chạy luôn. Ca tích hợp cần BO19_TEST_PG_SUPERUSER_DSN — một PostgreSQL mới, ví dụ container
pgvector/pgvector:0.8.1-pg18 (ADR-033): test tự làm bước 0 bằng superuser (đứng thay user mặc định Render),
rồi chạy migrate_main bằng một role migrator riêng.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bo19.entrypoints import migrate_main as mm  # noqa: E402
from bo19.startup import checks  # noqa: E402


class EmptyFileRule(unittest.TestCase):
    def test_chi_chu_thich_la_rong(self):
        self.assertEqual(mm.executable_sql("-- a\n/* b */\n  \n"), "")

    def test_file_rong_dung(self):
        d = Path(tempfile.mkdtemp())
        f = d / "x.sql"
        f.write_text("-- chỉ chú thích\n", encoding="utf-8")
        with self.assertRaisesRegex(mm.MigrationStop, "MIGRATE_EMPTY_FILE"):
            mm.read_sql(f, d)
        shutil.rmtree(d)


@unittest.skipUnless(os.environ.get("BO19_TEST_PG_SUPERUSER_DSN"), "cần BO19_TEST_PG_SUPERUSER_DSN")
class MigrateOnPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        cls.psycopg = psycopg
        cls.su = os.environ["BO19_TEST_PG_SUPERUSER_DSN"]
        cls.db = f"t_mig_{uuid.uuid4().hex[:8]}"
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
        # Bước 0 — như runbook, bằng role mạnh.
        with psycopg.connect(dsn(), autocommit=True) as c:
            c.execute("create extension if not exists vector")
            c.execute("grant create on schema public to bo19_migrator")
        cls.root = Path(tempfile.mkdtemp(prefix="bo19-mig-root-"))
        shutil.copytree(mm.MIGRATIONS_DIR, cls.root / "m")

    @classmethod
    def tearDownClass(cls):
        with cls.psycopg.connect(cls.su, autocommit=True) as c:
            c.execute(f"drop database if exists {cls.db} with (force)")
        shutil.rmtree(cls.root, ignore_errors=True)

    def run_mm(self, root: Path) -> None:
        logging.disable(logging.CRITICAL)
        try:
            mm.run(self.dsn("bo19_migrator"), root)
        finally:
            logging.disable(logging.NOTSET)

    def test_1_chay_lan_dau_roi_lan_hai_khong_doi_gi(self):
        self.run_mm(self.root / "m")
        with self.psycopg.connect(self.dsn("bo19_app")) as c:
            from bo19.persistence import probe
            known = checks.known_migrations(self.root / "m")
            self.assertEqual(checks.evaluate_ledger(probe.read_ledger(c), known), [])
            self.assertEqual(checks.evaluate_role(probe.role_facts(c), probe.write_probe(c, checks.AUDIT_EVENT_UPDATE_PROBE)), [])
        self.run_mm(self.root / "m")  # lần hai: mọi file đã có trong sổ
        with self.psycopg.connect(self.dsn("bo19_migrator")) as c:
            n = c.execute("select count(*) from schema_migration").fetchone()[0]
        self.assertEqual(n, len(checks.known_migrations(self.root / "m")))

    def test_2_file_da_ap_bi_sua_thi_dung(self):
        self.run_mm(self.root / "m")
        f = self.root / "m" / "schema" / "0009_llm_usage_reasoning_tokens.sql"
        saved = f.read_bytes()
        try:
            f.write_bytes(saved + b"\n-- sua sau khi ap\n")
            with self.assertRaisesRegex(mm.MigrationStop, "MIGRATE_LEDGER_MISMATCH schema/0009"):
                self.run_mm(self.root / "m")
        finally:
            f.write_bytes(saved)

    def test_3_app_khong_ghi_duoc_so(self):
        self.run_mm(self.root / "m")
        with self.psycopg.connect(self.dsn("bo19_app")) as c:
            with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                c.execute("delete from schema_migration where false")


if __name__ == "__main__":
    unittest.main()
