"""`document_sign` — người ký ghi nhận ký (mục Thao tác cổng của 03-agents.md; `POST /documents/{id}/actions/sign`; ADR-040 mục 6).

Một giao dịch: `PENDING_SIGNATURE → SIGNED`, rồi `SIGNED → PENDING_SEAL` nếu `requires_seal` (mở bước `SEAL` giao cho không ai — ai mang `document.apply_seal` làm được), `decision_record` `SIGNED`, đóng bước `SIGNATURE`, và
`request IN_REVIEW → APPROVED` — "đã ký" (AUD-01) — rồi `audit_event` và job `resume_document_graph`.

**Chỉ nhận chính người được giao** (`document.signer_employee_id`, do `signing_route` ghi): tên in trên bản `FINAL` là tên người đã ký. Người khác mang `document.sign` nhận `NotAssignedSigner` (`PermissionDenied`, chi tiết `assignee`).
"""
from __future__ import annotations

import uuid

from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.gate_ops import _gate as g
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import PermissionDenied, require
from bo19.tool_layer.kernel.transition import transition
from bo19.tool_layer.tools._common import actor_id

PERMISSION = "document.sign"
KIND = "SIGNED"


class NotAssignedSigner(PermissionDenied):
    """Có `document.sign` nhưng không phải người `signing_route` đã giao. Cùng mã `PERMISSION_DENIED`; `detail` = `assignee` (không phải tên một permission)."""

    def __init__(self) -> None:
        super().__init__("assignee")


def document_sign(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID, decision_id: uuid.UUID, expected_row_version: int) -> g.GateResult:
    me = actor_id(ctx)
    require(ctx, PERMISSION)
    with pool.acquire() as conn, unit_of_work(conn):
        doc = g.lock_document(conn, document_id)
        prior = g.prior_decision(conn, me, doc, decision_id, KIND)
        if prior is not None:
            return prior
        g.check_state(doc, expected_row_version, frozenset({"PENDING_SIGNATURE"}))
        g.separation(me, doc)
        step_id, assignee = g.open_step(conn, doc, "SIGNATURE")
        if doc.signer_employee_id != me or assignee != me:
            raise NotAssignedSigner
        created_at = g.record_decision(conn, decision_id, KIND, me, doc, step_id)
        g.decide_step(conn, step_id)
        transition(conn, "document", document_id, to="SIGNED", expected_from="PENDING_SIGNATURE", expected_row_version=expected_row_version)
        final = "SIGNED"
        seal_step = None
        if doc.requires_seal:
            transition(conn, "document", document_id, to="PENDING_SEAL", expected_from="SIGNED")
            seal_step = g.insert_step(conn, doc, "SEAL", assignee=None)
            final = "PENDING_SEAL"
        transition(conn, "request", doc.request_id, to="APPROVED", expected_from="IN_REVIEW")
        job = g.enqueue_resume(conn, doc, decision_id)
        g.record_audit(conn, ctx, doc, decision_id, "document.sign",
                       {"status_from": "PENDING_SIGNATURE", "status_to": final, "approval_step_id": step_id, "seal_step_id": seal_step, "job_id": job.job_id, "job_created": job.created})
        return g.GateResult(decision_id, created_at, False)
