"""Handler của job `resume_document_graph` (B9b1, ADR-040 mục 5; ADR-010): payload chỉ mang `document_id` và `decision_record_id` — do thao tác cổng enqueue trong cùng giao dịch với quyết định.

Quyền được kiểm **một lần, ở lúc enqueue** (mục 4.2 của 09-security.md): job không tự chọn làm gì, chỉ tiếp tục `document_graph` đã dừng ở đúng một `interrupt` với dữ liệu đã ghi. **Thử lại an toàn:** `resume_document` chỉ
đánh thức đúng điểm chờ mà loại quyết định đánh thức, và no-op khi việc đã xong. **Lỗi:** `RenderFailed` đổi thành `JobFailure(reason_code)` — `permanent` thì job `FAILED` ngay (ví dụ `NO_ELIGIBLE_SIGNER`), còn lại theo backoff.
Chỉ mã; không bao giờ thông điệp.
"""
from __future__ import annotations

import uuid

from bo19.orchestrator.runner import DocumentRunner, RenderFailed
from bo19.queue_worker.dispatcher import Handler, JobContext, JobFailure
from bo19.tool_layer import jobs

JOB_TYPE = "resume_document_graph"


def make_resume_document_graph_handler(runner: DocumentRunner) -> Handler:
    def handle(job: jobs.ClaimedJob, ctx: JobContext) -> None:
        try:
            document_id = uuid.UUID(str(job.payload["document_id"]))
            decision_id = uuid.UUID(str(job.payload["decision_record_id"]))
        except (KeyError, ValueError):
            raise JobFailure("SYSTEM_DEFECT", permanent=True) from None  # payload sai hình: lỗi lập trình ở chỗ enqueue, thử lại không đổi được
        try:
            runner.resume_document(document_id=document_id, decision_record_id=decision_id, cancel=ctx.cancel)
        except RenderFailed as e:
            raise JobFailure(e.reason_code, retry_after_s=e.retry_after_s, permanent=e.permanent) from None

    return handle
