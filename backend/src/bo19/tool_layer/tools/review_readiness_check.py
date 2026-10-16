"""Tool `review_readiness_check` — kiểm tất định định nghĩa **đủ điều kiện trình duyệt** (F2 của 01-prd.md; mục Tool Registry của 03-agents.md; ADR-039).

Mã lỗi: `VARIABLE_MISSING` · `PLACEHOLDER_VALUE` · `WRONG_SOURCE` · `FRAME_TEXT_IN_VARIABLE` · `SEAL_UNDETERMINED` · `TEMPLATE_NOT_ACTIVE_AT_RENDER` — tính trên **chính bảng giá trị** mà `render_draft` dựng
(`tools.render_values.build_values`), nên "bản đã render" và "bản đã kiểm" không lệch nhau. Chỉ đọc; không `audit_event` (đọc), kết quả chỉ mang mã và tên biến — không giá trị.

`document_transition` (`DRAFT → PENDING_APPROVAL`) **tự chạy lại** phép kiểm này trong giao dịch của nó (`NOT_READY`): node không bỏ qua được.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_system
from bo19.tool_layer.tools.render_values import Issue, build_values


@dataclass(frozen=True)
class Readiness:
    ok: bool
    issues: tuple[Issue, ...]  # (mã, tên biến) — rỗng khi `ok`

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(sorted({i.code for i in self.issues}))


def review_readiness_check(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID) -> Readiness:
    require_system(ctx)
    with pool.acquire() as conn, read_only(conn):
        built = build_values(conn, document_id)
    return Readiness(not built.issues, built.issues)
