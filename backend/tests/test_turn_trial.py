"""`tools/turn-trial/turn_trial.py` chạy trọn với provider giả — B6b. Không mạng, không khoá thật.

Điều được chứng minh: không `--confirm-real` thì không làm gì (mã 3); thiếu khoá hay DSN thì mã 2; chạy đủ kịch bản trên database tạm rồi xoá nó; kết quả CHỈ có số và mã —
không văn bản tin nhắn, không văn bản trả lời; hai tỷ lệ `QUOTE_NOT_IN_MESSAGE` và `VALUE_NOT_IN_QUOTE` được tính và báo riêng; hạn mức số lời gọi được giữ.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_turn_trial -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import contextlib
import importlib.util
import io
import json
import logging
import os
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

import httpx
import psycopg

from tests import pg_support
from tests.graph_support import FakeLlm, p1, slot

tt_p1 = p1

TOOL = Path(__file__).resolve().parents[2] / "tools" / "turn-trial" / "turn_trial.py"
spec = importlib.util.spec_from_file_location("turn_trial", TOOL)
tt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tt)

KEY = "KHOA_GIA_CUA_TEST_KHONG_LOT_RA"


def fake() -> FakeLlm:
    llm = FakeLlm()
    llm.set("classify_intent", p1())
    llm.set("extract_slots", {"slots": [slot("recipient_org", "Ngân hàng GIẢ", "ngân hàng giả"), slot("purpose", "bịa đặt hoàn toàn khác", "hồ sơ vay vốn")]})
    return llm


class KhongMang(unittest.TestCase):
    def run_main(self, argv: list[str], env: dict[str, str]) -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=False), mock.patch("sys.argv", ["turn_trial.py", *argv]), contextlib.redirect_stdout(out):
            code = tt.main()
        return code, out.getvalue()

    def test_khong_confirm_real_thi_chi_in_ke_hoach(self):
        code, text = self.run_main([], {"BO19_LLM_API_KEY": KEY})
        self.assertEqual(code, 3)
        self.assertIn("Kế hoạch: 11 lượt", text)
        self.assertNotIn(KEY, text)

    def test_nhan_hong_la_ma_2_va_khong_lam_gi(self):
        for label in ("../b6b", "a/b", "b7 x", ""):
            with self.subTest(label=label):
                code, text = self.run_main(["--confirm-real", "--label", label], {"BO19_LLM_API_KEY": KEY})
                self.assertEqual(code, 2)
                self.assertNotIn("Kế hoạch", text)

    def test_nhan_mac_dinh_khong_ghi_de_ket_qua_b6b(self):
        self.assertEqual(tt.RUN_LABEL, "b7")

    def test_thieu_khoa_hoac_dsn_la_ma_2(self):
        env = {k: v for k, v in os.environ.items() if k not in ("BO19_LLM_API_KEY", "BO19_TRIAL_PG_ADMIN_DSN")}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(self.run_main(["--confirm-real"], {})[0], 2)
            self.assertEqual(self.run_main(["--confirm-real"], {"BO19_LLM_API_KEY": KEY})[0], 2)


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class ChayVoiServerGia(unittest.TestCase):
    def execute(self, only: str = "", **kw):
        chosen = [s for s in tt.SCENARIOS if not only or s[0] in only.split(",")]
        llm = fake()
        lines: list[str] = []
        summary, turns, profile = tt.execute(chosen, admin_dsn=pg_support.SUPERUSER_DSN, key=KEY, base_url="https://llm.example.test/openai/v1", transport=llm.transport, pace=False,
                                             echo=lines.append, **kw)
        return summary, turns, profile, lines, llm

    def test_chay_du_kich_ban_tinh_hai_ty_le_rieng_va_xoa_database_tam(self):
        before = self.trial_databases()
        summary, turns, profile, lines, llm = self.execute("S1,S2")
        self.assertEqual([t["scenario"] for t in turns], ["S1", "S2"])
        self.assertEqual(summary["slots_produced"], 4)  # mỗi lượt P2 trả 2 slot
        # S1: `recipient_org` quote không có trong tin (QUOTE), `purpose` quote có nhưng value bịa dài hơn quote (VALUE); S2: cả hai quote không có trong tin (QUOTE, QUOTE)
        self.assertEqual((summary["quote_not_in_message"], summary["value_not_in_quote"]), (3, 1))
        self.assertEqual((summary["rate_quote_not_in_message"], summary["rate_value_not_in_quote"]), (0.75, 0.25))  # hai tỷ lệ báo riêng
        self.assertEqual((summary["p2_turns"], summary["p2_turns_with_evidence_mismatch"]), (2, 2))
        self.assertEqual(self.trial_databases(), before)  # database tạm đã bị xoá
        self.assertEqual(set(profile), {"classify_intent", "extract_slots"})
        self.assertEqual(summary["calls"], 4)  # hai lượt × (P1 + P2)

    def test_ket_qua_chi_co_so_va_ma_khong_co_van_ban(self):
        summary, turns, profile, lines, _ = self.execute("S1,S2")
        md = tt.render(summary, turns, profile)
        blob = md + json.dumps(turns, ensure_ascii=False) + "\n".join(lines)
        for _, _, text in tt.SCENARIOS:
            self.assertNotIn(text, blob)
        for fragment in ("Ngân hàng GIẢ", "bịa đặt hoàn toàn khác", "Để làm", "mình cần thêm", KEY):
            self.assertNotIn(fragment, blob)
        self.assertIn("QUOTE_NOT_IN_MESSAGE", md)
        self.assertIn("VALUE_NOT_IN_QUOTE", md)

    def test_moi_tin_nhan_thu_mang_nhan_gia(self):
        self.assertTrue(all("(giả)" in unicodedata.normalize("NFC", text) for _, _, text in tt.SCENARIOS))

    def test_han_muc_so_loi_goi_duoc_giu(self):
        summary, turns, *_ = self.execute("S1,S2,S2b,S3,S4,S5,S5b", prior_calls=tt.MAX_CALLS - 5)
        self.assertLessEqual(summary["calls"], 5)  # còn 5 lời gọi trừ 4 chừa chỗ cho sửa parse: chỉ chạy được một lượt
        self.assertLess(len(turns), 7)

    def test_ghi_ten_slot_bi_loai(self):
        summary, turns, *_ = self.execute("S1")
        self.assertEqual(sorted(turns[0]["rejected_slots"]), ["purpose", "recipient_org"])  # tên cấu hình, không phải giá trị
        self.assertIn("recipient_org", tt.render(summary, turns, {}))

    def execute_with(self, llm, only: str, **kw):
        chosen = [s for s in tt.SCENARIOS if s[0] in only.split(",")]
        return tt.execute(chosen, admin_dsn=pg_support.SUPERUSER_DSN, key=KEY, base_url="https://llm.example.test/openai/v1", transport=llm.transport, pace=False, echo=lambda _: None, **kw)

    def test_loi_503_ghi_truong_loi_provider_chi_ma_va_so(self):  # O1-17
        llm = FakeLlm()
        llm.set("classify_intent", *[httpx.Response(503, json={"error": {"message": f"chi tiết lỗi {KEY}", "type": "server_error"}}) for _ in range(3)])
        summary, turns, _ = self.execute_with(llm, "S7")
        self.assertEqual(turns[0]["error_code"], "PROVIDER_CALL_FAILED")
        self.assertEqual(turns[0]["provider_errors"], [{"call_name": "classify_intent", "kind": "HTTP_STATUS", "subcode": "PROVIDER_CALL_FAILED", "http_status": 503,
                                                        "attempts": 2, "retry_after_seconds": None}])  # WV-05: một lần thử lại
        self.assertEqual((summary["provider_errors"], summary["provider_errors_by_kind"]), (1, {"PROVIDER_CALL_FAILED:HTTP_STATUS": 1}))
        md = tt.render(summary, turns, {})
        self.assertIn("PROVIDER_CALL_FAILED/HTTP_STATUS http=503 lần thử=2", md)
        self.assertNotIn("chi tiết lỗi", md + json.dumps(turns, ensure_ascii=False))
        self.assertNotIn(KEY, md + json.dumps(turns, ensure_ascii=False))

    def test_treo_toi_han_chot_ghi_deadline(self):  # O1-17: kiểu sự cố của S7 ở B6b
        llm = FakeLlm()
        llm.set("classify_intent", tt_p1())
        llm.delays["classify_intent"] = 5
        summary, turns, _ = self.execute_with(llm, "S7", turn_deadline_s=1.5)
        errors = turns[0]["provider_errors"]
        self.assertEqual(len(errors), 1)
        self.assertEqual((errors[0]["call_name"], errors[0]["kind"], errors[0]["subcode"], errors[0]["http_status"]), ("classify_intent", "DEADLINE", "PROVIDER_CALL_FAILED", None))
        self.assertEqual(set(errors[0]), set(tt.PROVIDER_ERROR_FIELDS))

    def test_lan_chay_khong_loi_thi_khong_co_loi_provider_va_tra_lai_handler_log(self):
        root, sentinel = logging.getLogger(), logging.NullHandler()  # handler của tiến trình gọi — phải còn sau khi đo
        root.addHandler(sentinel)
        self.addCleanup(root.removeHandler, sentinel)
        before = list(root.handlers)
        summary, turns, *_ = self.execute("S6")
        self.assertIn(sentinel, root.handlers)
        self.assertEqual((turns[0]["provider_errors"], summary["provider_errors"], summary["provider_errors_by_kind"]), ([], 0, {}))
        self.assertEqual(logging.getLogger().handlers, before)

    def test_bo_loc_log_chi_giu_dung_cac_truong(self):
        log = tt.ProviderErrorLog()
        log.write(json.dumps({"message": "LLM_PROVIDER_ERROR", "call_name": "extract_slots", "kind": "CONNECTION", "subcode": "PROVIDER_CALL_FAILED", "http_status": None,
                              "attempts": 1, "retry_after_seconds": None, "provider_error_type": "x", "trace_id": "t", "unmetered_attempts": 1}) + "\n")
        log.write(json.dumps({"message": "LLM_ATTEMPT_MEASURED", "call_name": "extract_slots"}) + "\nkhông phải json\n")
        self.assertEqual(log.drain(), [{"call_name": "extract_slots", "kind": "CONNECTION", "subcode": "PROVIDER_CALL_FAILED", "http_status": None, "attempts": 1,
                                        "retry_after_seconds": None}])
        self.assertEqual(log.drain(), [])

    def trial_databases(self) -> set[str]:
        with psycopg.connect(pg_support.SUPERUSER_DSN, autocommit=True) as c:
            return {r[0] for r in c.execute("select datname from pg_database where datname like 'trial_%'").fetchall()}


if __name__ == "__main__":
    unittest.main()
