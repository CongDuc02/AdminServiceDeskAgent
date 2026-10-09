"""Nhãn trạng thái `request` (`bo19.domain.status_labels`) — S2 của `proposals/reply-templates.md`. B6a."""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest

from bo19.domain.request_machine import REQUEST_STATUSES
from bo19.domain.status_labels import REQUEST_STATUS_LABELS, request_status_label


class NhanTrangThai(unittest.TestCase):
    def test_du_muoi_trang_thai_dung_thu_tu_va_khong_trung(self):
        self.assertEqual(tuple(REQUEST_STATUS_LABELS), REQUEST_STATUSES)
        self.assertEqual(len(set(REQUEST_STATUS_LABELS.values())), len(REQUEST_STATUSES))

    def test_khong_nhan_nao_la_ma_tran_hay_rong(self):  # NFR-04: không hiển thị mã trạng thái trần
        for code, label in REQUEST_STATUS_LABELS.items():
            self.assertTrue(label.strip(), code)
            self.assertNotEqual(label.upper().replace(" ", "_"), code)
            self.assertNotRegex(label, r"^[A-Z_]+$")

    def test_tra_nhan_va_trang_thai_la_la_loi(self):
        self.assertEqual(request_status_label("DRAFT"), "Đang soạn")
        with self.assertRaises(KeyError):
            request_status_label("LA")


if __name__ == "__main__":
    unittest.main()
