"""Handler của job `render_document` (B9a, ADR-039): đọc `request_id` từ payload (chỉ mang id) rồi chạy `DocumentRunner.run_render` — tạo `DRAFT`, chạy `document_graph` tới điểm dừng `await_content_review`.

**Thử lại an toàn:** `run_render` đọc checkpoint — job chạy lại sau khi graph đã chờ ở `interrupt` hoặc đã `END` là no-op; chạy lại sau khi bị ngắt giữa chừng thì tiếp từ checkpoint cuối, không sinh lại biến đã lưu.
**Lỗi:** `RenderFailed` đổi thành `JobFailure(reason_code)` — `permanent` thì job `FAILED` ngay (thử lại không đổi kết quả và tốn lời gọi LLM), còn lại theo backoff của hàng đợi; `retry_after_s` của 429 đi theo.
Chỉ mã; không bao giờ thông điệp (có thể mang giá trị).
"""
from __future__ import annotations

import uuid

from bo19.orchestrator.runner import DocumentRunner, RenderFailed
from bo19.queue_worker.dispatcher import Handler, JobContext, JobFailure
from bo19.tool_layer import jobs

JOB_TYPE = "render_document"


def make_render_document_handler(runner: DocumentRunner) -> Handler:
    def handle(job: jobs.ClaimedJob, ctx: JobContext) -> None:
        try:
            request_id = uuid.UUID(str(job.payload["request_id"]))
        except (KeyError, ValueError):
            raise JobFailure("SYSTEM_DEFECT", permanent=True) from None  # payload sai hình: lỗi lập trình ở chỗ enqueue, thử lại không đổi được
        try:
            runner.run_render(request_id=request_id, cancel=ctx.cancel)
        except RenderFailed as e:
            raise JobFailure(e.reason_code, retry_after_s=e.retry_after_s, permanent=e.permanent) from None

    return handle
