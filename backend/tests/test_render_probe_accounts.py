"""`tools/render-probes/render_probe_accounts.py` — ngoại lệ có thời hạn của cổng 2.7 (PO, 2026-10-21): seed 2–3 tài khoản giả, thu hồi sau đo.

Chạy trên PostgreSQL thật đã migrate (DB riêng mỗi lớp). Mật khẩu giả chỉ nằm trong file tạm của test. Cần BO19_TEST_PG_SUPERUSER_DSN.
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_render_probe_accounts -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import datetime as dt
import importlib.util
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from psycopg.conninfo import conninfo_to_dict

from bo19.api.auth.hasher import PasswordVerifier
from tests import pg_support

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("render_probe_accounts", REPO / "tools" / "render-probes" / "render_probe_accounts.py")
rpa = importlib.util.module_from_spec(spec)
sys.modules["render_probe_accounts"] = rpa
spec.loader.exec_module(rpa)

CHEAP = PasswordVerifier(time_cost=1, memory_cost_kib=8, parallelism=1)
T0 = dt.datetime(2026, 10, 22, 8, 0, tzinfo=dt.timezone.utc)


class Guards(unittest.TestCase):
    def test_host_phai_khai_tuong_minh_va_khop(self):
        dsn = "postgresql://bo19_migrator:x@db.example.test:5432/bo19?sslmode=require"
        rpa.check_host(dsn, "db.example.test")
        for allow in ("", "khac.example.test", "db.example.test,x"):
            with self.assertRaises(rpa.ProbeRefused) as cm:
                rpa.check_host(dsn, allow)
            self.assertEqual(str(cm.exception), "PROBE_HOST_NOT_ALLOWED")

    def test_localhost_cung_khong_duoc_mien_khai_bao(self):
        with self.assertRaises(rpa.ProbeRefused):
            rpa.check_host("postgresql://u:x@localhost/db", "")

    def test_khong_xac_nhan_ngoai_le_thi_tu_choi_truoc_khi_noi(self):
        with self.assertRaises(rpa.ProbeRefused) as cm:
            rpa.seed("postgresql://u:x@nowhere.invalid/db", allow_host="nowhere.invalid", confirmed=False, count=3, hours=72)
        self.assertEqual(str(cm.exception), "PROBE_EXCEPTION_NOT_CONFIRMED")

    def test_gioi_han_so_tai_khoan_va_gio(self):
        for count, hours in ((0, 72), (4, 72), (3, 0), (3, 73)):
            with self.assertRaises(rpa.ProbeRefused) as cm:
                rpa.seed("postgresql://u:x@nowhere.invalid/db", allow_host="nowhere.invalid", confirmed=True, count=count, hours=hours)
            self.assertEqual(str(cm.exception), "PROBE_LIMITS", (count, hours))

    def test_ma_tai_khoan_la_do_va_id_co_dinh(self):
        self.assertEqual(rpa.codes(3), ["DO-0001", "DO-0002", "DO-0003"])
        self.assertEqual(rpa.employee_id("DO-0001"), rpa.employee_id("DO-0001"))
        self.assertNotEqual(rpa.employee_id("DO-0001"), rpa.employee_id("DO-0002"))


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class TrenPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)
        cls.host = conninfo_to_dict(cls.db.dsn()).get("host") or "localhost"

    @classmethod
    def tearDownClass(cls):
        cls.db.drop()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="bo19-probe-")
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.lines: list[str] = []
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("delete from chat_session where employee_id in (select id from employee where source like 'RENDER_PROBE_%')")
            c.execute("delete from employee_credential where employee_id in (select id from employee where source like 'RENDER_PROBE_%')")
            c.execute("delete from employee_role where employee_id in (select id from employee where source like 'RENDER_PROBE_%')")
            c.execute("delete from employee where source like 'RENDER_PROBE_%'")

    def dsn(self, role="bo19_migrator"):
        return self.db.dsn(role)

    def seed(self, **kw):
        args = dict(allow_host=self.host, confirmed=True, count=3, hours=72, out=self.out, now=T0, verifier=CHEAP, echo=self.lines.append)
        args.update(kw)
        return rpa.seed(self.dsn(), **args)

    def teardown(self, **kw):
        return rpa.teardown(self.dsn(), allow_host=self.host, out=self.out, now=T0 + dt.timedelta(hours=2), echo=self.lines.append, **kw)

    def query(self, sql, params=()):
        with self.db.connect("bo19_migrator") as c:
            return c.execute(sql, params).fetchall()

    def test_seed_tao_ba_tai_khoan_gia_mat_khau_khong_lo_ra_dau_ra(self):
        data = self.seed()
        self.assertEqual(data["accounts"], ["DO-0001", "DO-0002", "DO-0003"])
        rows = self.query("select employee_code, source, full_name, is_active from employee where source = 'RENDER_PROBE_FAKE' order by 1")
        self.assertEqual([r[0] for r in rows], ["DO-0001", "DO-0002", "DO-0003"])
        self.assertTrue(all("(GIẢ)" in r[2] and r[3] for r in rows))
        self.assertEqual(self.query("select count(*) from employee_credential c join employee e on e.id = c.employee_id where e.source = 'RENDER_PROBE_FAKE'"), [(3,)])
        self.assertEqual(self.query("select r.role_code from employee_role r join employee e on e.id = r.employee_id where e.source = 'RENDER_PROBE_FAKE'"), [("EMPLOYEE",)] * 3)
        passwords = (self.out / rpa.PASSWORDS).read_text(encoding="utf-8")
        secrets_ = [line.split("\t", 1)[1] for line in passwords.splitlines() if "\t" in line]
        self.assertEqual(len(secrets_), 3)
        output = "\n".join(self.lines)
        for secret in secrets_:
            self.assertNotIn(secret, output)  # mật khẩu không bao giờ in ra
        window = json.loads((self.out / rpa.WINDOW).read_text(encoding="utf-8"))
        self.assertEqual((window["seeded_at"], window["expires_at"], window["torn_down_at"]), ("2026-10-22T08:00:00+00:00", "2026-10-25T08:00:00+00:00", None))  # ghi giờ seed và hạn

    def test_khong_cap_quyen_le_nao(self):
        self.seed()
        self.assertEqual(self.query("select count(*) from employee_permission_grant g join employee e on e.id = g.employee_id where e.source = 'RENDER_PROBE_FAKE'"), [(0,)])

    def test_teardown_thu_hoi_va_xoa_khi_khong_co_dong_nao_tham_chieu(self):
        self.seed()
        summary = self.teardown()
        self.assertEqual((summary["credentials_deleted"], summary["roles_deleted"], summary["employees_deleted"], summary["employees_kept_revoked"]), (3, 3, 3, 0))
        self.assertEqual(self.query("select count(*) from employee where employee_code like 'DO-%%'"), [(0,)])
        self.assertFalse((self.out / rpa.PASSWORDS).exists())  # file mật khẩu bị xoá
        window = json.loads((self.out / rpa.WINDOW).read_text(encoding="utf-8"))
        self.assertEqual(window["torn_down_at"], "2026-10-22T10:00:00+00:00")  # ghi giờ xoá

    def test_teardown_khi_da_co_dong_tham_chieu_thi_thu_hoi_nhung_giu_employee(self):
        self.seed()
        eid = rpa.employee_id("DO-0001")
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("insert into chat_session (id, employee_id) values (%s, %s)", (uuid.uuid4(), eid))
        summary = self.teardown()
        self.assertEqual((summary["credentials_deleted"], summary["employees_deleted"], summary["employees_kept_revoked"]), (3, 2, 1))
        self.assertEqual(self.query("select source, is_active from employee where id = %s", (eid,)), [("RENDER_PROBE_REVOKED", False)])
        self.assertEqual(self.query("select count(*) from employee_credential where employee_id = %s", (eid,)), [(0,)])  # không đăng nhập lại được

    def test_seed_sau_han_ma_chua_thu_hoi_bi_tu_choi_nhung_teardown_van_chay(self):
        self.seed()
        with self.assertRaises(rpa.ProbeRefused) as cm:
            self.seed(now=T0 + dt.timedelta(hours=73))
        self.assertEqual(str(cm.exception), "PROBE_WINDOW_EXPIRED")
        self.assertEqual(self.teardown()["credentials_deleted"], 3)

    def test_role_khac_migrator_bi_tu_choi(self):
        with self.assertRaises(rpa.ProbeRefused) as cm:
            rpa.seed(self.dsn("bo19_app"), allow_host=self.host, confirmed=True, count=3, hours=72, out=self.out, now=T0, verifier=CHEAP, echo=self.lines.append)
        self.assertEqual(str(cm.exception), "PROBE_ROLE_NOT_MIGRATOR")

    def test_usage_dem_llm_usage_tu_luc_seed(self):
        self.seed()
        session = uuid.uuid4()
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("insert into chat_session (id, employee_id) values (%s, %s)", (session, rpa.employee_id("DO-0001")))
            for when in ("2026-10-22T07:59:00+00:00", "2026-10-22T08:01:00+00:00", "2026-10-22T09:00:00+00:00"):
                c.execute("insert into llm_usage (id, call_name, model_tier, chat_session_id, input_tokens, outcome, trace_id, created_at) values (%s, 'classify_intent', 'CHEAP', %s, 1, 'OK', %s, %s)",
                          (uuid.uuid4(), session, str(uuid.uuid4()), when))
        self.assertEqual(rpa.usage(self.dsn(), allow_host=self.host, out=self.out, echo=self.lines.append), 2)  # chỉ hai dòng sau giờ seed

    def test_chay_lai_seed_khong_nhan_doi_tai_khoan(self):
        self.seed()
        self.seed()
        self.assertEqual(self.query("select count(*) from employee where source = 'RENDER_PROBE_FAKE'"), [(3,)])


if __name__ == "__main__":
    unittest.main()
