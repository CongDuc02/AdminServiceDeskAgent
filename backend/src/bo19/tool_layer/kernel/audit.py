"""Ghi `audit_event` — trong **cùng giao dịch** với thao tác sinh ra nó (luật `audit_event`, A-055 hướng 1, ở mục Tool Registry của 03-agents.md).

`record(conn, ctx, …)` đòi `conn` đang trong giao dịch (`require_transaction`): thao tác lăn thì `audit_event` lăn theo — không có dòng kiểm toán cho việc không xảy ra, không có việc
xảy ra mà thiếu dòng. Bảng chỉ thêm với `bo19_app` (không `UPDATE`, không `DELETE`).

**Payload chỉ mang mã và tham chiếu, không mang văn bản** (mục Bảng chi tiết của 04-data.md; NFR-05): khoá là tên `snake_case`; giá trị là số nguyên, boolean, `null`, hoặc chuỗi ngắn
**không có khoảng trắng** (mã enum, tên slot, id, mốc thời gian ISO); lồng tối đa ba tầng. Văn bản tự do — một tên riêng, một câu của nhân viên, một đoạn do LLM sinh — có khoảng trắng
hoặc dài hơn 64 ký tự nên bị từ chối. **Chỗ hở còn lại, nói thẳng:** một giá trị ngắn không khoảng trắng (một mã số) vẫn lọt qua; kiểm này chặn văn bản tự do, không chặn một lập trình
viên truyền nhầm một mã. Mask theo `slot_sensitivity` là việc của chỗ gọi (giá trị slot không bao giờ vào đây — chỉ tên slot).
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import psycopg

from bo19.tool_layer.kernel.context import KernelError, ToolContext, require_transaction

_ACTION = re.compile(r"^[a-z_]+\.[a-z_]+$")  # khớp ck_audit_event_action
_ENTITY_TYPE = re.compile(r"^[a-z][a-z_]*$")  # khớp ck_audit_event_entity_type
_ENTITY_ID = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_SCALAR = re.compile(r"^[A-Za-z0-9_.:+\-/]{0,64}$")  # không khoảng trắng, không dấu: mã, id, ISO 8601
MAX_DEPTH, MAX_ITEMS, MAX_BYTES = 3, 50, 4096
SEVERITIES = ("INFO", "WARNING")  # danh sách đóng ở GLOSSARY.md, mục audit_severity; ba ca dùng WARNING do chỗ gọi chịu trách nhiệm


class AuditInvalid(KernelError):
    """Dòng kiểm toán sai hình dạng — lỗi lập trình, không phải lỗi nghiệp vụ."""

    code = "AUDIT_INVALID"


def check_payload(value: Any, *, _depth: int = 1) -> Any:
    """Kiểm một payload chỉ-tham-chiếu (dùng cho cả `audit_event.payload` và `job.payload`); trả bản chuẩn hoá JSON. Lỗi chỉ nêu đường dẫn, không nêu giá trị."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str):
        if not _SCALAR.match(value):
            raise AuditInvalid("text")
        return value
    if isinstance(value, (list, tuple, dict)) and _depth > MAX_DEPTH:
        raise AuditInvalid("depth")  # tối đa ba tầng danh sách/từ điển lồng nhau
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_ITEMS:
            raise AuditInvalid("items")
        return [check_payload(v, _depth=_depth + 1) for v in value]
    if isinstance(value, dict):
        if len(value) > MAX_ITEMS:
            raise AuditInvalid("items")
        out = {}
        for k, v in value.items():
            if not isinstance(k, str) or not _KEY.match(k):
                raise AuditInvalid("key")
            out[k] = check_payload(v, _depth=_depth + 1)
        return out
    raise AuditInvalid("type")  # float, bytes, đối tượng lạ


def record(conn: psycopg.Connection, ctx: ToolContext, *, action: str, entity_type: str, entity_id: str | uuid.UUID, request_id: uuid.UUID | None = None,
           document_id: uuid.UUID | None = None, decision_record_id: uuid.UUID | None = None, payload: dict[str, Any] | None = None, severity: str = "INFO") -> uuid.UUID:
    """Một dòng `audit_event` trong giao dịch hiện tại của `conn`. Trả id."""
    require_transaction(conn)
    if not _ACTION.match(action):
        raise AuditInvalid("action")
    if not _ENTITY_TYPE.match(entity_type):
        raise AuditInvalid("entity_type")
    entity = str(entity_id)
    if not _ENTITY_ID.match(entity):
        raise AuditInvalid("entity_id")
    if severity not in SEVERITIES:
        raise AuditInvalid("severity")
    body = check_payload(payload or {})
    if not isinstance(body, dict):
        raise AuditInvalid("payload")
    text = json.dumps(body, ensure_ascii=True, separators=(",", ":"))
    if len(text) > MAX_BYTES:
        raise AuditInvalid("size")
    event_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO audit_event (id, actor_kind, actor_employee_id, action, severity, entity_type, entity_id, request_id, document_id, decision_record_id, payload, trace_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)",
        (event_id, ctx.actor.kind, ctx.actor.employee_id, action, severity, entity_type, entity, request_id, document_id, decision_record_id, text, ctx.trace_id))
    return event_id
