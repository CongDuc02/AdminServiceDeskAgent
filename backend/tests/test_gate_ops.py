"""Bốn thao tác cổng trên `document` — `document_approve_content`, `document_sign`, `document_apply_seal`, `document_issue` (B9b1; mục Thao tác cổng của 03-agents.md; ADR-040) — PostgreSQL thật, role `bo19_app`.

Điều được chứng minh, nói bằng hành vi (mỗi quy tắc một test, để đột biến bỏ quy tắc nào cũng đỏ):
- **một giao dịch:** trạng thái, `decision_record`, bước, `audit_event`, job cùng commit hoặc cùng lăn (enqueue hỏng thì không còn gì);
- **permission** kiểm trước mọi thứ; **D-006** — người thụ hưởng luôn `SelfApprovalBlocked` ở Sprint 1; **trạng thái và `row_version`** lệch thì `StateConflict`, không ghi gì;
- **idempotency** theo id `decision_record` (ba điều kiện của mục 1.8 của 05-api.md); hai cán bộ bấm cùng lúc: một thắng;
- **`approved_content_hash`** (INV-01) khớp bản dựng tay độc lập, không gồm biến điền-sau-duyệt; bản nháp được ghim;
- **`document_sign` chỉ nhận người được giao**; `request IN_REVIEW → APPROVED`; `requires_seal` rẽ `PENDING_SEAL`;
- **`document_apply_seal`:** `seal_action` lấy loại dấu từ `document`, `copies_count`, `page_count` của `EDGE_STAMP`; **`document_issue`:** bước `ISSUE_ORDER` sinh ra đã `DECIDED`, không cấp số, mỗi `document` một lệnh.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_gate_ops -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import threading
import unittest
import uuid
from unittest import mock

from bo19.persistence.pool import Pool
from bo19.tool_layer.gate_ops import _gate as gate
from bo19.tool_layer.gate_ops.document_apply_seal import InvalidSealInput, document_apply_seal
from bo19.tool_layer.gate_ops.document_approve_content import NotApprovable, document_approve_content
from bo19.tool_layer.gate_ops.document_issue import document_issue
from bo19.tool_layer.gate_ops.document_sign import NotAssignedSigner, document_sign
from bo19.tool_layer.kernel.permission import PermissionDenied, system_context
from bo19.tool_layer.tools._common import NotOwnRequest
from bo19.tool_layer.tools.signing_route import signing_route
from tests import pg_support
from tests.doc_support import BODY_OK
from tests.gate_support import (FlowMixin, audit_actions, ctx_of, document_row, expected_hash, make_officer, make_pending_approval, make_template_version, rows, scalar)


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class GateBase(FlowMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.get_db()
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-gates", min_size=1, max_size=8)
        cls.pool.open()
        cls.version_id = make_template_version(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()

    def setUp(self):
        self.sys = system_context()

    def snapshot(self, doc) -> tuple:
        """Mọi thứ một thao tác cổng có thể ghi, để chứng minh 'không ghi gì'."""
        return (document_row(self.db, doc.document_id), scalar(self.db, "select count(*) from decision_record where document_id = %s", doc.document_id),
                rows(self.db, "select id, step_kind, status, assignee_employee_id from approval_step where document_id = %s order by id", doc.document_id),
                scalar(self.db, "select count(*) from audit_event where document_id = %s", doc.document_id), scalar(self.db, "select count(*) from job where subject_document_id = %s", doc.document_id),
                scalar(self.db, "select count(*) from document_render_pin where render_id = %s", doc.render_id), scalar(self.db, "select count(*) from seal_action where document_id = %s", doc.document_id),
                scalar(self.db, "select status from request where id = %s", doc.request_id))


def expected_values(db, doc) -> dict[str, str]:
    """Bảng giá trị của bản nháp, dựng độc lập: bốn slot `DIRECT_SLOT` đọc thẳng từ `request_slot` (kiểu chuỗi) cộng nội dung tự do của fixture."""
    out = {name: scalar(db, "select value #>> '{}' from request_slot where request_id = %s and slot_name = %s", doc.request_id, name)
           for name in ("full_name", "department_name", "job_title", "recipient_org")}
    out["purpose_statement"] = BODY_OK
    return out


class Duyet(GateBase):
    def test_duong_thang_mot_giao_dich_day_du(self):
        doc, (officer, ctx) = self.doc(), self.officer()
        key = uuid.uuid4()
        before = self.version(doc)
        r = self.approve(doc, ctx, key)
        self.assertEqual((r.decision_record_id, r.replayed), (key, False))
        row = document_row(self.db, doc.document_id)
        self.assertEqual((row["status"], row["row_version"], row["approved_decision_id"], row["approved_render_id"]), ("APPROVED", before + 1, key, doc.render_id))
        self.assertEqual(rows(self.db, "select kind, actor_employee_id, request_id, document_id, change_scope from decision_record where id = %s", key), [("APPROVED", officer, doc.request_id, doc.document_id, None)])
        step = rows(self.db, "select id, status, closed_at is not null, self_approved from approval_step where document_id = %s and step_kind = 'CONTENT_REVIEW'", doc.document_id)
        self.assertEqual([(s[1], s[2], s[3]) for s in step], [("DECIDED", True, False)])
        self.assertEqual(scalar(self.db, "select approval_step_id from decision_record where id = %s", key), step[0][0])
        self.assertEqual(scalar(self.db, "select status from request where id = %s", doc.request_id), "IN_REVIEW")  # approve-content không đổi trạng thái request
        self.assertEqual(rows(self.db, "select pin_reason, decision_record_id from document_render_pin where render_id = %s", doc.render_id), [("APPROVED_CONTENT", key)])

    def test_hash_khop_ban_dung_tay_va_khong_gom_bien_dien_sau_duyet(self):
        doc, (_, ctx) = self.doc(), self.officer()
        self.approve(doc, ctx)
        row = document_row(self.db, doc.document_id)
        values = expected_values(self.db, doc)
        self.assertEqual(set(values), {"full_name", "department_name", "job_title", "recipient_org", "purpose_statement"})  # không document_number, issued_date, signer_user_id
        self.assertEqual(bytes(row["approved_content_hash"]), expected_hash(self.version_id, "NON_PRODUCTION", values))

    def test_audit_job_va_payload_chi_mang_id(self):
        doc, (_, ctx) = self.doc(), self.officer()
        key = uuid.uuid4()
        self.approve(doc, ctx, key)
        ev = rows(self.db, "select actor_kind, action, entity_type, request_id, decision_record_id from audit_event where decision_record_id = %s", key)
        self.assertEqual(ev, [("EMPLOYEE", "document.approve_content", "document", doc.request_id, key)])
        job = rows(self.db, "select job_type, status, subject_document_id, payload, dedupe_key from job where subject_document_id = %s and job_type = 'resume_document_graph'", doc.document_id)
        self.assertEqual(len(job), 1)
        self.assertEqual((job[0][0], job[0][1], job[0][2], job[0][4]), ("resume_document_graph", "QUEUED", doc.document_id, str(key)))
        self.assertEqual(job[0][3], {"document_id": str(doc.document_id), "decision_record_id": str(key)})
        blob = repr(rows(self.db, "select payload from audit_event where document_id = %s", doc.document_id))
        self.assertNotIn(BODY_OK, blob)

    def test_thieu_permission_khong_ghi_gi(self):
        doc = self.doc()
        for roles in (("EMPLOYEE",), ()):
            _, ctx = self.officer(roles=roles)
            before = self.snapshot(doc)
            with self.assertRaises(PermissionDenied) as cm:
                self.approve(doc, ctx)
            self.assertEqual(cm.exception.detail, "document.approve_content")
            self.assertEqual(self.snapshot(doc), before)

    def test_tac_nhan_he_thong_khong_duoc(self):
        doc = self.doc()
        with self.assertRaises(NotOwnRequest):  # `actor_id` ném trước cả `require`: hệ thống không phải người thật
            document_approve_content(self.pool, self.sys, document_id=doc.document_id, decision_id=uuid.uuid4(), expected_row_version=self.version(doc))
        self.assertEqual(self.status(doc), "PENDING_APPROVAL")

    def test_nguoi_thu_huong_bi_chan_d006(self):
        officer, ctx = self.officer()
        doc = self.doc(beneficiary=(officer, ctx))  # người duyệt chính là người thụ hưởng
        other = self.officer()  # còn người khác mang quyền: vẫn chặn
        before = self.snapshot(doc)
        with self.assertRaises(gate.SelfApprovalBlocked):
            self.approve(doc, ctx)
        self.assertEqual(self.snapshot(doc), before)
        self.assertEqual(self.approve(doc, other[1]).replayed, False)  # người khác duyệt được

    def test_row_version_lech_va_trang_thai_lech_la_state_conflict(self):
        doc, (_, ctx) = self.doc(), self.officer()
        before = self.snapshot(doc)
        with self.assertRaises(gate.StateConflict) as cm:
            self.approve(doc, ctx, version=self.version(doc) + 1)
        self.assertEqual(cm.exception.current_status, "PENDING_APPROVAL")
        self.assertEqual(self.snapshot(doc), before)
        self.approve(doc, ctx)
        after = self.snapshot(doc)
        with self.assertRaises(gate.StateConflict) as cm:
            self.approve(doc, ctx, key=uuid.uuid4())  # đã APPROVED: khoá khác
        self.assertEqual(cm.exception.current_status, "APPROVED")
        self.assertEqual(self.snapshot(doc), after)

    def test_document_khong_ton_tai(self):
        _, ctx = self.officer()
        with self.assertRaises(gate.DocumentNotFound):
            document_approve_content(self.pool, ctx, document_id=uuid.uuid4(), decision_id=uuid.uuid4(), expected_row_version=1)

    def test_lap_lai_cung_khoa_khong_ghi_them_gi(self):
        doc, (_, ctx) = self.doc(), self.officer()
        key = uuid.uuid4()
        first = self.approve(doc, ctx, key)
        snap = self.snapshot(doc)
        again = self.approve(doc, ctx, key, version=999)  # lặp lại hợp lệ không kiểm row_version: trạng thái đã đổi là đương nhiên
        self.assertEqual((again.decision_record_id, again.replayed, again.created_at), (key, True, first.created_at))
        self.assertEqual(self.snapshot(doc), snap)

    def test_trung_khoa_lech_nguoi_doi_tuong_hay_loai_la_conflict(self):
        doc, (_, ctx) = self.doc(), self.officer()
        key = uuid.uuid4()
        self.approve(doc, ctx, key)
        _, other_ctx = self.officer()
        with self.assertRaises(gate.DecisionIdConflict):  # khác người
            self.approve(doc, other_ctx, key)
        other_doc = self.doc()
        with self.assertRaises(gate.DecisionIdConflict):  # khác document
            self.approve(other_doc, ctx, key)
        self.assertEqual(self.status(other_doc), "PENDING_APPROVAL")
        x_id, x_ctx = self.officer(signer=True, code="ZZ" + uuid.uuid4().hex[:8])  # mã sắp cuối: không bao giờ được `signing_route` chọn
        key2 = uuid.uuid4()
        self.approve(self.doc(), x_ctx, key2)
        doc2, _, _ = self.pending_signature()
        before = self.snapshot(doc2)
        with self.assertRaises(gate.DecisionIdConflict):  # cùng người, khác loại: id của một quyết định APPROVED dùng cho thao tác ký
            self.sign(doc2, x_ctx, key2)
        self.assertEqual(self.snapshot(doc2), before)

    def test_trung_khoa_cung_nguoi_cung_document_nhung_khac_loai_thao_tac(self):
        """Cùng người, cùng `document`, khác loại: id của quyết định APPROVED không dùng lại được cho thao tác phát hành."""
        doc, (_, octx) = self.doc(), self.officer()
        key = uuid.uuid4()
        self.approve(doc, octx, key)
        before = self.snapshot(doc)
        with self.assertRaises(gate.DecisionIdConflict):
            self.issue(doc, octx, key)
        with self.assertRaises(gate.DecisionIdConflict):
            self.seal(doc, octx, key)
        self.assertEqual(self.snapshot(doc), before)

    def test_khong_co_ban_nhap_hien_hanh_thi_khong_duyet(self):
        doc, (_, ctx) = self.doc(), self.officer()
        with self.db.connect("bo19_migrator") as c:
            c.execute("update document set current_draft_render_id = null where id = %s", (doc.document_id,))
        before = self.snapshot(doc)
        with self.assertRaises(NotApprovable):
            self.approve(doc, ctx)
        self.assertEqual(self.snapshot(doc), before)

    def test_hai_can_bo_bam_cung_luc_mot_thang_mot_state_conflict(self):
        doc = self.doc()
        a, b = self.officer(), self.officer()
        barrier = threading.Barrier(2)
        out: list = []
        v0 = self.version(doc)

        def go(ctx):
            barrier.wait()
            try:
                out.append(self.approve(doc, ctx, version=v0))
            except Exception as e:  # noqa: BLE001 — thu kết quả của từng luồng
                out.append(e)

        threads = [threading.Thread(target=go, args=(c[1],)) for c in (a, b)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        wins = [r for r in out if isinstance(r, gate.GateResult)]
        losses = [r for r in out if isinstance(r, gate.StateConflict)]
        self.assertEqual((len(wins), len(losses)), (1, 1), out)
        self.assertEqual(scalar(self.db, "select count(*) from decision_record where document_id = %s and kind = 'APPROVED'", doc.document_id), 1)
        self.assertEqual(scalar(self.db, "select count(*) from job where subject_document_id = %s", doc.document_id), 1)

    def test_enqueue_hong_thi_khong_con_gi(self):
        doc, (_, ctx) = self.doc(), self.officer()
        before = self.snapshot(doc)
        with mock.patch.object(gate, "enqueue", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.approve(doc, ctx)
        self.assertEqual(self.snapshot(doc), before)  # trạng thái, quyết định, bước, ghim, audit: tất cả lăn lại
        self.assertEqual(self.approve(doc, ctx).replayed, False)  # và duyệt lại được

    def test_thieu_noi_dung_tu_do_thi_khong_duyet(self):
        doc, (_, ctx) = self.doc(), self.officer()
        with self.db.connect("bo19_migrator") as c:
            c.execute("delete from document_free_content where document_id = %s", (doc.document_id,))
        before = self.snapshot(doc)
        with self.assertRaises(NotApprovable):
            self.approve(doc, ctx)
        self.assertEqual(self.snapshot(doc), before)

    def test_phien_ban_template_bi_go_sau_khi_render_van_duyet_duoc(self):
        """Người duyệt thấy đúng bản nháp đã render từ phiên bản đã ghim; phiên bản bị gỡ sau đó không chặn (chỉ `TEMPLATE_NOT_ACTIVE_AT_RENDER`, mục 6.4.2 của 03-agents.md)."""
        version = make_template_version(self.db)
        doc, (_, ctx) = make_pending_approval(self.db, self.pool, version), self.officer()
        with self.db.connect("bo19_migrator") as c:
            c.execute("update template_version set status = 'RETIRED', retired_at = now() where id = %s", (version,))
        self.approve(doc, ctx)
        self.assertEqual(self.status(doc), "APPROVED")
        self.assertEqual(bytes(document_row(self.db, doc.document_id)["approved_content_hash"]), expected_hash(version, "NON_PRODUCTION", expected_values(self.db, doc)))


class Ky(GateBase):
    def test_duong_thang_co_dau_di_pending_seal(self):
        doc, (signer, sctx), _ = self.pending_signature()
        key = uuid.uuid4()
        before = self.version(doc)
        r = self.sign(doc, sctx, key)
        self.assertEqual((r.decision_record_id, r.replayed), (key, False))
        row = document_row(self.db, doc.document_id)
        self.assertEqual((row["status"], row["signer_employee_id"], row["row_version"] > before), ("PENDING_SEAL", signer, True))
        self.assertEqual(scalar(self.db, "select status from request where id = %s", doc.request_id), "APPROVED")  # APPROVED nghĩa là đã ký (AUD-01)
        steps = rows(self.db, "select step_kind, status, assignee_employee_id from approval_step where document_id = %s order by opened_at, id", doc.document_id)
        self.assertEqual(steps, [("CONTENT_REVIEW", "DECIDED", None), ("SIGNATURE", "DECIDED", signer), ("SEAL", "OPEN", None)])
        self.assertEqual(rows(self.db, "select kind, actor_employee_id from decision_record where id = %s", key), [("SIGNED", signer)])
        self.assertEqual(scalar(self.db, "select count(*) from job where subject_document_id = %s and job_type = 'resume_document_graph'", doc.document_id), 2)  # một cho duyệt, một cho ký

    def test_khong_can_dau_dung_o_signed(self):
        doc, (_, sctx), _ = self.pending_signature(requires_seal=False)
        self.sign(doc, sctx)
        self.assertEqual(self.status(doc), "SIGNED")
        self.assertEqual(scalar(self.db, "select count(*) from approval_step where document_id = %s and step_kind = 'SEAL'", doc.document_id), 0)
        self.assertEqual(scalar(self.db, "select status from request where id = %s", doc.request_id), "APPROVED")

    def test_chi_nhan_nguoi_duoc_giao_nguoi_khac_mang_document_sign_bi_tu_choi(self):
        doc, _, _ = self.pending_signature()
        _, other_ctx = self.officer(signer=True, code="ZZ" + uuid.uuid4().hex[:8])  # cũng mang document.sign nhưng không được giao (mã sắp cuối)
        before = self.snapshot(doc)
        with self.assertRaises(NotAssignedSigner) as cm:
            self.sign(doc, other_ctx)
        self.assertEqual(cm.exception.detail, "assignee")
        self.assertIsInstance(cm.exception, PermissionDenied)
        self.assertEqual(self.snapshot(doc), before)

    def test_thieu_permission_document_sign(self):
        doc, _, (_, octx) = self.pending_signature()  # cán bộ ADMIN_OFFICER thường không mang document.sign (cấp lẻ)
        before = self.snapshot(doc)
        with self.assertRaises(PermissionDenied) as cm:
            self.sign(doc, octx)
        self.assertEqual(cm.exception.detail, "document.sign")
        self.assertEqual(self.snapshot(doc), before)

    def test_nguoi_thu_huong_duoc_giao_ky_van_bi_chan(self):
        """`signing_route` không giao cho người thụ hưởng; nếu dữ liệu vẫn có (sửa tay) thì cổng chặn D-006, không tin `signing_route`."""
        officer, ctx = self.officer(signer=True)
        doc = self.doc(beneficiary=(officer, ctx))
        other = self.officer()
        self.approve(doc, other[1])
        with self.db.connect("bo19_migrator") as c:
            c.execute("update document set status = 'PENDING_SIGNATURE', signer_employee_id = %s where id = %s", (officer, doc.document_id))
            c.execute("insert into approval_step (id, document_id, step_kind, assignee_employee_id) values (%s, %s, 'SIGNATURE', %s)", (uuid.uuid4(), doc.document_id, officer))
        before = self.snapshot(doc)
        with self.assertRaises(gate.SelfApprovalBlocked):
            self.sign(doc, ctx)
        self.assertEqual(self.snapshot(doc), before)

    def test_trang_thai_va_row_version(self):
        doc, (_, sctx), _ = self.pending_signature()
        before = self.snapshot(doc)
        with self.assertRaises(gate.StateConflict) as cm:
            self.sign(doc, sctx, version=self.version(doc) + 5)
        self.assertEqual(cm.exception.current_status, "PENDING_SIGNATURE")
        self.assertEqual(self.snapshot(doc), before)
        doc2 = self.doc()  # còn PENDING_APPROVAL: chưa tới bước ký
        with self.assertRaises(gate.StateConflict) as cm:
            self.sign(doc2, sctx)
        self.assertEqual(cm.exception.current_status, "PENDING_APPROVAL")

    def test_lap_lai_va_trung_khoa(self):
        doc, (_, sctx), _ = self.pending_signature()
        key = uuid.uuid4()
        first = self.sign(doc, sctx, key)
        snap = self.snapshot(doc)
        again = self.sign(doc, sctx, key, version=1)
        self.assertEqual((again.replayed, again.created_at), (True, first.created_at))
        self.assertEqual(self.snapshot(doc), snap)
        _, other = self.officer(signer=True, code="ZZ" + uuid.uuid4().hex[:8])
        with self.assertRaises(gate.DecisionIdConflict):
            self.sign(doc, other, key)

    def test_enqueue_hong_thi_khong_con_gi(self):
        doc, (_, sctx), _ = self.pending_signature()
        before = self.snapshot(doc)
        with mock.patch.object(gate, "enqueue", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.sign(doc, sctx)
        self.assertEqual(self.snapshot(doc), before)


class DongDau(GateBase):
    def test_duong_thang(self):
        doc, _, (officer, octx) = self.pending_seal()
        key = uuid.uuid4()
        r = self.seal(doc, octx, key, copies=3)
        self.assertEqual((r.decision_record_id, r.replayed), (key, False))
        self.assertEqual(self.status(doc), "SEALED")
        self.assertEqual(rows(self.db, "select seal_type, operating_mode, copies_count, page_count, decision_record_id from seal_action where document_id = %s", doc.document_id),
                         [("ORGANIZATION_ROUND", "NON_PRODUCTION", 3, None, key)])
        self.assertEqual(rows(self.db, "select kind, actor_employee_id from decision_record where id = %s", key), [("SEALED", officer)])
        self.assertEqual(scalar(self.db, "select status from approval_step where document_id = %s and step_kind = 'SEAL'", doc.document_id), "DECIDED")
        self.assertIn("document.apply_seal", audit_actions(self.db, doc.document_id))
        self.assertEqual(scalar(self.db, "select count(*) from job where subject_document_id = %s and job_type = 'resume_document_graph'", doc.document_id), 3)

    def test_loai_dau_lay_tu_document(self):
        doc, _, (_, octx) = self.pending_seal(seal_type="TITLE_STAMP")
        self.seal(doc, octx)
        self.assertEqual(scalar(self.db, "select seal_type from seal_action where document_id = %s", doc.document_id), "TITLE_STAMP")

    def test_edge_stamp_can_page_count_tu_hai(self):
        doc, _, (_, octx) = self.pending_seal(seal_type="EDGE_STAMP")
        before = self.snapshot(doc)
        for pages, rule in ((None, "REQUIRED"), (1, "OUT_OF_RANGE")):
            with self.assertRaises(InvalidSealInput) as cm:
                self.seal(doc, octx, pages=pages)
            self.assertEqual((cm.exception.field, cm.exception.rule), ("page_count", rule))
        self.assertEqual(self.snapshot(doc), before)
        self.seal(doc, octx, pages=2)
        self.assertEqual(scalar(self.db, "select page_count from seal_action where document_id = %s", doc.document_id), 2)

    def test_so_ban_toi_thieu_mot(self):
        doc, _, (_, octx) = self.pending_seal()
        with self.assertRaises(InvalidSealInput) as cm:
            self.seal(doc, octx, copies=0)
        self.assertEqual((cm.exception.field, cm.exception.rule), ("copies_count", "OUT_OF_RANGE"))
        self.assertEqual(self.status(doc), "PENDING_SEAL")

    def test_thieu_permission_va_trang_thai(self):
        doc, _, (_, octx) = self.pending_seal()
        before = self.snapshot(doc)
        with self.assertRaises(PermissionDenied) as cm:
            self.seal(doc, self.officer(roles=("EMPLOYEE",))[1])
        self.assertEqual(cm.exception.detail, "document.apply_seal")
        with self.assertRaises(gate.StateConflict) as cm:
            self.seal(doc, octx, version=self.version(doc) + 1)
        self.assertEqual(cm.exception.current_status, "PENDING_SEAL")
        self.assertEqual(self.snapshot(doc), before)

    def test_nguoi_thu_huong_bi_chan_o_cong_hai(self):
        officer, ctx = self.officer()
        doc, _, _ = self.pending_seal(beneficiary=(officer, ctx))  # người thụ hưởng mang document.apply_seal (ADMIN_OFFICER)
        before = self.snapshot(doc)
        with self.assertRaises(gate.SelfApprovalBlocked):
            self.seal(doc, ctx)
        self.assertEqual(self.snapshot(doc), before)
        self.seal(doc, self.officer()[1])  # người khác đóng dấu được

    def test_lap_lai_khong_ghi_them_seal_action(self):
        doc, _, (_, octx) = self.pending_seal()
        key = uuid.uuid4()
        self.seal(doc, octx, key)
        snap = self.snapshot(doc)
        self.assertEqual(self.seal(doc, octx, key, copies=9).replayed, True)
        self.assertEqual(self.snapshot(doc), snap)

    def test_enqueue_hong_thi_khong_con_seal_action(self):
        doc, _, (_, octx) = self.pending_seal()
        before = self.snapshot(doc)
        with mock.patch.object(gate, "enqueue", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.seal(doc, octx)
        self.assertEqual(self.snapshot(doc), before)


class PhatHanh(GateBase):
    def test_tu_sealed_ghi_lenh_khong_cap_so_khong_doi_trang_thai(self):
        doc, _, (officer, octx) = self.sealed()
        key = uuid.uuid4()
        before = document_row(self.db, doc.document_id)
        r = self.issue(doc, octx, key)
        self.assertEqual((r.decision_record_id, r.replayed), (key, False))
        after = document_row(self.db, doc.document_id)
        self.assertEqual((after["status"], after["row_version"], after["issued_register_entry_id"], after["issued_at"]), ("SEALED", before["row_version"], None, None))
        self.assertEqual(scalar(self.db, "select count(*) from document_register_entry where document_id = %s", doc.document_id), 0)  # không có số nào
        step = rows(self.db, "select step_kind, status, closed_at is not null, self_approved from approval_step where id = (select approval_step_id from decision_record where id = %s)", key)
        self.assertEqual(step, [("ISSUE_ORDER", "DECIDED", True, False)])  # sinh ra đã DECIDED
        self.assertEqual(rows(self.db, "select kind, actor_employee_id from decision_record where id = %s", key), [("ISSUE_ORDERED", officer)])
        job = rows(self.db, "select status, subject_document_id, payload, dedupe_key from job where job_type = 'finalize_issue' and subject_document_id = %s", doc.document_id)
        self.assertEqual(job, [("QUEUED", doc.document_id, {"document_id": str(doc.document_id), "decision_record_id": str(key)}, str(key))])
        self.assertIn("document.issue", audit_actions(self.db, doc.document_id))

    def test_tu_signed_khong_can_dau(self):
        doc, (_, sctx), (_, octx) = self.pending_signature(requires_seal=False)
        self.sign(doc, sctx)
        self.assertEqual(self.status(doc), "SIGNED")
        self.assertEqual(self.issue(doc, octx).replayed, False)

    def test_chua_toi_cong_phat_hanh_la_state_conflict(self):
        doc, _, (_, octx) = self.pending_seal()  # PENDING_SEAL
        before = self.snapshot(doc)
        with self.assertRaises(gate.StateConflict) as cm:
            self.issue(doc, octx)
        self.assertEqual(cm.exception.current_status, "PENDING_SEAL")
        self.assertEqual(self.snapshot(doc), before)

    def test_signed_con_can_dau_khong_phat_hanh_duoc(self):
        doc, _, (_, octx) = self.sealed()
        with self.db.connect("bo19_migrator") as c:
            c.execute("update document set status = 'SIGNED' where id = %s", (doc.document_id,))  # trạng thái thoáng qua của document_sign, dựng tay: cần dấu mà đang SIGNED
        with self.assertRaises(gate.StateConflict):
            self.issue(doc, octx)

    def test_moi_document_mot_lenh(self):
        doc, _, (_, octx) = self.sealed()
        self.issue(doc, octx)
        snap = self.snapshot(doc)
        with self.assertRaises(gate.StateConflict):
            self.issue(doc, octx, key=uuid.uuid4())
        self.assertEqual(self.snapshot(doc), snap)

    def test_dang_cho_tiep_quan_thi_tu_choi(self):
        doc, _, (_, octx) = self.sealed()
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into approval_step (id, document_id, step_kind, status) values (%s, %s, 'TAKEOVER', 'OPEN')", (uuid.uuid4(), doc.document_id))
        before = self.snapshot(doc)
        with self.assertRaises(gate.AwaitingTakeover):
            self.issue(doc, octx)
        self.assertEqual(self.snapshot(doc), before)

    def test_thieu_permission(self):
        doc, _, _ = self.sealed()
        before = self.snapshot(doc)
        with self.assertRaises(PermissionDenied) as cm:
            self.issue(doc, self.officer(roles=("EMPLOYEE",))[1])
        self.assertEqual(cm.exception.detail, "document.issue")
        self.assertEqual(self.snapshot(doc), before)

    def test_nguoi_thu_huong_bi_chan_o_buoc_phat_hanh(self):
        officer, ctx = self.officer()
        doc, _, _ = self.sealed(beneficiary=(officer, ctx))
        before = self.snapshot(doc)
        with self.assertRaises(gate.SelfApprovalBlocked):
            self.issue(doc, ctx)
        self.assertEqual(self.snapshot(doc), before)

    def test_lap_lai_cung_khoa(self):
        doc, _, (_, octx) = self.sealed()
        key = uuid.uuid4()
        first = self.issue(doc, octx, key)
        snap = self.snapshot(doc)
        again = self.issue(doc, octx, key, version=77)
        self.assertEqual((again.replayed, again.created_at), (True, first.created_at))
        self.assertEqual(self.snapshot(doc), snap)

    def test_enqueue_hong_thi_khong_con_lenh(self):
        doc, _, (_, octx) = self.sealed()
        before = self.snapshot(doc)
        with mock.patch("bo19.tool_layer.gate_ops.document_issue.enqueue", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.issue(doc, octx)
        self.assertEqual(self.snapshot(doc), before)  # không bước ISSUE_ORDER, không quyết định, không job


if __name__ == "__main__":
    unittest.main()
