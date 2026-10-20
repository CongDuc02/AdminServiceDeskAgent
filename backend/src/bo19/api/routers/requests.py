"""Router nhóm Request — bốn endpoint Sprint 1 của mục Request của 05-api.md (đoạn Triển khai ở B7): `GET /requests?scope=OWN`, `GET /requests/{id}`, `POST …/actions/confirm-slots`,
`POST …/actions/submit`. `POST …/actions/cancel` ở Sprint 2; `scope=ALL`, `ASSIGNED` ở Sprint 3 (mục Endpoint → sprint của 12-roadmap.md).

Quyền: người đăng nhập (đọc lại từ DB mỗi request — ADR-013), và **chỉ người tạo** thấy hay ghi được: không tồn tại và của người khác cùng `NOT_FOUND`. Mọi ghi đi qua `tool_layer`
(`employee_ops.request_slot_confirm`, `gate_ops.request_submit`); mã lỗi nội bộ được dịch ở đây sang `error_code` của 05-api.md, `details` chỉ mang tên và mã.
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse

from bo19.api.deps.idempotency import idempotency_key
from bo19.api.deps.session import current_employee
from bo19.api.deps.state import AppState, get_state
from bo19.api.errors import ApiError
from bo19.api.queries import requests as queries
from bo19.api.queries.auth import SessionEmployee
from bo19.api.schemas.requests import DecisionResultOut, RequestDetailOut, RequestSummaryPageOut, SlotConfirmBody, SubmitBody
from bo19.config import working_values as wv
from bo19.observability.trace import current_trace_id
from bo19.tool_layer.employee_ops.request_slot_confirm import Confirmation, NotProposed, StaleValue, request_slot_confirm
from bo19.tool_layer.gate_ops.request_submit import AwaitingTakeover, DecisionIdConflict, NotReady, StateConflict, request_submit
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import PermissionDenied, employee_context
from bo19.tool_layer.tools._common import NotEditable, NotOwnRequest

router = APIRouter(tags=["requests"])

READ_OWN = "request.read_own"
RequestStatusParam = Literal["DRAFT", "NEEDS_INFO", "SUBMITTED", "IN_REVIEW", "CHANGES_REQUESTED", "APPROVED", "FULFILLED", "REJECTED", "CANCELLED", "EXPIRED"]


def _ctx(state: AppState, employee: SessionEmployee) -> ToolContext:
    with state.pool.acquire() as conn:
        return employee_context(conn, employee.id, current_trace_id())


def _denied(e: PermissionDenied) -> ApiError:
    return ApiError("PERMISSION_DENIED", {"permission": e.detail} if e.detail else None)


def _invalid(field: str, code: str) -> ApiError:
    return ApiError("VALIDATION_FAILED", {"fields": [{"field": field, "code": code}]})


def _detail(state: AppState, request_id: uuid.UUID, employee: SessionEmployee) -> RequestDetailOut:
    with state.pool.acquire() as conn:
        detail = queries.own_request_detail(conn, request_id, employee.id)
    if detail is None:
        raise ApiError("NOT_FOUND")
    return RequestDetailOut(**detail)


@router.get("/requests", response_model=RequestSummaryPageOut)
def list_requests(scope: Literal["OWN", "ALL", "ASSIGNED"] = Query(...), status: RequestStatusParam | None = Query(None), cursor: str | None = Query(None),
                  limit: int = Query(wv.PAGE_LIMIT_DEFAULT, ge=1, le=wv.PAGE_LIMIT_MAX), employee: SessionEmployee = Depends(current_employee),
                  state: AppState = Depends(get_state)) -> RequestSummaryPageOut:
    if scope != "OWN":
        raise _invalid("scope", "NOT_ALLOWED")  # ALL, ASSIGNED: Sprint 3
    if READ_OWN not in _ctx(state, employee).actor.permissions:
        raise ApiError("PERMISSION_DENIED", {"permission": READ_OWN})
    try:
        with state.pool.acquire() as conn:
            items, next_cursor = queries.list_own(conn, employee.id, status=status, limit=limit, cursor=cursor)
    except queries.BadCursor:
        raise _invalid("cursor", "INVALID_FORMAT") from None
    return RequestSummaryPageOut(items=items, next_cursor=next_cursor)


@router.get("/requests/{request_id}", response_model=RequestDetailOut)
def get_request(request_id: uuid.UUID, employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> RequestDetailOut:
    if READ_OWN not in _ctx(state, employee).actor.permissions:
        raise ApiError("NOT_FOUND")  # không được xem thì như không tồn tại (mục Phân quyền ở tầng API của 05-api.md)
    return _detail(state, request_id, employee)


@router.post("/requests/{request_id}/actions/confirm-slots", response_model=RequestDetailOut)
def confirm_slots(request_id: uuid.UUID, body: SlotConfirmBody, employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> RequestDetailOut:
    ctx = _ctx(state, employee)
    try:
        request_slot_confirm(state.pool, ctx, request_id=request_id, items=[Confirmation(c.slot_name, c.expected_row_version) for c in body.confirmations])
    except PermissionDenied as e:
        raise _denied(e) from None
    except NotOwnRequest:
        raise ApiError("NOT_FOUND") from None
    except NotEditable as e:
        raise ApiError("REQUEST_NOT_EDITABLE", {"current_status": e.detail}) from None
    except NotProposed as e:
        raise ApiError("SLOT_NOT_PROPOSED", {"slot_names": [e.detail]}) from None
    except StaleValue as e:
        raise ApiError("SLOT_VALUE_STALE", {"slot_names": [e.detail]}) from None
    return _detail(state, request_id, employee)


@router.post("/requests/{request_id}/actions/submit", response_model=DecisionResultOut)
def submit_request(request_id: uuid.UUID, body: SubmitBody, idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
                   employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> JSONResponse:
    key = idempotency_key(idempotency_key_header)
    ctx = _ctx(state, employee)
    try:
        submitted = request_submit(state.pool, ctx, request_id=request_id, decision_id=key, expected_row_version=body.expected_row_version)
    except PermissionDenied as e:
        raise _denied(e) from None
    except NotOwnRequest:
        raise ApiError("NOT_FOUND") from None
    except DecisionIdConflict:
        raise ApiError("IDEMPOTENCY_KEY_CONFLICT") from None
    except StateConflict as e:
        raise ApiError("STATE_CONFLICT", {"current_status": e.current_status}) from None
    except AwaitingTakeover:
        raise ApiError("DOCUMENT_AWAITING_TAKEOVER") from None
    except NotReady as e:
        raise ApiError("REQUEST_NOT_READY", {"missing_slots": list(e.missing_slots), "unconfirmed_slots": list(e.unconfirmed_slots),
                                             "failed_rules": [{"slot_name": s, "rule_code": c} for s, c in e.failed_rules]}) from None
    with state.pool.acquire() as conn:
        summary = queries.own_request_summary(conn, request_id, employee.id)
    out = DecisionResultOut(decision_record_id=submitted.decision_record_id, kind="SUBMITTED", created_at=submitted.created_at, request=summary, document=None)
    headers = {"Idempotent-Replayed": "true"} if submitted.replayed else {}
    return JSONResponse(out.model_dump(mode="json"), status_code=200, headers=headers)  # lặp lại giữ mã HTTP của lần đầu (mục 1.8 của 05-api.md)
