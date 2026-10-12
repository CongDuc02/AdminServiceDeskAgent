"""Node và router của `intake_graph` (mục `intake_graph` của 03-agents.md; mục Triển khai ở B6b của 06-structure.md).

Node là hàm `(state, config) -> cập nhật state`. Mọi tác động ra ngoài đi qua `TurnRuntime.call_tool` hoặc `call_llm` — kiểm hạn chót và cờ huỷ trước — và mọi tool thuộc `tool_layer`: node không chạm DB.
Mọi node ra quyết định **đọc lại trạng thái từ DB**; state chỉ để định tuyến và không bao giờ mang giá trị slot, văn bản tin nhắn hay văn bản do LLM sinh (ADR-008). Văn bản tin nhắn (`RES`) nằm trong
`TurnRuntime.message_text` — bộ nhớ của lượt, không vào checkpoint.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from typing import Any

from bo19.ai_gateway.budget import BudgetOwner
from bo19.ai_gateway.gateway import ParseFailed
from bo19.ai_gateway.prompt_modules import CLASSIFY_INTENT, EXTRACT_SLOTS
from bo19.domain.eligibility import SLOT_MISSING, SLOT_UNCONFIRMED
from bo19.observability.log import get_logger
from bo19.orchestrator.intake_graph import reply_templates as rt
from bo19.orchestrator.intake_graph.reply import append_reply, build_params
from bo19.orchestrator.intake_graph.routing import EDITABLE_BY_CHAT, SUPPORTED, map_intent
from bo19.orchestrator.intake_graph.turn import IntakeDeps, TurnRuntime
from bo19.orchestrator.runtime.node_boundary import NodeError
from bo19.orchestrator.state import PER_TURN_FIELDS
from bo19.tool_layer.checks import config as cfg
from bo19.tool_layer.tools.chat_turn_context_read import chat_turn_context_read
from bo19.tool_layer.tools.prior_attempt_lookup import BeneficiaryNotSelf
from bo19.tool_layer.tools.request_open import request_open
from bo19.tool_layer.tools.request_slots_propose import request_slots_propose
from bo19.tool_layer.tools.request_slots_write import SlotWrite, request_slots_write
from bo19.tool_layer.tools.request_transition import request_transition

log = get_logger("bo19.orchestrator.intake")

NodeFn = Callable[[Mapping[str, Any], Any], dict[str, Any]]
COLLECTING = frozenset({"DRAFT", "NEEDS_INFO"})
AFTER_COLLECTING = frozenset({"SUBMITTED", "IN_REVIEW", "CHANGES_REQUESTED", "APPROVED", "FULFILLED", "REJECTED"})
CLARIFICATION_MAX = 2  # WV-11 — số lần hỏi làm rõ trước khi chuyển sang khuôn liên hệ phòng hành chính (chưa hiệu chỉnh)
PURPOSE_SLOT = "purpose"  # slot mà khuôn `ASK_PURPOSE_RETRY` (có ví dụ cụ thể) áp dụng — PO duyệt V2, 2026-10-09
UNKNOWN_SLOT = "UNKNOWN_SLOT"  # tên slot do LLM bịa ra không bao giờ vào state — chỉ giữ chỗ cho khớp thứ tự với `rejection_codes`


def turn_of(config: Any) -> TurnRuntime:
    return config["configurable"]["turn"]


def _ids(state: Mapping[str, Any]) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    return uuid.UUID(state["chat_session_id"]), uuid.UUID(state["current_message_id"]), uuid.UUID(state["actor_employee_id"])


def _pending_view(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """`pending_question` cho P1/P2: mã khuôn và ứng viên — INT, không văn bản."""
    pq = state.get("pending_question")
    return None if not pq else {"template_id": pq["template_id"], "candidate_types": list(pq["candidate_types"])}


def make_nodes(deps: IntakeDeps) -> dict[str, NodeFn]:  # noqa: C901 — một chỗ khai mọi node để đọc một lượt từ trên xuống
    pool = deps.pool

    def load_turn(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        t = turn_of(config)
        sid, mid, _ = _ids(state)
        context = t.call_tool(chat_turn_context_read, pool, t.ctx, chat_session_id=sid, message_id=mid)
        if context.body is None or not context.body.strip():
            raise NodeError("MESSAGE_UNAVAILABLE")  # văn bản đã bị xoá hay rỗng: không có gì để phân loại
        t.message_text = context.body
        active = context.active_request
        status = active.status if active else None
        last = state.get("last_seen_request_status")
        count = state.get("clarification_count", 0)
        if last in COLLECTING and status in AFTER_COLLECTING:
            count = 0  # đặt lại đúng một lần cho mỗi request; CANCELLED và EXPIRED không bao giờ đặt lại (A-068)
        t.resume = status is not None and status != last and status not in COLLECTING  # chạy đúng một lần cho mỗi lần đổi
        t.scratch["open_type"] = active.request_type_code if active and status in EDITABLE_BY_CHAT else None
        return {**PER_TURN_FIELDS, "active_request_id": str(active.request_id) if active else None, "active_request_type": active.request_type_code if active else None,
                "last_seen_request_status": status, "clarification_count": count}

    def route_load(state: Mapping[str, Any], config: Any) -> str:
        return "resume" if turn_of(config).resume else "classify"

    def classify_intent(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        t = turn_of(config)
        t.progress("UNDERSTANDING")
        sid, _, _ = _ids(state)
        catalog = t.call_tool(cfg.load_catalog, pool)
        t.scratch["catalog"] = catalog
        inputs = {"current_turn_text": t.message_text, "pending_question": _pending_view(state), "active_request_type": t.scratch["open_type"], "request_type_catalog": catalog}
        owner = BudgetOwner(chat_session_id=sid, request_id=uuid.UUID(state["active_request_id"]) if state.get("active_request_id") else None)
        try:
            t.scratch["p1"] = t.call_llm(deps, CLASSIFY_INTENT, inputs, owner).output
        except ParseFailed:
            t.scratch["p1"] = None  # JSON hỏng sau lần sửa duy nhất → `UNPARSEABLE` → hỏi lại bằng khuôn (mục P1 của 07-prompts.md)
            return {"last_error_code": "PARSE_FAILED"}
        return {}

    def route_intent(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        t = turn_of(config)
        mapped = map_intent(t.scratch.get("p1"), t.scratch["catalog"], t.scratch["open_type"])
        t.scratch["mapped"] = mapped
        update: dict[str, Any] = {"intent_result": mapped.intent_result, "unsupported_type": mapped.unsupported_type}
        if mapped.intent_result == "OUT_OF_SCOPE":
            # Sprint 1: chưa có kho quy trình để hỏi — `procedure_store` là hằng NOT_READY, không gọi tool (PO Q4, B6b); đi thẳng khuôn "chưa hỗ trợ"
            update.update(procedure_store="NOT_READY", reply_template_id=rt.OUT_OF_SCOPE_KNOWN if mapped.unsupported_type else rt.OUT_OF_SCOPE_GENERIC, pending_question=None)
        return update

    def route_after_intent(state: Mapping[str, Any], config: Any) -> str:
        result = state["intent_result"]
        if result in ("AMBIGUOUS", "UNPARSEABLE", "MULTIPLE", "TYPE_CHANGED"):  # MULTIPLE, TYPE_CHANGED: Sprint 2 (AC-2.8) — Sprint 1 hỏi lại, không đoán
            return "clarify"
        if result == "OUT_OF_SCOPE":
            return "reply"
        return "open" if turn_of(config).scratch["open_type"] is None else "extract"  # SUPPORTED: chưa có request đang mở thì mở

    def ask_clarification(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        t = turn_of(config)
        count = state.get("clarification_count", 0)
        if count >= CLARIFICATION_MAX:
            return {"reply_template_id": rt.CLARIFY_LIMIT_REACHED, "pending_question": None}
        mapped = t.scratch["mapped"]
        supported = {e["code"] for e in t.scratch["catalog"] if e["support_status"] == SUPPORTED}
        raw = [t.scratch["open_type"], mapped.primary_type] if mapped.intent_result == "TYPE_CHANGED" else list(mapped.candidate_types)
        candidates = [c for i, c in enumerate(raw) if c in supported and c not in raw[:i]]
        template = rt.CLARIFY_TYPE if candidates else rt.CLARIFY_TYPE_NO_CANDIDATE
        return {"clarification_count": count + 1, "reply_template_id": template,
                "pending_question": {"kind": "CLARIFY_TYPE", "template_id": template, "slot_names": [], "candidate_types": candidates}}

    def open_request(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        t = turn_of(config)
        sid, mid, actor = _ids(state)
        primary = t.scratch["mapped"].primary_type
        opened = t.call_tool(request_open, pool, t.ctx, chat_session_id=sid, request_type=primary, beneficiary_employee_id=actor, opened_by_message_id=mid)
        return {"active_request_id": str(opened.request_id), "active_request_type": primary, "last_seen_request_status": "DRAFT"}

    def extract_slots(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        t = turn_of(config)
        sid, mid, _ = _ids(state)
        rid, request_type = uuid.UUID(state["active_request_id"]), state["active_request_type"]
        specs = t.call_tool(cfg.slot_specs, pool, request_type)
        update: dict[str, Any] = {}
        if not specs:
            return update
        known = {s["slot_name"] for s in specs}
        inputs = {"current_turn_text": t.message_text, "pending_question": _pending_view(state), "slot_specs": specs}
        try:
            output = t.call_llm(deps, EXTRACT_SLOTS, inputs, BudgetOwner(chat_session_id=sid, request_id=rid)).output
        except ParseFailed:
            return {"last_error_code": "PARSE_FAILED"}  # coi như không hiểu — hỏi lại (mục P2 của 07-prompts.md)
        items = [SlotWrite(s["slot_name"], s["value"], mid, s["evidence_quote"], _span(s["evidence_span"])) for s in output["slots"]]
        if not items:
            return update
        written = t.call_tool(request_slots_write, pool, t.ctx, request_id=rid, items=items)
        names, codes = [], []
        for r in written.rejected:
            names.append(r.slot_name if r.slot_name in known else UNKNOWN_SLOT)
            codes.append(":".join([r.code, *( ["+".join(r.rule_codes)] if r.rule_codes else []), *([r.reason] if r.reason else [])]))
        update.update(rejected_slots=names, rejection_codes=codes)
        if written.written and state.get("last_seen_request_status") == "NEEDS_INFO":
            t.call_tool(request_transition, pool, t.sys, request_id=rid, to="DRAFT")  # lượt sau nhân viên bổ sung thì về DRAFT, qua cùng tool
            update["last_seen_request_status"] = "DRAFT"
        return update

    def propose_values(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        t = turn_of(config)
        rid = uuid.UUID(state["active_request_id"])
        for origin in ("HR_PROFILE", "PRIOR_ATTEMPT"):
            try:
                t.call_tool(request_slots_propose, pool, t.ctx, request_id=rid, origin=origin)
            except BeneficiaryNotSelf:
                break  # request lập hộ người khác: không đề xuất từ hồ sơ của người lập (EC-IL-01)
        return {}

    def check_completeness(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        t = turn_of(config)
        rid, request_type = uuid.UUID(state["active_request_id"]), state["active_request_type"]
        checked = t.call_tool(cfg.check_completeness, pool, rid)  # đúng hàm F1 mà request_submit dùng lại — không tin kết quả của lượt trước
        user_slots = {s["slot_name"] for s in t.call_tool(cfg.slot_specs, pool, request_type)}
        t.scratch["eligible"] = checked.eligible
        return {"missing_slots": [r.slot_name for r in checked.reasons if r.code == SLOT_MISSING and r.slot_name in user_slots],
                "proposed_slots": [r.slot_name for r in checked.reasons if r.code == SLOT_UNCONFIRMED and r.slot_name]}

    def route_after_check(state: Mapping[str, Any], config: Any) -> str:
        return "offer" if turn_of(config).scratch["eligible"] else "ask"

    def ask_missing(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        t = turn_of(config)
        rid, request_type = uuid.UUID(state["active_request_id"]), state["active_request_type"]
        user_slots = {s["slot_name"] for s in t.call_tool(cfg.slot_specs, pool, request_type)}
        rejected = [s for s in state.get("rejected_slots", []) if s in user_slots]
        missing, proposed = list(state.get("missing_slots", [])), list(state.get("proposed_slots", []))
        if rejected:
            template, slots = (rt.ASK_PURPOSE_RETRY, rejected) if rejected == [PURPOSE_SLOT] else (rt.ASK_SLOT_RETRY, rejected)
            update: dict[str, Any] = {"rejected_slots": rejected}
        elif missing:
            template, slots, update = rt.ASK_SLOT, missing, {}
        elif proposed:
            template, slots, update = rt.CONFIRM_PROPOSALS, proposed, {}
        else:
            log.error("F1_UNEXPLAINED")  # không eligible mà không có slot nào để nêu — hỏng cấu hình hay lỗi mã: khuôn lỗi, không đoán
            return {"reply_template_id": rt.ERROR_BUSY, "last_error_code": "F1_UNEXPLAINED", "pending_question": None}
        kind = "CONFIRM_PROPOSALS" if template == rt.CONFIRM_PROPOSALS else "ASK_SLOT"
        update.update(reply_template_id=template, pending_question={"kind": kind, "template_id": template, "slot_names": list(slots), "candidate_types": []})
        if state.get("last_seen_request_status") == "DRAFT":
            t.call_tool(request_transition, pool, t.sys, request_id=rid, to="NEEDS_INFO")
            update["last_seen_request_status"] = "NEEDS_INFO"
        return update

    def offer_submit(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        return {"reply_template_id": rt.OFFER_SUBMIT, "pending_question": {"kind": "OFFER_SUBMIT", "template_id": rt.OFFER_SUBMIT, "slot_names": [], "candidate_types": []}}

    def resume_context(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        return {"reply_template_id": rt.RESUME_STATUS, "pending_question": None}  # Sprint 2: EXPIRED, EXPLAIN_TERMINAL, hỏi nhu cầu kế tiếp (EC-CV-01)

    def render_reply(state: Mapping[str, Any], config: Any) -> dict[str, Any]:
        t = turn_of(config)
        t.progress("PREPARING_REPLY")
        template = state.get("reply_template_id")
        if not template:
            raise NodeError("NO_REPLY_TEMPLATE")
        sid, mid, _ = _ids(state)
        params = t.call_tool(build_params, pool, template, state=state)
        t.call_tool(append_reply, pool, deps.templates, t.sys, chat_session_id=sid, employee_message_id=mid, template_id=template, params=params)
        return {}

    return {"load_turn": load_turn, "route_load": route_load, "classify_intent": classify_intent, "route_intent": route_intent, "route_after_intent": route_after_intent,
            "ask_clarification": ask_clarification, "open_request": open_request, "extract_slots": extract_slots, "propose_values": propose_values,
            "check_completeness": check_completeness, "route_after_check": route_after_check, "ask_missing": ask_missing, "offer_submit": offer_submit,
            "resume_context": resume_context, "render_reply": render_reply}


def _span(raw: Any) -> tuple[int, int] | None:
    return (raw[0], raw[1]) if isinstance(raw, list) and len(raw) == 2 and all(isinstance(i, int) and not isinstance(i, bool) for i in raw) else None
