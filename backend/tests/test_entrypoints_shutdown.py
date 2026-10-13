"""`worker_main` và `api_main` chạy THẬT như tiến trình con (B8a, O1-5): khởi động qua bước kiểm, nhận `SIGTERM`, tắt êm, và log `SIGTERM_RECEIVED` / `PROCESS_EXIT` kèm thời gian từ `SIGTERM`.

Điều được chứng minh, nói bằng hành vi:
- `worker_main` qua bước kiểm khởi động trên DB đã migrate, vào vòng poll (`WORKER_LOOP_START`), **không giành job `render_document`** (chưa có handler — vẫn `QUEUED`, `attempts` 0), `SIGTERM` → thoát mã 0 trong vài giây;
- bước kiểm trượt (thiếu `BO19_DATABASE_URL`) → thoát mã 1, `PROCESS_EXIT` mã 1, không vào vòng poll;
- `api_main` phục vụ `/healthz`, `SIGTERM` → `SIGTERM_RECEIVED`, thoát mã 0, `PROCESS_EXIT` có `seconds_since_sigterm`;
- không DSN, secret hay khoá nào lọt ra log.

Cần BO19_TEST_PG_SUPERUSER_DSN và chạy trên Linux (tín hiệu POSIX). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_entrypoints_shutdown -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.request
import uuid
from pathlib import Path

from tests import pg_support

BACKEND = Path(__file__).resolve().parents[1]
LLM_KEY = "KHOA_LLM_GIA_CUA_TEST_ENTRYPOINT_55bb"
SECRET = "b8a-entrypoint-secret-" + "s" * 30


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Proc:
    """Một tiến trình con; đọc stdout (JSON một dòng mỗi bản ghi) ở thread nền."""

    def __init__(self, module: str, env: dict[str, str]) -> None:
        self.p = subprocess.Popen([sys.executable, "-m", module], cwd=BACKEND, env={"PATH": os.environ["PATH"], "PYTHONPATH": "src", "PYTHONUNBUFFERED": "1", **env},
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        self.lines: list[dict] = []
        self.raw: list[str] = []
        self._t = threading.Thread(target=self._read, daemon=True)
        self._t.start()

    def _read(self) -> None:
        for line in self.p.stdout:  # type: ignore[union-attr]
            self.raw.append(line)
            try:
                self.lines.append(json.loads(line))
            except ValueError:
                pass

    def wait_for(self, message: str, timeout: float = 60) -> dict | None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for entry in list(self.lines):
                if entry.get("message") == message:
                    return entry
            if self.p.poll() is not None:
                break
            time.sleep(0.05)
        return next((e for e in self.lines if e.get("message") == message), None)

    def terminate(self, timeout: float = 30) -> int:
        self.p.send_signal(signal.SIGTERM)
        code = self.p.wait(timeout)
        self._t.join(5)
        return code

    def kill(self) -> None:
        if self.p.poll() is None:
            self.p.kill()
            self.p.wait(10)
        self._t.join(5)
        if self.p.stdout and not self.p.stdout.closed:
            self.p.stdout.close()

    def messages(self) -> list[str]:
        return [e.get("message", "") for e in self.lines]

    def text(self) -> str:
        return "".join(self.raw)


@unittest.skipUnless(pg_support.SUPERUSER_DSN and sys.platform != "win32", "cần BO19_TEST_PG_SUPERUSER_DSN và Linux")
class EntrypointBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)

    @classmethod
    def tearDownClass(cls):
        cls.db.drop()

    def env(self, **extra: str) -> dict[str, str]:
        return {"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": self.db.dsn("bo19_app"), "BO19_LLM_API_KEY": LLM_KEY, "BO19_SESSION_SECRET": SECRET, "BO19_SHUTDOWN_DELAY_SECONDS": "5", **extra}

    def start(self, module: str, **extra: str) -> Proc:
        p = Proc(module, self.env(**extra))
        self.addCleanup(p.kill)
        return p

    def assert_no_secrets(self, p: Proc) -> None:
        text = p.text()
        for secret in (LLM_KEY, SECRET, self.db.dsn("bo19_app")):
            self.assertNotIn(secret, text)


class WorkerMain(EntrypointBase):
    def test_vao_vong_poll_khong_gianh_render_document_va_tat_em_khi_sigterm(self):
        jid = uuid.uuid4()
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("delete from job")
            c.execute("insert into job (id, job_type, payload, max_attempts, run_after) values (%s, 'render_document', '{}'::jsonb, 5, now() - interval '1 minute')", (jid,))
        p = self.start("bo19.entrypoints.worker_main")
        started = p.wait_for("WORKER_LOOP_START")
        self.assertIsNotNone(started, p.text()[-2000:])
        self.assertIsNotNone(p.wait_for("STARTUP_OK"))
        time.sleep(3)  # hơn một chu kỳ poll (WV-21 = 2 s): nếu worker giành job nào thì đã giành
        before = time.monotonic()
        code = p.terminate()
        self.assertEqual(code, 0, p.text()[-2000:])
        self.assertLess(time.monotonic() - before, 10)
        msgs = p.messages()
        self.assertIn("SIGTERM_RECEIVED", msgs)
        self.assertIn("WORKER_LOOP_STOP", msgs)
        exit_line = next(e for e in p.lines if e.get("message") == "PROCESS_EXIT")
        self.assertEqual((exit_line["exit_code"], exit_line["signals"]), (0, "SIGTERM"))
        self.assertGreaterEqual(exit_line["seconds_since_sigterm"], 0)
        self.assertLess(exit_line["seconds_since_sigterm"], 10)
        self.assertLess(msgs.index("SIGTERM_RECEIVED"), msgs.index("PROCESS_EXIT"))
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select status, attempts from job where id = %s", (jid,)).fetchone(), ("QUEUED", 0))  # chưa có handler: không bị giành
        self.assert_no_secrets(p)

    def test_buoc_kiem_truot_thi_thoat_ma_1_va_khong_vao_vong_poll(self):
        env = self.env()
        del env["BO19_DATABASE_URL"]
        p = Proc("bo19.entrypoints.worker_main", env)
        self.addCleanup(p.kill)
        self.assertEqual(p.p.wait(60), 1, p.text()[-2000:])
        p._t.join(5)
        msgs = p.messages()
        self.assertIn("STARTUP_FAIL", msgs)
        self.assertNotIn("WORKER_LOOP_START", msgs)
        exit_line = next(e for e in p.lines if e.get("message") == "PROCESS_EXIT")
        self.assertEqual((exit_line["exit_code"], exit_line["seconds_since_sigterm"]), (1, None))
        self.assert_no_secrets(p)

    def test_khong_cau_hinh_object_storage_thi_canh_bao_khong_chan(self):
        p = self.start("bo19.entrypoints.worker_main")
        self.assertIsNotNone(p.wait_for("WORKER_LOOP_START"), p.text()[-2000:])
        warn = [e for e in p.lines if e.get("message") == "STARTUP_WARN" and e.get("code") == "STARTUP_14_NOT_CONFIGURED"]
        self.assertEqual(len(warn), 1)
        self.assertEqual(p.terminate(), 0)


class ApiMain(EntrypointBase):
    def test_phuc_vu_healthz_va_ghi_log_sigterm_khi_tat(self):
        port = free_port()
        p = self.start("bo19.entrypoints.api_main", PORT=str(port), BO19_SHUTDOWN_DELAY_SECONDS="30")  # bước kiểm #11: hạn chót lượt + biên (30 s) không dài hơn shutdown delay
        end, ok = time.monotonic() + 90, False
        while time.monotonic() < end and p.p.poll() is None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as r:
                    ok = r.status == 200
                    break
            except OSError:
                time.sleep(0.2)
        self.assertTrue(ok, p.text()[-3000:])
        code = p.terminate()
        self.assertEqual(code, 0, p.text()[-3000:])
        msgs = p.messages()
        self.assertIn("SIGTERM_RECEIVED", msgs)
        exit_line = next(e for e in p.lines if e.get("message") == "PROCESS_EXIT")
        self.assertEqual((exit_line["exit_code"], exit_line["signals"]), (0, "SIGTERM"))
        self.assertGreaterEqual(exit_line["seconds_since_sigterm"], 0)
        self.assertLess(msgs.index("SIGTERM_RECEIVED"), msgs.index("PROCESS_EXIT"))
        self.assert_no_secrets(p)

    def test_buoc_kiem_truot_thi_thoat_ma_1_va_log_process_exit(self):
        env = self.env(PORT=str(free_port()), BO19_SHUTDOWN_DELAY_SECONDS="30")
        del env["BO19_SESSION_SECRET"]
        p = Proc("bo19.entrypoints.api_main", env)
        self.addCleanup(p.kill)
        self.assertEqual(p.p.wait(60), 1, p.text()[-2000:])
        p._t.join(5)
        exit_line = next(e for e in p.lines if e.get("message") == "PROCESS_EXIT")
        self.assertEqual(exit_line["exit_code"], 1)
        self.assertIn("STARTUP_FAIL", p.messages())


if __name__ == "__main__":
    unittest.main()
