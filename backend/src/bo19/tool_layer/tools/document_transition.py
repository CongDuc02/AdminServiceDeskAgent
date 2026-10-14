"""Tool `document_transition` — phần của tác nhân hệ thống ở **trước cổng 1** (mục Tool Registry của 03-agents.md; ADR-039): **tạo `DRAFT`** và **`DRAFT → PENDING_APPROVAL`**.

Hai hàm, mỗi hàm một giao dịch, mỗi hàm một `audit_event`:

- `document_create_draft` — tạo `document` ở `DRAFT` với **id do người gọi cho** (`uuid5` theo `request`, ADR-039) nên gọi lại là idempotent. Ghim `operating_mode` hiện hành lúc tạo (INV-01, D-009) và
  `requires_seal`/`seal_type` theo mặc định của `request_type` (`SEAL_UNDETERMINED` ở `review_readiness_check` nếu mặc định chưa có). Yêu cầu `request` đang `SUBMITTED` (D-010: `document` được tạo tại thời điểm
  `request` sang `SUBMITTED`). Gọi lại với `document` đã có thì trả nó, không ghi gì.
- `document_submit_for_review` — **tự chạy lại** `review_readiness_check` trong giao dịch của nó (`NOT_READY` nếu trượt: node không bỏ qua được), rồi: `document` `DRAFT → PENDING_APPROVAL` (qua `kernel.transition`),
  gắn `current_draft_render_id` (bản nháp đúng `document`, đúng vòng, `render_kind = DRAFT`), mở `approval_step` `CONTENT_REVIEW` `OPEN` (thao tác cổng của B9b cần nó cho `decision_record`), và `request`
  `SUBMITTED → IN_REVIEW` nếu chưa ở đó — một giao dịch. Đã ở `PENDING_APPROVAL` với đúng bản nháp đó thì trả như đã làm (idempotent), không mở thêm bước.

Lỗi: `NOT_DRAFT`, `NOT_READY` (kèm mã), `REQUEST_NOT_SUBMITTED`, `DOCUMENT_CONFLICT`, `DRAFT_RENDER_NOT_FOUND`, `ILLEGAL_TRANSITION` (từ kernel). Chỉ tác nhân hệ thống.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from bo19.persistence.pool import Pool
from bo19.persistence.read import current_operating_mode
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.kernel import audit
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_system
from bo19.tool_layer.kernel.transition import transition
from bo19.tool_layer.tools._common import ToolError
from bo19.tool_layer.tools.render_values import Issue, build_values


class RequestNotSubmitted(ToolError):
    code = "REQUEST_NOT_SUBMITTED"


class DocumentConflict(ToolError):
    code = "DOCUMENT_CONFLICT"  # `document_id` đã là `document` của `request` khác, hoặc `request` đã có `document` mang id khác


class NotDraft(ToolError):
    code = "NOT_DRAFT"


class DocumentNotFound(ToolError):
    code = "DOCUMENT_NOT_FOUND"


class DraftRenderNotFound(ToolError):
    code = "DRAFT_RENDER_NOT_FOUND"


class NotReady(ToolError):
    code = "NOT_READY"

    def __init__(self, issues: tuple[Issue, ...]) -> None:
        super().__init__()
        self.issues = issues  # (mã, tên biến) — không giá trị

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(sorted({i.code for i in self.issues}))


@dataclass(frozen=True)
class DraftCreated:
    document_id: uuid.UUID
    created: bool
    operating_mode: str
    template_version_id: uuid.UUID
    revision_round: int


@dataclass(frozen=True)
class Submitted:
    document_id: uuid.UUID
    approval_step_id: uuid.UUID
    render_id: uuid.UUID
    already: bool  # đã ở `PENDING_APPROVAL` với đúng bản nháp này


def document_create_draft(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID, request_id: uuid.UUID, template_version_id: uuid.UUID) -> DraftCreated:
    require_system(ctx)
    with pool.acquire() as conn:
        mode = current_operating_mode(conn).mode  # đọc TRƯỚC giao dịch ghi: `read_only` mở giao dịch riêng
    with pool.acquire() as conn, unit_of_work(conn):
        req = conn.execute("SELECT r.status, t.requires_seal_default, t.seal_type_default FROM request r JOIN request_type t ON t.code = r.request_type_code WHERE r.id = %s FOR UPDATE", (request_id,)).fetchone()
        if req is None:
            raise DocumentConflict
        status, requires_seal, seal_type = req
        existing = conn.execute("SELECT id, request_id, template_version_id, operating_mode, revision_round FROM document WHERE id = %s OR request_id = %s", (document_id, request_id)).fetchall()
        if existing:
            doc = next((r for r in existing if r[0] == document_id), None)
            if doc is None or doc[1] != request_id or len(existing) > 1:
                raise DocumentConflict
            return DraftCreated(doc[0], False, doc[3], doc[2], doc[4])
        if status != "SUBMITTED":
            raise RequestNotSubmitted
        conn.execute("INSERT INTO document (id, request_id, template_version_id, status, operating_mode, requires_seal, seal_type) VALUES (%s, %s, %s, 'DRAFT', %s, %s, %s)",
                     (document_id, request_id, template_version_id, mode, requires_seal, seal_type))
        audit.record(conn, ctx, action="document.create_draft", entity_type="document", entity_id=document_id, document_id=document_id, request_id=request_id,
                     payload={"operating_mode": mode, "template_version_id": template_version_id, "requires_seal": requires_seal})
    return DraftCreated(document_id, True, mode, template_version_id, 0)


def document_submit_for_review(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID, draft_pdf_key: str) -> Submitted:
    require_system(ctx)
    with pool.acquire() as conn, unit_of_work(conn):
        doc = conn.execute("SELECT status, revision_round, request_id, current_draft_render_id FROM document WHERE id = %s FOR UPDATE", (document_id,)).fetchone()
        if doc is None:
            raise DocumentNotFound
        status, round_, request_id, current_render = doc
        render = conn.execute("SELECT id FROM document_render WHERE document_id = %s AND pdf_object_key = %s AND render_kind = 'DRAFT' AND revision_round = %s",
                              (document_id, draft_pdf_key, round_)).fetchone()
        if render is None:
            raise DraftRenderNotFound
        render_id = render[0]
        if status == "PENDING_APPROVAL" and current_render == render_id:
            step = conn.execute("SELECT id FROM approval_step WHERE document_id = %s AND step_kind = 'CONTENT_REVIEW' AND revision_round = %s ORDER BY opened_at DESC LIMIT 1", (document_id, round_)).fetchone()
            return Submitted(document_id, step[0], render_id, already=True)
        if status != "DRAFT":
            raise NotDraft
        built = build_values(conn, document_id)
        if built.issues:
            raise NotReady(built.issues)
        transition(conn, "document", document_id, to="PENDING_APPROVAL", expected_from="DRAFT")
        conn.execute("UPDATE document SET current_draft_render_id = %s WHERE id = %s", (render_id, document_id))
        step_id = uuid.uuid4()
        conn.execute("INSERT INTO approval_step (id, document_id, step_kind, level, revision_round, status) VALUES (%s, %s, 'CONTENT_REVIEW', 1, %s, 'OPEN')", (step_id, document_id, round_))
        transition(conn, "request", request_id, to="IN_REVIEW")  # đã ở IN_REVIEW (vòng FREE_CONTENT) thì không làm gì
        audit.record(conn, ctx, action="document.submit_for_review", entity_type="document", entity_id=document_id, document_id=document_id, request_id=request_id,
                     payload={"revision_round": round_, "render_id": render_id, "approval_step_id": step_id})
    return Submitted(document_id, step_id, render_id, already=False)
