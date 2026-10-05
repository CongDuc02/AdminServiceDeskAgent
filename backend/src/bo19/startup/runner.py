"""Bộ chạy bước kiểm khởi động — mục Bước kiểm khởi động của 06-structure.md.

Chạy **hết** mọi bước áp cho entrypoint rồi mới gom danh sách mã trượt; không dừng ở bước trượt đầu tiên. Bước `Chặn` trượt thì báo cáo
mang mã, entrypoint ghi log rồi thoát mã khác 0. Mỗi bước tự bắt ngoại lệ của chính nó: một bước hỏng không làm mất kết quả các bước khác,
và một bước kiểm nổ coi như **trượt** (fail-closed), không coi như đạt.

Bước có trong `MATRIX` mà chưa có code (`REGISTRY`) là bước **chưa làm**: ghi `STARTUP_CHECK_PENDING` mỗi lần khởi động — thiếu một bước
kiểm thì phải thấy trong log, không im lặng. Bước cần DB mà không nối được thì ghi `STARTUP_CHECK_SKIPPED`, không tính là đạt.
Không bao giờ ghi DSN, mật khẩu hay giá trị biến vào log — chỉ mã và tên biến.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg

from bo19.config.settings import Settings
from bo19.observability.log import Log, get_logger
from bo19.startup.checks import MIGRATIONS_DIR
from bo19.startup.connect import classify_connect_error, connect
from bo19.startup.model import MATRIX, Check, Context, Entry, Level, Result, Step, code
from bo19.startup.registry import REGISTRY

CONNECT_FAILED = "STARTUP_DB_CONNECT_FAILED"


@dataclass(frozen=True)
class Report:
    entry: Entry
    failures: tuple[str, ...]  # mã của bước Chặn trượt (và lỗi nối DB, lỗi cấu hình dùng chung)
    warnings: tuple[str, ...]
    passed: tuple[str, ...]    # số bước đã chạy và đạt
    skipped: tuple[str, ...]   # bước cần DB nhưng không nối được
    pending: tuple[str, ...]   # bước áp cho entrypoint này mà chưa có code

    @property
    def ok(self) -> bool:
        return not self.failures


def pending_steps(steps: Sequence[Step] = MATRIX, registry: Mapping[str, Check] = REGISTRY) -> tuple[str, ...]:
    """Số bước có trong ma trận mà chưa có code — toàn ma trận, không lọc theo entrypoint."""
    return tuple(s.number for s in steps if s.number not in registry)


def _crash_code(step: Step, exc: BaseException) -> str:
    return code(step.number, f"CHECK_CRASHED:{type(exc).__qualname__}")


def run(entry: Entry, settings: Settings, env: Mapping[str, str], *, migrations_root: Path = MIGRATIONS_DIR,
        steps: Sequence[Step] = MATRIX, registry: Mapping[str, Check] = REGISTRY,
        connector: Callable[[str, str], psycopg.Connection] = connect, log: Log | None = None) -> Report:
    log = log or get_logger("bo19.startup")
    applicable = [s for s in steps if s.applies(entry)]
    log.info("STARTUP_BEGIN", entry=entry.value)

    failures: list[str] = []
    warnings: list[str] = []
    passed: list[str] = []
    skipped: list[str] = []
    pending: list[str] = []

    # Cấu hình dùng chung cho cả entrypoint — không thuộc một bước đánh số nào.
    needs_db = any(s.needs_db and s.number in registry for s in applicable)
    if needs_db and settings.problem("database_url"):
        failures.append("STARTUP_CONFIG_DATABASE_URL_MISSING")
    if entry in (Entry.API, Entry.COMBINED) and settings.problem("port"):
        failures.append("STARTUP_CONFIG_PORT_INVALID")

    conn = None
    if needs_db and settings.database_url:
        try:
            conn = connector(settings.database_url, f"bo19-{entry.value}-startup")
        except psycopg.Error as e:
            # Thông báo của driver có thể mang host — chỉ ghi lớp phân loại (O1-4), không ghi nguyên văn.
            failures.append(CONNECT_FAILED)
            log.error("STARTUP_DB_CONNECT_DETAIL", failure_kind=classify_connect_error(e).value, exc=e)

    ctx = Context(entry, settings, env, conn, migrations_root)
    try:
        for step in applicable:
            check = registry.get(step.number)
            if check is None:
                pending.append(step.number)
                log.warning("STARTUP_CHECK_PENDING", step=step.number, entry=entry.value)
                continue
            if step.needs_db and conn is None:
                skipped.append(step.number)
                log.warning("STARTUP_CHECK_SKIPPED", step=step.number, reason="DB_UNAVAILABLE")
                continue
            try:
                result: Result = check(ctx)
            except Exception as e:  # noqa: BLE001 — một bước nổ là một bước trượt, không phải một bước đạt
                result = Result((_crash_code(step, e),))
            if conn is not None and not conn.closed:
                conn.rollback()  # mỗi bước trả giao dịch sạch cho bước sau
            if result.info:
                log.info("STARTUP_CHECK_INFO", step=step.number, **result.info)
            if not result.codes:
                passed.append(step.number)
            elif step.level is Level.BLOCK:
                failures.extend(result.codes)
            else:
                warnings.extend(result.codes)
    finally:
        if conn is not None:
            conn.close()

    for c in warnings:
        log.warning("STARTUP_WARN", code=c)
    for c in failures:
        log.error("STARTUP_FAIL", code=c)
    if failures:
        log.error("STARTUP_ABORT", failed=len(failures))
    else:
        log.info("STARTUP_OK", entry=entry.value, passed=",".join(passed), pending=",".join(pending), skipped=",".join(skipped))
    return Report(entry, tuple(failures), tuple(warnings), tuple(passed), tuple(skipped), tuple(pending))
