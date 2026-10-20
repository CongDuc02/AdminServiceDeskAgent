"""Nền chung cho test thao tác cổng và `signing_route` (B9b1, ADR-040): PostgreSQL thật đã migrate (DB dùng chung của `pg_support.get_db()`), **không** object storage và không `soffice`.

Dựng một `document` ở `PENDING_APPROVAL` bằng chính các tool thật (`build_request`, `request_submit`, `document_create_draft`, `document_draft_save`, `document_submit_for_review`); chỉ **bản render nháp** là dòng
ghi thẳng bằng chủ bảng (tắt kiểm khoá ngoại tới `stored_object_commit`) — thao tác cổng không đọc `object_storage` (mục 5.4 của 04-data.md). Template của fixture là một phiên bản `ACTIVE` giả với danh mục biến của
`doc_support.VARIABLES` (loại `WORK_CONFIRMATION`): mỗi lớp test một phiên bản riêng, nên không đè lên nhau trên DB dùng chung (`template_fetch` không chạy ở đây). Mọi nhân viên, giá trị, mẫu là dữ liệu GIẢ của test.

Không có test nào ở đây.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from bo19.orchestrator.runner import document_id_for
from bo19.persistence.pool import Pool
from bo19.tool_layer.gate_ops.document_apply_seal import document_apply_seal
from bo19.tool_layer.gate_ops.document_approve_content import document_approve_content
from bo19.tool_layer.gate_ops.document_issue import document_issue
from bo19.tool_layer.gate_ops.document_sign import document_sign
from bo19.tool_layer.gate_ops.request_submit import request_submit
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import employee_context, system_context
from bo19.tool_layer.tools.document_draft_save import document_draft_save
from bo19.tool_layer.tools.document_transition import document_create_draft, document_submit_for_review
from bo19.tool_layer.tools.signing_route import signing_route
from tests.doc_support import BODY_OK, VARIABLES
from tests.request_support import build_request

OFFICER_ROLES = ("EMPLOYEE", "ADMIN_OFFICER")


@dataclass(frozen=True)
class Doc:
    """Một `document` đã dựng: id, request, người thụ hưởng và khoá bản nháp."""

    document_id: uuid.UUID
    request_id: uuid.UUID
    beneficiary_id: uuid.UUID
    version_id: uuid.UUID
    render_id: uuid.UUID
    pdf_key: str


def make_template_version(db, *, variables=VARIABLES, status: str = "ACTIVE") -> uuid.UUID:
    """Phiên bản template giả cho `WORK_CONFIRMATION` — chỉ dòng DB (không có object nguồn thật)."""
    tid, vid = uuid.uuid4(), uuid.uuid4()
    with db.connect(autocommit=True) as c:
        c.execute("set session_replication_role = replica")
        c.execute("insert into template (id, code, request_type_code, name) values (%s, %s, 'WORK_CONFIRMATION', 'MẪU GIẢ')", (tid, f"GIA_{uuid.uuid4().hex[:8]}"))
        c.execute("insert into template_version (id, template_id, version_no, status, source_object_key, uploaded_by_employee_id, required_fonts, activated_at, retired_at) "
                  "values (%s, %s, 1, %s, %s, %s, %s, now(), %s)",
                  (vid, tid, status, f"templates/{uuid.uuid4()}/source.docx", uuid.uuid4(), ["Times New Roman"], "2026-02-01T00:00:00+00" if status == "RETIRED" else None))
        for name, kind, source, after, guidance, max_len, inputs in variables:
            c.execute("insert into template_variable (template_version_id, variable_name, kind, source_slot_name, fill_after_approval, variable_guidance, max_length) values (%s, %s, %s, %s, %s, %s, %s)",
                      (vid, name, kind, source, after, guidance, max_len))
            for slot in inputs:
                c.execute("insert into template_variable_input (template_version_id, variable_name, slot_name) values (%s, %s, %s)", (vid, name, slot))
    return vid


def ctx_of(pool: Pool, employee_id: uuid.UUID) -> ToolContext:
    with pool.acquire() as conn:
        return employee_context(conn, employee_id)


def make_pending_approval(db, pool: Pool, version_id: uuid.UUID, *, requires_seal: bool = True, seal_type: str | None = "ORGANIZATION_ROUND",
                          beneficiary: tuple[uuid.UUID, ToolContext] | None = None) -> Doc:
    """Một `document` ở `PENDING_APPROVAL` với bước `CONTENT_REVIEW` mở. `beneficiary`: người thụ hưởng kiêm người tạo (mặc định một nhân viên mới); `requires_seal`/`seal_type` đặt lại sau khi tạo `DRAFT`."""
    sysctx = system_context()
    eid, ctx = beneficiary or _new_employee(db, pool)
    rid = build_request(pool, db, eid, ctx)
    with db.connect("bo19_migrator") as c:
        version = c.execute("select row_version from request where id = %s", (rid,)).fetchone()[0]
    request_submit(pool, ctx, request_id=rid, decision_id=uuid.uuid4(), expected_row_version=version)
    did = document_id_for(rid)
    document_create_draft(pool, sysctx, document_id=did, request_id=rid, template_version_id=version_id)
    with db.connect("bo19_migrator") as c:
        c.execute("update document set requires_seal = %s, seal_type = %s where id = %s", (requires_seal, seal_type if requires_seal else None, did))
    document_draft_save(pool, sysctx, document_id=did, variable_name="purpose_statement", revision_round=0, attempt_no=1, body=BODY_OK, validation_outcome="PASSED",
                        prompt_module_version="1.1", input_fingerprint=b"\x07" * 32)
    render_id, pdf_key = uuid.uuid4(), f"renders/{uuid.uuid4()}.pdf"
    with db.connect(autocommit=True) as c:
        c.execute("set session_replication_role = replica")
        c.execute("insert into document_render (id, document_id, operating_mode, render_kind, input_hash, template_version_id, revision_round, docx_object_key, pdf_object_key, watermark_text) "
                  "values (%s, %s, 'NON_PRODUCTION', 'DRAFT', %s, %s, 0, %s, %s, 'BẢN THỬ NGHIỆM')", (render_id, did, hashlib.sha256(render_id.bytes).digest(), version_id, f"renders/{uuid.uuid4()}.docx", pdf_key))
    document_submit_for_review(pool, sysctx, document_id=did, draft_pdf_key=pdf_key)
    return Doc(did, rid, eid, version_id, render_id, pdf_key)


def _new_employee(db, pool: Pool) -> tuple[uuid.UUID, ToolContext]:
    eid, _ = db.make_employee(roles=("EMPLOYEE",))
    return eid, ctx_of(pool, eid)


def make_officer(db, pool: Pool, *, signer: bool = False, **kw) -> tuple[uuid.UUID, ToolContext]:
    """Cán bộ hành chính (`ADMIN_OFFICER`); `signer=True` cấp lẻ `document.sign` (cấp lẻ, không thuộc gói vai trò)."""
    kw.setdefault("roles", OFFICER_ROLES)
    if signer:
        kw["grants"] = (*kw.get("grants", ()), "document.sign")
    eid, _ = db.make_employee(**kw)
    return eid, ctx_of(pool, eid)


def document_row(db, document_id: uuid.UUID) -> dict:
    with db.connect("bo19_migrator") as c:
        cur = c.execute("select * from document where id = %s", (document_id,))
        row = cur.fetchone()
        return dict(zip([d.name for d in cur.description], row)) if row else {}


def rows(db, sql: str, *args) -> list[tuple]:
    with db.connect("bo19_migrator") as c:
        return c.execute(sql, args).fetchall()


def scalar(db, sql: str, *args):
    r = rows(db, sql, *args)
    return r[0][0] if r else None


class FlowMixin:
    """Đưa một `document` qua các cổng bằng chính các thao tác cổng thật. Lớp dùng cần `self.db`, `self.pool`, `self.version_id` (từ `make_template_version`) và `self.sys` (ngữ cảnh hệ thống)."""

    def doc(self, **kw):
        return make_pending_approval(self.db, self.pool, self.version_id, **kw)

    def officer(self, **kw):
        return make_officer(self.db, self.pool, **kw)

    def version(self, doc) -> int:
        return document_row(self.db, doc.document_id)["row_version"]

    def status(self, doc) -> str:
        return document_row(self.db, doc.document_id)["status"]

    def approve(self, doc, ctx, key=None, version=None):
        return document_approve_content(self.pool, ctx, document_id=doc.document_id, decision_id=key or uuid.uuid4(), expected_row_version=version or self.version(doc))

    def route(self, doc):
        return signing_route(self.pool, self.sys, document_id=doc.document_id)

    def sign(self, doc, ctx, key=None, version=None):
        return document_sign(self.pool, ctx, document_id=doc.document_id, decision_id=key or uuid.uuid4(), expected_row_version=version or self.version(doc))

    def seal(self, doc, ctx, key=None, version=None, copies=1, pages=None):
        return document_apply_seal(self.pool, ctx, document_id=doc.document_id, decision_id=key or uuid.uuid4(), expected_row_version=version or self.version(doc), copies_count=copies, page_count=pages)

    def issue(self, doc, ctx, key=None, version=None):
        return document_issue(self.pool, ctx, document_id=doc.document_id, decision_id=key or uuid.uuid4(), expected_row_version=version or self.version(doc))

    def pending_signature(self, **kw):
        """Một `document` đã qua cổng 1 và `signing_route`. Trả (document, (id, ctx) của người ký **thực sự được giao** — `signing_route` chọn theo mã nhỏ nhất trong cả DB dùng chung —, (id, ctx) của người duyệt)."""
        self.officer(signer=True)  # bảo đảm có ít nhất một người mang document.sign
        officer = self.officer()
        doc = self.doc(**kw)
        self.approve(doc, officer[1])
        self.route(doc)
        signer_id = document_row(self.db, doc.document_id)["signer_employee_id"]
        return doc, (signer_id, ctx_of(self.pool, signer_id)), officer

    def pending_seal(self, **kw):
        doc, signer, officer = self.pending_signature(**kw)
        self.sign(doc, signer[1])
        return doc, signer, officer

    def sealed(self, **kw):
        doc, signer, officer = self.pending_seal(**kw)
        self.seal(doc, officer[1])
        return doc, signer, officer


def expected_hash(version_id: uuid.UUID, mode: str, values: dict[str, str]) -> bytes:
    """Hash tính độc lập với `domain.content_hash` — từ chuỗi JSON dựng tay — để một lỗi trong hàm đó không tự khớp với chính nó."""
    body = '{"operating_mode":' + json.dumps(mode) + ',"template_version_id":' + json.dumps(str(version_id)) + ',"v":1,"values":{' + ",".join(
        f"{json.dumps(k, ensure_ascii=False)}:{json.dumps(values[k], ensure_ascii=False)}" for k in sorted(values)) + "}}"
    return hashlib.sha256(body.encode("utf-8")).digest()


def audit_actions(db, document_id: uuid.UUID) -> list[str]:
    return [r[0] for r in rows(db, "select action from audit_event where document_id = %s order by occurred_at, id", document_id)]
