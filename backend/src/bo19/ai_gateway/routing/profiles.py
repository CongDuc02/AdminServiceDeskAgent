"""Hồ sơ model — cấu hình có schema (ADR-035, điều kiện 1; mục Triển khai ở B4 của 06-structure.md).

`model_profiles.json` nằm trong repo, không bí mật. Schema liệt kê, cho từng mã model, tham số được phép gửi kèm và miền giá trị; mỗi tier trỏ một mã model
cùng tham số của nó. Đổi hồ sơ — kể cả chỉ `reasoning_effort` — là một thay đổi có ghi: một dòng `CHANGELOG.md` và kích hoạt Regression gate (điều kiện 2).
Chỉ `base_url` và khoá là biến môi trường (`config.settings`) — đổi sang OpenRouter là đổi base URL, khoá và hồ sơ model, không đổi mã.

`load_profiles` không ném: trả `ProfileCheck` gồm hồ sơ (nếu hợp lệ) và danh sách mã lỗi, vì bước kiểm khởi động #21 chạy hết rồi mới gom mã.
Mã lỗi mang tên tham số, tên tier và mã model — **không** mang giá trị.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parent / "model_profiles.json"
REQUIRED_TIERS = ("CHEAP", "STRONG")  # EMBEDDING khi A-028 chốt
SCHEMA_VERSION = 1

# Tham số do `ai_gateway` tự đặt hoặc provider từ chối (docs/reference/llm-groq.md mục 6a) — không bao giờ khai được qua cấu hình.
RESERVED_PARAMS = frozenset({"model", "messages", "response_format", "stream", "stream_options", "n", "logprobs", "logit_bias", "top_logprobs", "name"})


@dataclass(frozen=True)
class ModelProfile:
    tier: str
    model: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Profiles:
    tiers: dict[str, ModelProfile]

    def for_tier(self, tier: str) -> ModelProfile:
        return self.tiers[tier]


@dataclass(frozen=True)
class ProfileCheck:
    profiles: Profiles | None
    codes: tuple[str, ...]


def _is_scalar(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool))


def _in_domain(value: Any, domain: list[Any]) -> bool:
    return any(value == d and type(value) is type(d) for d in domain)  # `True` không được coi là `1`


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
    models, tiers = raw.get("models"), raw.get("tiers")
    if not isinstance(models, dict) or not isinstance(tiers, dict):
        return ProfileCheck(None, ("PROFILE_SCHEMA_INVALID",))
    allowed: dict[str, dict[str, list[Any]]] = {}
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
            elif not isinstance(domain, list) or not domain or not all(_is_scalar(v) for v in domain):
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
            codes.append(f"PROFILE_MODEL_UNKNOWN:{tier}")  # tier trỏ tới model không có (hoặc không hợp lệ) trong `models`
            continue
        tier_ok = True
        for name, value in params.items():
            if name not in allowed[model]:
                codes.append(f"PROFILE_PARAM_NOT_ALLOWED:{tier}:{_safe(name)}")  # tham số không thuộc model đó
                tier_ok = False
            elif not _in_domain(value, allowed[model][name]):
                codes.append(f"PROFILE_PARAM_VALUE_INVALID:{tier}:{_safe(name)}")  # giá trị ngoài miền — không ghi giá trị
                tier_ok = False
        if tier_ok:
            out[tier] = ModelProfile(tier, model, dict(params))
    if codes:
        return ProfileCheck(None, tuple(codes))
    return ProfileCheck(Profiles(out), ())


def _safe(text: object) -> str:
    """Tên trong mã lỗi: chỉ ký tự khuôn tên, tối đa 64 — một khoá lạ trong file không được đưa nội dung tuỳ ý vào log."""
    return "".join(c if c.isalnum() or c in "_.-/" else "?" for c in str(text))[:64]
