"""`render_integrity_check` (B9b1; mục Tool Registry của 03-agents.md; mục 5.4 của 04-data.md; ADR-040) — PostgreSQL, SeaweedFS và `soffice` THẬT (bản render do đường thật dựng).

Điều được chứng minh, nói bằng hành vi:
- bản render nguyên vẹn qua, và tool đọc lại **cả hai** object (`.docx` và `.pdf`);
- **byte bị sửa** ở object nào (cùng độ dài, khác nội dung) cũng là `RENDER_CHECKSUM_MISMATCH`; **object mất** ở object nào cũng là `RENDER_OBJECT_MISSING` — không phân biệt thứ tự đọc;
- `render_id` lạ là `RenderNotFound`; chỉ tác nhân hệ thống; chỉ đọc (không `audit_event`, không ghi gì);
- hai mã lỗi là lỗi **tạm** theo `failure.classify` (khôi phục byte rồi thử lại, mục Sau khi trượt kiểm của 04-data.md).

Cần BO19_TEST_PG_SUPERUSER_DSN, BO19_TEST_S3_*, `soffice` (image target `test`). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_render_integrity_check -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import uuid

from bo19.orchestrator.document_graph.failure import classify
from bo19.orchestrator.runner import document_id_for
from bo19.tool_layer.kernel.permission import SystemActorRequired
from bo19.tool_layer.tools import render_integrity_check as ric
from tests.doc_support import DocBase, draft_output


class IntegrityCheck(DocBase):
    def rendered(self):
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        self.run_render(rid)
        render_id, docx_key, pdf_key = self.rows("select id, docx_object_key, pdf_object_key from document_render where document_id = %s", document_id_for(rid))[0]
        return rid, render_id, docx_key, pdf_key

    def check(self, render_id):
        return ric.render_integrity_check(self.pool, self.storage, self.sys, render_id=render_id)

    def tamper(self, key):
        size = self.raw.get_object(Bucket=self.bucket, Key=key)["ContentLength"]
        self.raw.put_object(Bucket=self.bucket, Key=key, Body=b"x" * size)  # cùng độ dài, khác nội dung

    def test_nguyen_ven_thi_qua_va_doc_ca_hai_object(self):
        _, render_id, _, _ = self.rendered()
        r = self.check(render_id)
        self.assertEqual((r.render_id, r.objects), (render_id, 2))

    def test_sua_byte_docx_la_checksum_mismatch(self):
        _, render_id, docx_key, _ = self.rendered()
        self.tamper(docx_key)
        with self.assertRaises(ric.RenderChecksumMismatch):
            self.check(render_id)

    def test_sua_byte_pdf_la_checksum_mismatch(self):
        _, render_id, _, pdf_key = self.rendered()
        self.tamper(pdf_key)
        with self.assertRaises(ric.RenderChecksumMismatch):
            self.check(render_id)

    def test_mat_docx_la_object_missing(self):
        _, render_id, docx_key, _ = self.rendered()
        self.raw.delete_object(Bucket=self.bucket, Key=docx_key)
        with self.assertRaises(ric.RenderObjectMissing):
            self.check(render_id)

    def test_mat_pdf_la_object_missing(self):
        _, render_id, _, pdf_key = self.rendered()
        self.raw.delete_object(Bucket=self.bucket, Key=pdf_key)
        with self.assertRaises(ric.RenderObjectMissing):
            self.check(render_id)

    def test_render_la_khong_ton_tai(self):
        with self.assertRaises(ric.RenderNotFound):
            self.check(uuid.uuid4())

    def test_chi_tac_nhan_he_thong(self):
        _, render_id, _, _ = self.rendered()
        with self.assertRaises(SystemActorRequired):
            ric.render_integrity_check(self.pool, self.storage, self.ctx, render_id=render_id)

    def test_chi_doc_khong_ghi_gi(self):
        rid, render_id, _, _ = self.rendered()
        did = document_id_for(rid)
        before = (self.scalar("select count(*) from audit_event where document_id = %s", did), self.scalar("select count(*) from stored_object"), self.scalar("select count(*) from document_render"))
        self.check(render_id)
        self.assertEqual(before, (self.scalar("select count(*) from audit_event where document_id = %s", did), self.scalar("select count(*) from stored_object"), self.scalar("select count(*) from document_render")))

    def test_hai_ma_loi_la_loi_tam_theo_failure_classify(self):
        for code in ("RENDER_CHECKSUM_MISMATCH", "RENDER_OBJECT_MISSING"):
            f = classify(code)
            self.assertEqual((f.reason_code, f.permanent), (code, False))
        self.assertEqual(classify("RENDER_NOT_FOUND").permanent, True)
