"""Nối PostgreSQL cho bước kiểm khởi động, và phân loại lỗi nối — O1-4 của 12-roadmap.md.

`sqlstate` là None ở mọi lỗi nối, kể cả sai mật khẩu (S2; `docs/reference/psycopg-connect-errors.md`), nên phân loại dựa trên thông báo của
libpq — theo đúng các chuỗi đã quan sát ở file đó, không đoán thêm. Thông báo có thể mang host nên **không bao giờ** vào log; chỉ ghi lớp.
"""
from __future__ import annotations

import enum

import psycopg


class ConnectFailure(str, enum.Enum):
    AUTH = "AUTH"        # máy chủ trả lời và từ chối xác thực — sai mật khẩu hay role không tồn tại
    NETWORK = "NETWORK"  # không tới được máy chủ — không phân giải được host, cổng đóng, quá hạn
    OTHER = "OTHER"      # mọi thứ chưa quan sát: không đoán


_NETWORK_MARKERS = ("failed to resolve host", "Connection refused")


def classify_connect_error(exc: BaseException) -> ConnectFailure:
    if isinstance(exc, psycopg.errors.ConnectionTimeout):
        return ConnectFailure.NETWORK
    text = str(exc)
    if "authentication failed" in text:
        return ConnectFailure.AUTH
    if any(marker in text for marker in _NETWORK_MARKERS):
        return ConnectFailure.NETWORK
    return ConnectFailure.OTHER


def connect(dsn: str, application_name: str) -> psycopg.Connection:
    return psycopg.connect(dsn, connect_timeout=10, application_name=application_name)
