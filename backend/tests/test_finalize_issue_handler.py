"""Handler của job `finalize_issue` (B9b2, ADR-041 mục 3) với runner GIẢ — không DB, không object storage.

Chứng minh khi nào handler huỷ số: CHỈ khi job sắp `FAILED` — lỗi vĩnh viễn, hoặc lỗi tạm ở lượt cuối (`attempts >= max_attempts`, đúng điều kiện `final` của dispatcher) — và lỗi không phải `JOB_CANCELLED`
(drain / mất lease không phải bỏ cuộc). Lỗi tạm còn lượt thì KHÔNG huỷ: lần thử sau dùng lại chính số đó. Payload sai hình là lỗi lập trình, không đụng số nào. Lý do huỷ: mã vĩnh viễn, hoặc `ISSUE_RETRIES_EXHAUSTED`.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_finalize_issue_handler -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import datetime as dt
import unittest
import uuid

from bo19.orchestrator.runner import RenderFailed, RenderOutcome
from bo19.queue_worker.dispatcher import JobContext, JobFailure
from bo19.queue_worker.handlers import build_handlers
from bo19.queue_worker.handlers.finalize_issue import RETRIES_EXHAUSTED, make_finalize_issue_handler
from bo19.tool_layer import jobs

DOC, DECISION = uuid.uuid4(), uuid.uuid4()


class FakeRunner:
    def __init__(self, error: RenderFailed | None = None) -> None:
        self.error, self.finalized, self.abandoned = error, [], []

    def run_finalize_issue(self, *, document_id, decision_record_id, cancel=None):
        self.finalized.append((document_id, decision_record_id))
        if self.error:
            raise self.error
        return RenderOutcome(document_id, "ENDED", None, False)

    def abandon_issue(self, *, document_id, reason_code, trace_id=None):
        self.abandoned.append((document_id, reason_code))
        return uuid.uuid4()


def job(attempts: int = 1, max_attempts: int = 5, payload: dict | None = None) -> jobs.ClaimedJob:
    return jobs.ClaimedJob(id=uuid.uuid4(), job_type="finalize_issue", payload=payload if payload is not None else {"document_id": str(DOC), "decision_record_id": str(DECISION)},
                           subject_document_id=DOC, dedupe_key=str(DECISION), attempts=attempts, max_attempts=max_attempts, locked_by="w", locked_at=dt.datetime.now(dt.timezone.utc), lease_id=uuid.uuid4())


def failed(code: str, *, permanent: bool, retry_after_s: int | None = None) -> RenderFailed:
    return RenderFailed(code, permanent=permanent, retry_after_s=retry_after_s, raw_code=code)


class Handler(unittest.TestCase):
    def run_handler(self, runner: FakeRunner, j: jobs.ClaimedJob):
        return make_finalize_issue_handler(runner)(j, JobContext())  # type: ignore[arg-type]

    def test_thanh_cong_chi_goi_run_finalize_issue_voi_dung_id(self):
        r = FakeRunner()
        self.run_handler(r, job())
        self.assertEqual((r.finalized, r.abandoned), ([(DOC, DECISION)], []))

    def test_loi_vinh_vien_huy_so_voi_ma_do_roi_job_failed_ngay(self):
        r = FakeRunner(failed("CONTENT_HASH_MISMATCH", permanent=True))
        with self.assertRaises(JobFailure) as cm:
            self.run_handler(r, job(attempts=1, max_attempts=5))
        self.assertEqual((cm.exception.code, cm.exception.permanent), ("CONTENT_HASH_MISMATCH", True))
        self.assertEqual(r.abandoned, [(DOC, "CONTENT_HASH_MISMATCH")])

    def test_loi_tam_con_luot_khong_huy_so_va_giu_retry_after(self):
        r = FakeRunner(failed("PROVIDER_UNAVAILABLE", permanent=False, retry_after_s=17))
        with self.assertRaises(JobFailure) as cm:
            self.run_handler(r, job(attempts=4, max_attempts=5))
        self.assertEqual((cm.exception.code, cm.exception.permanent, cm.exception.retry_after_s), ("PROVIDER_UNAVAILABLE", False, 17))
        self.assertEqual(r.abandoned, [])

    def test_loi_tam_o_luot_cuoi_huy_so_voi_ly_do_het_luot_nhung_job_giu_ma_goc(self):
        for attempts, max_attempts in ((5, 5), (6, 5), (1, 1)):
            r = FakeRunner(failed("RENDER_CONVERSION_FAILED", permanent=False))
            with self.assertRaises(JobFailure) as cm:
                self.run_handler(r, job(attempts=attempts, max_attempts=max_attempts))
            self.assertEqual((cm.exception.code, cm.exception.permanent), ("RENDER_CONVERSION_FAILED", False), (attempts, max_attempts))
            self.assertEqual(r.abandoned, [(DOC, RETRIES_EXHAUSTED)], (attempts, max_attempts))
        self.assertEqual(RETRIES_EXHAUSTED, "ISSUE_RETRIES_EXHAUSTED")

    def test_job_cancelled_khong_bao_gio_huy_so(self):
        for permanent, attempts in ((False, 5), (False, 1), (True, 1)):
            r = FakeRunner(failed("JOB_CANCELLED", permanent=permanent))
            with self.assertRaises(JobFailure):
                self.run_handler(r, job(attempts=attempts, max_attempts=5))
            self.assertEqual(r.abandoned, [], (permanent, attempts))

    def test_payload_sai_hinh_la_loi_lap_trinh_khong_dung_so(self):
        for payload in ({}, {"document_id": str(DOC)}, {"document_id": "không-phải-uuid", "decision_record_id": str(DECISION)}, {"document_id": str(DOC), "decision_record_id": None}):
            r = FakeRunner()
            with self.assertRaises(JobFailure) as cm:
                self.run_handler(r, job(payload=payload))
            self.assertEqual((cm.exception.code, cm.exception.permanent), ("SYSTEM_DEFECT", True))
            self.assertEqual((r.finalized, r.abandoned), ([], []))

    def test_dang_ky_o_build_handlers_khi_co_runner(self):
        self.assertNotIn("finalize_issue", build_handlers(document_runner=None))
        handlers = build_handlers(document_runner=FakeRunner())  # type: ignore[arg-type]
        self.assertIn("finalize_issue", handlers)
        self.assertEqual({"render_document", "resume_document_graph", "finalize_issue"} - set(handlers), set())


if __name__ == "__main__":
    unittest.main()
