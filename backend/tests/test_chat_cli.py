"""`tools/chat-cli/chat_cli.py` chạy trọn với provider giả — B7b. Không mạng, không khoá thật.

Điều được chứng minh: không `--confirm-real` thì không làm gì (mã 3); thiếu khoá hay DSN thì mã 2; **không gõ `dong y` thì thoát mã 4 trước khi tạo database hay gọi mạng**; hành trình
chat → `/slots` → `/confirm` → `/submit` đi qua đúng thao tác của `tool_layer` (có `decision_record` và job `render_document` chỉ mang id); `/confirm` đích danh, không có "tất cả";
giá trị slot (kể cả `RES`) chỉ hiện trên màn hình; **không file nào được mở để ghi, không nạp `readline`, không còn database tạm**; hạn mức lời gọi được giữ; lỗi provider chỉ hiện mã.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_chat_cli -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import builtins
import contextlib
import importlib.util
import io
import logging
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

import httpx
import psycopg

from tests import pg_support
from tests.graph_support import FakeLlm, p1, slot
from tests.tool_support import RES

TOOL = Path(__file__).resolve().parents[2] / "tools" / "chat-cli" / "chat_cli.py"
spec = importlib.util.spec_from_file_location("chat_cli", TOOL)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

KEY = "KHOA_GIA_CUA_TEST_CLI_KHONG_LOT_RA"
BASE = "https://llm.example.test/openai/v1"
RECIPIENT = "Ngân hàng GIẢ ABC"
PURPOSE = f"bổ sung hồ sơ vay vốn {RES}"
MESSAGE = f"xin giấy xác nhận công tác gửi tới {RECIPIENT}, mục đích {PURPOSE}"
HR = "full_name department_name job_title contract_type employment_start_date"


def fake() -> FakeLlm:
    llm = FakeLlm()
    llm.set("classify_intent", p1())
    llm.set("extract_slots", {"slots": [slot("recipient_org", RECIPIENT, RECIPIENT), slot("purpose", PURPOSE, PURPOSE)]})
    return llm


class KhongMang(unittest.TestCase):
    def run_main(self, argv: list[str], env: dict[str, str]) -> tuple[int, str]:
        out = io.StringIO()
        base = {k: v for k, v in os.environ.items() if k not in ("BO19_LLM_API_KEY", "BO19_TRIAL_PG_ADMIN_DSN")}
        with mock.patch.dict(os.environ, {**base, **env}, clear=True), mock.patch("sys.argv", ["chat_cli.py", *argv]), contextlib.redirect_stdout(out):
            code = cli.main()
        return code, out.getvalue()

    def test_khong_confirm_real_thi_chi_in_ke_hoach(self):
        code, text = self.run_main([], {"BO19_LLM_API_KEY": KEY})
        self.assertEqual(code, 3)
        self.assertIn("Kế hoạch", text)
        self.assertNotIn(KEY, text)

    def test_thieu_khoa_hoac_dsn_la_ma_2(self):
        self.assertEqual(self.run_main(["--confirm-real"], {})[0], 2)
        self.assertEqual(self.run_main(["--confirm-real"], {"BO19_LLM_API_KEY": KEY})[0], 2)

    def test_tran_so_loi_goi_ngoai_khoang_la_ma_2(self):
        for n in ("0", "41", "-1"):
            self.assertEqual(self.run_main(["--confirm-real", "--max-calls", n], {"BO19_LLM_API_KEY": KEY, "BO19_TRIAL_PG_ADMIN_DSN": "x"})[0], 2, n)

    def test_dong_nhac_va_chuoi_dong_y_dung_nguyen_van_theo_po(self):
        self.assertEqual(cli.NOTICE, "Mọi nội dung bạn gõ được gửi tới Groq ở nước ngoài (A-080). Chỉ gõ thông tin bịa.")
        self.assertEqual(cli.CONSENT, "dong y")
        for ok in ("dong y", "  DONG Y\n", "Dong Y"):
            self.assertTrue(cli.consented(ok), ok)
        for bad in ("", "y", "yes", "đồng ý", "dong y roi", "dongy"):
            self.assertFalse(cli.consented(bad), bad)

    def test_ma_nguon_khong_nap_readline_va_khong_mo_file_de_ghi(self):
        src = TOOL.read_text(encoding="utf-8")
        for forbidden in ("import readline", "write_text", "write_bytes", 'add_argument("--keep-db"', "keep_db="):
            self.assertNotIn(forbidden, src, forbidden)
        self.assertIsNone(re.search(r"(?<![.\w])open\(", src), "không gọi open() dựng sẵn")  # `pool.open()` là mở pool, không phải mở file


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class ChayVoiServerGia(unittest.TestCase):
    def run_cli(self, script: str, llm: FakeLlm | None = None, **kw) -> tuple[int, str, FakeLlm]:
        llm = llm or fake()
        out = io.StringIO()
        writes: list[tuple] = []
        real_open = builtins.open

        def spy(file, mode="r", *a, **k):
            if any(c in str(mode) for c in "wax+"):
                writes.append((str(file), mode))
            return real_open(file, mode, *a, **k)

        with mock.patch("builtins.open", spy):
            code = cli.execute(admin_dsn=pg_support.SUPERUSER_DSN, key=KEY, base_url=BASE, transport=llm.transport, pace=False, stdin=io.StringIO(script), out=out, **kw)
        self.writes = writes
        return code, out.getvalue(), llm

    def trial_databases(self) -> set[str]:
        with psycopg.connect(pg_support.SUPERUSER_DSN, autocommit=True) as c:
            return {r[0] for r in c.execute("select datname from pg_database where datname like 'trial_%'").fetchall()}

    def test_khong_dong_y_thi_thoat_ma_4_khong_database_khong_goi_mang(self):
        before = self.trial_databases()
        for answer in ("\n", "khong\n", "yes\n", ""):
            code, text, llm = self.run_cli(answer + MESSAGE + "\n")
            self.assertEqual(code, 4, answer)
            self.assertEqual(llm.requests, [])
            self.assertNotIn("agent>", text)
            self.assertIn(cli.NOTICE, text)
            self.assertEqual(self.trial_databases(), before)

    def test_hanh_trinh_chat_slots_confirm_submit(self):
        before = self.trial_databases()
        script = f"dong y\n{MESSAGE}\n/slots\n/confirm {HR}\n/slots\n/submit\n/quit\n"
        code, text, llm = self.run_cli(script)
        self.assertEqual(code, 0, text)
        self.assertIn(cli.NOTICE, text)
        self.assertIn("agent> ", text)
        self.assertEqual(len(llm.requests), 2)  # P1 + P2
        self.assertIn(RES, text)  # `/slots` hiện giá trị, kể cả RES — chỉ trên màn hình (PO, Q2)
        self.assertIn("chưa xác nhận: ", text)  # `/slots` đầu tiên: năm giá trị hồ sơ mới ở PROPOSED
        self.assertIn("Đã xác nhận: " + ", ".join(HR.split()), text)  # `/confirm` đích danh, đúng thứ tự gõ
        self.assertIn("sẵn sàng gửi: có", text)
        self.assertIn("Đã gửi — decision_record", text)
        self.assertIn("render_document", text)
        self.assertNotIn(KEY, text)
        self.assertEqual(self.trial_databases(), before)  # database tạm đã bị xoá

    def test_submit_khi_chua_xac_nhan_la_request_not_ready(self):
        code, text, _ = self.run_cli(f"dong y\n{MESSAGE}\n/submit\n/quit\n")
        self.assertEqual(code, 0)
        self.assertIn("REQUEST_NOT_READY", text)
        self.assertNotIn("Đã gửi", text)

    def test_confirm_khong_co_tat_ca_va_slot_khong_cho_xac_nhan(self):
        code, text, _ = self.run_cli(f"dong y\n{MESSAGE}\n/confirm\n/confirm all\n/confirm purpose\n/slots\n/quit\n")
        self.assertEqual(code, 0)
        self.assertIn("không có xác nhận tất cả", text)
        self.assertEqual(text.count("Không xác nhận được (NOT_PROPOSED"), 2, text[-900:])  # `all` không phải slot; `purpose` đã PROVIDED
        self.assertNotIn("Đã xác nhận:", text)

    def test_chua_co_yeu_cau_va_lenh_la(self):
        code, text, llm = self.run_cli("dong y\n/slots\n/confirm full_name\n/submit\n/xyz\n\n/new\n/quit\n")
        self.assertEqual(code, 0)
        self.assertEqual(text.count("Chưa có yêu cầu nào trong phiên này."), 3)
        self.assertIn("Đã mở phiên mới", text)
        self.assertEqual(llm.requests, [])

    def test_khong_ghi_file_va_khong_nap_readline(self):
        self.run_cli(f"dong y\n{MESSAGE}\n/slots\n/quit\n")
        self.assertEqual(self.writes, [], "CLI không được mở file nào để ghi")
        # Chỉ kiểm CLI không tự nạp: module `readline` không phải của tiến trình test chạy dưới `unittest`.
        self.assertNotIn("import readline", TOOL.read_text(encoding="utf-8"))

    def test_han_muc_loi_goi_duoc_giu(self):
        script = f"dong y\n{MESSAGE}\n{MESSAGE}\n{MESSAGE}\n/quit\n"
        code, text, llm = self.run_cli(script, max_calls=5)
        self.assertEqual(code, 0)
        self.assertEqual(len(llm.requests), 2)  # lượt đầu: 0 + 4 ≤ 5; lượt hai: 2 + 4 > 5
        self.assertEqual(text.count("Hết hạn mức 5 lời gọi"), 2)

    def test_loi_provider_chi_hien_ma(self):
        llm = FakeLlm()
        llm.set("classify_intent", *[httpx.Response(503, json={"error": {"message": f"chi tiết lỗi {KEY}", "type": "server_error"}}) for _ in range(3)])
        code, text, _ = self.run_cli(f"dong y\n{MESSAGE}\n/quit\n", llm)
        self.assertEqual(code, 0)
        self.assertIn("LỖI PROVIDER PROVIDER_CALL_FAILED/HTTP_STATUS http=503", text)
        self.assertIn("lỗi provider: 1 (PROVIDER_CALL_FAILED/HTTP_STATUS)", text)
        self.assertNotIn("chi tiết lỗi", text)
        self.assertNotIn(KEY, text)

    def test_tra_lai_handler_log_cua_tien_trinh_goi(self):
        root, sentinel = logging.getLogger(), logging.NullHandler()
        root.addHandler(sentinel)
        self.addCleanup(root.removeHandler, sentinel)
        before = list(root.handlers)
        self.run_cli(f"dong y\n{MESSAGE}\n/quit\n")
        self.assertEqual(root.handlers, before)

    def test_eof_giua_chung_van_don_dep(self):
        before = self.trial_databases()
        code, text, _ = self.run_cli(f"dong y\n{MESSAGE}\n")  # không /quit
        self.assertEqual(code, 0)
        self.assertIn("Tổng:", text)
        self.assertEqual(self.trial_databases(), before)


if __name__ == "__main__":
    unittest.main()
