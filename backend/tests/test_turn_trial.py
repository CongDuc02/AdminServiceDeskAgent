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
import os
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

import psycopg

from tests import pg_support
from tests.graph_support import FakeLlm, p1, slot

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

    def trial_databases(self) -> set[str]:
        with psycopg.connect(pg_support.SUPERUSER_DSN, autocommit=True) as c:
            return {r[0] for r in c.execute("select datname from pg_database where datname like 'trial_%'").fetchall()}


if __name__ == "__main__":
    unittest.main()
