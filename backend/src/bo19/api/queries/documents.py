"""Truy vấn của nhóm Văn bản — chỉ qua `persistence.read` (mọi giao dịch `READ ONLY`). Mục Hàng đợi và văn bản của 05-api.md; mục Hàng đợi của 08-hitl.md (B9b1).

**Phạm vi thấy được** (mục 3.4 của 09-security.md): `request.read_all` thấy mọi văn bản; chỉ có `request.read_assigned` thì chỉ thấy văn bản có `approval_step` giao cho chính mình (`OPEN` hoặc `DECIDED`).
Không thấy được thì như không tồn tại — `None`, router đổi thành `NOT_FOUND`.

**Cờ dẫn xuất** (không có cột riêng — quy ước cờ dẫn xuất, mục 1.2 của 04-data.md): `halted` = có bước `TAKEOVER` `OPEN`; `issue_in_progress` = có lệnh `ISSUE_ORDERED` mà `document` chưa `ISSUED` và lệnh chưa bỏ cuộc (số `VOIDED`
hay `document_halt` tại `finalize_issue` sau lệnh — mục 4.4 của 04-data.md); `job_failed` = job `resume_document_graph` / `finalize_issue` MỚI NHẤT của `document` đã `FAILED`.
`document_number` chỉ từ `ISSUED` trở đi (mục Dữ liệu trong response của 05-api.md).
"""
from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import psycopg

from bo19.api.queries import _doc_flags as flags
from bo19.api.queries import requests as request_queries
from bo19.domain.status_labels import document_status_label
from bo19.persistence.read import read_only
from bo19.tool_layer.tools.render_values import build_values

BadCursor = request_queries.BadCursor

_HALTED = "EXISTS (SELECT 1 FROM approval_step h WHERE h.document_id = d.id AND h.step_kind = 'TAKEOVER' AND h.status = 'OPEN')"
_ORDER = flags.ORDER
_JOB = ("SELECT j.status, j.last_error_code FROM job j WHERE j.subject_document_id = d.id AND j.job_type IN ('resume_document_graph', 'finalize_issue') "
        "ORDER BY j.enqueued_at DESC, j.id DESC LIMIT 1")
_ISSUE_IN_PROGRESS = flags.ISSUE_IN_PROGRESS
_ASSIGNED_TO_ME = "EXISTS (SELECT 1 FROM approval_step s WHERE s.document_id = d.id AND s.assignee_employee_id = %s AND s.status <> 'CANCELLED')"

_BASE = (
    "SELECT d.id, d.request_id, r.request_type_code, d.status, d.status_changed_at, d.revision_round, d.operating_mode, d.requires_seal, d.seal_type, "
    f"{_ISSUE_IN_PROGRESS}, {_HALTED}, (j.status = 'FAILED'), CASE WHEN j.status = 'FAILED' THEN j.last_error_code END, "
    "CASE WHEN d.status IN ('ISSUED', 'REVOKED', 'SUPERSEDED', 'ARCHIVED') THEN e.formatted_number END, d.issued_date, d.row_version, "
    "t.name_vi, b.id, b.employee_code, b.full_name "
    "FROM document d JOIN request r ON r.id = d.request_id JOIN request_type t ON t.code = r.request_type_code JOIN employee b ON b.id = r.beneficiary_employee_id "
    "LEFT JOIN document_register_entry e ON e.id = d.issued_register_entry_id "
    f"LEFT JOIN LATERAL ({_ORDER}) o ON true LEFT JOIN LATERAL ({_JOB}) j ON true"
)


def _summary(row: tuple) -> dict[str, Any]:
    (doc_id, request_id, type_code, status, changed, round_, mode, requires_seal, seal_type, issue_in_progress, halted, job_failed, job_failed_code, number, issued_date, version) = row[:16]
    return {"id": doc_id, "request_id": request_id, "request_type_code": type_code, "status": status, "status_label": document_status_label(status, bool(issue_in_progress)),
            "status_changed_at": changed, "revision_round": round_, "operating_mode": mode, "requires_seal": requires_seal, "seal_type": seal_type,
            "issue_in_progress": bool(issue_in_progress), "halted": bool(halted), "job_failed": bool(job_failed), "job_failed_code": job_failed_code if job_failed else None,
            "document_number": number, "issued_date": issued_date, "row_version": version}


