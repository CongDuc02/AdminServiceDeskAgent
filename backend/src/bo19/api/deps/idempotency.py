"""Header `Idempotency-Key` — bắt buộc trên endpoint tạo dòng mới; giá trị **là** uuid của dòng chính mà lệnh ghi tạo ra (mục Idempotency của 05-api.md).

Thiếu → `IDEMPOTENCY_KEY_REQUIRED` (400); không phải uuid → `VALIDATION_FAILED` (`Idempotency-Key` / `INVALID_FORMAT`). Ba phép kiểm khi trùng khoá nằm ở thao tác của `tool_layer`,
vì chúng cần đọc dòng đã có dưới khoá của chính giao dịch ghi.
"""
from __future__ import annotations

import uuid

from bo19.api.errors import ApiError


def idempotency_key(value: str | None) -> uuid.UUID:
    if value is None or not value.strip():
        raise ApiError("IDEMPOTENCY_KEY_REQUIRED")
    try:
        return uuid.UUID(value.strip())
    except ValueError:
        raise ApiError("VALIDATION_FAILED", {"fields": [{"field": "Idempotency-Key", "code": "INVALID_FORMAT"}]}) from None
