"""Prompt module P4 `draft_free_content` bản 1.1 — giọng bên phát hành (PO, 2026-10-16; `07-prompts.md` mục 4.4).

Bản 1.0 viết "Xin được cấp giấy xác nhận…" — giọng người xin, và chép lại tin nhắn của nhân viên. Phép kiểm ở đây khoá **chỉ dẫn và few-shot** (thứ duy nhất quyết định giọng — chưa có phép kiểm bằng code
trên đầu ra, xem mục 4.4): giọng bên phát hành, cấm giọng đơn xin, không chép lại, không lặp thông tin của mẫu; ví dụ đúng giọng và qua `validate_body`; ví dụ "không viết" nằm SAU nhãn của nó.
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_p4_prompt -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import re
import unittest

from bo19.ai_gateway.prompt_modules import DRAFT_FREE_CONTENT
from bo19.domain import free_content

REQUEST_PHRASES = ("xin được", "kính xin", "đề nghị cấp", "tôi xin", "mong được")
TEXT = DRAFT_FREE_CONTENT.instructions
POSITIVE, _, NEGATIVE = TEXT.partition("KHÔNG viết (")


class P4Giong(unittest.TestCase):
    def test_phien_ban_1_1(self):
        self.assertEqual(DRAFT_FREE_CONTENT.version, "1.1")

    def test_quy_dinh_giong_va_ngoi_cua_ben_phat_hanh(self):
        for needle in ("bên PHÁT HÀNH", "Kính gửi", 'gọi là "Ông/Bà"', "CẤM giọng đơn xin", "không dùng ngôi thứ nhất"):
            self.assertIn(needle, TEXT, needle)

    def test_cam_dich_danh_tung_cum_don_xin(self):
        rule = TEXT.split("CẤM giọng đơn xin")[1].split("\n")[0]
        for phrase in ("Xin được", "Kính xin", "Đề nghị cấp", "Tôi xin", "Mong được"):
            self.assertIn(phrase, rule, phrase)

    def test_khong_chep_lai_tin_nhan_va_khong_lap_thong_tin_cua_mau(self):
        self.assertIn("Không chép lại câu chữ của nhân viên", TEXT)
        self.assertIn("Không lặp thông tin đã có chỗ khác trong mẫu", TEXT)
        for field in ("nơi nhận", "họ tên", "chức danh", "đơn vị"):
            self.assertIn(field, TEXT.split("Không lặp thông tin")[1].split("\n")[0], field)

    def test_van_giu_rang_buoc_cu(self):
        for needle in ("không thêm nơi nhận/số ký hiệu", "Không được dùng recipient_org", "Độ dài ≤ max_length", "Chỉ trả JSON"):
            self.assertIn(needle, TEXT, needle)

    def few_shot_bodies(self):
        return re.findall(r'"body":"(.*?)"\}', POSITIVE)

    def test_co_hai_vi_du_dung_giong(self):
        bodies = self.few_shot_bodies()
        self.assertEqual(len(bodies), 2)
        for body in bodies:
            self.assertTrue(body.startswith("Giấy xác nhận này được cấp để Ông/Bà "), body)
            self.assertFalse(any(p in body.lower() for p in REQUEST_PHRASES), body)
            self.assertFalse(re.search(r"\b(tôi|chúng tôi)\b", body.lower()), body)  # không ngôi thứ nhất
            self.assertEqual(free_content.validate_body(body, max_length=400), [], body)  # qua chính phép kiểm của hệ thống

    def test_vi_du_khong_viet_co_nhan_va_nam_sau_vi_du_dung(self):
        self.assertTrue(NEGATIVE, "thiếu ví dụ 'KHÔNG viết'")
        self.assertIn("giọng đơn xin", NEGATIVE.split(")")[0])
        self.assertTrue(any(p in NEGATIVE.lower() for p in REQUEST_PHRASES))  # là ví dụ của giọng sai
        self.assertLess(TEXT.index('"body"'), TEXT.index("KHÔNG viết ("))
        self.assertNotIn('"body"', NEGATIVE)  # không phải một cặp input→output mà mô hình có thể bắt chước

    def test_ngan_du_de_khong_vuot_tran_dau_vao(self):
        self.assertLess(len(TEXT), 2800)  # chỉ dẫn P4 còn nhỏ so với trần input — số cứng chỉ để bắt phình to bất ngờ


if __name__ == "__main__":
    unittest.main()
