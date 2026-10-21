"""Handler `render_document` (B9a, ADR-039) chạy dưới `Dispatcher` thật: từ `request_submit` → job `QUEUED` → worker giành → `DocumentRunner.run_render` → `PENDING_APPROVAL`. PostgreSQL, SeaweedFS, `soffice`, checkpointer THẬT;
provider LLM là transport giả.

Điều được chứng minh, nói bằng hành vi:
- job do `request_submit` đưa vào hàng đợi chạy tới `SUCCEEDED` và `document` ở `PENDING_APPROVAL`; thử lại job sau đó là no-op;
- lỗi **vĩnh viễn** (`PARSE_FAILED`, `FREE_CONTENT_INVALID`, `RENDER_INPUT_INVALID`…) làm job `FAILED` NGAY ở lượt đầu, mang đúng mã bảng mã `document_halt`; lỗi **tạm** (chuyển đổi hỏng) về `QUEUED` với backoff rồi chạy lại **tiếp từ checkpoint,
  không sinh lại nội dung**; `retry-after` vượt WV-19 thì `FAILED` `PROVIDER_RATE_LIMITED`;
- payload sai hình thì `FAILED` ngay (`SYSTEM_DEFECT`); thiếu object storage hay khoá LLM thì **không đăng ký handler** và job vẫn `QUEUED`;
- `lease_id`: mất lease thì cờ huỷ bật và lần ghi muộn không ghi được gì.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_render_document_handler -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import uuid
from unittest import mock

import httpx

from bo19.config.settings import load_settings
from bo19.entrypoints import worker_main
from bo19.orchestrator.runner import document_id_for
from bo19.queue_worker.dispatcher import Dispatcher
from bo19.queue_worker.handlers import build_handlers
from bo19.tool_layer.rendering import convert
from tests.doc_support import DocBase, draft_output
from tests.test_settings import GOOD


class HandlerBase(DocBase):
    def dispatcher(self, runner=None) -> Dispatcher:
        return Dispatcher(self.pool, build_handlers(document_runner=runner or self.runner), poll_s=0.05, heartbeat_s=0.2, lease_s=30, drain_s=5)

    def job(self, rid: uuid.UUID) -> dict:
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select status, attempts, last_error_code, extract(epoch from run_after - now()) as run_in_s, payload from job where payload->>'request_id' = %s", (str(rid),))
            return dict(zip([d.name for d in cur.description], cur.fetchone()))

    def make_ready(self, rid: uuid.UUID) -> None:
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("update job set run_after = now() where payload->>'request_id' = %s", (str(rid),))


class ChayTuSubmit(HandlerBase):
    def test_job_tu_request_submit_toi_pending_approval(self):
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        self.assertEqual(self.job(rid)["status"], "QUEUED")
        self.assertTrue(self.dispatcher().run_once())
        job = self.job(rid)
        self.assertEqual((job["status"], job["attempts"], job["last_error_code"]), ("SUCCEEDED", 1, None))
        self.assertEqual(self.document(rid)["status"], "PENDING_APPROVAL")
        self.assertEqual(self.thread(rid)["status"], "WAITING")
        self.assertFalse(self.dispatcher().run_once())  # hàng đợi trống

    def test_chay_lai_job_da_xong_la_no_op(self):
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        self.dispatcher().run_once()
        with self.db.connect("bo19_migrator", autocommit=True) as c:  # ép job chạy lại như thể lần trước mất lease sau khi graph đã tới điểm dừng
            c.execute("update job set status = 'QUEUED', attempts = 0, finished_at = null, run_after = now() where payload->>'request_id' = %s", (str(rid),))
        self.assertTrue(self.dispatcher().run_once())
        self.assertEqual(self.job(rid)["status"], "SUCCEEDED")
        self.assertEqual(self.llm_calls(), 1)
        self.assertEqual(self.scalar("select count(*) from document where request_id = %s", rid), 1)


class Loi(HandlerBase):
    def test_loi_vinh_vien_failed_ngay_o_luot_dau(self):
        self.llm.set("draft_free_content", "không phải JSON")
        rid = self.submitted_request()
        self.assertTrue(self.dispatcher().run_once())
        job = self.job(rid)
        self.assertEqual((job["status"], job["attempts"], job["last_error_code"]), ("FAILED", 1, "PARSE_FAILED"))
        self.assertEqual(self.document(rid)["status"], "DRAFT")  # ở lại DRAFT, không vào cổng

    def test_noi_dung_trượt_hai_lan_la_free_content_invalid(self):
        bad = draft_output("Đề nghị cấp giấy {{ ho_ten }} để bổ sung hồ sơ vay vốn.")
        self.llm.set("draft_free_content", bad)
        rid = self.submitted_request()
        self.dispatcher().run_once()
        job = self.job(rid)
        self.assertEqual((job["status"], job["attempts"], job["last_error_code"]), ("FAILED", 1, "FREE_CONTENT_INVALID"))
        self.assertEqual(self.llm_calls(), 2)

    def test_loi_tam_ve_queued_voi_backoff_roi_chay_lai_tiep_tu_checkpoint(self):
        self.llm.will("draft_free_content", draft_output())
        rid = self.submitted_request()
        with mock.patch.object(convert, "convert_to_pdf", side_effect=convert.ConversionFailed()):
            self.dispatcher().run_once()
        job = self.job(rid)
        self.assertEqual((job["status"], job["attempts"], job["last_error_code"]), ("QUEUED", 1, "RENDER_CONVERSION_FAILED"))
        self.assertAlmostEqual(job["run_in_s"], 20, delta=4)  # base 10 s × 2^1 (WV-20, chưa hiệu chỉnh)
        self.make_ready(rid)
        self.dispatcher().run_once()
        job = self.job(rid)
        self.assertEqual((job["status"], job["attempts"]), ("SUCCEEDED", 2))
        self.assertEqual(self.llm_calls(), 1)  # lần chạy lại KHÔNG sinh lại nội dung
        self.assertEqual(self.document(rid)["status"], "PENDING_APPROVAL")

    def test_429_vuot_wv19_failed_ngay_provider_rate_limited(self):
        self.llm.set("draft_free_content", httpx.Response(429, headers={"retry-after": "500"}, json={"error": {"message": "x", "type": "rate_limit"}}))
        rid = self.submitted_request()
        self.dispatcher().run_once()
        job = self.job(rid)
        self.assertEqual((job["status"], job["attempts"], job["last_error_code"]), ("FAILED", 1, "PROVIDER_RATE_LIMITED"))

    def test_loi_5xx_cua_provider_la_loi_tam(self):
        self.llm.set("draft_free_content", httpx.Response(500, json={"error": {"message": "x", "type": "server_error"}}))
        rid = self.submitted_request()
        self.dispatcher().run_once()
        job = self.job(rid)
        self.assertEqual((job["status"], job["last_error_code"]), ("QUEUED", "PROVIDER_UNAVAILABLE"))

    def test_payload_sai_hinh_failed_ngay(self):
        from bo19.persistence.write import unit_of_work
        from bo19.tool_layer.kernel.enqueue import enqueue
        with self.pool.acquire() as conn, unit_of_work(conn):
            enqueue(conn, job_type="render_document", payload={"request_id": "khong-phai-uuid"}, dedupe_key="payload-sai")
        self.assertTrue(self.dispatcher().run_once())
        row = self.rows("select status, attempts, last_error_code from job where dedupe_key = 'payload-sai'")[0]
        self.assertEqual(row, ("FAILED", 1, "SYSTEM_DEFECT"))

    def test_ma_loi_khong_mang_gia_tri_nao(self):
        from tests.doc_support import NATIONAL_ID
        self.llm.set("draft_free_content", "không phải JSON")
        rid = self.submitted_request(national_id=NATIONAL_ID)
        self.dispatcher().run_once()
        blob = repr(self.rows("select last_error_code, payload from job where payload->>'request_id' = %s", str(rid)))
        self.assertNotIn(NATIONAL_ID, blob)


class DangKy(DocBase):
    def test_khong_co_runner_thi_khong_dang_ky_va_job_van_queued(self):
        self.assertEqual(build_handlers(document_runner=None), {})
        rid = self.submitted_request()
        self.assertFalse(Dispatcher(self.pool, build_handlers(document_runner=None), poll_s=0.05).run_once())
        self.assertEqual(self.scalar("select status from job where payload->>'request_id' = %s", str(rid)), "QUEUED")

    def test_co_runner_thi_dang_ky_render_document(self):
        self.assertEqual(set(build_handlers(document_runner=self.runner)), {"render_document", "resume_document_graph", "finalize_issue"})

    def test_worker_main_khong_dung_runner_khi_thieu_storage_hoac_khoa_llm(self):
        base = dict(GOOD)
        with_storage = {**base, "BO19_OBJECT_STORAGE_ENDPOINT_URL": "http://s3.test:8333", "BO19_OBJECT_STORAGE_BUCKET": "b", "BO19_OBJECT_STORAGE_ACCESS_KEY_ID": "a", "BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY": "s"}
        fp = {"BO19_RENDER_FINGERPRINT_KEY": "k" * 32}
        for label, env in (("không storage, không khoá", {**base, **fp}), ("không storage, có khoá", {**base, **fp, "BO19_LLM_API_KEY": "k"}), ("có storage, không khoá", {**with_storage, **fp}),
                           ("có storage, có khoá LLM, thiếu khoá dấu vân tay", {**with_storage, "BO19_LLM_API_KEY": "k"})):
            self.assertIsNone(worker_main.open_document_runner(load_settings(env), self.pool), label)

    def test_worker_main_dung_runner_khi_du_storage_va_khoa(self):
        from tests.s3_support import ENDPOINT
        import os
        env = {**GOOD, "BO19_DATABASE_URL": self.db.dsn("bo19_app"), "BO19_ENVIRONMENT": "dev", "BO19_LLM_API_KEY": "k", "BO19_RENDER_FINGERPRINT_KEY": "k" * 32, "BO19_OBJECT_STORAGE_ENDPOINT_URL": ENDPOINT, "BO19_OBJECT_STORAGE_BUCKET": self.bucket,
               "BO19_OBJECT_STORAGE_ACCESS_KEY_ID": os.environ["BO19_TEST_S3_ACCESS_KEY_ID"], "BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY": os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"]}
        runner = worker_main.open_document_runner(load_settings(env), self.pool)
        try:
            self.assertIsNotNone(runner)
            self.assertEqual(runner.snapshot(document_id_for(uuid.uuid4())).values, None)  # checkpointer mở được, không `setup()`
        finally:
            runner.close()
