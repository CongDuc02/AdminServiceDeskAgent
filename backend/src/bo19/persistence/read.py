"""Lối đọc — mọi giao dịch mở ở READ ONLY: ghi bị PostgreSQL từ chối (mục Cây backend của 06-structure.md).

`read_only(conn)` là cửa duy nhất: mọi truy vấn của `api/queries` và các bước kiểm khởi động chạy trong nó.
`current_operating_mode` — một lần đọc cho bước kiểm khởi động #15 và #17, và cho `GET /me`.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg
from psycopg.pq import TransactionStatus

NON_PRODUCTION = "NON_PRODUCTION"
PRODUCTION = "PRODUCTION"

# Chế độ hiện hành là dòng có `effective_at` lớn nhất đã tới; chưa có dòng nào thì `NON_PRODUCTION` (D-009, mục operating_mode_change của 04-data.md).
_CURRENT_MODE = "SELECT to_mode FROM operating_mode_change WHERE effective_at <= now() ORDER BY effective_at DESC LIMIT 1"


@contextmanager
def read_only(conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    """Một giao dịch `READ ONLY` trên `conn`. Nếu `conn` còn giao dịch dở thì rollback trước — `SET TRANSACTION` phải là câu đầu."""
    if conn.info.transaction_status != TransactionStatus.IDLE:
        conn.rollback()
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        yield conn


@dataclass(frozen=True)
class OperatingModeRead:
    mode: str
    from_row: bool  # False: chưa có dòng nào — mặc định an toàn của D-009


def current_operating_mode(conn: psycopg.Connection) -> OperatingModeRead:
    with read_only(conn):
        row = conn.execute(_CURRENT_MODE).fetchone()
    return OperatingModeRead(row[0], True) if row else OperatingModeRead(NON_PRODUCTION, False)
