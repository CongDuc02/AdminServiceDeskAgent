"""Giành, gia hạn lease và kết thúc job cho `queue_worker` (ADR-004, ADR-010; mục Retry, backoff và job lỗi vĩnh viễn của 11-ops.md; mục Vận hành của 04-data.md).

**Không sinh `audit_event`:** đây là sổ sách kỹ thuật của hàng đợi, thuộc danh sách miễn (A-055) — thao tác nghiệp vụ gây ra job đã ghi `audit_event` của chính nó (`request_submit`). Enqueue ở `kernel.enqueue`.
Không có `ToolContext`: không người thật nào gọi các hàm này; chỉ `queue_worker`. Mọi hàm là một giao dịch ngắn trên `Pool`; đồng hồ là của DB (`now()`), không của tiến trình.

**Vòng đời một lượt thử (PO, 2026-10-13):** `attempts` tăng **lúc giành**. `succeed` → `SUCCEEDED`. `fail` → còn lượt thì về `QUEUED` với `run_after = now + max(base × 2^attempts, retry_after)`, hết lượt thì `FAILED`;
`retry_after` vượt WV-19 thì `FAILED` ngay với `PROVIDER_RATE_LIMITED`. **`release` (drain) không tiêu lượt thử** (`attempts − 1`). **Lease hết hạn tính một lượt thử** (`reclaim_expired`).

**Hàng rào chủ lease (B8b, PO 2026-10-13):** mỗi lần giành, DB sinh một `lease_id` (`gen_random_uuid()`) mới; mọi thao tác sau lúc giành so `lease_id` của `ClaimedJob` — không so `locked_at` (đồng hồ lùi, hai lần giành cùng mốc) và không so `locked_by` (chỉ để chẩn đoán).
Worker đã mất lease (đã bị `reclaim_expired`, hay đã `release` rồi được giành lại — kể cả bởi chính `worker_id` đó) không `succeed`, `fail`, `release` hay `heartbeat` đè được; các hàm trả `False`/`None`. Mọi lối thoát khỏi `RUNNING` đặt `lease_id = NULL`. Worker chỉ giành loại job mà tiến trình đó có handler (`job_types`).
"""
from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from bo19.config import working_values as wv
from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work

_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")  # khớp ck_job_error_code
RATE_LIMITED = "PROVIDER_RATE_LIMITED"
LEASE_EXPIRED = "LEASE_EXPIRED"
_BACKOFF_CAP_S = 24 * 3600  # chặn trên cho `base × 2^attempts` — `max_attempts` nhỏ nên không bao giờ chạm, nhưng một giá trị cấu hình lệch không được đẩy `run_after` xa vô hạn


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    job_type: str
    payload: dict[str, Any]
    subject_document_id: uuid.UUID | None
    dedupe_key: str | None
    attempts: int
    max_attempts: int
    locked_by: str
    locked_at: dt.datetime  # chỉ để chẩn đoán — KHÔNG phải token hàng rào
    lease_id: uuid.UUID  # token hàng rào: DB sinh ngẫu nhiên mỗi lần giành


@dataclass(frozen=True)
class FailOutcome:
    status: str  # QUEUED | FAILED
    last_error_code: str


@dataclass(frozen=True)
class Reclaimed:
    id: uuid.UUID
    job_type: str
    status: str  # QUEUED | FAILED


def backoff_seconds(job_type: str, attempts: int) -> int:
    return min(_BACKOFF_CAP_S, wv.JOB_BACKOFF_BASE_S[job_type] * 2 ** attempts)


_CLAIM = (
    "WITH next AS (SELECT id FROM job WHERE status = 'QUEUED' AND run_after <= now() AND job_type = ANY(%(types)s) ORDER BY run_after, enqueued_at, id LIMIT 1 FOR UPDATE SKIP LOCKED) "
    "UPDATE job j SET status = 'RUNNING', attempts = j.attempts + 1, locked_by = %(worker)s, locked_at = now(), lease_id = gen_random_uuid(), lease_expires_at = now() + make_interval(secs => %(lease)s), "
    "started_at = now(), finished_at = NULL FROM next WHERE j.id = next.id "
    "RETURNING j.id, j.job_type, j.payload, j.subject_document_id, j.dedupe_key, j.attempts, j.max_attempts, j.locked_by, j.locked_at, j.lease_id"
)


def claim(pool: Pool, *, worker_id: str, job_types: Collection[str], lease_s: float = wv.JOB_LEASE_S) -> ClaimedJob | None:
    """Giành job `QUEUED` đã tới `run_after`, cũ nhất trước, trong số `job_types`. `FOR UPDATE SKIP LOCKED`: hai worker không bao giờ giành cùng một job. Không có thì `None`."""
    types = sorted(set(job_types))
    if not types:
        return None  # không handler nào thì không giành gì — job loại khác vẫn `QUEUED`
    with pool.acquire() as conn, unit_of_work(conn):
        row = conn.execute(_CLAIM, {"types": types, "worker": worker_id, "lease": lease_s}).fetchone()
    return ClaimedJob(*row) if row else None


