"""`finalize_issue` (B9b2, ADR-041) qua thao tác cổng THẬT và `Dispatcher` thật — PostgreSQL, SeaweedFS, `soffice` và checkpointer THẬT; provider LLM là transport giả. Định dạng số là GIẢ của fixture.

Điều được chứng minh, nói bằng hành vi:
- **đường thẳng (có dấu và không dấu):** lệnh phát hành → worker chạy `finalize_issue` → `document` `ISSUED` với số `TRIAL` từ `document_register`, `request` `FULFILLED`, thread `ENDED`; bản `FINAL` là PDF/DOCX thật
  in số, ngày `dd/mm/yyyy` và **họ tên + chức danh của người đã ký** (không in mã nhân viên), watermark thử nghiệm giữ nguyên; hai object mang metadata `ISSUED` + số, bản nháp thì không; bản `FINAL` được ghim `ISSUED`,
  bản nháp ghim `APPROVED_CONTENT`; `audit_event` của việc chuyển `ISSUED` mang người ra lệnh; checkpoint không chứa số hay tên người ký (ADR-008);
- **số liên tiếp:** hai văn bản phát hành lần lượt nhận 001 và 002, không lỗ;
- **chạy lại sau khi xong là no-op** (không số mới, không audit thêm);
- **`approved_content_hash` lệch dừng TRƯỚC khi cấp số** (INV-01): job `FAILED` `CONTENT_HASH_MISMATCH` ngay, không dòng sổ, không bộ đếm, không bản `FINAL`, `document` ở `SEALED`;
- **lỗi vĩnh viễn sau khi đã có số** (dấu giữ chỗ còn sót ở khung template): job `FAILED`, số `VOIDED` kèm lý do, không bản `FINAL` nào được ghi, `document` ở `SEALED`;
- **lỗi tạm còn lượt:** số GIỮ NGUYÊN (không `VOIDED`); lần thử sau phát hành với đúng số đó, bộ đếm chỉ tăng một lần; ở cả hai chỗ hỏng (chuyển PDF, kiểm byte);
- **hết lượt vì lỗi tạm:** số `VOIDED` với lý do `ISSUE_RETRIES_EXHAUSTED`, job `FAILED` giữ mã lỗi gốc.

Cần BO19_TEST_PG_SUPERUSER_DSN, BO19_TEST_S3_*, `soffice` (image target `test`). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_finalize_issue -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import io
import re
import unittest
import uuid
from unittest import mock

from docx import Document

from bo19.orchestrator.runner import document_id_for
from bo19.tool_layer.kernel.permission import employee_context
from bo19.tool_layer.rendering.watermark import WATERMARK_TEXT
from bo19.tool_layer.tools._common import ToolError
from bo19.tool_layer.tools.render_integrity_check import RenderChecksumMismatch
from tests.doc_support import BODY_OK, NATIONAL_ID, make_template, retire_active_templates, template_docx
from tests.render_support import pdf_text, pdfinfo_fields
from tests.test_document_gates_graph import GateGraphBase

SIGNER_NAME, SIGNER_TITLE = "NGUYỄN VĂN KÝ (GIẢ)", "Trưởng phòng Hành chính (giả)"
NODES = "bo19.orchestrator.document_graph.nodes"


class ConversionFailed(ToolError):
    code = "CONVERSION_FAILED"  # lỗi tạm theo `failure.classify`


class FinalizeBase(GateGraphBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with cls.db.connect("bo19_migrator", autocommit=True) as c:
            reg = c.execute("select document_register_id from request_type where code = 'WORK_CONFIRMATION'").fetchone()[0]
            c.execute("delete from document_register_format")  # data migration 0003 đã nạp khuôn số thật (M1.2); fixture dùng khuôn GIẢ của riêng nó
            c.execute("insert into document_register_format (id, document_register_id, series, format_pattern, symbol, seq_min_digits, effective_from) "
                      "values (%s, %s, 'TRIAL', 'TRIAL-{seq}/{year}/{symbol}', 'THU-NGHIEM', 3, timestamptz '2020-01-01 00:00:00+00')", (uuid.uuid4(), reg))

    def setUp(self):
        super().setUp()
        with self.db.connect(autocommit=True) as c:  # mỗi test một bộ đếm sạch: số kỳ vọng tính từ 001 (siêu người dùng + replica: văn bản ISSUED của test trước còn trỏ tới dòng sổ)
            c.execute("set session_replication_role = replica")
            c.execute("delete from document_register_entry")
            c.execute("delete from document_register_counter")

    # ---- dựng ----------------------------------------------------------------------------------------------------------------

    def to_sealed(self, *, seal: bool = True):
        """Một `request` đi hết ba cổng bằng thao tác thật và worker thật, dừng chờ lệnh phát hành. Trả (rid, signer_id) — người ký là người `signing_route` THỰC SỰ giao (mã nhỏ nhất trong DB của lớp), đặt tên và chức danh có dấu để so với bản `FINAL`."""
        self.signer()  # bảo đảm có ít nhất một người mang document.sign
        rid = self.waiting()
        if not seal:
            with self.db.connect("bo19_migrator") as c:
                c.execute("update document set requires_seal = false, seal_type = null where id = %s", (document_id_for(rid),))
        self.approve(rid)
        self.drain()
        signer_id = self.scalar("select signer_employee_id from document where id = %s", document_id_for(rid))
        with self.db.connect("bo19_migrator") as c:
            c.execute("update employee set full_name = %s, job_title = %s where id = %s", (SIGNER_NAME, SIGNER_TITLE, signer_id))
        with self.pool.acquire() as conn:
            sctx = employee_context(conn, signer_id)
        self.sign(rid, sctx)
        self.drain()
        if seal:
            self.seal(rid)
            self.drain()
        self.assertEqual(self.at(rid), ("WAITING", "await_issue"))
        return rid, signer_id

    def order(self, rid) -> uuid.UUID:
        return self.issue(rid)

    def final_render(self, rid) -> tuple:
        return self.rows("select id, docx_object_key, pdf_object_key, watermark_text from document_render where document_id = %s and render_kind = 'FINAL'", document_id_for(rid))

    def entries(self, rid) -> list[tuple]:
        return self.rows("select seq, formatted_number, status, void_reason from document_register_entry where document_id = %s order by seq", document_id_for(rid))

    def fetch(self, key: str) -> bytes:
        return self.raw.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def make_job_runnable(self, rid):
        with self.db.connect("bo19_migrator") as c:
            c.execute("update job set run_after = now() where subject_document_id = %s and job_type = 'finalize_issue' and status = 'QUEUED'", (document_id_for(rid),))


class DuongThang(FinalizeBase):
    def test_co_dau_phat_hanh_so_trial_ban_final_ten_va_chuc_danh_nguoi_ky(self):
        rid, signer_id = self.to_sealed()
        did = document_id_for(rid)
        issuer_decision = self.order(rid)
        self.assertEqual(self.status(rid), "SEALED")  # lệnh chưa đổi trạng thái
        self.assertEqual(self.entries(rid), [])  # và chưa cấp số
        self.assertEqual(self.drain(), 1)

        self.assertEqual(self.status(rid), "ISSUED")
        self.assertEqual(self.scalar("select status from request where id = %s", rid), "FULFILLED")
        self.assertEqual(self.at(rid)[0], "ENDED")
        self.assertEqual(self.jobs(rid, "finalize_issue"), [("SUCCEEDED", 1, None)])

        (seq, number, status, void_reason), = self.entries(rid)
        year = self.scalar("select extract(year from (assigned_at at time zone 'Asia/Ho_Chi_Minh'))::int from document_register_entry where document_id = %s", did)
        self.assertEqual((seq, number, status, void_reason), (1, f"TRIAL-001/{year}/THU-NGHIEM", "ASSIGNED", None))
        self.assertEqual(self.scalar("select series from document_register_entry where document_id = %s", did), "TRIAL")
        self.assertEqual(self.scalar("select issue_decision_id from document_register_entry where document_id = %s", did), issuer_decision)
        row = self.rows("select issued_register_entry_id is not null, final_render_id is not null, issued_date, issued_at is not null from document where id = %s", did)[0]
        self.assertEqual((row[0], row[1], row[3]), (True, True, True))
        issued_date = row[2].strftime("%d/%m/%Y")

        (render_id, docx_key, pdf_key, watermark), = self.final_render(rid)
        self.assertEqual(self.scalar("select final_render_id from document where id = %s", did), render_id)
        self.assertEqual(self.rows("select pin_reason, decision_record_id from document_render_pin where render_id = %s", render_id), [("ISSUED", issuer_decision)])
        self.assertEqual(self.rows("select pin_reason from document_render_pin p join document_render r on r.id = p.render_id where r.document_id = %s and r.render_kind = 'DRAFT'", did), [("APPROVED_CONTENT",)])
        self.assertEqual(watermark, WATERMARK_TEXT)

        # bản FINAL: số, ngày, HỌ TÊN + CHỨC DANH người ký; không mã nhân viên, không dấu giữ chỗ
        signer_code = self.scalar("select employee_code from employee where id = %s", signer_id)
        text = pdf_text(self.fetch(pdf_key))
        flat = re.sub(r"\s+", " ", text)
        self.assertIn(number, flat)
        self.assertIn(issued_date, flat)
        self.assertIn(f"{SIGNER_NAME}, {SIGNER_TITLE}", flat)
        self.assertNotIn(signer_code, flat)
        self.assertNotIn("cấp khi phát hành", flat)
        self.assertIn(BODY_OK, flat)
        self.assertEqual(pdfinfo_fields(self.fetch(pdf_key))["Subject"], WATERMARK_TEXT)  # watermark thử nghiệm giữ nguyên ở bản FINAL
        paragraphs = [p.text for p in Document(io.BytesIO(self.fetch(docx_key))).paragraphs]
        self.assertIn(f"Số: {number} ngày {issued_date} — người ký {SIGNER_NAME}, {SIGNER_TITLE}", paragraphs)

        # metadata của bản ghim ISSUED nằm trong CÙNG lệnh PUT: hai object FINAL có, bản nháp không
        for key in (docx_key, pdf_key):
            meta = self.raw.head_object(Bucket=self.bucket, Key=key)["Metadata"]
            iso = "-".join(reversed(issued_date.split("/")))  # `issued_date` in trên văn bản là dd/mm/yyyy; metadata mang ISO yyyy-mm-dd (số không có năm nên đối soát cần ngày — ADR-043)
            self.assertEqual(meta, {"bo19-pin-reason": "ISSUED", "bo19-document-number": number, "bo19-issued-date": iso}, key)
        draft_keys = self.rows("select docx_object_key, pdf_object_key from document_render where document_id = %s and render_kind = 'DRAFT'", did)[0]
        for key in draft_keys:
            self.assertEqual(self.raw.head_object(Bucket=self.bucket, Key=key)["Metadata"], {}, key)

        # audit: tác nhân của việc chuyển ISSUED là người ra lệnh
        officer_id = self.officer_id
        ev = self.rows("select actor_kind, actor_employee_id, decision_record_id, payload from audit_event where document_id = %s and action = 'document.issue_complete'", did)
        self.assertEqual([(e[0], e[1], e[2], e[3]["executed_by"]) for e in ev], [("EMPLOYEE", officer_id, issuer_decision, "SYSTEM")])
        self.assertEqual(self.scalar("select count(*) from audit_event where document_id = %s and action = 'document.number_assign'", did), 1)

        # không gọi LLM lại, không render nháp lại, mỗi loại một bản
        self.assertEqual(self.llm_calls(), 1)
        self.assertEqual(self.scalar("select count(*) from document_render where document_id = %s and render_kind = 'DRAFT'", did), 1)
        # ADR-008: checkpoint không chứa số, tên người ký hay văn bản
        blob = self.checkpoint_text()
        for secret in (number, SIGNER_NAME, SIGNER_TITLE, BODY_OK, NATIONAL_ID):
            self.assertNotIn(secret, blob)

    def test_khong_can_dau_signed_toi_issued(self):
        rid, _ = self.to_sealed(seal=False)
        self.assertEqual(self.status(rid), "SIGNED")
        self.order(rid)
        self.assertEqual(self.drain(), 1)
        self.assertEqual((self.status(rid), self.scalar("select status from request where id = %s", rid)), ("ISSUED", "FULFILLED"))
        self.assertEqual([(e[0], e[2]) for e in self.entries(rid)], [(1, "ASSIGNED")])

    def test_hai_van_ban_hai_so_lien_tiep_khong_lo(self):
        first, _ = self.to_sealed()
        self.order(first)
        self.drain()
        rid, _ = self.to_sealed()
        self.order(rid)
        self.drain()
        self.assertEqual([self.status(first), self.status(rid)], ["ISSUED", "ISSUED"])
        self.assertEqual([e[0] for e in self.entries(first)] + [e[0] for e in self.entries(rid)], [1, 2])
        self.assertEqual([e[1].split("/")[0] for e in self.entries(first)] + [e[1].split("/")[0] for e in self.entries(rid)], ["TRIAL-001", "TRIAL-002"])
        self.assertEqual(self.scalar("select next_seq from document_register_counter"), 3)

    def test_chay_lai_sau_khi_xong_la_no_op(self):
        rid, _ = self.to_sealed()
        decision = self.order(rid)
        self.drain()
        self.assertEqual(self.status(rid), "ISSUED")
        before = (self.entries(rid), self.final_render(rid), self.scalar("select count(*) from audit_event where document_id = %s", document_id_for(rid)))
        out = self.runner.run_finalize_issue(document_id=document_id_for(rid), decision_record_id=decision)
        self.assertEqual((out.status, out.already), ("ENDED", True))
        self.assertEqual((self.entries(rid), self.final_render(rid), self.scalar("select count(*) from audit_event where document_id = %s", document_id_for(rid))), before)


class HuyTruocKhiCapSo(FinalizeBase):
    def test_hash_lech_dung_truoc_khi_cap_so(self):
        rid, _ = self.to_sealed()
        did = document_id_for(rid)
        with self.db.connect("bo19_migrator") as c:
            c.execute("update document_free_content set body = body || ' (đã sửa sau khi duyệt)' where document_id = %s", (did,))
        self.order(rid)
        self.assertEqual(self.drain(), 1)
        self.assertEqual(self.jobs(rid, "finalize_issue"), [("FAILED", 1, "CONTENT_HASH_MISMATCH")])  # vĩnh viễn: không thử lại
        self.assertEqual(self.entries(rid), [])  # CHƯA có số
        self.assertEqual(self.scalar("select count(*) from document_register_counter"), 0)
        self.assertEqual(self.final_render(rid), [])
        self.assertEqual(self.status(rid), "SEALED")
        self.assertEqual(self.scalar("select status from request where id = %s", rid), "APPROVED")
        self.assertEqual(self.scalar("select count(*) from audit_event where document_id = %s and action = 'document.number_void'", did), 0)


class SauKhiCoSo(FinalizeBase):
    def test_dau_giu_cho_con_sot_o_khung_template_thi_huy_so_va_khong_ghi_ban_final(self):
        retire_active_templates(self.db)
        make_template(self.db, self.pool, self.storage, data=template_docx(extra=("[Số văn bản — cấp khi phát hành]",)))  # bản nháp được phép mang dấu; bản FINAL thì không (A-098)
        rid, _ = self.to_sealed()
        self.order(rid)
        self.assertEqual(self.drain(), 1)
        self.assertEqual(self.jobs(rid, "finalize_issue"), [("FAILED", 1, "PLACEHOLDER_REMAINS")])
        (seq, _number, status, void_reason), = self.entries(rid)
        self.assertEqual((seq, status, void_reason), (1, "VOIDED", "PLACEHOLDER_REMAINS"))
        self.assertEqual(self.final_render(rid), [])
        self.assertEqual(self.status(rid), "SEALED")
        self.assertEqual(self.scalar("select status from request where id = %s", rid), "APPROVED")
        self.assertEqual(self.scalar("select count(*) from document_render_pin p join document_render r on r.id = p.render_id where r.document_id = %s and p.pin_reason = 'ISSUED'", document_id_for(rid)), 0)
        self.assertEqual(self.scalar("select severity from audit_event where document_id = %s and action = 'document.number_void'", document_id_for(rid)), "WARNING")
        # không object FINAL nào được ghi (lỗi xảy ra TRƯỚC khi ghi)
        keys = [o["Key"] for o in self.raw.list_objects_v2(Bucket=self.bucket, Prefix=f"renders/{document_id_for(rid)}/").get("Contents", [])]
        self.assertEqual(len(keys), 2)  # chỉ cặp .docx/.pdf của bản nháp

    def test_bien_dien_sau_duyet_khong_co_nguon_thi_huy_so_va_khong_ghi_ban_final(self):
        """Template khai một biến điền-sau-duyệt ngoài ba biến hệ thống biết (`document_number`, `issued_date`, `signer_user_id`): không điền bừa — dừng vĩnh viễn, số đã cấp thì `VOIDED`."""
        from tests.doc_support import VARIABLES

        retire_active_templates(self.db)
        make_template(self.db, self.pool, self.storage, variables=(*VARIABLES, ("approver_name", "SYSTEM", None, True, None, None, ())))
        rid, _ = self.to_sealed()
        self.order(rid)
        self.assertEqual(self.drain(), 1)
        self.assertEqual(self.jobs(rid, "finalize_issue"), [("FAILED", 1, "RENDER_INPUT_INVALID")])
        (entry,) = self.entries(rid)
        self.assertEqual((entry[2], entry[3]), ("VOIDED", "RENDER_INPUT_INVALID"))
        self.assertEqual((self.final_render(rid), self.status(rid)), ([], "SEALED"))

    def test_loi_tam_con_luot_giu_so_va_lan_sau_phat_hanh_dung_so_do(self):
        rid, _ = self.to_sealed()
        self.order(rid)
        with mock.patch(f"{NODES}.pdf_export", side_effect=ConversionFailed):
            self.assertEqual(self.drain(), 1)
        self.assertEqual(self.jobs(rid, "finalize_issue"), [("QUEUED", 1, "RENDER_CONVERSION_FAILED")])
        (first,) = self.entries(rid)
        self.assertEqual((first[0], first[2], first[3]), (1, "ASSIGNED", None))  # số GIỮ NGUYÊN, chưa huỷ
        self.assertEqual(self.status(rid), "SEALED")
        self.make_job_runnable(rid)
        self.assertEqual(self.drain(), 1)
        self.assertEqual(self.status(rid), "ISSUED")
        self.assertEqual(self.entries(rid), [first])  # đúng dòng số ấy, không số mới
        self.assertEqual(self.scalar("select next_seq from document_register_counter"), 2)  # bộ đếm chỉ tăng một lần
        self.assertEqual(self.jobs(rid, "finalize_issue"), [("SUCCEEDED", 2, None)])

    def test_kiem_byte_ban_cuoi_hong_la_loi_tam_va_lan_sau_dung_lai_ban_da_ghi(self):
        rid, _ = self.to_sealed()
        self.order(rid)
        with mock.patch(f"{NODES}.render_integrity_check", side_effect=RenderChecksumMismatch):
            self.assertEqual(self.drain(), 1)
        self.assertEqual(self.jobs(rid, "finalize_issue"), [("QUEUED", 1, "RENDER_CHECKSUM_MISMATCH")])
        (render_before,) = self.final_render(rid)  # bản FINAL đã ghi và có dòng document_render, nhưng CHƯA ghim, document CHƯA issued
        self.assertEqual(self.status(rid), "SEALED")
        self.assertEqual(self.scalar("select count(*) from document_render_pin where render_id = %s", render_before[0]), 0)
        self.make_job_runnable(rid)
        self.drain()
        self.assertEqual(self.status(rid), "ISSUED")
        self.assertEqual(self.final_render(rid), [render_before])  # cùng khoá theo input: dùng lại, không ghi bản thứ hai
        self.assertEqual(len(self.entries(rid)), 1)

    def test_het_luot_vi_loi_tam_thi_huy_so_voi_ly_do_het_luot(self):
        rid, _ = self.to_sealed()
        self.order(rid)
        with self.db.connect("bo19_migrator") as c:
            c.execute("update job set max_attempts = 1 where subject_document_id = %s and job_type = 'finalize_issue'", (document_id_for(rid),))
        with mock.patch(f"{NODES}.pdf_export", side_effect=ConversionFailed):
            self.assertEqual(self.drain(), 1)
        self.assertEqual(self.jobs(rid, "finalize_issue"), [("FAILED", 1, "RENDER_CONVERSION_FAILED")])  # mã lỗi gốc giữ nguyên
        (entry,) = self.entries(rid)
        self.assertEqual((entry[2], entry[3]), ("VOIDED", "ISSUE_RETRIES_EXHAUSTED"))
        self.assertEqual(self.status(rid), "SEALED")

    def test_lan_phat_hanh_sau_khi_huy_so_nhan_so_moi(self):
        """Số `VOIDED` không bao giờ dùng lại (ADR-011): gọi lại `finalize_issue` sau khi huỷ cấp số kế tiếp, số cũ giữ nguyên là lỗ hổng có lý do."""
        rid, _ = self.to_sealed()
        decision = self.order(rid)
        with self.db.connect("bo19_migrator") as c:
            c.execute("update job set max_attempts = 1 where subject_document_id = %s and job_type = 'finalize_issue'", (document_id_for(rid),))
        with mock.patch(f"{NODES}.pdf_export", side_effect=ConversionFailed):
            self.drain()
        self.assertEqual([e[2] for e in self.entries(rid)], ["VOIDED"])
        # Sprint 2 sẽ có đường phát hành lại (`RETURN_TO_ISSUE_QUEUE`); ở đây gọi thẳng runner trên cùng lệnh để chứng minh số mới được cấp
        out = self.runner.run_finalize_issue(document_id=document_id_for(rid), decision_record_id=decision)
        self.assertEqual(out.status, "ENDED")
        self.assertEqual([(e[0], e[2]) for e in self.entries(rid)], [(1, "VOIDED"), (2, "ASSIGNED")])
        self.assertEqual(self.status(rid), "ISSUED")


if __name__ == "__main__":
    unittest.main()
