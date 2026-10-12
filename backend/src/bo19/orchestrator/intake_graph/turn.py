"""Đối tượng của MỘT lượt chat và phần phụ thuộc dùng chung của graph (mục Triển khai ở B6b của 06-structure.md).

`TurnRuntime` **không** nằm trong state và không bao giờ được tuần tự hoá: nó mang văn bản tin nhắn (`RES`), hai ngữ cảnh tool, hạn chót tuyệt đối, cờ huỷ hợp tác và callback tiến độ. Node nhận nó
qua `config["configurable"]["turn"]`. `repr` không mang văn bản.

**Hạn chót và cờ huỷ (thread sync không huỷ được từ ngoài):** `alive()` được gọi trước MỌI lần gọi tool hay gateway — `call_tool`, `call_llm` — nên sau khi cờ bật hay hạn chót qua, thread không ghi gì
thêm. `call_llm` truyền `turn_deadline = deadline` vào gateway, nên mỗi lời gọi nhận min(WV-04/WV-06, thời gian còn lại của lượt).
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bo19.ai_gateway.budget import BudgetOwner
from bo19.ai_gateway.gateway import Gateway, GatewayResult
from bo19.ai_gateway.prompt_modules import PromptModule
from bo19.orchestrator.intake_graph.reply_templates import Templates
from bo19.orchestrator.runtime.node_boundary import TURN_CANCELLED, TURN_DEADLINE, NodeError
from bo19.persistence.pool import Pool
from bo19.tool_layer.kernel.context import ToolContext

Progress = Callable[[str], None]
STAGES = ("UNDERSTANDING", "LOOKING_UP", "PREPARING_REPLY")


@dataclass(frozen=True)
class IntakeDeps:
    pool: Pool
    gateway: Gateway
    templates: Templates


@dataclass
class TurnRuntime:
    ctx: ToolContext  # nhân viên đang chat — tool của chính họ
    sys: ToolContext  # tác nhân hệ thống — tool chỉ tác nhân hệ thống được gọi
    deadline: float  # `time.monotonic()` tuyệt đối — hạn chót của cả lượt (WV-02)
    cancel: threading.Event = field(default_factory=threading.Event)
    on_progress: Progress | None = None
    message_text: str | None = field(default=None, repr=False)  # RES — chỉ trong bộ nhớ của lượt, không vào state, log hay checkpoint
    resume: bool = False  # `load_turn` quyết: lượt này đi `resume_context`
    scratch: dict[str, Any] = field(default_factory=dict, repr=False)  # mã trung gian giữa hai node (kết quả P1…): chỉ mã
    _stage: str | None = None

    def alive(self) -> None:
        if self.cancel.is_set():
            raise NodeError(TURN_CANCELLED)
        if time.monotonic() >= self.deadline:
            raise NodeError(TURN_DEADLINE)

    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    def progress(self, stage: str) -> None:
        if stage != self._stage and self.on_progress is not None:
            self._stage = stage
            try:
                self.on_progress(stage)
            except Exception:  # noqa: BLE001 — tiến độ là tiện ích: lỗi của người nghe không được làm hỏng lượt
                pass

    def call_tool(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Gọi một tool/hàm đọc cấu hình — sau khi kiểm hạn chót và cờ huỷ."""
        self.alive()
        return fn(*args, **kwargs)

    def call_llm(self, deps: IntakeDeps, module: PromptModule, inputs: dict[str, Any], owner: BudgetOwner) -> GatewayResult:
        """Một lời gọi gateway (async) từ node sync: `asyncio.run`, mỗi lời gọi một event loop riêng. Hạn chót lượt truyền xuống gateway."""
        self.alive()
        return asyncio.run(deps.gateway.call(module, inputs, owner, turn_deadline=self.deadline))