def heartbeat(pool: Pool, job: ClaimedJob, *, lease_s: float = wv.JOB_LEASE_S) -> bool:
    """Gia hạn lease. `False` nếu không còn là chủ lease **hoặc** lease đã hết hạn (worker phải dừng việc, không ghi gì nữa)."""
    with pool.acquire() as conn, unit_of_work(conn):
        row = conn.execute("UPDATE job SET lease_expires_at = now() + make_interval(secs => %s) WHERE id = %s AND status = 'RUNNING' AND lease_id = %s "
                           "AND lease_expires_at > now() RETURNING id", (lease_s, job.id, job.lease_id)).fetchone()
    return row is not None


def succeed(pool: Pool, job: ClaimedJob) -> bool:
    with pool.acquire() as conn, unit_of_work(conn):
        row = conn.execute("UPDATE job SET status = 'SUCCEEDED', finished_at = now(), locked_at = NULL, lease_id = NULL, lease_expires_at = NULL, last_error_code = NULL "
                           "WHERE id = %s AND status = 'RUNNING' AND lease_id = %s RETURNING id", (job.id, job.lease_id)).fetchone()
    return row is not None


def fail(pool: Pool, job: ClaimedJob, code: str, *, retry_after_s: int | None = None) -> FailOutcome | None:
    """Một lượt thử hỏng. `None` nếu không còn là chủ lease. `retry_after_s` — của 429: lấy `max` với backoff; vượt WV-19 thì `FAILED` ngay với `PROVIDER_RATE_LIMITED`."""
    if not _CODE.match(code):
        raise ValueError("code")  # chỉ mã — không thông điệp, không giá trị
    if retry_after_s is not None and retry_after_s < 0:
        raise ValueError("retry_after_s")
    give_up = retry_after_s is not None and retry_after_s > wv.LLM_RETRY_AFTER_CEILING_SECONDS
    final = give_up or job.attempts >= job.max_attempts
    stored = RATE_LIMITED if give_up else code
    with pool.acquire() as conn, unit_of_work(conn):
        if final:
            row = conn.execute("UPDATE job SET status = 'FAILED', finished_at = now(), locked_at = NULL, lease_id = NULL, lease_expires_at = NULL, last_error_code = %s "
                               "WHERE id = %s AND status = 'RUNNING' AND lease_id = %s RETURNING id", (stored, job.id, job.lease_id)).fetchone()
        else:
            delay = max(backoff_seconds(job.job_type, job.attempts), retry_after_s or 0)
            row = conn.execute("UPDATE job SET status = 'QUEUED', run_after = now() + make_interval(secs => %s), locked_at = NULL, lease_id = NULL, lease_expires_at = NULL, last_error_code = %s "
                               "WHERE id = %s AND status = 'RUNNING' AND lease_id = %s RETURNING id", (delay, stored, job.id, job.lease_id)).fetchone()
    if row is None:
        return None
    return FailOutcome("FAILED" if final else "QUEUED", stored)


def release(pool: Pool, job: ClaimedJob) -> bool:
    """Drain khi `SIGTERM`: trả job về hàng đợi, thả lease, **không tiêu một lượt thử**. `run_after` không đổi — job chạy lại ngay khi có worker."""
    with pool.acquire() as conn, unit_of_work(conn):
        row = conn.execute("UPDATE job SET status = 'QUEUED', attempts = attempts - 1, locked_at = NULL, lease_id = NULL, lease_expires_at = NULL WHERE id = %s AND status = 'RUNNING' "
                           "AND lease_id = %s RETURNING id", (job.id, job.lease_id)).fetchone()
    return row is not None


def reclaim_expired(pool: Pool) -> list[Reclaimed]:
    """Job `RUNNING` đã hết lease — worker chết hay treo. Tính **một lượt thử** (`attempts` đã tăng lúc giành): hết lượt thì `FAILED`, còn thì về `QUEUED` sau backoff. `SKIP LOCKED`: nhiều worker cùng gọi vẫn an toàn."""
    out: list[Reclaimed] = []
    with pool.acquire() as conn, unit_of_work(conn):
        rows = conn.execute("SELECT id, job_type, attempts, max_attempts FROM job WHERE status = 'RUNNING' AND lease_expires_at < now() ORDER BY lease_expires_at, id FOR UPDATE SKIP LOCKED").fetchall()
        for job_id, job_type, attempts, max_attempts in rows:
            if attempts >= max_attempts:
                conn.execute("UPDATE job SET status = 'FAILED', finished_at = now(), locked_at = NULL, lease_id = NULL, lease_expires_at = NULL, last_error_code = %s WHERE id = %s", (LEASE_EXPIRED, job_id))
                out.append(Reclaimed(job_id, job_type, "FAILED"))
            else:
                conn.execute("UPDATE job SET status = 'QUEUED', run_after = now() + make_interval(secs => %s), locked_at = NULL, lease_id = NULL, lease_expires_at = NULL, last_error_code = %s WHERE id = %s",
                             (backoff_seconds(job_type, attempts), LEASE_EXPIRED, job_id))
                out.append(Reclaimed(job_id, job_type, "QUEUED"))
    return out
