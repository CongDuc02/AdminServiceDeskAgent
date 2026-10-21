"""Khởi động lại tiến trình khi `document_graph` đang chờ ở `interrupt` vẫn resume đúng — **tiến trình Python thật** (điểm dừng thêm của PO ở B9a, 2026-10-13; mục 6.6 của 03-agents.md).

Mỗi bước là một tiến trình mới (`tests/doc_process.py`): pool riêng, `DocumentRunner` riêng, checkpointer PostgreSQL riêng, provider LLM giả riêng. Giữa hai tiến trình chỉ có PostgreSQL và SeaweedFS — như một lần deploy hay một lần
worker chết. Điều được chứng minh, nói bằng hành vi:

- tiến trình A chạy graph tới `await_content_review` rồi bị **`SIGKILL`** (hay `SIGTERM`); thread vẫn `WAITING` trong DB, checkpoint còn đó; tiến trình B **resume** bằng id `decision_record` của thao tác cổng THẬT, graph đi qua
  `route_review`, `route_signing` tới `await_signature` (B9b1), và **B không gọi LLM** (provider của B không có kịch bản — một lời gọi sẽ là lỗi) cũng không chạy lại node nào đã xong (`document` vẫn một bản render, một dòng `document_free_content`);
- **giữa các cổng (B9b1):** mỗi điểm chờ — `await_signature`, `await_seal`, `await_issue` — bị `SIGKILL` rồi tiến trình mới resume bằng quyết định kế tiếp (`SIGNED`, `SEALED`) vẫn đúng; tiến trình bị giết **giữa lúc** `route_signing` chạy
  (treo ở `render_integrity_check`) thì tiến trình mới tiếp từ checkpoint tới `await_signature`;
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
        code = self.p.wait(30)
        self.p.stdout.close()
        return code

    def finish(self) -> int:
        code = self.p.wait(WAIT_S)
        self.p.stdout.close()
        return code


class KhoiDongLai(DocBase):
    def waiting_request(self):
        """Tiến trình A chạy `run_render` tới điểm dừng rồi ngủ. Trả (request, tiến trình A, kết quả của nó)."""
        rid = self.submitted_request()
        a = Proc(self, "render", str(rid), llm="ok", sleep=True)
        self.addCleanup(self.reap, a)
        return rid, a, a.result()

    @staticmethod
    def reap(proc: Proc) -> None:
        if proc.p.poll() is None:
            proc.p.kill()
            proc.p.wait(30)
        if not proc.p.stdout.closed:
            proc.p.stdout.close()

    def assert_waiting_in_db(self, rid):
        self.assertEqual(self.document(rid)["status"], "PENDING_APPROVAL")
        thread = self.thread(rid)
        self.assertEqual((thread["status"], thread["waiting_at_node"]), ("WAITING", "await_content_review"))
        self.assertGreater(len(self.checkpoint_text()), 500)  # checkpoint còn trong PostgreSQL

    def test_giet_sigkill_khi_dang_cho_roi_tien_trinh_moi_resume_dung(self):
        self.make_signer()
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
        self.assertEqual((out["status"], out["waiting_at"], out["already"], out["llm_calls"]), ("WAITING", "await_signature", False, 0))
        self.assertNotEqual(out["pid"], first["pid"])  # đúng là tiến trình khác
        thread = self.thread(rid)
        self.assertEqual((thread["status"], thread["waiting_at_node"], thread["ended_at"]), ("WAITING", "await_signature", None))
        self.assertEqual(before[:2], (self.scalar("select count(*) from document_render where document_id = %s", document_id_for(rid)),
                                      self.scalar("select count(*) from document_free_content where document_id = %s", document_id_for(rid))))  # không node soạn/render nào chạy lại
        self.assertEqual(self.scalar("select count(*) from approval_step where document_id = %s", document_id_for(rid)), before[2] + 1)  # chỉ thêm bước SIGNATURE
        self.assertEqual(self.scalar("select count(*) from llm_usage where document_id = %s", document_id_for(rid)), 1)  # đúng một lời gọi, của tiến trình A
        self.assertEqual(self.document(rid)["status"], "PENDING_SIGNATURE")

    def test_sigterm_cung_the(self):
        self.make_signer()
        rid, a, _ = self.waiting_request()
        a.kill(signal.SIGTERM)
        self.assert_waiting_in_db(rid)
        decision = self.approve(rid)
        b = Proc(self, "resume", str(document_id_for(rid)), str(decision), llm="none")
        out = b.result()
        self.assertEqual((out["status"], out["waiting_at"], b.finish()), ("WAITING", "await_signature", 0))

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
        self.make_signer()
        rid, a, _ = self.waiting_request()
        a.kill()
        decision = self.approve(rid)
        for expected_already in (False, True):
            p = Proc(self, "resume", str(document_id_for(rid)), str(decision), llm="none")
            out = p.result()
            self.assertEqual((out["status"], out["waiting_at"], out["already"], p.finish()), ("WAITING", "await_signature", expected_already, 0))

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

    def test_giet_giua_cac_cong_moi_diem_cho_resume_dung_bang_tien_trinh_moi(self):
        """Duyệt → ký → đóng dấu, mỗi bước một tiến trình riêng bị `SIGKILL` khi graph đang chờ ở điểm kế tiếp; không lời gọi LLM nào ngoài lời gọi đầu."""
        from bo19.tool_layer.gate_ops.document_apply_seal import document_apply_seal
        from bo19.tool_layer.gate_ops.document_sign import document_sign
        from bo19.tool_layer.kernel.permission import employee_context

        self.make_signer()
        rid, a, _ = self.waiting_request()
        did = document_id_for(rid)
        a.kill()
        approved = self.approve(rid)
        p1 = Proc(self, "resume", str(did), str(approved), llm="none", sleep=True)  # đi tới await_signature rồi ngủ
        self.addCleanup(self.reap, p1)
        self.assertEqual(p1.result()["waiting_at"], "await_signature")
        p1.kill()
        self.assertEqual((self.document(rid)["status"], self.thread(rid)["waiting_at_node"]), ("PENDING_SIGNATURE", "await_signature"))
        assigned = self.scalar("select signer_employee_id from document where id = %s", did)  # `signing_route` chọn mã nhỏ nhất trong cả DB của lớp — không nhất thiết là `signer_id`
        self.assertIsNotNone(assigned)
        with self.pool.acquire() as conn:
            sctx, octx = employee_context(conn, assigned), employee_context(conn, self.scalar("select actor_employee_id from decision_record where id = %s", approved))
        version = lambda: self.scalar("select row_version from document where id = %s", did)  # noqa: E731
        signed = document_sign(self.pool, sctx, document_id=did, decision_id=uuid.uuid4(), expected_row_version=version()).decision_record_id
        p2 = Proc(self, "resume", str(did), str(signed), llm="none", sleep=True)
        self.addCleanup(self.reap, p2)
        self.assertEqual(p2.result()["waiting_at"], "await_seal")
        p2.kill()
        self.assertEqual((self.document(rid)["status"], self.thread(rid)["waiting_at_node"]), ("PENDING_SEAL", "await_seal"))
        sealed = document_apply_seal(self.pool, octx, document_id=did, decision_id=uuid.uuid4(), expected_row_version=version(), copies_count=1, page_count=None).decision_record_id
        p3 = Proc(self, "resume", str(did), str(sealed), llm="none", sleep=True)
        self.addCleanup(self.reap, p3)
        self.assertEqual(p3.result()["waiting_at"], "await_issue")
        p3.kill()
        self.assertEqual((self.document(rid)["status"], self.thread(rid)["status"], self.thread(rid)["waiting_at_node"]), ("SEALED", "WAITING", "await_issue"))
        for stale in (approved, signed, sealed):  # chạy lại quyết định đã xử lý ở một tiến trình khác: no-op
            p = Proc(self, "resume", str(did), str(stale), llm="none")
            out = p.result()
            self.assertEqual((out["waiting_at"], out["already"], p.finish()), ("await_issue", True, 0))
        self.assertEqual(self.scalar("select count(*) from llm_usage where document_id = %s", did), 1)

    def test_giet_giua_luc_route_signing_tien_trinh_moi_tiep_tu_checkpoint(self):
        self.make_signer()
        rid, a, _ = self.waiting_request()
        a.kill()
        approved = self.approve(rid)
        h = Proc(self, "hang_resume", str(document_id_for(rid)), str(approved), llm="none")
        self.addCleanup(self.reap, h)
        h.wait_line("HANGING")  # đã qua await_content_review và route_review, treo ở render_integrity_check
        self.assertEqual(h.kill(signal.SIGKILL), -signal.SIGKILL)
        self.assertEqual(self.document(rid)["status"], "APPROVED")  # chưa giao người ký
        b = Proc(self, "resume", str(document_id_for(rid)), str(approved), llm="none")
        out = b.result()
        self.assertEqual((out["status"], out["waiting_at"], out["already"], out["llm_calls"], b.finish()), ("WAITING", "await_signature", False, 0, 0))
        self.assertEqual(self.document(rid)["status"], "PENDING_SIGNATURE")
        self.assertEqual(self.scalar("select count(*) from approval_step where document_id = %s and step_kind = 'SIGNATURE'", document_id_for(rid)), 1)
        self.assertEqual(self.scalar("select count(*) from llm_usage where document_id = %s", document_id_for(rid)), 1)

    def run_render_ok(self, rid):
        self.llm.will("draft_free_content", {"variable_name": "purpose_statement", "body": BODY_OK})
        self.runner.run_render(request_id=rid)

    def test_giet_giua_luc_chay_tien_trinh_moi_tiep_tu_checkpoint_khong_goi_llm_lai(self):
        rid = self.submitted_request()
        a = Proc(self, "hang", str(rid), llm="ok")
        self.addCleanup(self.reap, a)
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

    # ---- B9b2: giết tiến trình trong `finalize_issue` (ADR-041 mục 5) ------------------------------------------------------------

    def to_await_issue(self):
        """Đưa một `request` tới `await_issue` bằng runner của test (không tiến trình con) và thao tác cổng thật, rồi ghi lệnh phát hành. Trả (rid, document_id, id lệnh phát hành)."""
        from bo19.tool_layer.gate_ops.document_apply_seal import document_apply_seal
        from bo19.tool_layer.gate_ops.document_issue import document_issue
        from bo19.tool_layer.gate_ops.document_sign import document_sign
        from bo19.tool_layer.kernel.permission import employee_context

        with self.db.connect(autocommit=True) as c:  # siêu người dùng + replica: văn bản ISSUED của test trước còn trỏ tới dòng sổ
            c.execute("set session_replication_role = replica")
            reg = c.execute("select document_register_id from request_type where code = 'WORK_CONFIRMATION'").fetchone()[0]
            c.execute("insert into document_register_format (id, document_register_id, series, format_pattern, symbol, seq_min_digits, effective_from) "
                      "values (%s, %s, 'TRIAL', 'TRIAL-{seq}/{year}/{symbol}', 'THU-NGHIEM', 3, timestamptz '2020-01-01 00:00:00+00') on conflict do nothing", (uuid.uuid4(), reg))
            c.execute("delete from document_register_entry")  # bộ đếm sạch cho mỗi test: số kỳ vọng tính từ 001
            c.execute("delete from document_register_counter")
        self.make_signer()
        rid = self.submitted_request()
        did = document_id_for(rid)
        self.llm.will("draft_free_content", {"variable_name": "purpose_statement", "body": BODY_OK})
        self.runner.run_render(request_id=rid)
        approved = self.approve(rid)
        self.runner.resume_document(document_id=did, decision_record_id=approved)
        assigned = self.scalar("select signer_employee_id from document where id = %s", did)
        officer = self.scalar("select actor_employee_id from decision_record where id = %s", approved)
        version = lambda: self.scalar("select row_version from document where id = %s", did)  # noqa: E731
        with self.pool.acquire() as conn:
            sctx, octx = employee_context(conn, assigned), employee_context(conn, officer)
        signed = document_sign(self.pool, sctx, document_id=did, decision_id=uuid.uuid4(), expected_row_version=version()).decision_record_id
        self.runner.resume_document(document_id=did, decision_record_id=signed)
        sealed = document_apply_seal(self.pool, octx, document_id=did, decision_id=uuid.uuid4(), expected_row_version=version(), copies_count=1, page_count=None).decision_record_id
        self.runner.resume_document(document_id=did, decision_record_id=sealed)
        order = document_issue(self.pool, octx, document_id=did, decision_id=uuid.uuid4(), expected_row_version=version()).decision_record_id
        self.assertEqual((self.document(rid)["status"], self.thread(rid)["waiting_at_node"]), ("SEALED", "await_issue"))
        return rid, did, order

    def entry(self, did) -> tuple:
        return self.rows("select id, seq, status from document_register_entry where document_id = %s", did)[0]

    def assert_issued_once(self, rid, did, entry_before):
        self.assertEqual(self.document(rid)["status"], "ISSUED")
        self.assertEqual(self.rows("select id, seq, status from document_register_entry where document_id = %s", did), [entry_before])  # đúng một dòng sổ — cùng số
        self.assertEqual(self.scalar("select next_seq from document_register_counter"), entry_before[1] + 1)  # bộ đếm tăng đúng một lần
        self.assertEqual(self.scalar("select count(*) from document_render where document_id = %s and render_kind = 'FINAL'", did), 1)
        self.assertEqual(self.scalar("select count(*) from document_render_pin p join document_render r on r.id = p.render_id where r.document_id = %s and p.pin_reason = 'ISSUED'", did), 1)
        self.assertEqual(self.scalar("select count(*) from audit_event where document_id = %s and action = 'document.issue_complete'", did), 1)
        self.assertEqual(self.scalar("select status from request where id = %s", rid), "FULFILLED")
        self.assertEqual(self.thread(rid)["status"], "ENDED")

    def test_giet_sau_khi_cap_so_truoc_khi_chuyen_pdf_tien_trinh_moi_phat_hanh_dung_so_do(self):
        rid, did, order = self.to_await_issue()
        h = Proc(self, "hang_finalize_pdf", str(did), str(order), llm="none")
        self.addCleanup(self.reap, h)
        h.wait_line("HANGING")  # đã cấp số, đã ghi .docx bản FINAL, kẹt ở pdf_export
        self.assertEqual(h.kill(signal.SIGKILL), -signal.SIGKILL)
        before = self.entry(did)
        self.assertEqual((before[1], before[2]), (1, "ASSIGNED"))
        self.assertEqual((self.document(rid)["status"], self.scalar("select count(*) from document_render where document_id = %s and render_kind = 'FINAL'", did)), ("SEALED", 0))
        b = Proc(self, "finalize", str(did), str(order), llm="none")
        out = b.result()
        self.assertEqual((out["status"], out["already"], out["llm_calls"], b.finish()), ("ENDED", False, 0, 0))
        self.assert_issued_once(rid, did, before)

    def test_giet_truoc_giao_dich_issued_tien_trinh_moi_ghim_dung_ban_final_da_ghi(self):
        rid, did, order = self.to_await_issue()
        h = Proc(self, "hang_finalize_mark", str(did), str(order), llm="none")
        self.addCleanup(self.reap, h)
        h.wait_line("HANGING")  # đã cấp số, ghi cặp .docx/.pdf FINAL, kiểm byte đạt; kẹt ngay trước giao dịch ISSUED
        self.assertEqual(h.kill(signal.SIGKILL), -signal.SIGKILL)
        before = self.entry(did)
        render_before = self.scalar("select id from document_render where document_id = %s and render_kind = 'FINAL'", did)
        self.assertIsNotNone(render_before)  # bản FINAL đã ghi...
        self.assertEqual((self.document(rid)["status"], self.scalar("select count(*) from document_render_pin where render_id = %s", render_before)), ("SEALED", 0))  # ...nhưng chưa ghim, chưa ISSUED
        b = Proc(self, "finalize", str(did), str(order), llm="none")
        out = b.result()
        self.assertEqual((out["status"], out["already"], b.finish()), ("ENDED", False, 0))
        self.assert_issued_once(rid, did, before)
        self.assertEqual(self.scalar("select final_render_id from document where id = %s", did), render_before)  # đúng bản đã ghi, không bản thứ hai

    def test_chay_lai_sau_khi_issued_o_tien_trinh_khac_la_no_op(self):
        rid, did, order = self.to_await_issue()
        a = Proc(self, "finalize", str(did), str(order), llm="none", sleep=True)
        self.addCleanup(self.reap, a)
        self.assertEqual(a.result()["status"], "ENDED")
        a.kill()
        before = self.entry(did)
        b = Proc(self, "finalize", str(did), str(order), llm="none")
        out = b.result()
        self.assertEqual((out["status"], out["already"], b.finish()), ("ENDED", True, 0))
        self.assert_issued_once(rid, did, before)
