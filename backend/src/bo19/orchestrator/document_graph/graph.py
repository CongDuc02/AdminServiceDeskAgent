"""Cạnh của `document_graph` — lát Sprint 1 (B9a), sơ đồ ở mục 6.4.1 của 03-agents.md.

```
START → prepare_draft → draft_free_content → validate_free_content ─ redraft → draft_free_content   (sinh lại đúng một lần mỗi biến, rồi `FREE_CONTENT_INVALID`)
                                                                   └ render ──→ render_draft → check_review_readiness → submit_for_review
                                                                                  → await_content_review (INTERRUPT, cổng 1) → route_review → END
```
Node dựng qua `GraphBuilder` — mọi node qua biên node (`runtime.node_boundary`). `document_graph` không import `langgraph`. **Tên node `interrupt` là contract** (mục Schema state đổi giữa chừng của 03-agents.md):
không đổi `await_content_review` khi còn thread đang chờ ở đó.
"""
from __future__ import annotations

from typing import Any

from bo19.orchestrator.document_graph.nodes import make_nodes
from bo19.orchestrator.document_graph.runtime import DocumentDeps
from bo19.orchestrator.runtime.builder import END, START, Graph, GraphBuilder
from bo19.orchestrator.state import DocumentState

NODE_NAMES = ("prepare_draft", "draft_free_content", "validate_free_content", "render_draft", "check_review_readiness", "submit_for_review", "await_content_review", "route_review")
INTERRUPT_NODE = "await_content_review"
RECURSION_LIMIT = 30


def build_document_graph(deps: DocumentDeps, checkpointer: Any) -> Graph:
    n = make_nodes(deps)
    b = GraphBuilder(DocumentState)
    for name in NODE_NAMES:
        b.node(name, n[name])
    b.edge(START, "prepare_draft")
    b.edge("prepare_draft", "draft_free_content")
    b.edge("draft_free_content", "validate_free_content")
    b.route("validate_free_content", n["route_after_validate"], {"redraft": "draft_free_content", "render": "render_draft"})
    b.edge("render_draft", "check_review_readiness")
    b.edge("check_review_readiness", "submit_for_review")
    b.edge("submit_for_review", "await_content_review")
    b.edge("await_content_review", "route_review")
    b.edge("route_review", END)
    return b.compile(checkpointer)
