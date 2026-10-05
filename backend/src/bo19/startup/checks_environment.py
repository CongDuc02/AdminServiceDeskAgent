"""Bước kiểm khởi động #15, #16 và #17 — `operating_mode` và `BO19_ENVIRONMENT` (ADR-023, lớp 2 của ba lớp khoá).

#15 đọc `operating_mode` hiện hành **một lần** và chỉ ghi log (D-009: chưa có dòng nào là `NON_PRODUCTION`). Giá trị đã đọc nằm ở `ctx.cache`
và #17 dùng lại, không đọc lần hai. #16 chặn khi thiếu hay sai `BO19_ENVIRONMENT` — không bao giờ mặc định thành `prod` (fail-closed).
#17 chỉ áp khi `BO19_ENVIRONMENT ≠ prod`; với `prod` luôn qua, bất kể `operating_mode` (một `prod` mới dựng vẫn ở `NON_PRODUCTION` theo D-009
và vẫn khởi động được). Nếu biến không đọc được, #17 tự bỏ qua phần so khớp — #16 đã bắt riêng, không báo trùng mã.
Chạy hết rồi mới gom mã: #17 vẫn chạy khi #16 trượt.
"""
from __future__ import annotations

from bo19.config.settings import Environment
from bo19.persistence import read
from bo19.startup.model import Context, Result, code

CACHE_KEY = "operating_mode"


def read_operating_mode_once(ctx: Context) -> read.OperatingModeRead | Exception:
    """Một lần đọc dùng chung cho #15 và #17. Lỗi đọc (bảng chưa có, thiếu quyền…) được giữ lại thay vì ném, để mỗi bước tự quyết."""
    if CACHE_KEY not in ctx.cache:
        try:
            ctx.cache[CACHE_KEY] = read.current_operating_mode(ctx.conn)
        except Exception as e:  # noqa: BLE001
            ctx.cache[CACHE_KEY] = e
    return ctx.cache[CACHE_KEY]


def step_15(ctx: Context) -> Result:
    got = read_operating_mode_once(ctx)
    if isinstance(got, Exception):
        return Result((), {"mode": "UNREADABLE", "source": "READ_ERROR", "read_error_type": type(got).__qualname__})
    return Result((), {"mode": got.mode, "source": "ROW" if got.from_row else "DEFAULT_NO_ROW"})


def step_16(ctx: Context) -> Result:
    problem = ctx.settings.problem("environment")
    return Result((code("16", problem.removeprefix("CONFIG_")),) if problem else ())


def step_17(ctx: Context) -> Result:
    environment = ctx.settings.environment
    if environment is None or environment is Environment.PROD:
        return Result()
    got = read_operating_mode_once(ctx)
    if isinstance(got, Exception):
        return Result((code("17", "OPERATING_MODE_UNREADABLE"),))  # không xác nhận được NON_PRODUCTION thì không khởi động (fail-closed)
    if got.mode != read.NON_PRODUCTION:
        return Result((code("17", "OPERATING_MODE_MISMATCH"),))
    return Result()
