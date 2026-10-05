"""`tools/seed-dev/seed_dev.py` trên PostgreSQL thật đã migrate bằng `migrate_main` — và AC-1.6 sau seed: `check_grants.py --app-dsn` → `Lệch: 0`, mã thoát 0.

Mỗi lớp test dựng DB riêng (không dùng DB chung): seed đặt mã nhân viên cố định nên cần một DB sạch. Mật khẩu giả chỉ nằm trong file tạm của test.
Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_seed_dev -v
"""
from __future__ import annotations

import importlib.util
import io
import logging
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from bo19.api.app import create_app
from bo19.api.auth.hasher import PasswordVerifier
from bo19.api.deps.state import AppState
from bo19.observability.log import configure_logging
from bo19.persistence.pool import Pool
from tests import pg_support

REPO = Path(__file__).resolve().parents[2]
SEED_PATH = REPO / "tools" / "seed-dev" / "seed_dev.py"
CHECK_GRANTS = REPO / "tools" / "contract-checks" / "check_grants.py"

spec = importlib.util.spec_from_file_location("seed_dev", SEED_PATH)
seed_dev = importlib.util.module_from_spec(spec)
sys.modules["seed_dev"] = seed_dev  # `@dataclass` + `from __future__ import annotations` tra cứu module trong sys.modules lúc định nghĩa lớp
spec.loader.exec_module(seed_dev)

CHEAP = PasswordVerifier(time_cost=1, memory_cost_kib=8, parallelism=1)  # test tự dựng hasher rẻ; hash vẫn là argon2id
CSRF = {"X-BO19-CSRF": "1"}
SECRET = "seed-test-" + "s" * 40


