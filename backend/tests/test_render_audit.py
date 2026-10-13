"""`tools/render-audit/render_audit.py` — phép kiểm watermark của bản render sau UAT (B9a / M5, ADR-038; mục 18 của 11-ops.md). `soffice`, `pdfinfo`, PostgreSQL, SeaweedFS THẬT.

Điều được chứng minh, nói bằng hành vi:
- **Đạt** khi cả ba chân đạt: DB (`watermark_text`), checksum (byte PDF = `stored_object_commit`), metadata (`pdfinfo` đọc `Subject`);
- **PDF thiếu metadata → báo lỗi** (`PDF_SUBJECT_MISSING`), PDF mang chuỗi khác → `PDF_SUBJECT_MISMATCH`, byte bị đổi → `CHECKSUM_MISMATCH` **và không đọc metadata** của byte lạ;
- cột DB thiếu / khác chuỗi AC-1.3 / có ở `PRODUCTION` → báo lỗi; `Author` không trung lập → báo lỗi;
- **không kiểm được thì mã thoát 2, không bao giờ in "đạt"** (thiếu `pdfinfo`, thiếu biến, DB không với tới); số dòng đã kiểm luôn được in;
- đầu ra không mang nội dung văn bản, giá trị slot hay credential.

Cần BO19_TEST_PG_SUPERUSER_DSN, BO19_TEST_S3_*, `soffice`, `pdfinfo` (image target `test`). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_render_audit -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import hashlib
import importlib.util
import io
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

from docx import Document

from bo19.tool_layer.rendering import convert, docx_fill, watermark
from bo19.tool_layer.rendering.doc_properties import SYSTEM_AUTHOR
from bo19.tool_layer.tools import docx_render as dr
from bo19.tool_layer.tools import pdf_export as pe
from tests.render_support import DECLARED, VALUES, build_template, require_tool
from tests.test_render_tools import RenderBase

TOOL = Path(__file__).resolve().parents[2] / "tools" / "render-audit" / "render_audit.py"
spec = importlib.util.spec_from_file_location("render_audit", TOOL)
ra = importlib.util.module_from_spec(spec)
sys.modules["render_audit"] = ra  # `@dataclass` cần tìm mô-đun của lớp
spec.loader.exec_module(ra)

TEXT = watermark.WATERMARK_TEXT


def build_pdf(mode: str, *, subject: str | None, author: str = SYSTEM_AUTHOR) -> bytes:
    """PDF thật do `soffice` dựng, với `subject`/`author` do test chọn (thay `apply_properties`) — để tạo đúng các ca hỏng."""
    def props(docx: bytes, _text) -> bytes:
        d = Document(io.BytesIO(docx))
        if subject is not None:
            d.core_properties.subject = subject
        d.core_properties.author = author
        buf = io.BytesIO()
        d.save(buf)
        return buf.getvalue()
    with mock.patch.object(docx_fill.doc_properties, "apply_properties", props):
        docx = docx_fill.fill_docx(build_template(), VALUES, declared=DECLARED, operating_mode=mode)
    return convert.convert_to_pdf(docx, timeout_s=300)


def sha(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


class AuditRender(unittest.TestCase):
    """Một dòng `document_render`: mã trượt theo từng chân. Không DB, không storage — chỉ PDF thật và `pdfinfo` thật."""

    @classmethod
    def setUpClass(cls):
        require_tool(cls, "soffice")
        require_tool(cls, "pdfinfo")
        cls.good_np = build_pdf("NON_PRODUCTION", subject=TEXT)
        cls.good_prod = build_pdf("PRODUCTION", subject=None)
        cls.no_subject = build_pdf("NON_PRODUCTION", subject=None)
        cls.other_subject = build_pdf("NON_PRODUCTION", subject="CHUỖI KHÁC HẲN")
        cls.prod_with_subject = build_pdf("PRODUCTION", subject=TEXT)
        cls.foreign_author = build_pdf("NON_PRODUCTION", subject=TEXT, author="Nguyễn Văn Soạn Mẫu")

    def audit(self, pdf, *, mode="NON_PRODUCTION", text=TEXT, checksum=None):
        return ra.audit_render(operating_mode=mode, db_watermark_text=text, expected_checksum=sha(pdf) if checksum is None and pdf is not None else (checksum or b""), pdf=pdf)

    def test_dat_ca_ba_chan(self):
        self.assertEqual(self.audit(self.good_np), [])
        self.assertEqual(self.audit(self.good_prod, mode="PRODUCTION", text=None), [])

    def test_pdf_thieu_metadata_bao_loi(self):
        self.assertEqual(self.audit(self.no_subject), [ra.PDF_SUBJECT_MISSING])

    def test_pdf_mang_chuoi_khac_bao_loi(self):
        self.assertEqual(self.audit(self.other_subject), [ra.PDF_SUBJECT_MISMATCH])
        self.assertEqual(self.audit(self.good_np, text="CHUỖI KHÁC HẲN"), [ra.DB_WATERMARK_MISMATCH, ra.PDF_SUBJECT_MISMATCH])  # PDF đúng chuỗi AC-1.3, cột lại khác

    def test_cot_db_thieu_hoac_khac_chuoi_ac_1_3(self):
        self.assertIn(ra.DB_WATERMARK_MISSING, self.audit(self.good_np, text=None))
        self.assertIn(ra.DB_WATERMARK_MISSING, self.audit(self.good_np, text=""))
        self.assertIn(ra.DB_WATERMARK_MISMATCH, self.audit(self.other_subject, text="CHUỖI KHÁC HẲN"))  # PDF và cột khớp nhau nhưng KHÔNG phải chuỗi của AC-1.3

    def test_production_khong_duoc_mang_watermark(self):
        self.assertEqual(self.audit(self.good_prod, mode="PRODUCTION", text=TEXT), [ra.DB_WATERMARK_UNEXPECTED])
        self.assertEqual(self.audit(self.prod_with_subject, mode="PRODUCTION", text=None), [ra.PDF_SUBJECT_UNEXPECTED])

    def test_checksum_lech_bao_loi_va_khong_doc_metadata_cua_byte_la(self):
        # PDF thiếu metadata nhưng checksum đã lưu là của byte KHÁC: chỉ báo CHECKSUM_MISMATCH, không có mã metadata.
        self.assertEqual(self.audit(self.no_subject, checksum=sha(self.good_np)), [ra.CHECKSUM_MISMATCH])

    def test_khong_tai_duoc_byte(self):
        self.assertEqual(self.audit(None), [ra.PDF_UNAVAILABLE])

    def test_pdf_hong_bao_pdf_unreadable_khong_im_lang(self):
        junk = b"%PDF-1.7 khong phai pdf that " * 20
        self.assertEqual(self.audit(junk), [ra.PDF_UNREADABLE])

    def test_tac_gia_khong_trung_tinh_bao_loi(self):
        self.assertEqual(self.audit(self.foreign_author), [ra.PDF_AUTHOR_NOT_NEUTRAL])

    def test_thieu_pdfinfo_la_khong_kiem_duoc_khong_phai_dat(self):
        with mock.patch.object(ra.shutil, "which", return_value=None):
            with self.assertRaises(ra.CannotCheck):
                self.audit(self.good_np)


@unittest.skipUnless(os.environ.get("BO19_TEST_PG_SUPERUSER_DSN"), "cần BO19_TEST_PG_SUPERUSER_DSN")
class AuditEndToEnd(RenderBase):
    """Chạy `main` thật với biến môi trường, trên dòng `document_render` do `docx_render` + `pdf_export` ghi."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        require_tool(cls, "pdfinfo")

    def env(self, **over) -> dict[str, str]:
        base = {"BO19_DATABASE_URL": self.db.dsn("bo19_app"), "BO19_OBJECT_STORAGE_ENDPOINT_URL": os.environ["BO19_TEST_S3_ENDPOINT"], "BO19_OBJECT_STORAGE_BUCKET": self.bucket,
                "BO19_OBJECT_STORAGE_ACCESS_KEY_ID": os.environ["BO19_TEST_S3_ACCESS_KEY_ID"], "BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY": os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"]}
        base.update(over)
        return {k: v for k, v in base.items() if v is not None}

    def run_audit(self, did: uuid.UUID | None, **env_over) -> tuple[int, str]:
        out = io.StringIO()
        argv = ["--document-id", str(did)] if did else []
        code = ra.main(argv, self.env(**env_over), out)
        return code, out.getvalue()

    def render_pair(self, mode: str = "NON_PRODUCTION") -> tuple[uuid.UUID, pe.PdfExport]:
        did = self.make_document(self.make_template(), mode=mode)
        return did, pe.pdf_export(self.pool, self.storage, self.sys, self.render_docx(did))

    def test_dat_thi_ma_thoat_0_va_in_so_dong_da_kiem(self):
        did, _ = self.render_pair()
        code, text = self.run_audit(did)
        self.assertEqual(code, 0, text)
        self.assertIn("Đã kiểm 1 bản render: 1 đạt, 0 trượt.", text)

    def test_ca_production_cung_dat(self):
        did, _ = self.render_pair("PRODUCTION")
        code, text = self.run_audit(did)
        self.assertEqual((code, "1 đạt, 0 trượt" in text), (0, True), text)

    def test_khong_co_dong_nao_thi_in_0_khong_im_lang(self):
        code, text = self.run_audit(uuid.uuid4())
        self.assertEqual(code, 0)
        self.assertIn("Đã kiểm 0 bản render", text)

    def test_loc_theo_document_chi_kiem_document_do(self):
        a, _ = self.render_pair()
        b, _ = self.render_pair()
        self.assertIn("Đã kiểm 1 bản render", self.run_audit(a)[1])
        self.assertIn("Đã kiểm 1 bản render", self.run_audit(b)[1])

    def test_pdf_bi_thay_bang_pdf_thieu_metadata_va_checksum_khop_bao_loi(self):
        did, out = self.render_pair()
        forged = build_pdf("NON_PRODUCTION", subject=None)  # thiếu metadata
        self.raw.put_object(Bucket=self.bucket, Key=out.pdf_key, Body=forged)
        with self.db.connect(autocommit=True) as c:  # siêu người dùng khớp luôn checksum đã lưu — chỉ còn chân metadata bắt được
            c.execute("update stored_object_commit set checksum_sha256 = %s where object_key = %s", (sha(forged), out.pdf_key))
        code, text = self.run_audit(did)
        self.assertEqual(code, 1, text)
        self.assertIn(ra.PDF_SUBJECT_MISSING, text)
        self.assertIn(f"render_id={out.render_id}", text)
        self.assertIn("0 đạt, 1 trượt", text)

    def test_byte_bi_doi_ma_checksum_khong_doi_bao_checksum_mismatch_thoi(self):
        did, out = self.render_pair()
        self.raw.put_object(Bucket=self.bucket, Key=out.pdf_key, Body=build_pdf("NON_PRODUCTION", subject=None))
        code, text = self.run_audit(did)
        self.assertEqual(code, 1)
        self.assertIn(ra.CHECKSUM_MISMATCH, text)
        self.assertNotIn(ra.PDF_SUBJECT_MISSING, text)

    def test_object_bi_xoa_bao_pdf_unavailable(self):
        did, out = self.render_pair()
        self.raw.delete_object(Bucket=self.bucket, Key=out.pdf_key)
        code, text = self.run_audit(did)
        self.assertEqual(code, 1)
        self.assertIn(ra.PDF_UNAVAILABLE, text)

    def test_cot_db_bi_sua_bao_loi(self):
        did, out = self.render_pair()
        with self.db.connect(autocommit=True) as c:
            c.execute("update document_render set watermark_text = 'CHUỖI SAI' where id = %s", (out.render_id,))
        code, text = self.run_audit(did)
        self.assertEqual(code, 1)
        self.assertIn(ra.DB_WATERMARK_MISMATCH, text)
        with self.db.connect(autocommit=True) as c:  # bỏ CHECK rồi để NULL — chân DB vẫn bắt
            c.execute("alter table document_render drop constraint ck_document_render_watermark")
            c.execute("update document_render set watermark_text = null where id = %s", (out.render_id,))
        code, text = self.run_audit(did)
        self.assertEqual(code, 1)
        self.assertIn(ra.DB_WATERMARK_MISSING, text)
        with self.db.connect(autocommit=True) as c:  # dựng lại CHECK cho các test sau trong cùng DB
            c.execute("update document_render set watermark_text = %s where id = %s", (TEXT, out.render_id))
            c.execute("alter table document_render add constraint ck_document_render_watermark check (operating_mode <> 'NON_PRODUCTION' or (watermark_text is not null and watermark_text <> ''))")

    def test_dau_ra_khong_mang_noi_dung_gia_tri_hay_credential(self):
        did, out = self.render_pair()
        self.raw.delete_object(Bucket=self.bucket, Key=out.pdf_key)  # ép có dòng trượt để có dòng chi tiết trong đầu ra
        _, text = self.run_audit(did)
        for secret in (*VALUES.values(), os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"], os.environ["BO19_TEST_S3_ACCESS_KEY_ID"], self.db.dsn("bo19_app")):
            self.assertNotIn(secret, text)

    def test_ma_thoat_2_khi_khong_kiem_duoc_va_khong_bao_gio_in_dat(self):
        did, _ = self.render_pair()
        cases = {
            "thiếu biến DB": self.env(BO19_DATABASE_URL=None),
            "thiếu biến storage": self.env(BO19_OBJECT_STORAGE_BUCKET=None),
            "DB không với tới": self.env(BO19_DATABASE_URL="postgresql://bo19_app@127.0.0.1:1/khong_co"),
        }
        for label, env in cases.items():
            out = io.StringIO()
            code = ra.main(["--document-id", str(did)], env, out)
            self.assertEqual(code, 2, label)
            self.assertIn("KHÔNG KIỂM ĐƯỢC", out.getvalue(), label)
            self.assertNotIn("đạt,", out.getvalue(), label)
        with mock.patch.object(ra.shutil, "which", return_value=None):
            out = io.StringIO()
            self.assertEqual(ra.main(["--document-id", str(did)], self.env(), out), 2)
            self.assertIn("PDFINFO_MISSING", out.getvalue())

    def test_ten_bien_thieu_duoc_nen_chi_ten_khong_gia_tri(self):
        out = io.StringIO()
        ra.main([], self.env(BO19_OBJECT_STORAGE_BUCKET=None), out)
        self.assertIn("BO19_OBJECT_STORAGE_BUCKET", out.getvalue())
        self.assertNotIn(os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"], out.getvalue())


if __name__ == "__main__":
    unittest.main()
