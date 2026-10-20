"""`document_issue` — ghi **lệnh phát hành** (mục Thao tác cổng của 03-agents.md; `POST /documents/{id}/actions/issue`, trả 202; ADR-040).

Một giao dịch: bước `ISSUE_ORDER` sinh ra đã `DECIDED` (chỗ mang cờ tự duyệt, ADR-027), `decision_record` `ISSUE_ORDERED` — chính là lệnh phát hành, không có bảng riêng — `audit_event`, và job `finalize_issue`.
`document` **không đổi trạng thái** (`SIGNED` không cần dấu, hoặc `SEALED`) và **không có số nào được cấp ở đây**: số chỉ cấp trong `finalize_issue` (`queue_worker`, B9b2). Lệnh đã ghi mà job chưa chạy — ví dụ worker ngừng —
không để lại số nào treo. Khoảng từ lệnh tới `ISSUED` là cờ dẫn xuất `issue_in_progress` (mục 4.4 của 04-data.md).

Mỗi `document` đúng một lệnh ở Sprint 1: đã có `ISSUE_ORDERED` thì `StateConflict` (lệnh mới sau tiếp quản là Sprint 2). `document` đang có bước `TAKEOVER` `OPEN` → `AwaitingTakeover`.
"""
from __future__ import annotations

import uuid

from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.gate_ops import _gate as g
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.enqueue import enqueue
from bo19.tool_layer.kernel.permission import require
from bo19.tool_layer.tools._common import actor_id

PERMISSION = "document.issue"
KIND = "ISSUE_ORDERED"


def document_issue(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID, decision_id: uuid.UUID, expected_row_version: int) -> g.GateResult:
    me = actor_id(ctx)
    require(ctx, PERMISSION)
    with pool.acquire() as conn, unit_of_work(conn):
        doc = g.lock_document(conn, document_id)
        prior = g.prior_decision(conn, me, doc, decision_id, KIND)
        if prior is not None:
            return prior
        g.check_state(doc, expected_row_version, frozenset({"SEALED", "SIGNED"}))
        if doc.status == "SIGNED" and doc.requires_seal is not False:
            raise g.StateConflict(doc.status)  # `SIGNED` mà còn cần dấu là trạng thái thoáng qua của `document_sign` — không phải chỗ phát hành
        if conn.execute("SELECT 1 FROM approval_step WHERE document_id = %s AND step_kind = 'TAKEOVER' AND status = 'OPEN'", (doc.id,)).fetchone() is not None:
            raise g.AwaitingTakeover
        if conn.execute("SELECT 1 FROM decision_record WHERE document_id = %s AND kind = 'ISSUE_ORDERED'", (doc.id,)).fetchone() is not None:
            raise g.StateConflict(doc.status)
        g.separation(me, doc)
        step_id = g.insert_step(conn, doc, "ISSUE_ORDER", assignee=None, decided=True)
        created_at = g.record_decision(conn, decision_id, KIND, me, doc, step_id)
        job = enqueue(conn, job_type=g.FINALIZE_JOB, payload={"document_id": str(doc.id), "decision_record_id": str(decision_id)}, subject_document_id=doc.id, dedupe_key=str(decision_id))
        g.record_audit(conn, ctx, doc, decision_id, "document.issue", {"status": doc.status, "approval_step_id": step_id, "job_id": job.job_id, "job_created": job.created})
        return g.GateResult(decision_id, created_at, False)
