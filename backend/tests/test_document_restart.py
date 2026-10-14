"""Khởi động lại tiến trình khi `document_graph` đang chờ ở `interrupt` vẫn resume đúng — **tiến trình Python thật** (điểm dừng thêm của PO ở B9a, 2026-10-13; mục 6.6 của 03-agents.md).

Mỗi bước là một tiến trình mới (`tests/doc_process.py`): pool riêng, `DocumentRunner` riêng, checkpointer PostgreSQL riêng, provider LLM giả riêng. Giữa hai tiến trình chỉ có PostgreSQL và SeaweedFS — như một lần deploy hay một lần
worker chết. Điều được chứng minh, nói bằng hành vi:

- tiến trình A chạy graph tới `await_content_review` rồi bị **`SIGKILL`** (hay `SIGTERM`); thread vẫn `WAITING` trong DB, checkpoint còn đó; tiến trình B **resume** bằng id `decision_record`, graph tới `END`, thread `ENDED`, và **B không gọi LLM**
  (provider của B không có kịch bản — một lời gọi sẽ là lỗi) cũng không chạy lại node nào đã xong (`document` vẫn một bản render, một dòng `document_free_content`);
- chạy lại `run_render` trong tiến trình mới khi thread đang chờ là no-op;
- tiến trình A bị giết **giữa lúc chạy** (treo ở `docx_render`, sau khi đã sinh và lưu nội dung): tiến trình B chạy `run_render` **tiếp từ checkpoint**, không gọi LLM lại, tới `PENDING_APPROVAL`;
- resume lần hai trong tiến trình khác là no-op.

Cần BO19_TEST_PG_SUPERUSER_DSN, BO19_TEST_S3_*, `soffice` (image target `test`). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_document_restart -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from bo19.orchestrator.runner import document_id_for
from tests.doc_support import BODY_OK, DocBase

BACKEND = Path(__file__).resolve().parents[1]
WAIT_S = 240


class Proc:
    """Một tiến trình `tests.doc_process`. `stdout` đọc từng dòng; `result()` trả dòng `RESULT` đầu tiên."""

    def __init__(self, case: "DocBase", *args: str, llm: str = "none", sleep: bool = False) -> None:
        env = {**os.environ, "BO19_PROC_DSN": case.db.dsn("bo19_app"), "BO19_PROC_BUCKET": case.bucket, "BO19_PROC_LLM": llm, "BO19_PROC_SLEEP": "1" if sleep else "0", "PYTHONUNBUFFERED": "1"}
        self.p = subprocess.Popen([sys.executable, "-m", "tests.doc_process", *args], cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.lines: list[str] = []

    def wait_line(self, prefix: str) -> str:
        deadline = time.monotonic() + WAIT_S
        while time.monotonic() < deadline:
            line = self.p.stdout.readline()
            if not line:
                if self.p.poll() is not None:
                    break
                continue
            self.lines.append(line.rstrip())
            if line.startswith(prefix):
                return line.rstrip()
        raise AssertionError(f"tiến trình không in {prefix!r} (mã thoát {self.p.poll()}, đã in {self.lines})")

    def result(self) -> dict:
        return json.loads(self.wait_line("RESULT ")[len("RESULT "):])

    def kill(self, sig: int = signal.SIGKILL) -> int:
        self.p.send_signal(sig)
        return self.p.wait(30)

    def finish(self) -> int:
        return self.p.wait(WAIT_S)


class KhoiDongLai(DocBase):
    def waiting_request(self):
        """Tiến trình A chạy `run_render` tới điểm dừng rồi ngủ. Trả (request, tiến trình A, kết quả của nó)."""
        rid = self.submitted_request()
        a = Proc(self, "render", str(rid), llm="ok", sleep=True)
        self.addCleanup(lambda: a.p.poll() is None and a.p.kill())
        return rid, a, a.result()

    def assert_waiting_in_db(self, rid):
        self.assertEqual(self.document(rid)["status"], "PENDING_APPROVAL")
        thread = self.thread(rid)
        self.assertEqual((thread["status"], thread["waiting_at_node"]), ("WAITING", "await_content_review"))
        self.assertGreater(len(self.checkpoint_text()), 500)  # checkpoint còn trong PostgreSQL

    def test_giet_sigkill_khi_dang_cho_roi_tien_trinh_moi_resume_dung(self):
        rid, a, first = self.waiting_request()
        self.assertEqual((first["status"], first["waiting_at"], first["llm_calls"]), ("WAITING", "await_content_review", 1))
        self.assertEqual(a.kill(signal.SIGKILL), -signal.SIGKILL)  # chết đột ngột, không dọn gì
        self.assert_waiting_in_db(rid)
        before = (self.scalar("select count(*) from document_render where document_id = %s", document_id_for(rid)),
                  self.scalar("select count(*) from document_free_content where document_id = %s", document_id_for(rid)),
                  self.scalar("select count(*) from approval_step where document_id = %s", document_id_for(rid)))
        decision = self.approve(rid)
        b = Proc(self, "resume", str(document_id_for(rid)), str(decision), llm="none")  # KHÔNG có kịch bản LLM: một lời gọi sẽ làm tiến trình hỏng
        out = b.result()
        self.assertEqual(b.finish(), 0)
        self.assertEqual((out["status"], out["already"], out["llm_calls"]), ("ENDED", False, 0))
        self.assertNotEqual(out["pid"], first["pid"])  # đúng là tiến trình khác
        thread = self.thread(rid)
        self.assertEqual((thread["status"], thread["waiting_at_node"], thread["ended_at"] is not None), ("ENDED", None, True))
        self.assertEqual(before, (self.scalar("select count(*) from document_render where document_id = %s", document_id_for(rid)),
                                  self.scalar("select count(*) from document_free_content where document_id = %s", document_id_for(rid)),
                                  self.scalar("select count(*) from approval_step where document_id = %s", document_id_for(rid))))  # không node nào chạy lại
        self.assertEqual(self.scalar("select count(*) from llm_usage where document_id = %s", document_id_for(rid)), 1)  # đúng một lời gọi, của tiến trình A
        self.assertEqual(self.document(rid)["status"], "PENDING_APPROVAL")  # B9a không đổi trạng thái document sau resume (B9b)

    def test_sigterm_cung_the(self):
        rid, a, _ = self.waiting_request()
        a.kill(signal.SIGTERM)
        self.assert_waiting_in_db(rid)
        decision = self.approve(rid)
        b = Proc(self, "resume", str(document_id_for(rid)), str(decision), llm="none")
        self.assertEqual((b.result()["status"], b.finish()), ("ENDED", 0))

    def test_chay_lai_run_render_trong_tien_trinh_moi_khi_dang_cho_la_no_op(self):
        rid, a, _ = self.waiting_request()
        a.kill()
        b = Proc(self, "render", str(rid), llm="none")
        out = b.result()
        self.assertEqual((out["status"], out["already"], out["llm_calls"]), ("WAITING", True, 0))
        self.assertEqual(b.finish(), 0)
        self.assert_waiting_in_db(rid)
        self.assertEqual(self.scalar("select count(*) from document where request_id = %s", rid), 1)

    def test_resume_lan_hai_o_tien_trinh_khac_la_no_op(self):
        rid, a, _ = self.waiting_request()
        a.kill()
        decision = self.approve(rid)
        for expected_already in (False, True):
            p = Proc(self, "resume", str(document_id_for(rid)), str(decision), llm="none")
            out = p.result()
            self.assertEqual((out["status"], out["already"], p.finish()), ("ENDED", expected_already, 0))

    def test_resume_voi_quyet_dinh_cua_document_khac_hong_va_thread_van_cho(self):
        rid, a, _ = self.waiting_request()
        a.kill()
        other = self.submitted_request()
        self.run_render_ok(other)
        foreign = self.approve(other)
        p = Proc(self, "resume", str(document_id_for(rid)), str(foreign), llm="none")
        out = p.result()
        self.assertEqual((out["error"], p.finish()), ("SYSTEM_DEFECT", 1))
        self.assertEqual(self.thread(rid)["status"], "WAITING")

    def run_render_ok(self, rid):
        self.llm.will("draft_free_content", {"variable_name": "purpose_statement", "body": BODY_OK})
        self.runner.run_render(request_id=rid)

    def test_giet_giua_luc_chay_tien_trinh_moi_tiep_tu_checkpoint_khong_goi_llm_lai(self):
        rid = self.submitted_request()
        a = Proc(self, "hang", str(rid), llm="ok")
        self.addCleanup(lambda: a.p.poll() is None and a.p.kill())
        a.wait_line("HANGING")  # đã sinh và lưu nội dung, đang kẹt ở `docx_render`
        self.assertEqual(a.kill(signal.SIGKILL), -signal.SIGKILL)
        self.assertEqual(self.document(rid)["status"], "DRAFT")
        self.assertEqual([(a_, o) for _, _, a_, o, _, _ in self.free_content(rid)], [(1, "PASSED")])
        self.assertEqual(self.scalar("select count(*) from document_render where document_id = %s", document_id_for(rid)), 0)
        b = Proc(self, "render", str(rid), llm="none")  # job thử lại; KHÔNG có kịch bản LLM
        out = b.result()
        self.assertEqual((out["status"], out["already"], out["llm_calls"], b.finish()), ("WAITING", False, 0, 0))
        self.assertEqual(self.document(rid)["status"], "PENDING_APPROVAL")
        self.assertEqual(self.scalar("select count(*) from document where request_id = %s", rid), 1)
        self.assertEqual(self.scalar("select count(*) from llm_usage where document_id = %s", document_id_for(rid)), 1)
        self.assertEqual(self.thread(rid)["status"], "WAITING")
