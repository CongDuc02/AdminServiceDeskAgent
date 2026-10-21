"""Đăng ký `job_type → handler` (mục Cây backend của 06-structure.md): handler gọi `runner` của `orchestrator`, thao tác của `tool_layer` hoặc `ai_gateway` (embedding của `procedure_ingest`).

`queue_worker` chỉ giành loại job có handler (`tool_layer.jobs.claim(job_types=…)`), nên job chưa có handler — `finalize_issue` (B9b2) — vẫn `QUEUED`, không bị giành rồi bỏ rơi.
**B9a:** `render_document` có handler, đăng ký ở `build_handlers` khi composition root có `DocumentRunner` (cần object storage và khoá LLM); thiếu thì không đăng ký — job vẫn `QUEUED`, như ở B8a.
**B9b1:** `resume_document_graph` cùng điều kiện đăng ký.
Thêm handler = thêm một dòng ở đây cùng test của loại job đó.
"""
from __future__ import annotations

from bo19.orchestrator.runner import DocumentRunner
from bo19.queue_worker.dispatcher import Handler
from bo19.queue_worker.handlers.render_document import JOB_TYPE as RENDER_DOCUMENT
from bo19.queue_worker.handlers.render_document import make_render_document_handler
from bo19.queue_worker.handlers.resume_document_graph import JOB_TYPE as RESUME_DOCUMENT_GRAPH
from bo19.queue_worker.handlers.resume_document_graph import make_resume_document_graph_handler

DEFAULT_HANDLERS: dict[str, Handler] = {}  # không phụ thuộc nào — giữ cho nơi gọi cũ; production dùng `build_handlers`


def build_handlers(*, document_runner: DocumentRunner | None) -> dict[str, Handler]:
    handlers: dict[str, Handler] = dict(DEFAULT_HANDLERS)
    if document_runner is not None:
        handlers[RENDER_DOCUMENT] = make_render_document_handler(document_runner)
        handlers[RESUME_DOCUMENT_GRAPH] = make_resume_document_graph_handler(document_runner)
    return handlers
