"""Handler của job `finalize_issue` (B9b2, ADR-041): payload chỉ mang `document_id` và `decision_record_id` (lệnh phát hành `ISSUE_ORDERED`) — do `document_issue` enqueue trong cùng giao dịch với lệnh.

Quyền được kiểm **một lần, ở lúc enqueue** (mục 4.2 của 09-security.md). Job chạy ít nhất một lần (ADR-004) và chạy lại an toàn ở mọi điểm chết (bảng ở ADR-041 mục 5).

**Bỏ cuộc (Sprint 1, chưa có `halt_for_human`):** khi `RenderFailed` làm job sắp `FAILED` — `permanent`, hoặc `attempts >= max_attempts` (đúng điều kiện `final` của dispatcher) — và lỗi không phải `JOB_CANCELLED`
(drain/mất lease không phải bỏ cuộc), handler chuyển số `ASSIGNED` đang mở của `document` sang `VOIDED` **trước** khi ném `JobFailure`: lý do = mã lỗi vĩnh viễn, hoặc `ISSUE_RETRIES_EXHAUSTED` khi hết lượt vì lỗi tạm.
Lỗi tạm còn lượt thì **không** huỷ số — lần thử sau dùng lại chính số đó. Chỉ mã; không bao giờ thông điệp.
"""
from __future__ import annotations

import uuid

from bo19.observability.log import get_logger
from bo19.orchestrator.runner import DocumentRunner, RenderFailed
from bo19.queue_worker.dispatcher import Handler, JobContext, JobFailure
from bo19.tool_layer import jobs

JOB_TYPE = "finalize_issue"
RETRIES_EXHAUSTED = "ISSUE_RETRIES_EXHAUSTED"
JOB_CANCELLED = "JOB_CANCELLED"

log = get_logger("bo19.queue_worker.finalize_issue")


def make_finalize_issue_handler(runner: DocumentRunner) -> Handler:
    def handle(job: jobs.ClaimedJob, ctx: JobContext) -> None:
        try:
            document_id = uuid.UUID(str(job.payload["document_id"]))
            decision_id = uuid.UUID(str(job.payload["decision_record_id"]))
        except (KeyError, ValueError):
            raise JobFailure("SYSTEM_DEFECT", permanent=True) from None  # payload sai hình: lỗi lập trình ở chỗ enqueue
        try:
            runner.run_finalize_issue(document_id=document_id, decision_record_id=decision_id, cancel=ctx.cancel)
        except RenderFailed as e:
            exhausted = not e.permanent and job.attempts >= job.max_attempts
            if (e.permanent or exhausted) and e.reason_code != JOB_CANCELLED:
                reason = RETRIES_EXHAUSTED if exhausted else e.reason_code
                voided = runner.abandon_issue(document_id=document_id, reason_code=reason)
                log.warning("ISSUE_ABANDONED", reason_code=reason, number_voided=voided is not None)
            raise JobFailure(e.reason_code, retry_after_s=e.retry_after_s, permanent=e.permanent) from None

    return handle
