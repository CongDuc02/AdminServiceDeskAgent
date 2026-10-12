"""Lối dựng graph duy nhất: mọi node đi qua biên node (mục Cây backend và Triển khai ở B6b của 06-structure.md; contract `graph-library`).

Chỉ `orchestrator.runtime` import `langgraph`. `intake_graph` khai node và cạnh qua `GraphBuilder` — không chạm LangGraph — và nhận lại một `Graph` có mặt tiền hẹp: `invoke` trên một thread,
đọc state hiện có của thread. `GraphBuilder.node` bọc node bằng `node_boundary.guard` — không có đường dựng node nào không qua biên.

**`config["configurable"]`** mang đối tượng của lượt (`turn`, không tuần tự hoá được) cạnh `thread_id` và `trace_id`: LangGraph chỉ chép kiểu nguyên thuỷ vào metadata của checkpoint, nên đối tượng
của lượt không vào bảng (test đọc bảng). **Không** để văn bản người dùng, tên slot hay giá trị vào `configurable` — mọi khoá nguyên thuỷ ở đó vào `checkpoints.metadata`.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END as _END
from langgraph.graph import START as _START
from langgraph.graph import StateGraph

from bo19.orchestrator.runtime.node_boundary import guard

START, END = _START, _END
NodeFn = Callable[..., dict[str, Any]]
RouteFn = Callable[..., str]


class Graph:
    """Mặt tiền hẹp của một graph đã biên dịch."""

    def __init__(self, compiled: Any) -> None:
        self._compiled = compiled

    def invoke(self, thread_id: str, state_input: Mapping[str, Any], *, configurable: Mapping[str, Any], recursion_limit: int = 40) -> dict[str, Any]:
        config = {"configurable": {**configurable, "thread_id": thread_id}, "recursion_limit": recursion_limit}
        return dict(self._compiled.invoke(dict(state_input), config))

    def values(self, thread_id: str) -> dict[str, Any] | None:
        """State hiện có của thread, hoặc `None` nếu thread chưa có checkpoint nào."""
        snapshot = self._compiled.get_state({"configurable": {"thread_id": thread_id}})
        return dict(snapshot.values) if snapshot.values else None


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

