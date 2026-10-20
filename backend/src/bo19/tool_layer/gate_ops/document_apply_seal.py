"""`document_apply_seal` — cổng HITL số 2: dùng con dấu (mục Thao tác cổng của 03-agents.md; `POST /documents/{id}/actions/apply-seal`; mục Duyệt dấu và khoảng hoàn tất phát hành của 08-hitl.md).

Một giao dịch: `PENDING_SEAL → SEALED`, `seal_action` (loại dấu **lấy từ `document`**, không nhận từ client; `operating_mode` đã ghim — `NON_PRODUCTION` là dấu thử nghiệm, D-009), `decision_record` `SEALED`, đóng bước `SEAL`,
`audit_event`, job `resume_document_graph`. `copies_count ≥ 1`; `page_count` bắt buộc và ≥ 2 khi dấu là `EDGE_STAMP` (EC-SR-03). Không có lối từ chối dùng dấu (A-034).
"""
from __future__ import annotations

import uuid

from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.gate_ops import _gate as g
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require
from bo19.tool_layer.kernel.transition import transition
from bo19.tool_layer.tools._common import ToolError, actor_id

PERMISSION = "document.apply_seal"
KIND = "SEALED"


class InvalidSealInput(ToolError):
    code = "INVALID_SEAL_INPUT"

    def __init__(self, field: str, rule: str) -> None:
        super().__init__(field)
        self.field, self.rule = field, rule  # rule ∈ REQUIRED | OUT_OF_RANGE — khớp mã con `fields[].code` của 05-api.md


def document_apply_seal(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID, decision_id: uuid.UUID, expected_row_version: int, copies_count: int, page_count: int | None) -> g.GateResult:
    me = actor_id(ctx)
    require(ctx, PERMISSION)
    with pool.acquire() as conn, unit_of_work(conn):
        doc = g.lock_document(conn, document_id)
        prior = g.prior_decision(conn, me, doc, decision_id, KIND)
        if prior is not None:
            return prior
        g.check_state(doc, expected_row_version, frozenset({"PENDING_SEAL"}))
        g.separation(me, doc)
        if copies_count < 1:
            raise InvalidSealInput("copies_count", "OUT_OF_RANGE")
        if doc.seal_type == "EDGE_STAMP":
            if page_count is None:
                raise InvalidSealInput("page_count", "REQUIRED")
            if page_count < 2:
                raise InvalidSealInput("page_count", "OUT_OF_RANGE")
        elif page_count is not None and page_count < 1:
            raise InvalidSealInput("page_count", "OUT_OF_RANGE")
        step_id, _ = g.open_step(conn, doc, "SEAL")
        created_at = g.record_decision(conn, decision_id, KIND, me, doc, step_id)
        g.decide_step(conn, step_id)
        conn.execute("INSERT INTO seal_action (id, document_id, operating_mode, seal_type, copies_count, page_count, decision_record_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                     (uuid.uuid4(), doc.id, doc.operating_mode, doc.seal_type, copies_count, page_count, decision_id))
        transition(conn, "document", document_id, to="SEALED", expected_from="PENDING_SEAL", expected_row_version=expected_row_version)
        job = g.enqueue_resume(conn, doc, decision_id)
        g.record_audit(conn, ctx, doc, decision_id, "document.apply_seal",
                       {"status_from": "PENDING_SEAL", "status_to": "SEALED", "approval_step_id": step_id, "seal_type": doc.seal_type, "operating_mode": doc.operating_mode, "copies_count": copies_count,
                        "page_count": page_count, "job_id": job.job_id, "job_created": job.created})
        return g.GateResult(decision_id, created_at, False)
