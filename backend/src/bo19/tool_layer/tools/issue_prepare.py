"""Tool `issue_prepare` — bước 0 của `finalize_issue` (B9b2, ADR-041 mục 2): chỉ đọc, **trước khi cấp số**.

Một giao dịch `READ ONLY`: (1) lệnh phát hành thuộc đúng `document` (`decision_record` `ISSUE_ORDERED`); (2) `document` ở `SIGNED` (không cần dấu) hoặc `SEALED` — hoặc đã `ISSUED` đúng với lệnh này (`already`: lần chạy
trước đã commit mà job chưa kịp `SUCCEEDED`; node kết thúc, không làm gì); (3) dựng bảng giá trị bằng `build_values` — cùng nguồn với bản nháp và với cổng 1; (4) **INV-01:** `approved_content_hash` tính lại bằng
`domain.content_hash.approved_content_hash` (cùng hàm với `document_approve_content`) từ các biến **không** điền-sau-duyệt, so với giá trị đã ghi ở cổng 1 — lệch là `CONTENT_HASH_MISMATCH` và **chưa có số nào bị tiêu**;
(5) người đã ký: `decision_record` `SIGNED` mới nhất — họ tên và chức danh in lên bản `FINAL` (PO, 2026-10-20).

Bảng giá trị trả về là bảng **sẽ được render**: node chỉ thêm ba biến `SYSTEM` điền-sau-duyệt (`domain.final_values`), không đọc lại giá trị nào, nên giữa kiểm hash và render không có khe hở. Giá trị không vào log, lỗi hay
`repr`. Chỉ tác nhân hệ thống.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from bo19.domain.content_hash import approved_content_hash
from bo19.persistence.pool import Pool
from bo19.persistence.read import read_only
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_system
from bo19.tool_layer.tools._common import ToolError
from bo19.tool_layer.tools.render_values import TEMPLATE_NOT_ACTIVE_AT_RENDER, build_values
from bo19.tool_layer.tools.template_fetch import read_version


class DocumentNotFound(ToolError):
    code = "DOCUMENT_NOT_FOUND"


class NoIssueOrder(ToolError):
    code = "NO_ISSUE_ORDER"


class StaleDocument(ToolError):
    code = "STALE_STATUS"  # `document` không ở trạng thái chờ phát hành, hoặc đã `ISSUED` bởi một lệnh khác


class ContentHashMismatch(ToolError):
    code = "CONTENT_HASH_MISMATCH"  # INV-01: nội dung hiện hành khác nội dung đã duyệt ở cổng 1


class RenderInputInvalid(ToolError):
    code = "RENDER_INPUT_INVALID"  # bảng giá trị còn lỗi, hoặc không có người ký — chỉ mã và tên biến


@dataclass(frozen=True)
class IssuePrepared:
    document_id: uuid.UUID
    already: bool  # `document` đã `ISSUED` đúng với lệnh này: không còn gì để làm
    values: dict[str, str] = field(default_factory=dict, repr=False)  # bảng giá trị sẽ render (biến điền-sau-duyệt còn dấu giữ chỗ — node thay)
    fill_after_approval: frozenset[str] = frozenset()
    signer_full_name: str = field(default="", repr=False)  # PER — công vụ của người phát hành (09-security.md mục 3.5)
    signer_job_title: str = field(default="", repr=False)

    def __repr__(self) -> str:
        return f"IssuePrepared(document_id={self.document_id}, already={self.already}, variables={sorted(self.values)})"


def issue_prepare(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID, issue_decision_id: uuid.UUID) -> IssuePrepared:
    require_system(ctx)
    with pool.acquire() as conn, read_only(conn):
        doc = conn.execute("SELECT status, requires_seal, operating_mode, template_version_id, approved_content_hash, issued_register_entry_id FROM document WHERE id = %s", (document_id,)).fetchone()
        if doc is None:
            raise DocumentNotFound
        status, requires_seal, mode, version_id, approved_hash, issued_entry = doc
        order = conn.execute("SELECT 1 FROM decision_record WHERE id = %s AND document_id = %s AND kind = 'ISSUE_ORDERED'", (issue_decision_id, document_id)).fetchone()
        if order is None:
            raise NoIssueOrder
        if status == "ISSUED":
            same = conn.execute("SELECT 1 FROM document_register_entry WHERE id = %s AND document_id = %s AND issue_decision_id = %s", (issued_entry, document_id, issue_decision_id)).fetchone()
            if same is None:
                raise StaleDocument
            return IssuePrepared(document_id, already=True)
        if status not in ("SIGNED", "SEALED") or (status == "SIGNED" and requires_seal is not False):
            raise StaleDocument
        built = build_values(conn, document_id)
        blocking = sorted({i.code for i in built.issues if i.code != TEMPLATE_NOT_ACTIVE_AT_RENDER})  # bản `FINAL` còn render được từ phiên bản `RETIRED` (ADR-015 chốt 3)
        if blocking:
            raise RenderInputInvalid(blocking[0])
        template = read_version(conn, version_id)
        after_approval = frozenset(v.name for v in template.variables if v.fill_after_approval)
        digest = approved_content_hash(template_version_id=version_id, operating_mode=mode, values={k: v for k, v in built.values.items() if k not in after_approval})
        if approved_hash is None or bytes(approved_hash) != digest:
            raise ContentHashMismatch
        signer = conn.execute("SELECT e.full_name, e.job_title FROM decision_record d JOIN employee e ON e.id = d.actor_employee_id WHERE d.document_id = %s AND d.kind = 'SIGNED' "
                              "ORDER BY d.created_at DESC, d.id DESC LIMIT 1", (document_id,)).fetchone()
        if signer is None:
            raise RenderInputInvalid("NO_SIGNER")
    return IssuePrepared(document_id, already=False, values=dict(built.values), fill_after_approval=after_approval, signer_full_name=signer[0], signer_job_title=signer[1])
