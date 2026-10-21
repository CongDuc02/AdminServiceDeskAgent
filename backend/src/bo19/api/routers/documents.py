"""Router nhóm Văn bản — bảy endpoint Sprint 1 của mục Hàng đợi và văn bản và mục Thao tác cổng trên văn bản của 05-api.md (đoạn Triển khai ở B9b1): `GET /documents/{id}`, `GET /review-queue`,
`GET /issue-queue`, và `POST /documents/{id}/actions/{approve-content,sign,apply-seal,issue}`. `request-changes`, `reject`, `resolve-halt`, `takeover-queue` là Sprint 2.

**NOT_FOUND hay PERMISSION_DENIED** (mục Phân quyền ở tầng API): văn bản người gọi không thấy được (`request.read_all`, hoặc `request.read_assigned` với bước giao cho mình — mục 3.4 của 09-security.md) là `NOT_FOUND`, kể cả
khi người đó mang permission của thao tác; `PERMISSION_DENIED` chỉ khi đã thấy mà thiếu permission. Mọi ghi đi qua `tool_layer.gate_ops`; mã lỗi nội bộ được dịch ở đây, `details` chỉ mang tên và mã.
`Idempotency-Key` = `decision_record.id`; lặp lại hợp lệ giữ mã HTTP của lần đầu (200; `issue`: 202) kèm `Idempotent-Replayed: true` (mục 1.8).
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse

from bo19.api.deps.idempotency import idempotency_key
from bo19.api.deps.session import current_employee
from bo19.api.deps.state import AppState, get_state
from bo19.api.errors import ApiError
from bo19.api.queries import documents as queries
from bo19.api.queries import requests as request_queries
from bo19.api.queries.auth import SessionEmployee
from bo19.api.schemas.documents import (ApplySealBody, ApproveContentBody, DocumentReviewViewOut, DocumentSummaryOut, IssueBody, ReviewQueuePageOut, SignBody)
from bo19.api.schemas.requests import DecisionResultOut, RequestSummaryOut
from bo19.config import working_values as wv
from bo19.observability.trace import current_trace_id
from bo19.tool_layer.gate_ops import _gate as gate
from bo19.tool_layer.gate_ops.document_apply_seal import InvalidSealInput, document_apply_seal
from bo19.tool_layer.gate_ops.document_approve_content import NotApprovable, document_approve_content
from bo19.tool_layer.gate_ops.document_issue import document_issue
from bo19.tool_layer.gate_ops.document_sign import document_sign
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import PermissionDenied, employee_context

router = APIRouter(tags=["documents"])

READ_ALL, READ_ASSIGNED = "request.read_all", "request.read_assigned"
QueueStatus = Literal["PENDING_APPROVAL", "PENDING_SIGNATURE", "PENDING_SEAL", "APPROVED"]
QUEUE_PERMISSION = {"PENDING_APPROVAL": "document.approve_content", "APPROVED": "document.approve_content", "PENDING_SIGNATURE": "document.sign", "PENDING_SEAL": "document.apply_seal"}


def _ctx(state: AppState, employee: SessionEmployee) -> ToolContext:
    with state.pool.acquire() as conn:
        return employee_context(conn, employee.id, current_trace_id())


def _scope(ctx: ToolContext) -> tuple[bool, bool]:
    return READ_ALL in ctx.actor.permissions, READ_ASSIGNED in ctx.actor.permissions


def _require_view_scope(ctx: ToolContext) -> bool:
    """Trả `read_all`; thiếu cả hai quyền xem là `PERMISSION_DENIED` (endpoint danh sách — không có tài nguyên nào để giấu)."""
    read_all, read_assigned = _scope(ctx)
    if not (read_all or read_assigned):
        raise ApiError("PERMISSION_DENIED", {"permission": READ_ALL})
    return read_all


@router.get("/documents/{document_id}", response_model=DocumentReviewViewOut)
def get_document(document_id: uuid.UUID, employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> DocumentReviewViewOut:
    ctx = _ctx(state, employee)
    read_all, read_assigned = _scope(ctx)
    with state.pool.acquire() as conn:
        view = queries.document_review_view(conn, document_id, employee.id, read_all=read_all, read_assigned=read_assigned)
    if view is None:
        raise ApiError("NOT_FOUND")
    return DocumentReviewViewOut(**view)


@router.get("/review-queue", response_model=ReviewQueuePageOut)
def review_queue(status: QueueStatus = Query(...), cursor: str | None = Query(None), limit: int = Query(wv.PAGE_LIMIT_DEFAULT, ge=1, le=wv.PAGE_LIMIT_MAX),
                 employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> ReviewQueuePageOut:
    ctx = _ctx(state, employee)
    wanted = QUEUE_PERMISSION[status]
    if wanted not in ctx.actor.permissions:
        raise ApiError("PERMISSION_DENIED", {"permission": wanted})
    read_all = _require_view_scope(ctx)
    try:
        with state.pool.acquire() as conn:
            items, next_cursor = queries.review_queue(conn, status=status, employee_id=employee.id, read_all=read_all, limit=limit, cursor=cursor)
    except queries.BadCursor:
        raise ApiError("VALIDATION_FAILED", {"fields": [{"field": "cursor", "code": "INVALID_FORMAT"}]}) from None
    return ReviewQueuePageOut(items=items, next_cursor=next_cursor)


@router.get("/issue-queue", response_model=ReviewQueuePageOut)
def issue_queue(cursor: str | None = Query(None), limit: int = Query(wv.PAGE_LIMIT_DEFAULT, ge=1, le=wv.PAGE_LIMIT_MAX),
                employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> ReviewQueuePageOut:
    ctx = _ctx(state, employee)
    if "document.issue" not in ctx.actor.permissions:
        raise ApiError("PERMISSION_DENIED", {"permission": "document.issue"})
    try:
        with state.pool.acquire() as conn:
            items, next_cursor = queries.issue_queue(conn, limit=limit, cursor=cursor)
    except queries.BadCursor:
        raise ApiError("VALIDATION_FAILED", {"fields": [{"field": "cursor", "code": "INVALID_FORMAT"}]}) from None
    return ReviewQueuePageOut(items=items, next_cursor=next_cursor)


# ---------------------------------------------------------------------------------------------------------------------------- thao tác cổng


def _act(state: AppState, employee: SessionEmployee, document_id: uuid.UUID, key: uuid.UUID, op: Callable[[ToolContext], gate.GateResult], *, kind: str, status_code: int) -> JSONResponse:
    ctx = _ctx(state, employee)
    read_all, read_assigned = _scope(ctx)
    with state.pool.acquire() as conn:
        if not queries.viewable(conn, document_id, employee.id, read_all=read_all, read_assigned=read_assigned):
            raise ApiError("NOT_FOUND")  # không thấy được thì như không tồn tại — kể cả khi mang permission của thao tác
    try:
        result = op(ctx)
    except PermissionDenied as e:
        raise ApiError("PERMISSION_DENIED", {"permission": e.detail} if e.detail else None) from None
    except gate.DocumentNotFound:
        raise ApiError("NOT_FOUND") from None
    except gate.DecisionIdConflict:
        raise ApiError("IDEMPOTENCY_KEY_CONFLICT") from None
    except gate.StateConflict as e:
        raise ApiError("STATE_CONFLICT", {"current_status": e.current_status}) from None
    except NotApprovable:
        raise ApiError("STATE_CONFLICT") from None
    except gate.SelfApprovalBlocked:
        raise ApiError("SELF_APPROVAL_BLOCKED") from None
    except gate.AwaitingTakeover:
        raise ApiError("DOCUMENT_AWAITING_TAKEOVER") from None
    except InvalidSealInput as e:
        raise ApiError("VALIDATION_FAILED", {"fields": [{"field": e.field, "code": e.rule}]}) from None
    with state.pool.acquire() as conn:
        summary = queries.document_summary(conn, document_id)
        request = request_queries.request_summary(conn, summary["request_id"])
    out = DecisionResultOut(decision_record_id=result.decision_record_id, kind=kind, created_at=result.created_at, request=RequestSummaryOut(**request),
                            document=DocumentSummaryOut(**summary).model_dump(mode="json"))
    headers = {"Idempotent-Replayed": "true"} if result.replayed else {}
    return JSONResponse(out.model_dump(mode="json"), status_code=status_code, headers=headers)  # lặp lại giữ mã HTTP của lần đầu (mục 1.8 của 05-api.md)


@router.post("/documents/{document_id}/actions/approve-content", response_model=DecisionResultOut)
def approve_content(document_id: uuid.UUID, body: ApproveContentBody, idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
                    employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> JSONResponse:
    key = idempotency_key(idempotency_key_header)
    return _act(state, employee, document_id, key, lambda ctx: document_approve_content(state.pool, ctx, document_id=document_id, decision_id=key, expected_row_version=body.expected_row_version),
                kind="APPROVED", status_code=200)


@router.post("/documents/{document_id}/actions/sign", response_model=DecisionResultOut)
def sign(document_id: uuid.UUID, body: SignBody, idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
         employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> JSONResponse:
    key = idempotency_key(idempotency_key_header)
    return _act(state, employee, document_id, key, lambda ctx: document_sign(state.pool, ctx, document_id=document_id, decision_id=key, expected_row_version=body.expected_row_version),
                kind="SIGNED", status_code=200)


@router.post("/documents/{document_id}/actions/apply-seal", response_model=DecisionResultOut)
def apply_seal(document_id: uuid.UUID, body: ApplySealBody, idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
               employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> JSONResponse:
    key = idempotency_key(idempotency_key_header)
    return _act(state, employee, document_id, key, lambda ctx: document_apply_seal(state.pool, ctx, document_id=document_id, decision_id=key, expected_row_version=body.expected_row_version,
                                                                                    copies_count=body.copies_count, page_count=body.page_count), kind="SEALED", status_code=200)


@router.post("/documents/{document_id}/actions/issue", response_model=DecisionResultOut, status_code=202)
def order_issue(document_id: uuid.UUID, body: IssueBody, idempotency_key_header: str | None = Header(None, alias="Idempotency-Key"),
                employee: SessionEmployee = Depends(current_employee), state: AppState = Depends(get_state)) -> JSONResponse:
    key = idempotency_key(idempotency_key_header)
    return _act(state, employee, document_id, key, lambda ctx: document_issue(state.pool, ctx, document_id=document_id, decision_id=key, expected_row_version=body.expected_row_version),
                kind="ISSUE_ORDERED", status_code=202)
