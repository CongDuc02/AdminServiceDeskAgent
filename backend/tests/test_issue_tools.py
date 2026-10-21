"""Ba tool của `finalize_issue` (B9b2, ADR-041) trên PostgreSQL thật, role `bo19_app` — không object storage, không `soffice` (bản `FINAL` là dòng `document_render` ghi thẳng bằng chủ bảng).

- **`issue_prepare`** (bước 0, chỉ đọc, TRƯỚC khi cấp số): lệnh phát hành phải thuộc đúng `document` và đúng loại; `document` ở `SIGNED` (không cần dấu) hay `SEALED`; bảng giá trị không còn lỗi; INV-01 —
  `approved_content_hash` tính lại phải bằng giá trị ghi ở cổng 1; người đã ký có tên và chức danh; đã `ISSUED` đúng với lệnh này thì `already`;
- **`document_mark_issued`** (giao dịch cuối): ghim `ISSUED`, `document → ISSUED` kèm bốn cột, `request → FULFILLED` chỉ khi không còn `document` nào của nó chưa qua `ISSUED`, `audit_event` mà tác nhân là NGƯỜI RA LỆNH;
  idempotent; dòng sổ, bản render, trạng thái sai thì không ghi gì;
- **`document_number_void_open`**: huỷ số `ASSIGNED` đang mở của `document` chưa `ISSUED`; không có số hay đã `ISSUED` thì không làm gì.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_issue_tools -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import datetime as dt
import hashlib
import unittest
import uuid

from bo19.persistence.pool import Pool
from bo19.tool_layer.kernel.permission import system_context
from bo19.tool_layer.numbering import document_number_assign, document_number_void_open
from bo19.tool_layer.tools import document_transition as dtn
from bo19.tool_layer.tools import issue_prepare as ip
from tests import pg_support
from tests.gate_support import FlowMixin, document_row, make_template_version, rows, scalar

UTC = dt.timezone.utc


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class IssueBase(FlowMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-issue-tools", min_size=1, max_size=4)
        cls.pool.open()
        cls.version_id = make_template_version(cls.db)
        with cls.db.connect("bo19_migrator", autocommit=True) as c:
            reg = c.execute("select document_register_id from request_type where code = 'WORK_CONFIRMATION'").fetchone()[0]
            c.execute("delete from document_register_format")  # data migration 0003 đã nạp khuôn số thật (M1.2); fixture dùng khuôn GIẢ của riêng nó
            c.execute("insert into document_register_format (id, document_register_id, series, format_pattern, symbol, seq_min_digits, effective_from) "
                      "values (%s, %s, 'TRIAL', 'TRIAL-{seq}/{year}/{symbol}', 'THU-NGHIEM', 3, timestamptz '2020-01-01 00:00:00+00')", (uuid.uuid4(), reg))

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()
        cls.db.drop()

    def setUp(self):
        self.sys = system_context()
        with self.db.connect("bo19_migrator") as c:
            c.execute("delete from employee_permission_grant")  # `signing_route` chọn trong cả DB của lớp

    # ---- dựng ----------------------------------------------------------------------------------------------------------------

    def issued_ready(self, **kw):
        """Một `document` đã qua mọi cổng và có lệnh phát hành. Trả (doc, signer, officer, issue_decision_id). `requires_seal=False`: dừng ở `SIGNED`."""
        version_id = kw.pop("version_id", self.version_id)
        make = (lambda: self.sealed(**kw)) if kw.get("requires_seal", True) else (lambda: self.pending_seal(**kw))
        saved, self.version_id = self.version_id, version_id
        try:
            doc, signer, officer = make()
        finally:
            self.version_id = saved
        decision = self.issue(doc, officer[1]).decision_record_id
        return doc, signer, officer, decision

    def order_for(self, doc, officer_id, *, level: int = 1) -> uuid.UUID:
        """Một `ISSUE_ORDERED` thêm bằng chủ bảng (kèm bước `ISSUE_ORDER` đã `DECIDED`) — cho ca lệnh thứ hai / document chưa tới chỗ phát hành."""
        step, decision = uuid.uuid4(), uuid.uuid4()
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into approval_step (id, document_id, step_kind, level, revision_round, status, closed_at) values (%s, %s, 'ISSUE_ORDER', %s, 0, 'DECIDED', now())", (step, doc.document_id, level))
            c.execute("insert into decision_record (id, kind, actor_employee_id, request_id, document_id, approval_step_id) values (%s, 'ISSUE_ORDERED', %s, %s, %s, %s)", (decision, officer_id, doc.request_id, doc.document_id, step))
        return decision

    def final_render(self, doc, *, kind: str = "FINAL", document_id=None) -> uuid.UUID:
        rid = uuid.uuid4()
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("insert into document_render (id, document_id, operating_mode, render_kind, input_hash, template_version_id, revision_round, docx_object_key, pdf_object_key, watermark_text) "
                      "values (%s, %s, 'NON_PRODUCTION', %s, %s, %s, 0, %s, %s, 'BẢN THỬ NGHIỆM')",
                      (rid, document_id or doc.document_id, kind, hashlib.sha256(rid.bytes).digest(), doc.version_id, f"renders/{rid}.docx", f"renders/{rid}.pdf"))
        return rid

    def assign(self, doc, decision):
        return document_number_assign(self.pool, self.sys, document_id=doc.document_id, issue_decision_id=decision)

    def prepare(self, doc, decision):
        return ip.issue_prepare(self.pool, self.sys, document_id=doc.document_id, issue_decision_id=decision)

    def mark(self, doc, decision, entry, render, date=dt.date(2026, 3, 9)):
        return dtn.document_mark_issued(self.pool, self.sys, document_id=doc.document_id, issue_decision_id=decision, entry_id=entry, render_id=render, issued_date=date)


class IssuePrepare(IssueBase):
    def test_san_sang_tra_bang_gia_tri_nguoi_ky_va_ten_bien_dien_sau_duyet(self):
        doc, signer, _, decision = self.issued_ready()
        with self.db.connect("bo19_migrator") as c:
            c.execute("update employee set full_name = %s, job_title = %s where id = %s", ("NGUYỄN VĂN KÝ (GIẢ)", "Trưởng phòng Hành chính (giả)", signer[0]))
        out = self.prepare(doc, decision)
        self.assertFalse(out.already)
        self.assertEqual((out.signer_full_name, out.signer_job_title), ("NGUYỄN VĂN KÝ (GIẢ)", "Trưởng phòng Hành chính (giả)"))
        self.assertEqual(out.fill_after_approval, {"document_number", "issued_date", "signer_user_id"})
        self.assertEqual(set(out.values), {"full_name", "department_name", "job_title", "recipient_org", "purpose_statement", "document_number", "issued_date", "signer_user_id"})
        self.assertIn("cấp khi phát hành", out.values["document_number"])  # dấu giữ chỗ của bản nháp — node thay bằng giá trị thật
        self.assertNotIn("NGUYỄN", repr(out))
        self.assertNotIn(out.values["purpose_statement"], repr(out))

    def test_lenh_phat_hanh_phai_thuoc_document_va_dung_loai(self):
        doc, _, officer, decision = self.issued_ready()
        other, _, _, other_decision = self.issued_ready()
        approved = scalar(self.db, "select id from decision_record where document_id = %s and kind = 'APPROVED'", doc.document_id)
        for bad in (uuid.uuid4(), other_decision, approved):
            with self.assertRaises(ip.NoIssueOrder, msg=str(bad)):
                self.prepare(doc, bad)
        self.assertFalse(self.prepare(doc, decision).already)

    def test_chi_san_sang_o_sealed_hoac_signed_khong_can_dau(self):
        doc, _, officer = self.pending_seal()  # PENDING_SEAL: chưa qua cổng 2
        decision = self.order_for(doc, officer[0])
        with self.assertRaises(ip.StaleDocument):
            self.prepare(doc, decision)
        free, _, officer2, decision2 = self.issued_ready(requires_seal=False)  # SIGNED không cần dấu
        self.assertEqual(self.prepare_status(free), "SIGNED")
        self.assertFalse(self.prepare(free, decision2).already)

    def test_signed_con_can_dau_la_trang_thai_thoang_qua_khong_phai_cho_phat_hanh(self):
        """`SIGNED` mà `requires_seal` còn đúng chỉ là khoảnh khắc giữa hai câu UPDATE của `document_sign` — không phát hành từ đó."""
        doc, _, officer = self.pending_seal()
        decision = self.order_for(doc, officer[0])
        with self.db.connect("bo19_migrator") as c:
            c.execute("update document set status = 'SIGNED' where id = %s", (doc.document_id,))
        with self.assertRaises(ip.StaleDocument):
            self.prepare(doc, decision)

    def test_phien_ban_template_da_go_van_phat_hanh_duoc(self):
        """Bản `FINAL` còn render được từ phiên bản `RETIRED` (ADR-015 chốt 3): văn bản đã duyệt bằng phiên bản đó không bị chặn chỉ vì template đã bị thay sau khi duyệt."""
        version = make_template_version(self.db)  # phiên bản riêng của test: gỡ phiên bản dùng chung của lớp sẽ làm hỏng các test sau
        doc, _, _, decision = self.issued_ready(version_id=version)
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("update template_version set status = 'RETIRED', retired_at = now() where id = %s", (version,))
        self.assertFalse(self.prepare(doc, decision).already)

    def prepare_status(self, doc) -> str:
        return document_row(self.db, doc.document_id)["status"]

    def test_hash_lech_la_content_hash_mismatch_truoc_khi_co_so(self):
        doc, _, _, decision = self.issued_ready()
        with self.db.connect("bo19_migrator") as c:
            c.execute("update document_free_content set body = body || ' (đã sửa sau khi duyệt)' where document_id = %s", (doc.document_id,))
        with self.assertRaises(ip.ContentHashMismatch):
            self.prepare(doc, decision)
        self.assertEqual(scalar(self.db, "select count(*) from document_register_entry where document_id = %s", doc.document_id), 0)  # đọc thôi — không tiêu số

    def test_hash_da_ghi_bi_sua_cung_lech(self):
        doc, _, _, decision = self.issued_ready()
        with self.db.connect("bo19_migrator") as c:
            c.execute("update document set approved_content_hash = decode(repeat('ab', 32), 'hex') where id = %s", (doc.document_id,))
        with self.assertRaises(ip.ContentHashMismatch):
            self.prepare(doc, decision)

    def test_bien_dien_sau_duyet_khong_vao_hash(self):
        """Hash không đổi dù bảng giá trị có dấu giữ chỗ khác — chỉ biến không điền-sau-duyệt được tính (INV-01)."""
        doc, _, _, decision = self.issued_ready()
        self.assertFalse(self.prepare(doc, decision).already)  # dấu giữ chỗ của bản nháp nằm trong `values` nhưng hash vẫn khớp

    def test_bang_gia_tri_con_loi_la_render_input_invalid(self):
        doc, _, _, decision = self.issued_ready()
        with self.db.connect("bo19_migrator") as c:
            c.execute("update document_free_content set body = '[điền sau]' where document_id = %s", (doc.document_id,))  # dấu giữ chỗ chung trong nội dung
        with self.assertRaises(ip.RenderInputInvalid) as cm:
            self.prepare(doc, decision)
        self.assertEqual(cm.exception.detail, "PLACEHOLDER_VALUE")  # lỗi bảng giá trị được báo TRƯỚC khi so hash

    def test_khong_co_nguoi_ky(self):
        doc, _, _, decision = self.issued_ready()
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("delete from decision_record where document_id = %s and kind = 'SIGNED'", (doc.document_id,))
        with self.assertRaises(ip.RenderInputInvalid) as cm:
            self.prepare(doc, decision)
        self.assertEqual(cm.exception.detail, "NO_SIGNER")

    def test_nguoi_ky_la_nguoi_co_quyet_dinh_signed_moi_nhat(self):
        doc, signer, _, decision = self.issued_ready()
        other, _ = self.db.make_employee(roles=("EMPLOYEE",))
        with self.db.connect("bo19_migrator") as c:
            c.execute("update employee set full_name = 'NGƯỜI KHÁC (GIẢ)' where id = %s", (other,))
            c.execute("update employee set full_name = 'NGƯỜI ĐÃ KÝ (GIẢ)' where id = %s", (signer[0],))
        out = self.prepare(doc, decision)
        self.assertEqual(out.signer_full_name, "NGƯỜI ĐÃ KÝ (GIẢ)")  # người đã ký, không phải người nào khác

    def test_da_issued_dung_lenh_la_already_lenh_khac_la_stale(self):
        doc, _, officer, decision = self.issued_ready()
        entry = self.assign(doc, decision)
        self.mark(doc, decision, entry.entry_id, self.final_render(doc))
        out = self.prepare(doc, decision)
        self.assertEqual((out.already, out.values), (True, {}))
        second = self.order_for(doc, officer[0], level=2)
        with self.assertRaises(ip.StaleDocument):
            self.prepare(doc, second)  # ISSUED bởi lệnh khác

    def test_document_khong_ton_tai(self):
        with self.assertRaises(ip.DocumentNotFound):
            ip.issue_prepare(self.pool, self.sys, document_id=uuid.uuid4(), issue_decision_id=uuid.uuid4())

    def test_chi_tac_nhan_he_thong(self):
        from bo19.tool_layer.kernel.permission import SystemActorRequired

        doc, _, officer, decision = self.issued_ready()
        with self.assertRaises(SystemActorRequired):
            ip.issue_prepare(self.pool, officer[1], document_id=doc.document_id, issue_decision_id=decision)


class MarkIssued(IssueBase):
    def test_ghim_issued_document_issued_request_fulfilled_audit_cua_nguoi_ra_lenh(self):
        doc, _, officer, decision = self.issued_ready()
        entry = self.assign(doc, decision)
        render = self.final_render(doc)
        before = document_row(self.db, doc.document_id)
        out = self.mark(doc, decision, entry.entry_id, render, dt.date(2026, 3, 9))
        self.assertEqual((out.document_id, out.already), (doc.document_id, False))
        row = document_row(self.db, doc.document_id)
        self.assertEqual((row["status"], row["issued_register_entry_id"], row["final_render_id"], row["issued_date"]), ("ISSUED", entry.entry_id, render, dt.date(2026, 3, 9)))
        self.assertIsNotNone(row["issued_at"])
        self.assertEqual(row["row_version"], before["row_version"] + 1)
        self.assertGreater(row["status_changed_at"], before["status_changed_at"])
        self.assertEqual(rows(self.db, "select pin_reason, decision_record_id from document_render_pin where render_id = %s", render), [("ISSUED", decision)])
        self.assertEqual(scalar(self.db, "select status from request where id = %s", doc.request_id), "FULFILLED")
        events = rows(self.db, "select actor_kind, actor_employee_id, decision_record_id, payload from audit_event where document_id = %s and action = 'document.issue_complete'", doc.document_id)
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0][0], events[0][1], events[0][2]), ("EMPLOYEE", officer[0], decision))  # người ra lệnh là tác nhân
        self.assertEqual(events[0][3]["executed_by"], "SYSTEM")
        self.assertEqual((events[0][3]["status_from"], events[0][3]["status_to"]), ("SEALED", "ISSUED"))
        self.assertNotIn(entry.formatted_number, str(events[0][3]))  # audit không mang chuỗi số

    def test_idempotent_lan_hai_khong_ghi_them(self):
        doc, _, _, decision = self.issued_ready()
        entry = self.assign(doc, decision)
        render = self.final_render(doc)
        self.mark(doc, decision, entry.entry_id, render)
        version = document_row(self.db, doc.document_id)["row_version"]
        out = self.mark(doc, decision, entry.entry_id, render)
        self.assertEqual(out.already, True)
        self.assertEqual(document_row(self.db, doc.document_id)["row_version"], version)
        self.assertEqual(scalar(self.db, "select count(*) from audit_event where document_id = %s and action = 'document.issue_complete'", doc.document_id), 1)
        self.assertEqual(scalar(self.db, "select count(*) from document_render_pin where render_id = %s", render), 1)

    def test_dong_so_khong_dung_thi_khong_ghi_gi(self):
        doc, _, _, decision = self.issued_ready()
        other, _, _, other_decision = self.issued_ready()
        entry, other_entry = self.assign(doc, decision), self.assign(other, other_decision)
        render = self.final_render(doc)
        before = document_row(self.db, doc.document_id)
        for bad in (uuid.uuid4(), other_entry.entry_id):  # không có; của document khác
            with self.assertRaises(dtn.StaleDocument, msg=str(bad)):
                self.mark(doc, decision, bad, render)
        document_number_void_open(self.pool, self.sys, document_id=doc.document_id, reason_code="TEST")
        with self.assertRaises(dtn.StaleDocument):
            self.mark(doc, decision, entry.entry_id, render)  # dòng sổ đã VOIDED
        self.assertEqual(document_row(self.db, doc.document_id), before)
        self.assertEqual(scalar(self.db, "select count(*) from document_render_pin where render_id = %s", render), 0)

    def test_ban_render_phai_la_final_cua_dung_document(self):
        doc, _, _, decision = self.issued_ready()
        other, _, _, _ = self.issued_ready()
        entry = self.assign(doc, decision)
        for bad in (uuid.uuid4(), self.final_render(doc, kind="DRAFT"), self.final_render(other)):
            with self.assertRaises(dtn.StaleDocument, msg=str(bad)):
                self.mark(doc, decision, entry.entry_id, bad)
        self.assertEqual(document_row(self.db, doc.document_id)["status"], "SEALED")

    def test_lenh_phai_la_cua_document(self):
        doc, _, _, decision = self.issued_ready()
        _, _, _, other_decision = self.issued_ready()
        entry = self.assign(doc, decision)
        with self.assertRaises(dtn.NoIssueOrder):
            self.mark(doc, other_decision, entry.entry_id, self.final_render(doc))

    def test_sai_trang_thai(self):
        doc, _, officer = self.pending_seal()
        decision = self.order_for(doc, officer[0])
        entry = self.assign(doc, decision)  # dòng sổ và bản FINAL đều HỢP LỆ: chỉ trạng thái `PENDING_SEAL` là sai
        with self.assertRaises(dtn.StaleDocument):
            self.mark(doc, decision, entry.entry_id, self.final_render(doc))
        self.assertEqual(document_row(self.db, doc.document_id)["status"], "PENDING_SEAL")

    def test_da_issued_voi_dong_so_khac_la_stale(self):
        doc, _, _, decision = self.issued_ready()
        entry = self.assign(doc, decision)
        self.mark(doc, decision, entry.entry_id, self.final_render(doc))
        with self.assertRaises(dtn.StaleDocument):
            self.mark(doc, decision, uuid.uuid4(), self.final_render(doc))

    def test_request_chua_fulfilled_khi_con_document_khac_chua_xong(self):
        doc, _, _, decision = self.issued_ready()
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("insert into document (id, request_id, template_version_id, status, operating_mode) values (%s, %s, %s, 'DRAFT', 'NON_PRODUCTION')", (uuid.uuid4(), doc.request_id, doc.version_id))
        entry = self.assign(doc, decision)
        self.mark(doc, decision, entry.entry_id, self.final_render(doc))
        self.assertEqual(document_row(self.db, doc.document_id)["status"], "ISSUED")
        self.assertEqual(scalar(self.db, "select status from request where id = %s", doc.request_id), "APPROVED")

    def test_signed_khong_can_dau_cung_issued(self):
        doc, _, _, decision = self.issued_ready(requires_seal=False)
        self.assertEqual(document_row(self.db, doc.document_id)["status"], "SIGNED")
        entry = self.assign(doc, decision)
        self.mark(doc, decision, entry.entry_id, self.final_render(doc))
        self.assertEqual(document_row(self.db, doc.document_id)["status"], "ISSUED")

    def test_chi_tac_nhan_he_thong(self):
        from bo19.tool_layer.kernel.permission import SystemActorRequired

        doc, _, officer, decision = self.issued_ready()
        with self.assertRaises(SystemActorRequired):
            dtn.document_mark_issued(self.pool, officer[1], document_id=doc.document_id, issue_decision_id=decision, entry_id=uuid.uuid4(), render_id=uuid.uuid4(), issued_date=dt.date(2026, 1, 1))


class VoidOpen(IssueBase):
    def test_huy_so_assigned_dang_mo_kem_ly_do_va_audit_canh_bao(self):
        doc, _, _, decision = self.issued_ready()
        entry = self.assign(doc, decision)
        got = document_number_void_open(self.pool, self.sys, document_id=doc.document_id, reason_code="PLACEHOLDER_REMAINS")
        self.assertEqual(got, entry.entry_id)
        self.assertEqual(rows(self.db, "select status, void_reason, voided_at is not null from document_register_entry where id = %s", entry.entry_id), [("VOIDED", "PLACEHOLDER_REMAINS", True)])
        ev = rows(self.db, "select severity, actor_kind, payload from audit_event where document_id = %s and action = 'document.number_void'", doc.document_id)
        self.assertEqual((len(ev), ev[0][0], ev[0][1], ev[0][2]["reason_code"]), (1, "WARNING", "SYSTEM", "PLACEHOLDER_REMAINS"))
        self.assertEqual(document_row(self.db, doc.document_id)["status"], "SEALED")  # document đứng yên
        # lần phát hành sau nhận số MỚI, số cũ không dùng lại (ADR-011)
        again = self.assign(doc, decision)
        self.assertEqual((again.created, again.seq), (True, entry.seq + 1))

    def test_khong_co_so_hoac_da_huy_thi_khong_lam_gi(self):
        doc, _, _, decision = self.issued_ready()
        self.assertIsNone(document_number_void_open(self.pool, self.sys, document_id=doc.document_id, reason_code="X"))
        self.assign(doc, decision)
        self.assertIsNotNone(document_number_void_open(self.pool, self.sys, document_id=doc.document_id, reason_code="X"))
        self.assertIsNone(document_number_void_open(self.pool, self.sys, document_id=doc.document_id, reason_code="X"))  # lần hai: không còn số ASSIGNED
        self.assertEqual(scalar(self.db, "select count(*) from audit_event where document_id = %s and action = 'document.number_void'", doc.document_id), 1)

    def test_document_da_issued_thi_khong_bao_gio_huy(self):
        doc, _, _, decision = self.issued_ready()
        entry = self.assign(doc, decision)
        self.mark(doc, decision, entry.entry_id, self.final_render(doc))
        self.assertIsNone(document_number_void_open(self.pool, self.sys, document_id=doc.document_id, reason_code="X"))
        self.assertEqual(scalar(self.db, "select status from document_register_entry where id = %s", entry.entry_id), "ASSIGNED")

    def test_chi_huy_so_cua_dung_document(self):
        doc, _, _, decision = self.issued_ready()
        other, _, _, other_decision = self.issued_ready()
        mine, theirs = self.assign(doc, decision), self.assign(other, other_decision)
        document_number_void_open(self.pool, self.sys, document_id=doc.document_id, reason_code="X")
        self.assertEqual(scalar(self.db, "select status from document_register_entry where id = %s", theirs.entry_id), "ASSIGNED")
        self.assertEqual(scalar(self.db, "select status from document_register_entry where id = %s", mine.entry_id), "VOIDED")

    def test_ma_ly_do_chi_mot_ma_va_tac_nhan_he_thong(self):
        from bo19.tool_layer.kernel.permission import SystemActorRequired

        doc, _, officer, _ = self.issued_ready()
        for bad in ("chữ thường", "CÓ DẤU CÁCH", "", "1ABC"):
            with self.assertRaises(ValueError, msg=bad):
                document_number_void_open(self.pool, self.sys, document_id=doc.document_id, reason_code=bad)
        with self.assertRaises(SystemActorRequired):
            document_number_void_open(self.pool, officer[1], document_id=doc.document_id, reason_code="X")
        from bo19.tool_layer.numbering import DocumentNotFound

        with self.assertRaises(DocumentNotFound):
            document_number_void_open(self.pool, self.sys, document_id=uuid.uuid4(), reason_code="X")


class KernelIssued(IssueBase):
    """Cạnh `→ ISSUED` của kernel (ADR-041 mục 6): `ck_document_issued_complete` đòi bốn cột trong cùng câu UPDATE — ba qua `set_values`, `issued_at` do kernel đặt."""

    def go(self, doc, **kw):
        from bo19.persistence.write import unit_of_work
        from bo19.tool_layer.kernel import transition as tr

        with self.pool.acquire() as conn, unit_of_work(conn):
            return tr.transition(conn, "document", doc.document_id, to="ISSUED", **kw)

    def test_thieu_hoac_thua_cot_bi_tu_choi_truoc_khi_dung_db(self):
        from bo19.tool_layer.kernel import transition as tr

        doc, _, _, decision = self.issued_ready()
        entry = self.assign(doc, decision)
        full = {"issued_register_entry_id": entry.entry_id, "final_render_id": self.final_render(doc), "issued_date": dt.date(2026, 3, 9)}
        before = document_row(self.db, doc.document_id)
        with self.assertRaises(tr.SetValuesIncomplete):
            self.go(doc)
        for missing in full:
            with self.assertRaises(tr.SetValuesIncomplete, msg=missing):
                self.go(doc, set_values={k: v for k, v in full.items() if k != missing})
        for extra in ("issued_at", "status", "approved_content_hash"):
            with self.assertRaises(tr.ExtraColumnNotAllowed, msg=extra):
                self.go(doc, set_values={**full, extra: dt.datetime.now(UTC)})  # `issued_at` do kernel đặt, không do người gọi
        self.assertEqual(document_row(self.db, doc.document_id), before)

    def test_di_duoc_va_kernel_dat_issued_at(self):
        doc, _, _, decision = self.issued_ready()
        entry = self.assign(doc, decision)
        full = {"issued_register_entry_id": entry.entry_id, "final_render_id": self.final_render(doc), "issued_date": dt.date(2026, 3, 9)}
        r = self.go(doc, expected_from="SEALED", set_values=full)
        row = document_row(self.db, doc.document_id)
        self.assertEqual((r.status, r.changed, row["status"]), ("ISSUED", True, "ISSUED"))
        self.assertIsNotNone(row["issued_at"])
        self.assertEqual((row["issued_register_entry_id"], row["issued_date"]), (entry.entry_id, dt.date(2026, 3, 9)))


if __name__ == "__main__":
    unittest.main()
