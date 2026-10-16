"""Metadata của PDF mang chuỗi watermark, và không mang tên người soạn mẫu (B9a / M5, ADR-038) — `soffice` THẬT, `pdfinfo` THẬT (poppler: công cụ chuẩn, độc lập với mã của dự án).

Điều được chứng minh, nói bằng hành vi:
- `NON_PRODUCTION`: `/Subject` của PDF do `soffice` dựng từ một `.docx` do `fill_docx` đóng = chuỗi watermark NGUYÊN VĂN; luồng XMP `dc:description` cũng mang nó (LibreOffice phản chiếu);
- `PRODUCTION`: PDF **không** mang chuỗi ấy — kể cả khi thuộc tính `subject` của mẫu cố tình chứa đúng chuỗi đó (`subject` bị xoá);
- `author` và `lastModifiedBy` của mẫu bị ghi đè bằng tên hệ thống ở cả hai chế độ: `/Author` của PDF là tên hệ thống, và tên người soạn mẫu **không xuất hiện ở bất kỳ dạng mã hoá nào** trong byte PDF (chữ thường, UTF-16BE hex), trong XMP, hay trong `docProps/core.xml` của `.docx`;
- `title` của mẫu **giữ nguyên** (thuộc mốc M1.1 — PO) — test ghi lại hành vi đó để nó không đổi lặng lẽ.

Cần `soffice` và `pdfinfo` (image target `test`; CI đặt BO19_REQUIRE_SOFFICE=1). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_pdf_metadata -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import io
import unittest
import zipfile
from unittest import mock

from bo19.tool_layer.rendering import convert, docx_fill, watermark
from bo19.tool_layer.rendering.doc_properties import SYSTEM_AUTHOR
from tests.render_support import DECLARED, VALUES, build_template, pdfinfo_fields, pdfinfo_xmp, require_tool

AUTHOR_NAME = "Nguyễn Văn Soạn Mẫu"
EDITOR_NAME = "Trần Thị Người Sửa Cuối"
TEMPLATE_TITLE = "TIÊU ĐỀ CỦA MẪU"


def make_pdf(mode: str, **properties: str) -> tuple[bytes, bytes]:
    template = build_template(properties={"author": AUTHOR_NAME, "last_modified_by": EDITOR_NAME, "title": TEMPLATE_TITLE, **properties})
    docx = docx_fill.fill_docx(template, VALUES, declared=DECLARED, operating_mode=mode)
    return docx, convert.convert_to_pdf(docx, timeout_s=300)


def core_xml(docx: bytes) -> str:
    return zipfile.ZipFile(io.BytesIO(docx)).read("docProps/core.xml").decode("utf-8")


def spellings(name: str) -> list[bytes]:
    """Mọi dạng mà một chuỗi có thể nằm trong byte PDF: UTF-8, UTF-16BE (có/không BOM) ở dạng nhị phân và hex (hoa/thường)."""
    out = [name.encode("utf-8")]
    for raw in (name.encode("utf-16-be"), b"\xfe\xff" + name.encode("utf-16-be")):
        out += [raw, raw.hex().encode(), raw.hex().upper().encode()]
    return out


class PdfMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_tool(cls, "soffice")
        require_tool(cls, "pdfinfo")
        cls.np_docx, cls.np_pdf = make_pdf("NON_PRODUCTION")
        # `subject` của mẫu cố tình mang đúng chuỗi watermark: ở PRODUCTION nó phải bị xoá, không được lọt sang PDF.
        cls.prod_docx, cls.prod_pdf = make_pdf("PRODUCTION", subject=watermark.WATERMARK_TEXT)

    # ---- chuỗi watermark ----

    def test_non_production_subject_cua_pdf_bang_chuoi_watermark_nguyen_van(self):
        self.assertEqual(pdfinfo_fields(self.np_pdf).get("Subject"), watermark.WATERMARK_TEXT)

    def test_non_production_xmp_cung_mang_chuoi(self):
        self.assertIn(f"<rdf:li xml:lang=\"x-default\">{watermark.WATERMARK_TEXT}</rdf:li>", pdfinfo_xmp(self.np_pdf))  # dc:description — LibreOffice phản chiếu `Subject`

    def test_chuoi_la_chuoi_cua_ac_1_3(self):
        self.assertEqual(watermark.WATERMARK_TEXT, "BẢN THỬ NGHIỆM — KHÔNG CÓ GIÁ TRỊ PHÁP LÝ")

    def test_production_pdf_khong_mang_chuoi_du_template_cai_san(self):
        info = pdfinfo_fields(self.prod_pdf)
        self.assertNotIn("Subject", info)
        self.assertNotIn("KHÔNG CÓ GIÁ TRỊ PHÁP LÝ", pdfinfo_xmp(self.prod_pdf))
        for form in spellings(watermark.WATERMARK_TEXT):
            self.assertNotIn(form, self.prod_pdf)

    def test_docx_subject_theo_che_do(self):
        from docx import Document
        self.assertEqual(Document(io.BytesIO(self.np_docx)).core_properties.subject, watermark.WATERMARK_TEXT)
        self.assertEqual(Document(io.BytesIO(self.prod_docx)).core_properties.subject, "")

    # ---- tên người soạn mẫu ----

    def test_author_cua_pdf_la_ten_he_thong_o_ca_hai_che_do(self):
        for pdf in (self.np_pdf, self.prod_pdf):
            self.assertEqual(pdfinfo_fields(pdf).get("Author"), SYSTEM_AUTHOR)

    def test_ten_nguoi_soan_khong_con_o_bat_ky_dang_nao_trong_pdf(self):
        for pdf in (self.np_pdf, self.prod_pdf):
            blob = pdfinfo_xmp(pdf) + "\n" + " ".join(f"{k}={v}" for k, v in pdfinfo_fields(pdf).items())
            for name in (AUTHOR_NAME, EDITOR_NAME):
                self.assertNotIn(name, blob)
                for form in spellings(name):
                    self.assertNotIn(form, pdf, (name, form[:20]))

    def test_ten_nguoi_soan_khong_con_trong_core_xml_cua_docx(self):
        for docx in (self.np_docx, self.prod_docx):
            xml = core_xml(docx)
            self.assertNotIn(AUTHOR_NAME, xml)
            self.assertNotIn(EDITOR_NAME, xml)
            self.assertIn(f">{SYSTEM_AUTHOR}<", xml)

    def test_kiem_chung_la_kiem_duoc_phep_thu_thay_tac_gia_thi_lot_vao_pdf(self):
        """Chứng minh bộ kiểm có răng: nếu không ghi đè, tên người soạn LỌT vào PDF — đúng thứ B9a chặn. (Dựng PDF từ mẫu chưa qua `apply_properties`.)"""
        template = build_template(properties={"author": AUTHOR_NAME})
        with mock.patch.object(docx_fill.doc_properties, "apply_properties", side_effect=lambda docx, text: docx):
            docx = docx_fill.fill_docx(template, VALUES, declared=DECLARED, operating_mode="NON_PRODUCTION")
        pdf = convert.convert_to_pdf(docx, timeout_s=300)
        self.assertEqual(pdfinfo_fields(pdf).get("Author"), AUTHOR_NAME)
        self.assertNotIn("Subject", pdfinfo_fields(pdf))

    # ---- title để M1.1 ----

    def test_title_cua_mau_giu_nguyen_thuoc_m1_1(self):
        self.assertEqual(pdfinfo_fields(self.np_pdf).get("Title"), TEMPLATE_TITLE)
        self.assertEqual(pdfinfo_fields(self.prod_pdf).get("Title"), TEMPLATE_TITLE)


if __name__ == "__main__":
    unittest.main()
