"""Tool `template_fetch` — lấy template đang hiệu lực của một `request_type` bằng **tra cứu chính xác**, không bằng vector search (F2; mục Tool Registry của 03-agents.md; ADR-039).

Hai hàm, cùng một kết quả: `template_fetch(request_type)` — phiên bản `ACTIVE` (phải ra **đúng một**; hai template cùng `request_type` đều `ACTIVE` là lỗi cấu hình, không chọn bừa) — và
`template_version_read(template_version_id)` — danh mục biến của một phiên bản đã ghim cho `document` (bất kể trạng thái: `document` đã ghim phiên bản lúc tạo `DRAFT`).

Danh mục biến mang tên biến, loại (`DIRECT_SLOT`/`FREE_CONTENT`/`SYSTEM`), slot nguồn, cờ *điền sau duyệt*, `variable_guidance`, `max_length` và danh sách slot input tự khai của biến nội dung tự do
(`template_variable_input` — danh sách nạp của INV-03). Chỉ tác nhân hệ thống; chỉ đọc (không `audit_event`).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_system
from bo19.tool_layer.tools._common import ToolError


class NoActiveTemplate(ToolError):
    code = "NO_ACTIVE_TEMPLATE"


class TemplateAmbiguous(ToolError):
    code = "TEMPLATE_AMBIGUOUS"  # hơn một template của loại này cùng có phiên bản `ACTIVE` — lỗi cấu hình


class TemplateVersionNotFound(ToolError):
    code = "TEMPLATE_VERSION_NOT_FOUND"


@dataclass(frozen=True)
class VariableInfo:
    name: str
    kind: str  # DIRECT_SLOT | FREE_CONTENT | SYSTEM
    source_slot_name: str | None
    fill_after_approval: bool
    variable_guidance: str | None
    max_length: int | None
    slot_inputs: tuple[str, ...]  # slot input tự khai (chỉ biến FREE_CONTENT), đã sắp xếp


@dataclass(frozen=True)
class TemplateInfo:
    template_id: uuid.UUID
    template_version_id: uuid.UUID
    version_no: int
    status: str
    variables: tuple[VariableInfo, ...]  # sắp theo tên

    @property
    def free_content_variables(self) -> tuple[str, ...]:
        return tuple(v.name for v in self.variables if v.kind == "FREE_CONTENT")

    def variable(self, name: str) -> VariableInfo:
        return next(v for v in self.variables if v.name == name)


_VARS = ("SELECT v.variable_name, v.kind, v.source_slot_name, v.fill_after_approval, v.variable_guidance, v.max_length, "
         "COALESCE((SELECT array_agg(i.slot_name ORDER BY i.slot_name) FROM template_variable_input i WHERE i.template_version_id = v.template_version_id AND i.variable_name = v.variable_name), '{}') "
         "FROM template_variable v WHERE v.template_version_id = %s ORDER BY v.variable_name")


def _variables(conn, version_id: uuid.UUID) -> tuple[VariableInfo, ...]:
    return tuple(VariableInfo(r[0], r[1], r[2], r[3], r[4], r[5], tuple(r[6])) for r in conn.execute(_VARS, (version_id,)).fetchall())


def read_version(conn, version_id: uuid.UUID) -> TemplateInfo:
    """Cùng logic cho `template_version_read` và cho các tool khác đã có `conn` (đọc trong giao dịch của chúng)."""
    row = conn.execute("SELECT v.template_id, v.id, v.version_no, v.status FROM template_version v WHERE v.id = %s", (version_id,)).fetchone()
    if row is None:
        raise TemplateVersionNotFound
    return TemplateInfo(row[0], row[1], row[2], row[3], _variables(conn, version_id))


def template_fetch(pool: Pool, ctx: ToolContext, *, request_type: str) -> TemplateInfo:
    require_system(ctx)
    with pool.acquire() as conn, read_only(conn):
        rows = conn.execute("SELECT v.id FROM template t JOIN template_version v ON v.template_id = t.id WHERE t.request_type_code = %s AND v.status = 'ACTIVE' ORDER BY v.id", (request_type,)).fetchall()
        if not rows:
            raise NoActiveTemplate
        if len(rows) > 1:
            raise TemplateAmbiguous
        return read_version(conn, rows[0][0])


def template_version_read(pool: Pool, ctx: ToolContext, *, template_version_id: uuid.UUID) -> TemplateInfo:
    require_system(ctx)
    with pool.acquire() as conn, read_only(conn):
        return read_version(conn, template_version_id)
