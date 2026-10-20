"""`document_graph` lát Sprint 1 (B9a, ADR-039; mục 6.4.1 của 03-agents.md) — PostgreSQL, SeaweedFS, `soffice` và checkpointer THẬT; provider LLM là transport giả theo tên lời gọi.

Điều được chứng minh, nói bằng hành vi:
- **đường thẳng:** job tới `PENDING_APPROVAL` — một lời gọi LLM, `document_free_content` `PASSED` kèm `prompt_module_version` và dấu vân tay có khoá, bản render nháp có `watermark_text`, `approval_step` `CONTENT_REVIEW` mở,
  `request` `IN_REVIEW`, thread `WAITING` ở `await_content_review`; **checkpoint không chứa giá trị `RES` hay văn bản do LLM sinh** (ADR-008);
- **AC-1.11:** nội dung giả chứa cú pháp trường của template, hoặc nguyên văn giá trị của một slot `RES` khác, **trượt** `validate_free_content` — sinh lại đúng một lần, trượt lần hai thì `FREE_CONTENT_INVALID` (vĩnh viễn) và
  `document` ở lại `DRAFT`, không có bản render;
- **thử lại an toàn:** lỗi tạm giữa chừng rồi chạy lại thì tiếp từ checkpoint — **không gọi LLM lại**; chạy lại khi đã chờ hay đã `END` là no-op;
- **lỗi mang mã của bảng mã `document_halt`**, `permanent` đúng chỗ; hủy hợp tác (`cancel`) dừng trước khi ghi gì;
- **resume** đọc quyết định từ DB (`route_review`), kiểm nó thuộc đúng `document`; graph tới `END`, thread `ENDED`.

Cần BO19_TEST_PG_SUPERUSER_DSN, BO19_TEST_S3_*, `soffice` (image target `test`). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_document_graph -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import threading
import uuid
from unittest import mock

import httpx

from bo19.orchestrator.runner import RenderFailed, document_id_for
from bo19.tool_layer.rendering import convert
from tests.doc_support import BODY_OK, NATIONAL_ID, DocBase, draft_output
from tests.request_support import PURPOSE


class DuongThang(DocBase):
    def test_toi_pending_approval_voi_mot_loi_goi_llm(self):
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        out = self.run_render(rid)
        self.assertEqual((out.status, out.waiting_at, out.already, out.document_id), ("WAITING", "await_content_review", False, document_id_for(rid)))
        self.assertEqual(self.llm_calls(), 1)
        doc = self.document(rid)
        self.assertEqual((doc["status"], doc["revision_round"], doc["operating_mode"], doc["requires_seal"], doc["seal_type"]), ("PENDING_APPROVAL", 0, "NON_PRODUCTION", True, "ORGANIZATION_ROUND"))
        self.assertEqual(doc["template_version_id"], self.version_id)
        self.assertEqual(self.scalar("select status from request where id = %s", rid), "IN_REVIEW")
        thread = self.thread(rid)
        self.assertEqual((thread["status"], thread["waiting_at_node"], thread["ended_at"]), ("WAITING", "await_content_review", None))

    def test_free_content_bang_chung_va_ban_render_nhap(self):
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        self.run_render(rid)
        (name, rnd, attempt, outcome, version, body), = self.free_content(rid)
        self.assertEqual((name, rnd, attempt, outcome, version, body), ("purpose_statement", 0, 1, "PASSED", "1.1", BODY_OK))
        fp = self.rows("select input_fingerprint, fingerprint_key_id from document_free_content where document_id = %s", document_id_for(rid))[0]
        self.assertEqual((len(bytes(fp[0])), fp[1]), (32, "render-fp-v1"))
        render = self.rows("select render_kind, revision_round, watermark_text, operating_mode from document_render where document_id = %s", document_id_for(rid))
        self.assertEqual([(r[0], r[1], r[2] is not None, r[3]) for r in render], [("DRAFT", 0, True, "NON_PRODUCTION")])
        doc = self.document(rid)
        self.assertIsNotNone(doc["current_draft_render_id"])
        self.assertEqual(self.scalar("select id from document_render where document_id = %s", document_id_for(rid)), doc["current_draft_render_id"])

    def test_approval_step_content_review_mo_va_audit(self):
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        self.run_render(rid)
        did = document_id_for(rid)
        self.assertEqual(self.rows("select step_kind, level, revision_round, status, assignee_employee_id from approval_step where document_id = %s", did), [("CONTENT_REVIEW", 1, 0, "OPEN", None)])
        actions = [r[0] for r in self.rows("select action from audit_event where document_id = %s order by occurred_at, id", did)]
        for expected in ("document.create_draft", "document.draft_save", "document.docx_render", "document.pdf_export", "document.submit_for_review"):
            self.assertIn(expected, actions)
        blob = repr(self.rows("select payload from audit_event where document_id = %s", did))
        self.assertNotIn(BODY_OK, blob)
        self.assertNotIn(PURPOSE, blob)

    def test_checkpoint_khong_chua_gia_tri_res_hay_van_ban_llm(self):
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request(national_id=NATIONAL_ID)
        self.run_render(rid)
        text = self.checkpoint_text()
        self.assertGreater(len(text), 500)  # có checkpoint thật để quét
        for secret in (BODY_OK, PURPOSE, NATIONAL_ID, "Ngân hàng GIẢ ABC", "NGƯỜI GIẢ"):
            self.assertNotIn(secret, text)

    def test_input_cua_llm_chi_gom_slot_da_khai_cua_bien(self):
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request(national_id=NATIONAL_ID)
        self.run_render(rid)
        sent = repr(self.llm.calls("draft_free_content")[0])
        self.assertIn(PURPOSE, sent)
        self.assertNotIn(NATIONAL_ID, sent)
        self.assertNotIn("Ngân hàng GIẢ ABC", sent)  # `recipient_org` do template điền thẳng, không qua LLM


class AC111(DocBase):
    """AC-1.11 qua node THẬT `validate_free_content`: hai đầu ra giả đều trượt, sinh lại đúng một lần rồi `FREE_CONTENT_INVALID`."""

    def _fails_twice(self, first: str, second: str):
        self.llm.will("draft_free_content", draft_output(first), draft_output(second))
        rid = self.submitted_request(national_id=NATIONAL_ID)
        with self.assertRaises(RenderFailed) as cm:
            self.run_render(rid)
        return rid, cm.exception

    def _assert_stopped(self, rid, error):
        self.assertEqual((error.reason_code, error.permanent), ("FREE_CONTENT_INVALID", True))
        self.assertEqual(self.llm_calls(), 2)  # đúng một lần sinh lại
        self.assertEqual([(a, o) for _, _, a, o, _, _ in self.free_content(rid)], [(1, "FAILED"), (2, "FAILED")])
        self.assertEqual(self.document(rid)["status"], "DRAFT")  # không bao giờ vào PENDING_APPROVAL
        self.assertEqual(self.scalar("select count(*) from document_render where document_id = %s", document_id_for(rid)), 0)

    def test_cu_phap_truong_cua_template_truot(self):
        rid, error = self._fails_twice("Đề nghị cấp giấy {{ ho_ten }} để bổ sung hồ sơ vay vốn.", "Nội dung có {% for x in y %} cú pháp khối của template.")
        self._assert_stopped(rid, error)

    def test_nguyen_van_slot_res_khac_truot(self):
        leaked = f"Đề nghị cấp giấy cho công dân mang số định danh {NATIONAL_ID} để bổ sung hồ sơ."
        rid, error = self._fails_twice(leaked, leaked)
        self._assert_stopped(rid, error)

    def test_sinh_lai_mot_lan_roi_dat_thi_di_tiep(self):
        self.llm.will("draft_free_content", draft_output("Nội dung có {{ bien_la }} cú pháp trường."), draft_output())
        rid = self.submitted_request()
        out = self.run_render(rid)
        self.assertEqual(out.status, "WAITING")
        self.assertEqual([(a, o) for _, _, a, o, _, _ in self.free_content(rid)], [(1, "FAILED"), (2, "PASSED")])
        self.assertEqual(self.llm_calls(), 2)
        self.assertEqual(self.document(rid)["status"], "PENDING_APPROVAL")

    def test_noi_dung_co_nguyen_van_slot_da_khai_cua_chinh_bien_van_dat(self):
        """Chỉ slot RES **ngoài** input đã khai của biến bị cấm: chính `purpose` (input của `purpose_statement`) xuất hiện nguyên văn trong nội dung vẫn đạt."""
        self.llm.will("draft_free_content", draft_output(f"Nhân viên đề nghị cấp giấy xác nhận với mục đích: {PURPOSE}."))
        rid = self.submitted_request(national_id=NATIONAL_ID)
        self.assertEqual(self.run_render(rid).status, "WAITING")
        self.assertEqual([(a, o) for _, _, a, o, _, _ in self.free_content(rid)], [(1, "PASSED")])

    def test_placeholder_khung_va_markup_truot(self):
        for bad in ("N/A", "Kính gửi Ngân hàng ABC xin nêu mục đích của hồ sơ này.", "Nội dung có thẻ <script>alert(1)</script> nhúng vào văn bản.", "Điền sau ... hồ sơ vay vốn tại ngân hàng"):
            self.llm.set("draft_free_content", draft_output(bad if len(bad) >= 10 else bad + " " * (10 - len(bad)) + "."))
            rid = self.submitted_request()
            with self.assertRaises(RenderFailed, msg=bad) as cm:
                self.run_render(rid)
            self.assertEqual(cm.exception.reason_code, "FREE_CONTENT_INVALID", bad)


class Readiness(DocBase):
    def test_gia_tri_slot_la_placeholder_thi_review_not_ready_o_node_check(self):
        """Render được (giá trị có mặt) nhưng không đủ điều kiện trình duyệt (F2): node `check_review_readiness` dừng, `document` ở lại `DRAFT`, không có `approval_step`."""
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        with self.db.connect(autocommit=True) as c:
            c.execute("update request_slot set value = to_jsonb('N/A'::text) where request_id = %s and slot_name = 'department_name'", (rid,))
        with self.assertRaises(RenderFailed) as cm:
            self.run_render(rid)
        self.assertEqual((cm.exception.reason_code, cm.exception.permanent, cm.exception.raw_code), ("REVIEW_NOT_READY", True, "REVIEW_NOT_READY"))
        self.assertEqual(self.document(rid)["status"], "DRAFT")
        self.assertEqual(self.scalar("select count(*) from approval_step where document_id = %s", document_id_for(rid)), 0)
        self.assertEqual(self.scalar("select count(*) from document_render where document_id = %s", document_id_for(rid)), 1)  # đã render — kiểm đứng SAU render theo thiết kế


class NodeTrucTiep(DocBase):
    """`draft_free_content` gọi thẳng, không qua graph: chốt chặn của chính node (lần sinh nào đã có thì không sinh lại; tối đa hai lần) — các đường đi bình thường không chạm tới chúng vì checkpoint đã ở sau node."""

    def setUp(self):
        super().setUp()
        from bo19.orchestrator.document_graph import nodes as nodes_module
        from bo19.orchestrator.document_graph.runtime import DocumentDeps, RenderRuntime
        from bo19.tool_layer.tools import document_draft_save as dds
        from bo19.tool_layer.tools import document_transition as dt_
        self.rid = self.submitted_request()
        self.did = document_id_for(self.rid)
        dt_.document_create_draft(self.pool, self.sys, document_id=self.did, request_id=self.rid, template_version_id=self.version_id)
        self.dds = dds
        deps = DocumentDeps(pool=self.pool, gateway=self.gateway, storage=self.storage, fingerprinter=dds.InputFingerprinter("x"))
        self.node = nodes_module.make_nodes(deps)["draft_free_content"]
        self.run = RenderRuntime(sys=self.sys)
        self.state = {"document_id": str(self.did), "request_id": str(self.rid), "request_type": "WORK_CONFIRMATION", "pending_targets": ["purpose_statement"]}

    def save(self, attempt: int, outcome: str) -> None:
        self.dds.document_draft_save(self.pool, self.sys, document_id=self.did, variable_name="purpose_statement", revision_round=0, attempt_no=attempt, body=BODY_OK,
                                     validation_outcome=outcome, prompt_module_version="1.0", input_fingerprint=b"" * 32)

    def call(self):
        return self.node(self.state, {"configurable": {"run": self.run}})

    def test_bien_da_passed_thi_khong_goi_llm(self):
        self.save(1, "PASSED")
        self.assertEqual(self.call(), {})
        self.assertEqual(self.llm_calls(), 0)
        self.assertNotIn("purpose_statement", self.run.scratch.get("drafts", {}))

    def test_da_co_lan_failed_thi_lan_sinh_lai_mang_attempt_no_hai(self):
        self.llm.will("draft_free_content", draft_output())
        self.save(1, "FAILED")
        self.call()
        self.assertEqual(self.llm_calls(), 1)
        self.assertEqual(self.run.scratch["drafts"]["purpose_statement"]["attempt_no"], 2)

    def test_chua_co_gi_thi_attempt_no_mot(self):
        self.llm.will("draft_free_content", draft_output())
        self.call()
        self.assertEqual(self.run.scratch["drafts"]["purpose_statement"]["attempt_no"], 1)

    def test_hai_lan_failed_roi_thi_khong_goi_llm_nua_va_la_free_content_invalid(self):
        from bo19.orchestrator.runtime.node_boundary import NodeError
        self.save(1, "FAILED")
        self.save(2, "FAILED")
        with self.assertRaises(NodeError) as cm:
            self.call()
        self.assertEqual(cm.exception.code, "FREE_CONTENT_INVALID")
        self.assertEqual(self.llm_calls(), 0)


class ThuLai(DocBase):
    def test_loi_tam_roi_chay_lai_tiep_tu_checkpoint_khong_goi_llm_lai(self):
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        with mock.patch.object(convert, "convert_to_pdf", side_effect=convert.ConversionFailed()):
            with self.assertRaises(RenderFailed) as cm:
                self.run_render(rid)
        self.assertEqual((cm.exception.reason_code, cm.exception.permanent), ("RENDER_CONVERSION_FAILED", False))
        self.assertEqual(self.document(rid)["status"], "DRAFT")
        self.assertEqual(self.runner.snapshot(document_id_for(rid)).next_nodes, ("render_draft",))  # dừng đúng node hỏng
        out = self.run_render(rid)  # job thử lại
        self.assertEqual((out.status, out.already), ("WAITING", False))
        self.assertEqual(self.llm_calls(), 1)  # không sinh lại
        self.assertEqual(self.document(rid)["status"], "PENDING_APPROVAL")
        self.assertEqual(self.scalar("select count(*) from document where request_id = %s", rid), 1)

    def test_chay_lai_khi_da_cho_la_no_op(self):
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        self.run_render(rid)
        before = (self.scalar("select count(*) from audit_event where document_id = %s", document_id_for(rid)), self.scalar("select count(*) from approval_step where document_id = %s", document_id_for(rid)))
        with mock.patch.object(convert, "convert_to_pdf", side_effect=AssertionError("không được chuyển đổi lại")):
            again = self.run_render(rid)
        self.assertEqual((again.status, again.already), ("WAITING", True))
        self.assertEqual(self.llm_calls(), 1)
        self.assertEqual(before, (self.scalar("select count(*) from audit_event where document_id = %s", document_id_for(rid)), self.scalar("select count(*) from approval_step where document_id = %s", document_id_for(rid))))

    def test_mat_scratch_giua_hai_node_sinh_lai_khong_tinh_vao_regenerated(self):
        """Tiến trình chết giữa `draft_free_content` và `validate_free_content`: `scratch` mất. Chạy lại: sinh lại mà KHÔNG mất lượt sinh lại duy nhất (vẫn còn một lần nữa nếu trượt)."""
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        from bo19.orchestrator.document_graph import nodes as nodes_module

        class Crash(Exception):
            pass

        def boom(*a, **k):
            raise Crash

        with mock.patch.object(nodes_module, "document_draft_save", boom):
            with self.assertRaises(RenderFailed):
                self.run_render(rid)
        self.assertEqual(self.free_content(rid), [])  # chưa lưu gì
        self.llm.will("draft_free_content", draft_output())  # lần gọi thứ hai cho lần chạy lại
        out = self.run_render(rid)
        self.assertEqual(out.status, "WAITING")
        self.assertEqual(self.llm_calls(), 2)
        self.assertEqual([(a, o) for _, _, a, o, _, _ in self.free_content(rid)], [(1, "PASSED")])


class LoiMangMa(DocBase):
    def failed(self, rid):  # KHÔNG đặt tên `fail`: `assertEqual` trên tuple gọi `self.failed(msg)` — ghi đè nó làm mọi assert tuple của lớp này không bao giờ đỏ
        with self.assertRaises(RenderFailed) as cm:
            self.run_render(rid)
        return cm.exception

    def test_json_hong_sau_lan_sua_la_parse_failed_vinh_vien(self):
        self.llm.set("draft_free_content", "đây không phải JSON")
        e = self.failed(self.submitted_request())
        self.assertEqual((e.reason_code, e.permanent), ("PARSE_FAILED", True))

    def test_provider_loi_la_loi_tam_kem_retry_after(self):
        self.llm.set("draft_free_content", httpx.Response(429, headers={"retry-after": "500"}, json={"error": {"message": "x", "type": "rate_limit"}}))
        e = self.failed(self.submitted_request())
        self.assertEqual((e.reason_code, e.permanent), ("PROVIDER_UNAVAILABLE", False))
        self.assertEqual(e.retry_after_s, 500)  # vượt WV-19: provider không chờ, hàng đợi sẽ `FAILED` ngay (jobs.fail)

    def test_het_budget_la_vinh_vien_va_khong_goi_provider(self):
        rid = self.submitted_request()
        with self.db.connect(autocommit=True) as c:
            c.execute("insert into llm_usage (id, call_name, model_tier, prompt_module_version, request_id, input_tokens, output_tokens, outcome, trace_id) "
                      "values (%s, 'draft_free_content', 'STRONG', '1.0', %s, 100000000, 100000000, 'OK', %s)", (uuid.uuid4(), rid, str(uuid.uuid4())))
        e = self.failed(rid)
        self.assertEqual((e.reason_code, e.permanent), ("BUDGET_EXCEEDED", True))
        self.assertEqual(self.llm_calls(), 0)

    def test_thieu_font_la_vinh_vien_sau_khi_da_sinh_noi_dung(self):
        from tests.doc_support import make_template, retire_active_templates
        retire_active_templates(self.db)
        make_template(self.db, self.pool, self.storage, fonts=("Times New Roman", "Font Khong Co Bo19"))
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        e = self.failed(rid)
        self.assertEqual((e.reason_code, e.permanent), ("FONT_MISSING", True))
        self.assertEqual(self.document(rid)["status"], "DRAFT")

    def test_bien_system_khong_co_co_dien_sau_duyet_ma_van_ban_dung_la_render_input_invalid(self):
        from tests.doc_support import VARIABLES, make_template, retire_active_templates, template_docx
        retire_active_templates(self.db)
        make_template(self.db, self.pool, self.storage, variables=VARIABLES + (("so_ho_so", "SYSTEM", None, False, None, None, ()),), data=template_docx(("Số hồ sơ: {{ so_ho_so }}",)))
        self.llm.will("draft_free_content", draft_output())
        e = self.failed(self.submitted_request())
        self.assertEqual((e.reason_code, e.permanent), ("RENDER_INPUT_INVALID", True))  # `docx_render`: MISSING_VARIABLE — mẫu dùng biến mà bảng giá trị không có

    def test_bien_system_khong_co_co_dien_sau_duyet_ma_van_ban_khong_dung_la_review_not_ready(self):
        from tests.doc_support import VARIABLES, make_template, retire_active_templates
        retire_active_templates(self.db)
        make_template(self.db, self.pool, self.storage, variables=VARIABLES + (("so_ho_so", "SYSTEM", None, False, None, None, ()),), data=None)
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        e = self.failed(rid)
        self.assertEqual((e.reason_code, e.permanent), ("REVIEW_NOT_READY", True))  # render qua (mẫu không dùng biến), `check_review_readiness` bắt VARIABLE_MISSING
        self.assertEqual(self.document(rid)["status"], "DRAFT")

    def test_khong_co_template_dang_hieu_luc_la_template_not_active(self):
        from tests.doc_support import retire_active_templates
        retire_active_templates(self.db)
        e = self.failed(self.submitted_request())
        self.assertEqual((e.reason_code, e.permanent), ("TEMPLATE_NOT_ACTIVE", True))
        self.assertEqual(self.llm_calls(), 0)

    def test_template_bi_sua_trong_storage_la_checksum_mismatch_tam(self):
        key = self.scalar("select source_object_key from template_version where id = %s", self.version_id)
        size = self.raw.get_object(Bucket=self.bucket, Key=key)["ContentLength"]
        self.raw.put_object(Bucket=self.bucket, Key=key, Body=b"x" * size)  # cùng độ dài, khác nội dung
        self.llm.will("draft_free_content", draft_output())
        e = self.failed(self.submitted_request())
        self.assertEqual((e.reason_code, e.permanent), ("RENDER_CHECKSUM_MISMATCH", False))

    def test_template_mat_trong_storage_la_object_missing_tam(self):
        key = self.scalar("select source_object_key from template_version where id = %s", self.version_id)
        self.raw.delete_object(Bucket=self.bucket, Key=key)
        self.llm.will("draft_free_content", draft_output())
        e = self.failed(self.submitted_request())
        self.assertEqual((e.reason_code, e.permanent), ("RENDER_OBJECT_MISSING", False))

    def test_request_chua_submitted_la_system_defect_va_khong_tao_document(self):
        from tests.request_support import build_request
        rid = build_request(self.pool, self.db, self.eid, self.ctx)  # DRAFT, chưa gửi
        e = self.failed(rid)
        self.assertEqual((e.reason_code, e.permanent), ("SYSTEM_DEFECT", True))
        self.assertEqual(self.scalar("select count(*) from document where request_id = %s", rid), 0)

    def test_co_huy_dung_truoc_khi_ghi_gi(self):
        rid = self.submitted_request()
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(RenderFailed) as cm:
            self.run_render(rid, cancel=cancel)
        self.assertEqual((cm.exception.reason_code, cm.exception.permanent), ("JOB_CANCELLED", False))
        self.assertEqual(self.scalar("select count(*) from document where request_id = %s", rid), 0)
        self.assertEqual(self.llm_calls(), 0)

    def test_loi_khong_mang_gia_tri(self):
        self.llm.set("draft_free_content", "không phải JSON")
        e = self.failed(self.submitted_request(national_id=NATIONAL_ID))
        for text in (repr(e), str(e), e.raw_code):
            self.assertNotIn(PURPOSE, text)
            self.assertNotIn(NATIONAL_ID, text)


class Resume(DocBase):
    def test_resume_doc_quyet_dinh_tu_db_va_toi_diem_cho_ky(self):
        """B9b1: sau cổng 1 graph đi tiếp `route_review` → `route_signing` và dừng ở `await_signature` (không còn `END` ngay sau `route_review` như B9a)."""
        self.make_signer()
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        self.run_render(rid)
        decision = self.approve(rid)
        did = document_id_for(rid)
        out = self.runner.resume_document(document_id=did, decision_record_id=decision)
        self.assertEqual((out.status, out.waiting_at, out.already), ("WAITING", "await_signature", False))
        snap = self.runner.snapshot(did)
        self.assertFalse(snap.finished)
        self.assertEqual(snap.values["last_signal"], {"decision_record_id": str(decision), "kind": "APPROVED", "change_scope": None, "change_targets": []})
        thread = self.thread(rid)
        self.assertEqual((thread["status"], thread["waiting_at_node"], thread["ended_at"]), ("WAITING", "await_signature", None))
        self.assertEqual(self.llm_calls(), 1)  # resume không chạy lại node nào đã xong
        again = self.runner.resume_document(document_id=did, decision_record_id=decision)  # thử lại job: no-op
        self.assertEqual((again.status, again.waiting_at, again.already), ("WAITING", "await_signature", True))

    def test_quyet_dinh_cua_document_khac_la_system_defect(self):
        self.llm.will("draft_free_content", draft_output())
        a, b = self.submitted_request(), self.submitted_request()
        self.run_render(a)
        self.run_render(b)
        foreign = self.approve(b)
        with self.assertRaises(RenderFailed) as cm:
            self.runner.resume_document(document_id=document_id_for(a), decision_record_id=foreign)
        self.assertEqual((cm.exception.reason_code, cm.exception.permanent), ("SYSTEM_DEFECT", True))
        self.assertEqual(self.thread(a)["status"], "WAITING")  # vẫn chờ — payload sai không làm thread kết thúc

    def test_resume_thread_khong_cho_la_loi(self):
        with self.assertRaises(RenderFailed) as cm:
            self.runner.resume_document(document_id=uuid.uuid4(), decision_record_id=uuid.uuid4())
        self.assertEqual(cm.exception.raw_code, "THREAD_NOT_WAITING")
