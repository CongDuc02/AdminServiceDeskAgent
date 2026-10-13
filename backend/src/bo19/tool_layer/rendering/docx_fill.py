"""Điền bảng giá trị biến vào template `.docx` và đóng watermark (tool `docx_render`, mục Tool Registry của 03-agents.md; ADR-001; AC-1.3).

`fill_docx(template, values, declared=…, operating_mode=…)` là hàm **thuần** trên byte: không DB, không object storage, không đồng hồ.

**Kiểm trước khi điền** (docxtpl điền biến thiếu bằng chuỗi rỗng, không báo lỗi — `docs/reference/docxtpl-0.20.1.md`):
- `MISSING_VARIABLE` — template dùng một biến mà bảng giá trị không có (thân văn bản, header, footer: `get_undeclared_template_variables`);
- `UNKNOWN_VARIABLE` — bảng giá trị có một biến mà phiên bản template không khai (`declared` = danh mục `template_variable` của phiên bản).
Lỗi **chỉ mang tên biến** (`[a-z][a-z0-9_]*`), không bao giờ giá trị. Giá trị phải là `str` không có ký tự bị XML 1.0 cấm (`InvalidVariableValue`, chỉ tên biến); xuống dòng `\\n` thành ngắt dòng của Word.
Giá trị được điền như DỮ LIỆU (một lần, `autoescape`): `{{`, `{%`, `<`, `&` trong giá trị không bị thông dịch lại.

**Watermark (AC-1.3):** `operating_mode = NON_PRODUCTION` thì mọi tiêu đề trang của file mang một shape watermark **chéo trải thân trang** (`rendering.watermark`, B8c) — trong **file**, nên có cả ở `.docx` lẫn PDF. **Không có tham số tắt**: chế độ do chỗ gọi đọc từ `document` (đã ghim lúc tạo `DRAFT`, INV-01) và truyền vào; giá trị lạ là lỗi lập trình (`ValueError`), không phải "không watermark". `PRODUCTION` không thêm gì.
"""
from __future__ import annotations

import io
import re
from collections.abc import Collection, Mapping

from docxtpl import DocxTemplate

from bo19.tool_layer.rendering.watermark import WATERMARK_TEXT, add_watermark  # noqa: F401 — tên cũ vẫn dùng được từ `docx_fill`
from bo19.tool_layer.tools._common import ToolError

MODES = ("NON_PRODUCTION", "PRODUCTION")
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_XML_FORBIDDEN = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


class VariableError(ToolError):
    """Gốc của lỗi biến: mang danh sách TÊN biến (đã sắp xếp), không giá trị."""

    def __init__(self, names: Collection[str]) -> None:
        self.names = tuple(sorted(names))
        super().__init__(",".join(self.names))


class MissingVariable(VariableError):
    code = "MISSING_VARIABLE"


class UnknownVariable(VariableError):
    code = "UNKNOWN_VARIABLE"


class InvalidVariableValue(VariableError):
    code = "INVALID_VARIABLE_VALUE"  # mã nội bộ của tool: giá trị không phải str hoặc có ký tự XML cấm


class TemplateUnreadable(ToolError):
    code = "TEMPLATE_UNREADABLE"


def template_variables(template: bytes) -> frozenset[str]:
    """Các biến mà template dùng (thân văn bản, header, footer)."""
    try:
        return frozenset(DocxTemplate(io.BytesIO(template)).get_undeclared_template_variables())
    except Exception:  # noqa: BLE001 — file hỏng hay cú pháp Jinja sai: một mã, không thông điệp (có thể mang đoạn văn bản của template)
        raise TemplateUnreadable from None


def fill_docx(template: bytes, values: Mapping[str, str], *, declared: Collection[str], operating_mode: str) -> bytes:
    if operating_mode not in MODES:
        raise ValueError("operating_mode")
    bad = sorted(k for k, v in values.items() if not _NAME.match(k) or not isinstance(v, str) or _XML_FORBIDDEN.search(v))
    if bad:
        raise InvalidVariableValue(k if _NAME.match(k) else "invalid_name" for k in bad)
    used = template_variables(template)
    missing = used - set(values)
    if missing:
        raise MissingVariable(missing)
    unknown = set(values) - set(declared)
    if unknown:
        raise UnknownVariable(unknown)
    context = dict(values)  # docxtpl 0.20.1 tự đổi xuống dòng trong giá trị thành ngắt dòng của Word (đo ở B8b; docs/reference/docxtpl-0.20.1.md)
    try:
        doc = DocxTemplate(io.BytesIO(template))
        doc.render(context, autoescape=True)
        buf = io.BytesIO()
        doc.save(buf)
    except Exception:  # noqa: BLE001 — như trên: chỉ mã
        raise TemplateUnreadable from None
    out = buf.getvalue()
    return add_watermark(out) if operating_mode == "NON_PRODUCTION" else out
