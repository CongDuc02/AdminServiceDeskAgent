"""`document_approve_content` — cổng HITL số 1: cán bộ duyệt nội dung (mục Thao tác cổng của 03-agents.md; `POST /documents/{id}/actions/approve-content`, mục Thao tác cổng trên văn bản của 05-api.md; ADR-040).

Một giao dịch: `PENDING_APPROVAL → APPROVED` kèm `approved_content_hash`, `approved_decision_id`, `approved_render_id` **trong cùng câu `UPDATE`** (`ck_document_approved_complete`), ghim bản nháp đang duyệt
(`document_render_pin`, `APPROVED_CONTENT`), `decision_record` `APPROVED`, đóng bước `CONTENT_REVIEW`, `audit_event`, job `resume_document_graph`. `request` **ở nguyên `IN_REVIEW`**.

**Hash tính lại từ DB tại chỗ**, không tin bản nháp hay state của graph: hàm `build_values` cho bảng giá trị (cùng nguồn với `render_draft`), bỏ biến *điền sau duyệt*, rồi `domain.content_hash` — `finalize_issue` (B9b2) gọi lại
đúng hàm đó (INV-01). Còn issue nào của bảng giá trị ngoài `TEMPLATE_NOT_ACTIVE_AT_RENDER` (phiên bản đã ghim bị gỡ sau khi render nháp thì bản nháp vẫn là bản người duyệt thấy) thì **không duyệt**: `NotApprovable`.
Không đọc `object_storage` (mục 5.4 của 04-data.md): kiểm toàn vẹn byte là việc của `route_signing`.
"""
from __future__ import annotations

import uuid

from bo19.domain.content_hash import approved_content_hash
from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.gate_ops import _gate as g
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require
from bo19.tool_layer.kernel.transition import transition
from bo19.tool_layer.tools._common import ToolError, actor_id
from bo19.tool_layer.tools.render_values import TEMPLATE_NOT_ACTIVE_AT_RENDER, build_values
from bo19.tool_layer.tools.template_fetch import read_version

PERMISSION = "document.approve_content"
KIND = "APPROVED"


class NotApprovable(ToolError):
    code = "NOT_APPROVABLE"  # bảng giá trị còn issue (ngoài phiên bản template bị gỡ) hoặc `document` chưa có bản nháp hiện hành — chỉ mang mã


def document_approve_content(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID, decision_id: uuid.UUID, expected_row_version: int) -> g.GateResult:
    me = actor_id(ctx)
    require(ctx, PERMISSION)
    with pool.acquire() as conn, unit_of_work(conn):
        doc = g.lock_document(conn, document_id)
        prior = g.prior_decision(conn, me, doc, decision_id, KIND)
        if prior is not None:
            return prior
        g.check_state(doc, expected_row_version, frozenset({"PENDING_APPROVAL"}))
        g.separation(me, doc)
        step_id, _ = g.open_step(conn, doc, "CONTENT_REVIEW")
        if doc.current_draft_render_id is None:
            raise NotApprovable("NO_DRAFT_RENDER")
        built = build_values(conn, document_id)
        blocking = sorted({i.code for i in built.issues if i.code != TEMPLATE_NOT_ACTIVE_AT_RENDER})
        if blocking:
            raise NotApprovable(blocking[0])
        template = read_version(conn, doc.template_version_id)
        after_approval = {v.name for v in template.variables if v.fill_after_approval}
        digest = approved_content_hash(template_version_id=doc.template_version_id, operating_mode=doc.operating_mode,
                                       values={k: v for k, v in built.values.items() if k not in after_approval})
        created_at = g.record_decision(conn, decision_id, KIND, me, doc, step_id)
        conn.execute("INSERT INTO document_render_pin (render_id, pin_reason, decision_record_id) VALUES (%s, 'APPROVED_CONTENT', %s)", (doc.current_draft_render_id, decision_id))
        g.decide_step(conn, step_id)
        transition(conn, "document", document_id, to="APPROVED", expected_from="PENDING_APPROVAL", expected_row_version=expected_row_version,
                   set_values={"approved_content_hash": digest, "approved_decision_id": decision_id, "approved_render_id": doc.current_draft_render_id})
        job = g.enqueue_resume(conn, doc, decision_id)
        g.record_audit(conn, ctx, doc, decision_id, "document.approve_content",
                       {"status_from": "PENDING_APPROVAL", "status_to": "APPROVED", "approval_step_id": step_id, "render_id": doc.current_draft_render_id, "job_id": job.job_id, "job_created": job.created})
        return g.GateResult(decision_id, created_at, False)
