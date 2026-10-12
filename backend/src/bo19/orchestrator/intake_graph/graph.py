"""Cạnh của `intake_graph` — sơ đồ ở mục `intake_graph` của 03-agents.md (Sprint 1: không có `embed_query`, `procedure_retrieval`, `select_procedure_passages`).

```
START → load_turn ─ resume ─→ resume_context ─────────────────────────────────────────────┐
                  └ classify → classify_intent → route_intent ─ clarify → ask_clarification ┤
                                                             ├ reply (ngoài phạm vi) ───────┤
                                                             ├ open ─→ open_request ─┐       │
                                                             └ extract ──────────────┴→ extract_slots → propose_values → check_completeness
                                                                                  ask ← ┤                                        └ offer
                                                                              ask_missing / offer_submit ───────────────────────┘
                                                                                                          → render_reply → END
```
Node dựng qua `GraphBuilder` — mọi node qua biên node (`runtime.node_boundary`). `intake_graph` không import `langgraph`: kiểu của checkpointer là `Any` ở đây.
"""
from __future__ import annotations

from typing import Any

from bo19.orchestrator.intake_graph.nodes import make_nodes
from bo19.orchestrator.intake_graph.turn import IntakeDeps
from bo19.orchestrator.runtime.builder import END, START, Graph, GraphBuilder
from bo19.orchestrator.state import IntakeState

NODE_NAMES = ("load_turn", "classify_intent", "route_intent", "ask_clarification", "open_request", "extract_slots", "propose_values", "check_completeness",
              "ask_missing", "offer_submit", "resume_context", "render_reply")


def build_intake_graph(deps: IntakeDeps, checkpointer: Any) -> Graph:
    n = make_nodes(deps)
    b = GraphBuilder(IntakeState)
    for name in NODE_NAMES:
        b.node(name, n[name])
    b.edge(START, "load_turn")
    b.route("load_turn", n["route_load"], {"resume": "resume_context", "classify": "classify_intent"})
    b.edge("classify_intent", "route_intent")
    b.route("route_intent", n["route_after_intent"], {"clarify": "ask_clarification", "reply": "render_reply", "open": "open_request", "extract": "extract_slots"})
    b.edge("open_request", "extract_slots")
    b.edge("extract_slots", "propose_values")
    b.edge("propose_values", "check_completeness")
    b.route("check_completeness", n["route_after_check"], {"ask": "ask_missing", "offer": "offer_submit"})
    for last in ("ask_clarification", "ask_missing", "offer_submit", "resume_context"):
        b.edge(last, "render_reply")
    b.edge("render_reply", END)
    return b.compile(checkpointer)
