"""Dấu giữ chỗ của biến *điền sau duyệt* trong bản NHÁP, và phép kiểm "bản cuối không còn dấu giữ chỗ nào" (A-098; PO 2026-10-15; ADR-039 mục 9).

Bản nháp phải **nhìn ra ngay là chưa chính thức**: biến điền-sau-duyệt (INV-01: số văn bản, ngày ban hành, người ký…) hiện `[Số văn bản — cấp khi phát hành]`, không phải một chuỗi lẫn được với nội dung thật.
Bản `FINAL` thì **không được còn dấu giữ chỗ nào**: `docx_render` với `render_kind = FINAL` thất bại (`PLACEHOLDER_REMAINS`) nếu một giá trị là dấu giữ chỗ của hệ thống, là giữ chỗ chung (`free_content.is_placeholder`),
hoặc nếu chữ của file đã điền còn một dấu giữ chỗ của hệ thống (ví dụ nằm sẵn trong khung của template). Nhãn chỉ là chữ hiển thị; việc nhận ra dấu giữ chỗ dựa vào khuôn `[… — cấp khi phát hành]`, không dựa vào tên biến.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from bo19.domain import free_content

SUFFIX = "cấp khi phát hành"
# Nhãn hiển thị của biến điền-sau-duyệt đã biết (WORK_CONFIRMATION); biến lạ hiện tên biến — vẫn nhận ra được vì khuôn không đổi.
_LABELS = {"document_number": "Số văn bản", "issued_date": "Ngày ban hành", "signer_user_id": "Người ký"}
_MARKER = re.compile(r"\[[^\[\]\r\n]{1,80}?\s[—–-]\s+" + SUFFIX + r"\s*\]", re.IGNORECASE)


def marker_for(variable_name: str) -> str:
    return f"[{_LABELS.get(variable_name, variable_name)} — {SUFFIX}]"


def contains_marker(text: str) -> bool:
    return _MARKER.search(unicodedata.normalize("NFC", text)) is not None


def placeholder_variables(values: Mapping[str, str]) -> tuple[str, ...]:
    """TÊN các biến mà giá trị là dấu giữ chỗ — của hệ thống hay giữ chỗ chung. Không trả giá trị."""
    return tuple(sorted(name for name, value in values.items() if contains_marker(value) or free_content.is_placeholder(value)))
