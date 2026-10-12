"""Lắp và ghi câu trả lời của agent — dùng chung cho `render_reply`, `runner` (lượt lỗi) và bộ giám sát lượt (mục Triển khai ở B6b của 06-structure.md; mục `intake_graph` của 03-agents.md).

Văn bản lắp từ khuôn (`reply_templates`) với tham số lấy từ **cấu hình DB** (tên loại, nhãn slot) và **mã** trong state — không bao giờ từ văn bản của nhân viên hay của LLM, và văn bản KHÔNG đi qua state (ADR-008).
Tin ghi qua `chat_message_append` với `id` **xác định** theo tin nhân viên (`uuid5`): mọi bên muốn ghi câu trả lời cho lượt đó dùng cùng một `id`, nên ghi hai lần là idempotent theo `id`; DB giữ thêm một lớp
bằng `in_reply_to_message_id` + `UNIQUE` (migration 0012) cho bên nào dùng `id` khác.
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from bo19.domain.status_labels import request_status_label
from bo19.orchestrator.intake_graph import reply_templates as rt
from bo19.orchestrator.intake_graph.reply_templates import Templates
from bo19.persistence.pool import Pool
from bo19.tool_layer.checks import config as cfg
from bo19.tool_layer.endpoint_ops.chat import Appended, chat_message_append
from bo19.tool_layer.kernel.context import ToolContext

AGENT_REPLY_NAMESPACE = uuid.UUID("6f0b5a52-3c1e-4d7a-9b44-2f7a1d9e8c10")


def agent_message_id(employee_message_id: uuid.UUID | str) -> uuid.UUID:
    return uuid.uuid5(AGENT_REPLY_NAMESPACE, f"agent-reply:{employee_message_id}")


def build_params(pool: Pool, template_id: str, *, state: Mapping[str, Any]) -> dict[str, Any]:
    """Tham số của khuôn, từ cấu hình DB và mã trong state. Khuôn không tham số trả `{}`."""
    request_type = state.get("active_request_type")

    def names(codes: list[str]) -> list[str]:
        mapping = cfg.type_names(pool)
        return [mapping[c] for c in codes if c in mapping]

    def labels(slots: list[str]) -> list[str]:
        mapping = cfg.slot_labels(pool, request_type) if request_type else {}
        return [mapping[s] for s in slots if s in mapping]

    supported = lambda: list(cfg.type_names(pool, supported_only=True).values())  # noqa: E731
    if template_id == rt.CLARIFY_TYPE:
        return {"type_names": names(list((state.get("pending_question") or {}).get("candidate_types") or []))}
    if template_id in (rt.CLARIFY_TYPE_NO_CANDIDATE, rt.OUT_OF_SCOPE_GENERIC):
        return {"type_names": supported()}
    if template_id == rt.ASK_SLOT:
        return {"type_name": names([request_type])[0], "slot_labels": labels(list(state.get("missing_slots") or []))}
    if template_id == rt.ASK_SLOT_RETRY:
        return {"slot_labels": labels(list(state.get("rejected_slots") or []))}
    if template_id == rt.CONFIRM_PROPOSALS:
        return {"slot_labels": labels(list(state.get("proposed_slots") or []))}
    if template_id == rt.OFFER_SUBMIT:
        return {"type_name": names([request_type])[0]}
    if template_id == rt.OUT_OF_SCOPE_KNOWN:
        return {"unsupported_type_name": names([state["unsupported_type"]])[0], "type_names": supported()}
    if template_id == rt.RESUME_STATUS:
        return {"type_name": names([request_type])[0], "status_label": request_status_label(state["last_seen_request_status"])}
    return {}  # CLARIFY_LIMIT_REACHED, ASK_PURPOSE_RETRY, ERROR_BUSY, BUDGET_LIMIT


def append_reply(pool: Pool, templates: Templates, sys_ctx: ToolContext, *, chat_session_id: uuid.UUID, employee_message_id: uuid.UUID, template_id: str,
                 params: Mapping[str, Any] | None = None) -> Appended:
    """Lắp khuôn rồi ghi tin của agent trả lời tin nhân viên. Thiếu/thừa tham số → `ReplyTemplateError` (mã), không bao giờ lộ cho nhân viên."""
    text = templates.render(template_id, params)
    return chat_message_append(pool, sys_ctx, chat_session_id=chat_session_id, message_id=agent_message_id(employee_message_id), author="AGENT", body=text,
                               reply_template_id=template_id, in_reply_to_message_id=employee_message_id)
