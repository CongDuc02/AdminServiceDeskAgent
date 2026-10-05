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


def reset_signal_state() -> None:
    m._S4.update({"t_sigterm": None, "sig_counts": {}, "sig_total": 0, "witness": None, "wit_busy": False})


class Handler(unittest.TestCase):
    def setUp(self) -> None:
        reset_signal_state()

    def server(self) -> m._S4Server:
        return m._S4Server(uvicorn.Config(app=lambda *a, **k: None))

    def test_moi_lan_nhan_tin_hieu_deu_co_dong_con_sigterm_received_chi_mot_lan(self):
        s, out = self.server(), FlushStream()
        with contextlib.redirect_stdout(out):
            s.handle_exit(signal.SIGTERM, None)
            s.handle_exit(signal.SIGTERM, None)  # lần hai: có dòng SIGNAL_RECEIVED, không có SIGTERM_RECEIVED thứ hai
            s.handle_exit(signal.SIGINT, None)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 4, lines)
        self.assertRegex(lines[0], rf"SIGNAL_RECEIVED sig=SIGTERM nth=1 total=1 utc={UTC_RE} pid={os.getpid()}")
        self.assertRegex(lines[1], rf"SIGTERM_RECEIVED utc={UTC_RE} pid={os.getpid()} boot_utc={UTC_RE}")
        self.assertRegex(lines[2], rf"SIGNAL_RECEIVED sig=SIGTERM nth=2 total=2 utc={UTC_RE}")
        self.assertRegex(lines[3], rf"SIGNAL_RECEIVED sig=SIGINT nth=1 total=3 utc={UTC_RE}")
        self.assertEqual(sum(l.startswith("SIGTERM_RECEIVED") for l in lines), 1)
        self.assertTrue(s.should_exit)  # uvicorn vẫn bắt đầu tắt êm
        self.assertEqual(out.flushes, 4)
        self.assertIsNotNone(m._S4["t_sigterm"])

    def test_sigint_dau_tien_co_dong_va_khong_co_sigterm_received(self):
        s, out = self.server(), FlushStream()
        with contextlib.redirect_stdout(out):
            s.handle_exit(signal.SIGINT, None)
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"SIGNAL_RECEIVED sig=SIGINT nth=1 total=1")
        self.assertTrue(s.should_exit)
        self.assertIsNone(m._S4["t_sigterm"])

    def test_tin_hieu_khac_duoc_ghi_va_cai_dat_khong_lam_hong_tien_trinh(self):
        names = ("SIGHUP", "SIGQUIT", "SIGUSR1", "SIGUSR2", "SIGALRM", "SIGCONT", "SIGTSTP")
        before = {n: signal.getsignal(getattr(signal, n)) for n in names}
        try:
            self.assertEqual(m._s4_install_signal_logging(), list(names))
            out = FlushStream()
            with contextlib.redirect_stdout(out):
                signal.raise_signal(signal.SIGUSR1)  # tới handler thật, không phải gọi hàm trực tiếp
            lines = out.getvalue().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertRegex(lines[0], rf"SIGNAL_RECEIVED sig=SIGUSR1 nth=1 total=1 utc={UTC_RE} pid={os.getpid()} extra=1")
        finally:
            for n, h in before.items():
                signal.signal(getattr(signal, n), h)


class FakeConn:
    """Thay kết nối nhân chứng: ghi lại application_name được đặt; delay giả lập kết nối treo."""

    def __init__(self, delay: float = 0.0, error: Exception | None = None) -> None:
        self.names: list[str] = []
        self.delay, self.error = delay, error

    def execute(self, sql: str, params: tuple) -> None:
        self.names.append(params[0])
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error


