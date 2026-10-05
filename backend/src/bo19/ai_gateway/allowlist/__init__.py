"""Allowlist input fail-closed — ADR-008; mục Allowlist input của từng lời gọi ra ngoài của 03-agents.md; INV-03.

So tập khoá của `inputs` với đúng tập mà module đã khai — **thừa hay thiếu đều từ chối**. Chạy **trước mọi thứ khác** trong `call` (mục Nghĩa vụ kế thừa của 06-structure.md):
không có đường tới provider mà không đi qua phép kiểm này.

`AllowlistRejected` mang tên khoá thừa và thiếu (tên do code gọi đặt, đã làm sạch), **không bao giờ mang giá trị**.
"""
from __future__ import annotations

from typing import Any

from bo19.ai_gateway.prompt_modules.base import InputInvalid, PromptModule, VariableSpec


class AllowlistRejected(Exception):
    code = "ALLOWLIST_REJECTED"

    def __init__(self, missing: tuple[str, ...], extra: tuple[str, ...], forbidden: tuple[str, ...] = ()) -> None:
        super().__init__(self.code)
        self.missing, self.extra, self.forbidden = missing, extra, forbidden


def _names(keys: Any) -> tuple[str, ...]:
    return tuple(sorted("".join(c if c.isalnum() or c == "_" else "?" for c in str(k))[:64] for k in keys))


def check(module: PromptModule, inputs: dict[str, Any], variable: VariableSpec | None = None) -> None:
    if module.uses_variable and variable is None:
        raise InputInvalid  # P4 không có `variable` thì không biết slot nào hợp lệ: lỗi của người gọi
    declared = module.allowed_inputs(variable)
    forbidden = _names(declared & module.forbidden_inputs)  # `variable` khai một khoá cấm: cấu hình sai, từ chối
    if forbidden:
        raise AllowlistRejected((), (), forbidden)
    given = set(inputs)
    missing, extra = declared - given, given - declared
    present_forbidden = given & module.forbidden_inputs
    if missing or extra or present_forbidden:
        raise AllowlistRejected(_names(missing), _names(extra), _names(present_forbidden))
