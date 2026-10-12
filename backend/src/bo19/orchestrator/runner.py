"""Lối vào công khai của orchestrator: `IntakeRunner.run_turn` và `write_error_reply` (mục Cây backend và Triển khai ở B6b của 06-structure.md; ADR-016).

`api` chỉ gọi `orchestrator` qua file này (contract `api-surface`). `document_graph` (`run_render`, `resume_document`, `run_finalize_issue`, `purge_thread`) chưa có — lát sau.

**Chạy trong một thread, đồng bộ** (ADR-016, mục Triển khai ở B6b): bộ giám sát lượt gọi `run_turn` bằng `asyncio.to_thread`. Thread sync không huỷ được từ ngoài, nên `deadline` (mốc tuyệt đối theo
`time.monotonic()`) và `cancel` (cờ huỷ hợp tác) đi vào `TurnRuntime`: node kiểm cả hai trước mỗi lần gọi tool hay gateway; mỗi lời gọi gateway nhận min(WV-04/WV-06, thời gian còn lại của lượt).

**Mọi lượt đã nhận kết thúc bằng đúng một tin nhắn của agent.** Thành công: `render_reply` ghi. Lỗi — exception mang mã rời node, hết hạn chót, cờ huỷ, lỗi ngoài graph — `run_turn` ghi khuôn lỗi bằng cùng hàm
và cùng `id` xác định (`reply.agent_message_id`); bộ giám sát có thể ghi `ERROR_BUSY` **cùng lúc** ở hạn chót, và DB bảo đảm đúng một tin (migration `0012`). `run_turn` không ném: lỗi trả về trong `TurnOutcome`.
"""
from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bo19.ai_gateway.gateway import Gateway
from bo19.observability.log import get_logger
from bo19.observability.trace import trace_scope
from bo19.orchestrator.intake_graph import reply_templates as rt
from bo19.orchestrator.intake_graph.graph import build_intake_graph
from bo19.orchestrator.intake_graph.reply import agent_message_id, append_reply
from bo19.orchestrator.intake_graph.turn import IntakeDeps, TurnRuntime
from bo19.orchestrator.runtime.builder import Graph
from bo19.orchestrator.runtime.checkpointer import Checkpointing, open_checkpointer
from bo19.orchestrator.runtime.node_boundary import NodeError, code_of
from bo19.orchestrator.runtime.threads import touch_intake_thread
from bo19.orchestrator.state import SCHEMA_VERSION, initial_state
from bo19.persistence.pool import Pool
from bo19.tool_layer.kernel.permission import employee_context, system_context

log = get_logger("bo19.orchestrator.runner")

BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
RECURSION_LIMIT = 40


@dataclass(frozen=True)
class TurnOutcome:
    """Kết quả của một lượt — chỉ mã, id và tên slot; không văn bản."""

    reply_message_id: uuid.UUID | None  # None khi không ghi được tin nào (DB hỏng) — bộ giám sát phát `turn.error`
    reply_template_id: str | None
    error_code: str | None  # có mã nghĩa là lượt đi nhánh lỗi
    active_request_id: uuid.UUID | None = None
    intent_result: str | None = None
    pending_question: dict[str, Any] | None = None
    rejected_slots: tuple[str, ...] = ()
    rejection_codes: tuple[str, ...] = ()


def error_template(error_code: str) -> str:
    return rt.BUDGET_LIMIT if error_code == BUDGET_EXCEEDED else rt.ERROR_BUSY


