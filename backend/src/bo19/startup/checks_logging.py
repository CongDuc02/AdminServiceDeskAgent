"""Bước kiểm khởi động #10 — root logger có đúng một handler, và là handler mask của `observability` (NFR-05).

Log viết ra trước khi có handler mask là log đã lộ, không mask lại được (12-roadmap.md); bước này chặn tiến trình nếu thư viện nào
gắn thêm handler vào root logger, hoặc handler mask bị gỡ. `startup` không tự chạm `logging` — hỏi `observability`.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence

from bo19.observability import handler as obs_handler
from bo19.startup.model import Context, Result, code


def evaluate_root_handlers(handlers: Sequence[logging.Handler]) -> list[str]:
    if len(handlers) != 1:
        return [code("10", "ROOT_HANDLERS_NOT_ONE")]
    if type(handlers[0]) is not obs_handler.MaskedJsonHandler:  # đúng lớp, không chấp nhận lớp con — lớp con có thể bỏ qua mask
        return [code("10", "ROOT_HANDLER_NOT_MASK")]
    return []


def step_10(_ctx: Context) -> Result:
    return Result(tuple(evaluate_root_handlers(obs_handler.root_handlers())))
