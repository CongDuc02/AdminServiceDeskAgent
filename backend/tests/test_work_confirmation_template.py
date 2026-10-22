"""Mẫu nháp `tpl_work_confirmation.docx` (M1.1, `docs/design/proposals/mau-giay-xac-nhan-cong-tac/`): họ font, danh mục biến, thể thức A4/lề, và ĐỘ PHỦ của các biến thể câu chữ.

Mẫu chưa vào hệ thống (cơ chế `ENUM` chờ PO duyệt) nên test này chạy trên file trong `docs/` bằng `fill_docx` — hàm thuần, không DB, không soffice. Mọi giá trị là dữ liệu GIẢ.
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_work_confirmation_template -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import io
import re
import unittest
from pathlib import Path

from docx import Document
from docx.shared import Mm

from bo19.tool_layer.rendering.convert import convert_to_pdf
from bo19.tool_layer.rendering.docx_fill import fill_docx, template_variables
from bo19.tool_layer.rendering.fonts import declared_families
from tests.render_support import pdf_text, require_tool

TEMPLATE = Path(__file__).resolve().parents[2] / "docs" / "design" / "proposals" / "mau-giay-xac-nhan-cong-tac" / "tpl_work_confirmation.docx"
VARIABLES = frozenset({"full_name", "department_name", "job_title", "recipient_org", "contract_type", "employment_start_date", "employment_end_date",
                       "purpose_statement", "document_number", "issued_date", "signer_title", "signer_name"})
BASE = {
    "full_name": "Nguyễn Văn Mẫu (GIẢ)", "department_name": "Phòng Mẫu (GIẢ)", "job_title": "Chuyên viên (GIẢ)", "recipient_org": "Ngân hàng Mẫu (GIẢ)",
    "employment_start_date": "02/03/2022", "employment_end_date": "", "purpose_statement": "Câu mục đích giả.", "document_number": "01/GXN-ABC-TN",
    "issued_date": "21/10/2026", "signer_title": "GIÁM ĐỐC (GIẢ)", "signer_name": "Trần Thị Mẫu (GIẢ)", "contract_type": "INDEFINITE",
}
CLAUSES = {
    "PROBATION": "trong thời gian thử việc",
    "FIXED_TERM": "theo hợp đồng lao động xác định thời hạn",
    "INDEFINITE": "theo hợp đồng lao động không xác định thời hạn",
}


def text_of(blob: bytes) -> str:
    doc = Document(io.BytesIO(blob))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.extend(p.text for p in cell.paragraphs)
    return "\n".join(parts)


def fill(**over: str) -> str:
    return text_of(fill_docx(TEMPLATE.read_bytes(), {**BASE, **over}, declared=VARIABLES, operating_mode="NON_PRODUCTION"))


class MauNhap(unittest.TestCase):
    def test_chi_khai_times_new_roman(self):
        self.assertEqual(declared_families(TEMPLATE.read_bytes()), {"Times New Roman"})  # nằm trong bộ cổng 1.6 — không Webdings/Arial

    def test_danh_muc_bien_la_dung_tap_da_de_xuat(self):
        self.assertEqual(template_variables(TEMPLATE.read_bytes()), VARIABLES)

    def test_a4_va_le_trong_khoang_cua_phu_luc_i(self):
        sec = Document(io.BytesIO(TEMPLATE.read_bytes())).sections[0]
        self.assertEqual((round(sec.page_width.mm), round(sec.page_height.mm)), (210, 297))
        self.assertTrue(20 <= round(sec.top_margin.mm) <= 25 and 20 <= round(sec.bottom_margin.mm) <= 25)  # trên, dưới 20–25 mm
        self.assertTrue(30 <= round(sec.left_margin.mm) <= 35)  # trái 30–35 mm
        self.assertTrue(15 <= round(sec.right_margin.mm) <= 20)  # phải 15–20 mm
        self.assertGreater(sec.page_width, Mm(1))

    def test_moi_ma_contract_type_cho_dung_mot_menh_de_khong_rong(self):
        """Độ phủ (đề xuất mục 4): thêm mã thứ tư mà không thêm nhánh vào mẫu thì test này đỏ, thay vì cho ra văn bản thiếu câu."""
        for code, clause in CLAUSES.items():
            with self.subTest(code=code):
                body = fill(contract_type=code)
                self.assertIn(clause, body)
                self.assertEqual(sum(body.count(c) for c in CLAUSES.values()), 1, body)  # đúng một mệnh đề loại hợp đồng

    def test_thu_viec_khong_ham_y_nhan_vien_chinh_thuc(self):
        body = fill(contract_type="PROBATION")
        self.assertNotIn("hợp đồng lao động", body)  # EC-WC-01: không câu chữ hàm ý chính thức

    def test_dang_lam_viec_va_da_nghi_viec(self):
        now = fill(employment_end_date="")
        self.assertIn("Hiện đang làm việc tại Công ty từ ngày 02/03/2022", now)
        self.assertNotIn("đến ngày", now)
        left = fill(employment_end_date="15/09/2026", contract_type="FIXED_TERM")
        self.assertIn("Đã làm việc tại Công ty từ ngày 02/03/2022 đến ngày 15/09/2026", left)
        self.assertNotIn("Hiện đang", left)

    def test_ngay_viet_du_theo_nghi_dinh_va_dau_giu_cho_giu_nguyen(self):
        self.assertIn("ngày 21 tháng 10 năm 2026", fill())
        draft = fill(issued_date="[Ngày phát hành — cấp khi phát hành]")  # bản nháp (A-098): dấu giữ chỗ không bị cắt vụn
        self.assertIn("[Ngày phát hành — cấp khi phát hành]", draft)
        self.assertNotRegex(draft, re.compile(r"ngày \[N"))

    def test_ten_cong_ty_va_dia_danh_hu_cau_cua_do_an(self):
        body = fill()
        self.assertIn("CÔNG TY TNHH GIẢI PHÁP ABC", body)  # PO 2026-10-21: tên công ty HƯ CẤU, dùng cho đồ án
        self.assertIn("Hà Nội, ngày 21 tháng 10 năm 2026", body)
        self.assertNotIn("[TÊN CÔNG TY]", body)
        self.assertNotIn("[Địa danh]", body)

    def test_so_dai_trial_va_kinh_gui(self):
        body = fill()
        self.assertIn("Số: 01/GXN-ABC-TN", body)  # NON_PRODUCTION cấp dải TRIAL (data migration 0003)
        self.assertIn("Kính gửi: Ngân hàng Mẫu (GIẢ)", body)

    def test_khoi_ky_ba_tang_chuc_vu_hoa_khoang_ky_ho_ten_khong_dau_phay_khong_huong_dan(self):
        """PO 2026-10-22 (A-100): CHỨC VỤ in hoa đậm → chỗ ký và đóng dấu (4 dòng trống) → họ tên đậm; không dòng hướng dẫn biểu mẫu."""
        doc = Document(io.BytesIO(fill_docx(TEMPLATE.read_bytes(), BASE, declared=VARIABLES, operating_mode="NON_PRODUCTION")))
        cells = [c for table in doc.tables for row in table.rows for c in row.cells]
        sign = next(c for c in cells if "GIÁM ĐỐC (GIẢ)" in c.text)
        paragraphs = [p.text for p in sign.paragraphs]
        at_title, at_name = paragraphs.index("GIÁM ĐỐC (GIẢ)"), paragraphs.index("Trần Thị Mẫu (GIẢ)")
        self.assertEqual(paragraphs[at_title + 1 : at_name], [""] * 4)  # bốn dòng trống giữa chức vụ và họ tên
        self.assertTrue(all(r.bold for p in sign.paragraphs if p.text for r in p.runs))  # cả chức vụ và họ tên đậm
        self.assertNotIn(",", "".join(paragraphs))  # không dấu phẩy nối tên và chức danh
        self.assertNotIn("Ký, ghi rõ", fill())  # hướng dẫn biểu mẫu không in trên văn bản phát hành
        self.assertNotIn("đóng dấu)", fill())


def pdf(**over: str) -> str:
    require_tool(None, "soffice")
    require_tool(None, "pdftotext")
    return pdf_text(convert_to_pdf(fill_docx(TEMPLATE.read_bytes(), {**BASE, **over}, declared=VARIABLES, operating_mode="NON_PRODUCTION"), timeout_s=120))


class TrongPdf(unittest.TestCase):
    """PO 2026-10-21: điều kiện trong mẫu bao CẢ MỆNH ĐỀ của slot không bắt buộc — vắng `employment_end_date` thì PDF không có dòng nghỉ việc nào, không nhãn rỗng."""

    def test_vang_ngay_nghi_viec_khong_co_dong_nghi_viec_nao_trong_pdf(self):
        text = pdf(employment_end_date="")
        for fragment in ("Đã làm việc", "đến ngày", "nghỉ"):
            self.assertNotIn(fragment, text, fragment)
        self.assertIn("Hiện đang làm việc tại Công ty từ ngày 02/03/2022", text)
        self.assertNotRegex(text, r"(?mi)^\s*(ngày\s+)?(nghỉ|kết thúc)[^\n]*:\s*$")  # không nhãn rỗng kiểu "Ngày nghỉ việc:"

    def test_co_ngay_nghi_viec_thi_pdf_co_dung_mot_cau_da_lam_viec(self):
        text = pdf(employment_end_date="15/09/2026", contract_type="FIXED_TERM")
        self.assertEqual(text.count("Đã làm việc"), 1)
        self.assertIn("15/09/2026", text)
        self.assertNotIn("Hiện đang", text)


if __name__ == "__main__":
    unittest.main()
