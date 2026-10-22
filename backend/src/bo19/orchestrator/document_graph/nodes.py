"""Node và router của `document_graph` — lát Sprint 1 (mục 6.4.1 của 03-agents.md; ADR-039).

**B9b1 (ADR-040):** thêm `route_signing`, `await_signature`, `route_after_signature`, `await_seal`, `await_issue` — ba điểm `interrupt` mới, mỗi điểm chỉ gọi `wait_for_human`. `route_review` đã có nhánh `APPROVED`;
loại quyết định khác (`REJECTED`, `CHANGES_REQUESTED`) là Sprint 2 nên là `UNSUPPORTED_DECISION`.

Node là hàm `(state, config) -> cập nhật state`. Mọi tác động ra ngoài đi qua `RenderRuntime.call_tool` hoặc `call_llm` (kiểm cờ huỷ trước), mọi tool thuộc `tool_layer`: node không chạm DB. Mọi node ra quyết định
**đọc lại trạng thái từ DB**; state chỉ để định tuyến và không bao giờ mang giá trị slot hay văn bản do LLM sinh (ADR-008). Văn bản do LLM sinh nằm ở `RenderRuntime.scratch["drafts"]` — bộ nhớ của lần chạy.

**B9b2 (ADR-041):** `await_issue` đọc id lệnh phát hành như ba điểm chờ kia; thêm `finalize_issue` (kiểm `approved_content_hash` → cấp số → render `FINAL` → kiểm byte → `ISSUED`) rồi `END`.

**Lỗi ở Sprint 1:** node ném `NodeError(mã)` (mã của tool hay của chính node; `failure.classify` đổi sang `reason_code` của bảng mã `document_halt`); Sprint 2 đổi thành `halt_for_human`.

**`await_content_review` chỉ gọi `wait_for_human` và không có tác động nào trước đó** — resume chạy lại node từ đầu. `route_review` là bản tối thiểu của B9a: đọc `decision_record` từ DB rồi kết thúc; bốn nhánh thật là B9b.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from typing import Any

from bo19.ai_gateway.budget import BudgetOwner
from bo19.ai_gateway.gateway import ParseFailed
from bo19.ai_gateway.prompt_modules import DRAFT_FREE_CONTENT, VariableSpec
from bo19.domain import final_values, free_content
from bo19.observability.log import get_logger
from bo19.orchestrator.document_graph.runtime import DocumentDeps, RenderRuntime
from bo19.orchestrator.runtime.builder import wait_for_human
from bo19.orchestrator.runtime.node_boundary import NodeError
from bo19.tool_layer import storage as store
from bo19.tool_layer.tools import document_reads as reads
from bo19.tool_layer.tools.docx_render import docx_render
from bo19.tool_layer.numbering import document_number_assign
from bo19.tool_layer.tools.document_draft_save import document_draft_save
from bo19.tool_layer.tools.document_transition import document_mark_issued, document_submit_for_review
from bo19.tool_layer.tools.issue_prepare import issue_prepare
from bo19.tool_layer.tools.pdf_export import pdf_export
from bo19.tool_layer.tools.render_integrity_check import render_integrity_check
from bo19.tool_layer.tools.render_values import render_values_build
from bo19.tool_layer.tools.request_slots_read import request_slots_read
from bo19.tool_layer.tools.review_readiness_check import review_readiness_check
from bo19.tool_layer.tools.signing_route import signing_route
from bo19.tool_layer.tools.template_fetch import TemplateInfo, template_version_read

log = get_logger("bo19.orchestrator.document")

NodeFn = Callable[[Mapping[str, Any], Any], dict[str, Any]]
MAX_ATTEMPTS = 2  # lần sinh chính và lần sinh lại duy nhất (ADR-009; `attempt_no` ∈ {1, 2})


def run_of(config: Any) -> RenderRuntime:
    return config["configurable"]["run"]


def _ids(state: Mapping[str, Any]) -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(state["document_id"]), uuid.UUID(state["request_id"])


def make_nodes(deps: DocumentDeps) -> dict[str, NodeFn]:  # noqa: C901 — một chỗ khai mọi node để đọc từ trên xuống
    pool = deps.pool

    def template_of(run: RenderRuntime, document_id: uuid.UUID) -> tuple[reads.DocumentHeader, TemplateInfo]:
        header = run.call_tool(reads.document_header_read, pool, run.sys, document_id=document_id)
        cached = run.scratch.get("template")
        if cached is None or cached.template_version_id != header.template_version_id:
            cached = run.call_tool(template_version_read, pool, run.sys, template_version_id=header.template_version_id)
            run.scratch["template"] = cached
        return header, cached

    def prepare_draft(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        run = run_of(config)
        document_id, _ = _ids(state)
        header, template = template_of(run, document_id)
        if header.status != "DRAFT":
            raise NodeError("NOT_DRAFT")  # graph chỉ chạy từ DRAFT; thử lại sau khi đã vào cổng là việc của `run_render` (đọc snapshot), không của node
        return {"template_id": str(template.template_id), "template_version": template.version_no, "free_content_variables": list(template.free_content_variables),
                "pending_targets": list(template.free_content_variables), "regenerated_variables": [], "revision_round": header.revision_round, "readiness_failures": [], "last_signal": None}

    def draft_free_content(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        run = run_of(config)
        document_id, request_id = _ids(state)
        header, template = template_of(run, document_id)
        attempts = run.call_tool(reads.free_content_attempts_read, pool, run.sys, document_id=document_id, revision_round=header.revision_round)
        drafts = run.scratch.setdefault("drafts", {})
        for name in state["pending_targets"]:
            done = attempts.get(name, ())
            if any(outcome == "PASSED" for _, outcome in done):
                continue  # lần chạy trước đã sinh xong và lưu — không gọi LLM lại
            attempt_no = (max(a for a, _ in done) if done else 0) + 1
            if attempt_no > MAX_ATTEMPTS:
                raise NodeError("FREE_CONTENT_INVALID")
            spec = template.variable(name)
            slots = run.call_tool(request_slots_read, pool, run.sys, request_id=request_id, slot_names=list(spec.slot_inputs), declared_slots=frozenset(spec.slot_inputs))
            if set(slots) != set(spec.slot_inputs):
                raise NodeError("REVIEW_NOT_READY")  # slot input của biến vắng: hồ sơ chưa đủ
            inputs = {**slots, "variable_guidance": spec.variable_guidance, "request_type": state["request_type"]}
            variable = VariableSpec(name, spec.max_length, tuple(spec.slot_inputs))
            try:
                result = run.call_llm(deps, DRAFT_FREE_CONTENT, inputs, BudgetOwner(request_id=request_id, document_id=document_id), variable)
            except ParseFailed:
                raise NodeError("PARSE_FAILED") from None
            except Exception as e:  # noqa: BLE001 — chỉ lấy `retry-after` (số) của lỗi provider nếu có, rồi để biên node đổi thành mã; `orchestrator` không import `ai_gateway.providers` (contract `allowlist-gate`)
                run.note_retry_after(getattr(e, "retry_after_seconds", None))
                raise
            drafts[name] = {"body": result.output["body"], "attempt_no": attempt_no, "module_version": result.prompt_module_version,
                            "fingerprint": deps.fingerprinter.digest(name, {**slots, "variable_guidance": spec.variable_guidance, "request_type": state["request_type"]})}
        return {}

    def validate_free_content(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        run = run_of(config)
        document_id, request_id = _ids(state)
        header, template = template_of(run, document_id)
        drafts: dict[str, Any] = run.scratch.setdefault("drafts", {})
        res_values: dict[str, str] | None = None
        regenerated = list(state["regenerated_variables"])
        again: list[str] = []
        for name in state["pending_targets"]:
            draft = drafts.pop(name, None)
            if draft is None:
                # Không có gì để kiểm: hoặc biến đã `PASSED` ở lần chạy trước, hoặc `scratch` mất (tiến trình chết giữa hai node). Chỉ cái sau cần sinh lại — và không tính vào `regenerated_variables`.
                attempts = run.call_tool(reads.free_content_attempts_read, pool, run.sys, document_id=document_id, revision_round=header.revision_round)
                if not any(o == "PASSED" for _, o in attempts.get(name, ())):
                    again.append(name)
                continue
            spec = template.variable(name)
            if res_values is None:
                res_values = run.call_tool(reads.request_res_slots_read, pool, run.sys, request_id=request_id)
            forbidden = [v for slot, v in res_values.items() if slot not in spec.slot_inputs]
            codes = free_content.validate_body(draft["body"], max_length=spec.max_length, forbidden_res_values=forbidden)
            outcome = "FAILED" if codes else "PASSED"
            run.call_tool(document_draft_save, pool, run.sys, document_id=document_id, variable_name=name, revision_round=header.revision_round, attempt_no=draft["attempt_no"],
                          body=draft["body"], validation_outcome=outcome, prompt_module_version=draft["module_version"], input_fingerprint=draft["fingerprint"],
                          fingerprint_key_id=deps.fingerprinter.key_id)
            log.info("FREE_CONTENT_VALIDATED", variable=name, outcome=outcome, attempt_no=draft["attempt_no"], codes=",".join(codes) or None)
            if codes:
                if name in regenerated:
                    raise NodeError("FREE_CONTENT_INVALID")  # lần sinh lại duy nhất của biến trong vòng này đã dùng (ADR-009)
                regenerated.append(name)
                again.append(name)
        return {"pending_targets": again, "regenerated_variables": regenerated}

    def route_after_validate(state: Mapping[str, Any], config: Any) -> str:
        return "redraft" if state["pending_targets"] else "render"

    def render_draft(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        run = run_of(config)
        document_id, _ = _ids(state)
        built = run.call_tool(render_values_build, pool, run.sys, document_id=document_id)
        try:
            docx = run.call_tool(docx_render, pool, deps.storage, run.sys, document_id=document_id, render_kind="DRAFT", values=built.values)
            pdf = run.call_tool(pdf_export, pool, deps.storage, run.sys, docx)
        except store.FileUnavailable as e:
            raise NodeError("RENDER_CHECKSUM_MISMATCH" if e.reason == "CHECKSUM_MISMATCH" else "RENDER_OBJECT_MISSING") from None
        return {"draft_render_key": pdf.pdf_key}

    def check_review_readiness(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        run = run_of(config)
        document_id, _ = _ids(state)
        result = run.call_tool(review_readiness_check, pool, run.sys, document_id=document_id)
        if not result.ok:
            log.warning("REVIEW_NOT_READY", codes=",".join(result.codes), variables=",".join(sorted({i.variable for i in result.issues if i.variable})) or None)
            raise NodeError("REVIEW_NOT_READY")
        return {"readiness_failures": []}

    def submit_for_review(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        run = run_of(config)
        document_id, _ = _ids(state)
        key = state["draft_render_key"]
        if not key:
            raise NodeError("DRAFT_RENDER_NOT_FOUND")
        run.call_tool(document_submit_for_review, pool, run.sys, document_id=document_id, draft_pdf_key=key)
        return {}

    def _await_decision(state: Mapping[str, Any]) -> dict[str, Any]:
        """Dùng chung cho ba điểm chờ có quyết định đi kèm. **Chỉ gọi `wait_for_human` và không có tác động nào trước đó** — resume chạy lại node từ đầu."""
        signal = wait_for_human({"document_id": state["document_id"], "revision_round": state["revision_round"]})
        decision_id = signal.get("decision_record_id") if isinstance(signal, dict) else None
        try:
            uuid.UUID(str(decision_id))
        except ValueError:
            raise NodeError("SYSTEM_DEFECT") from None
        return {"last_signal": {"decision_record_id": str(decision_id), "kind": None, "change_scope": None, "change_targets": []}}

    def await_content_review(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        return _await_decision(state)

    def _read_decision(state: Mapping[str, Any], config: Any, expected_kind: str) -> dict[str, Any]:
        """Đọc quyết định từ DB (không từ payload resume), kiểm nó thuộc đúng `document` và đúng loại; trả `last_signal` đã điền."""
        run = run_of(config)
        document_id, _ = _ids(state)
        signal = state["last_signal"]
        decision = run.call_tool(reads.decision_record_read, pool, run.sys, decision_record_id=uuid.UUID(signal["decision_record_id"]), document_id=document_id)
        if decision.kind != expected_kind:
            raise NodeError("UNSUPPORTED_DECISION")  # `REJECTED`, `CHANGES_REQUESTED`: Sprint 2 — chưa có thao tác nào ghi chúng
        return {**signal, "kind": decision.kind, "change_scope": decision.change_scope, "change_targets": list(decision.change_targets)}

    def route_review(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        """Sau cổng 1: đọc quyết định từ DB; `APPROVED` đi tiếp sang `route_signing`. Ba nhánh còn lại (`REJECTED`, `FREE_CONTENT`, `SLOT_DATA`) là Sprint 2."""
        return {"last_signal": _read_decision(state, config, "APPROVED")}

    def route_signing(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        """`render_integrity_check` trên bản đã duyệt **trước**, rồi `signing_route` — người ký là người đầu tiên dựa vào byte (mục Tool Registry của 03-agents.md). Chạy lại sau lần chạy dở là idempotent."""
        run = run_of(config)
        document_id, _ = _ids(state)
        header = run.call_tool(reads.document_header_read, pool, run.sys, document_id=document_id)
        if header.approved_render_id is None:
            raise NodeError("STALE_STATUS")  # chưa duyệt nội dung mà vào định tuyến ký: graph sai trạng thái
        run.call_tool(render_integrity_check, pool, deps.storage, run.sys, render_id=header.approved_render_id)
        run.call_tool(signing_route, pool, run.sys, document_id=document_id)
        return {}

    def await_signature(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        return _await_decision(state)

    def route_after_signature(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        """Sau bước ký: đọc quyết định từ DB (`SIGNED`; người ký trả lại — `CHANGES_REQUESTED` — là Sprint 2) và `requires_seal`, để cạnh điều kiện rẽ `await_seal` / `await_issue`."""
        run = run_of(config)
        document_id, _ = _ids(state)
        signal = _read_decision(state, config, "SIGNED")
        header = run.call_tool(reads.document_header_read, pool, run.sys, document_id=document_id)
        if header.requires_seal is None:
            raise NodeError("SYSTEM_DEFECT")  # `ck_document_seal_determined`: từ `APPROVED` trở đi `requires_seal` đã xác định
        return {"last_signal": signal, "requires_seal": header.requires_seal}

    def after_signature_target(state: Mapping[str, Any], config: Any) -> str:
        return "seal" if state.get("requires_seal") else "issue"

    def await_seal(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        return _await_decision(state)

    def await_issue(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        """Chờ lệnh phát hành (`document_issue`, `ISSUE_ORDERED`); `finalize_issue` hoàn tất. Không có tác động nào trước `interrupt`."""
        return _await_decision(state)

    def finalize_issue(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        """Hoàn tất một lệnh phát hành (ADR-041 mục 2). Chạy lại sau khi chết giữa chừng hội tụ về cùng một số, cùng cặp object, cùng một `ISSUED` (bảng ở ADR-041 mục 5)."""
        run = run_of(config)
        document_id, _ = _ids(state)
        decision_id = uuid.UUID(state["last_signal"]["decision_record_id"])
        prep = run.call_tool(issue_prepare, pool, run.sys, document_id=document_id, issue_decision_id=decision_id)  # kiểm `approved_content_hash` TRƯỚC khi cấp số
        if prep.already:
            return {}
        assigned = run.call_tool(document_number_assign, pool, run.sys, document_id=document_id, issue_decision_id=decision_id)
        system = final_values.system_values(prep.fill_after_approval, formatted_number=assigned.formatted_number, issued_date=assigned.issued_date,
                                            signer=final_values.signer_line(prep.signer_full_name, prep.signer_job_title),
                                            signer_name=prep.signer_full_name, signer_title=prep.signer_job_title)
        if system.unresolved:
            log.warning("FINAL_VARIABLE_UNRESOLVED", variables=",".join(system.unresolved))
            raise NodeError("RENDER_INPUT_INVALID")
        metadata = {"bo19-pin-reason": "ISSUED", "bo19-document-number": assigned.formatted_number, "bo19-issued-date": assigned.issued_date.isoformat()}  # trong CÙNG lệnh PUT (mục 5.3 của 04-data.md)
        try:
            docx = run.call_tool(docx_render, pool, deps.storage, run.sys, document_id=document_id, render_kind="FINAL", values={**prep.values, **system.values}, object_metadata=metadata)
            pdf = run.call_tool(pdf_export, pool, deps.storage, run.sys, docx, object_metadata=metadata)
        except store.FileUnavailable as e:
            raise NodeError("RENDER_CHECKSUM_MISMATCH" if e.reason == "CHECKSUM_MISMATCH" else "RENDER_OBJECT_MISSING") from None
        run.call_tool(render_integrity_check, pool, deps.storage, run.sys, render_id=pdf.render_id)
        run.call_tool(document_mark_issued, pool, run.sys, document_id=document_id, issue_decision_id=decision_id, entry_id=assigned.entry_id, render_id=pdf.render_id, issued_date=assigned.issued_date)
        return {}

    return {"prepare_draft": prepare_draft, "draft_free_content": draft_free_content, "validate_free_content": validate_free_content, "route_after_validate": route_after_validate,
            "render_draft": render_draft, "check_review_readiness": check_review_readiness, "submit_for_review": submit_for_review, "await_content_review": await_content_review,
            "route_review": route_review, "route_signing": route_signing, "await_signature": await_signature, "route_after_signature": route_after_signature,
            "after_signature_target": after_signature_target, "await_seal": await_seal, "await_issue": await_issue, "finalize_issue": finalize_issue}
