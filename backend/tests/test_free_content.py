"""`bo19.domain.free_content` — kiểm nội dung tự do do LLM sinh (mục Output validation trước khi render của 09-security.md; F2) — hàm thuần, không IO. B9a.

AC-1.11 ở mức hàm: một đầu ra giả chứa cú pháp trường của template, và một đầu ra giả chứa nguyên văn giá trị của một slot `RES` khác — cả hai trượt. (Qua node thật: `tests/test_document_graph.py`.)

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_free_content -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest

from bo19.domain import free_content as fc

OK = "Nhân viên đề nghị cấp giấy xác nhận để bổ sung hồ sơ vay vốn theo yêu cầu của đơn vị tiếp nhận."


def codes(body: str, **kw) -> list[str]:
    return fc.validate_body(body, max_length=kw.pop("max_length", 400), **kw)


class Dat(unittest.TestCase):
    def test_noi_dung_hop_le(self):
        self.assertEqual(codes(OK), [])

    def test_dau_va_tieng_viet_nfd_van_hop_le(self):
        import unicodedata
        self.assertEqual(codes(unicodedata.normalize("NFD", OK)), [])


class ChatLuong(unittest.TestCase):
    def test_rong(self):
        for body in ("", "   ", "\n\t "):
            self.assertEqual(codes(body), [fc.EMPTY], repr(body))

    def test_placeholder(self):
        for body in ("N/A", "n/a", "...", "…", "---", "[điền sau]", "TBD", "Mục đích: ... (điền)", "Mục đích [điền vào] sau khi có thông tin", "Giá trị N/A cho hồ sơ", "!!!"):
            self.assertIn(fc.PLACEHOLDER, codes(body), body)

    def test_khong_nham_cau_binh_thuong_la_placeholder(self):
        for body in (OK, "Bổ sung hồ sơ vay vốn tại Ngân hàng X theo yêu cầu của đơn vị tiếp nhận.", "Hồ sơ gồm 3 phần: lý lịch, hợp đồng và xác nhận thu nhập của đơn vị."):
            self.assertNotIn(fc.PLACEHOLDER, codes(body), body)

    def test_cau_khung(self):
        for body in ("Kính gửi Ngân hàng ABC: đề nghị xem xét hồ sơ vay vốn.", "KÍNH GỬI Ngân hàng ABC xin xem xét", "Nội dung\nSố: 123/QĐ-GIẢ\nxin xác nhận", "Nơi nhận: Phòng Nhân sự, lưu văn thư"):
            self.assertIn(fc.FRAME_TEXT, codes(body), body)


class AnNinh(unittest.TestCase):
    """AC-1.11 — mục Output validation trước khi render."""

    def test_cu_phap_truong_cua_template_truot(self):
        for body in ("Đề nghị cấp giấy {{ ho_ten }} để bổ sung hồ sơ.", "Nội dung }} đóng trước khi mở và còn thừa nữa", "Khối {% if x %} điều kiện của template nằm trong nội dung", "Chú thích {# ghi chú #} của template nằm trong nội dung văn bản"):
            self.assertIn(fc.TEMPLATE_SYNTAX, codes(body), body)

    def test_the_html_xml_truot(self):
        for body in ("Nội dung có <b>chữ đậm</b> không được phép nhúng vào văn bản.", "Có thẻ <w:p/> của WordprocessingML trong nội dung văn bản chính", "Ký tự &amp; đã mã hoá thực thể nằm trong nội dung văn bản"):
            self.assertIn(fc.MARKUP, codes(body), body)

    def test_so_sanh_hon_kem_khong_phai_markup(self):
        self.assertNotIn(fc.MARKUP, codes("Mức lương thử việc < 100% và hồ sơ gồm 3 > 2 phần theo quy định hiện hành."))

    def test_dai_qua_max_length(self):
        self.assertIn(fc.TOO_LONG, codes(OK, max_length=20))
        self.assertNotIn(fc.TOO_LONG, codes(OK, max_length=len(OK)))

    def test_nguyen_van_slot_res_khac_truot(self):
        secret = "012345678901"
        body = f"Đề nghị cấp giấy cho công dân mang số định danh {secret} để bổ sung hồ sơ vay vốn."
        self.assertIn(fc.CONTAINS_RES_VALUE, codes(body, forbidden_res_values=[secret]))
        self.assertIn(fc.CONTAINS_RES_VALUE, codes(body.upper().replace(secret, secret), forbidden_res_values=[secret]))
        self.assertNotIn(fc.CONTAINS_RES_VALUE, codes(OK, forbidden_res_values=[secret]))

    def test_so_sanh_khong_phan_biet_hoa_thuong_va_khoang_trang(self):
        value = "Nguyễn  Thị   Hương"  # nhiều khoảng trắng
        self.assertIn(fc.CONTAINS_RES_VALUE, codes("Đề nghị cấp giấy cho bà nguyễn thị hương để làm hồ sơ vay vốn.", forbidden_res_values=[value]))

    def test_gia_tri_res_qua_ngan_khong_gay_khop_ngau_nhien(self):
        self.assertNotIn(fc.CONTAINS_RES_VALUE, codes(OK, forbidden_res_values=["đề", "hồ", "A"]))
        self.assertEqual(fc.MIN_RES_LENGTH, 4)

    def test_nhieu_loi_cung_luc_tra_du_ma(self):
        body = "Kính gửi {{ x }} <b>N/A</b>"
        self.assertEqual(set(codes(body, max_length=5)), {fc.PLACEHOLDER, fc.FRAME_TEXT, fc.TEMPLATE_SYNTAX, fc.MARKUP, fc.TOO_LONG})

    def test_ma_loi_khong_mang_noi_dung(self):
        for code in codes("Kính gửi {{ 012345678901 }}", forbidden_res_values=["012345678901"]):
            self.assertRegex(code, r"^[A-Z_]+$")


if __name__ == "__main__":
    unittest.main()
