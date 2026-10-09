"""Hồ sơ model — cấu hình có schema (ADR-035, điều kiện 1; quyết định PO 2026-10-05 ở mục Cập nhật của ADR-035; A-090).

`model_profiles.json` nằm trong repo, không bí mật. **Schema 2:**

- `models[<mã model>].allowed_params` — tham số được phép gửi kèm và miền giá trị của từng tham số: `{"values": [...]}` (danh sách đóng) hoặc
  `{"type": "integer" | "number", "min": ..., "max": ...}` (khoảng, `max` tuỳ chọn).
- `tiers[<tier>]` — mã model và `params`. **Mọi tham số ảnh hưởng output ghi tường minh, không dựa mặc định provider:** `reasoning_effort`, `temperature` và `include_reasoning` là bắt buộc ở cả hai tier. `include_reasoning: false` bảo Groq không trả văn bản suy luận; adapter vẫn bỏ trường suy luận nếu provider trả về (lớp thứ hai).
- `calibration[<call_name>]` — **tuỳ chọn**: nhãn một dòng nói trần output của module đã hiệu chỉnh theo đâu (PO, 2026-10-09: "hiệu chỉnh theo B4b, n nhỏ"). JSON không có comment nên nhãn là dữ liệu;
  không gửi cho provider. Khoá phải là module có thật, giá trị là chuỗi không rỗng, tối đa 120 ký tự.
- `module_params[<call_name>]` — tham số theo từng module. **Trần output cứng** `max_completion_tokens` là bắt buộc cho mọi module có prompt module (A-090). Tham số của module và của tier không được trùng tên.

`max_tokens` (deprecated, `docs/reference/llm-groq-chat-params.md`) không bao giờ gửi: nằm trong `RESERVED_PARAMS`.
Đổi hồ sơ — kể cả chỉ một giá trị — là một thay đổi có ghi: một dòng `CHANGELOG.md` và kích hoạt Regression gate (ADR-035, điều kiện 2).

`load_profiles` không ném: trả `ProfileCheck` gồm hồ sơ (nếu hợp lệ) và danh sách mã lỗi, vì bước kiểm khởi động #21 chạy hết rồi mới gom mã.
Mã lỗi mang tên tham số, tên tier, tên module và mã model — **không** mang giá trị.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parent / "model_profiles.json"
REQUIRED_TIERS = ("CHEAP", "STRONG")  # EMBEDDING khi A-028 chốt
REQUIRED_TIER_PARAMS = ("reasoning_effort", "temperature", "include_reasoning")  # include_reasoning=false: không nhận văn bản suy luận (PO, 2026-10-05; số đo B4b)
REQUIRED_MODULE_PARAMS = ("max_completion_tokens",)
# Module có prompt module và tier của nó — `tests/test_checks_gateway.py` đòi khớp `prompt_modules.MODULES`.
MODULE_TIERS = {"classify_intent": "CHEAP", "extract_slots": "CHEAP", "draft_free_content": "STRONG"}
SCHEMA_VERSION = 2
MAX_CALIBRATION_LABEL = 120

# Tham số do `ai_gateway` tự đặt, provider từ chối, hoặc đã bị thay thế (docs/reference/llm-groq.md mục 6a; llm-groq-chat-params.md) — không bao giờ khai được qua cấu hình.
RESERVED_PARAMS = frozenset({"model", "messages", "response_format", "stream", "stream_options", "n", "logprobs", "logit_bias", "top_logprobs", "name", "max_tokens"})


@dataclass(frozen=True)
class ModelProfile:
    tier: str
    model: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Profiles:
    tiers: dict[str, ModelProfile]
    modules: dict[str, dict[str, Any]] = field(default_factory=dict)
    calibration: dict[str, str] = field(default_factory=dict)

    def for_tier(self, tier: str) -> ModelProfile:
        return self.tiers[tier]

    def profile_for(self, call_name: str, tier: str) -> ModelProfile:
        """Hồ sơ hiệu lực của một lời gọi: tham số của tier cộng tham số của module (trần output)."""
        base = self.tiers[tier]
        return ModelProfile(base.tier, base.model, {**base.params, **self.modules.get(call_name, {})})


@dataclass(frozen=True)
class ProfileCheck:
    profiles: Profiles | None
    codes: tuple[str, ...]


def _is_scalar(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool))


def _in_values(value: Any, values: list[Any]) -> bool:
    return any(value == d and type(value) is type(d) for d in values)  # `True` không được coi là `1`


def _domain_ok(domain: Any) -> bool:
    if not isinstance(domain, dict):
        return False
    if set(domain) == {"values"}:
        return isinstance(domain["values"], list) and bool(domain["values"]) and all(_is_scalar(v) for v in domain["values"])
    kind, lo, hi = domain.get("type"), domain.get("min"), domain.get("max")
    if kind not in ("integer", "number") or not set(domain) <= {"type", "min", "max"} or lo is None:
        return False
    nums = [x for x in (lo, hi) if x is not None]
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in nums) or (kind == "integer" and not all(isinstance(x, int) for x in nums)):
        return False
    return hi is None or hi >= lo


def _value_ok(value: Any, domain: dict[str, Any]) -> bool:
    if "values" in domain:
        return _in_values(value, domain["values"])
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if domain["type"] == "integer" and not isinstance(value, int):
        return False
    return value >= domain["min"] and (domain.get("max") is None or value <= domain["max"])


def load_profiles(path: Path = DEFAULT_PATH) -> ProfileCheck:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ProfileCheck(None, ("PROFILE_FILE_UNREADABLE",))
    return validate(raw)


def validate(raw: Any) -> ProfileCheck:
    codes: list[str] = []
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        return ProfileCheck(None, ("PROFILE_SCHEMA_VERSION_INVALID",))
    models, tiers, module_params = raw.get("models"), raw.get("tiers"), raw.get("module_params")
    if not isinstance(models, dict) or not isinstance(tiers, dict) or not isinstance(module_params, dict):
        return ProfileCheck(None, ("PROFILE_SCHEMA_INVALID",))
    allowed: dict[str, dict[str, dict[str, Any]]] = {}
    for model, spec in models.items():
        params = spec.get("allowed_params") if isinstance(spec, dict) else None
        if not isinstance(params, dict):
            codes.append(f"PROFILE_MODEL_INVALID:{_safe(model)}")
            continue
        ok = True
        for name, domain in params.items():
            if name in RESERVED_PARAMS:
                codes.append(f"PROFILE_PARAM_RESERVED:{_safe(model)}:{_safe(name)}")
                ok = False
            elif not _domain_ok(domain):
                codes.append(f"PROFILE_PARAM_DOMAIN_INVALID:{_safe(model)}:{_safe(name)}")
                ok = False
        if ok:
            allowed[model] = params

    out: dict[str, ModelProfile] = {}
    for tier in REQUIRED_TIERS:
        if tier not in tiers:
            codes.append(f"PROFILE_TIER_MISSING:{tier}")
    for tier, spec in tiers.items():
        if tier not in REQUIRED_TIERS:
            codes.append(f"PROFILE_TIER_UNKNOWN:{_safe(tier)}")
            continue
        model = spec.get("model") if isinstance(spec, dict) else None
        params = spec.get("params") if isinstance(spec, dict) else None
        if not isinstance(model, str) or not model.strip():
            codes.append(f"PROFILE_TIER_MODEL_MISSING:{tier}")
            continue
        if not isinstance(params, dict):
            codes.append(f"PROFILE_TIER_PARAMS_INVALID:{tier}")
            continue
        if model not in allowed:
            codes.append(f"PROFILE_MODEL_UNKNOWN:{tier}")
            continue
        tier_ok = True
        for name in REQUIRED_TIER_PARAMS:
            if name not in params:
                codes.append(f"PROFILE_TIER_PARAM_MISSING:{tier}:{name}")  # tường minh, không dựa mặc định provider
                tier_ok = False
        for name, value in params.items():
            if name not in allowed[model]:
                codes.append(f"PROFILE_PARAM_NOT_ALLOWED:{tier}:{_safe(name)}")
                tier_ok = False
            elif not _value_ok(value, allowed[model][name]):
                codes.append(f"PROFILE_PARAM_VALUE_INVALID:{tier}:{_safe(name)}")  # không ghi giá trị
                tier_ok = False
        if tier_ok:
            out[tier] = ModelProfile(tier, model, dict(params))

    modules: dict[str, dict[str, Any]] = {}
    for call, tier in MODULE_TIERS.items():
        if call not in module_params:
            codes.append(f"PROFILE_MODULE_MISSING:{call}")
    for call, params in module_params.items():
        tier = MODULE_TIERS.get(call)
        if tier is None:
            codes.append(f"PROFILE_MODULE_UNKNOWN:{_safe(call)}")
            continue
        if not isinstance(params, dict):
            codes.append(f"PROFILE_MODULE_PARAMS_INVALID:{call}")
            continue
        base = out.get(tier)
        model = tiers.get(tier, {}).get("model") if isinstance(tiers.get(tier), dict) else None
        if base is None or model not in allowed:
            continue  # lỗi của tier đã được báo
        mod_ok = True
        for name in REQUIRED_MODULE_PARAMS:
            if name not in params:
                codes.append(f"PROFILE_MODULE_PARAM_MISSING:{call}:{name}")  # trần output cứng bắt buộc (A-090)
                mod_ok = False
        for name, value in params.items():
            if name in base.params:
                codes.append(f"PROFILE_PARAM_CONFLICT:{call}:{_safe(name)}")
                mod_ok = False
            elif name not in allowed[model]:
                codes.append(f"PROFILE_MODULE_PARAM_NOT_ALLOWED:{call}:{_safe(name)}")
                mod_ok = False
            elif not _value_ok(value, allowed[model][name]):
                codes.append(f"PROFILE_MODULE_PARAM_VALUE_INVALID:{call}:{_safe(name)}")
                mod_ok = False
        if mod_ok:
            modules[call] = dict(params)
    calibration: dict[str, str] = {}
    raw_cal = raw.get("calibration", {})
    if not isinstance(raw_cal, dict):
        codes.append("PROFILE_CALIBRATION_INVALID")
    else:
        for call, label in raw_cal.items():
            if call not in MODULE_TIERS or not isinstance(label, str) or not label.strip() or len(label) > MAX_CALIBRATION_LABEL or not label.isprintable():
                codes.append(f"PROFILE_CALIBRATION_INVALID:{_safe(call)}")  # không ghi nhãn
            else:
                calibration[call] = label
    if codes:
        return ProfileCheck(None, tuple(codes))
    return ProfileCheck(Profiles(out, modules, calibration), ())


def _safe(text: object) -> str:
    """Tên trong mã lỗi: chỉ ký tự khuôn tên, tối đa 64 — một khoá lạ trong file không được đưa nội dung tuỳ ý vào log."""
    return "".join(c if c.isalnum() or c in "_.-/" else "?" for c in str(text))[:64]
