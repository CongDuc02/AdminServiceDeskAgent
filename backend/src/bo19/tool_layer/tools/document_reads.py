"""Năm phép đọc nhỏ cho `document_graph` (B9a, ADR-039) — chỉ tác nhân hệ thống, giao dịch `READ ONLY`, kết quả chỉ mang id, mã, tên, số: **không** văn bản biến, không giá trị slot.

- `request_header_read` — loại và trạng thái của một `request` (lớp chạy graph cần loại để chọn template);
- `document_header_read` — phiên bản template đã ghim, vòng, trạng thái, chế độ của một `document` (node đọc lại từ DB thay vì tin state);
- `free_content_attempts_read` — mỗi biến đã có những lần sinh nào ở một vòng và kết quả (không đọc `body`): để thử lại job không sinh lại biến đã `PASSED` và không vượt hai lần sinh;
- `decision_record_read` — một `decision_record` thuộc đúng `document` (cho `route_review`; `route_review` đọc quyết định từ DB, không từ payload resume);
- `request_res_slots_read` — giá trị các slot `RES` kiểu chuỗi, **chỉ** cho `validate_free_content` so nguyên văn (kênh duy nhất đưa giá trị `RES` vào bộ nhớ của node; không vào state, log hay lỗi).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_system
from bo19.tool_layer.tools._common import ToolError


class RequestNotFound(ToolError):
    code = "REQUEST_NOT_FOUND"


class DocumentNotFound(ToolError):
    code = "DOCUMENT_NOT_FOUND"


class DecisionNotFound(ToolError):
    code = "DECISION_NOT_FOUND"  # không có, hoặc không thuộc `document` này — cùng một mã


@dataclass(frozen=True)
class RequestHeader:
    request_type_code: str
    status: str


@dataclass(frozen=True)
class DocumentHeader:
    document_id: uuid.UUID
    request_id: uuid.UUID
    template_version_id: uuid.UUID
    revision_round: int
    status: str
    operating_mode: str


@dataclass(frozen=True)
class DecisionRead:
    kind: str
    change_scope: str | None
    change_targets: tuple[str, ...]


def request_header_read(pool: Pool, ctx: ToolContext, *, request_id: uuid.UUID) -> RequestHeader:
    require_system(ctx)
    with pool.acquire() as conn, read_only(conn):
        row = conn.execute("SELECT request_type_code, status FROM request WHERE id = %s", (request_id,)).fetchone()
    if row is None:
        raise RequestNotFound
    return RequestHeader(row[0], row[1])


def document_header_read(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID) -> DocumentHeader:
    require_system(ctx)
    with pool.acquire() as conn, read_only(conn):
        row = conn.execute("SELECT id, request_id, template_version_id, revision_round, status, operating_mode FROM document WHERE id = %s", (document_id,)).fetchone()
    if row is None:
        raise DocumentNotFound
    return DocumentHeader(*row)


def free_content_attempts_read(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID, revision_round: int) -> dict[str, tuple[tuple[int, str], ...]]:
    """{tên biến: ((lần sinh, kết quả), …)} theo thứ tự lần sinh — chỉ các biến đã có ít nhất một lần ở vòng này."""
    require_system(ctx)
    with pool.acquire() as conn, read_only(conn):
        rows = conn.execute("SELECT variable_name, attempt_no, validation_outcome FROM document_free_content WHERE document_id = %s AND revision_round = %s ORDER BY variable_name, attempt_no",
                            (document_id, revision_round)).fetchall()
    out: dict[str, list[tuple[int, str]]] = {}
    for name, attempt, outcome in rows:
        out.setdefault(name, []).append((attempt, outcome))
    return {k: tuple(v) for k, v in out.items()}


def decision_record_read(pool: Pool, ctx: ToolContext, *, decision_record_id: uuid.UUID, document_id: uuid.UUID) -> DecisionRead:
    require_system(ctx)
    with pool.acquire() as conn, read_only(conn):
        row = conn.execute("SELECT kind, change_scope, change_targets FROM decision_record WHERE id = %s AND document_id = %s", (decision_record_id, document_id)).fetchone()
    if row is None:
        raise DecisionNotFound
    return DecisionRead(row[0], row[1], tuple(row[2] or ()))


def request_res_slots_read(pool: Pool, ctx: ToolContext, *, request_id: uuid.UUID) -> dict[str, str]:
    """Giá trị các slot `RES` (kiểu chuỗi) còn hiệu lực của một `request` — **chỉ cho `validate_free_content`** so nguyên văn (mục Output validation trước khi render của 09-security.md): một biến nội dung tự do
    không được chứa nguyên văn giá trị của một slot `RES` ngoài input đã khai của nó. Giá trị đi vào bộ nhớ của lần chạy rồi bị bỏ; không vào state, log hay lỗi."""
    require_system(ctx)
    with pool.acquire() as conn, read_only(conn):
        rows = conn.execute("SELECT s.slot_name, s.value FROM request_slot s JOIN slot_definition sd ON sd.request_type_code = s.request_type_code AND sd.slot_name = s.slot_name "
                            "WHERE s.request_id = %s AND sd.sensitivity = 'RES' AND s.value IS NOT NULL AND s.value_status <> 'ERASED'", (request_id,)).fetchall()
    return {name: value for name, value in rows if isinstance(value, str)}
