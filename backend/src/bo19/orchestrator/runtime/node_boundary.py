"""Biên node — chỉ exception mang mã rời một node (mục Nghĩa vụ kế thừa và Triển khai ở B6b của 06-structure.md; A-045).

LangGraph lưu exception của node vào bảng checkpoint (`checkpoint_writes`, kênh `ERROR` — `docs/reference/langgraph-checkpoint-postgres.md` mục 6; thử nghiệm B6b: **thông điệp của exception
nằm nguyên văn trong `blob`**). Một exception mang giá trị `RES` — ví dụ `KeyError` với khoá là văn bản người dùng, hay thông điệp của thư viện chép lại input — sẽ thành PII nằm trong checkpoint.
Vì vậy mọi node đi qua `guard`: exception bất kỳ được đổi thành `NodeError(code)` — chỉ mã, tạo **ngoài** khối `except` để không kéo theo `__context__` — rồi mới rời node.

Mã lấy từ thuộc tính `code` của exception nếu nó là mã hợp lệ (`ToolError`, `BudgetExceeded`, `ProviderError`, …); không thì `NODE_UNEXPECTED`. Tên kiểu exception (không phải thông điệp) vào log.
"""
# Không `from __future__ import annotations` ở file này: LangGraph chỉ tiêm `config` vào node khi tham số được chú thích đúng `RunnableConfig`, và đọc chú thích thật, không đọc chuỗi.
import re
from collections.abc import Callable
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphBubbleUp

from bo19.observability.log import get_logger

log = get_logger("bo19.orchestrator")

_CODE = re.compile(r"^[A-Z][A-Z0-9_]*(:[A-Za-z0-9_]{1,40})?$")
UNEXPECTED = "NODE_UNEXPECTED"
TURN_CANCELLED, TURN_DEADLINE = "TURN_CANCELLED", "TURN_DEADLINE"


class NodeError(Exception):
    """Exception duy nhất được phép rời node. `args` chỉ có mã."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    def __reduce__(self) -> tuple[Any, ...]:
        return (NodeError, (self.code,))


def code_of(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and _CODE.match(code) else UNEXPECTED


def guard(name: str, fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Bọc một node: kết quả đi qua; `NodeError` đi qua nguyên vẹn; mọi exception khác bị đổi thành `NodeError(code)`."""

    def wrapped(state: Any, config: Optional[RunnableConfig] = None) -> Any:  # noqa: UP007, UP045 — chú thích thật cho LangGraph
        failure: str | None = None
        try:
            return fn(state, config)
        except (NodeError, GraphBubbleUp):
            raise  # `GraphInterrupt` (B9a, `interrupt`) là điều khiển luồng của LangGraph, không phải lỗi: phải đi qua nguyên vẹn — nó không mang văn bản của người dùng
        except Exception as e:  # noqa: BLE001 — chính là mục đích của biên node
            failure = code_of(e)
            log.warning("NODE_FAILED", node=name, code=failure, exception_type=type(e).__name__)
        raise NodeError(failure)  # ngoài khối except: không có `__context__`

    wrapped.__name__ = name
    return wrapped
