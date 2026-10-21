"""`document_graph` B9b1 (ADR-040) từ cổng 1 tới `await_issue`, qua thao tác cổng THẬT và `Dispatcher` thật — PostgreSQL, SeaweedFS, `soffice` và checkpointer THẬT; provider LLM là transport giả.

Điều được chứng minh, nói bằng hành vi:
- **đường thẳng có dấu:** duyệt → worker chạy `resume_document_graph` → `route_signing` (`render_integrity_check` rồi `signing_route`) → chờ ở `await_signature`; ký → `PENDING_SEAL`, chờ ở `await_seal`;
  đóng dấu → `SEALED`, chờ ở `await_issue`; **không gọi LLM lại**, không render lại; mọi job `SUCCEEDED`; checkpoint không chứa văn bản LLM hay giá trị `RES` (ADR-008);
- **không cần dấu:** ký xong đi thẳng `await_issue`; **lệnh phát hành** ghi job `finalize_issue` (B9b2 có handler: `test_finalize_issue.py`) — `document` không đổi trạng thái tới khi worker chạy;
- **`NO_ELIGIBLE_SIGNER`** (không ai, hoặc chỉ còn người thụ hưởng): job `FAILED` ngay, `document` ở `APPROVED`; cấp quyền rồi chạy lại **tiếp từ checkpoint**, không làm lại node nào đã xong;
- **toàn vẹn byte:** bản đã duyệt bị sửa → job thử lại (lỗi tạm), không người ký nào được giao; khôi phục byte thì đi tiếp;
- **resume theo loại quyết định:** chạy lại sau khi đã qua điểm chờ là no-op; quyết định của điểm chờ SAU thì `THREAD_NOT_WAITING`; quyết định lạ loại hay của `document` khác là lỗi hệ thống vĩnh viễn.

Cần BO19_TEST_PG_SUPERUSER_DSN, BO19_TEST_S3_*, `soffice` (image target `test`). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_document_gates_graph -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import uuid
from unittest import mock

from bo19.orchestrator.runner import RenderFailed, document_id_for
from bo19.queue_worker.dispatcher import Dispatcher
from bo19.queue_worker.handlers import build_handlers
from bo19.tool_layer.gate_ops.document_apply_seal import document_apply_seal
from bo19.tool_layer.gate_ops.document_approve_content import document_approve_content
from bo19.tool_layer.gate_ops.document_issue import document_issue
from bo19.tool_layer.gate_ops.document_sign import document_sign
from tests.doc_support import BODY_OK, NATIONAL_ID, DocBase, draft_output
from tests.gate_support import make_officer
from tests.request_support import PURPOSE


class GateGraphBase(DocBase):
    def setUp(self):
        super().setUp()
        with self.db.connect("bo19_migrator") as c:  # DB riêng của lớp test dùng chung giữa các test: gỡ quyền cấp lẻ của test trước (`signing_route` chọn trong cả DB)
            c.execute("delete from employee_permission_grant")
        self.officer_id, self.octx = make_officer(self.db, self.pool)
        self.dispatcher = Dispatcher(self.pool, build_handlers(document_runner=self.runner), poll_s=0.05, heartbeat_s=0.2, lease_s=30, drain_s=5)

    # ---- dựng ----------------------------------------------------------------------------------------------------------------

    def signer(self):
        """Người ký duy nhất của DB riêng của lớp test, hoặc người đầu tiên được cấp `document.sign`."""
        return make_officer(self.db, self.pool, signer=True)

    def waiting(self, llm_bodies=1):
        """Một `request` đã `run_render` tới `PENDING_APPROVAL`."""
        self.llm.will("draft_free_content", *[draft_output() for _ in range(llm_bodies)])
        rid = self.submitted_request(national_id=NATIONAL_ID)
        self.run_render(rid)
        return rid

    def version(self, rid) -> int:
        return self.scalar("select row_version from document where id = %s", document_id_for(rid))

    def approve(self, rid, key=None):
        return document_approve_content(self.pool, self.octx, document_id=document_id_for(rid), decision_id=key or uuid.uuid4(), expected_row_version=self.version(rid)).decision_record_id

    def sign(self, rid, ctx, key=None):
        return document_sign(self.pool, ctx, document_id=document_id_for(rid), decision_id=key or uuid.uuid4(), expected_row_version=self.version(rid)).decision_record_id

    def seal(self, rid, key=None):
        return document_apply_seal(self.pool, self.octx, document_id=document_id_for(rid), decision_id=key or uuid.uuid4(), expected_row_version=self.version(rid), copies_count=2, page_count=None).decision_record_id

    def issue(self, rid, key=None):
        return document_issue(self.pool, self.octx, document_id=document_id_for(rid), decision_id=key or uuid.uuid4(), expected_row_version=self.version(rid)).decision_record_id

    def drain(self) -> int:
        """Worker chạy mọi job đang sẵn sàng. Trả số job đã chạy."""
        n = 0
        while self.dispatcher.run_once():
            n += 1
            self.assertLess(n, 20)
        return n

    def jobs(self, rid, job_type="resume_document_graph") -> list[tuple]:
        return self.rows("select status, attempts, last_error_code from job where subject_document_id = %s and job_type = %s order by enqueued_at, id", document_id_for(rid), job_type)

    def status(self, rid) -> str:
        return self.document(rid)["status"]

    def at(self, rid) -> tuple[str, str | None]:
        t = self.thread(rid)
        return t["status"], t["waiting_at_node"]


class DuongThang(GateGraphBase):
    def test_duyet_ky_dong_dau_toi_await_issue(self):
        signer_id, sctx = self.signer()
        rid = self.waiting()
        did = document_id_for(rid)
        self.assertEqual(self.at(rid), ("WAITING", "await_content_review"))

        approved = self.approve(rid)
        self.assertEqual(self.status(rid), "APPROVED")  # đứng ở APPROVED tới khi worker chạy
        self.assertEqual(self.drain(), 2)  # render_document (no-op, đã chờ) và resume_document_graph
        self.assertEqual((self.status(rid), self.at(rid)), ("PENDING_SIGNATURE", ("WAITING", "await_signature")))
        self.assertEqual(self.document(rid)["status"], "PENDING_SIGNATURE")
        self.assertEqual(self.scalar("select signer_employee_id from document where id = %s", did), signer_id)
        self.assertEqual(self.rows("select step_kind, status, assignee_employee_id from approval_step where document_id = %s and step_kind = 'SIGNATURE'", did), [("SIGNATURE", "OPEN", signer_id)])
        self.assertEqual(self.jobs(rid), [("SUCCEEDED", 1, None)])

        signed = self.sign(rid, sctx)
        self.assertEqual(self.status(rid), "PENDING_SEAL")
        self.assertEqual(self.drain(), 1)
        self.assertEqual((self.status(rid), self.at(rid)), ("PENDING_SEAL", ("WAITING", "await_seal")))

        sealed = self.seal(rid)
        self.assertEqual(self.status(rid), "SEALED")
        self.assertEqual(self.drain(), 1)
        self.assertEqual((self.status(rid), self.at(rid)), ("SEALED", ("WAITING", "await_issue")))
        self.assertEqual(self.jobs(rid), [("SUCCEEDED", 1, None)] * 3)

        # AC-1.2 (phần B9b1): hai quyết định riêng APPROVED và SEALED, mỗi cái một audit_event
        for kind, decision, action in (("APPROVED", approved, "document.approve_content"), ("SEALED", sealed, "document.apply_seal"), ("SIGNED", signed, "document.sign")):
            self.assertEqual(self.rows("select kind from decision_record where id = %s", decision), [(kind,)])
            self.assertEqual(self.rows("select action, actor_kind from audit_event where decision_record_id = %s", decision), [(action, "EMPLOYEE")])
        self.assertEqual(self.scalar("select count(*) from decision_record where document_id = %s and kind in ('APPROVED', 'SEALED')", did), 2)

        self.assertEqual(self.llm_calls(), 1)  # không sinh lại nội dung ở bất kỳ điểm nào
        self.assertEqual(self.scalar("select count(*) from document_render where document_id = %s", did), 1)  # không render lại
        self.assertEqual(self.scalar("select status from request where id = %s", rid), "APPROVED")  # đã ký

    def test_checkpoint_khong_chua_van_ban_llm_hay_gia_tri_res(self):
        _, sctx = self.signer()
        rid = self.waiting()
        self.approve(rid)
        self.drain()
        self.sign(rid, sctx)
        self.drain()
        self.seal(rid)
        self.drain()
        text = self.checkpoint_text()
        for secret in (BODY_OK, PURPOSE, NATIONAL_ID, "Ngân hàng GIẢ ABC", "NGƯỜI GIẢ"):
            self.assertNotIn(secret, text)
        self.assertGreater(len(text), 500)

    def test_khong_can_dau_ky_xong_di_thang_await_issue(self):
        _, sctx = self.signer()
        rid = self.waiting()
        self.assertEqual(self.drain(), 1)  # job render_document còn QUEUED (test gọi run_render trực tiếp): chạy là no-op
        with self.db.connect("bo19_migrator") as c:
            c.execute("update document set requires_seal = false, seal_type = null where id = %s", (document_id_for(rid),))
        self.approve(rid)
        self.drain()
        self.sign(rid, sctx)
        self.assertEqual(self.status(rid), "SIGNED")
        self.drain()
        self.assertEqual((self.status(rid), self.at(rid)), ("SIGNED", ("WAITING", "await_issue")))
        self.assertEqual(self.scalar("select count(*) from approval_step where document_id = %s and step_kind = 'SEAL'", document_id_for(rid)), 0)

    def test_lenh_phat_hanh_ghi_job_finalize_issue_queued_va_khong_doi_trang_thai_toi_khi_worker_chay(self):
        _, sctx = self.signer()
        rid = self.waiting()
        self.approve(rid)
        self.drain()
        self.sign(rid, sctx)
        self.drain()
        self.seal(rid)
        self.drain()
        order = self.issue(rid)
        self.assertEqual(self.status(rid), "SEALED")
        self.assertEqual(self.jobs(rid, "finalize_issue"), [("QUEUED", 0, None)])
        self.assertEqual(self.at(rid), ("WAITING", "await_issue"))  # lệnh chỉ ghi và enqueue; `finalize_issue` chạy ở worker (B9b2 — test_finalize_issue.py)
        self.assertEqual(self.rows("select kind from decision_record where id = %s", order), [("ISSUE_ORDERED",)])
        self.assertEqual(self.scalar("select count(*) from document_register_entry where document_id = %s", document_id_for(rid)), 0)  # và không số nào bị tiêu ở luồng request


class KhongCoNguoiKy(GateGraphBase):
    def test_khong_ai_mang_document_sign_job_failed_va_tiep_tu_checkpoint(self):
        rid = self.waiting()
        approved = self.approve(rid)
        self.drain()
        self.assertEqual(self.jobs(rid), [("FAILED", 1, "NO_ELIGIBLE_SIGNER")])  # vĩnh viễn: failed ngay ở lượt đầu
        self.assertEqual(self.status(rid), "APPROVED")
        self.assertIsNone(self.scalar("select signer_employee_id from document where id = %s", document_id_for(rid)))
        self.assertEqual(self.scalar("select count(*) from approval_step where document_id = %s and step_kind = 'SIGNATURE'", document_id_for(rid)), 0)
        self.assertEqual(self.runner.snapshot(document_id_for(rid)).next_nodes, ("route_signing",))  # dừng đúng node hỏng, không ở điểm chờ

        signer_id, _ = self.signer()  # cấp quyền rồi chạy lại: tiếp từ checkpoint
        calls = self.llm_calls()
        out = self.runner.resume_document(document_id=document_id_for(rid), decision_record_id=approved)
        self.assertEqual((out.status, out.waiting_at, out.already), ("WAITING", "await_signature", False))
        self.assertEqual(self.status(rid), "PENDING_SIGNATURE")
        self.assertEqual(self.scalar("select signer_employee_id from document where id = %s", document_id_for(rid)), signer_id)
        self.assertEqual(self.llm_calls(), calls)

    def test_chi_nguoi_thu_huong_mang_document_sign_van_khong_ai_ky(self):
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into employee_permission_grant (id, employee_id, permission_code) values (%s, %s, 'document.sign')", (uuid.uuid4(), self.eid))
        rid = self.waiting()
        self.approve(rid)
        self.drain()
        self.assertEqual(self.jobs(rid), [("FAILED", 1, "NO_ELIGIBLE_SIGNER")])
        self.assertEqual(self.status(rid), "APPROVED")


class ToanVenByte(GateGraphBase):
    def test_ban_da_duyet_bi_sua_thi_khong_giao_nguoi_ky_va_khoi_phuc_thi_di_tiep(self):
        _, sctx = self.signer()
        rid = self.waiting()
        did = document_id_for(rid)
        render_id, docx_key, pdf_key = self.rows("select id, docx_object_key, pdf_object_key from document_render where document_id = %s", did)[0]
        original = self.raw.get_object(Bucket=self.bucket, Key=pdf_key)["Body"].read()
        self.raw.put_object(Bucket=self.bucket, Key=pdf_key, Body=b"x" * len(original))
        approved = self.approve(rid)
        self.drain()
        job = self.jobs(rid)[0]
        self.assertEqual((job[0], job[2]), ("QUEUED", "RENDER_CHECKSUM_MISMATCH"))  # lỗi tạm: hẹn thử lại theo backoff
        self.assertEqual(self.status(rid), "APPROVED")
        self.assertIsNone(self.scalar("select signer_employee_id from document where id = %s", did))
        self.assertEqual(self.scalar("select count(*) from approval_step where document_id = %s and step_kind = 'SIGNATURE'", did), 0)

        self.raw.put_object(Bucket=self.bucket, Key=pdf_key, Body=original)  # khôi phục byte
        out = self.runner.resume_document(document_id=did, decision_record_id=approved)
        self.assertEqual((out.status, out.waiting_at), ("WAITING", "await_signature"))
        self.assertEqual(self.status(rid), "PENDING_SIGNATURE")
        self.assertEqual(self.sign(rid, sctx) is not None, True)

    def test_object_mat_la_object_missing_tam(self):
        self.signer()
        rid = self.waiting()
        _, docx_key, _ = self.rows("select id, docx_object_key, pdf_object_key from document_render where document_id = %s", document_id_for(rid))[0]
        self.raw.delete_object(Bucket=self.bucket, Key=docx_key)
        self.approve(rid)
        self.drain()
        job = self.jobs(rid)[0]
        self.assertEqual((job[0], job[2]), ("QUEUED", "RENDER_OBJECT_MISSING"))
        self.assertEqual(self.status(rid), "APPROVED")


class ResumeTheoLoaiQuyetDinh(GateGraphBase):
    def at_signature(self):
        _, sctx = self.signer()
        rid = self.waiting()
        approved = self.approve(rid)
        self.drain()
        return rid, sctx, approved

    def test_chay_lai_quyet_dinh_da_xu_ly_la_no_op(self):
        rid, sctx, approved = self.at_signature()
        did = document_id_for(rid)
        snap = (self.scalar("select count(*) from audit_event where document_id = %s", did), self.rows("select status, row_version from approval_step where document_id = %s order by id", did), self.at(rid), self.scalar("select row_version from document where id = %s", did))
        out = self.runner.resume_document(document_id=did, decision_record_id=approved)  # thread đang chờ await_signature, sau await_content_review
        self.assertEqual((out.status, out.waiting_at, out.already), ("WAITING", "await_signature", True))
        self.assertEqual(snap, (self.scalar("select count(*) from audit_event where document_id = %s", did), self.rows("select status, row_version from approval_step where document_id = %s order by id", did), self.at(rid), self.scalar("select row_version from document where id = %s", did)))
        signed = self.sign(rid, sctx)
        self.drain()
        for decision in (approved, signed):  # cả hai đều đã qua
            self.assertTrue(self.runner.resume_document(document_id=did, decision_record_id=decision).already)
        self.assertEqual(self.at(rid), ("WAITING", "await_seal"))

    def test_job_resume_chay_hai_lan_cho_cung_quyet_dinh(self):
        rid, _, approved = self.at_signature()
        with self.db.connect("bo19_migrator", autocommit=True) as c:  # ép job chạy lại như thể lần trước mất lease sau khi graph đã đi tiếp
            c.execute("update job set status = 'QUEUED', attempts = 0, finished_at = null, run_after = now() where subject_document_id = %s and job_type = 'resume_document_graph'", (document_id_for(rid),))
        self.assertEqual(self.drain(), 1)
        self.assertEqual(self.jobs(rid), [("SUCCEEDED", 1, None)])
        self.assertEqual((self.status(rid), self.at(rid)), ("PENDING_SIGNATURE", ("WAITING", "await_signature")))
        self.assertEqual(self.scalar("select count(*) from approval_step where document_id = %s and step_kind = 'SIGNATURE'", document_id_for(rid)), 1)

    def test_quyet_dinh_cua_diem_cho_sau_khi_thread_chua_toi_do(self):
        """Thread còn chờ `await_content_review`; một quyết định `SIGNED` (dựng tay) không được đánh thức nó."""
        self.signer()
        rid = self.waiting()
        did = document_id_for(rid)
        decision = uuid.uuid4()
        with self.db.connect("bo19_migrator") as c:
            step = c.execute("select id from approval_step where document_id = %s and step_kind = 'CONTENT_REVIEW'", (did,)).fetchone()[0]
            c.execute("insert into decision_record (id, kind, actor_employee_id, request_id, document_id, approval_step_id) values (%s, 'SIGNED', %s, %s, %s, %s)", (decision, self.officer_id, rid, did, step))
        with self.assertRaises(RenderFailed) as cm:
            self.runner.resume_document(document_id=did, decision_record_id=decision)
        self.assertEqual(cm.exception.raw_code, "THREAD_NOT_WAITING")
        self.assertEqual(self.at(rid), ("WAITING", "await_content_review"))

    def test_loai_quyet_dinh_chua_ho_tro_la_loi_he_thong_vinh_vien(self):
        self.signer()
        rid = self.waiting()
        did = document_id_for(rid)
        decision = uuid.uuid4()
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into decision_record (id, kind, actor_employee_id, request_id, document_id) values (%s, 'REJECTED', %s, %s, %s)", (decision, self.officer_id, rid, did))
        with self.assertRaises(RenderFailed) as cm:
            self.runner.resume_document(document_id=did, decision_record_id=decision)
        self.assertEqual((cm.exception.reason_code, cm.exception.permanent, cm.exception.raw_code), ("SYSTEM_DEFECT", True, "UNSUPPORTED_DECISION"))
        self.assertEqual(self.at(rid), ("WAITING", "await_content_review"))

    def test_quyet_dinh_cua_document_khac(self):
        self.signer()
        a, b = self.waiting(2), self.submitted_request()
        self.run_render(b)
        foreign = self.approve(b)
        with self.assertRaises(RenderFailed) as cm:
            self.runner.resume_document(document_id=document_id_for(a), decision_record_id=foreign)
        self.assertEqual((cm.exception.reason_code, cm.exception.permanent), ("SYSTEM_DEFECT", True))
        self.assertEqual(self.at(a), ("WAITING", "await_content_review"))

    def test_loi_giua_chung_roi_chay_lai_tiep_tu_checkpoint_khong_lam_lai_node(self):
        """`signing_route` hỏng một lần (lỗi hạ tầng) sau khi `interrupt` đã trả: chạy lại phải tiếp bằng `invoke(None)`, không dừng ở `THREAD_NOT_WAITING`."""
        self.signer()
        rid = self.waiting()
        approved = self.approve(rid)
        from bo19.orchestrator.document_graph import nodes as nodes_module

        with mock.patch.object(nodes_module, "signing_route", side_effect=RuntimeError("hạ tầng chớp tắt")):
            with self.assertRaises(RenderFailed) as cm:
                self.runner.resume_document(document_id=document_id_for(rid), decision_record_id=approved)
        self.assertFalse(cm.exception.permanent)
        self.assertEqual(self.status(rid), "APPROVED")
        snap = self.runner.snapshot(document_id_for(rid))
        self.assertEqual((snap.waiting_at, snap.next_nodes), (None, ("route_signing",)))
        out = self.runner.resume_document(document_id=document_id_for(rid), decision_record_id=approved)
        self.assertEqual((out.status, out.waiting_at), ("WAITING", "await_signature"))
        self.assertEqual(self.llm_calls(), 1)

    def test_chua_co_thread_thi_khong_resume_duoc(self):
        with self.assertRaises(RenderFailed) as cm:
            self.runner.resume_document(document_id=uuid.uuid4(), decision_record_id=uuid.uuid4())
        self.assertEqual(cm.exception.raw_code, "THREAD_NOT_WAITING")


class QuyenXemCuaNguoiKy(GateGraphBase):
    def test_nguoi_duoc_giao_buoc_ky_la_assigned_con_nguoi_khac_thi_khong(self):
        """Cơ sở của quy ước `request.read_assigned` (mục 3.4 của 09-security.md): bước `SIGNATURE` có `assignee_employee_id` là người ký; ba bước còn lại không giao cho ai."""
        signer_id, _ = self.signer()
        rid = self.waiting()
        self.approve(rid)
        self.drain()
        did = document_id_for(rid)
        self.assertEqual(self.rows("select step_kind, assignee_employee_id from approval_step where document_id = %s order by step_kind", did), [("CONTENT_REVIEW", None), ("SIGNATURE", signer_id)])
