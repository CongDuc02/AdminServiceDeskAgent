"""Lối ghi DB: unit of work một giao dịch (mục Cây backend của 06-structure.md).

Chỉ `tool_layer`, `ai_gateway.budget`, `orchestrator.runtime` và `entrypoints` được import file này (contract `write-path`).
B3 chỉ cần mức tối thiểu: một giao dịch ghi — commit khi xong, rollback khi có ngoại lệ — và lỗi toàn vẹn đổi thành `IntegrityViolation`
mang mã (`persistence.errors`). Chưa có nhiều bước ghi nối nhau, chưa có hook audit: chúng thuộc `tool_layer.kernel`.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.pq import TransactionStatus

from bo19.persistence.errors import IntegrityViolation, classify


@contextmanager
def unit_of_work(conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    """Một giao dịch ghi trên `conn`. Gọi khi `conn` đang rỗi; nếu còn giao dịch dở của lần dùng trước thì rollback trước."""
    if conn.info.transaction_status != TransactionStatus.IDLE:
        conn.rollback()
    try:
        with conn.transaction():
            yield conn
    except psycopg.Error as e:
        code = classify(e)
        if code is None:
            raise
        raise IntegrityViolation(code) from None  # `from None`: chuỗi nguyên nhân mang thông điệp PostgreSQL — không để lọt
