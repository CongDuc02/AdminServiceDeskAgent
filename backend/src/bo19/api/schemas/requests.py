"""Model request/response của nhóm Request — khớp `RequestSummary`, `RequestSummaryPage`, `SlotView`, `RequestDetail`, `SlotConfirmBody`, `SubmitBody`, `DecisionResult`
ở `contracts/openapi.yaml` (mục Request của 05-api.md).

Body chặt (`extra="forbid"`, số nguyên `strict`): một trường lạ như `submit_ready` từ client là `VALIDATION_FAILED`, không bị lặng lẽ bỏ qua — `submit` không có chỗ nào nhận kết quả kiểm từ client.
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SLOT_NAME = r"^[a-z][a-z0-9_]*$"


class SlotConfirmItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot_name: str = Field(pattern=SLOT_NAME, max_length=64)
    expected_row_version: int = Field(ge=1, strict=True)


class SlotConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmations: list[SlotConfirmItem] = Field(min_length=1)


class SubmitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_row_version: int = Field(ge=1, strict=True)


class EmployeeBriefOut(BaseModel):
    id: uuid.UUID
    employee_code: str
    full_name: str


class RequestSummaryOut(BaseModel):
    id: uuid.UUID
    request_type_code: str
    request_type_name: str
    status: str
    status_label: str
    status_changed_at: dt.datetime
    created_at: dt.datetime
    created_by_employee_id: uuid.UUID
    beneficiary: EmployeeBriefOut
    chat_session_id: uuid.UUID | None
    submitted_at: dt.datetime | None
    expires_at: dt.datetime | None
    row_version: int
    artifacts: list[dict[str, Any]]  # `ArtifactRef` — rỗng tới khi có `document` (B9)


class RequestSummaryPageOut(BaseModel):
    items: list[RequestSummaryOut]
    next_cursor: str | None


class ProvenanceOut(BaseModel):
    source: str
    synced_at: dt.datetime


class SlotViewOut(BaseModel):
    slot_name: str
    label: str
    description: str
    data_type: str
    source: str
    sensitivity: Literal["INT", "PER", "RES"]
    is_required: bool
    value: Any
    value_status: Literal["PROVIDED", "PROPOSED", "CONFIRMED", "SYSTEM_SET", "ERASED"] | None
    erased: bool
    provenance: ProvenanceOut | None
    proposed_from_request_id: uuid.UUID | None
    confirmed_at: dt.datetime | None
    row_version: int | None


class FailedRuleOut(BaseModel):
    slot_name: str
    rule_code: str


class RequestDetailOut(RequestSummaryOut):
    slots: list[SlotViewOut]
    missing_slots: list[str]
    unconfirmed_slots: list[str]
    failed_rules: list[FailedRuleOut]
    submit_ready: bool
    changes_requested: dict[str, Any] | None  # `ChangesRequestedView` — có khi có `document` (B9)
    documents: list[dict[str, Any]]  # `DocumentOwnerView` — như trên


class DecisionResultOut(BaseModel):
    decision_record_id: uuid.UUID
    kind: str
    created_at: dt.datetime
    request: RequestSummaryOut
    document: dict[str, Any] | None  # `DocumentSummary` — `null` khi chưa có `document`, như sau `SUBMITTED`
