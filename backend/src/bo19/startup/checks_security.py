"""Bước kiểm khởi động #12, #19 và #20 — secret phiên, tracing của `langsmith`, tham số `argon2id`.

#19 — tên biến lấy từ tài liệu gốc đã tải bằng `curl` (`docs/reference/langsmith-tracing-env-nguon-goc.md`, đúng bản lock):
bốn tên bật tracing là `{LANGSMITH,LANGCHAIN}_TRACING{,_V2}`; sáu tên `*_TRACING_MODE`, `*_TRACING_SAMPLING_RATE`, `*_TRACING_QUEUE_MAX_SIZE`
không tự bật nhưng cũng chứa `TRACING`. Đặc tả đã duyệt (A-082, 2026-09-27) chặn theo **mẫu tên**, không theo danh sách: bắt đầu bằng
`LANGSMITH_` hoặc `LANGCHAIN_` **và** chứa `TRACING`, so không phân biệt hoa thường, bất kể giá trị, kể cả rỗng. Mẫu phủ cả bốn tên trên,
và phủ cả tên mà bản sau của `langsmith` có thể thêm. Log và mã ghi **tên** biến, không bao giờ ghi giá trị.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from bo19.startup.model import Context, Result, code

TRACING_PREFIXES = ("LANGSMITH_", "LANGCHAIN_")
TRACING_WORD = "TRACING"
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_]")

# WV-16 — OWASP, cấu hình thứ hai trong năm cấu hình (docs/reference/owasp-password-storage-argon2id.md). Không ngoại lệ theo môi trường.
ARGON2_MIN_TIME_COST = 2
ARGON2_MIN_MEMORY_COST_KIB = 19456
ARGON2_PARALLELISM = 1


def tracing_variable_names(env: Mapping[str, str]) -> list[str]:
    """Tên các biến trong `env` khớp mẫu — trả tên đúng như trong `env`, đã bỏ ký tự lạ; không đụng tới giá trị."""
    names = []
    for name in env:
        upper = name.upper()
        if upper.startswith(TRACING_PREFIXES) and TRACING_WORD in upper:
            names.append(_SAFE_NAME.sub("?", name)[:80])
    return sorted(names)


def step_19(ctx: Context) -> Result:
    return Result(tuple(code("19", f"TRACING_ENV_SET:{n}") for n in tracing_variable_names(ctx.env)))


def step_12(ctx: Context) -> Result:
    """Secret ký `bo19_session` có mặt (ADR-013). Độ dài tối thiểu chưa chốt — A-088: bước này không bịa một con số."""
    problem = ctx.settings.problem("session_secret")
    return Result((code("12", problem.removeprefix("CONFIG_")),) if problem else ())


def step_20(ctx: Context) -> Result:
    s = ctx.settings
    codes = [code("20", p.removeprefix("CONFIG_")) for f in ("argon2_time_cost", "argon2_memory_cost_kib", "argon2_parallelism") if (p := s.problem(f))]
    if codes:
        return Result(tuple(codes))
    if s.argon2_time_cost < ARGON2_MIN_TIME_COST:
        codes.append(code("20", "ARGON2_TIME_COST_BELOW_MIN"))
    if s.argon2_memory_cost_kib < ARGON2_MIN_MEMORY_COST_KIB:
        codes.append(code("20", "ARGON2_MEMORY_COST_KIB_BELOW_MIN"))
    if s.argon2_parallelism != ARGON2_PARALLELISM:
        codes.append(code("20", "ARGON2_PARALLELISM_NOT_1"))
    return Result(tuple(codes))
