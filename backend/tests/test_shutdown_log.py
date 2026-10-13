"""`bo19.observability.shutdown` (O1-5) — log `SIGTERM_RECEIVED`, `SIGNAL_RECEIVED`, `PROCESS_EXIT`.

Điều được chứng minh: `SIGTERM` ghi `SIGTERM_RECEIVED`, tín hiệu khác ghi `SIGNAL_RECEIVED`; `PROCESS_EXIT` mang mã thoát và `seconds_since_sigterm` (`null` nếu chưa nhận `SIGTERM`, số dương nếu đã nhận);
mọi tín hiệu nhận được được liệt kê; mọi dòng có `timestamp` UTC (`Z`); chỉ mã, tên tín hiệu và số.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_shutdown_log -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import io
import json
import logging
import signal
import time
import unittest

from bo19.observability.log import configure_logging
from bo19.observability.shutdown import ShutdownLog


class ShutdownLogTest(unittest.TestCase):
    def setUp(self):
        self.out = io.StringIO()
        handler = configure_logging(self.out)
        self.addCleanup(logging.getLogger().removeHandler, handler)

    def lines(self) -> list[dict]:
        return [json.loads(line) for line in self.out.getvalue().splitlines() if line.strip()]

    def test_sigterm_va_thoat_ghi_thoi_gian_tu_sigterm(self):
        s = ShutdownLog("bo19.test")
        s.received(signal.SIGTERM)
        time.sleep(0.05)
        s.exited(0)
        first, last = self.lines()
        self.assertEqual((first["message"], first["signal"], first["component"], first["level"]), ("SIGTERM_RECEIVED", "SIGTERM", "bo19.test", "INFO"))
        self.assertEqual((last["message"], last["exit_code"], last["signals"]), ("PROCESS_EXIT", 0, "SIGTERM"))
        self.assertGreaterEqual(last["seconds_since_sigterm"], 0.05)
        self.assertLess(last["seconds_since_sigterm"], 5)
        for line in (first, last):
            self.assertTrue(line["timestamp"].endswith("Z"))  # giờ UTC

    def test_tin_hieu_khac_la_signal_received_va_thoat_ma_khac_khong_khi_chua_co_sigterm(self):
        s = ShutdownLog("bo19.test")
        s.received(signal.SIGINT)
        s.exited(1)
        first, last = self.lines()
        self.assertEqual((first["message"], first["signal"]), ("SIGNAL_RECEIVED", "SIGINT"))
        self.assertEqual((last["exit_code"], last["seconds_since_sigterm"], last["signals"]), (1, None, "SIGINT"))

    def test_nhieu_tin_hieu_moc_la_lan_sigterm_dau_tien(self):
        s = ShutdownLog("bo19.test")
        s.received(signal.SIGTERM)
        time.sleep(0.05)
        s.received(signal.SIGTERM)
        s.received(signal.SIGINT)
        s.exited(0)
        last = self.lines()[-1]
        self.assertEqual(last["signals"], "SIGTERM,SIGTERM,SIGINT")
        self.assertGreaterEqual(last["seconds_since_sigterm"], 0.05)  # tính từ lần đầu, không bị đặt lại

    def test_thoat_ma_khong_co_tin_hieu(self):
        s = ShutdownLog("bo19.test")
        s.exited(0)
        (line,) = self.lines()
        self.assertEqual((line["message"], line["exit_code"], line["seconds_since_sigterm"], line["signals"]), ("PROCESS_EXIT", 0, None, None))


if __name__ == "__main__":
    unittest.main()
