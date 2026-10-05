"""`trace_id` theo contextvar — UUID v4, chữ thường, có gạch nối (ADR-024; mục Log schema của 11-ops.md).

Sinh một lần cho mỗi đơn vị công việc tại điểm vào (một request HTTP, một job, một lần cron) rồi đi theo contextvar
qua api → orchestrator → tool_layer → queue_worker. Dùng `contextvars` của thư viện chuẩn để `handler.py` đọc được
mà không import structlog (docs/reference/structlog-25.4.0.md, mục 3).
"""
from __future__ import annotations

import contextlib
import contextvars
import re
import uuid
from collections.abc import Iterator

_TRACE_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("bo19_trace_id", default=None)


def new_trace_id() -> str:
    return str(uuid.uuid4())


def is_trace_id(value: object) -> bool:
    return isinstance(value, str) and _TRACE_ID_RE.match(value) is not None


def current_trace_id() -> str | None:
    return _trace_id.get()


@contextlib.contextmanager
def trace_scope(trace_id: str | None = None) -> Iterator[str]:
    """Mở một đơn vị công việc: sinh `trace_id` mới (hoặc nhận một giá trị đúng khuôn) và trả lại giá trị cũ khi ra."""
    value = new_trace_id() if trace_id is None else trace_id
    if not is_trace_id(value):
        raise ValueError("trace_id phải là UUID v4 chữ thường, có gạch nối (ADR-024)")
    token = _trace_id.set(value)
    try:
        yield value
    finally:
        _trace_id.reset(token)
