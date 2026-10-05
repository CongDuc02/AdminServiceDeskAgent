"""Test khối SPIKE S4 của api_main (A-031, A-086) — gỡ cùng khối đó ở bước dọn.

Chạy từ backend/:  python -m unittest tests.test_spike_s4 -v   (cần uvicorn, fastapi — có trong lock)
Không cần PostgreSQL: chỉ thử vòng giữ, handler và cấu hình log, không chạy bước kiểm khởi động.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import signal
import sys
import time
import unittest
import unittest.mock
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn  # noqa: E402

from bo19.entrypoints import api_main as m  # noqa: E402

UTC_RE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+00:00"


class FlushStream(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flushes = 0

    def flush(self) -> None:
        self.flushes += 1
        super().flush()


def parse_utc(s: str) -> float:
    return datetime.fromisoformat(s).timestamp()


class Hold(unittest.IsolatedAsyncioTestCase):
    async def hold(self, cap: str | None) -> FlushStream:
        out = FlushStream()
        m._S4["t_sigterm"] = time.monotonic()
        env = {"BO19_S4_HOLD_S": cap} if cap is not None else {}
        with unittest.mock.patch.dict(os.environ, env, clear=False), contextlib.redirect_stdout(out):
            if cap is None:
                os.environ.pop("BO19_S4_HOLD_S", None)
            async with m._s4_lifespan(None):
                pass
        return out

    async def test_giu_moi_giay_mot_dong_co_gio_utc_va_so_thu_tu(self):
        out = await self.hold("3")
        lines = out.getvalue().splitlines()
        holds = [re.fullmatch(rf"SHUTDOWN_HOLD n=(\d+) utc=({UTC_RE}) since_sigterm=(\d+\.\d{{3}})", l) for l in lines[:3]]
        self.assertTrue(all(holds), lines)
        self.assertEqual([int(h[1]) for h in holds], [1, 2, 3])  # số thứ tự liên tục — lỗ giữa chừng nhận ra được
        gaps = [parse_utc(b[2]) - parse_utc(a[2]) for a, b in zip(holds, holds[1:])]
        for g in gaps:
            self.assertAlmostEqual(g, 1.0, delta=0.15)
        since = [float(h[3]) for h in holds]
        self.assertEqual(since, sorted(since))
        self.assertRegex(lines[3], rf"HOLD_CAP_REACHED n=3 utc={UTC_RE} since_sigterm=\d+\.\d{{3}}")
        self.assertRegex(lines[4], rf"PROCESS_EXIT utc={UTC_RE} since_sigterm=\d+\.\d{{3}}")
        self.assertEqual(len(lines), 5)

    async def test_flush_tung_dong(self):
        out = await self.hold("2")
        self.assertEqual(out.flushes, len(out.getvalue().splitlines()))

    async def test_khong_dat_bien_thi_khong_giu_va_khong_in_gi(self):
        out = await self.hold(None)
        self.assertEqual(out.getvalue(), "")


class Handler(unittest.TestCase):
    def server(self) -> m._S4Server:
        return m._S4Server(uvicorn.Config(app=lambda *a, **k: None))

    def test_sigterm_ghi_mot_dong_va_van_chuyen_tiep_cho_uvicorn(self):
        m._S4["t_sigterm"] = None
        s, out = self.server(), FlushStream()
        with contextlib.redirect_stdout(out):
            s.handle_exit(signal.SIGTERM, None)
            s.handle_exit(signal.SIGTERM, None)  # lần hai không ghi lại
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], rf"SIGTERM_RECEIVED utc={UTC_RE} pid={os.getpid()} boot_utc={UTC_RE}")
        self.assertTrue(s.should_exit)  # uvicorn vẫn bắt đầu tắt êm
        self.assertEqual(out.flushes, 1)
        self.assertIsNotNone(m._S4["t_sigterm"])

    def test_sigint_khong_ghi_dong_sigterm(self):
        m._S4["t_sigterm"] = None
        s, out = self.server(), FlushStream()
        with contextlib.redirect_stdout(out):
            s.handle_exit(signal.SIGINT, None)
        self.assertEqual(out.getvalue(), "")
        self.assertTrue(s.should_exit)


class LogConfig(unittest.TestCase):
    def test_log_uvicorn_co_gio_utc(self):
        old = logging_converter()
        try:
            cfg = m._s4_log_config()
            for name in ("default", "access"):
                self.assertTrue(cfg["formatters"][name]["fmt"].startswith("%(asctime)sZ "), name)
            self.assertIs(logging_converter(), time.gmtime)
            self.assertNotIn("asctime", uvicorn.config.LOGGING_CONFIG["formatters"]["access"]["fmt"])  # bản gốc không bị sửa
        finally:
            set_logging_converter(old)


def logging_converter():
    import logging

    return logging.Formatter.converter


def set_logging_converter(fn) -> None:  # noqa: ANN001
    import logging

    logging.Formatter.converter = fn


if __name__ == "__main__":
    unittest.main()
