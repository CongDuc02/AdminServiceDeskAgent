"""`tools/render-trial/render_trial.py` chạy trọn với provider GIẢ — B9a. Không mạng, không khoá thật; PostgreSQL, SeaweedFS, `soffice`, `pdfinfo` thật.

Điều được chứng minh, nói bằng hành vi: công cụ chạy đường thật `request_submit` → `Dispatcher` → `DocumentRunner` tới `PENDING_APPROVAL`; kết quả chỉ mang số, mã và cờ (không văn bản do LLM sinh, không giá trị slot);
kiểm M5 trên PDF vừa dựng cho cờ đúng; **không bao giờ vượt `MAX_CALLS` = 10 lời gọi** kể cả khi mọi lời gọi hỏng; không có `--confirm-real` thì không gọi gì (mã 3); thiếu biến môi trường thì mã 2.

Cần BO19_TEST_PG_SUPERUSER_DSN, BO19_TEST_S3_*, `soffice`, `pdfinfo` (image target `test`). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_render_trial -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import contextlib
import importlib.util
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests import pg_support
from tests.doc_support import BODY_OK, draft_output
from tests.graph_support import FakeLlm
from tests.render_support import require_tool
from tests.s3_support import ENDPOINT, REQUIRED

TOOL = Path(__file__).resolve().parents[2] / "tools" / "render-trial" / "render_trial.py"
spec = importlib.util.spec_from_file_location("render_trial", TOOL)
rt = importlib.util.module_from_spec(spec)
sys.modules["render_trial"] = rt
spec.loader.exec_module(rt)


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class RenderTrial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENDPOINT:
            if REQUIRED:
                raise AssertionError("BO19_REQUIRE_S3=1 nhưng thiếu BO19_TEST_S3_ENDPOINT")
            raise unittest.SkipTest("cần BO19_TEST_S3_ENDPOINT")
        require_tool(cls, "soffice")
        require_tool(cls, "pdfinfo")

    def s3(self) -> dict:
        return {"endpoint": os.environ["BO19_TEST_S3_ENDPOINT"], "key": os.environ["BO19_TEST_S3_ACCESS_KEY_ID"], "secret": os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"]}

    def run_tool(self, llm: FakeLlm, runs: int) -> dict:
        return rt.execute(admin_dsn=pg_support.SUPERUSER_DSN, key="khoa-gia", base_url="https://llm.example.test/openai/v1", s3=self.s3(), runs=runs, transport=llm.transport, pace=False, echo=lambda *_: None)

    def test_hai_job_that_toi_pending_approval_va_kiem_m5_dung(self):
        llm = FakeLlm().will("draft_free_content", draft_output())
        summary = self.run_tool(llm, 2)
        self.assertEqual(len(summary["runs"]), 2)
        for run in summary["runs"]:
            self.assertEqual((run["job_status"], run["job_attempts"], run["job_error_code"], run["document_status"]), ("SUCCEEDED", 1, None, "PENDING_APPROVAL"))
            self.assertEqual([(f["attempt_no"], f["outcome"], f["prompt_module_version"]) for f in run["free_content"]], [(1, "PASSED", "1.1")])
            pdf = run["pdf"]
            self.assertEqual((pdf["render_row"], pdf["db_watermark_text_ok"], pdf["pdf_subject_ok"], pdf["pdf_author_neutral"], pdf["pdfinfo_ran"]), (True, True, True, True, True))
        self.assertEqual(summary["calls_used"], 2)
        self.assertEqual(len(llm.calls("draft_free_content")), 2)
        sent = repr(llm.calls("draft_free_content")[0])
        self.assertIn("(giả)", sent)  # đầu vào mang nhãn giả

    def test_ket_qua_chi_mang_so_ma_va_co_khong_van_ban_llm(self):
        llm = FakeLlm().will("draft_free_content", draft_output())
        summary = self.run_tool(llm, 1)
        markdown = rt.render_md(summary)
        import json
        blob = markdown + json.dumps(summary, ensure_ascii=False)
        self.assertNotIn(BODY_OK, blob)
        for purpose, recipient in rt.PURPOSES:
            self.assertNotIn(purpose, blob)  # giá trị slot không vào kết quả
            self.assertNotIn(recipient, blob)
        self.assertIn("PENDING_APPROVAL", markdown)

    def test_khong_bao_gio_vuot_10_loi_goi_ke_ca_khi_moi_loi_goi_hong(self):
        llm = FakeLlm().set("draft_free_content", "không phải JSON")  # mỗi job: 1 lần gọi + 1 lần sửa parse = 2 lời gọi
        summary = self.run_tool(llm, 6)
        self.assertLessEqual(summary["calls_used"], rt.MAX_CALLS)
        self.assertLessEqual(len(llm.calls("draft_free_content")), rt.MAX_CALLS)  # số yêu cầu HTTP thật tới provider giả, kể cả sửa parse
        self.assertLess(len(summary["runs"]), 6)  # dừng trước khi hết số job
        for run in summary["runs"]:
            self.assertEqual((run["job_status"], run["job_error_code"], run["document_status"]), ("FAILED", "PARSE_FAILED", "DRAFT"))

    def test_counting_transport_chan_cung_yeu_cau_thu_muoi_mot(self):
        """Lớp chặn cuối: dù logic phía trên sai, yêu cầu HTTP thứ 11 KHÔNG được gửi đi."""
        import asyncio
        import httpx
        sent = []

        async def inner(request):
            sent.append(1)
            return httpx.Response(200, json={})
        transport = rt.CountingTransport(httpx.MockTransport(inner), limit=3)

        async def go():
            async with httpx.AsyncClient(transport=transport) as client:
                for _ in range(3):
                    await client.post("https://llm.example.test/x", json={})
                with self.assertRaises(httpx.ConnectError):
                    await client.post("https://llm.example.test/x", json={})
        asyncio.run(go())
        self.assertEqual((len(sent), transport.requests), (3, 3))
        self.assertEqual(rt.MAX_CALLS, 10)

    def test_main_khong_confirm_real_thoat_ma_3_va_khong_goi_gi(self):
        out = io.StringIO()
        with mock.patch.object(sys, "argv", ["render_trial.py"]), contextlib.redirect_stdout(out), mock.patch.object(rt, "execute", side_effect=AssertionError("không được chạy")):
            self.assertEqual(rt.main(), 3)
        self.assertIn("Chưa có --confirm-real", out.getvalue())

    def test_main_thieu_bien_thi_ma_2_chi_neu_ten(self):
        out = io.StringIO()
        env = {k: v for k, v in os.environ.items() if k not in ("BO19_LLM_API_KEY", "BO19_TRIAL_PG_ADMIN_DSN")}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(sys, "argv", ["render_trial.py", "--confirm-real"]), contextlib.redirect_stdout(out):
            self.assertEqual(rt.main(), 2)
        self.assertIn("BO19_LLM_API_KEY", out.getvalue())
        self.assertIn("BO19_TRIAL_PG_ADMIN_DSN", out.getvalue())

    def test_tham_so_sai_ma_2(self):
        for argv in (["--runs", "0"], ["--runs", "7"], ["--label", "co dau cach"]):
            out = io.StringIO()
            with mock.patch.object(sys, "argv", ["render_trial.py", *argv]), contextlib.redirect_stdout(out):
                self.assertEqual(rt.main(), 2, argv)
