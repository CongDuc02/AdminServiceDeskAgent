"""Bước kiểm khởi động #5 (trần budget) và #21 (hồ sơ model, base URL) — B4; hồ sơ model `model_profiles.json` (ADR-035, điều kiện 1).

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_checks_gateway -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

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
    def test_file_trong_repo_hop_le_va_dung_gia_tri_khoi_dau_da_duyet(self):  # PO duyệt 2026-10-05, nhãn "chưa hiệu chỉnh"
        check = profiles.load_profiles()
        self.assertEqual(check.codes, ())
        cheap, strong = check.profiles.for_tier("CHEAP"), check.profiles.for_tier("STRONG")
        self.assertEqual((cheap.model, cheap.params), ("openai/gpt-oss-20b", {"reasoning_effort": "low", "temperature": 0.2}))
        self.assertEqual((strong.model, strong.params), ("openai/gpt-oss-120b", {"reasoning_effort": "medium", "temperature": 0.3}))
        self.assertEqual(check.profiles.modules, {"classify_intent": {"max_completion_tokens": 512}, "extract_slots": {"max_completion_tokens": 1536},
                                                   "draft_free_content": {"max_completion_tokens": 2048}})

    def test_ca_hai_tier_ghi_tuong_minh_moi_tham_so_anh_huong_output(self):  # không dựa mặc định provider
        for tier in ("CHEAP", "STRONG"):
            self.assertTrue(set(profiles.REQUIRED_TIER_PARAMS) <= set(profiles.load_profiles().profiles.for_tier(tier).params), tier)

    def test_profile_hieu_luc_cua_loi_goi_la_tier_cong_tran_output_cua_module(self):
        p = profiles.load_profiles().profiles
        self.assertEqual(p.profile_for("classify_intent", "CHEAP").params, {"reasoning_effort": "low", "temperature": 0.2, "max_completion_tokens": 512})
        self.assertEqual(p.profile_for("draft_free_content", "STRONG").params, {"reasoning_effort": "medium", "temperature": 0.3, "max_completion_tokens": 2048})
        self.assertEqual(p.for_tier("CHEAP").params, {"reasoning_effort": "low", "temperature": 0.2})  # tier không bị sửa tại chỗ

    def test_module_co_prompt_module_deu_co_tran_output_va_khop_tier(self):
        from bo19.ai_gateway.prompt_modules import MODULES
        self.assertEqual(profiles.MODULE_TIERS, {name: m.tier for name, m in MODULES.items()})

    def test_file_khong_chua_bi_mat(self):
        text = profiles.DEFAULT_PATH.read_text(encoding="utf-8").lower()
        for word in ("key", "secret", "token\"", "password", "http"):
            self.assertNotIn(word, text)

    def test_max_tokens_deprecated_khong_bao_gio_khai_duoc(self):
        raw = mutated(lambda r: r["models"]["openai/gpt-oss-20b"]["allowed_params"].update({"max_tokens": {"type": "integer", "min": 1}}))
        self.assertIn("PROFILE_PARAM_RESERVED:openai/gpt-oss-20b:max_tokens", profiles.validate(raw).codes)

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

    def test_thieu_tham_so_tuong_minh_cua_tier_la_loi(self):
        for name in profiles.REQUIRED_TIER_PARAMS:
            for tier in ("CHEAP", "STRONG"):
                raw = mutated(lambda r, n=name, t=tier: r["tiers"][t]["params"].pop(n))
                self.assertEqual(profiles.validate(raw).codes, (f"PROFILE_TIER_PARAM_MISSING:{tier}:{name}",), (tier, name))

    def test_model_khong_co_trong_danh_sach(self):
        raw = mutated(lambda r: r["tiers"]["CHEAP"].update({"model": "openai/gpt-4o-mini"}))
        self.assertEqual(profiles.validate(raw).codes, ("PROFILE_MODEL_UNKNOWN:CHEAP",))

    def test_tham_so_khong_thuoc_model_do_bi_tu_choi(self):
        raw = mutated(lambda r: r["tiers"]["STRONG"]["params"].update({"top_p": 0.5}))
        self.assertEqual(profiles.validate(raw).codes, ("PROFILE_PARAM_NOT_ALLOWED:STRONG:top_p",))

    def test_gia_tri_ngoai_mien_bi_tu_choi_va_khong_lo_gia_tri(self):
        for value in ("extreme", "LOW", "", None, 1, True, ["low"]):
            raw = mutated(lambda r, v=value: r["tiers"]["CHEAP"]["params"].update({"reasoning_effort": v}))
            self.assertEqual(profiles.validate(raw).codes, ("PROFILE_PARAM_VALUE_INVALID:CHEAP:reasoning_effort",), repr(value))
        raw = mutated(lambda r: r["tiers"]["CHEAP"]["params"].update({"reasoning_effort": "BI_MAT_GIA_TRI"}))
        self.assertNotIn("BI_MAT_GIA_TRI", " ".join(profiles.validate(raw).codes))

    def test_temperature_theo_mien_0_den_2(self):  # llm-groq-chat-params.md mục 2
        for good in (0, 0.0, 0.2, 1, 2, 2.0):
            self.assertEqual(profiles.validate(mutated(lambda r, g=good: r["tiers"]["CHEAP"]["params"].update({"temperature": g}))).codes, (), good)
        for bad in (-0.1, 2.01, "0.2", None, True, [0.2]):
            raw = mutated(lambda r, b=bad: r["tiers"]["CHEAP"]["params"].update({"temperature": b}))
            self.assertEqual(profiles.validate(raw).codes, ("PROFILE_PARAM_VALUE_INVALID:CHEAP:temperature",), repr(bad))

    def test_tran_output_cua_module_bat_buoc_va_la_so_nguyen_duong(self):
        for call in profiles.MODULE_TIERS:
            raw = mutated(lambda r, c=call: r["module_params"].pop(c))
            self.assertEqual(profiles.validate(raw).codes, (f"PROFILE_MODULE_MISSING:{call}",), call)
            raw = mutated(lambda r, c=call: r["module_params"][c].pop("max_completion_tokens"))
            self.assertEqual(profiles.validate(raw).codes, (f"PROFILE_MODULE_PARAM_MISSING:{call}:max_completion_tokens",), call)
            for bad in (0, -5, 1.5, "512", None, True):
                raw = mutated(lambda r, c=call, b=bad: r["module_params"][c].update({"max_completion_tokens": b}))
                self.assertEqual(profiles.validate(raw).codes, (f"PROFILE_MODULE_PARAM_VALUE_INVALID:{call}:max_completion_tokens",), (call, bad))

    def test_module_la_hoac_tham_so_trung_tier(self):
        self.assertEqual(profiles.validate(mutated(lambda r: r["module_params"].update({"module_la": {"max_completion_tokens": 5}}))).codes, ("PROFILE_MODULE_UNKNOWN:module_la",))
        raw = mutated(lambda r: r["module_params"]["classify_intent"].update({"temperature": 0.5}))
        self.assertEqual(profiles.validate(raw).codes, ("PROFILE_PARAM_CONFLICT:classify_intent:temperature",))
        raw = mutated(lambda r: r["module_params"]["classify_intent"].update({"top_p": 0.5}))
        self.assertEqual(profiles.validate(raw).codes, ("PROFILE_MODULE_PARAM_NOT_ALLOWED:classify_intent:top_p",))

    def test_bool_khong_duoc_coi_la_so(self):
        def fn(r):
            r["models"]["openai/gpt-oss-20b"]["allowed_params"]["flag"] = {"values": [1]}
            r["tiers"]["CHEAP"]["params"]["flag"] = True
        self.assertEqual(profiles.validate(mutated(fn)).codes, ("PROFILE_PARAM_VALUE_INVALID:CHEAP:flag",))

    def test_tham_so_do_gateway_tu_dat_khong_khai_duoc(self):
        for name in ("stream", "response_format", "n", "logprobs", "logit_bias", "top_logprobs", "model", "messages", "name", "max_tokens"):
            raw = mutated(lambda r, n=name: r["models"]["openai/gpt-oss-20b"]["allowed_params"].update({n: {"values": ["x"]}}))
            self.assertIn(f"PROFILE_PARAM_RESERVED:openai/gpt-oss-20b:{name}", profiles.validate(raw).codes, name)

    def test_mien_gia_tri_hong(self):
        bad = ([], "low", None, {"values": []}, {"values": "low"}, {"values": [[1]]}, {"type": "integer"}, {"type": "text", "min": 0}, {"type": "integer", "min": 1.5},
               {"type": "integer", "min": 5, "max": 2}, {"type": "number", "min": 0, "extra": 1}, {"values": ["a"], "min": 1})
        for domain in bad:
            raw = mutated(lambda r, d=domain: r["models"]["openai/gpt-oss-20b"]["allowed_params"].update({"reasoning_effort": d}))
            self.assertIn("PROFILE_PARAM_DOMAIN_INVALID:openai/gpt-oss-20b:reasoning_effort", profiles.validate(raw).codes, repr(domain))

    def test_schema_version_va_hinh_dang_goc(self):
        self.assertEqual(profiles.validate(mutated(lambda r: r.update({"schema_version": 1}))).codes, ("PROFILE_SCHEMA_VERSION_INVALID",))
        self.assertEqual(profiles.validate([]).codes, ("PROFILE_SCHEMA_VERSION_INVALID",))
        self.assertEqual(profiles.validate(mutated(lambda r: r.update({"models": []}))).codes, ("PROFILE_SCHEMA_INVALID",))
        self.assertEqual(profiles.validate(mutated(lambda r: r.pop("module_params"))).codes, ("PROFILE_SCHEMA_INVALID",))

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
