"""`graph_thread` — sổ thread LangGraph, cạnh bảng checkpoint (mục Bảng chi tiết của 04-data.md; ngoại lệ đóng số 2 của mục Tool Registry của 03-agents.md).

Chỉ định danh thread, trạng thái và mốc thời gian — không PII, không quyết định nghiệp vụ. Ghi bởi lớp chạy graph, không bởi node nào, nên không `audit_event` (sổ sách kỹ thuật).
Thread `intake:{chat_session_id}` sống tới khi phiên đóng (job `checkpoint_purge` chuyển nó `ENDED`/`PURGED` — chưa có ở B6b).
"""
from __future__ import annotations

import uuid

from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work


class ThreadSchemaMismatch(Exception):
    """Thread đã có ghi `state_schema_version` khác phiên bản mã đang chạy — không resume bằng state sai hình (mục Schema state đổi giữa chừng của 03-agents.md; bước kiểm #9 là phép kiểm lúc khởi động)."""

    code = "THREAD_SCHEMA_MISMATCH"


class ThreadNotActive(Exception):
    code = "THREAD_NOT_ACTIVE"  # `ENDED`/`PURGED`: phiên đã đóng — không chạy lượt mới trên thread đó


def intake_thread_id(chat_session_id: uuid.UUID | str) -> str:
    return f"intake:{chat_session_id}"


def touch_intake_thread(pool: Pool, chat_session_id: uuid.UUID, *, schema_version: int) -> str:
    """Tạo thread `ACTIVE` nếu chưa có; có rồi thì ghi `last_step_at`. Trả `thread_id`."""
    thread_id = intake_thread_id(chat_session_id)
    with pool.acquire() as conn, unit_of_work(conn):
        conn.execute("INSERT INTO graph_thread (thread_id, graph_name, chat_session_id, state_schema_version) VALUES (%s, 'intake_graph', %s, %s) ON CONFLICT (thread_id) DO NOTHING",
                     (thread_id, chat_session_id, schema_version))
        row = conn.execute("SELECT status, state_schema_version FROM graph_thread WHERE thread_id = %s FOR UPDATE", (thread_id,)).fetchone()
        if row[0] != "ACTIVE":
            raise ThreadNotActive
        if row[1] != schema_version:
            raise ThreadSchemaMismatch
        conn.execute("UPDATE graph_thread SET last_step_at = now(), updated_at = now() WHERE thread_id = %s", (thread_id,))
    return thread_id


# ---- thread `document:{document_id}` (B9a, ADR-039) ------------------------------------------------------------------------------------------------------------

DOCUMENT_GRAPH = "document_graph"


def document_thread_id(document_id: uuid.UUID | str) -> str:
    return f"document:{document_id}"


def touch_document_thread(pool: Pool, document_id: uuid.UUID, *, schema_version: int) -> str:
    """Tạo thread `ACTIVE` nếu chưa có (cần `document` đã có dòng — khoá ngoại); có rồi thì ghi `last_step_at`. `ENDED`/`PURGED` thì `ThreadNotActive`. Trả `thread_id`."""
    thread_id = document_thread_id(document_id)
    with pool.acquire() as conn, unit_of_work(conn):
        conn.execute("INSERT INTO graph_thread (thread_id, graph_name, document_id, state_schema_version) VALUES (%s, 'document_graph', %s, %s) ON CONFLICT (thread_id) DO NOTHING",
                     (thread_id, document_id, schema_version))
        row = conn.execute("SELECT status, state_schema_version FROM graph_thread WHERE thread_id = %s FOR UPDATE", (thread_id,)).fetchone()
        if row[0] not in ("ACTIVE", "WAITING"):
            raise ThreadNotActive
        if row[1] != schema_version:
            raise ThreadSchemaMismatch
        conn.execute("UPDATE graph_thread SET last_step_at = now(), updated_at = now() WHERE thread_id = %s", (thread_id,))
    return thread_id


def mark_document_thread(pool: Pool, document_id: uuid.UUID, *, waiting_at: str | None = None, ended: bool = False) -> None:
    """Ghi trạng thái thread theo kết quả của một lần chạy graph: chờ ở một `interrupt` (`WAITING`, tên node), đã tới `END` (`ENDED`), hoặc đang chạy (`ACTIVE`). Do lớp chạy graph gọi, không do node."""
    if waiting_at is not None and ended:
        raise ValueError("waiting_at và ended loại trừ nhau")
    with pool.acquire() as conn, unit_of_work(conn):
        if ended:
            conn.execute("UPDATE graph_thread SET status = 'ENDED', waiting_at_node = NULL, ended_at = now(), last_step_at = now(), updated_at = now() WHERE thread_id = %s AND status IN ('ACTIVE', 'WAITING')",
                         (document_thread_id(document_id),))
        elif waiting_at is not None:
            conn.execute("UPDATE graph_thread SET status = 'WAITING', waiting_at_node = %s, last_step_at = now(), updated_at = now() WHERE thread_id = %s AND status IN ('ACTIVE', 'WAITING')",
                         (waiting_at, document_thread_id(document_id)))
        else:
            conn.execute("UPDATE graph_thread SET status = 'ACTIVE', waiting_at_node = NULL, last_step_at = now(), updated_at = now() WHERE thread_id = %s AND status IN ('ACTIVE', 'WAITING')",
                         (document_thread_id(document_id),))
