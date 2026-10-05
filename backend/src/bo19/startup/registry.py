"""Bước kiểm đã có code ở B2 — số bước → hàm. Bước nào có trong `MATRIX` mà không có ở đây là bước **chưa làm**:
bộ chạy ghi `STARTUP_CHECK_PENDING` cho nó ở mỗi lần khởi động, và `tests/test_startup_runner.py` khoá danh sách đó — thêm một bước vào
đây mà không sửa danh sách khai báo trong test là test đỏ, và ngược lại.
"""
from __future__ import annotations

from bo19.startup import checks, checks_logging
from bo19.startup.model import Check

REGISTRY: dict[str, Check] = {
    "1": checks.step_01,
    "2": checks.step_02,
    "10": checks_logging.step_10,
}
