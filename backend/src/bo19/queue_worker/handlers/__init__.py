"""Đăng ký `job_type → handler` (mục Cây backend của 06-structure.md): handler gọi `runner` của `orchestrator`, thao tác của `tool_layer` hoặc `ai_gateway` (embedding của `procedure_ingest`).

**B8a: rỗng.** `queue_worker` chỉ giành loại job có handler (`tool_layer.jobs.claim(job_types=…)`), nên job chưa có handler — `render_document` (B9a), `resume_document_graph`, `finalize_issue` (B9b) — vẫn `QUEUED`, không bị
giành rồi bỏ rơi. Thêm handler = thêm một dòng ở đây cùng test của loại job đó.
"""
from __future__ import annotations

from bo19.queue_worker.dispatcher import Handler

DEFAULT_HANDLERS: dict[str, Handler] = {}
