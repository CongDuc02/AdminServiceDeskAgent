"""`request_slots_read` — nạp giá trị slot cho prompt (slot `ERASED` có `value` NULL nên không bao giờ được trả), theo đúng danh sách tự khai của prompt module (mục Tool Registry của 03-agents.md; INV-03).

Chỉ tác nhân hệ thống của graph đang xử lý `request` đó. Xin một slot không có trong khai báo của module gọi → `SLOT_NOT_DECLARED`: đây là **bug** (prompt module xin slot nó không khai),
không bao giờ lộ ra client — lộ ra là rò cấu trúc prompt. Kiểm TRƯỚC khi đọc dòng nào. Chỉ đọc (giao dịch `READ ONLY`).
"""
from __future__ import annotations

import uuid
from typing import Any

from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
from bo19.tool_layer.checks.eligibility import RequestNotFound
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_system
from bo19.tool_layer.tools._common import ToolError


class SlotNotDeclared(ToolError):
    code = "SLOT_NOT_DECLARED"


def request_slots_read(pool: Pool, ctx: ToolContext, *, request_id: uuid.UUID, slot_names: list[str], declared_slots: frozenset[str]) -> dict[str, Any]:
    """`declared_slots` — danh sách slot mà prompt module gọi đã tự khai (từ khai báo của module, không từ người gọi tool)."""
    require_system(ctx)
    undeclared = [n for n in slot_names if n not in declared_slots]
    if undeclared:
        raise SlotNotDeclared(undeclared[0])
    with pool.acquire() as conn, read_only(conn):
        if conn.execute("SELECT 1 FROM request WHERE id = %s", (request_id,)).fetchone() is None:
            raise RequestNotFound
        rows = conn.execute("SELECT slot_name, value FROM request_slot WHERE request_id = %s AND slot_name = ANY(%s) AND value IS NOT NULL",
                            (request_id, list(slot_names))).fetchall()
    return {name: value for name, value in rows}
