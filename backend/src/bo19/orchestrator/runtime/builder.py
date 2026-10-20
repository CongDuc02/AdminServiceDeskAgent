"""Lối dựng graph duy nhất: mọi node đi qua biên node (mục Cây backend và Triển khai ở B6b của 06-structure.md; contract `graph-library`).

Chỉ `orchestrator.runtime` import `langgraph`. `intake_graph` khai node và cạnh qua `GraphBuilder` — không chạm LangGraph — và nhận lại một `Graph` có mặt tiền hẹp: `invoke` trên một thread,
đọc state hiện có của thread. `GraphBuilder.node` bọc node bằng `node_boundary.guard` — không có đường dựng node nào không qua biên.

**`config["configurable"]`** mang đối tượng của lượt (`turn`, không tuần tự hoá được) cạnh `thread_id` và `trace_id`: LangGraph chỉ chép kiểu nguyên thuỷ vào metadata của checkpoint, nên đối tượng
của lượt không vào bảng (test đọc bảng). **Không** để văn bản người dùng, tên slot hay giá trị vào `configurable` — mọi khoá nguyên thuỷ ở đó vào `checkpoints.metadata`.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END as _END
from langgraph.graph import START as _START
from langgraph.graph import StateGraph
from langgraph.types import Command, interrupt

from bo19.orchestrator.runtime.node_boundary import guard

START, END = _START, _END
NodeFn = Callable[..., dict[str, Any]]
RouteFn = Callable[..., str]


INTERRUPTED = "__interrupt__"  # khoá LangGraph đặt vào kết quả `invoke` khi graph dừng ở một `interrupt`


def wait_for_human(payload: Mapping[str, Any]) -> Any:
    """Dừng graph tại node gọi (`interrupt`) cho tới khi có giá trị resume; trả giá trị đó. Lần đầu chạy tới đây graph dừng và checkpoint được ghi; resume chạy lại node từ đầu và `interrupt` trả giá trị.

    Payload và giá trị resume chỉ mang id, mã, tên (mục Checkpointer và PII của 03-agents.md). **Node gọi hàm này không được có tác động nào TRƯỚC lời gọi** — resume chạy lại node từ đầu.
    """
    return interrupt(dict(payload))


@dataclass(frozen=True)
class Snapshot:
    """Trạng thái của một thread: state, node sẽ chạy kế tiếp, và node đang chờ ở `interrupt` (nếu có)."""

    values: dict[str, Any] | None
    next_nodes: tuple[str, ...]
    waiting_at: str | None
    has_tasks: bool = False  # checkpoint còn task — kể cả task ĐÃ XONG mà superstep chưa được ghi thành checkpoint mới (xem `pending`)

    @property
    def exists(self) -> bool:
        return bool(self.values)

    @property
    def pending(self) -> bool:
        """Còn việc để chạy tiếp từ checkpoint: có node kế, **hoặc** có task đã xong mà kết quả (pending writes) chưa thành checkpoint. Tiến trình bị `SIGKILL` ngay sau khi một node xong và trước khi
        checkpoint kế tiếp được ghi để lại đúng trạng thái này: `next` rỗng nhưng graph CHƯA kết thúc (B9b1, test tiến trình thật)."""
        return self.exists and (bool(self.next_nodes) or self.has_tasks)

    @property
    def finished(self) -> bool:
        return self.exists and not self.pending


class Graph:
    """Mặt tiền hẹp của một graph đã biên dịch."""

    def __init__(self, compiled: Any) -> None:
        self._compiled = compiled

    def invoke(self, thread_id: str, state_input: Mapping[str, Any] | None, *, configurable: Mapping[str, Any], recursion_limit: int = 40) -> dict[str, Any]:
        """`state_input = None`: tiếp tục từ checkpoint cuối của thread (một lần chạy dở bị ngắt) — không bắt đầu lại từ START."""
        config = {"configurable": {**configurable, "thread_id": thread_id}, "recursion_limit": recursion_limit}
        return dict(self._compiled.invoke(None if state_input is None else dict(state_input), config))

    def resume(self, thread_id: str, value: Any, *, configurable: Mapping[str, Any], recursion_limit: int = 40) -> dict[str, Any]:
        """Trả `value` cho `interrupt` đang chờ của thread rồi chạy tiếp. Giá trị resume chỉ mang id (ADR-008)."""
        config = {"configurable": {**configurable, "thread_id": thread_id}, "recursion_limit": recursion_limit}
        return dict(self._compiled.invoke(Command(resume=value), config))

    def values(self, thread_id: str) -> dict[str, Any] | None:
        """State hiện có của thread, hoặc `None` nếu thread chưa có checkpoint nào."""
        snapshot = self._compiled.get_state({"configurable": {"thread_id": thread_id}})
        return dict(snapshot.values) if snapshot.values else None

    def snapshot(self, thread_id: str) -> Snapshot:
        snap = self._compiled.get_state({"configurable": {"thread_id": thread_id}})
        waiting = next((t.name for t in snap.tasks if getattr(t, "interrupts", None)), None)
        return Snapshot(dict(snap.values) if snap.values else None, tuple(snap.next), waiting, bool(snap.tasks))


class GraphBuilder:
    def __init__(self, state_schema: type) -> None:
        self._graph = StateGraph(state_schema)
        self._names: set[str] = set()

    def node(self, name: str, fn: NodeFn) -> "GraphBuilder":
        if name in self._names:
            raise ValueError(f"node trùng tên: {name}")
        self._names.add(name)
        self._graph.add_node(name, guard(name, fn))  # biên node: không có đường dựng node nào không qua `guard`
        return self

    def edge(self, source: str, target: str) -> "GraphBuilder":
        self._graph.add_edge(source, target)
        return self

    def route(self, source: str, router: RouteFn, targets: Mapping[str, str]) -> "GraphBuilder":
        """Cạnh điều kiện: `router(state, config)` trả khoá của `targets`. Router cũng đi qua biên node."""
        self._graph.add_conditional_edges(source, guard(f"route:{source}", router), dict(targets))
        return self

    def compile(self, checkpointer: BaseCheckpointSaver) -> Graph:
        return Graph(self._graph.compile(checkpointer=checkpointer))

