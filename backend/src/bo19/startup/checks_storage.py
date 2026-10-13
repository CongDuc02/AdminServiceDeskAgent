"""Bước kiểm khởi động #14 — `object_storage` với tới được (mục Bước kiểm khởi động của 06-structure.md; ADR-014).

**Cảnh báo, không chặn:** sự cố tạm thời của storage không được làm tiến trình khởi động lại liên tục; thao tác hỏng lúc dùng trả `FILE_UNAVAILABLE` hoặc job thử lại. Hai mã cảnh báo:
`STARTUP_14_NOT_CONFIGURED` (nhóm biến object storage vắng — chưa dùng được) và `STARTUP_14_UNREACHABLE` (bucket không với tới được bằng credential đã cấu hình). Chỉ mã — không endpoint, không tên bucket, không credential.
Cấu hình có phần thiếu hay sai đã bị chặn ở `Settings.problems`, nên bước này chỉ gặp nhóm đầy đủ hoặc vắng hẳn.
"""
from __future__ import annotations

from bo19.startup.model import Context, Result, code
from bo19.tool_layer.storage import from_settings


def step_14(ctx: Context) -> Result:
    storage = from_settings(ctx.settings)
    if storage is None:
        return Result((code("14", "NOT_CONFIGURED"),))
    if not storage.reachable():
        return Result((code("14", "UNREACHABLE"),))
    return Result()
