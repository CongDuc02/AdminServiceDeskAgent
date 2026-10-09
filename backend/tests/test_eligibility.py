"""Hàm "Yêu cầu đủ điều kiện xử lý" (F1) — `bo19.domain.eligibility`, thuần. B6a.

Bốn điều kiện của F1 (`01-prd.md`) × từng loại hỏng; các ca "KHÔNG đủ điều kiện" nêu tên ở F1; kết quả không bao giờ chứa giá trị.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_eligibility -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest
import uuid

from bo19.domain import eligibility as el
from bo19.domain.eligibility import Header, Reason, SlotDef, SlotState

ME, OTHER = uuid.uuid4(), uuid.uuid4()
HEADER = Header(ME, ME)

DEFS = [
    SlotDef("requester_employee_code", "STRING", "SYSTEM", True, {}),
    SlotDef("beneficiary_employee_id", "STRING", "SYSTEM", True, {}),
    SlotDef("full_name", "STRING", "HR_PROFILE", True, {}),
    SlotDef("contract_type", "ENUM", "HR_PROFILE", True, {"one_of": ["PROBATION", "FIXED_TERM", "INDEFINITE"]}),
    SlotDef("employment_end_date", "DATE", "HR_PROFILE", False, {}),
    SlotDef("purpose", "TEXT", "USER_INPUT", True, {"non_blank": True, "min_tokens": 3}),
    SlotDef("recipient_org", "STRING", "USER_INPUT", True, {"non_blank": True}),
    SlotDef("copies_count", "INT", "USER_INPUT", False, {"int_range": {"min": 1}}),
    SlotDef("document_number", "STRING", "SYSTEM", False, {}),
]


def full() -> dict[str, SlotState]:
    return {s.name: s for s in [
        SlotState("requester_employee_code", "SYSTEM_SET", "NV001"), SlotState("beneficiary_employee_id", "SYSTEM_SET", str(ME)),
        SlotState("full_name", "CONFIRMED", "Nguyễn Văn A"), SlotState("contract_type", "CONFIRMED", "INDEFINITE"),
        SlotState("purpose", "PROVIDED", "bổ sung hồ sơ vay vốn"), SlotState("recipient_org", "PROVIDED", "Ngân hàng X"),
    ]}


def run(slots: dict[str, SlotState] | None = None, header: Header = HEADER, on_behalf: bool = False, defs: list[SlotDef] = DEFS):
    return el.evaluate(header, defs, list((slots if slots is not None else full()).values()), creator_can_create_on_behalf=on_behalf)


class DuDieuKien(unittest.TestCase):
    def test_ho_so_day_du_la_du_dieu_kien(self):
        self.assertEqual(run(), ())
        self.assertTrue(el.is_eligible(HEADER, DEFS, list(full().values()), creator_can_create_on_behalf=False))

    def test_slot_tuy_chon_co_hay_khong_deu_khong_chan(self):
        s = full()
        s["copies_count"] = SlotState("copies_count", "PROVIDED", 2)
        s["employment_end_date"] = SlotState("employment_end_date", "CONFIRMED", "2026-01-31")
        self.assertEqual(run(s), ())

    def test_slot_system_bat_buoc_khi_issued_khong_chan_truoc_submitted(self):
        self.assertNotIn("document_number", [r.slot_name for r in run()])  # is_required = false


class DieuKien1UserInput(unittest.TestCase):
    def test_thieu_slot_bat_buoc(self):
        for name in ("purpose", "recipient_org"):
            s = full()
            del s[name]
            self.assertEqual(run(s), (Reason(el.SLOT_MISSING, name),), name)

    def test_gia_tri_proposed_tu_lan_expired_chua_xac_nhan_khong_duoc_tinh(self):
        s = full()
        s["recipient_org"] = SlotState("recipient_org", "PROPOSED", "Ngân hàng X")
        self.assertEqual(run(s), (Reason(el.SLOT_UNCONFIRMED, "recipient_org"),))

    def test_gia_tri_proposed_da_xac_nhan_duoc_tinh(self):
        s = full()
        s["recipient_org"] = SlotState("recipient_org", "CONFIRMED", "Ngân hàng X")
        self.assertEqual(run(s), ())

    def test_slot_da_xoa_hoac_gia_tri_none_la_thieu(self):
        s = full()
        s["purpose"] = SlotState("purpose", "ERASED", None)
        self.assertEqual(run(s), (Reason(el.SLOT_MISSING, "purpose"),))
        s["purpose"] = SlotState("purpose", "PROVIDED", None)
        self.assertEqual(run(s), (Reason(el.SLOT_MISSING, "purpose"),))

    def test_gia_tri_user_input_do_he_thong_dat_khong_duoc_tinh(self):
        s = full()
        s["purpose"] = SlotState("purpose", "SYSTEM_SET", "bổ sung hồ sơ vay vốn")  # agent không được tự điền USER_INPUT
        self.assertEqual(run(s), (Reason(el.SLOT_MISSING, "purpose"),))


class DieuKien2HrProfile(unittest.TestCase):
    def test_hr_profile_chua_xac_nhan_chan_ke_ca_khi_moi_gia_tri_khac_da_xac_nhan(self):  # AC-1.4
        s = full()
        s["contract_type"] = SlotState("contract_type", "PROPOSED", "INDEFINITE")
        self.assertEqual(run(s), (Reason(el.SLOT_UNCONFIRMED, "contract_type"),))

    def test_hr_profile_bat_buoc_thieu_la_missing(self):
        s = full()
        del s["full_name"]
        self.assertEqual(run(s), (Reason(el.SLOT_MISSING, "full_name"),))

    def test_hr_profile_do_nguoi_dung_tu_go_khong_duoc_tinh(self):
        s = full()
        s["full_name"] = SlotState("full_name", "PROVIDED", "Tên tự khai")  # HR_PROFILE chỉ qua xác nhận, không qua lời khai
        self.assertEqual(run(s), (Reason(el.SLOT_MISSING, "full_name"),))

    def test_slot_tuy_chon_dang_proposed_van_chan(self):
        s = full()
        s["employment_end_date"] = SlotState("employment_end_date", "PROPOSED", "2026-01-31")
        self.assertEqual(run(s), (Reason(el.SLOT_UNCONFIRMED, "employment_end_date"),))

    def test_slot_system_bat_buoc_phai_do_he_thong_dat(self):
        s = full()
        s["requester_employee_code"] = SlotState("requester_employee_code", "PROVIDED", "NV001")
        self.assertEqual(run(s), (Reason(el.SLOT_MISSING, "requester_employee_code"),))
        del s["requester_employee_code"]
        self.assertEqual(run(s), (Reason(el.SLOT_MISSING, "requester_employee_code"),))


class DieuKien3Rule(unittest.TestCase):
    def test_purpose_rong_nghia_theo_f1_bi_chan(self):
        for text in ("cần gấp", "làm việc", "...", "  "):
            s = full()
            s["purpose"] = SlotState("purpose", "PROVIDED", text)
            self.assertEqual(len(run(s)), 1, text)
            self.assertEqual(run(s)[0].slot_name, "purpose")

    def test_ma_rule_dung_voi_tung_loai_hong(self):
        s = full()
        s["purpose"] = SlotState("purpose", "PROVIDED", "cần gấp")
        s["copies_count"] = SlotState("copies_count", "PROVIDED", 0)
        s["contract_type"] = SlotState("contract_type", "CONFIRMED", "KHAC")
        self.assertEqual(set(run(s)), {Reason("RULE_MIN_TOKENS", "purpose"), Reason("RULE_INT_RANGE", "copies_count"), Reason("RULE_ONE_OF", "contract_type")})

    def test_rule_chay_theo_cau_hinh_hien_hanh_khong_theo_luc_ghi(self):
        s = full()
        stricter = [SlotDef(d.name, d.data_type, d.source, d.is_required, {"non_blank": True, "min_tokens": 9} if d.name == "purpose" else d.rules) for d in DEFS]
        self.assertEqual(run(s), ())
        self.assertEqual(run(s, defs=stricter), (Reason("RULE_MIN_TOKENS", "purpose"),))

    def test_kieu_du_lieu_sai_la_rule_type(self):
        s = full()
        s["copies_count"] = SlotState("copies_count", "PROVIDED", "2")
        self.assertEqual(run(s), (Reason("RULE_TYPE", "copies_count"),))

    def test_slot_chua_dinh_nghia_bi_bo_qua_khong_gay_loi(self):
        s = full()
        s["la"] = SlotState("la", "PROVIDED", "x")
        self.assertEqual(run(s), ())


class DieuKien4NguoiThuHuong(unittest.TestCase):
    def test_khong_xac_dinh_nguoi_thu_huong(self):
        self.assertEqual(run(header=Header(ME, None)), (Reason(el.BENEFICIARY_UNKNOWN),))

    def test_lap_ho_nguoi_khac_can_quyen_create_on_behalf(self):
        h = Header(ME, OTHER)
        self.assertEqual(run(header=h, on_behalf=False), (Reason(el.ON_BEHALF_FORBIDDEN),))
        self.assertEqual(run(header=h, on_behalf=True), ())

    def test_tu_lap_cho_minh_khong_can_quyen_them(self):
        self.assertEqual(run(on_behalf=False), ())


class BaoMatVaThuTu(unittest.TestCase):
    def test_ket_qua_va_repr_khong_chua_gia_tri(self):
        secret = "GIA_TRI_RES_KHONG_DUOC_LOT_RA"
        s = full()
        s["purpose"] = SlotState("purpose", "PROVIDED", secret)
        out = run(s)
        self.assertNotIn(secret, repr(out))
        self.assertNotIn(secret, repr(s["purpose"]))
        self.assertNotIn(secret, str(s["purpose"]))
        s["purpose"] = SlotState("purpose", "PROVIDED", secret.replace("_", " ")[:5])
        self.assertNotIn(secret, repr(run(s)))

    def test_nhieu_loi_cung_luc_va_thu_tu_on_dinh_theo_ten_slot(self):
        s = full()
        del s["purpose"]
        del s["recipient_org"]
        s["contract_type"] = SlotState("contract_type", "PROPOSED", "INDEFINITE")
        got = run(s, header=Header(ME, OTHER))
        self.assertEqual([(r.code, r.slot_name) for r in got], [(el.SLOT_UNCONFIRMED, "contract_type"), (el.SLOT_MISSING, "purpose"), (el.SLOT_MISSING, "recipient_org"), (el.ON_BEHALF_FORBIDDEN, None)])
        self.assertEqual(got, run(s, header=Header(ME, OTHER)))  # tất định

    def test_khong_doi_dau_vao(self):
        s = full()
        before = dict(s)
        run(s)
        self.assertEqual(s, before)


if __name__ == "__main__":
    unittest.main()
