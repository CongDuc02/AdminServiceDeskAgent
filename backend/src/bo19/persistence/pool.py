"""Pool kết nối — hai ngữ nghĩa mượn (mục Cây backend của 06-structure.md, Pool cạn thì bỏ lượt của ADR-013).

- `acquire(timeout)` — cho nghiệp vụ: chờ tới `timeout` giây; hết hạn thì `PoolExhausted`.
- `try_acquire()` — cho vòng poll tín hiệu: **gần như không chờ** — tối đa `_TRY_WAIT_SECONDS` (10 ms); pool cạn thì trả `None`, nhịp đó bỏ lượt.
  Không dùng `timeout=0`: `psycopg_pool` tính hạn chót rồi trừ thời gian đã trôi, nên `0` thành số âm và không bao giờ giao connection, kể cả khi có connection rảnh.

Cả hai trả connection về pool khi thoát, và luôn rollback giao dịch còn dở trước khi trả: connection quay lại pool ở trạng thái rỗi.
Kích thước và timeout là giá trị tạm của `config.working_values` (A-057).
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
import psycopg_pool
from psycopg.pq import TransactionStatus

from bo19.config import working_values as wv


_TRY_WAIT_SECONDS = 0.01


class PoolExhausted(Exception):
    """Không mượn được connection trong thời gian cho phép. Mang mã, không mang DSN hay host."""

    code = "POOL_EXHAUSTED"


class Pool:
    def __init__(self, dsn: str, *, application_name: str, min_size: int = wv.POOL_MIN_SIZE, max_size: int = wv.POOL_MAX_SIZE,
                 acquire_timeout_s: float = wv.POOL_ACQUIRE_TIMEOUT_SECONDS) -> None:
        self._acquire_timeout_s = acquire_timeout_s
        self._pool = psycopg_pool.ConnectionPool(
            dsn, min_size=min_size, max_size=max_size, open=False,
            kwargs={"connect_timeout": 10, "application_name": application_name},
        )

    def open(self, wait_timeout_s: float = 15) -> None:
        self._pool.open(wait=True, timeout=wait_timeout_s)

    def close(self) -> None:
        self._pool.close()

    @contextmanager
    def acquire(self, timeout: float | None = None) -> Iterator[psycopg.Connection]:
        wait = self._acquire_timeout_s if timeout is None else timeout
        try:
            conn = self._pool.getconn(timeout=wait)
        except psycopg_pool.PoolTimeout as e:
            raise PoolExhausted from e
        try:
            yield conn
        finally:
            self._give_back(conn)

    @contextmanager
    def try_acquire(self) -> Iterator[psycopg.Connection | None]:
        try:
            conn = self._pool.getconn(timeout=_TRY_WAIT_SECONDS)
        except psycopg_pool.PoolTimeout:
            yield None
            return
        try:
            yield conn
        finally:
            self._give_back(conn)

    def _give_back(self, conn: psycopg.Connection) -> None:
        if not conn.closed and conn.info.transaction_status != TransactionStatus.IDLE:
            conn.rollback()
        self._pool.putconn(conn)