def _item(row: tuple) -> dict[str, Any]:
    return {"document": _summary(row), "request_type_name": row[16], "beneficiary": {"id": row[17], "employee_code": row[18], "full_name": row[19]}}


def document_summary(conn: psycopg.Connection, document_id: uuid.UUID) -> dict[str, Any] | None:
    """`DocumentSummary` — không lọc người xem (người gọi vừa ghi quyết định lên văn bản này)."""
    with read_only(conn):
        row = conn.execute(_BASE + " WHERE d.id = %s", (document_id,)).fetchone()
    return _summary(row) if row else None


def viewable(conn: psycopg.Connection, document_id: uuid.UUID, employee_id: uuid.UUID, *, read_all: bool, read_assigned: bool) -> bool:
    """Văn bản có tồn tại và người này thấy được không (mục 3.4 của 09-security.md). Không thấy được thì router không lộ sự tồn tại."""
    with read_only(conn):
        if not read_all and not read_assigned:
            return False
        row = conn.execute("SELECT 1 FROM document d WHERE d.id = %s" + ("" if read_all else f" AND {_ASSIGNED_TO_ME}"), (document_id,) if read_all else (document_id, employee_id)).fetchone()
    return row is not None


# ---------------------------------------------------------------------------------------------------------------------------- hàng đợi


def _page(conn: psycopg.Connection, where: list[str], params: list[Any], *, filt: str, limit: int, cursor: str | None) -> tuple[list[dict[str, Any]], str | None]:
    """Keyset theo (`status_changed_at`, `id`) tăng dần — chờ lâu nhất trước (mục 2.2 của 08-hitl.md)."""
    if cursor:
        after = request_queries.decode_cursor(cursor, filt)
        where = [*where, "(d.status_changed_at, d.id) > (%s, %s)"]
        params = [*params, *after]
    with read_only(conn):
        rows = conn.execute(_BASE + " WHERE " + " AND ".join(where) + " ORDER BY d.status_changed_at, d.id LIMIT %s", (*params, limit + 1)).fetchall()
    items = [_item(r) for r in rows[:limit]]
    last = items[-1]["document"] if items and len(rows) > limit else None
    return items, (request_queries.encode_cursor(last["status_changed_at"], last["id"], filt) if last else None)


def review_queue(conn: psycopg.Connection, *, status: str, employee_id: uuid.UUID, read_all: bool, limit: int, cursor: str | None) -> tuple[list[dict[str, Any]], str | None]:
    """Hàng đợi MỘT trạng thái. `read_all=False` thì chỉ văn bản có bước giao cho `employee_id`."""
    filt = f"REVIEW:{status}:{'ALL' if read_all else 'ASSIGNED'}"
    where, params = ["d.status = %s"], [status]
    if not read_all:
        where.append(_ASSIGNED_TO_ME)
        params.append(employee_id)
    return _page(conn, where, params, filt=filt, limit=limit, cursor=cursor)


def issue_queue(conn: psycopg.Connection, *, limit: int, cursor: str | None) -> tuple[list[dict[str, Any]], str | None]:
    """`SIGNED` không cần dấu hoặc `SEALED`; chưa có lệnh phát hành; không đang dừng chờ tiếp quản (mục 2.1 của 08-hitl.md). Theo `ix_document_awaiting_issue`."""
    where = ["(d.status = 'SEALED' OR (d.status = 'SIGNED' AND d.requires_seal IS FALSE))", "o.id IS NULL", f"NOT {_HALTED}"]
    return _page(conn, where, [], filt="ISSUE", limit=limit, cursor=cursor)


# ---------------------------------------------------------------------------------------------------------------------------- màn hình duyệt


