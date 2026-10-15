"""Dựng bảng giá trị biến cho một bản render nháp, và các điều kiện "đủ điều kiện trình duyệt" (F2) tính trên chính bảng đó (B9a; mục Tool Registry của 03-agents.md; ADR-039; A-098).

Một hàm, hai việc: `build_values(conn, document_id)` trả (a) `values` — bảng giá trị biến cho `docx_render`, **chỉ gồm biến có giá trị dùng được** (biến không dựng được thì vắng mặt, nên `docx_render` ném `MISSING_VARIABLE`
thay vì điền chỗ trống), và (b) `issues` — danh sách (mã, tên biến) theo định nghĩa F2. `review_readiness_check` là `issues` rỗng; `render_draft` dùng `values`. Cùng một nguồn nên "bản đã render" và "bản đã kiểm" không lệch nhau.

Nguồn của từng loại biến:
- `DIRECT_SLOT` — giá trị slot nguồn: `HR_PROFILE` phải `CONFIRMED`, `USER_INPUT` phải `PROVIDED`/`CONFIRMED`, `SYSTEM` phải `SYSTEM_SET` (cùng bảng chấp nhận với `domain.eligibility`); trạng thái khác là `WRONG_SOURCE`
  ("agent tự đặt giá trị cho biến chưa xác nhận" — F2), vắng hay `ERASED` là `VARIABLE_MISSING`. Định dạng theo kiểu slot: `STRING`/`TEXT` nguyên văn, `INT` số nguyên, `DATE` `dd/mm/yyyy` (A-098);
  kiểu khác (`ENUM`, `LIST`, `BOOL`, `FILE`) chưa hỗ trợ — biến vắng mặt, mã `VARIABLE_MISSING` (câu chữ theo loại hợp đồng là việc của đoạn điều kiện của template thật, M1.1).
- `FREE_CONTENT` — dòng `document_free_content` `PASSED` hiện hành (vòng lớn nhất, rồi lần sinh lớn nhất); vắng là `VARIABLE_MISSING`.
- `SYSTEM` — chỉ biến mang cờ *điền sau duyệt* (INV-01: `document_number`, `issued_date`, `signer_user_id`…): bản nháp hiện dấu giữ chỗ nhìn ra ngay là chưa chính thức — `provisional.marker_for(tên)`, ví dụ `[Số văn bản — cấp khi phát hành]` (A-098, PO 2026-10-15) — **không** qua kiểm "không placeholder" và không vào
  `approved_content_hash`. `SYSTEM` không mang cờ thì chưa có nguồn ở B9a: vắng mặt, `VARIABLE_MISSING`.

Điều kiện cấp văn bản: `SEAL_UNDETERMINED` (`requires_seal` chưa xác định, hoặc cần dấu mà thiếu `seal_type`); `TEMPLATE_NOT_ACTIVE_AT_RENDER` (phiên bản đã ghim không còn `ACTIVE`).

Giá trị không bao giờ vào log, `audit_event` hay lỗi; `BuiltValues.__repr__` không in chúng.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

import psycopg

from bo19.domain import free_content, provisional
from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_system
from bo19.tool_layer.tools._common import ToolError
from bo19.tool_layer.tools.template_fetch import read_version

VARIABLE_MISSING = "VARIABLE_MISSING"
PLACEHOLDER_VALUE = "PLACEHOLDER_VALUE"
WRONG_SOURCE = "WRONG_SOURCE"
FRAME_TEXT_IN_VARIABLE = "FRAME_TEXT_IN_VARIABLE"
SEAL_UNDETERMINED = "SEAL_UNDETERMINED"
TEMPLATE_NOT_ACTIVE_AT_RENDER = "TEMPLATE_NOT_ACTIVE_AT_RENDER"

_ACCEPTED = {"USER_INPUT": frozenset({"PROVIDED", "CONFIRMED"}), "HR_PROFILE": frozenset({"CONFIRMED"}), "SYSTEM": frozenset({"SYSTEM_SET"})}
_OTHER = frozenset({"PROVIDED", "CONFIRMED", "SYSTEM_SET"})


class DocumentNotFound(ToolError):
    code = "DOCUMENT_NOT_FOUND"


@dataclass(frozen=True)
class Issue:
    code: str
    variable: str | None = None  # tên biến (cấu hình) — không phải giá trị


@dataclass(frozen=True)
class BuiltValues:
    document_id: uuid.UUID
    values: dict[str, str] = field(repr=False)
    issues: tuple[Issue, ...]

    def __repr__(self) -> str:
        return f"BuiltValues(document_id={self.document_id}, variables={sorted(self.values)}, issues={[i.code for i in self.issues]})"

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(sorted({i.code for i in self.issues}))


def _format(data_type: str, value: Any) -> str | None:
    """Giá trị slot → chuỗi cho biến; `None` nếu kiểu chưa hỗ trợ hay giá trị không đúng kiểu."""
    if data_type in ("STRING", "TEXT"):
        return value if isinstance(value, str) else None
    if data_type == "INT":
        return str(value) if isinstance(value, int) and not isinstance(value, bool) else None
    if data_type == "DATE":
        try:
            return dt.date.fromisoformat(value).strftime("%d/%m/%Y") if isinstance(value, str) else None
        except ValueError:
            return None
    return None


def build_values(conn: psycopg.Connection, document_id: uuid.UUID) -> BuiltValues:
    doc = conn.execute("SELECT d.request_id, d.template_version_id, d.requires_seal, d.seal_type FROM document d WHERE d.id = %s", (document_id,)).fetchone()
    if doc is None:
        raise DocumentNotFound
    request_id, version_id, requires_seal, seal_type = doc
    template = read_version(conn, version_id)
    slots = {r[0]: r[1:] for r in conn.execute(
        "SELECT s.slot_name, s.value, s.value_status, sd.source, sd.data_type, sd.sensitivity FROM request_slot s "
        "JOIN slot_definition sd ON sd.request_type_code = s.request_type_code AND sd.slot_name = s.slot_name WHERE s.request_id = %s", (request_id,)).fetchall()}
    free = {r[0]: r[1] for r in conn.execute(
        "SELECT DISTINCT ON (variable_name) variable_name, body FROM document_free_content WHERE document_id = %s AND validation_outcome = 'PASSED' "
        "ORDER BY variable_name, revision_round DESC, attempt_no DESC", (document_id,)).fetchall()}
    values: dict[str, str] = {}
    issues: list[Issue] = []

    def bad(code: str, variable: str) -> None:
        issues.append(Issue(code, variable))

    for v in template.variables:
        if v.kind == "DIRECT_SLOT":
            slot = slots.get(v.source_slot_name or "")
            if slot is None or slot[0] is None or slot[1] == "ERASED":
                bad(VARIABLE_MISSING, v.name)
                continue
            value, status, source, data_type, _sensitivity = slot
            if status not in _ACCEPTED.get(source, _OTHER):
                bad(WRONG_SOURCE, v.name)
                continue
            text = _format(data_type, value)
            if text is None:
                bad(VARIABLE_MISSING, v.name)  # kiểu chưa hỗ trợ hay giá trị sai kiểu — A-098
                continue
            if free_content.is_placeholder(text):
                bad(PLACEHOLDER_VALUE, v.name)
            values[v.name] = text
        elif v.kind == "FREE_CONTENT":
            body = free.get(v.name)
            if body is None:
                bad(VARIABLE_MISSING, v.name)
                continue
            if free_content.is_placeholder(body):
                bad(PLACEHOLDER_VALUE, v.name)
            if free_content.frame_phrase_in(body):
                bad(FRAME_TEXT_IN_VARIABLE, v.name)
            values[v.name] = body
        elif v.kind == "SYSTEM":
            if v.fill_after_approval:
                values[v.name] = provisional.marker_for(v.name)
            else:
                bad(VARIABLE_MISSING, v.name)
    if requires_seal is None or (requires_seal and not seal_type):
        issues.append(Issue(SEAL_UNDETERMINED))
    if template.status != "ACTIVE":
        issues.append(Issue(TEMPLATE_NOT_ACTIVE_AT_RENDER))
    return BuiltValues(document_id, values, tuple(issues))


def render_values_build(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID) -> BuiltValues:
    """Đọc trong một giao dịch `READ ONLY`. Chỉ tác nhân hệ thống."""
    require_system(ctx)
    with pool.acquire() as conn, read_only(conn):
        return build_values(conn, document_id)
