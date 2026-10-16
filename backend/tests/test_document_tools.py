"""Tool của lát B9a (ADR-039): `template_fetch`, `document_transition` (tạo `DRAFT`, trình duyệt), `document_draft_save`, bảng giá trị biến + `review_readiness_check`, bốn phép đọc nhỏ — PostgreSQL thật.

Điều được chứng minh, nói bằng hành vi:
- `template_fetch`: đúng một phiên bản `ACTIVE`; danh mục biến kèm input tự khai; hai template cùng loại đều `ACTIVE` là lỗi chứ không chọn bừa;
- `document_create_draft`: idempotent theo id; ghim `operating_mode` và mặc định dấu của `request_type`; `request` chưa `SUBMITTED` thì từ chối; `document` thứ hai của cùng `request` là xung đột;
- `document_draft_save`: ghi một lần, **chặn cứng khi không ở `DRAFT`** (lớp thứ hai của INV-01), đúng vòng; dấu vân tay có khoá, không lộ khoá;
- bảng giá trị: nguồn đúng trạng thái (HR chưa xác nhận → `WRONG_SOURCE`), thiếu → `VARIABLE_MISSING`, `DATE` → `dd/mm/yyyy`, kiểu chưa hỗ trợ không bị đoán, biến điền-sau-duyệt là dấu giữ chỗ cố định và không bị coi là placeholder;
- `document_submit_for_review`: **tự chạy lại** readiness (`NOT_READY`), một giao dịch đủ bốn việc, idempotent;
- mọi tool chỉ tác nhân hệ thống; lỗi và `audit_event` không mang giá trị.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_document_tools -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import uuid

from bo19.domain import provisional
from bo19.orchestrator.runner import document_id_for
from bo19.tool_layer.kernel.context import Actor, ToolContext
from bo19.tool_layer.kernel.permission import SystemActorRequired
from bo19.tool_layer.tools import document_draft_save as dds
from bo19.tool_layer.tools import document_reads as reads
from bo19.tool_layer.tools import document_transition as dt_
from bo19.tool_layer.tools import render_values as rv
from bo19.tool_layer.tools import review_readiness_check as rrc
from bo19.tool_layer.tools import template_fetch as tf
from bo19.tool_layer.tools.docx_render import docx_render
from bo19.tool_layer.tools.pdf_export import pdf_export
from tests.doc_support import BODY_OK, FINGERPRINT_KEY, NATIONAL_ID, VARIABLES, DocBase, make_template, retire_active_templates
from tests.request_support import PURPOSE, RECIPIENT


class TemplateFetch(DocBase):
    def test_phien_ban_active_va_danh_muc_bien(self):
        info = tf.template_fetch(self.pool, self.sys, request_type="WORK_CONFIRMATION")
        self.assertEqual((info.template_version_id, info.version_no, info.status), (self.version_id, 1, "ACTIVE"))
        self.assertEqual([v.name for v in info.variables], sorted(v[0] for v in VARIABLES))
        purpose = info.variable("purpose_statement")
        self.assertEqual((purpose.kind, purpose.max_length, purpose.slot_inputs, purpose.fill_after_approval), ("FREE_CONTENT", 400, ("purpose",), False))
        self.assertTrue(info.variable("document_number").fill_after_approval)
        self.assertEqual(info.variable("full_name").source_slot_name, "full_name")
        self.assertEqual(info.free_content_variables, ("purpose_statement",))

    def test_khong_co_phien_ban_active(self):
        retire_active_templates(self.db)
        with self.assertRaises(tf.NoActiveTemplate):
            tf.template_fetch(self.pool, self.sys, request_type="WORK_CONFIRMATION")
        with self.assertRaises(tf.NoActiveTemplate):
            tf.template_fetch(self.pool, self.sys, request_type="LOAI_LA")

    def test_hai_template_cung_loai_deu_active_la_loi_khong_chon_bua(self):
        make_template(self.db, self.pool, self.storage)
        with self.assertRaises(tf.TemplateAmbiguous):
            tf.template_fetch(self.pool, self.sys, request_type="WORK_CONFIRMATION")

    def test_doc_phien_ban_da_ghim_bat_ke_trang_thai(self):
        retire_active_templates(self.db)
        retired = tf.template_version_read(self.pool, self.sys, template_version_id=self.version_id)
        self.assertEqual(retired.status, "RETIRED")
        with self.assertRaises(tf.TemplateVersionNotFound):
            tf.template_version_read(self.pool, self.sys, template_version_id=uuid.uuid4())

    def test_chi_tac_nhan_he_thong(self):
        with self.assertRaises(SystemActorRequired):
            tf.template_fetch(self.pool, self.ctx, request_type="WORK_CONFIRMATION")


class CreateDraft(DocBase):
    def create(self, rid, **kw):
        return dt_.document_create_draft(self.pool, self.sys, document_id=kw.pop("document_id", document_id_for(rid)), request_id=rid, template_version_id=self.version_id)

    def test_tao_draft_ghim_che_do_va_mac_dinh_dau(self):
        rid = self.submitted_request()
        made = self.create(rid)
        self.assertEqual((made.created, made.operating_mode, made.revision_round), (True, "NON_PRODUCTION", 0))
        doc = self.document(rid)
        self.assertEqual((doc["status"], doc["operating_mode"], doc["requires_seal"], doc["seal_type"], doc["template_version_id"]), ("DRAFT", "NON_PRODUCTION", True, "ORGANIZATION_ROUND", self.version_id))
        audit = self.rows("select action, actor_kind, payload from audit_event where document_id = %s", document_id_for(rid))
        self.assertEqual([(a, k) for a, k, _ in audit], [("document.create_draft", "SYSTEM")])
        self.assertEqual(audit[0][2]["operating_mode"], "NON_PRODUCTION")

    def test_goi_lai_idempotent_khong_ghi_them(self):
        rid = self.submitted_request()
        self.create(rid)
        again = self.create(rid)
        self.assertEqual((again.created, again.operating_mode), (False, "NON_PRODUCTION"))
        self.assertEqual(self.scalar("select count(*) from document where request_id = %s", rid), 1)
        self.assertEqual(self.scalar("select count(*) from audit_event where document_id = %s", document_id_for(rid)), 1)

    def test_request_chua_submitted_bi_tu_choi(self):
        from tests.request_support import build_request
        rid = build_request(self.pool, self.db, self.eid, self.ctx)
        with self.assertRaises(dt_.RequestNotSubmitted):
            self.create(rid)
        self.assertEqual(self.scalar("select count(*) from document where request_id = %s", rid), 0)

    def test_document_thu_hai_cua_cung_request_la_xung_dot(self):
        rid = self.submitted_request()
        self.create(rid)
        with self.assertRaises(dt_.DocumentConflict):
            self.create(rid, document_id=uuid.uuid4())
        other = self.submitted_request()
        with self.assertRaises(dt_.DocumentConflict):  # id đã là document của request khác
            self.create(other, document_id=document_id_for(rid))

    def test_request_khong_ton_tai(self):
        with self.assertRaises(dt_.DocumentConflict):
            self.create(uuid.uuid4())

    def test_chi_tac_nhan_he_thong(self):
        rid = self.submitted_request()
        with self.assertRaises(SystemActorRequired):
            dt_.document_create_draft(self.pool, self.ctx, document_id=document_id_for(rid), request_id=rid, template_version_id=self.version_id)


class DraftSave(DocBase):
    def draft(self):
        rid = self.submitted_request()
        dt_.document_create_draft(self.pool, self.sys, document_id=document_id_for(rid), request_id=rid, template_version_id=self.version_id)
        return rid, document_id_for(rid)

    def save(self, did, **kw):
        args = dict(document_id=did, variable_name="purpose_statement", revision_round=0, attempt_no=1, body=BODY_OK, validation_outcome="PASSED", prompt_module_version="1.0",
                    input_fingerprint=b"\x01" * 32, fingerprint_key_id=dds.KEY_ID)
        args.update(kw)
        return dds.document_draft_save(self.pool, self.sys, **args)

    def test_ghi_mot_lan_khong_de_len(self):
        _, did = self.draft()
        self.assertTrue(self.save(did).created)
        self.assertFalse(self.save(did, body="Văn bản khác hẳn ở lần ghi thứ hai của cùng khoá.").created)
        rows = self.rows("select body, validation_outcome from document_free_content where document_id = %s", did)
        self.assertEqual(rows, [(BODY_OK, "PASSED")])
        self.assertTrue(self.save(did, attempt_no=2, validation_outcome="FAILED").created)  # lần sinh lại là dòng riêng
        self.assertEqual(self.scalar("select count(*) from document_free_content where document_id = %s", did), 2)

    def test_chan_cung_khi_khong_o_draft_va_sai_vong(self):
        rid, did = self.draft()
        with self.assertRaises(dds.RoundMismatch):
            self.save(did, revision_round=1)
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("update document set status = 'PENDING_APPROVAL' where id = %s", (did,))
        with self.assertRaises(dds.NotDraft):
            self.save(did)
        self.assertEqual(self.scalar("select count(*) from document_free_content where document_id = %s", did), 0)

    def test_tham_so_sai_va_document_khong_ton_tai(self):
        _, did = self.draft()
        for bad in (dict(attempt_no=3), dict(validation_outcome="OK"), dict(body="")):
            with self.assertRaises(ValueError, msg=bad):
                self.save(did, **bad)
        with self.assertRaises(dds.DocumentNotFound):
            self.save(uuid.uuid4())

    def test_audit_khong_mang_van_ban(self):
        _, did = self.draft()
        self.save(did)
        blob = repr(self.rows("select payload from audit_event where action = 'document.draft_save' and document_id = %s", did))
        self.assertNotIn(BODY_OK, blob)
        self.assertIn("purpose_statement", blob)

    def test_chi_tac_nhan_he_thong(self):
        _, did = self.draft()
        with self.assertRaises(SystemActorRequired):
            dds.document_draft_save(self.pool, self.ctx, document_id=did, variable_name="purpose_statement", revision_round=0, attempt_no=1, body=BODY_OK, validation_outcome="PASSED",
                                    prompt_module_version="1.0", input_fingerprint=b"x" * 32)


class Fingerprint(DocBase):
    def test_co_khoa_tat_dinh_va_khong_lo_khoa(self):
        a, b = dds.InputFingerprinter(FINGERPRINT_KEY), dds.InputFingerprinter(FINGERPRINT_KEY + "x")
        inputs = {"purpose": PURPOSE, "variable_guidance": "g", "request_type": "WORK_CONFIRMATION"}
        self.assertEqual(a.digest("purpose_statement", inputs), a.digest("purpose_statement", dict(reversed(list(inputs.items())))))
        self.assertEqual(len(a.digest("purpose_statement", inputs)), 32)
        self.assertNotEqual(a.digest("purpose_statement", inputs), b.digest("purpose_statement", inputs))  # khác khoá, khác dấu vân tay
        self.assertNotEqual(a.digest("purpose_statement", inputs), a.digest("khac", inputs))
        self.assertNotEqual(a.digest("purpose_statement", inputs), a.digest("purpose_statement", {**inputs, "purpose": PURPOSE + "."}))
        self.assertNotIn(FINGERPRINT_KEY, repr(a))
        self.assertEqual(a.key_id, "render-fp-v1")

    def test_khong_phai_bam_tran(self):
        import hashlib
        import json
        a = dds.InputFingerprinter(FINGERPRINT_KEY)
        inputs = {"purpose": PURPOSE}
        plain = hashlib.sha256(json.dumps({"variable_name": "purpose_statement", "inputs": inputs}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).digest()
        self.assertNotEqual(a.digest("purpose_statement", inputs), plain)  # đoán ngược được nếu băm trần (ADR-009)

    def test_khoa_la_hmac_truc_tiep_khong_dan_xuat_tu_secret_phien(self):
        """A-097 (PO, 2026-10-15): khoá riêng, đưa thẳng vào HMAC-SHA256 — đổi bất kỳ secret nào khác không làm đổi dấu vân tay."""
        import hashlib
        import hmac
        import json
        inputs = {"purpose": PURPOSE}
        canonical = json.dumps({"variable_name": "purpose_statement", "inputs": inputs}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(FINGERPRINT_KEY.encode(), canonical.encode(), hashlib.sha256).digest()
        self.assertEqual(dds.InputFingerprinter(FINGERPRINT_KEY).digest("purpose_statement", inputs), expected)
        self.assertFalse(hasattr(dds, "_hkdf_sha256"))
        with self.assertRaises(ValueError):
            dds.InputFingerprinter("")


class Values(DocBase):
    def ready(self):
        rid = self.submitted_request()
        did = document_id_for(rid)
        dt_.document_create_draft(self.pool, self.sys, document_id=did, request_id=rid, template_version_id=self.version_id)
        dds.document_draft_save(self.pool, self.sys, document_id=did, variable_name="purpose_statement", revision_round=0, attempt_no=1, body=BODY_OK, validation_outcome="PASSED",
                                prompt_module_version="1.0", input_fingerprint=b"\x02" * 32)
        return rid, did

    def build(self, did) -> rv.BuiltValues:
        return rv.render_values_build(self.pool, self.sys, document_id=did)

    def test_day_du_la_san_sang_va_bien_dien_sau_duyet_la_dau_giu_cho(self):
        rid, did = self.ready()
        built = self.build(did)
        self.assertEqual(built.issues, ())
        self.assertEqual(set(built.values), {v[0] for v in VARIABLES})
        self.assertEqual(built.values["recipient_org"], RECIPIENT)
        self.assertEqual(built.values["purpose_statement"], BODY_OK)
        self.assertEqual(built.values["document_number"], "[Số văn bản — cấp khi phát hành]")  # A-098 (PO, 2026-10-15): nhìn ra ngay là chưa chính thức
        self.assertEqual(built.values["issued_date"], "[Ngày ban hành — cấp khi phát hành]")
        self.assertEqual(built.values["signer_user_id"], "[Người ký — cấp khi phát hành]")
        for name in ("document_number", "issued_date", "signer_user_id"):
            self.assertEqual(built.values[name], provisional.marker_for(name))
            self.assertTrue(provisional.contains_marker(built.values[name]))
        self.assertTrue(rrc.review_readiness_check(self.pool, self.sys, document_id=did).ok)

    def test_thieu_noi_dung_tu_do(self):
        rid = self.submitted_request()
        did = document_id_for(rid)
        dt_.document_create_draft(self.pool, self.sys, document_id=did, request_id=rid, template_version_id=self.version_id)
        built = self.build(did)
        self.assertEqual([(i.code, i.variable) for i in built.issues], [(rv.VARIABLE_MISSING, "purpose_statement")])
        self.assertNotIn("purpose_statement", built.values)  # vắng mặt, không điền chỗ trống

    def test_ho_so_nhan_su_chua_xac_nhan_la_wrong_source(self):
        rid, did = self.ready()
        with self.db.connect(autocommit=True) as c:
            c.execute("update request_slot set value_status = 'PROPOSED', confirmed_at = null where request_id = %s and slot_name = 'full_name'", (rid,))
        built = self.build(did)
        self.assertEqual([(i.code, i.variable) for i in built.issues], [(rv.WRONG_SOURCE, "full_name")])
        self.assertNotIn("full_name", built.values)

    def test_slot_bi_xoa_la_thieu(self):
        rid, did = self.ready()
        with self.db.connect(autocommit=True) as c:
            c.execute("update request_slot set value_status = 'ERASED', value = null, value_erased_at = now(), confirmed_at = null where request_id = %s and slot_name = 'job_title'", (rid,))
        self.assertEqual([(i.code, i.variable) for i in self.build(did).issues], [(rv.VARIABLE_MISSING, "job_title")])

    def test_gia_tri_slot_la_placeholder_va_noi_dung_tu_do_chua_cau_khung(self):
        rid, did = self.ready()
        with self.db.connect(autocommit=True) as c:
            c.execute("update request_slot set value = to_jsonb('N/A'::text) where request_id = %s and slot_name = 'department_name'", (rid,))
            c.execute("insert into document_free_content (id, document_id, variable_name, revision_round, attempt_no, template_version_id, body, validation_outcome, prompt_module_version, input_fingerprint, fingerprint_key_id) "
                      "values (%s, %s, 'purpose_statement', 0, 2, %s, 'Kính gửi Ngân hàng ABC xin xem xét hồ sơ của nhân viên.', 'PASSED', '1.0', %s, 'k')", (uuid.uuid4(), did, self.version_id, b"\x03" * 32))
        codes = {(i.code, i.variable) for i in self.build(did).issues}
        self.assertEqual(codes, {(rv.PLACEHOLDER_VALUE, "department_name"), (rv.FRAME_TEXT_IN_VARIABLE, "purpose_statement")})

    def test_lan_sinh_hien_hanh_la_passed_lon_nhat_va_failed_khong_dung(self):
        rid, did = self.ready()
        with self.db.connect(autocommit=True) as c:
            c.execute("insert into document_free_content (id, document_id, variable_name, revision_round, attempt_no, template_version_id, body, validation_outcome, prompt_module_version, input_fingerprint, fingerprint_key_id) "
                      "values (%s, %s, 'purpose_statement', 0, 2, %s, 'Bản FAILED của lần sinh lại không được dùng làm giá trị hiện hành.', 'FAILED', '1.0', %s, 'k')", (uuid.uuid4(), did, self.version_id, b"\x04" * 32))
        self.assertEqual(self.build(did).values["purpose_statement"], BODY_OK)

    def test_dinh_dang_date_va_kieu_chua_ho_tro(self):
        from tests.doc_support import template_docx
        retire_active_templates(self.db)
        variables = VARIABLES + (("start_date", "DIRECT_SLOT", "employment_start_date", False, None, None, ()), ("contract", "DIRECT_SLOT", "contract_type", False, None, None, ()))
        vid = make_template(self.db, self.pool, self.storage, variables=variables, data=template_docx())
        self.version_id = vid
        rid = self.submitted_request()
        did = document_id_for(rid)
        dt_.document_create_draft(self.pool, self.sys, document_id=did, request_id=rid, template_version_id=vid)
        built = self.build(did)
        self.assertEqual(built.values["start_date"], "01/01/2020")  # 2020-01-01 trong employee giả của test
        self.assertNotIn("contract", built.values)  # ENUM chưa hỗ trợ (A-098): không đoán câu chữ
        self.assertIn((rv.VARIABLE_MISSING, "contract"), {(i.code, i.variable) for i in built.issues})

    def test_seal_chua_xac_dinh_va_template_het_hieu_luc(self):
        rid, did = self.ready()
        with self.db.connect(autocommit=True) as c:
            c.execute("update document set requires_seal = null, seal_type = null where id = %s", (did,))
        self.assertEqual({i.code for i in self.build(did).issues}, {rv.SEAL_UNDETERMINED})
        with self.db.connect(autocommit=True) as c:
            c.execute("update document set requires_seal = true, seal_type = 'ORGANIZATION_ROUND' where id = %s", (did,))
            c.execute("set session_replication_role = replica")
            c.execute("update template_version set status = 'RETIRED', retired_at = now() where id = %s", (self.version_id,))
        self.assertEqual({i.code for i in self.build(did).issues}, {rv.TEMPLATE_NOT_ACTIVE_AT_RENDER})

    def test_gia_tri_khong_vao_repr(self):
        rid, did = self.ready()
        text = repr(self.build(did))
        for secret in (BODY_OK, RECIPIENT, PURPOSE):
            self.assertNotIn(secret, text)

    def test_document_khong_ton_tai_va_chi_he_thong(self):
        with self.assertRaises(rv.DocumentNotFound):
            self.build(uuid.uuid4())
        with self.assertRaises(SystemActorRequired):
            rv.render_values_build(self.pool, self.ctx, document_id=uuid.uuid4())


class SubmitForReview(DocBase):
    def rendered(self):
        rid = self.submitted_request()
        did = document_id_for(rid)
        dt_.document_create_draft(self.pool, self.sys, document_id=did, request_id=rid, template_version_id=self.version_id)
        dds.document_draft_save(self.pool, self.sys, document_id=did, variable_name="purpose_statement", revision_round=0, attempt_no=1, body=BODY_OK, validation_outcome="PASSED",
                                prompt_module_version="1.0", input_fingerprint=b"\x05" * 32)
        built = rv.render_values_build(self.pool, self.sys, document_id=did)
        docx = docx_render(self.pool, self.storage, self.sys, document_id=did, render_kind="DRAFT", values=built.values)
        pdf = pdf_export(self.pool, self.storage, self.sys, docx)
        return rid, did, pdf

    def test_mot_giao_dich_du_bon_viec_va_idempotent(self):
        rid, did, pdf = self.rendered()
        out = dt_.document_submit_for_review(self.pool, self.sys, document_id=did, draft_pdf_key=pdf.pdf_key)
        self.assertFalse(out.already)
        self.assertEqual(out.render_id, pdf.render_id)
        self.assertEqual(self.document(rid)["status"], "PENDING_APPROVAL")
        self.assertEqual(self.document(rid)["current_draft_render_id"], pdf.render_id)
        self.assertEqual(self.scalar("select status from request where id = %s", rid), "IN_REVIEW")
        self.assertEqual(self.rows("select step_kind, status from approval_step where document_id = %s", did), [("CONTENT_REVIEW", "OPEN")])
        again = dt_.document_submit_for_review(self.pool, self.sys, document_id=did, draft_pdf_key=pdf.pdf_key)
        self.assertEqual((again.already, again.approval_step_id), (True, out.approval_step_id))
        self.assertEqual(self.scalar("select count(*) from approval_step where document_id = %s", did), 1)

    def test_tu_chay_lai_readiness_not_ready_khong_ghi_gi(self):
        rid, did, pdf = self.rendered()
        with self.db.connect(autocommit=True) as c:  # sau khi render, một slot HR bị đưa về chưa xác nhận
            c.execute("update request_slot set value_status = 'PROPOSED', confirmed_at = null where request_id = %s and slot_name = 'full_name'", (rid,))
        with self.assertRaises(dt_.NotReady) as cm:
            dt_.document_submit_for_review(self.pool, self.sys, document_id=did, draft_pdf_key=pdf.pdf_key)
        self.assertEqual(cm.exception.codes, ("WRONG_SOURCE",))
        self.assertEqual(self.document(rid)["status"], "DRAFT")
        self.assertEqual(self.scalar("select count(*) from approval_step where document_id = %s", did), 0)
        self.assertEqual(self.scalar("select status from request where id = %s", rid), "SUBMITTED")
        self.assertNotIn("NGƯỜI GIẢ", repr(cm.exception.issues))

    def test_render_la_khong_thuoc_document_hoac_khong_co(self):
        rid, did, pdf = self.rendered()
        with self.assertRaises(dt_.DraftRenderNotFound):
            dt_.document_submit_for_review(self.pool, self.sys, document_id=did, draft_pdf_key="renders/khong-co.pdf")
        with self.assertRaises(dt_.DocumentNotFound):
            dt_.document_submit_for_review(self.pool, self.sys, document_id=uuid.uuid4(), draft_pdf_key=pdf.pdf_key)

    def test_khong_o_draft_va_khong_phai_tac_nhan_he_thong(self):
        rid, did, pdf = self.rendered()
        with self.db.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("update document set status = 'REJECTED' where id = %s", (did,))
        with self.assertRaises(dt_.NotDraft):
            dt_.document_submit_for_review(self.pool, self.sys, document_id=did, draft_pdf_key=pdf.pdf_key)
        with self.assertRaises(SystemActorRequired):
            dt_.document_submit_for_review(self.pool, self.ctx, document_id=did, draft_pdf_key=pdf.pdf_key)


class Reads(DocBase):
    def test_bon_phep_doc_nho(self):
        rid = self.submitted_request(national_id=NATIONAL_ID)
        did = document_id_for(rid)
        self.assertEqual(reads.request_header_read(self.pool, self.sys, request_id=rid), reads.RequestHeader("WORK_CONFIRMATION", "SUBMITTED"))
        with self.assertRaises(reads.RequestNotFound):
            reads.request_header_read(self.pool, self.sys, request_id=uuid.uuid4())
        dt_.document_create_draft(self.pool, self.sys, document_id=did, request_id=rid, template_version_id=self.version_id)
        header = reads.document_header_read(self.pool, self.sys, document_id=did)
        self.assertEqual((header.status, header.revision_round, header.template_version_id), ("DRAFT", 0, self.version_id))
        self.assertEqual(reads.free_content_attempts_read(self.pool, self.sys, document_id=did, revision_round=0), {})
        dds.document_draft_save(self.pool, self.sys, document_id=did, variable_name="purpose_statement", revision_round=0, attempt_no=1, body=BODY_OK, validation_outcome="FAILED",
                                prompt_module_version="1.0", input_fingerprint=b"\x06" * 32)
        self.assertEqual(reads.free_content_attempts_read(self.pool, self.sys, document_id=did, revision_round=0), {"purpose_statement": ((1, "FAILED"),)})
        self.assertEqual(reads.free_content_attempts_read(self.pool, self.sys, document_id=did, revision_round=1), {})
        res = reads.request_res_slots_read(self.pool, self.sys, request_id=rid)
        self.assertEqual(res["national_id"], NATIONAL_ID)
        self.assertEqual(res["purpose"], PURPOSE)
        self.assertNotIn("full_name", res)  # PER, không phải RES
        with self.assertRaises(reads.DecisionNotFound):
            reads.decision_record_read(self.pool, self.sys, decision_record_id=uuid.uuid4(), document_id=did)

    def test_chi_tac_nhan_he_thong(self):
        for call in (lambda: reads.request_header_read(self.pool, self.ctx, request_id=uuid.uuid4()),
                     lambda: reads.document_header_read(self.pool, self.ctx, document_id=uuid.uuid4()),
                     lambda: reads.free_content_attempts_read(self.pool, self.ctx, document_id=uuid.uuid4(), revision_round=0),
                     lambda: reads.decision_record_read(self.pool, self.ctx, decision_record_id=uuid.uuid4(), document_id=uuid.uuid4()),
                     lambda: reads.request_res_slots_read(self.pool, self.ctx, request_id=uuid.uuid4())):
            with self.assertRaises(SystemActorRequired):
                call()
        employee = ToolContext.create(Actor.employee(self.eid, {"request.read_all", "document.issue"}))
        with self.assertRaises(SystemActorRequired):
            reads.request_header_read(self.pool, employee, request_id=uuid.uuid4())
