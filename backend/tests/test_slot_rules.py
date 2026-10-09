"""Từ vựng `validation_rules` v1 (`bo19.domain.slot_rules`) — hàm thuần. B6a; `proposals/validation-rules-vocabulary.md` (PO duyệt 2026-10-09).

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_slot_rules -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unicodedata
import unittest

from bo19.domain import slot_rules as sr

PURPOSE = {"non_blank": True, "min_tokens": 3}


class MinTokens(unittest.TestCase):
    def test_hai_vi_du_cua_f1_bi_tu_choi_va_cau_du_tieng_qua(self):
        for bad in ("cần gấp", "làm việc"):
            self.assertEqual(sr.check_value("TEXT", PURPOSE, bad), ("RULE_MIN_TOKENS",), bad)
        self.assertEqual(sr.check_value("TEXT", PURPOSE, "bổ sung hồ sơ vay vốn"), ())

    def test_xin_visa_la_hai_tieng_nen_bi_hoi_lai_day_la_dem_tieng_khong_phai_tu(self):  # PO, 2026-10-09
        self.assertEqual(sr.tokens("xin visa"), 2)
        self.assertEqual(sr.check_value("TEXT", PURPOSE, "xin visa"), ("RULE_MIN_TOKENS",))
        self.assertEqual(sr.check_value("TEXT", PURPOSE, "xin visa du lịch"), ())

    def test_bien_n_va_n_tru_1(self):
        for n in (1, 2, 3, 5):
            rules = {"min_tokens": n}
            self.assertEqual(sr.check_value("STRING", rules, " ".join(["a"] * n)), ())
            if n > 1:
                self.assertEqual(sr.check_value("STRING", rules, " ".join(["a"] * (n - 1))), ("RULE_MIN_TOKENS",))

    def test_khoang_trang_unicode_va_nhieu_khoang_trang_khong_dem_them(self):
        self.assertEqual(sr.tokens("  a\t\tb\n c d　e  "), 5)  # no-break space và khoảng trắng CJK cũng tách
        self.assertEqual(sr.tokens("a    b"), 2)
        self.assertEqual(sr.tokens(""), 0)
        self.assertEqual(sr.tokens("   "), 0)

    def test_dem_sau_nfc_ket_hop_va_dung_san_nhu_nhau(self):
        composed = unicodedata.normalize("NFC", "bổ sung hồ sơ")
        decomposed = unicodedata.normalize("NFD", "bổ sung hồ sơ")
        self.assertNotEqual(composed, decomposed)
        self.assertEqual(sr.tokens(composed), sr.tokens(decomposed))
        self.assertEqual(sr.check_value("TEXT", PURPOSE, decomposed), ())

    def test_dau_cau_dinh_lien_khong_tach_tieng(self):
        self.assertEqual(sr.tokens("vay-vốn,ngân-hàng"), 1)  # tách theo khoảng trắng, đúng như đã duyệt: cơ học, không phân tích câu


class NonBlank(unittest.TestCase):
    def test_chu_hoac_so_moi_qua(self):
        for ok in ("a", "ế", "7", "  x  ", "٣", "…và"):  # chữ số Ả Rập-Ấn Độ thuộc N*
            self.assertEqual(sr.check_value("STRING", {"non_blank": True}, ok), (), ok)

    def test_chi_dau_cau_hoac_khoang_trang_la_rong(self):
        for bad in ("", "   ", "...", "—", "\t\n", "!?", "​", "()"):
            self.assertEqual(sr.check_value("STRING", {"non_blank": True}, bad), ("RULE_NON_BLANK",), repr(bad))

    def test_non_blank_chay_truoc_min_tokens(self):
        self.assertEqual(sr.check_value("TEXT", PURPOSE, "..."), ("RULE_NON_BLANK",))  # không phải MIN_TOKENS: thứ tự cố định


class IntRange(unittest.TestCase):
    def test_min_max_va_bien(self):
        r = {"int_range": {"min": 1, "max": 3}}
        for v, want in ((0, ("RULE_INT_RANGE",)), (1, ()), (2, ()), (3, ()), (4, ("RULE_INT_RANGE",)), (-5, ("RULE_INT_RANGE",))):
            self.assertEqual(sr.check_value("INT", r, v), want, v)

    def test_chi_min_hoac_chi_max(self):
        self.assertEqual(sr.check_value("INT", {"int_range": {"min": 1}}, 10**9), ())  # không có max: không có chặn trên (A-011 chưa có trần)
        self.assertEqual(sr.check_value("INT", {"int_range": {"min": 1}}, 0), ("RULE_INT_RANGE",))
        self.assertEqual(sr.check_value("INT", {"int_range": {"max": 5}}, -100), ())
        self.assertEqual(sr.check_value("INT", {"int_range": {"max": 5}}, 6), ("RULE_INT_RANGE",))


class OneOf(unittest.TestCase):
    def test_phan_biet_hoa_thuong_va_gia_tri_la(self):
        r = {"one_of": ["PROBATION", "FIXED_TERM", "INDEFINITE"]}
        self.assertEqual(sr.check_value("ENUM", r, "PROBATION"), ())
        for bad in ("probation", "PROBATION ", "OTHER", ""):
            self.assertEqual(sr.check_value("ENUM", r, bad), ("RULE_ONE_OF",), repr(bad))


class KiemKieuDuLieu(unittest.TestCase):
    def test_kieu_sai_la_rule_type_va_dung_truoc_moi_rule(self):
        cases = [("INT", True), ("INT", "3"), ("INT", 3.0), ("INT", None), ("STRING", 5), ("TEXT", ["a"]), ("ENUM", 1), ("DATE", "2026-13-01"), ("DATE", "20261001"),
                 ("DATE", "2026-02-30"), ("DATE", "2026-1-1"), ("DATE", 5), ("BOOL", "true"), ("LIST", "a"), ("FILE", "x"), ("TIMESTAMP", "ngày mai"), ("TIMESTAMP", 5)]
        for dtype, value in cases:
            self.assertEqual(sr.check_value(dtype, {}, value), ("RULE_TYPE",), (dtype, value))

    def test_kieu_dung(self):
        good = [("INT", 3), ("STRING", "a"), ("TEXT", ""), ("ENUM", "X"), ("DATE", "2026-02-28"), ("BOOL", False), ("LIST", []), ("TIMESTAMP", "2026-10-09T10:00:00+07:00")]
        for dtype, value in good:
            self.assertEqual(sr.check_value(dtype, {}, value), (), (dtype, value))

    def test_ket_qua_khong_bao_gio_chua_gia_tri(self):
        secret = "GIA_TRI_RES_KHONG_DUOC_LOT_RA"
        for rules in ({"min_tokens": 99}, {"non_blank": True}, {}, {"one_of": ["x"]}):
            self.assertNotIn(secret, "".join(sr.check_value("TEXT", rules, secret)))
            self.assertNotIn(secret, "".join(sr.check_value("ENUM", rules, secret)))


class CauHinh(unittest.TestCase):
    def test_hop_le(self):
        for dtype, rules in (("TEXT", PURPOSE), ("STRING", {"non_blank": True}), ("INT", {"int_range": {"min": 1}}), ("INT", {"int_range": {"min": 1, "max": 1}}),
                             ("ENUM", {"one_of": ["a", "b"]}), ("STRING", {}), ("DATE", {})):
            self.assertEqual(sr.validate_config(dtype, rules), [], (dtype, rules))

    def test_kieu_la_tham_so_sai_kieu_va_kieu_khong_hop_data_type(self):
        bad = [
            ("TEXT", {"max_words": 3}, "RULE_KIND_UNKNOWN:max_words"),
            ("TEXT", {"min_tokens": 0}, "RULE_PARAM_INVALID:min_tokens"), ("TEXT", {"min_tokens": True}, "RULE_PARAM_INVALID:min_tokens"), ("TEXT", {"min_tokens": "3"}, "RULE_PARAM_INVALID:min_tokens"),
            ("TEXT", {"non_blank": False}, "RULE_PARAM_INVALID:non_blank"), ("TEXT", {"non_blank": 1}, "RULE_PARAM_INVALID:non_blank"),
            ("INT", {"int_range": {}}, "RULE_PARAM_INVALID:int_range"), ("INT", {"int_range": {"min": 3, "max": 1}}, "RULE_PARAM_INVALID:int_range"),
            ("INT", {"int_range": {"lo": 1}}, "RULE_PARAM_INVALID:int_range"), ("INT", {"int_range": {"min": 1.5}}, "RULE_PARAM_INVALID:int_range"), ("INT", {"int_range": {"min": True}}, "RULE_PARAM_INVALID:int_range"),
            ("INT", {"int_range": 3}, "RULE_PARAM_INVALID:int_range"),
            ("ENUM", {"one_of": []}, "RULE_PARAM_INVALID:one_of"), ("ENUM", {"one_of": ["a", "a"]}, "RULE_PARAM_INVALID:one_of"), ("ENUM", {"one_of": ["a", 1]}, "RULE_PARAM_INVALID:one_of"),
            ("ENUM", {"one_of": [""]}, "RULE_PARAM_INVALID:one_of"), ("ENUM", {"one_of": "a"}, "RULE_PARAM_INVALID:one_of"),
            ("INT", {"non_blank": True}, "RULE_KIND_DATA_TYPE:non_blank"), ("TEXT", {"int_range": {"min": 1}}, "RULE_KIND_DATA_TYPE:int_range"), ("DATE", {"one_of": ["a"]}, "RULE_KIND_DATA_TYPE:one_of"),
            ("STRING", {"one_of": ["a"]}, "RULE_KIND_DATA_TYPE:one_of"),
        ]
        for dtype, rules, code in bad:
            self.assertEqual(sr.validate_config(dtype, rules), [code], (dtype, rules))

    def test_goc_khong_phai_doi_tuong_va_data_type_la(self):
        for rules in ([], "x", None, 5):
            self.assertEqual(sr.validate_config("TEXT", rules), ["RULES_NOT_OBJECT"])
        self.assertEqual(sr.validate_config("HEX", {}), ["DATA_TYPE_UNKNOWN:HEX"])

    def test_ma_loi_cau_hinh_khong_mang_gia_tri_tham_so(self):
        self.assertNotIn("BI_MAT", "".join(sr.validate_config("TEXT", {"min_tokens": "BI_MAT"})))

    def test_moi_kieu_trong_tu_vung_co_ma_va_data_type(self):
        self.assertEqual(set(sr.KINDS), set(sr.KIND_DATA_TYPES))
        self.assertEqual({sr.CODES[k] for k in sr.KINDS} | {sr.CODES["type"]}, {"RULE_NON_BLANK", "RULE_MIN_TOKENS", "RULE_INT_RANGE", "RULE_ONE_OF", "RULE_TYPE"})


if __name__ == "__main__":
    unittest.main()
