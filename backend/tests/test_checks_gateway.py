"""Bước kiểm khởi động #5 (trần budget) và #21 (hồ sơ model, base URL) — B4; hồ sơ model `model_profiles.json` (ADR-035, điều kiện 1).

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_checks_gateway -v
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bo19.ai_gateway.routing import profiles
from bo19.config import working_values as wv
from bo19.config.settings import DEFAULT_LLM_BASE_URL, load_settings
from bo19.startup.checks_gateway import CEILED_CALLS, step_05, step_21
from bo19.startup.model import Context, Entry

BASE = {"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": "x", "BO19_SESSION_SECRET": "y" * 32}
KEY = "KHOA_API_KHONG_DUOC_LOT_RA_O_DAU_CA"


def ctx(**env) -> Context:
    return Context(Entry.API, load_settings({**BASE, **env}), {}, None, Path("."))


GOOD = json.loads(profiles.DEFAULT_PATH.read_text(encoding="utf-8"))


def mutated(fn) -> dict:
    raw = copy.deepcopy(GOOD)
    fn(raw)
    return raw


class Buoc5(unittest.TestCase):
    def test_gia_tri_hien_tai_dat_va_phu_du_cac_loi_goi(self):
        self.assertEqual(step_05(ctx()).codes, ())
        self.assertEqual(set(CEILED_CALLS), set(wv.TOKEN_CEILING_PER_CALL))

    def test_gia_tri_theo_bang_11_ops(self):  # mục Định cỡ A-022 của 11-ops.md
        self.assertEqual(wv.TOKEN_CEILING_PER_CALL, {"classify_intent": 1500, "extract_slots": 3500, "select_procedure_passages": 6000,
                                                      "embed_query": 500, "draft_free_content": 4000, "revise_free_content": 4000})
        self.assertEqual((wv.TOKEN_CEILING_CHAT_SESSION, wv.TOKEN_CEILING_REQUEST, wv.CHANGES_REQUESTED_MAX_ROUNDS), (46_500, 92_000, 3))

    def test_thieu_tran_nao_cung_chan_voi_ma_rieng(self):  # ADR-019 ca 2: thiếu không bao giờ là "không có trần"
        for call in CEILED_CALLS:
            ceilings = {k: v for k, v in wv.TOKEN_CEILING_PER_CALL.items() if k != call}
            with mock.patch.object(wv, "TOKEN_CEILING_PER_CALL", ceilings):
                self.assertEqual(step_05(ctx()).codes, (f"STARTUP_05_CEILING_MISSING:{call}",))

    def test_gia_tri_khong_hop_le_cung_la_vang_mat(self):
        for bad in (None, 0, -1, "1500", 1500.5, True):
            with mock.patch.object(wv, "TOKEN_CEILING_PER_CALL", {**wv.TOKEN_CEILING_PER_CALL, "extract_slots": bad}):
                self.assertEqual(step_05(ctx()).codes, ("STARTUP_05_CEILING_MISSING:extract_slots",), repr(bad))

    def test_tran_chu_budget_va_vong_sua(self):
        for attr, name in (("TOKEN_CEILING_CHAT_SESSION", "chat_session"), ("TOKEN_CEILING_REQUEST", "request"), ("CHANGES_REQUESTED_MAX_ROUNDS", "changes_requested_rounds")):
            with mock.patch.object(wv, attr, None):
                self.assertEqual(step_05(ctx()).codes, (f"STARTUP_05_CEILING_MISSING:{name}",))

    def test_chay_het_roi_gom_nhieu_ma(self):
        with mock.patch.object(wv, "TOKEN_CEILING_PER_CALL", {}), mock.patch.object(wv, "TOKEN_CEILING_REQUEST", 0):
            self.assertEqual(len(step_05(ctx()).codes), len(CEILED_CALLS) + 1)


class HoSoModel(unittest.TestCase):
    def test_file_trong_repo_hop_le_va_dung_cau_hinh_da_duyet(self):
        check = profiles.load_profiles()
        self.assertEqual(check.codes, ())
        cheap, strong = check.profiles.for_tier("CHEAP"), check.profiles.for_tier("STRONG")
        self.assertEqual((cheap.model, cheap.params), ("openai/gpt-oss-20b", {"reasoning_effort": "low"}))  # chỉ đạo của PO — ADR-035
        self.assertEqual((strong.model, strong.params), ("openai/gpt-oss-120b", {}))  # A-090: chưa chốt reasoning_effort, temperature

    def test_file_khong_chua_bi_mat(self):
        text = profiles.DEFAULT_PATH.read_text(encoding="utf-8").lower()
        for word in ("key", "secret", "token", "password", "http"):
            self.assertNotIn(word, text)

    def test_thieu_tier(self):
        raw = mutated(lambda r: r["tiers"].pop("STRONG"))
        self.assertEqual(profiles.validate(raw).codes, ("PROFILE_TIER_MISSING:STRONG",))

    def test_tier_la(self):
        raw = mutated(lambda r: r["tiers"].update({"EMBEDDING": {"model": "openai/gpt-oss-20b", "params": {}}}))
        self.assertEqual(profiles.validate(raw).codes, ("PROFILE_TIER_UNKNOWN:EMBEDDING",))

    def test_thieu_ma_model_hoac_params(self):
        self.assertEqual(profiles.validate(mutated(lambda r: r["tiers"]["CHEAP"].pop("model"))).codes, ("PROFILE_TIER_MODEL_MISSING:CHEAP",))
        self.assertEqual(profiles.validate(mutated(lambda r: r["tiers"]["CHEAP"].pop("params"))).codes, ("PROFILE_TIER_PARAMS_INVALID:CHEAP",))
        self.assertEqual(profiles.validate(mutated(lambda r: r["tiers"]["CHEAP"].update({"model": "  "}))).codes, ("PROFILE_TIER_MODEL_MISSING:CHEAP",))

    def test_model_khong_co_trong_danh_sach(self):
        raw = mutated(lambda r: r["tiers"]["CHEAP"].update({"model": "openai/gpt-4o-mini"}))
        self.assertEqual(profiles.validate(raw).codes, ("PROFILE_MODEL_UNKNOWN:CHEAP",))

    def test_tham_so_khong_thuoc_model_do_bi_tu_choi(self):  # "không có tham số nào ngoài danh sách được phép của chính mã model đó"
        raw = mutated(lambda r: r["tiers"]["STRONG"]["params"].update({"temperature": 0.2}))
        self.assertEqual(profiles.validate(raw).codes, ("PROFILE_PARAM_NOT_ALLOWED:STRONG:temperature",))
        # đổi sang model mà `reasoning_effort` không hợp lệ (ví dụ gpt-4o-mini của đường đảo ngược): tham số phải bỏ cùng lúc
        def swap(r):
            r["models"]["openai/gpt-4o-mini"] = {"allowed_params": {}}
            r["tiers"]["CHEAP"]["model"] = "openai/gpt-4o-mini"
        self.assertEqual(profiles.validate(mutated(swap)).codes, ("PROFILE_PARAM_NOT_ALLOWED:CHEAP:reasoning_effort",))

    def test_gia_tri_ngoai_mien_bi_tu_choi_va_khong_lo_gia_tri(self):
        for value in ("extreme", "LOW", "", None, 1, True, ["low"]):
            raw = mutated(lambda r, v=value: r["tiers"]["CHEAP"]["params"].update({"reasoning_effort": v}))
            codes = profiles.validate(raw).codes
            self.assertEqual(codes, ("PROFILE_PARAM_VALUE_INVALID:CHEAP:reasoning_effort",), repr(value))
        raw = mutated(lambda r: r["tiers"]["CHEAP"]["params"].update({"reasoning_effort": "BI_MAT_GIA_TRI"}))
        self.assertNotIn("BI_MAT_GIA_TRI", " ".join(profiles.validate(raw).codes))

    def test_bool_khong_duoc_coi_la_so(self):
        def fn(r):
            r["models"]["openai/gpt-oss-20b"]["allowed_params"]["flag"] = [1]
            r["tiers"]["CHEAP"]["params"]["flag"] = True
        self.assertEqual(profiles.validate(mutated(fn)).codes, ("PROFILE_PARAM_VALUE_INVALID:CHEAP:flag",))

    def test_tham_so_do_gateway_tu_dat_khong_khai_duoc(self):
        for name in ("stream", "response_format", "n", "logprobs", "logit_bias", "top_logprobs", "model", "messages", "name"):
            raw = mutated(lambda r, n=name: r["models"]["openai/gpt-oss-20b"]["allowed_params"].update({n: ["x"]}))
            self.assertIn(f"PROFILE_PARAM_RESERVED:openai/gpt-oss-20b:{name}", profiles.validate(raw).codes, name)

    def test_mien_gia_tri_hong(self):
        for domain in ([], "low", None, [[1]], [{"a": 1}]):
            raw = mutated(lambda r, d=domain: r["models"]["openai/gpt-oss-20b"]["allowed_params"].update({"reasoning_effort": d}))
            self.assertIn("PROFILE_PARAM_DOMAIN_INVALID:openai/gpt-oss-20b:reasoning_effort", profiles.validate(raw).codes, repr(domain))

    def test_schema_version_va_hinh_dang_goc(self):
        self.assertEqual(profiles.validate(mutated(lambda r: r.update({"schema_version": 2}))).codes, ("PROFILE_SCHEMA_VERSION_INVALID",))
        self.assertEqual(profiles.validate([]).codes, ("PROFILE_SCHEMA_VERSION_INVALID",))
        self.assertEqual(profiles.validate(mutated(lambda r: r.update({"models": []}))).codes, ("PROFILE_SCHEMA_INVALID",))

    def test_file_khong_doc_duoc_hoac_khong_phai_json(self):
        self.assertEqual(profiles.load_profiles(Path("/khong/co/file.json")).codes, ("PROFILE_FILE_UNREADABLE",))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            p.write_text("{khong phai json", encoding="utf-8")
            self.assertEqual(profiles.load_profiles(p).codes, ("PROFILE_FILE_UNREADABLE",))

    def test_ten_la_trong_file_khong_dua_noi_dung_tuy_y_vao_ma(self):
        raw = mutated(lambda r: r["tiers"]["CHEAP"]["params"].update({"khoa bi mat\nvà dòng mới": 1}))
        code = profiles.validate(raw).codes[0]
        self.assertNotIn("\n", code)
        self.assertLessEqual(len(code), 200)


class Buoc21(unittest.TestCase):
    def test_mac_dinh_dat(self):
        self.assertEqual(step_21(ctx()).codes, ())
        self.assertEqual(load_settings(BASE).llm_base_url, DEFAULT_LLM_BASE_URL)

    def test_base_url_phai_la_https(self):
        for bad in ("http://api.groq.com/openai/v1", "ftp://x", "https://", "https:// x", "api.groq.com", "javascript:alert(1)"):
            c = step_21(ctx(BO19_LLM_BASE_URL=bad)).codes
            self.assertEqual(c, ("STARTUP_21_LLM_BASE_URL_INVALID",), bad)
            self.assertNotIn(bad, " ".join(c))

    def test_base_url_khac_hop_le_la_duoc(self):  # đường đảo ngược sang OpenRouter chỉ đổi biến (ADR-035 tiêu chí 1)
        for good in ("https://openrouter.ai/api/v1", "https://llm.example.com:8443/v1/"):
            self.assertEqual(step_21(ctx(BO19_LLM_BASE_URL=good)).codes, (), good)

    def test_gop_ma_cua_ca_hai_nguon(self):
        with mock.patch("bo19.startup.checks_gateway.load_profiles", return_value=profiles.ProfileCheck(None, ("PROFILE_TIER_MISSING:STRONG",))):
            self.assertEqual(step_21(ctx(BO19_LLM_BASE_URL="http://x")).codes, ("STARTUP_21_LLM_BASE_URL_INVALID", "STARTUP_21_PROFILE_TIER_MISSING:STRONG"))


class KhoaApi(unittest.TestCase):
    def test_khoa_la_tuy_chon_o_b4(self):
        s = load_settings(BASE)
        self.assertIsNone(s.llm_api_key)
        self.assertEqual(s.problems, ())  # thiếu khoá không phải lỗi cấu hình lúc khởi động

    def test_khoa_khong_vao_repr_hay_str_cua_settings(self):
        s = load_settings({**BASE, "BO19_LLM_API_KEY": KEY})
        self.assertEqual(s.llm_api_key, KEY)
        for text in (repr(s), str(s), f"{s}", f"{s!r}"):
            self.assertNotIn(KEY, text)
        self.assertNotIn(KEY, repr(s.__dict__.keys()))
        self.assertIn("llm_api_key=<ẩn>", repr(s))

    def test_khoa_rong_hoac_khoang_trang_la_khong_dat(self):
        for v in ("", "   "):
            self.assertIsNone(load_settings({**BASE, "BO19_LLM_API_KEY": v}).llm_api_key)

    def test_khoa_khong_vao_ma_loi_khi_base_url_sai(self):
        s = load_settings({**BASE, "BO19_LLM_API_KEY": KEY, "BO19_LLM_BASE_URL": "http://x"})
        self.assertNotIn(KEY, repr(s.problems))


if __name__ == "__main__":
    unittest.main()
