"""`combined_main` (B9a2, ADR-033) — TIẾN TRÌNH THẬT: PostgreSQL, SeaweedFS, `soffice` thật; `soffice` GIẢ (script `sh` sống lâu) ở ca tắt giữa lúc chuyển đổi.

Điều được chứng minh, nói bằng hành vi:
- **#18:** `staging` và `prod` bị chặn (`STARTUP_18_COMBINED_ONLY_IN_DEV`), không giành job nào;
- **một tiến trình, hai vai:** phục vụ `/healthz` VÀ xử lý job `render_document` tới `PENDING_APPROVAL` do vòng poll trong chính nó;
- **bước kiểm là HỢP các cột:** thiếu `BO19_RENDER_FINGERPRINT_KEY` (#24, cột `worker`) hay `BO19_LLM_API_KEY` (#22) đều chặn;
- **`SIGTERM` lúc `soffice` đang chuyển đổi (PO 2026-10-16):** thoát mã 0 trong ≈ 5 s, nhóm tiến trình `soffice` bị giết (không còn tiến trình sống), job `release` về `QUEUED` KHÔNG tiêu lượt thử; rồi một tiến trình `combined_main` khác chạy tiếp job tới `PENDING_APPROVAL`.
Mẫu thử KHÔNG có biến nội dung tự do nên không có lời gọi LLM nào (provider không cần thật). Mọi dữ liệu là dữ liệu giả của test.

Cần BO19_TEST_PG_SUPERUSER_DSN, BO19_TEST_S3_ENDPOINT, `soffice` (image target `test`).
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_combined_main -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)
from tests.static_support import shared_build

import io
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import uuid
from pathlib import Path

from docx import Document

from bo19.orchestrator.runner import document_id_for
from tests.doc_support import FONT, VARIABLES, DocBase, make_template, retire_active_templates
from tests.test_entrypoints_shutdown import FP_KEY, LLM_KEY, SECRET, Proc, free_port

MODULE = "bo19.entrypoints.combined_main"
NO_FREE = tuple(v for v in VARIABLES if v[1] != "FREE_CONTENT")  # không có lời gọi LLM nào
LINUX = sys.platform.startswith("linux")


def template_no_free() -> bytes:
    doc = Document()
    for style in ("Normal", "Header", "Footer"):
        doc.styles[style].font.name = FONT
    for text in ("MẪU GIẢ — chỉ để thử, không phải mẫu của tổ chức", "{{ full_name }} — {{ department_name }} — {{ job_title }}", "Kính gửi: {{ recipient_org }}",
                 "Số: {{ document_number }} ngày {{ issued_date }} — người ký {{ signer_user_id }}"):
        doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def group_alive(pgid: int) -> list[int]:
    """PID còn SỐNG (không phải zombie) trong nhóm tiến trình `pgid`."""
    alive = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", encoding="utf-8", errors="replace") as f:
                text = f.read()
            rest = text[text.rindex(")") + 2:].split()
            if int(rest[2]) == pgid and rest[0] != "Z":
                alive.append(int(name))
        except (OSError, ValueError, IndexError):
            continue
    return alive


@unittest.skipUnless(LINUX, "cần Linux")
class CombinedMain(DocBase):
    def setUp(self):
        super().setUp()
        retire_active_templates(self.db)
        self.version_id = make_template(self.db, self.pool, self.storage, variables=NO_FREE, data=template_no_free())
        self.procs: list[Proc] = []
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def tearDown(self):
        for p in self.procs:
            p.kill()
        super().tearDown()

    # ---- dựng tiến trình -------------------------------------------------------------------------------------------------------

    def env(self, **extra: str | None) -> dict[str, str]:
        env = {"BO19_ENVIRONMENT": "dev", "BO19_STATIC_DIR": str(shared_build()), "BO19_DATABASE_URL": self.db.dsn("bo19_app"), "BO19_SESSION_SECRET": SECRET, "BO19_LLM_API_KEY": LLM_KEY, "BO19_RENDER_FINGERPRINT_KEY": FP_KEY,
               "PORT": str(free_port()), "BO19_OBJECT_STORAGE_ENDPOINT_URL": os.environ["BO19_TEST_S3_ENDPOINT"], "BO19_OBJECT_STORAGE_BUCKET": self.bucket,
               "BO19_OBJECT_STORAGE_ACCESS_KEY_ID": os.environ["BO19_TEST_S3_ACCESS_KEY_ID"], "BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY": os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"]}
        env.update({k: v for k, v in extra.items() if v is not None})
        for k, v in extra.items():
            if v is None:
                env.pop(k, None)
        return env

    def start(self, **extra: str | None) -> tuple[Proc, int]:
        env = self.env(**extra)
        p = Proc(MODULE, env)
        self.procs.append(p)
        return p, int(env["PORT"])

    def fake_soffice_path(self) -> tuple[str, Path]:
        """PATH có một `soffice` GIẢ đứng trước: `--version` trả dòng phiên bản (bước kiểm #6); chuyển đổi thì sinh một tiến trình con sống lâu rồi chờ, ghi PID nhóm vào file mốc."""
        marker = Path(self.tmp.name) / "convert-started"
        script = Path(self.tmp.name) / "bin" / "soffice"
        script.parent.mkdir()
        script.write_text("#!/bin/sh\ncase \"$*\" in *--version*) echo 'LibreOffice 25.2.3.2 520(Build:2) GIA'; exit 0;; esac\n"
                          f"sleep 300 &\necho $$ > {marker}\nwait\n", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return f"{script.parent}{os.pathsep}{os.environ['PATH']}", marker

    def healthz(self, port: int) -> int:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as r:
            return r.status

    def wait_until(self, fn, timeout: float, what: str):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = fn()
            if value:
                return value
            time.sleep(0.1)
        self.fail(f"quá hạn {timeout} s: {what}")

    def job(self, rid: uuid.UUID) -> tuple:
        row = self.rows("select status, attempts, last_error_code from job where payload->>'request_id' = %s", str(rid))
        return row[0] if row else (None, None, None)

    # ---- #18 và hợp các cột ----------------------------------------------------------------------------------------------------

    def test_staging_va_prod_bi_chan_o_buoc_18_va_khong_giành_job(self):
        rid = self.submitted_request()
        for environment in ("staging", "prod"):
            p, _ = self.start(BO19_ENVIRONMENT=environment)
            self.assertEqual(p.p.wait(60), 1, p.text()[-2000:])
            fail = [e for e in p.lines if e.get("message") == "STARTUP_FAIL"]
            self.assertIn("STARTUP_18_COMBINED_ONLY_IN_DEV", [e.get("code") for e in fail], environment)
            self.assertNotIn("WORKER_LOOP_START", p.messages())
        self.assertEqual(self.job(rid)[0:2], ("QUEUED", 0))

    def test_buoc_kiem_la_hop_cac_cot_thieu_khoa_dau_van_tay_hay_khoa_llm_bi_chan(self):
        for name, code in (("BO19_RENDER_FINGERPRINT_KEY", "STARTUP_24_RENDER_FINGERPRINT_KEY_MISSING"), ("BO19_LLM_API_KEY", "STARTUP_22_LLM_API_KEY_MISSING")):
            p, _ = self.start(**{name: None})
            self.assertEqual(p.p.wait(60), 1, p.text()[-2000:])
            self.assertIn(code, [e.get("code") for e in p.lines if e.get("message") == "STARTUP_FAIL"], name)
            self.assertNotIn("WORKER_LOOP_START", p.messages())

    # ---- một tiến trình, hai vai ------------------------------------------------------------------------------------------------

    def test_mot_tien_trinh_vua_phuc_vu_vua_xu_ly_job_roi_tat_em(self):
        rid = self.submitted_request()
        p, port = self.start()
        self.assertIsNotNone(p.wait_for("WORKER_LOOP_START", 60), p.text()[-2000:])
        self.wait_until(lambda: self._try(lambda: self.healthz(port) == 200), 30, "/healthz")
        self.wait_until(lambda: self.job(rid)[0] == "SUCCEEDED", 120, f"job render_document ({p.text()[-1500:]})")
        self.assertEqual(self.document(rid)["status"], "PENDING_APPROVAL")
        code = p.terminate(30)
        self.assertEqual(code, 0, p.text()[-2000:])
        msgs = p.messages()
        for name in ("SIGTERM_RECEIVED", "WORKER_LOOP_STOP", "PROCESS_EXIT"):
            self.assertIn(name, msgs)
        self.assertLess(msgs.index("SIGTERM_RECEIVED"), msgs.index("PROCESS_EXIT"))
        self.assertEqual(self.healthz_down(port), True)  # cổng đã đóng

    def _try(self, fn):
        try:
            return fn()
        except OSError:
            return False

    def healthz_down(self, port: int) -> bool:
        try:
            self.healthz(port)
        except OSError:
            return True
        return False

    # ---- SIGTERM lúc soffice đang chuyển đổi -----------------------------------------------------------------------------------

    def test_sigterm_giua_chuyen_doi_giet_soffice_release_khong_tieu_luot_roi_chay_tiep(self):
        rid = self.submitted_request()
        path, marker = self.fake_soffice_path()
        p, _ = self.start(PATH=path)
        self.assertIsNotNone(p.wait_for("WORKER_LOOP_START", 60), p.text()[-2000:])
        pgid = int(self.wait_until(lambda: marker.exists() and marker.read_text().strip(), 120, f"soffice giả khởi động ({p.text()[-1500:]})"))
        self.assertEqual(self.job(rid)[0:2], ("RUNNING", 1))
        self.assertTrue(group_alive(pgid))
        started = time.monotonic()
        code = p.terminate(30)
        took = time.monotonic() - started
        self.assertEqual(code, 0, p.text()[-2500:])
        self.assertLess(took, 5.0, f"thoát sau {took:.1f} s — hạn Render ≈ 5 s")  # PO: ≈ 5 s
        self.assertIn("JOB_RELEASED_ON_DRAIN", p.messages())
        self.assertEqual(group_alive(pgid), [])  # không còn soffice (hay con của nó) nào sống
        self.assertEqual(self.job(rid)[0:2], ("QUEUED", 0))  # release: không tiêu lượt thử
        self.assertEqual(self.document(rid)["status"], "DRAFT")  # chưa tới PENDING_APPROVAL

        # lần chạy sau (soffice thật) tiếp tục job tới cùng
        q, _ = self.start()
        self.assertIsNotNone(q.wait_for("WORKER_LOOP_START", 60), q.text()[-2000:])
        self.wait_until(lambda: self.job(rid)[0] == "SUCCEEDED", 180, f"job chạy tiếp ({q.text()[-1500:]})")
        self.assertEqual(self.job(rid)[1], 1)  # lượt thử 1: lần bị huỷ không được tính
        self.assertEqual(self.document(rid)["status"], "PENDING_APPROVAL")
        self.assertEqual(q.terminate(30), 0)

    def test_bo_xu_ly_tin_hieu_som_dung_vong_poll_va_ghi_tin_hieu_mot_lan(self):
        """Tín hiệu tới trước khi uvicorn cài bộ xử lý của nó không được mất — `serve` dựa vào đó để không chạy uvicorn nữa."""
        import signal as _signal
        from bo19.entrypoints.combined_main import make_signal_handler
        from bo19.observability.shutdown import ShutdownLog
        from bo19.queue_worker.dispatcher import Dispatcher
        shutdown, dispatcher = ShutdownLog("bo19.test"), Dispatcher(object(), {})
        handler = make_signal_handler(shutdown, dispatcher)
        self.assertFalse(dispatcher.stopping)
        handler(_signal.SIGTERM, None)
        self.assertTrue(dispatcher.stopping)
        self.assertEqual(shutdown.signals, ["SIGTERM"])
        handler(_signal.SIGTERM, None)  # uvicorn bắn lại tín hiệu sau khi tắt: không ghi lần hai
        self.assertEqual(shutdown.signals, ["SIGTERM"])

    def test_cau_noi_tin_hieu_dat_should_exit_khi_tin_hieu_toi_truoc_uvicorn(self):
        import threading as _threading
        from bo19.entrypoints.api_main import watch_for_signal
        from bo19.observability.shutdown import ShutdownLog

        class FakeServer:
            should_exit = False

        shutdown, server, finished = ShutdownLog("bo19.test"), FakeServer(), _threading.Event()
        t = _threading.Thread(target=watch_for_signal, args=(shutdown, server, finished, 0.01))
        t.start()
        time.sleep(0.1)
        self.assertFalse(server.should_exit)  # chưa có tín hiệu: không đụng tới uvicorn
        import signal as _signal
        shutdown.received(_signal.SIGTERM)
        t.join(5)
        self.assertTrue(server.should_exit)
        # `finished` được đặt thì cầu nối dừng dù không có tín hiệu
        fresh_server, fresh_finished = FakeServer(), _threading.Event()
        t2 = _threading.Thread(target=watch_for_signal, args=(ShutdownLog("bo19.test"), fresh_server, fresh_finished, 0.01))
        t2.start()
        fresh_finished.set()
        t2.join(5)
        self.assertFalse(t2.is_alive() or fresh_server.should_exit)

    def test_sigterm_ngay_sau_khi_vong_poll_bat_dau_van_thoat_nhanh(self):
        for _ in range(3):
            p, _ = self.start()
            self.assertIsNotNone(p.wait_for("WORKER_LOOP_START", 60), p.text()[-2000:])
            started = time.monotonic()
            try:
                code = p.terminate(30)  # gửi ngay: có thể trước cả khi uvicorn cài bộ xử lý
            except subprocess.TimeoutExpired:
                self.fail("không thoát sau SIGTERM 30 s: " + " ".join(m for m in p.messages()[-12:]))
            self.assertEqual(code, 0, p.text()[-2000:])
            self.assertLess(time.monotonic() - started, 6.0)

    def test_sigterm_khi_roi_khong_co_job_thoat_nhanh(self):
        p, _ = self.start()
        self.assertIsNotNone(p.wait_for("WORKER_LOOP_START", 60), p.text()[-2000:])
        self.assertTrue({"CPU_PINNED", "CPU_PIN_SKIPPED"} & set(p.messages()), "combined_main phải quyết định ghim CPU lúc khởi động (WV-34)")
        started = time.monotonic()
        self.assertEqual(p.terminate(30), 0, p.text()[-2000:])
        self.assertLess(time.monotonic() - started, 5.0)


if __name__ == "__main__":
    unittest.main()
