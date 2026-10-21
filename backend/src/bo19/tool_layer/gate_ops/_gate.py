"""Phần dùng chung của bốn thao tác cổng trên `document` — `document_approve_content`, `document_sign`, `document_apply_seal`, `document_issue` (B9b1; mục Thao tác cổng của 03-agents.md; ADR-040).

Mỗi thao tác là MỘT giao dịch theo khuôn `request_submit`: permission → khoá `document` rồi `request` (cùng thứ tự với `document_submit_for_review`) → `decision_record` trùng khoá → trạng thái và `row_version` → tách biệt
trách nhiệm (D-006) → nghiệp vụ → ghi `decision_record`, đóng `approval_step`, đổi trạng thái, `audit_event`, enqueue. Mọi thứ commit cùng nhau hoặc lăn cùng nhau.

**Khoá = id của `decision_record`.** Cùng khoá, cùng người, cùng `document`, cùng loại → lặp lại hợp lệ (không ghi gì); lệch bất kỳ điều nào → `DecisionIdConflict`, không trả gì về dòng đó. Hai cán bộ bấm cùng lúc dùng hai khoá
khác nhau: người sau thấy `row_version`/trạng thái đã đổi (`StateConflict`); `uq_decision_one_per_approval_step` là lớp thứ hai ở DB.

**D-006 ở Sprint 1:** người thụ hưởng của `request` thì bị chặn — luôn `SelfApprovalBlocked`. Đường thoát (`self_approval_reason`, bước `self_approved`) là Sprint 3 (kế hoạch B9b); không có đường nào tự bỏ qua.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import psycopg

from bo19.tool_layer.gate_ops._errors import AwaitingTakeover, DecisionIdConflict, StateConflict
from bo19.tool_layer.kernel import audit
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.enqueue import Enqueued, enqueue
from bo19.tool_layer.kernel.transition import transition
from bo19.tool_layer.tools._common import ToolError

RESUME_JOB = "resume_document_graph"
FINALIZE_JOB = "finalize_issue"

__all__ = ["DecisionIdConflict", "StateConflict", "DocumentNotFound", "SelfApprovalBlocked", "AwaitingTakeover", "StepMissing", "GateDocument", "GateResult"]


class DocumentNotFound(ToolError):
    code = "DOCUMENT_NOT_FOUND"


class SelfApprovalBlocked(ToolError):
    code = "SELF_APPROVAL_BLOCKED"  # D-006: người thụ hưởng làm thao tác bị chặn; đường thoát là Sprint 3


class StepMissing(ToolError):
    code = "APPROVAL_STEP_MISSING"  # trạng thái nói cổng đang mở mà không có `approval_step` `OPEN` tương ứng — dữ liệu hỏng, không phải lỗi nghiệp vụ


@dataclass(frozen=True)
class GateDocument:
    id: uuid.UUID
    request_id: uuid.UUID
    status: str
    row_version: int
    revision_round: int
    operating_mode: str
    requires_seal: bool | None
    seal_type: str | None
    signer_employee_id: uuid.UUID | None
    template_version_id: uuid.UUID
    current_draft_render_id: uuid.UUID | None
    beneficiary_employee_id: uuid.UUID
    request_status: str


@dataclass(frozen=True)
class GateResult:
    decision_record_id: uuid.UUID
    created_at: dt.datetime
    replayed: bool  # khoá đã là `decision_record` cùng loại của chính người này, cho chính `document` này: không ghi gì


def lock_document(conn: psycopg.Connection, document_id: uuid.UUID) -> GateDocument:
    """Khoá hàng `document` rồi hàng `request` của nó. Không tồn tại → `DocumentNotFound`."""
    row = conn.execute("SELECT id, request_id, status, row_version, revision_round, operating_mode, requires_seal, seal_type, signer_employee_id, template_version_id, current_draft_render_id "
                       "FROM document WHERE id = %s FOR UPDATE", (document_id,)).fetchone()
    if row is None:
        raise DocumentNotFound
    req = conn.execute("SELECT status, beneficiary_employee_id FROM request WHERE id = %s FOR UPDATE", (row[1],)).fetchone()
    return GateDocument(*row, beneficiary_employee_id=req[1], request_status=req[0])


def prior_decision(conn: psycopg.Connection, me: uuid.UUID, doc: GateDocument, decision_id: uuid.UUID, kind: str) -> GateResult | None:
    """Đọc SAU khi giành khoá: lần gọi cùng khoá chạy trước đã commit thì thấy ở đây."""
    prior = conn.execute("SELECT actor_employee_id, document_id, kind, created_at FROM decision_record WHERE id = %s", (decision_id,)).fetchone()
    if prior is None:
        return None
    if (prior[0], prior[1], prior[2]) != (me, doc.id, kind):
        raise DecisionIdConflict
    return GateResult(decision_id, prior[3], True)


def check_state(doc: GateDocument, expected_row_version: int, statuses: frozenset[str]) -> None:
    if doc.row_version != expected_row_version or doc.status not in statuses:
        raise StateConflict(doc.status)


def separation(me: uuid.UUID, doc: GateDocument) -> None:
    """D-006 ở Sprint 1 (ADR-040 mục 3): căn cứ chặn là `request.beneficiary_employee_id`, không phải người tạo — nhập hộ rồi duyệt là hợp lệ."""
    if me == doc.beneficiary_employee_id:
        raise SelfApprovalBlocked


def open_step(conn: psycopg.Connection, doc: GateDocument, step_kind: str) -> tuple[uuid.UUID, uuid.UUID | None]:
    """(id, người được giao) của bước `OPEN` loại `step_kind` ở vòng hiện tại, đã khoá hàng. Thiếu → `StepMissing`."""
    row = conn.execute("SELECT id, assignee_employee_id FROM approval_step WHERE document_id = %s AND step_kind = %s AND revision_round = %s AND status = 'OPEN' FOR UPDATE",
                       (doc.id, step_kind, doc.revision_round)).fetchone()
    if row is None:
        raise StepMissing(step_kind)
    return row[0], row[1]


def insert_step(conn: psycopg.Connection, doc: GateDocument, step_kind: str, *, assignee: uuid.UUID | None, decided: bool = False) -> uuid.UUID:
    """Thêm một `approval_step`. `decided`: sinh ra đã `DECIDED` (`ISSUE_ORDER`) — chỉ là chỗ mang cờ tự duyệt, không bao giờ `OPEN`."""
    step_id = uuid.uuid4()
    if decided:
        conn.execute("INSERT INTO approval_step (id, document_id, step_kind, level, revision_round, assignee_employee_id, status, closed_at) VALUES (%s, %s, %s, 1, %s, %s, 'DECIDED', now())",
                     (step_id, doc.id, step_kind, doc.revision_round, assignee))
    else:
        conn.execute("INSERT INTO approval_step (id, document_id, step_kind, level, revision_round, assignee_employee_id, status) VALUES (%s, %s, %s, 1, %s, %s, 'OPEN')",
                     (step_id, doc.id, step_kind, doc.revision_round, assignee))
    return step_id


def decide_step(conn: psycopg.Connection, step_id: uuid.UUID) -> None:
    transition(conn, "approval_step", step_id, to="DECIDED", expected_from="OPEN")


def record_decision(conn: psycopg.Connection, decision_id: uuid.UUID, kind: str, me: uuid.UUID, doc: GateDocument, step_id: uuid.UUID | None) -> dt.datetime:
    return conn.execute("INSERT INTO decision_record (id, kind, actor_employee_id, request_id, document_id, approval_step_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING created_at",
                        (decision_id, kind, me, doc.request_id, doc.id, step_id)).fetchone()[0]


def enqueue_resume(conn: psycopg.Connection, doc: GateDocument, decision_id: uuid.UUID) -> Enqueued:
    """Job đánh thức `document_graph`: payload chỉ mang id (ADR-008); `dedupe_key` = id quyết định nên mỗi quyết định đúng một job sống."""
    return enqueue(conn, job_type=RESUME_JOB, payload={"document_id": str(doc.id), "decision_record_id": str(decision_id)}, subject_document_id=doc.id, dedupe_key=str(decision_id))


def record_audit(conn: psycopg.Connection, ctx: ToolContext, doc: GateDocument, decision_id: uuid.UUID, action: str, payload: dict) -> None:
    audit.record(conn, ctx, action=action, entity_type="document", entity_id=doc.id, request_id=doc.request_id, document_id=doc.id, decision_record_id=decision_id, payload=payload)