class IntakeRunner:
    def __init__(self, deps: IntakeDeps, graph: Graph, checkpointing: Checkpointing | None = None) -> None:
        self._deps, self._graph, self._checkpointing = deps, graph, checkpointing

    @classmethod
    def open(cls, *, pool: Pool, gateway: Gateway, dsn: str, templates: rt.Templates | None = None) -> "IntakeRunner":
        """Composition root gọi một lần lúc khởi động: nạp khuôn (đã qua #23), mở checkpointer (không `setup()`), biên dịch graph."""
        checkpointing = open_checkpointer(dsn)
        deps = IntakeDeps(pool=pool, gateway=gateway, templates=templates or rt.load())
        return cls(deps, build_intake_graph(deps, checkpointing.saver), checkpointing)

    def close(self) -> None:
        if self._checkpointing is not None:
            self._checkpointing.close()

    # ------------------------------------------------------------------------------------------------------------------------

    def run_turn(self, *, chat_session_id: uuid.UUID, message_id: uuid.UUID, actor_employee_id: uuid.UUID, trace_id: str, deadline: float,
                 cancel: threading.Event | None = None, on_progress: Callable[[str], None] | None = None) -> TurnOutcome:
        with trace_scope(trace_id):
            failure: str | None = None
            final: dict[str, Any] | None = None
            try:
                with self._deps.pool.acquire() as conn:
                    ctx = employee_context(conn, actor_employee_id, trace_id)
                turn = TurnRuntime(ctx=ctx, sys=system_context(trace_id), deadline=deadline, cancel=cancel or threading.Event(), on_progress=on_progress)
                thread_id = touch_intake_thread(self._deps.pool, chat_session_id, schema_version=SCHEMA_VERSION)
                ids = {"trace_id": trace_id, "chat_session_id": str(chat_session_id), "actor_employee_id": str(actor_employee_id), "current_message_id": str(message_id)}
                state_input = ids if self._graph.values(thread_id) is not None else initial_state(**ids)  # thread đã có: chỉ bốn trường định danh, phần còn lại từ checkpoint
                final = self._graph.invoke(thread_id, state_input, configurable={"turn": turn, "trace_id": trace_id}, recursion_limit=RECURSION_LIMIT)
            except NodeError as e:
                failure = e.code
            except Exception as e:  # noqa: BLE001 — `run_turn` không ném: mọi lỗi thành khuôn lỗi
                failure = code_of(e)
                log.warning("TURN_FAILED", code=failure, exception_type=type(e).__name__)
            if failure is not None or final is None:
                failure = failure or "NODE_UNEXPECTED"
                log.info("TURN_ERROR_REPLY", code=failure)
                reply_id = self.write_error_reply(chat_session_id=chat_session_id, message_id=message_id, trace_id=trace_id, error_code=failure)
                return TurnOutcome(reply_id, error_template(failure), failure)
            return _outcome(final, agent_message_id(message_id))

    def write_error_reply(self, *, chat_session_id: uuid.UUID, message_id: uuid.UUID, trace_id: str, error_code: str) -> uuid.UUID | None:
        """Ghi khuôn lỗi trả lời tin nhân viên — idempotent theo `id` xác định, và DB giữ đúng một tin. Không ném; `None` nếu không ghi được."""
        try:
            appended = append_reply(self._deps.pool, self._deps.templates, system_context(trace_id), chat_session_id=chat_session_id, employee_message_id=message_id,
                                    template_id=error_template(error_code))
            return appended.message_id
        except Exception as e:  # noqa: BLE001
            log.error("ERROR_REPLY_NOT_WRITTEN", code=code_of(e), exception_type=type(e).__name__)
            return None


def _outcome(final: dict[str, Any], reply_id: uuid.UUID) -> TurnOutcome:
    pq = final.get("pending_question")
    rid = final.get("active_request_id")
    return TurnOutcome(
        reply_message_id=reply_id, reply_template_id=final.get("reply_template_id"), error_code=final.get("last_error_code") if final.get("reply_template_id") == rt.ERROR_BUSY else None,
        active_request_id=uuid.UUID(rid) if rid else None, intent_result=final.get("intent_result"),
        pending_question=None if not pq else {"kind": pq["kind"], "slot_names": list(pq["slot_names"]), "candidate_types": list(pq["candidate_types"])},
        rejected_slots=tuple(final.get("rejected_slots") or ()), rejection_codes=tuple(final.get("rejection_codes") or ()))
