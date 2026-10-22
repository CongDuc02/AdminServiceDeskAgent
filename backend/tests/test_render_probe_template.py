"""`tools/render-probes/render_probe_template.py` — template GIẢ cho phép đo `soffice` trên Render (ngoại lệ cổng 2.7, PO 2026-10-21): nạp bằng `bo19_migrator` + object storage, retire ngay sau đo.

PostgreSQL thật đã migrate + SeaweedFS thật (bucket riêng mỗi test). Cần BO19_TEST_PG_SUPERUSER_DSN và BO19_TEST_S3_ENDPOINT.
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_render_probe_template -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import datetime as dt
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from docx import Document
from psycopg.conninfo import conninfo_to_dict

from bo19.api.auth.hasher import PasswordVerifier
from bo19.tool_layer.rendering.docx_fill import template_variables
from bo19.tool_layer.rendering.fonts import declared_families
from tests import pg_support, s3_support

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "render-probes"))
spec = importlib.util.spec_from_file_location("render_probe_template", REPO / "tools" / "render-probes" / "render_probe_template.py")
rpt = importlib.util.module_from_spec(spec)
sys.modules["render_probe_template"] = rpt
spec.loader.exec_module(rpt)
import render_probe_accounts as rpa  # noqa: E402  (cùng module mà `rpt` đã nạp)

CHEAP = PasswordVerifier(time_cost=1, memory_cost_kib=8, parallelism=1)
T0 = dt.datetime(2026, 10, 22, 8, 0, tzinfo=dt.timezone.utc)


class Docx(unittest.TestCase):
    def test_docx_gia_nhan_gia_chi_times_new_roman_va_du_bien(self):
        blob = rpt.template_docx()
        self.assertEqual(declared_families(blob), {"Times New Roman"})  # nằm trong bộ cổng 1.6
        self.assertEqual(template_variables(blob), {name for name, *_ in rpt.VARIABLES})
        text = "\n".join(p.text for p in Document(io.BytesIO(blob)).paragraphs)
        self.assertIn("(giả)", text)

    def test_khong_co_bien_noi_dung_tu_do_nen_job_render_khong_goi_llm(self):
        self.assertEqual({kind for _, kind, _, _ in rpt.VARIABLES}, {"DIRECT_SLOT", "SYSTEM"})

    def test_thieu_bien_moi_truong_object_storage_thi_tu_choi(self):
        with self.assertRaises(rpt.TemplateRefused) as cm:
            rpt.storage_from_env({"BO19_OBJECT_STORAGE_BUCKET": "x"})
        self.assertEqual(str(cm.exception), "TEMPLATE_STORAGE_ENV_MISSING")


class KiemTraStorage(unittest.TestCase):
    ENV = {"BO19_OBJECT_STORAGE_ENDPOINT_URL": "https://abc.r2.cloudflarestorage.com", "BO19_OBJECT_STORAGE_BUCKET": "bo19-render-dev", "BO19_OBJECT_STORAGE_REGION": "auto",
           "BO19_OBJECT_STORAGE_ACCESS_KEY_ID": "K" * 32, "BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY": "BI_MAT_KHONG_DUOC_IN" + "S" * 20}

    def storage(self, *, put_denied=False):
        from bo19.object_storage import StorageError

        class Fake:
            deleted: list = []

            def reachable(self): return True
            def list_keys(self, prefix): return iter([])
            def put_if_absent(self, key, data, **kw):
                if put_denied:
                    raise StorageError("ACCESS_DENIED")
            def delete(self, key): Fake.deleted.append(key)

        return Fake()

    def test_tat_ca_dat(self):
        out: list[str] = []
        self.assertEqual(rpt.check_storage(self.ENV, storage=self.storage(), echo=out.append), 0)
        text = "\n".join(out)
        self.assertIn("CHECK_PUT OK", text)
        self.assertIn("CHECK_RESULT OK", text)
        self.assertIn("bucket_is_render_dev=True", text)
        self.assertIn("endpoint_r2=True", text)

    def test_doc_dat_ghi_bi_tu_choi_noi_dung_la_token_khong_co_quyen_ghi_va_khong_lo_bi_mat(self):
        out: list[str] = []
        self.assertEqual(rpt.check_storage(self.ENV, storage=self.storage(put_denied=True), echo=out.append), 1)
        text = "\n".join(out)
        self.assertIn("CHECK_REACHABLE OK", text)
        self.assertIn("CHECK_LIST OK", text)
        self.assertIn("CHECK_PUT ACCESS_DENIED", text)
        self.assertIn("CHECK_RESULT FAILED", text)
        for secret in ("BI_MAT", "abc.r2", "KKKKKKKK"):
            self.assertNotIn(secret, text)

    def test_hinh_dang_bat_bucket_sai_va_khoang_trang_thua(self):
        env = {**self.ENV, "BO19_OBJECT_STORAGE_BUCKET": "bo19-dev ", "BO19_OBJECT_STORAGE_ENDPOINT_URL": "https://x.example.test"}
        out: list[str] = []
        rpt.check_storage(env, storage=self.storage(), echo=out.append)
        text = out[0]
        self.assertIn("bucket_is_render_dev=False", text)
        self.assertIn("endpoint_r2=False", text)
        self.assertIn("edge_whitespace=True", text)


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class TrenPostgresVaS3(s3_support.S3Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)
        cls.host = conninfo_to_dict(cls.db.dsn()).get("host") or "localhost"

    @classmethod
    def tearDownClass(cls):
        cls.db.drop()

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory(prefix="bo19-probe-tpl-")
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.lines: list[str] = []
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("update template_version set status = 'RETIRED', retired_at = now() where status = 'ACTIVE'")
        self.dsn = self.db.dsn("bo19_migrator")
        rpa.seed(self.dsn, allow_host=self.host, confirmed=True, count=1, hours=72, out=self.out, now=T0, verifier=CHEAP, echo=self.lines.append)

    def install(self, **kw):
        return rpt.install(self.dsn, self.storage, allow_host=self.host, out=self.out, now=T0 + dt.timedelta(minutes=5), echo=self.lines.append, **kw)

    def retire(self, **kw):
        return rpt.retire(self.dsn, allow_host=self.host, out=self.out, now=T0 + dt.timedelta(minutes=30), echo=self.lines.append, **kw)

    def query(self, sql, params=()):
        with self.db.connect("bo19_migrator") as c:
            return c.execute(sql, params).fetchall()

    def test_install_dung_template_active_bien_va_object(self):
        window = self.install()
        rows = self.query("select t.code, t.name, v.status, v.required_fonts, v.uploaded_by_employee_id from template t join template_version v on v.template_id = t.id where t.code = %s and v.status = 'ACTIVE'", (rpt.CODE,))
        self.assertEqual(rows, [(rpt.CODE, rpt.NAME, "ACTIVE", ["Times New Roman"], rpa.employee_id("DO-0001"))])
        self.assertIn("(giả)", rows[0][1])  # nhãn rõ
        variables = self.query("select variable_name, kind, fill_after_approval from template_variable where template_version_id = %s order by 1", (uuid.UUID(window["template_version_id"]),))
        self.assertEqual({v[0] for v in variables}, {name for name, *_ in rpt.VARIABLES})
        key = self.query("select source_object_key from template_version where id = %s", (uuid.UUID(window["template_version_id"]),))[0][0]
        self.assertEqual(self.query("select count(*) from stored_object_commit where object_key = %s", (key,)), [(1,)])
        self.assertTrue(self.raw_get(key).startswith(b"PK"))  # file .docx thật nằm trong bucket
        self.assertEqual(window["template_installed_at"], "2026-10-22T08:05:00+00:00")  # ghi giờ nạp
        self.assertIn("giờ Việt Nam 2026-10-22 15:05:00", "\n".join(self.lines))  # và in giờ Việt Nam để PO ghi vào roadmap

    def test_template_active_duoc_tim_thay_nhu_template_that(self):
        from bo19.persistence.pool import Pool
        from bo19.tool_layer.kernel.permission import system_context
        from bo19.tool_layer.tools import template_fetch
        self.install()
        pool = Pool(self.db.dsn("bo19_app"), application_name="bo19-test-probe-template", min_size=1, max_size=2)
        pool.open()
        self.addCleanup(pool.close)
        info = template_fetch.template_fetch(pool, system_context(), request_type="WORK_CONFIRMATION")  # đường tra cứu thật của ứng dụng
        self.assertEqual((info.status, {v.name for v in info.variables}), ("ACTIVE", {name for name, *_ in rpt.VARIABLES}))

    def test_khong_nap_hai_lan_va_khong_de_len_template_active_khac(self):
        self.install()
        with self.assertRaises(rpt.TemplateRefused) as cm:
            self.install()
        self.assertEqual(str(cm.exception), "TEMPLATE_ACTIVE_ALREADY_EXISTS")
        self.retire()
        # một template THẬT đang ACTIVE thì không nạp
        real = uuid.uuid4()
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("insert into template (id, code, request_type_code, name) values (%s, 'THAT_TEST', 'WORK_CONFIRMATION', 'mẫu thật của test')", (real,))
            c.execute("insert into template_version (id, template_id, version_no, status, source_object_key, uploaded_by_employee_id, required_fonts, activated_at) "
                      "select %s, %s, 1, 'ACTIVE', source_object_key, uploaded_by_employee_id, required_fonts, now() from template_version limit 1", (uuid.uuid4(), real))
        with self.assertRaises(rpt.TemplateRefused) as cm:
            self.install()
        self.assertEqual(str(cm.exception), "TEMPLATE_ACTIVE_ALREADY_EXISTS")

    def test_retire_chuyen_retired_va_ghi_gio_retire(self):
        self.install()
        window = self.retire()
        self.assertEqual(self.query("select status, retired_at is not null from template_version where id = %s", (uuid.UUID(window["template_version_id"]),)), [("RETIRED", True)])
        self.assertEqual(window["template_retired_at"], "2026-10-22T08:30:00+00:00")
        self.assertIn("PROBE_TEMPLATE_RETIRED rows=1", "\n".join(self.lines))
        self.assertEqual(self.query("select count(*) from template_version v join template t on t.id = v.template_id where t.code = %s and v.status = 'ACTIVE'", (rpt.CODE,)), [(0,)])

    def test_nap_lai_sau_retire_tang_so_phien_ban(self):
        first = self.install()
        n1 = self.query("select version_no from template_version where id = %s", (uuid.UUID(first["template_version_id"]),))[0][0]
        self.retire()
        second = self.install()
        self.assertEqual(self.query("select version_no, status from template_version where id = %s", (uuid.UUID(second["template_version_id"]),)), [(n1 + 1, "ACTIVE")])

    def test_khong_co_cua_so_hoac_da_thu_hoi_hoac_thieu_tai_khoan_thi_tu_choi(self):
        rpa.teardown(self.dsn, allow_host=self.host, out=self.out, now=T0 + dt.timedelta(minutes=2), echo=self.lines.append)
        with self.assertRaises(rpt.TemplateRefused) as cm:
            self.install()
        self.assertEqual(str(cm.exception), "TEMPLATE_NO_ACTIVE_WINDOW")
        (self.out / rpa.WINDOW).unlink()
        with self.assertRaises(rpt.TemplateRefused):
            self.install()

    def test_nothing_to_retire(self):
        with self.assertRaises(rpt.TemplateRefused) as cm:
            self.retire()
        self.assertEqual(str(cm.exception), "TEMPLATE_NOTHING_TO_RETIRE")


if __name__ == "__main__":
    unittest.main()
