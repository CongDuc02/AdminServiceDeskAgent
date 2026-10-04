"""Test bước kiểm khởi động #1 và #2 — S2 của Spike 1.

Chạy từ backend/:  python -m unittest discover -s tests -v   (cần psycopg — có trong lock)
Lớp `PostgresRoleTest` cần một PostgreSQL mới, nối bằng superuser, qua biến BO19_TEST_PG_SUPERUSER_DSN —
ví dụ container pgvector/pgvector:0.8.1-pg18 (ADR-033). Không có biến đó thì bỏ qua lớp này.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bo19.config.settings import ConfigError, Settings, load_settings  # noqa: E402
from bo19.persistence.probe import RoleFacts  # noqa: E402
from bo19.startup import checks  # noqa: E402

CLEAN = RoleFacts("bo19_app", False, False, False, False, False, 0)


def facts(**kw) -> RoleFacts:
    return RoleFacts(**{**CLEAN.__dict__, **kw})


class Step02Role(unittest.TestCase):
    def test_bo19_app_sach_dat(self):
        self.assertEqual(checks.evaluate_role(CLEAN, "DENIED"), [])

    def test_so_huu_database_truot(self):
        self.assertIn("STARTUP_02_OWNS_DATABASE", checks.evaluate_role(facts(owns_database=True), "DENIED"))

    def test_so_huu_schema_public_truot(self):
        self.assertIn("STARTUP_02_OWNS_SCHEMA_PUBLIC", checks.evaluate_role(facts(owns_public=True), "DENIED"))

    def test_createrole_truot(self):
        self.assertIn("STARTUP_02_CREATEROLE", checks.evaluate_role(facts(createrole=True), "DENIED"))

    def test_createdb_truot(self):
        self.assertIn("STARTUP_02_CREATEDB", checks.evaluate_role(facts(createdb=True), "DENIED"))

    def test_superuser_truot(self):
        self.assertIn("STARTUP_02_SUPERUSER", checks.evaluate_role(facts(superuser=True), "DENIED"))

    def test_user_mac_dinh_render_truot_du_bon_ve(self):
        # Hình dạng của user mặc định Render đo ở S0, S1: không superuser, CREATEROLE, CREATEDB,
        # chủ database và public, không sở hữu bảng — vế cũ của #2 để lọt role này.
        got = checks.evaluate_role(facts(user="<user_mac_dinh>", createrole=True, createdb=True,
                                         owns_database=True, owns_public=True), "ALLOWED")
        for code in ("STARTUP_02_CREATEROLE", "STARTUP_02_CREATEDB", "STARTUP_02_OWNS_DATABASE",
                     "STARTUP_02_OWNS_SCHEMA_PUBLIC", "STARTUP_02_AUDIT_EVENT_WRITABLE"):
            self.assertIn(code, got)

    def test_bo19_migrator_truot(self):
        self.assertIn("STARTUP_02_OWNS_TABLES", checks.evaluate_role(facts(owned_public_tables=47), "ALLOWED"))

    def test_probe_loi_khac_truot(self):
        self.assertEqual(checks.evaluate_role(CLEAN, "ERROR:42P01"), ["STARTUP_02_PROBE_ERROR:42P01"])


class Step01Ledger(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bo19-mig-"))
        (self.tmp / "schema").mkdir()
        (self.tmp / "data").mkdir()
        (self.tmp / "schema" / "0001_a.sql").write_text("select 1;\n", encoding="utf-8")
        (self.tmp / "data" / "0001_b.sql").write_text("select 2;\n", encoding="utf-8")
        self.known = checks.known_migrations(self.tmp)
        self.ok = {m.filename: (m.kind, m.sha256) for m in self.known}

    def test_doc_dung_hai_loai(self):
        self.assertEqual([(m.filename, m.kind) for m in self.known], [("schema/0001_a.sql", "schema"), ("data/0001_b.sql", "data")])

    def test_so_vang_truot(self):
        self.assertEqual(checks.evaluate_ledger(None, self.known), ["STARTUP_01_LEDGER_MISSING"])

    def test_so_du_dat(self):
        self.assertEqual(checks.evaluate_ledger(self.ok, self.known), [])

    def test_thieu_file_truot(self):
        led = dict(self.ok)
        del led["data/0001_b.sql"]
        self.assertEqual(checks.evaluate_ledger(led, self.known), ["STARTUP_01_NOT_APPLIED:data/0001_b.sql"])

    def test_lech_sha_truot(self):
        led = {**self.ok, "schema/0001_a.sql": ("schema", "0" * 64)}
        self.assertEqual(checks.evaluate_ledger(led, self.known), ["STARTUP_01_SHA256_MISMATCH:schema/0001_a.sql"])

    def test_so_co_them_migration_moi_hon_van_dat(self):
        # ADR-017: sổ có thêm migration mới hơn bản build biết thì vẫn chạy.
        self.assertEqual(checks.evaluate_ledger({**self.ok, "schema/0099_x.sql": ("schema", "f" * 64)}, self.known), [])

    def test_image_that_mang_0001_dung_sha(self):
        real = {m.filename: m.sha256 for m in checks.known_migrations()}
        self.assertEqual(real["schema/0001_initial.sql"],
                         "937ca18412aff409f2dd429a50b550524994fab73579b12bc23f68bc71e242fd")


class Config(unittest.TestCase):
    def test_thieu_dsn(self):
        with self.assertRaisesRegex(ConfigError, "CONFIG_DATABASE_URL_MISSING"):
            load_settings({})

    def test_repr_khong_lo_dsn(self):
        s = load_settings({"BO19_DATABASE_URL": "postgresql://u:matkhau@h/db", "PORT": "10000"})
        self.assertNotIn("matkhau", repr(s))
        self.assertIsInstance(s, Settings)


@unittest.skipUnless(os.environ.get("BO19_TEST_PG_SUPERUSER_DSN"), "cần BO19_TEST_PG_SUPERUSER_DSN")
class PostgresRoleTest(unittest.TestCase):
    """Dựng trên PostgreSQL thật: một role giống user mặc định Render, một role giống bo19_app."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        cls.psycopg = psycopg
        su = os.environ["BO19_TEST_PG_SUPERUSER_DSN"]
        tag = uuid.uuid4().hex[:8]
        cls.owner, cls.app, cls.db = f"t_owner_{tag}", f"t_app_{tag}", f"t_db_{tag}"
        with psycopg.connect(su, autocommit=True) as c:
            c.execute(f"create role {cls.owner} login createrole createdb")
            c.execute(f"create role {cls.app} login")
            c.execute(f"create database {cls.db} owner {cls.owner}")
        d = conninfo_to_dict(su)

        def dsn(user):
            dd = {**d, "user": user, "dbname": cls.db}
            dd.pop("password", None)
            return make_conninfo(**dd)
        cls.dsn = staticmethod(dsn)
        with psycopg.connect(dsn(cls.owner), autocommit=True) as c:
            c.execute("create table audit_event (id uuid primary key)")
            c.execute(f"grant select, insert on audit_event to {cls.app}")
        cls.su = su

    @classmethod
    def tearDownClass(cls):
        with cls.psycopg.connect(cls.su, autocommit=True) as c:
            c.execute(f"drop database if exists {cls.db} with (force)")
            c.execute(f"drop role if exists {cls.app}")
            c.execute(f"drop role if exists {cls.owner}")

    def run_checks(self, user):
        with self.psycopg.connect(self.dsn(user)) as c:
            from bo19.persistence import probe
            return checks.evaluate_role(probe.role_facts(c), probe.write_probe(c, checks.AUDIT_EVENT_UPDATE_PROBE))

    def test_role_giong_user_mac_dinh_truot(self):
        got = self.run_checks(self.owner)
        for code in ("STARTUP_02_CREATEROLE", "STARTUP_02_CREATEDB", "STARTUP_02_OWNS_DATABASE",
                     "STARTUP_02_OWNS_SCHEMA_PUBLIC", "STARTUP_02_OWNS_TABLES", "STARTUP_02_AUDIT_EVENT_WRITABLE"):
            self.assertIn(code, got)

    def test_role_giong_bo19_app_dat(self):
        self.assertEqual(self.run_checks(self.app), [])


if __name__ == "__main__":
    unittest.main()
