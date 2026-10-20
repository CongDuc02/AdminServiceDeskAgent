"""`signing_route` (B9b1; mục Tool Registry của 03-agents.md; mục 5 của 08-hitl.md; ADR-040 mục 6; A-099) — PostgreSQL thật, DB RIÊNG của lớp test (người mang `document.sign` là thứ test điều khiển chính xác).

- chọn **mã nhân viên nhỏ nhất** trong E(`document.sign`, d); loại người thụ hưởng, người không hoạt động, cấp lẻ đã thu hồi hoặc chưa tới hạn; vai trò `SIGNER` cũng tính;
- E rỗng — kể cả khi chỉ còn người thụ hưởng mang `document.sign` — là `NoEligibleSigner`, `document` ở nguyên `APPROVED`, không bước nào mở;
- một giao dịch: `APPROVED → PENDING_SIGNATURE` cùng `signer_employee_id`, bước `SIGNATURE` giao cho người đó, `audit_event`; chạy lại là idempotent.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_signing_route -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest
import uuid

from bo19.persistence.pool import Pool
from bo19.tool_layer.kernel.permission import SystemActorRequired, system_context
from bo19.tool_layer.gate_ops.document_approve_content import document_approve_content
from bo19.tool_layer.tools import signing_route as sr
from tests import pg_support
from tests.gate_support import ctx_of, document_row, make_officer, make_pending_approval, make_template_version, rows, scalar


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class SigningRouteBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-signing", min_size=1, max_size=4)
        cls.pool.open()
        cls.version_id = make_template_version(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()
        cls.db.drop()

    def setUp(self):
        self.sys = system_context()
        self.tok = uuid.uuid4().hex[:6]  # mã nhân viên duy nhất toàn DB: thêm hậu tố, thứ tự theo tiền tố vẫn giữ
        # Mỗi test một tập người mang quyền riêng: gỡ quyền của test trước.
        with self.db.connect("bo19_migrator") as c:
            c.execute("update employee set is_active = false")
            c.execute("delete from employee_permission_grant")

    def emp(self, code: str, **kw):
        return self.db.make_employee(f"{code}_{self.tok}", **kw)

    def holder(self, code: str, **kw):
        eid, _ = self.emp(code, grants=("document.sign",), roles=("EMPLOYEE",), **kw)
        return eid

    def approved(self, beneficiary=None):
        officer = make_officer(self.db, self.pool)
        doc = make_pending_approval(self.db, self.pool, self.version_id, beneficiary=beneficiary)
        document_approve_content(self.pool, officer[1], document_id=doc.document_id, decision_id=uuid.uuid4(), expected_row_version=document_row(self.db, doc.document_id)["row_version"])
        return doc

    def route(self, doc):
        return sr.signing_route(self.pool, self.sys, document_id=doc.document_id)


class ChonNguoiKy(SigningRouteBase):
    def test_chon_ma_nho_nhat(self):
        b = self.holder("H-0B")
        a = self.holder("H-0A")
        self.holder("H-0C")
        doc = self.approved()
        r = self.route(doc)
        self.assertEqual((r.signer_employee_id, r.already), (a, False))
        self.assertNotEqual(r.signer_employee_id, b)

    def test_ket_qua_khong_phu_thuoc_thu_tu_tao(self):
        first = self.holder("H-9Z")
        second = self.holder("H-1A")
        doc = self.approved()
        self.assertEqual(self.route(doc).signer_employee_id, second)
        self.assertNotEqual(self.route(doc).signer_employee_id, first)

    def test_loai_nguoi_thu_huong_du_ma_nho_nhat(self):
        benef_id, benef_code = self.emp("H-00", grants=("document.sign",), roles=("EMPLOYEE",))
        other = self.holder("H-05")
        doc = self.approved(beneficiary=(benef_id, ctx_of(self.pool, benef_id)))
        self.assertEqual(self.route(doc).signer_employee_id, other)

    def test_loai_nguoi_khong_hoat_dong(self):
        self.holder("H-01", active=False)
        ok = self.holder("H-02")
        self.assertEqual(self.route(self.approved()).signer_employee_id, ok)

    def test_loai_cap_le_da_thu_hoi_va_chua_toi_han(self):
        self.emp("H-01", roles=("EMPLOYEE",), revoked_grants=("document.sign",))
        future, _ = self.emp("H-02", roles=("EMPLOYEE",))
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into employee_permission_grant (id, employee_id, permission_code, granted_at) values (%s, %s, 'document.sign', now() + interval '1 day')", (uuid.uuid4(), future))
        ok = self.holder("H-03")
        self.assertEqual(self.route(self.approved()).signer_employee_id, ok)

    def test_vai_tro_signer_cung_tinh(self):
        signer_role, _ = self.emp("H-01", roles=("SIGNER",))
        self.holder("H-02")
        self.assertEqual(self.route(self.approved()).signer_employee_id, signer_role)

    def test_vai_tro_khong_mang_document_sign_khong_tinh(self):
        self.emp("H-01", roles=("EMPLOYEE", "ADMIN_OFFICER"))  # ADMIN_OFFICER không mang document.sign (cấp lẻ)
        ok = self.holder("H-02")
        self.assertEqual(self.route(self.approved()).signer_employee_id, ok)


class KhongAiKy(SigningRouteBase):
    def assert_untouched(self, doc):
        self.assertEqual(document_row(self.db, doc.document_id)["status"], "APPROVED")
        self.assertIsNone(document_row(self.db, doc.document_id)["signer_employee_id"])
        self.assertEqual(scalar(self.db, "select count(*) from approval_step where document_id = %s and step_kind = 'SIGNATURE'", doc.document_id), 0)
        self.assertEqual(scalar(self.db, "select count(*) from audit_event where document_id = %s and action = 'document.signing_route'", doc.document_id), 0)

    def test_khong_ai_mang_document_sign(self):
        doc = self.approved()
        with self.assertRaises(sr.NoEligibleSigner):
            self.route(doc)
        self.assert_untouched(doc)

    def test_chi_con_nguoi_thu_huong_mang_quyen_van_khong_tu_chon(self):
        benef_id, _ = self.emp("H-00", grants=("document.sign",), roles=("EMPLOYEE",))
        doc = self.approved(beneficiary=(benef_id, ctx_of(self.pool, benef_id)))
        with self.assertRaises(sr.NoEligibleSigner):
            self.route(doc)  # đường tự duyệt là Sprint 3
        self.assert_untouched(doc)

    def test_ma_loi_la_no_eligible_signer(self):
        self.assertEqual(sr.NoEligibleSigner.code, "NO_ELIGIBLE_SIGNER")


class MotGiaoDich(SigningRouteBase):
    def test_ghi_trang_thai_nguoi_ky_buoc_va_audit(self):
        signer = self.holder("H-01")
        doc = self.approved()
        before = document_row(self.db, doc.document_id)
        r = self.route(doc)
        row = document_row(self.db, doc.document_id)
        self.assertEqual((row["status"], row["signer_employee_id"], row["row_version"]), ("PENDING_SIGNATURE", signer, before["row_version"] + 1))
        self.assertEqual(rows(self.db, "select id, status, assignee_employee_id, level, revision_round, self_approval_expected from approval_step where document_id = %s and step_kind = 'SIGNATURE'", doc.document_id),
                         [(r.approval_step_id, "OPEN", signer, 1, 0, False)])
        ev = rows(self.db, "select actor_kind, actor_employee_id, entity_type, request_id, payload from audit_event where document_id = %s and action = 'document.signing_route'", doc.document_id)
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0][0], ev[0][1], ev[0][2], ev[0][3]), ("SYSTEM", None, "document", doc.request_id))
        self.assertEqual(ev[0][4], {"status_from": "APPROVED", "status_to": "PENDING_SIGNATURE", "signer_employee_id": str(signer), "approval_step_id": str(r.approval_step_id), "candidates": 1})

    def test_chay_lai_la_idempotent(self):
        signer = self.holder("H-01")
        doc = self.approved()
        first = self.route(doc)
        self.holder("H-00")  # người mới có mã nhỏ hơn xuất hiện sau: người đã giao không đổi
        snap = (document_row(self.db, doc.document_id), scalar(self.db, "select count(*) from approval_step where document_id = %s", doc.document_id), scalar(self.db, "select count(*) from audit_event where document_id = %s", doc.document_id))
        again = self.route(doc)
        self.assertEqual((again.signer_employee_id, again.approval_step_id, again.already), (signer, first.approval_step_id, True))
        self.assertEqual((document_row(self.db, doc.document_id), scalar(self.db, "select count(*) from approval_step where document_id = %s", doc.document_id), scalar(self.db, "select count(*) from audit_event where document_id = %s", doc.document_id)), snap)

    def test_chua_duyet_noi_dung_thi_khong_dinh_tuyen(self):
        self.holder("H-01")
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        with self.assertRaises(sr.NotApproved):
            self.route(doc)
        self.assertEqual(document_row(self.db, doc.document_id)["status"], "PENDING_APPROVAL")

    def test_document_khong_ton_tai(self):
        with self.assertRaises(sr.DocumentNotFound):
            sr.signing_route(self.pool, self.sys, document_id=uuid.uuid4())

    def test_chi_tac_nhan_he_thong(self):
        self.holder("H-01")
        doc = self.approved()
        _, octx = make_officer(self.db, self.pool)
        with self.assertRaises(SystemActorRequired):
            sr.signing_route(self.pool, octx, document_id=doc.document_id)
        self.assertEqual(document_row(self.db, doc.document_id)["status"], "APPROVED")


if __name__ == "__main__":
    unittest.main()
