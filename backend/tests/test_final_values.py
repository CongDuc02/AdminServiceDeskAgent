"""`domain.final_values` (B9b2, ADR-041 mục 4): giá trị của ba biến `SYSTEM` điền-sau-duyệt ở bản `FINAL`. Hàm thuần — không DB, không object storage.

- đổi theo TÊN biến: `document_number` = số đã định dạng, `issued_date` = `dd/mm/yyyy` (A-098), `signer_user_id` = `"<họ tên>, <chức danh>"` (PO, 2026-10-20: họ tên và chức danh, không mã);
- biến điền-sau-duyệt có tên khác không có nguồn: trả về trong `unresolved`, không điền bừa; biến không điền-sau-duyệt không bị đụng;
- `repr` không mang giá trị.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_final_values -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import datetime as dt
import unittest

from bo19.domain import final_values as fv

NUMBER = "TRIAL-007/2026/THU-NGHIEM"
SIGNER = "NGUYỄN VĂN KÝ (GIẢ), Trưởng phòng Hành chính (giả)"


class SystemValues(unittest.TestCase):
    def build(self, names, **kw):
        kw.setdefault("formatted_number", NUMBER)
        kw.setdefault("issued_date", dt.date(2026, 3, 9))
        kw.setdefault("signer", SIGNER)
        return fv.system_values(names, **kw)

    def test_ba_bien_theo_ten(self):
        out = self.build(["signer_user_id", "document_number", "issued_date"])
        self.assertEqual(out.values, {"document_number": NUMBER, "issued_date": "09/03/2026", "signer_user_id": SIGNER})
        self.assertEqual(out.unresolved, ())

    def test_ngay_dd_mm_yyyy_co_so_0(self):
        self.assertEqual(self.build(["issued_date"], issued_date=dt.date(2026, 1, 5)).values["issued_date"], "05/01/2026")
        self.assertEqual(self.build(["issued_date"], issued_date=dt.date(2026, 12, 31)).values["issued_date"], "31/12/2026")

    def test_ten_la_khong_co_nguon(self):
        out = self.build(["document_number", "approver_name", "zzz_unknown"])
        self.assertEqual(out.values, {"document_number": NUMBER})
        self.assertEqual(out.unresolved, ("approver_name", "zzz_unknown"))  # sắp theo tên — tất định

    def test_khong_co_bien_nao_thi_khong_co_gi(self):
        out = self.build([])
        self.assertEqual((out.values, out.unresolved), ({}, ()))

    def test_chi_dien_bien_duoc_khai_khong_them(self):
        self.assertEqual(self.build(["issued_date"]).values, {"issued_date": "09/03/2026"})  # không tự thêm số và người ký

    def test_dong_nguoi_ky_ho_ten_roi_chuc_danh(self):
        self.assertEqual(fv.signer_line("A", "B"), "A, B")
        self.assertNotIn("GIA-", SIGNER)  # mã nhân viên không bao giờ vào dòng ký

    def test_repr_khong_mang_gia_tri(self):
        text = repr(self.build(["document_number", "signer_user_id", "x"]))
        self.assertNotIn(NUMBER, text)
        self.assertNotIn("NGUYỄN", text)
        self.assertIn("document_number", text)
        self.assertIn("x", text)

    def test_tap_biet_nguon_la_ba_ten(self):
        self.assertEqual(fv.RESOLVABLE, {"document_number", "issued_date", "signer_user_id"})


if __name__ == "__main__":
    unittest.main()
