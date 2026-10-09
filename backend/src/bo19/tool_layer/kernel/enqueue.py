"""Đưa một job vào hàng đợi **trong giao dịch của thao tác gọi nó** (ADR-004, ADR-010; mục Retry, backoff và job lỗi vĩnh viễn của 11-ops.md).

Thao tác nghiệp vụ và job của nó commit cùng nhau hoặc lăn cùng nhau: không có job mồ côi cho việc không xảy ra, không có việc xảy ra mà thiếu job. `enqueue` **không** tự sinh `audit_event`:
nó là một bước của thao tác gọi (thao tác đó ghi `audit_event` của chính nó); giành, gia hạn lease và kết thúc job là việc của `tool_layer.jobs`, thuộc danh sách miễn (A-055).

`payload` chỉ mang tham chiếu — id, mã, tên — cùng luật với `audit_event.payload` (`audit.check_payload`; mục Bảng chi tiết của 04-data.md: "`payload` chỉ mang tham chiếu, không mang giá trị").
`max_attempts` theo `job_type` ở `config.working_values.JOB_MAX_ATTEMPTS` (11-ops.md, nhãn "chưa hiệu chỉnh").

**Idempotent theo `dedupe_key`:** chỉ một job `QUEUED` hay `RUNNING` cho mỗi (`job_type`, `dedupe_key`) (`uq_job_dedupe_pending`). Gọi lại khi job đó còn sống trả lại chính nó, `created = False`.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass

import psycopg

from bo19.config import working_values as wv
from bo19.tool_layer.kernel.audit import check_payload
from bo19.tool_layer.kernel.context import KernelError, require_transaction

_NEEDS_DOCUMENT = frozenset({"resume_document_graph", "finalize_issue"})  # khớp `ck_job_document_subject`


class UnknownJobType(KernelError):
    code = "UNKNOWN_JOB_TYPE"


class JobSubjectMissing(KernelError):
    code = "JOB_SUBJECT_MISSING"


class EnqueueConflict(KernelError):
    code = "ENQUEUE_CONFLICT"  # job trùng khoá cứ biến mất giữa hai câu lệnh — không xảy ra trong vận hành bình thường


@dataclass(frozen=True)
class Enqueued:
    job_id: uuid.UUID
    created: bool


_INSERT = (
    "INSERT INTO job (id, job_type, payload, subject_document_id, dedupe_key, max_attempts, run_after) "
    "VALUES (%s, %s, %s::jsonb, %s, %s, %s, COALESCE(%s, now())) "
    "ON CONFLICT (job_type, dedupe_key) WHERE dedupe_key IS NOT NULL AND status IN ('QUEUED', 'RUNNING') DO NOTHING RETURNING id"
)


def enqueue(conn: psycopg.Connection, *, job_type: str, payload: dict | None = None, subject_document_id: uuid.UUID | None = None,
            dedupe_key: str | None = None, run_after: dt.datetime | None = None) -> Enqueued:
    require_transaction(conn)
    max_attempts = wv.JOB_MAX_ATTEMPTS.get(job_type)
    if max_attempts is None:
        raise UnknownJobType(job_type[:40])
    if job_type in _NEEDS_DOCUMENT and subject_document_id is None:
        raise JobSubjectMissing(job_type)
    body = check_payload(payload or {})
    if not isinstance(body, dict):
        raise KernelError("payload")
    if dedupe_key is not None:
        check_payload(dedupe_key)  # cùng khuôn chuỗi ngắn không khoảng trắng
    text = json.dumps(body, ensure_ascii=True, separators=(",", ":"))
    for _ in range(2):
        job_id = uuid.uuid4()
        row = conn.execute(_INSERT, (job_id, job_type, text, subject_document_id, dedupe_key, max_attempts, run_after)).fetchone()
        if row is not None:
            return Enqueued(row[0], True)
        existing = conn.execute("SELECT id FROM job WHERE job_type = %s AND dedupe_key = %s AND status IN ('QUEUED', 'RUNNING')", (job_type, dedupe_key)).fetchone()
        if existing is not None:
            return Enqueued(existing[0], False)
    raise EnqueueConflict(job_type)