class Witness(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        reset_signal_state()

    async def hold(self, conn: FakeConn | None, cap: str) -> list[str]:
        out = FlushStream()
        m._S4["witness"] = conn
        m._S4["t_sigterm"] = time.monotonic()
        with unittest.mock.patch.dict(os.environ, {"BO19_S4_HOLD_S": cap}), contextlib.redirect_stdout(out):
            async with m._s4_lifespan(None):
                pass
        return out.getvalue().splitlines()

    async def test_application_name_moi_giay_gom_boot_utc_va_n(self):
        conn = FakeConn()
        await self.hold(conn, "3")
        tag = m._S4["boot_utc"][:23]
        self.assertEqual(conn.names, [f"s4 boot={tag} n={k}" for k in (1, 2, 3)])
        self.assertTrue(all(len(n) < 63 for n in conn.names))  # giới hạn của application_name

    async def test_ket_noi_treo_khong_chan_vong_giu(self):
        conn = FakeConn(delay=2.5)  # SET đầu tiên treo 2.5 s
        t = time.monotonic()
        lines = await self.hold(conn, "3")
        self.assertLess(time.monotonic() - t, 3.6)  # vòng giữ vẫn chạy đúng 3 s, không chờ DB
        holds = [re.fullmatch(rf"SHUTDOWN_HOLD n=(\d+) utc=({UTC_RE}) since_sigterm=\S+", l) for l in lines if l.startswith("SHUTDOWN_HOLD")]
        self.assertEqual([int(h[1]) for h in holds], [1, 2, 3])
        for a, b in zip(holds, holds[1:]):
            self.assertAlmostEqual(parse_utc(b[2]) - parse_utc(a[2]), 1.0, delta=0.15)
        self.assertTrue(any(l.startswith("WITNESS_SLOW n=1") for l in lines), lines)
        self.assertTrue(any(l.startswith("WITNESS_SKIP n=2") for l in lines), lines)  # lần trước chưa xong thì bỏ lượt
        self.assertEqual(conn.names.__len__(), 1)

    async def test_loi_ket_noi_chi_ghi_dong_loi_vong_giu_van_chay(self):
        conn = FakeConn(error=RuntimeError("boom"))
        lines = await self.hold(conn, "2")
        self.assertEqual([l.split()[0] for l in lines if l.startswith("WITNESS_ERR")], ["WITNESS_ERR", "WITNESS_ERR"])
        self.assertTrue(all("boom" not in l for l in lines))  # chỉ tên lớp lỗi, không thông điệp
        self.assertEqual(sum(l.startswith("SHUTDOWN_HOLD") for l in lines), 2)

    async def test_khong_co_nhan_chung_thi_khong_in_dong_witness(self):
        lines = await self.hold(None, "2")
        self.assertFalse(any(l.startswith("WITNESS") for l in lines))


class WitnessOpen(unittest.TestCase):
    def setUp(self) -> None:
        reset_signal_state()

    def test_mo_luc_khoi_dong_voi_application_name_co_boot_utc(self):
        out, conn = FlushStream(), FakeConn()
        settings = unittest.mock.Mock(database_url="postgresql://u:pw@db.internal.example/x")
        with unittest.mock.patch.object(m, "load_settings", return_value=settings), \
                unittest.mock.patch.object(m.psycopg, "connect", return_value=conn) as connect, contextlib.redirect_stdout(out):
            m._s4_open_witness()
        self.assertIs(m._S4["witness"], conn)
        kw = connect.call_args.kwargs
        self.assertTrue(kw["autocommit"])
        self.assertEqual(kw["application_name"], f"s4 boot={m._S4['boot_utc'][:23]} n=0")
        self.assertRegex(out.getvalue(), rf"WITNESS_OPEN utc={UTC_RE} application_name='s4 boot=\S+ n=0'")
        self.assertNotIn("pw", out.getvalue())
        self.assertNotIn("example", out.getvalue())

    def test_that_bai_khong_lo_dsn_hay_host(self):
        out = FlushStream()
        settings = unittest.mock.Mock(database_url="postgresql://u:pw@db.internal.example/x")
        err = m.psycopg.OperationalError('connection to server at "db.internal.example" failed')
        with unittest.mock.patch.object(m, "load_settings", return_value=settings), \
                unittest.mock.patch.object(m.psycopg, "connect", side_effect=err), contextlib.redirect_stdout(out):
            m._s4_open_witness()
        self.assertIsNone(m._S4["witness"])
        self.assertRegex(out.getvalue(), rf"WITNESS_FAIL utc={UTC_RE} error=OperationalError sqlstate=None")
        self.assertNotIn("example", out.getvalue())
        self.assertNotIn("pw", out.getvalue())


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