def document_review_view(conn: psycopg.Connection, document_id: uuid.UUID, employee_id: uuid.UUID, *, read_all: bool, read_assigned: bool) -> dict[str, Any] | None:
    """`DocumentReviewView`; `None` nếu không tồn tại **hoặc** người này không thấy được. Mọi phần đọc trong MỘT giao dịch chỉ đọc. Giá trị biến trả đủ kèm `sensitivity` (mục Dữ liệu trong response của 05-api.md);
    ẩn `RES` là việc của client (mục PII masking của 09-security.md)."""
    if not read_all and not read_assigned:
        return None
    with read_only(conn):
        row = conn.execute(_BASE + " WHERE d.id = %s", (document_id,)).fetchone()
        if row is None:
            return None
        if not read_all and not conn.execute("SELECT EXISTS (SELECT 1 FROM approval_step s WHERE s.document_id = %s AND s.assignee_employee_id = %s AND s.status <> 'CANCELLED')",
                                             (document_id, employee_id)).fetchone()[0]:
            return None
        summary = _summary(row)
        request = request_queries.request_summary_in(conn, summary["request_id"])
        d = conn.execute("SELECT template_version_id, current_draft_render_id, approved_render_id, final_render_id FROM document WHERE id = %s", (document_id,)).fetchone()
        tv = conn.execute("SELECT t.id, t.code, v.id, v.version_no FROM template_version v JOIN template t ON t.id = v.template_id WHERE v.id = %s", (d[0],)).fetchone()
        built = build_values(conn, document_id)
        vars_ = conn.execute(
            "SELECT v.variable_name, v.kind, v.source_slot_name, v.fill_after_approval, sd.source, sd.sensitivity, s.value_status, s.provenance_source, s.provenance_synced_at "
            "FROM template_variable v LEFT JOIN slot_definition sd ON sd.request_type_code = %s AND sd.slot_name = v.source_slot_name "
            "LEFT JOIN request_slot s ON s.request_id = %s AND s.slot_name = v.source_slot_name WHERE v.template_version_id = %s ORDER BY v.variable_name",
            (summary["request_type_code"], summary["request_id"], d[0])).fetchall()
        renders = conn.execute("SELECT r.id, r.render_kind, r.revision_round, r.template_version_id, r.created_at, p.pin_reason FROM document_render r "
                               "LEFT JOIN document_render_pin p ON p.render_id = r.id WHERE r.document_id = %s ORDER BY r.created_at, r.id", (document_id,)).fetchall()
        steps = conn.execute("SELECT id, step_kind, level, revision_round, status, assignee_employee_id, opened_at, closed_at, self_approval_expected, self_approved, self_approval_reason "
                             "FROM approval_step WHERE document_id = %s ORDER BY opened_at, id", (document_id,)).fetchall()
        decisions = conn.execute("SELECT x.id, x.kind, x.delegation_id, x.created_at, x.change_scope, x.change_targets, a.id, a.employee_code, a.full_name FROM decision_record x "
                                 "JOIN employee a ON a.id = x.actor_employee_id WHERE x.document_id = %s ORDER BY x.created_at, x.id", (document_id,)).fetchall()
        texts = conn.execute("SELECT decision_record_id, text_kind, body FROM decision_record_text WHERE decision_record_id = ANY(%s) ORDER BY text_kind", ([x[0] for x in decisions],)).fetchall() if decisions else []
    by_decision: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for decision_id, text_kind, body in texts:
        by_decision.setdefault(decision_id, []).append({"text_kind": text_kind, "body": body, "erased": False})
    variables = []
    for name, kind, source_slot, after, slot_source, sensitivity, value_status, prov_source, prov_synced in vars_:
        erased = value_status == "ERASED"
        variables.append({"variable_name": name, "kind": kind, "value": None if (kind == "SYSTEM" or erased) else built.values.get(name), "value_erased": erased, "source_slot_name": source_slot,
                          "slot_source": slot_source, "sensitivity": sensitivity, "provenance": {"source": prov_source, "synced_at": prov_synced} if prov_source is not None else None,
                          "fill_after_approval": after})
    return {"document": summary, "request": request, "template": {"template_id": tv[0], "template_code": tv[1], "template_version_id": tv[2], "version_no": tv[3]},
            "variables": variables,
            "renders": [{"id": r[0], "render_kind": r[1], "revision_round": r[2], "template_version_id": r[3], "created_at": r[4], "pin_reason": r[5]} for r in renders],
            "current_draft_render_id": d[1], "approved_render_id": d[2], "final_render_id": d[3],
            "approval_steps": [{"id": s[0], "step_kind": s[1], "level": s[2], "revision_round": s[3], "status": s[4], "assignee_employee_id": s[5], "opened_at": s[6], "closed_at": s[7],
                                "self_approval_expected": s[8], "self_approved": s[9], "self_approval_reason": s[10]} for s in steps],
            "decisions": [{"id": x[0], "kind": x[1], "actor": {"id": x[6], "employee_code": x[7], "full_name": x[8]}, "delegation_id": x[2], "created_at": x[3], "change_scope": x[4],
                           "change_targets": list(x[5]) if x[5] is not None else None, "texts": by_decision.get(x[0], [])} for x in decisions],
            "latest_halt": None}
