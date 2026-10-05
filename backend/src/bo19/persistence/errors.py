"""Tên ràng buộc → mã lỗi nội bộ của tool (mục Cây backend của 06-structure.md; tiền tố `ck_`, `uq_`, `fk_` ở mục Nguyên tắc dữ liệu của 04-data.md).

Mã lỗi nội bộ không bao giờ ra khỏi `api` (mục Mã lỗi của tool và thao tác của 05-api.md): lọt tới `api` thì thành `INTERNAL_ERROR`.
`CONSTRAINT_CODES` ánh xạ **tên ràng buộc đã biết** sang mã của tool; tool nào cần phân biệt một ràng buộc thì thêm một dòng ở đây cùng test.
Tên chưa có trong bảng rơi về mã chung theo tiền tố — không bao giờ ra thông điệp gốc của PostgreSQL, vì nó mang tên bảng, tên cột và có thể cả giá trị.
"""
from __future__ import annotations

import psycopg
from psycopg import errors

CONSTRAINT_CODES: dict[str, str] = {}

_PREFIX_CODES = (("ck_", "CHECK_VIOLATION"), ("uq_", "UNIQUE_VIOLATION"), ("fk_", "FOREIGN_KEY_VIOLATION"))
UNMAPPED = "CONSTRAINT_VIOLATION"  # lỗi toàn vẹn mà tên ràng buộc không có tiền tố đã biết, hoặc PostgreSQL không báo tên


class IntegrityViolation(Exception):
    """Vi phạm ràng buộc DB, đã quy về mã. Chỉ mang mã — không có thông điệp, tên bảng hay giá trị."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def classify(exc: psycopg.Error) -> str | None:
    """Mã nội bộ của một lỗi toàn vẹn dữ liệu; `None` nếu `exc` không phải lỗi toàn vẹn (không phải việc của hàm này)."""
    if not isinstance(exc, errors.IntegrityError):
        return None
    name = exc.diag.constraint_name or ""
    if name in CONSTRAINT_CODES:
        return CONSTRAINT_CODES[name]
    for prefix, code in _PREFIX_CODES:
        if name.startswith(prefix):
            return code
    return UNMAPPED
