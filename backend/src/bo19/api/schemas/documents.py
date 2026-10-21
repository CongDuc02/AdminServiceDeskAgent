"""Model request/response của nhóm Văn bản — khớp `DocumentSummary`, `ReviewQueueItem`, `ReviewQueuePage`, `DocumentReviewView` và bốn body thao tác cổng ở `contracts/openapi.yaml`
(mục Hàng đợi và văn bản, mục Thao tác cổng trên văn bản của 05-api.md; B9b1).

Body chặt (`extra="forbid"`, số nguyên `strict`): `self_approval_reason` nhận được (contract) nhưng ở Sprint 1 bị bỏ qua khi không bị chặn D-006 — đường thoát là Sprint 3. `ApplySealBody` **không** có `seal_type`:
loại dấu lấy từ `document`, và một trường lạ là `VALIDATION_FAILED`.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from bo19.api.schemas.requests import EmployeeBriefOut, ProvenanceOut, RequestSummaryOut


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_row_version: int = Field(ge=1, strict=True)
    self_approval_reason: str | None = Field(None, min_length=1)


class ApproveContentBody(_Body):
    pass


class SignBody(_Body):
    pass


class IssueBody(_Body):
    pass


class ApplySealBody(_Body):
    copies_count: int = Field(ge=1, strict=True)
    page_count: int | None = Field(None, ge=1, strict=True)


class DocumentSummaryOut(BaseModel):
    id: uuid.UUID
    request_id: uuid.UUID
    request_type_code: str
    status: str
    status_label: str
    status_changed_at: dt.datetime
    revision_round: int
    operating_mode: Literal["NON_PRODUCTION", "PRODUCTION"]
    requires_seal: bool | None
    seal_type: str | None
    issue_in_progress: bool
    halted: bool
    job_failed: bool
    job_failed_code: str | None  # Sprint 1 thêm: mã `job.last_error_code` khi `job_failed` (ví dụ `NO_ELIGIBLE_SIGNER`) — chỉ mã
    document_number: str | None
    issued_date: dt.date | None
    row_version: int


class ReviewQueueItemOut(BaseModel):
    document: DocumentSummaryOut
    request_type_name: str
    beneficiary: EmployeeBriefOut


class ReviewQueuePageOut(BaseModel):
    items: list[ReviewQueueItemOut]
    next_cursor: str | None


class TemplateRefOut(BaseModel):
    template_id: uuid.UUID
    template_code: str
    template_version_id: uuid.UUID
    version_no: int


class VariableViewOut(BaseModel):
    variable_name: str
    kind: str
    value: str | None
    value_erased: bool
    source_slot_name: str | None
    slot_source: str | None
    sensitivity: Literal["INT", "PER", "RES"] | None
    provenance: ProvenanceOut | None
    fill_after_approval: bool


class RenderRefOut(BaseModel):
    id: uuid.UUID
    render_kind: Literal["DRAFT", "FINAL"]
    revision_round: int
    template_version_id: uuid.UUID
    created_at: dt.datetime
    pin_reason: Literal["APPROVED_CONTENT", "ISSUED"] | None


class ApprovalStepViewOut(BaseModel):
    id: uuid.UUID
    step_kind: str
    level: int
    revision_round: int
    status: Literal["OPEN", "DECIDED", "CANCELLED"]
    assignee_employee_id: uuid.UUID | None
    opened_at: dt.datetime
    closed_at: dt.datetime | None
    self_approval_expected: bool
    self_approved: bool
    self_approval_reason: str | None


class DecisionTextViewOut(BaseModel):
    text_kind: str
    body: str | None
    erased: bool


class DecisionViewOut(BaseModel):
    id: uuid.UUID
    kind: str
    actor: EmployeeBriefOut
    delegation_id: uuid.UUID | None
    created_at: dt.datetime
    change_scope: Literal["FREE_CONTENT", "SLOT_DATA"] | None
    change_targets: list[str] | None
    texts: list[DecisionTextViewOut]


class DocumentReviewViewOut(BaseModel):
    document: DocumentSummaryOut
    request: RequestSummaryOut
    template: TemplateRefOut
    variables: list[VariableViewOut]
    renders: list[RenderRefOut]
    current_draft_render_id: uuid.UUID | None
    approved_render_id: uuid.UUID | None
    final_render_id: uuid.UUID | None
    approval_steps: list[ApprovalStepViewOut]
    decisions: list[DecisionViewOut]
    latest_halt: dict[str, Any] | None  # `HaltView` — luôn `null` ở Sprint 1: chưa có `halt_for_human`
