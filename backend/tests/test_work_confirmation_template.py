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

from bo19.tool_layer.rendering.docx_fill import fill_docx, template_variables
from bo19.tool_layer.rendering.fonts import declared_families

TEMPLATE = Path(__file__).resolve().parents[2] / "docs" / "design" / "proposals" / "mau-giay-xac-nhan-cong-tac" / "tpl_work_confirmation.docx"
VARIABLES = frozenset({"full_name", "department_name", "job_title", "recipient_org", "contract_type", "employment_start_date", "employment_end_date",
                       "purpose_statement", "document_number", "issued_date", "signer_user_id"})
BASE = {
    "full_name": "Nguyễn Văn Mẫu (GIẢ)", "department_name": "Phòng Mẫu (GIẢ)", "job_title": "Chuyên viên (GIẢ)", "recipient_org": "Ngân hàng Mẫu (GIẢ)",
    "employment_start_date": "02/03/2022", "employment_end_date": "", "purpose_statement": "Câu mục đích giả.", "document_number": "01/GXN-ABC",
    "issued_date": "21/10/2026", "signer_user_id": "Trần Thị Mẫu (GIẢ), Giám đốc (GIẢ)", "contract_type": "INDEFINITE",
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

    def test_so_va_nguoi_ky_dung_cho(self):
        body = fill()
        self.assertIn("Số: 01/GXN-ABC", body)
        self.assertIn("Trần Thị Mẫu (GIẢ), Giám đốc (GIẢ)", body)
        self.assertIn("Kính gửi: Ngân hàng Mẫu (GIẢ)", body)


if __name__ == "__main__":
    unittest.main()
