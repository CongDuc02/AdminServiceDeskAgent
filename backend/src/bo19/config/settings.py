"""Cấu hình có kiểu — phần cần cho S2 của Spike 1.

Chỉ hai biến: `BO19_DATABASE_URL` (mục Biến môi trường theo môi trường của 11-ops.md) và `PORT`
(Render đặt, mặc định 10000 — docs/reference/render-web-service-health-checks.md). Phần còn lại của
mục Cây backend (trần budget, múi giờ, hạn chót, BO19_ENVIRONMENT) thêm ở track build của Sprint 1.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


class ConfigError(Exception):
    """Cấu hình thiếu hay sai — mang một mã, không mang giá trị."""


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)  # secret — không bao giờ vào repr hay log
    port: int

    def __repr__(self) -> str:
        return f"Settings(database_url=<ẩn>, port={self.port})"


def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
    url = env.get("BO19_DATABASE_URL", "").strip()
    if not url:
        raise ConfigError("CONFIG_DATABASE_URL_MISSING")
    raw_port = env.get("PORT", "10000").strip()
    if not raw_port.isdigit() or not 1 <= int(raw_port) <= 65535:
        raise ConfigError("CONFIG_PORT_INVALID")
    return Settings(database_url=url, port=int(raw_port))
