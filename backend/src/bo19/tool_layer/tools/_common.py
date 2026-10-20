"""Phần dùng chung của các tool `intake_agent` (mục Tool Registry của 03-agents.md): lỗi có mã, nạp `request` của chính người gọi, trạng thái còn sửa được.

Mỗi tool là MỘT giao dịch (`unit_of_work`) và nhận `Pool`: node của graph không giữ connection. Lỗi chỉ mang mã và tên — không giá trị slot, không văn bản tin nhắn.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from bo19.tool_layer.kernel.context import KernelError, ToolContext


class ToolError(KernelError):
    code = "TOOL_ERROR"


class NotOwnRequest(ToolError):
    code = "NOT_OWN_REQUEST"  # không tồn tại và của người khác đều cho cùng một mã — không lộ sự tồn tại


class NotEditable(ToolError):
    code = "NOT_EDITABLE"


EDITABLE_STATUSES = frozenset({"DRAFT", "NEEDS_INFO"})  # CHANGES_REQUESTED còn sửa được chỉ ở ca SLOT_DATA — `slot_data_reopened` (O1-15, B9b)


@dataclass(frozen=True)
class RequestRow:
    id: uuid.UUID
    request_type_code: str
    status: str
    created_by_employee_id: uuid.UUID
    beneficiary_employee_id: uuid.UUID
    chat_session_id: uuid.UUID | None
    row_version: int


def actor_id(ctx: ToolContext) -> uuid.UUID:
    if ctx.actor.employee_id is None:
        raise NotOwnRequest  # tác nhân hệ thống không "sở hữu" request nào
    return ctx.actor.employee_id


def load_own_request(conn: psycopg.Connection, ctx: ToolContext, request_id: uuid.UUID, *, lock: bool = True) -> RequestRow:
    """`request` do chính người gọi tạo. Không tồn tại và của người khác cùng ném `NotOwnRequest`."""
    me = actor_id(ctx)
    row = conn.execute("SELECT id, request_type_code, status, created_by_employee_id, beneficiary_employee_id, chat_session_id, row_version FROM request WHERE id = %s"
                       + (" FOR UPDATE" if lock else ""), (request_id,)).fetchone()
    if row is None or row[3] != me:
        raise NotOwnRequest
    return RequestRow(*row)


def slot_data_reopened(conn: psycopg.Connection, request_id: uuid.UUID) -> bool:
    """Ca `SLOT_DATA` của `CHANGES_REQUESTED` (O1-15): quyết định **mới nhất** của `document` thuộc `request` là `CHANGES_REQUESTED` với `change_scope = SLOT_DATA` — người duyệt trả về vì dữ liệu `HR_PROFILE`
    sai, nhân viên phải xác nhận lại. Quyết định mới hơn (kể cả `RESUBMITTED`) làm vị từ sai; `FREE_CONTENT` là việc của agent, không phải của nhân viên. Không có `document` thì sai. Chỉ đọc."""
    row = conn.execute("SELECT x.kind, x.change_scope FROM decision_record x JOIN document d ON d.id = x.document_id WHERE d.request_id = %s ORDER BY x.created_at DESC, x.id DESC LIMIT 1",
                       (request_id,)).fetchone()
    return row is not None and tuple(row) == ("CHANGES_REQUESTED", "SLOT_DATA")


def require_editable(conn: psycopg.Connection, row: RequestRow) -> None:
    if row.status in EDITABLE_STATUSES:
        return
    if row.status == "CHANGES_REQUESTED" and slot_data_reopened(conn, row.id):
        return
    raise NotEditable(row.status)


def jsonb(value: Any) -> Jsonb:
    return Jsonb(value)
