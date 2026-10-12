"""Đọc cấu hình loại yêu cầu cho node của `intake_graph` — catalog cho P1, `slot_specs` cho P2, nhãn tiếng Việt cho khuôn (mục Triển khai ở B6b của 06-structure.md).

Không phải tool: cùng khuôn `check_request` — hàm đọc cấu hình **hiện hành** từ DB, giao dịch `READ ONLY`, nhận `Pool`. Mọi giá trị ở đây là cấu hình (INT), không phải dữ liệu của nhân viên.
`load_catalog` đúng năm trường mà `catalog_fingerprint` hash (mục Phiên bản và thay đổi của 07-prompts.md): `code`, `support_status`, `name_vi`, `description`, `example_phrases`.
"""
from __future__ import annotations

import uuid
from typing import Any

from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
from bo19.tool_layer.checks.eligibility import RequestCheck, check_request


def load_catalog(pool: Pool) -> list[dict[str, Any]]:
    with pool.acquire() as conn, read_only(conn):
        rows = conn.execute("SELECT code, support_status, name_vi, description, example_phrases FROM request_type ORDER BY code").fetchall()
    return [{"code": c, "support_status": s, "name_vi": n, "description": d, "example_phrases": list(e)} for c, s, n, d, e in rows]


def slot_specs(pool: Pool, request_type_code: str) -> list[dict[str, str]]:
    """Slot `USER_INPUT` của loại yêu cầu — đầu vào `slot_specs` của P2 (tên, kiểu, mô tả viết cho LLM). Slot `HR_PROFILE`/`SYSTEM` không có ở đây: P2 không được trả chúng."""
    with pool.acquire() as conn, read_only(conn):
        rows = conn.execute("SELECT slot_name, data_type, description FROM slot_definition WHERE request_type_code = %s AND source = 'USER_INPUT' ORDER BY display_order, slot_name",
                            (request_type_code,)).fetchall()
    return [{"slot_name": n, "data_type": t, "description": d} for n, t, d in rows]


def slot_labels(pool: Pool, request_type_code: str) -> dict[str, str]:
    """`slot_definition.label_vi` — chữ người dùng đọc được (`proposals/reply-templates.md`, S1)."""
    with pool.acquire() as conn, read_only(conn):
        rows = conn.execute("SELECT slot_name, label_vi FROM slot_definition WHERE request_type_code = %s", (request_type_code,)).fetchall()
    return dict(rows)


def type_names(pool: Pool, *, supported_only: bool = False) -> dict[str, str]:
    """`request_type.name_vi` theo mã — mọi loại, hoặc chỉ loại đang hỗ trợ (danh sách "hiện mình hỗ trợ" của khuôn)."""
    with pool.acquire() as conn, read_only(conn):
        rows = conn.execute("SELECT code, name_vi FROM request_type" + (" WHERE support_status = 'SUPPORTED'" if supported_only else "") + " ORDER BY code").fetchall()
    return dict(rows)


def check_completeness(pool: Pool, request_id: uuid.UUID) -> RequestCheck:
    """Hàm F1 trên dữ liệu hiện hành — **đúng hàm** mà `request_slot_confirm` và `request_submit` dùng (`check_request`)."""
    with pool.acquire() as conn, read_only(conn):
        return check_request(conn, request_id)
