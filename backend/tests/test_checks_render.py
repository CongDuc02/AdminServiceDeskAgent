"""Bước kiểm khởi động #6 (`soffice` headless) và #7 (font của template) — B8b; mục Bước kiểm khởi động của 06-structure.md, ADR-015 chốt 3, ADR-036.

Điều được chứng minh, nói bằng hành vi:
- **#6:** trong image thật `soffice` chuyển được một `.docx` tối thiểu trong hạn; không có `soffice` / chuyển đổi hỏng / quá hạn / thiếu `fc-match` thì mỗi trường hợp một mã riêng (`STARTUP_06_*`) và **Chặn**;
- **#7:** tập font cần = `required_fonts` của mọi phiên bản `ACTIVE` HỢP mọi phiên bản mà một `document` chưa tới trạng thái kết thúc đang dùng (phiên bản `RETIRED` vẫn được tính nếu còn văn bản chờ `finalize_issue`); phiên bản
  `UPLOADED` không dùng và phiên bản `RETIRED` chỉ còn văn bản đã kết thúc không được tính; font thiếu → `STARTUP_07_FONT_MISSING` kèm tên họ ở log; ánh xạ "Times New Roman" hỏng (`fc-match` không ra Liberation Serif) cũng là thiếu;
  không có phiên bản nào là tập rỗng — đạt;
- ma trận: #6 và #7 chỉ cho `worker`, mức Chặn, và đã có trong registry (không còn `STARTUP_CHECK_PENDING`).

Cần BO19_TEST_PG_SUPERUSER_DSN (#7) và `soffice` (#6; image target `test`; CI đặt BO19_REQUIRE_SOFFICE=1).
Chạy từ backend/ với PYTHONPATH=src:  python -m unittest tests.test_checks_render -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest
import uuid
from pathlib import Path
from unittest import mock

from bo19.startup import checks_render as cr
from bo19.startup.model import MATRIX, Context, Entry, Level
from bo19.startup.registry import REGISTRY
from bo19.tool_layer.rendering import convert, fonts
from tests import pg_support
from tests.render_support import require_tool


def ctx(conn=None) -> Context:
    return Context(Entry.WORKER, None, {}, conn, Path("."))  # type: ignore[arg-type] — #6 và #7 không đọc `settings`


class Buoc6(unittest.TestCase):
    def test_soffice_that_chuyen_duoc_docx_toi_thieu(self):
        require_tool(self, "soffice")
        self.assertEqual(cr.step_06(ctx()).codes, ())

    def test_khong_co_soffice(self):
        with mock.patch.object(convert, "available", return_value=False):
            self.assertEqual(cr.step_06(ctx()).codes, ("STARTUP_06_SOFFICE_MISSING",))

    def test_chuyen_doi_hong(self):
        with mock.patch.object(convert, "available", return_value=True), mock.patch.object(fonts, "_run", return_value="Liberation Serif\n"), \
                mock.patch.object(convert, "convert_to_pdf", side_effect=convert.ConversionFailed):
            self.assertEqual(cr.step_06(ctx()).codes, ("STARTUP_06_CONVERT_FAILED",))

    def test_chuyen_doi_qua_han(self):
        with mock.patch.object(convert, "available", return_value=True), mock.patch.object(fonts, "_run", return_value="Liberation Serif\n"), \
                mock.patch.object(convert, "convert_to_pdf", side_effect=convert.ConversionTimeout):
            self.assertEqual(cr.step_06(ctx()).codes, ("STARTUP_06_CONVERT_TIMEOUT",))

    def test_thieu_cong_cu_font(self):
        with mock.patch.object(convert, "available", return_value=True), mock.patch.object(fonts, "_run", side_effect=fonts.FontToolMissing), \
                mock.patch.object(convert, "convert_to_pdf", side_effect=AssertionError("không được chuyển đổi khi thiếu fc-match")):
            self.assertEqual(cr.step_06(ctx()).codes, ("STARTUP_06_FONT_TOOL_MISSING",))

    def test_han_la_wv_25_va_duoc_truyen_vao(self):
        seen = {}
        with mock.patch.object(convert, "available", return_value=True), mock.patch.object(fonts, "_run", return_value="x\n"), \
                mock.patch.object(convert, "convert_to_pdf", side_effect=lambda data, **kw: seen.update(kw) or b"%PDF-"):
            cr.step_06(ctx())
        self.assertEqual(seen["timeout_s"], cr.wv.SOFFICE_STARTUP_CHECK_TIMEOUT_S)


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class Buoc7(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_tool(cls, "fc-match")
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)

    @classmethod
    def tearDownClass(cls):
        cls.db.drop()

    def setUp(self):
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            for table in ("document_render", "document", "template_variable", "template_version", "template"):
                c.execute(f"delete from {table}")
        self.conn = self.db.connect("bo19_app")
        self.addCleanup(self.conn.close)

    def version(self, status: str, fonts_: tuple[str, ...]) -> uuid.UUID:
        tid, vid = uuid.uuid4(), uuid.uuid4()
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("insert into template (id, code, request_type_code, name) values (%s, %s, 'WORK_CONFIRMATION', 'MẪU GIẢ')", (tid, f"G_{uuid.uuid4().hex[:8]}"))
            c.execute("insert into template_version (id, template_id, version_no, status, source_object_key, uploaded_by_employee_id, required_fonts, activated_at, retired_at) values (%s, %s, 1, %s, %s, %s, %s, %s, %s)",
                      (vid, tid, status, f"templates/{vid}", uuid.uuid4(), list(fonts_), None if status == "UPLOADED" else "2026-01-01T00:00:00+00", "2026-02-01T00:00:00+00" if status == "RETIRED" else None))
        return vid

    def document(self, version: uuid.UUID, status: str) -> None:
        issued = status in ("ISSUED", "REVOKED", "SUPERSEDED")
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            req = uuid.uuid4()
            c.execute("insert into request (id, request_type_code, status, created_by_employee_id, beneficiary_employee_id) values (%s, 'WORK_CONFIRMATION', 'DRAFT', %s, %s)", (req, uuid.uuid4(), uuid.uuid4()))
            if status in ("DRAFT", "PENDING_APPROVAL"):
                c.execute("insert into document (id, request_id, template_version_id, status, operating_mode, requires_seal) values (%s, %s, %s, %s, 'NON_PRODUCTION', false)", (uuid.uuid4(), req, version, status))
            else:
                tail = (uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()) if issued else (None, None, None, None)
                c.execute("insert into document (id, request_id, template_version_id, status, operating_mode, requires_seal, approved_content_hash, approved_decision_id, approved_render_id, signer_employee_id, "
                          "final_render_id, issued_register_entry_id, issued_date, issued_at) values (%s, %s, %s, %s, 'NON_PRODUCTION', false, %s, %s, %s, %s, %s, %s, %s, %s)",
                          (uuid.uuid4(), req, version, status, b"\x00" * 32, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), tail[0], tail[1], "2026-10-13" if issued else None, "2026-10-13T00:00:00+00" if issued else None))

    def run7(self):
        return cr.step_07(ctx(self.conn))

    def test_khong_co_phien_ban_nao_la_tap_rong_va_dat(self):
        self.assertEqual(self.run7().codes, ())

    def test_phien_ban_active_co_font_co_mat_va_anh_xa_dung(self):
        self.version("ACTIVE", ("Times New Roman", "Liberation Serif"))
        self.assertEqual(self.run7().codes, ())

    def test_font_thieu_la_chan_va_log_ten_ho(self):
        self.version("ACTIVE", ("Times New Roman", "Font Khong Co Bo19", "Arial Giả"))
        r = self.run7()
        self.assertEqual(r.codes, ("STARTUP_07_FONT_MISSING",))
        self.assertEqual(r.info, {"families": "Arial Giả,Font Khong Co Bo19"})

    def test_anh_xa_hong_la_thieu_du_van_co_mot_font_thay_the_gan_nhat(self):
        self.version("ACTIVE", ("Times New Roman",))
        with mock.patch.object(fonts, "_run", side_effect=lambda cmd: "DejaVu Serif\n" if cmd[0] == "fc-match" else "Liberation Serif\nDejaVu Serif\n"):
            self.assertEqual(self.run7().codes, ("STARTUP_07_FONT_MISSING",))

    def test_phien_ban_retired_con_van_ban_dang_cho_thi_van_duoc_tinh(self):
        v = self.version("RETIRED", ("Font Da Nghi Bo19",))
        self.assertEqual(self.run7().codes, ())  # chưa văn bản nào dùng
        self.document(v, "SIGNED")  # finalize_issue sẽ render bản cuối bằng đúng phiên bản này
        self.assertEqual(self.run7().codes, ("STARTUP_07_FONT_MISSING",))

    def test_van_ban_da_ket_thuc_khong_keo_phien_ban_vao(self):
        for status in ("ISSUED", "REVOKED", "SUPERSEDED"):
            v = self.version("RETIRED", ("Font Da Nghi Bo19",))
            self.document(v, status)
        self.assertEqual(self.run7().codes, ())

    def test_moi_trang_thai_chua_ket_thuc_deu_keo_phien_ban_vao(self):
        for status in ("DRAFT", "PENDING_APPROVAL", "SIGNED"):
            with self.db.connect(autocommit=True) as c:
                c.execute("set session_replication_role = replica")
                c.execute("delete from document")
                c.execute("delete from template_version")
            v = self.version("RETIRED", ("Font Da Nghi Bo19",))
            self.document(v, status)
            self.assertEqual(self.run7().codes, ("STARTUP_07_FONT_MISSING",), status)

    def test_phien_ban_uploaded_chua_dung_khong_tinh(self):
        self.version("UPLOADED", ("Font Chua Kich Hoat",))
        self.assertEqual(self.run7().codes, ())

    def test_thieu_fc_match_la_ma_rieng(self):
        self.version("ACTIVE", ("Times New Roman",))
        with mock.patch.object(fonts, "_run", side_effect=fonts.FontToolMissing):
            self.assertEqual(self.run7().codes, ("STARTUP_07_FONT_TOOL_MISSING",))

    def test_giao_dich_sach_sau_buoc(self):
        self.version("ACTIVE", ("Times New Roman",))
        self.run7()
        self.conn.rollback()  # bộ chạy làm việc này sau mỗi bước; bước không được để lỗi lại


class MaTran(unittest.TestCase):
    def test_6_va_7_chi_cho_worker_muc_chan_va_da_co_code(self):
        steps = {s.number: s for s in MATRIX}
        for n in ("6", "7"):
            self.assertEqual(steps[n].entries, frozenset({Entry.WORKER}), n)
            self.assertIs(steps[n].level, Level.BLOCK, n)
            self.assertIn(n, REGISTRY, n)
        self.assertTrue(steps["7"].needs_db)
        self.assertFalse(steps["6"].needs_db)

    def test_trang_thai_ket_thuc_khop_vong_doi_document(self):
        self.assertEqual(set(cr.TERMINAL_DOCUMENT_STATUSES), {"ISSUED", "REVOKED", "SUPERSEDED", "ARCHIVED", "REJECTED"})


if __name__ == "__main__":
    unittest.main()
