"""Cấu hình có kiểu — đọc biến môi trường một lần lúc khởi động (mục Biến môi trường theo môi trường của 11-ops.md).

`load_settings` **không bao giờ ném** vì một giá trị sai: nó trả `Settings` kèm `problems` — mọi biến thiếu hay sai, mỗi biến một mã —
vì bước kiểm khởi động chạy hết rồi mới gom danh sách mã trượt (mục Bước kiểm khởi động của 06-structure.md), không dừng ở lỗi đầu.
Trường có `problems` mang giá trị `None`. Tiến trình chỉ phục vụ khi bước kiểm khởi động đạt, tức khi `problems` rỗng.
Giá trị trong `problems` là **mã**, không bao giờ là giá trị của biến; `repr` ẩn DSN và secret.

Mặc định của các biến số là giá trị WV của `proposals/sprint1-working-values-a031-a048.md` — Render không cần đặt chúng.
"""
from __future__ import annotations

import enum
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ORG_TIMEZONE = "Asia/Ho_Chi_Minh"  # A-041 `Đã chốt`


class Environment(str, enum.Enum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


# Tên biến cho từng trường — log ghi tên biến, không ghi giá trị.
ENV_NAMES: Mapping[str, str] = {
    "environment": "BO19_ENVIRONMENT",
    "database_url": "BO19_DATABASE_URL",
    "port": "PORT",
    "session_secret": "BO19_SESSION_SECRET",
    "timezone": "BO19_ORG_TIMEZONE",
    "shutdown_delay_s": "BO19_SHUTDOWN_DELAY_SECONDS",
    "turn_deadline_s": "BO19_TURN_DEADLINE_SECONDS",
    "turn_margin_s": "BO19_TURN_DEADLINE_MARGIN_SECONDS",
    "object_storage_timeout_s": "BO19_OBJECT_STORAGE_TIMEOUT_SECONDS",
    "stored_object_lease_s": "BO19_STORED_OBJECT_LEASE_SECONDS",
    "argon2_time_cost": "BO19_ARGON2_TIME_COST",
    "argon2_memory_cost_kib": "BO19_ARGON2_MEMORY_COST_KIB",
    "argon2_parallelism": "BO19_ARGON2_PARALLELISM",
    "llm_base_url": "BO19_LLM_BASE_URL",
    "llm_api_key": "BO19_LLM_API_KEY",
}

DEFAULT_LLM_BASE_URL = "https://api.groq.com/openai/v1"  # ADR-032 mốc 1, ADR-035; đổi sang provider khác là đổi biến này, khoá và hồ sơ model — không đổi mã

# (trường, mặc định) — WV-01, WV-02, WV-03, WV-08, WV-10, WV-16.
_INT_DEFAULTS: tuple[tuple[str, int], ...] = (
    ("shutdown_delay_s", 30), ("turn_deadline_s", 20), ("turn_margin_s", 10), ("object_storage_timeout_s", 30),
    ("stored_object_lease_s", 120), ("argon2_time_cost", 2), ("argon2_memory_cost_kib", 19456), ("argon2_parallelism", 1),
)


@dataclass(frozen=True)
class Settings:
    environment: Environment | None
    database_url: str | None = field(repr=False)  # secret — không bao giờ vào repr hay log
    port: int | None
    session_secret: str | None = field(repr=False)  # secret
    timezone: str | None
    shutdown_delay_s: int | None
    turn_deadline_s: int | None
    turn_margin_s: int | None
    object_storage_timeout_s: int | None
    stored_object_lease_s: int | None
    argon2_time_cost: int | None
    argon2_memory_cost_kib: int | None
    argon2_parallelism: int | None
    llm_base_url: str | None
    llm_api_key: str | None = field(repr=False)  # secret — không bao giờ vào repr, log hay lỗi (ADR-035, mục Cập nhật B4)
    problems: tuple[tuple[str, str], ...] = ()  # (trường, mã) — mã dạng CONFIG_<TÊN>_MISSING | _INVALID

    def problem(self, name: str) -> str | None:
        return dict(self.problems).get(name)

    def __repr__(self) -> str:
        hidden = ("database_url", "session_secret", "llm_api_key")
        shown = ", ".join(f"{f}={getattr(self, f)!r}" for f in ENV_NAMES if f not in hidden)
        return f"Settings({shown}, database_url=<ẩn>, session_secret=<ẩn>, llm_api_key=<ẩn>, problems={[p for p, _ in self.problems]})"


def _code(name: str, kind: str) -> str:
    return f"CONFIG_{ENV_NAMES[name].removeprefix('BO19_')}_{kind}"


def _get(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(ENV_NAMES[name])
    return None if value is None or value.strip() == "" else value.strip()


def _https_url(raw: str) -> bool:
    parts = urlsplit(raw)
    return parts.scheme == "https" and bool(parts.hostname) and not any(c.isspace() for c in raw)


def _positive_int(raw: str) -> int | None:
    return int(raw) if raw.isascii() and raw.isdigit() and len(raw) <= 9 and int(raw) >= 1 else None


def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
    problems: list[tuple[str, str]] = []
    values: dict[str, object] = {}

    raw = _get(env, "environment")
    if raw is None:
        values["environment"] = None
        problems.append(("environment", _code("environment", "MISSING")))
    else:
        try:
            values["environment"] = Environment(raw)  # đúng chữ thường, đúng một trong dev|staging|prod — không đoán, không mặc định
        except ValueError:
            values["environment"] = None
            problems.append(("environment", _code("environment", "INVALID")))

    for name in ("database_url", "session_secret"):
        raw = _get(env, name)
        values[name] = raw
        if raw is None:
            problems.append((name, _code(name, "MISSING")))

    raw = _get(env, "port") or "10000"  # Render đặt PORT; mặc định 10000 (docs/reference/render-web-service-health-checks.md)
    port = _positive_int(raw)
    values["port"] = port if port is not None and port <= 65535 else None
    if values["port"] is None:
        problems.append(("port", _code("port", "INVALID")))

    raw = _get(env, "timezone") or ORG_TIMEZONE
    values["timezone"] = None
    if raw == ORG_TIMEZONE:
        try:
            ZoneInfo(raw)
            values["timezone"] = raw
        except Exception:  # noqa: BLE001 — thiếu tzdata trong image cũng là cấu hình không dùng được
            pass
    if values["timezone"] is None:
        problems.append(("timezone", _code("timezone", "INVALID")))

    for name, default in _INT_DEFAULTS:
        raw = _get(env, name)
        value = default if raw is None else _positive_int(raw)
        values[name] = value
        if value is None:
            problems.append((name, _code(name, "INVALID")))

    raw = _get(env, "llm_base_url") or DEFAULT_LLM_BASE_URL
    values["llm_base_url"] = raw if _https_url(raw) else None  # bắt buộc https (bước kiểm #21)
    if values["llm_base_url"] is None:
        problems.append(("llm_base_url", _code("llm_base_url", "INVALID")))
    values["llm_api_key"] = _get(env, "llm_api_key")  # tuỳ chọn ở B4 — `api` chưa gọi LLM; thiếu khoá không phải lỗi cấu hình lúc khởi động

    return Settings(problems=tuple(problems), **values)  # type: ignore[arg-type]
