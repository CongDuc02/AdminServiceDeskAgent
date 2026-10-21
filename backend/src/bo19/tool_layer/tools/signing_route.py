"""Tool `signing_route` — xác định người ký, ghi `signer_employee_id`, `APPROVED → PENDING_SIGNATURE` (mục Tool Registry của 03-agents.md; mục 5 của 08-hitl.md; ADR-040 mục 6; A-099).

Chỉ tác nhân hệ thống; gọi ở `route_signing`, **sau** `render_integrity_check`. Một giao dịch: chọn người ký, đổi trạng thái cùng cột đi kèm (`signer_employee_id` — `ck_document_signer_assigned`), mở bước `SIGNATURE` `OPEN` giao cho người đó,
`audit_event`. Sprint đầu một cấp.

**Quy tắc chọn (A-099):** trong E(`document.sign`, d) — nhân viên đang hoạt động, mang `document.sign`, **không phải người thụ hưởng** — lấy người có `employee_code` nhỏ nhất. E rỗng → `NoEligibleSigner` (kể cả khi chỉ còn
người thụ hưởng mang `document.sign`: đường tự duyệt là Sprint 3, `self_approval_expected` chưa đặt). Idempotent: đã `PENDING_SIGNATURE` thì trả người đã giao, không ghi gì.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.kernel import audit
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import eligible_holders, require_system
from bo19.tool_layer.kernel.transition import transition
from bo19.tool_layer.tools._common import ToolError

PERMISSION = "document.sign"


class NoEligibleSigner(ToolError):
    code = "NO_ELIGIBLE_SIGNER"


class DocumentNotFound(ToolError):
    code = "DOCUMENT_NOT_FOUND"


class NotApproved(ToolError):
    code = "STALE_STATUS"  # `document` không ở `APPROVED` (hay `PENDING_SIGNATURE` đã giao) — cùng mã với kernel: graph sai trạng thái là lỗi hệ thống


@dataclass(frozen=True)
class SigningRouted:
    document_id: uuid.UUID
    signer_employee_id: uuid.UUID
    approval_step_id: uuid.UUID
    already: bool


def signing_route(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID) -> SigningRouted:
    require_system(ctx)
    with pool.acquire() as conn, unit_of_work(conn):
        doc = conn.execute("SELECT status, revision_round, request_id, signer_employee_id FROM document WHERE id = %s FOR UPDATE", (document_id,)).fetchone()
        if doc is None:
            raise DocumentNotFound
        status, round_, request_id, signer = doc
        if status == "PENDING_SIGNATURE":
            step = conn.execute("SELECT id FROM approval_step WHERE document_id = %s AND step_kind = 'SIGNATURE' AND revision_round = %s AND status = 'OPEN'", (document_id, round_)).fetchone()
            if step is None or signer is None:
                raise NotApproved
            return SigningRouted(document_id, signer, step[0], already=True)
        if status != "APPROVED":
            raise NotApproved
        beneficiary = conn.execute("SELECT beneficiary_employee_id FROM request WHERE id = %s", (request_id,)).fetchone()[0]
        holders = eligible_holders(conn, PERMISSION, exclude=beneficiary)
        if not holders:
            raise NoEligibleSigner
        signer = holders[0][0]
        transition(conn, "document", document_id, to="PENDING_SIGNATURE", expected_from="APPROVED", set_values={"signer_employee_id": signer})
        step_id = uuid.uuid4()
        conn.execute("INSERT INTO approval_step (id, document_id, step_kind, level, revision_round, assignee_employee_id, status) VALUES (%s, %s, 'SIGNATURE', 1, %s, %s, 'OPEN')",
                     (step_id, document_id, round_, signer))
        audit.record(conn, ctx, action="document.signing_route", entity_type="document", entity_id=document_id, document_id=document_id, request_id=request_id,
                     payload={"status_from": "APPROVED", "status_to": "PENDING_SIGNATURE", "signer_employee_id": signer, "approval_step_id": step_id, "candidates": len(holders)})
    return SigningRouted(document_id, signer, step_id, already=False)
