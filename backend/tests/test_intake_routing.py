"""Ánh xạ output P1 → `intent_result` — đủ TÁM dòng của bảng ở mục `intake_graph` của 03-agents.md (G2, PO duyệt: Sprint 1 cài đủ tám dòng và test đủ tám dòng).

Hàm thuần, không cần PostgreSQL. Mỗi dòng có ít nhất một ca khớp và một ca "gần khớp nhưng thuộc dòng khác", để thứ tự xét ("dòng đầu tiên khớp thì dừng") bị khoá bằng test.
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_intake_routing -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest

from bo19.orchestrator.intake_graph.routing import Mapped, map_intent

CATALOG = [
    {"code": "WORK_CONFIRMATION", "support_status": "SUPPORTED"},
    {"code": "INTRODUCTION_LETTER", "support_status": "SUPPORTED"},
    {"code": "INCOME_CONFIRMATION", "support_status": "KNOWN_UNSUPPORTED"},
    {"code": "ROOM_BOOKING", "support_status": "KNOWN_UNSUPPORTED"},
]


def out(intent="WORK_CONFIRMATION", secondary=None, confidence="high"):
    return {"intent": intent, "secondary_intent": secondary, "confidence": confidence, "retrieval_query": None}


class TamDong(unittest.TestCase):
    def check(self, output, open_type=None, **expected) -> Mapped:
        m = map_intent(output, CATALOG, open_type)
        for key, value in expected.items():
            self.assertEqual(getattr(m, key), value, (output, open_type, key))
        return m

    def test_dong_1_json_hong_hoac_ma_ngoai_catalog(self):
        self.check(None, intent_result="UNPARSEABLE", row=1)
        self.check(out("LOAI_LA"), intent_result="UNPARSEABLE", row=1)
        self.check(out("WORK_CONFIRMATION", "LOAI_LA"), intent_result="UNPARSEABLE", row=1)
        self.check(out("WORK_CONFIRMATION", "NEED_CLARIFICATION"), intent_result="UNPARSEABLE", row=1)  # schema không cho secondary là NEED_CLARIFICATION
        self.check(out("LOAI_LA", confidence="low"), intent_result="UNPARSEABLE", row=1)  # dòng 1 trước dòng 2

    def test_dong_2_nhap_nhang(self):
        m = self.check(out("NEED_CLARIFICATION"), intent_result="AMBIGUOUS", row=2, candidate_types=())
        self.assertIsNone(m.primary_type)
        self.check(out("WORK_CONFIRMATION", confidence="low"), intent_result="AMBIGUOUS", row=2, candidate_types=("WORK_CONFIRMATION",))
        self.check(out("WORK_CONFIRMATION", "INTRODUCTION_LETTER", "low"), intent_result="AMBIGUOUS", row=2, candidate_types=("WORK_CONFIRMATION", "INTRODUCTION_LETTER"))  # dòng 2 trước dòng 3
        self.check(out("NEED_CLARIFICATION", "WORK_CONFIRMATION"), intent_result="AMBIGUOUS", row=2, candidate_types=("WORK_CONFIRMATION",))

    def test_dong_3_hai_nhu_cau_it_nhat_mot_duoc_ho_tro(self):
        m = self.check(out("WORK_CONFIRMATION", "INTRODUCTION_LETTER"), intent_result="MULTIPLE", row=3, primary_type="WORK_CONFIRMATION", pending_type="INTRODUCTION_LETTER")
        self.assertEqual(m.candidate_types, ("WORK_CONFIRMATION", "INTRODUCTION_LETTER"))  # cả hai SUPPORTED: intent là loại mở
        self.check(out("ROOM_BOOKING", "WORK_CONFIRMATION"), intent_result="MULTIPLE", row=3, primary_type="WORK_CONFIRMATION", pending_type="ROOM_BOOKING")  # chỉ secondary được hỗ trợ
        self.check(out("WORK_CONFIRMATION", "ROOM_BOOKING"), intent_result="MULTIPLE", row=3, primary_type="WORK_CONFIRMATION", pending_type="ROOM_BOOKING")
        self.check(out("OUT_OF_SCOPE", "WORK_CONFIRMATION"), intent_result="MULTIPLE", row=3, primary_type="WORK_CONFIRMATION", pending_type=None)  # OUT_OF_SCOPE lưu None

    def test_dong_4_hai_nhu_cau_khong_cai_nao_duoc_ho_tro(self):
        self.check(out("ROOM_BOOKING", "INCOME_CONFIRMATION"), intent_result="OUT_OF_SCOPE", row=4, unsupported_type="ROOM_BOOKING")
        self.check(out("OUT_OF_SCOPE", "ROOM_BOOKING"), intent_result="OUT_OF_SCOPE", row=4, unsupported_type=None)

    def test_dong_5_loai_duoc_ho_tro(self):
        self.check(out("WORK_CONFIRMATION"), None, intent_result="SUPPORTED", row=5, primary_type="WORK_CONFIRMATION")  # chưa có loại đang mở
        self.check(out("WORK_CONFIRMATION"), "WORK_CONFIRMATION", intent_result="SUPPORTED", row=5)  # trùng loại đang mở
        self.check(out("WORK_CONFIRMATION", "WORK_CONFIRMATION"), None, intent_result="SUPPORTED", row=5)  # secondary bằng intent không phải nhu cầu thứ hai

    def test_dong_6_doi_loai_giua_chung(self):
        self.check(out("INTRODUCTION_LETTER"), "WORK_CONFIRMATION", intent_result="TYPE_CHANGED", row=6, primary_type="INTRODUCTION_LETTER")

    def test_dong_7_loai_da_biet_la_chua_ho_tro(self):
        self.check(out("INCOME_CONFIRMATION"), None, intent_result="OUT_OF_SCOPE", row=7, unsupported_type="INCOME_CONFIRMATION")
        self.check(out("INCOME_CONFIRMATION"), "WORK_CONFIRMATION", intent_result="OUT_OF_SCOPE", row=7, unsupported_type="INCOME_CONFIRMATION")  # kể cả khi có loại đang mở

    def test_dong_8_ngoai_pham_vi(self):
        m = self.check(out("OUT_OF_SCOPE"), intent_result="OUT_OF_SCOPE", row=8, unsupported_type=None)
        self.assertIsNone(m.primary_type)

    def test_moi_ket_qua_co_dung_mot_dong_va_dong_nam_trong_1_den_8(self):
        for output in (None, out("X"), out("NEED_CLARIFICATION"), out("OUT_OF_SCOPE", "WORK_CONFIRMATION"), out("ROOM_BOOKING", "INCOME_CONFIRMATION"), out(), out("INTRODUCTION_LETTER"),
                       out("ROOM_BOOKING"), out("OUT_OF_SCOPE")):
            m = map_intent(output, CATALOG, "WORK_CONFIRMATION")
            self.assertIn(m.row, range(1, 9))
            self.assertIn(m.intent_result, {"SUPPORTED", "AMBIGUOUS", "OUT_OF_SCOPE", "TYPE_CHANGED", "MULTIPLE", "UNPARSEABLE"})

    def test_khong_mang_van_ban_tu_do(self):  # `retrieval_query` là văn bản từ lời nhân viên — ánh xạ không giữ nó
        m = map_intent({**out("OUT_OF_SCOPE"), "retrieval_query": "GIA_TRI_RES_9f3a"}, CATALOG, None)
        self.assertNotIn("GIA_TRI_RES_9f3a", repr(m))


if __name__ == "__main__":
    unittest.main()
