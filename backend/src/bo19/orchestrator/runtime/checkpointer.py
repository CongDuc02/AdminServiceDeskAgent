"""Checkpointer của LangGraph trên PostgreSQL — `PostgresSaver` trên một pool riêng; **KHÔNG BAO GIỜ gọi `setup()`** (mục Migration và checkpointer của 06-structure.md).

Nguồn đã ghim (`docs/reference/langgraph-checkpoint-postgres.md`, mục 5): kết nối phải `autocommit=True` và `row_factory=dict_row`; `prepare_threshold=0` theo `from_conn_string` của thư viện.
Credential là của `bo19_app`: nó không có quyền tạo bảng nên `setup()` sẽ bị từ chối — bảng do `migrate_main` tạo bằng `bo19_migrator` (bước 2) và cấp quyền ở bước 3.
Pool riêng vì kết nối của checkpointer khác kiểu kết nối nghiệp vụ (`dict_row`, autocommit) và checkpoint commit trên kết nối của chính nó, không dự phần vào giao dịch của tool.
"""
from __future__ import annotations

from dataclasses import dataclass

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DEFAULT_MAX_SIZE = 4  # giá trị TẠM cùng nhãn với kích thước pool nghiệp vụ (A-057) — chưa có số đo


@dataclass
class Checkpointing:
    saver: PostgresSaver
    pool: ConnectionPool

    def close(self) -> None:
        self.pool.close()


def open_checkpointer(dsn: str, *, max_size: int = DEFAULT_MAX_SIZE, application_name: str = "bo19-checkpointer") -> Checkpointing:
    pool = ConnectionPool(dsn, min_size=1, max_size=max_size, open=False, name="bo19-checkpointer",
                          kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0, "application_name": application_name})
    pool.open(wait=True, timeout=15)
    return Checkpointing(PostgresSaver(pool), pool)
