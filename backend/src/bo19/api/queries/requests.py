"""Truy vấn của nhóm Request — chỉ qua `persistence.read` (mọi giao dịch `READ ONLY`). Mục Request của 05-api.md (đoạn Triển khai ở B7); mục Phân trang
(`scope=OWN`: `created_at` giảm dần, `id` giảm dần, index `ix_request_created_by`).

**Sprint 1 chỉ có vế người tạo:** mọi hàm nhận `employee_id` của người đang đăng nhập và chỉ trả `request` **do chính họ tạo** — không tồn tại và của người khác cho cùng kết quả `None`
(`NOT_FOUND`, không lộ sự tồn tại). `submit_ready`, `missing_slots`, `unconfirmed_slots`, `failed_rules` tính bằng **đúng hàm kiểm** F1 qua `tool_layer.checks` — không có nguồn thứ hai.
Giá trị slot đi kèm `sensitivity`; contract không che giá trị với người được xem (mục Dữ liệu trong response của 05-api.md) — người tạo xem yêu cầu của chính mình.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import uuid
from typing import Any

import psycopg

from bo19.domain.status_labels import request_status_label
from bo19.persistence.read import read_only
from bo19.tool_layer.checks.eligibility import check_request


class BadCursor(Exception):
    code = "BAD_CURSOR"


_SUMMARY = (
    "SELECT r.id, r.request_type_code, t.name_vi, r.status, r.status_changed_at, r.created_at, r.created_by_employee_id, r.chat_session_id, r.row_version, "
    "b.id, b.employee_code, b.full_name, r.submitted_at, r.expires_at "
    "FROM request r JOIN request_type t ON t.code = r.request_type_code JOIN employee b ON b.id = r.beneficiary_employee_id"
)


def _summary(row: tuple) -> dict[str, Any]:
    """`RequestSummary` của Sprint 1: `artifacts` luôn `[]` vì chưa có `document` (B9)."""
    (rid, type_code, type_name, status, changed, created, creator, session, version, b_id, b_code, b_name, submitted, expires) = row
    return {"id": rid, "request_type_code": type_code, "request_type_name": type_name, "status": status, "status_label": request_status_label(status),
            "status_changed_at": changed, "created_at": created, "created_by_employee_id": creator, "beneficiary": {"id": b_id, "employee_code": b_code, "full_name": b_name},
            "chat_session_id": session, "submitted_at": submitted, "expires_at": expires, "row_version": version, "artifacts": []}


def request_summary(conn: psycopg.Connection, request_id: uuid.UUID) -> dict[str, Any] | None:
    """Không lọc người xem — người gọi phải đã biết `request` này thuộc phạm vi của họ (lượt chat của chính họ, hay `decision_record` của chính họ)."""
    with read_only(conn):
        row = conn.execute(_SUMMARY + " WHERE r.id = %s", (request_id,)).fetchone()
    return _summary(row) if row else None


def own_request_summary(conn: psycopg.Connection, request_id: uuid.UUID, employee_id: uuid.UUID) -> dict[str, Any] | None:
    with read_only(conn):
        row = conn.execute(_SUMMARY + " WHERE r.id = %s AND r.created_by_employee_id = %s", (request_id, employee_id)).fetchone()
    return _summary(row) if row else None


# ---------------------------------------------------------------------------------------------------------------------------- danh sách


def encode_cursor(created_at: dt.datetime, request_id: uuid.UUID, filt: str) -> str:
    """Cursor mờ: bộ khoá của dòng cuối (`created_at`, `id`) cộng bộ lọc đã dùng — dùng với bộ lọc khác thì `BadCursor` (mục Phân trang của 05-api.md)."""
    raw = {"c": created_at.isoformat(), "i": str(request_id), "f": filt}
    return base64.urlsafe_b64encode(json.dumps(raw, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(cursor: str, filt: str) -> tuple[dt.datetime, uuid.UUID]:
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if not isinstance(raw, dict) or raw.get("f") != filt:
            raise BadCursor
        created = dt.datetime.fromisoformat(raw["c"])
        if created.tzinfo is None:
            raise BadCursor
        return created, uuid.UUID(raw["i"])
    except (ValueError, KeyError, TypeError, AttributeError):
        raise BadCursor from None


def list_own(conn: psycopg.Connection, employee_id: uuid.UUID, *, status: str | None, limit: int, cursor: str | None) -> tuple[list[dict[str, Any]], str | None]:
    """`scope=OWN`: yêu cầu do mình tạo, mới nhất trước. `next_cursor` là `None` khi hết."""
    filt = f"OWN:{status or ''}"
    after = decode_cursor(cursor, filt) if cursor else None
    where, params = ["r.created_by_employee_id = %s"], [employee_id]
    if status:
        where.append("r.status = %s")
        params.append(status)
    if after:
        where.append("(r.created_at, r.id) < (%s, %s)")
        params.extend(after)
    with read_only(conn):
        rows = conn.execute(_SUMMARY + " WHERE " + " AND ".join(where) + " ORDER BY r.created_at DESC, r.id DESC LIMIT %s", (*params, limit + 1)).fetchall()
    items = [_summary(r) for r in rows[:limit]]
    last = items[-1] if items and len(rows) > limit else None
    return items, (encode_cursor(last["created_at"], last["id"], filt) if last else None)


# ---------------------------------------------------------------------------------------------------------------------------- chi tiết

_SLOTS = (
    "SELECT d.slot_name, d.label_vi, d.description, d.data_type, d.source, d.sensitivity, d.is_required, "
    "s.value, s.value_status, s.provenance_source, s.provenance_synced_at, s.proposed_from_request_id, s.confirmed_at, s.row_version "
    "FROM slot_definition d LEFT JOIN request_slot s ON s.request_id = %s AND s.slot_name = d.slot_name "
    "WHERE d.request_type_code = %s ORDER BY d.display_order, d.slot_name"
)


def _slot(row: tuple) -> dict[str, Any]:
    (name, label, description, data_type, source, sensitivity, required, value, value_status, prov_source, prov_synced, proposed_from, confirmed_at, version) = row
    erased = value_status == "ERASED"
    return {"slot_name": name, "label": label, "description": description, "data_type": data_type, "source": source, "sensitivity": sensitivity, "is_required": required,
            "value": None if erased else value, "value_status": value_status, "erased": erased,
            "provenance": {"source": prov_source, "synced_at": prov_synced} if prov_source is not None else None,
            "proposed_from_request_id": proposed_from, "confirmed_at": confirmed_at, "row_version": version}


def own_request_detail(conn: psycopg.Connection, request_id: uuid.UUID, employee_id: uuid.UUID) -> dict[str, Any] | None:
    """`RequestDetail` của người tạo; `None` nếu không phải yêu cầu của người này. Mọi phần đọc trong MỘT giao dịch chỉ đọc — một ảnh nhất quán."""
    with read_only(conn):
        row = conn.execute(_SUMMARY + " WHERE r.id = %s AND r.created_by_employee_id = %s", (request_id, employee_id)).fetchone()
        if row is None:
            return None
        detail = _summary(row)
        slots = [_slot(r) for r in conn.execute(_SLOTS, (request_id, detail["request_type_code"])).fetchall()]
        check = check_request(conn, request_id)
    return {**detail, "slots": slots, "missing_slots": list(check.missing_slots), "unconfirmed_slots": list(check.unconfirmed_slots),
            "failed_rules": [{"slot_name": s, "rule_code": c} for s, c in check.failed_rules], "submit_ready": check.eligible,
            "changes_requested": None, "documents": []}  # hai trường cuối có giá trị khi có `document` (B9)


def own_decision(conn: psycopg.Connection, decision_id: uuid.UUID, employee_id: uuid.UUID) -> tuple[str, dt.datetime, uuid.UUID] | None:
    """(kind, created_at, request_id) của một `decision_record` do chính người này ghi — cho `DecisionResult`."""
    with read_only(conn):
        row = conn.execute("SELECT kind, created_at, request_id FROM decision_record WHERE id = %s AND actor_employee_id = %s", (decision_id, employee_id)).fetchone()
    return (row[0], row[1], row[2]) if row else None
