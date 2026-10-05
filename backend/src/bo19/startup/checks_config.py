"""Bước kiểm khởi động #11 và #13 — ràng buộc cấu hình thời gian và múi giờ của tổ chức.

#11 so **giá trị cấu hình** với nhau — không đo shutdown delay thực của Render (S4 đo ≈ 5 s trên gói free so với 30 s cấu hình; A-031, R2-5).
Giá trị biến không hợp lệ (không phải số nguyên dương) là mã trượt của chính bước này, và phép so sánh khi đó không chạy.
"""
from __future__ import annotations

from bo19.config.settings import Settings
from bo19.startup.model import Context, Entry, Result, code


def _invalid(step: str, settings: Settings, fields: tuple[str, ...]) -> list[str]:
    return [code(step, p.removeprefix("CONFIG_")) for f in fields if (p := settings.problem(f))]


def evaluate_turn_deadline(settings: Settings) -> list[str]:
    """`api`: hạn chót lượt chat cộng biên an toàn không dài hơn shutdown delay (ADR-016; WV-02 + WV-03 ≤ WV-01)."""
    fields = ("shutdown_delay_s", "turn_deadline_s", "turn_margin_s")
    bad = _invalid("11", settings, fields)
    if bad:
        return bad
    if settings.turn_deadline_s + settings.turn_margin_s > settings.shutdown_delay_s:
        return [code("11", "TURN_DEADLINE_EXCEEDS_SHUTDOWN_DELAY")]
    return []


def evaluate_lease(settings: Settings) -> list[str]:
    """`worker`: lease của `stored_object` dài hơn **hẳn** timeout của lớp tool chạm `object_storage` (WV-10 > WV-08)."""
    fields = ("stored_object_lease_s", "object_storage_timeout_s")
    bad = _invalid("11", settings, fields)
    if bad:
        return bad
    if settings.stored_object_lease_s <= settings.object_storage_timeout_s:
        return [code("11", "LEASE_NOT_ABOVE_STORAGE_TIMEOUT")]
    return []


def step_11(ctx: Context) -> Result:
    codes: list[str] = []
    if ctx.entry in (Entry.API, Entry.COMBINED):
        codes += evaluate_turn_deadline(ctx.settings)
    if ctx.entry in (Entry.WORKER, Entry.COMBINED):
        codes += evaluate_lease(ctx.settings)
    return Result(tuple(codes))


def step_13(ctx: Context) -> Result:
    """Múi giờ của tổ chức: `Asia/Ho_Chi_Minh` (A-041 `Đã chốt`) — `issued_date` và kỳ đánh số phụ thuộc nó."""
    return Result(tuple(_invalid("13", ctx.settings, ("timezone",))))
