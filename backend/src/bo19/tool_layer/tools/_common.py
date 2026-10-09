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


EDITABLE_STATUSES = frozenset({"DRAFT", "NEEDS_INFO"})  # CHANGES_REQUESTED ca SLOT_DATA mở khi có document_graph (chưa xác định được ca ở B6a)


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


def require_editable(row: RequestRow) -> None:
    if row.status not in EDITABLE_STATUSES:
        raise NotEditable(row.status)


def jsonb(value: Any) -> Jsonb:
    return Jsonb(value)