class Chua(unittest.TestCase):
    """Thuần — không cần DB."""

    def test_nhan_gia_tren_moi_tai_khoan(self):
        for e in seed_dev.EMPLOYEES:
            self.assertTrue(e.code.startswith("GIA-"), e.code)
            self.assertIn("(GIẢ)", e.full_name)
        self.assertEqual(seed_dev.SOURCE, "SEED_DEV_FAKE")

    def test_chi_mot_dong_cap_le_va_la_document_sign_cho_mot_admin_officer(self):
        self.assertEqual((seed_dev.SIGNER_CODE, seed_dev.SIGNER_PERMISSION), ("GIA-0101", "document.sign"))
        self.assertEqual({e.role for e in seed_dev.EMPLOYEES if e.code == seed_dev.SIGNER_CODE}, {"ADMIN_OFFICER"})

    def test_id_co_dinh_theo_ma(self):
        self.assertEqual(seed_dev.employee_id("GIA-0001"), seed_dev.employee_id("GIA-0001"))
        self.assertNotEqual(seed_dev.employee_id("GIA-0001"), seed_dev.employee_id("GIA-0002"))

    def test_host_khong_phai_local_bi_tu_choi_truoc_khi_noi(self):
        for dsn in ("postgresql://u@dpg-abc123.oregon-postgres.render.com/db", "postgresql://u@dpg-abc123-a/db", "postgresql://u@db.example.com:5432/x",
                    "host=dpg-abc123-a user=u dbname=x", "postgresql://u@127.0.0.1,db.example.com/x"):
            with self.assertRaises(seed_dev.SeedRefused) as cm:
                seed_dev.check_host(dsn, frozenset())
            self.assertEqual(str(cm.exception), "SEED_HOST_NOT_LOCAL")
            self.assertNotIn("render", str(cm.exception))  # thông điệp là mã, không mang host

    def test_host_local_va_host_khai_ro_duoc_qua(self):
        for dsn in ("postgresql://u@localhost/db", "postgresql://u@127.0.0.1:5432/db", "postgresql://u@[::1]/db", "postgresql:///db", "host=/var/run/postgresql dbname=x"):
            seed_dev.check_host(dsn, frozenset())
        seed_dev.check_host("postgresql://u@pg:5432/db", frozenset({"pg"}))

    def test_cli_thieu_bien_moi_truong_la_ma_thoat_2_khong_in_gi_nhay_cam(self):
        env = {k: v for k, v in os.environ.items() if k != "BO19_MIGRATOR_DATABASE_URL"}
        r = subprocess.run([sys.executable, str(SEED_PATH)], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertIn("SEED_DEV_CONFIG_MISSING", r.stderr)

    def test_cli_dsn_render_bi_chan_khong_noi_va_khong_in_dsn(self):
        dsn = "postgresql://bo19_migrator:BI_MAT_DSN_KHONG_LOT@dpg-abc123.oregon-postgres.render.com/bo19"
        r = subprocess.run([sys.executable, str(SEED_PATH)], env={**os.environ, "BO19_MIGRATOR_DATABASE_URL": dsn}, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertIn("SEED_HOST_NOT_LOCAL", r.stderr)
        for text in (r.stdout, r.stderr):
            self.assertNotIn("BI_MAT_DSN_KHONG_LOT", text)
            self.assertNotIn("render.com", text)

    def test_tham_so_argon2_yeu_hon_wv16_bi_tu_choi(self):
        old = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(old)))
        os.environ["BO19_ARGON2_TIME_COST"] = "1"
        with self.assertRaises(seed_dev.SeedRefused) as cm:
            seed_dev.default_verifier()
        self.assertEqual(str(cm.exception), "SEED_ARGON2_PARAMS_BELOW_WV16")


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class SeedTrenPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)  # DB sạch riêng
        cls.tmp = tempfile.TemporaryDirectory(prefix="bo19-seed-")
        cls.pw_file = Path(cls.tmp.name) / "out" / "passwords.local.txt"

    @classmethod
    def tearDownClass(cls):
        cls.db.drop()
        cls.tmp.cleanup()

    def seed(self, **kw):
        out = io.StringIO()
        report = seed_dev.run(self.db.dsn("bo19_migrator"), self.pw_file, allow_hosts=frozenset({self.host()}), verifier=CHEAP, out=out, **kw)
        return report, out.getvalue()

    def host(self) -> str:
        from psycopg.conninfo import conninfo_to_dict
        return conninfo_to_dict(self.db.dsn()).get("host") or "localhost"

    def query(self, sql: str, params=()):
        with self.db.connect("bo19_migrator") as c:
            return c.execute(sql, params).fetchall()

    # --- thứ tự: các test dưới đây dùng chung một DB sạch nên đặt tên có số để unittest chạy theo thứ tự chữ cái ---------------------------

    def test_1_lan_dau_nap_dung_du_lieu_gia_co_nhan(self):
        report, stdout = self.seed()
        self.assertEqual((report.employees_created, report.roles_created, report.grants_created, report.credentials_written), (5, 5, 1, 5))
        rows = self.query("select employee_code, source, full_name, national_id, date_of_birth, is_active from employee order by 1")
        self.assertEqual([r[0] for r in rows], ["GIA-0001", "GIA-0002", "GIA-0003", "GIA-0101", "GIA-0102"])
        for code, source, name, national_id, dob, active in rows:
            self.assertEqual(source, "SEED_DEV_FAKE")
            self.assertIn("(GIẢ)", name)
            self.assertIsNone(national_id)
            self.assertIsNone(dob)
            self.assertTrue(active)
        roles = dict(self.query("select e.employee_code, er.role_code from employee_role er join employee e on e.id = er.employee_id"))
        self.assertEqual(roles, {"GIA-0001": "EMPLOYEE", "GIA-0002": "EMPLOYEE", "GIA-0003": "EMPLOYEE", "GIA-0101": "ADMIN_OFFICER", "GIA-0102": "ADMIN_OFFICER"})

    def test_2_dung_mot_dong_cap_le_document_sign_cho_admin_officer_va_khong_operating_mode_change(self):
        self.seed()
        grants = self.query("select e.employee_code, g.permission_code, g.revoked_at from employee_permission_grant g join employee e on e.id = g.employee_id")
        self.assertEqual(grants, [("GIA-0101", "document.sign", None)])
        self.assertEqual(self.query("select count(*) from employee_permission_grant where permission_code = 'operating_mode.change'"), [(0,)])  # ADR-023 lớp 1
        self.assertEqual(self.query("select count(*) from operating_mode_change"), [(0,)])  # không đụng chế độ vận hành

    def test_3_credential_la_argon2id_va_mat_khau_chi_o_trong_file(self):
        _, stdout = self.seed()
        creds = self.query("select e.employee_code, c.password_hash, c.hash_algorithm from employee_credential c join employee e on e.id = c.employee_id order by 1")
        self.assertEqual(len(creds), 5)
        passwords = seed_dev.read_passwords(self.pw_file)
        self.assertEqual(sorted(passwords), [c[0] for c in creds])
        self.assertEqual(len(set(passwords.values())), 5)  # mỗi tài khoản một mật khẩu riêng
        for code, h, alg in creds:
            self.assertEqual(alg, "argon2id")
            self.assertTrue(h.startswith("$argon2id$"))
            self.assertTrue(CHEAP.verify(h, passwords[code]))
            self.assertNotIn(passwords[code], stdout)  # không in mật khẩu
            self.assertNotIn(passwords[code], h)
        self.assertNotIn("password", "".join(stdout.split("SEED_DEV_PASSWORDS_FILE")[0]).lower())  # dòng tóm tắt không nhắc nội dung

    def test_4_chay_lai_khong_doi_gi(self):
        self.seed()
        before_hash = self.query("select employee_id, password_hash from employee_credential order by 1")
        before_file = self.pw_file.read_bytes()
        report, stdout = self.seed()
        self.assertEqual((report.employees_created, report.roles_created, report.grants_created, report.credentials_written), (0, 0, 0, 0))
        self.assertEqual(self.query("select employee_id, password_hash from employee_credential order by 1"), before_hash)
        self.assertEqual(self.pw_file.read_bytes(), before_file)
        self.assertNotIn("SEED_DEV_PASSWORDS_FILE", stdout)  # không ghi file thì không nhắc file
        self.assertEqual(self.query("select count(*) from employee_permission_grant"), [(1,)])

    def test_5_reset_passwords_doi_mat_khau_cua_ca_nam(self):
        self.seed()
        before = seed_dev.read_passwords(self.pw_file)
        before_hash = dict(self.query("select employee_id::text, password_hash from employee_credential"))
        report, _ = self.seed(reset_passwords=True)
        self.assertEqual(report.credentials_written, 5)
        after = seed_dev.read_passwords(self.pw_file)
        self.assertTrue(all(after[c] != before[c] for c in before))
        after_hash = dict(self.query("select employee_id::text, password_hash from employee_credential"))
        self.assertTrue(all(after_hash[k] != before_hash[k] for k in before_hash))
        rows = self.query("select e.employee_code, c.password_hash from employee_credential c join employee e on e.id = c.employee_id")
        self.assertTrue(all(CHEAP.verify(h, after[code]) for code, h in rows))

    def test_6_dang_nhap_that_bang_tai_khoan_seed_va_permission(self):
        self.seed()
        handler = configure_logging(io.StringIO())
        self.addCleanup(logging.getLogger().removeHandler, handler)
        passwords = seed_dev.read_passwords(self.pw_file)
        pool = Pool(self.db.dsn("bo19_app"), application_name="bo19-test-seed", min_size=1, max_size=3)
        pool.open()
        self.addCleanup(pool.close)
        client = TestClient(create_app(AppState(pool=pool, session_secret=SECRET, verifier=CHEAP)), raise_server_exceptions=False,
                            base_url="https://testserver", client=(pg_support.unique_ip(), 1))

        def me(code: str) -> dict:
            r = client.post("/api/v1/auth/session", json={"employee_code": code, "password": passwords[code]}, headers=CSRF)
            self.assertEqual(r.status_code, 204, code)
            return client.get("/api/v1/me", headers={"Cookie": r.headers["set-cookie"].split(";")[0]}).json()

        signer, officer, employee = me("GIA-0101"), me("GIA-0102"), me("GIA-0001")
        self.assertIn("document.sign", signer["permissions"])  # cấp lẻ
        self.assertIn("document.issue", signer["permissions"])  # gói ADMIN_OFFICER
        self.assertNotIn("document.sign", officer["permissions"])  # chỉ MỘT người được cấp
        self.assertNotIn("document.issue", employee["permissions"])
        for body in (signer, officer, employee):
            self.assertNotIn("operating_mode.change", body["permissions"])
            self.assertEqual(body["operating_mode"], "NON_PRODUCTION")
        self.assertIn("(GIẢ)", signer["employee"]["full_name"])
        self.assertEqual(client.post("/api/v1/auth/session", json={"employee_code": "GIA-0001", "password": "sai"}, headers=CSRF).status_code, 401)

    def test_7_db_dang_o_production_bi_tu_choi_va_khong_ghi_gi(self):
        with self.db.connect(autocommit=True) as c:  # superuser — fixture, như test_ac_1_7
            c.execute("set session_replication_role = replica")
            c.execute("delete from operating_mode_change")
            c.execute("insert into operating_mode_change (id, from_mode, to_mode, decided_by_employee_id, decision_reference, effective_at) "
                      "values (%s, 'NON_PRODUCTION', 'PRODUCTION', %s, 'FIXTURE SEED', now() - interval '1 hour')", (uuid.uuid4(), uuid.uuid4()))

        def restore():
            with self.db.connect(autocommit=True) as c:
                c.execute("set session_replication_role = replica")
                c.execute("delete from operating_mode_change")

        self.addCleanup(restore)
        before = self.query("select count(*) from employee")
        with self.assertRaises(seed_dev.SeedRefused) as cm:
            self.seed()
        self.assertEqual(str(cm.exception), "SEED_DB_NOT_NON_PRODUCTION")
        self.assertEqual(self.query("select count(*) from employee"), before)

    def test_8_noi_bang_role_khac_migrator_bi_tu_choi(self):
        with self.assertRaises(seed_dev.SeedRefused) as cm:
            seed_dev.run(self.db.dsn("bo19_app"), self.pw_file, allow_hosts=frozenset({self.host()}), verifier=CHEAP, out=io.StringIO())
        self.assertEqual(str(cm.exception), "SEED_ROLE_NOT_MIGRATOR")

    def test_9_ac_1_6_check_grants_app_dsn_sau_seed_lech_0(self):
        """AC-1.6 — `check_grants.py --app-dsn` trên DB đã migrate bằng `migrate_main` VÀ đã seed: `Lệch: 0`, mã thoát 0."""
        self.seed()
        env = {**os.environ, "BO19_APP_DSN_LOCAL": self.db.dsn("bo19_app"), "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([sys.executable, str(CHECK_GRANTS), "--app-dsn", "env:BO19_APP_DSN_LOCAL"], env=env, capture_output=True, text=True, encoding="utf-8", timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-1500:])
        self.assertIn("Lệch: 0", r.stdout)


if __name__ == "__main__":
    unittest.main()
