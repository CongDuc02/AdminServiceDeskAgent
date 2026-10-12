"""Bước kiểm khởi động #23 — file khuôn trả lời hợp lệ (06-structure.md, mục Bước kiểm khởi động; `proposals/reply-templates.md`, R2).

Cùng khuôn #21: `api` không khởi động với file khuôn hỏng. Mã lỗi mang tên khuôn/tham số, không mang văn bản khuôn.
"""
from __future__ import annotations

from bo19.orchestrator.intake_graph import reply_templates
from bo19.startup.model import Context, Result, code


def step_23(ctx: Context) -> Result:
    return Result(tuple(code("23", c) for c in reply_templates.check()))
