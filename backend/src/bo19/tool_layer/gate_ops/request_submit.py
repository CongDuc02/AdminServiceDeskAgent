"""`request_submit` — nhân viên gửi `request` của mình (mục 5.2 của 03-agents.md; `POST /requests/{id}/actions/submit`, đoạn Triển khai ở B7 của mục Request của 05-api.md).

**Không tin graph:** chạy lại **đúng hàm** "đủ điều kiện xử lý" (F1) mà `check_completeness` và `request_slot_confirm` dùng, trên dữ liệu đọc trong chính giao dịch này — kết quả của graph hay
`submit_ready` của client không có chỗ nào để đi vào. Trượt thì `NotReady` kèm **tên** slot (thiếu, chưa xác nhận, trượt rule) — không giá trị.

**Một giao dịch, hàng `request` bị khoá** (`FOR UPDATE` trong `load_own_request`): `DRAFT → SUBMITTED` (kèm `submitted_at`), `decision_record` loại `SUBMITTED` có id là `Idempotency-Key`, `audit_event`,
và job `render_document` (D-010, ADR-004) — commit cùng nhau hoặc lăn cùng nhau. Payload của job **chỉ mang id** (mục Vận hành của 04-data.md); `dedupe_key` = `request_id`.

**Hai lần gửi đồng thời** xếp hàng ở khoá hàng `request`: lần sau thấy `decision_record` của lần trước nếu cùng khoá (lặp lại hợp lệ, không ghi gì) hoặc `row_version` đã đổi
(`StateConflict`) — một `decision_record`, một job. `dedupe_key` của job là lớp thứ hai, cho đường nào lách được khoá hàng.

**Chưa làm (O1-15):** `CHANGES_REQUESTED → SUBMITTED` ở ca `SLOT_DATA` (`RESUBMITTED`, job `resume_document_graph`) — cần `document_graph`; tới đó `CHANGES_REQUESTED` là `StateConflict`.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.checks.eligibility import check_request
from bo19.tool_layer.kernel import audit
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.enqueue import enqueue
from bo19.tool_layer.kernel.permission import require_any
from bo19.tool_layer.kernel.transition import transition
from bo19.tool_layer.tools._common import ToolError, actor_id, load_own_request

JOB_TYPE = "render_document"
SUBMITTABLE = frozenset({"DRAFT", "NEEDS_INFO"})  # NEEDS_INFO chỉ để trả `NotReady` có tên slot; NEEDS_INFO mà đạt thì vẫn `StateConflict` — không tự đi hai cạnh


class StateConflict(ToolError):
    """Trạng thái hay `row_version` không còn như lúc nhân viên nhìn (mục 1.9 của 05-api.md)."""

    code = "STATE_CONFLICT"

    def __init__(self, current_status: str) -> None:
        super().__init__(current_status)
        self.current_status = current_status


class NotReady(ToolError):
    code = "REQUEST_NOT_READY"

    def __init__(self, missing_slots: tuple[str, ...], unconfirmed_slots: tuple[str, ...], failed_rules: tuple[tuple[str, str], ...]) -> None:
        super().__init__()
        self.missing_slots, self.unconfirmed_slots, self.failed_rules = missing_slots, unconfirmed_slots, failed_rules


class DecisionIdConflict(ToolError):
    code = "DECISION_ID_CONFLICT"  # `Idempotency-Key` đã là một `decision_record` khác người, khác `request` hay khác loại — không trả gì về dòng đó


@dataclass(frozen=True)
class Submitted:
    decision_record_id: uuid.UUID
    created_at: dt.datetime
    replayed: bool  # khoá đã là `decision_record` `SUBMITTED` của chính người này, cho chính `request` này: không ghi gì


def request_submit(pool: Pool, ctx: ToolContext, *, request_id: uuid.UUID, decision_id: uuid.UUID, expected_row_version: int) -> Submitted:
    me = actor_id(ctx)
    require_any(ctx, ("request.create", "request.supply_info"))
    with pool.acquire() as conn, unit_of_work(conn):
        row = load_own_request(conn, ctx, request_id)  # khoá hàng; không tồn tại và của người khác cùng `NotOwnRequest`
        prior = conn.execute("SELECT actor_employee_id, request_id, kind, created_at FROM decision_record WHERE id = %s", (decision_id,)).fetchone()
        if prior is not None:  # đọc SAU khi giành khoá: lần gửi cùng khoá chạy trước đã commit thì thấy ở đây
            if (prior[0], prior[1], prior[2]) != (me, request_id, "SUBMITTED"):
                raise DecisionIdConflict
            return Submitted(decision_id, prior[3], True)
        if row.row_version != expected_row_version or row.status not in SUBMITTABLE:
            raise StateConflict(row.status)
        check = check_request(conn, request_id)
        if not check.eligible:
            raise NotReady(check.missing_slots, check.unconfirmed_slots, check.failed_rules)
        if row.status != "DRAFT":
            raise StateConflict(row.status)
        transition(conn, "request", request_id, to="SUBMITTED", expected_from="DRAFT", expected_row_version=expected_row_version, extra_now=("submitted_at",))
        created_at = conn.execute("INSERT INTO decision_record (id, kind, actor_employee_id, request_id) VALUES (%s, 'SUBMITTED', %s, %s) RETURNING created_at",
                                  (decision_id, me, request_id)).fetchone()[0]
        job = enqueue(conn, job_type=JOB_TYPE, payload={"request_id": str(request_id), "decision_record_id": str(decision_id)}, dedupe_key=str(request_id))
        audit.record(conn, ctx, action="request.submit", entity_type="request", entity_id=request_id, request_id=request_id, decision_record_id=decision_id,
                     payload={"status_from": "DRAFT", "status_to": "SUBMITTED", "job_id": str(job.job_id), "job_created": job.created})
        return Submitted(decision_id, created_at, False)
