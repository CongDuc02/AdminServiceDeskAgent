"""`request_transition` — chuyển trạng thái `request` mà graph được phép tự làm: `DRAFT ↔ NEEDS_INFO` (mục Tool Registry của 03-agents.md).

**Không** gồm `SUBMITTED` — đó là thao tác của nhân viên (`request_submit`). Tác nhân hệ thống. Chuyển sang trạng thái đang có = không làm gì (kernel). Mọi cạnh khác — kể cả cạnh hợp lệ của
máy trạng thái như `DRAFT → CANCELLED` — là `ILLEGAL_TRANSITION` ở đây: graph không có quyền đó. `audit_event` mỗi lần đổi thật.
"""
from __future__ import annotations

import uuid

from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.kernel import audit
from bo19.tool_layer.kernel import transition as kernel
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_system

GRAPH_STATUSES = frozenset({"DRAFT", "NEEDS_INFO"})


def request_transition(pool: Pool, ctx: ToolContext, *, request_id: uuid.UUID, to: str) -> kernel.TransitionResult:
    require_system(ctx)
    if to not in GRAPH_STATUSES:
        raise kernel.IllegalTransition(f"?>{to}"[:40])
    with pool.acquire() as conn, unit_of_work(conn):
        row = conn.execute("SELECT status FROM request WHERE id = %s FOR UPDATE", (request_id,)).fetchone()
        if row is None:
            raise kernel.RowNotFound("request")
        if row[0] not in GRAPH_STATUSES:
            raise kernel.IllegalTransition(f"{row[0]}>{to}")
        result = kernel.transition(conn, "request", request_id, to=to)
        if result.changed:
            audit.record(conn, ctx, action="request.transition", entity_type="request", entity_id=request_id, request_id=request_id, payload={"from": row[0], "to": to})
        return result
