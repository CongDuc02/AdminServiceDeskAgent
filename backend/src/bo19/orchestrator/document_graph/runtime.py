"""Phần dùng chung của `document_graph` (ADR-039): phụ thuộc của node và đối tượng của MỘT lần chạy (`RenderRuntime`).

`RenderRuntime` **không** nằm trong state và không bao giờ được tuần tự hoá: nó mang `scratch` — nơi giữ văn bản do LLM sinh giữa `draft_free_content` và `validate_free_content` (ADR-008: văn bản LLM không vào state,
log hay checkpoint) — cờ huỷ hợp tác của job (mất lease, drain) và ngữ cảnh hệ thống. Node nhận nó qua `config["configurable"]["run"]`; `repr` không mang gì trong `scratch`.

`alive()` được gọi trước MỌI lần gọi tool hay gateway: sau khi cờ bật, thread không ghi gì thêm (thread sync không huỷ được từ ngoài; lệnh ghi muộn còn bị hàng rào chủ lease của `tool_layer.jobs` chặn thêm một lớp).
"""
from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bo19.ai_gateway.budget import BudgetOwner
from bo19.ai_gateway.gateway import Gateway, GatewayResult
from bo19.ai_gateway.prompt_modules import PromptModule, VariableSpec
from bo19.orchestrator.runtime.node_boundary import NodeError
from bo19.persistence.pool import Pool
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.storage import ObjectStorage
from bo19.tool_layer.tools.document_draft_save import InputFingerprinter

JOB_CANCELLED = "JOB_CANCELLED"


@dataclass(frozen=True)
class DocumentDeps:
    pool: Pool
    gateway: Gateway
    storage: ObjectStorage
    fingerprinter: InputFingerprinter


@dataclass
class RenderRuntime:
    sys: ToolContext
    cancel: threading.Event = field(default_factory=threading.Event)
    scratch: dict[str, Any] = field(default_factory=dict, repr=False)

    def alive(self) -> None:
        if self.cancel.is_set():
            raise NodeError(JOB_CANCELLED)

    def call_tool(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        self.alive()
        return fn(*args, **kwargs)

    def call_llm(self, deps: DocumentDeps, module: PromptModule, inputs: dict[str, Any], owner: BudgetOwner, variable: VariableSpec) -> GatewayResult:
        """Một lời gọi gateway (async) từ node sync: `asyncio.run`, mỗi lời gọi một event loop riêng. Ở `worker` không có hạn chót lượt — hạn chót là của tier (WV-06)."""
        self.alive()
        return asyncio.run(deps.gateway.call(module, inputs, owner, variable=variable))

    def note_retry_after(self, seconds: int | None) -> None:
        if seconds is not None:
            self.scratch["retry_after_s"] = seconds
