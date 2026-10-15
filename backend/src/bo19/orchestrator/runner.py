"""Lối vào công khai của orchestrator: `IntakeRunner.run_turn` và `write_error_reply` (mục Cây backend và Triển khai ở B6b của 06-structure.md; ADR-016).

`DocumentRunner.run_render` và `resume_document` (B9a, ADR-039) cho `document_graph`; `run_finalize_issue`, `purge_thread` — lát sau.

`api` chỉ gọi `orchestrator` qua file này (contract `api-surface`).

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
from bo19.observability.trace import new_trace_id, trace_scope
from bo19.orchestrator.document_graph.failure import classify
from bo19.orchestrator.document_graph.graph import RECURSION_LIMIT as DOCUMENT_RECURSION_LIMIT
from bo19.orchestrator.document_graph.graph import build_document_graph
from bo19.orchestrator.document_graph.runtime import DocumentDeps, RenderRuntime
from bo19.orchestrator.intake_graph import reply_templates as rt
from bo19.orchestrator.intake_graph.graph import build_intake_graph
from bo19.orchestrator.intake_graph.reply import agent_message_id, append_reply
from bo19.orchestrator.intake_graph.turn import IntakeDeps, TurnRuntime
from bo19.orchestrator.runtime.builder import INTERRUPTED, Graph, Snapshot
from bo19.orchestrator.runtime.checkpointer import Checkpointing, open_checkpointer
from bo19.orchestrator.runtime.node_boundary import NodeError, code_of
from bo19.orchestrator.runtime.threads import document_thread_id, mark_document_thread, touch_document_thread, touch_intake_thread
from bo19.orchestrator.state import DOCUMENT_SCHEMA_VERSION, SCHEMA_VERSION, initial_document_state, initial_state
from bo19.persistence.pool import Pool
from bo19.tool_layer.kernel.permission import employee_context, system_context
from bo19.tool_layer.storage import ObjectStorage
from bo19.tool_layer.tools.document_draft_save import InputFingerprinter
from bo19.tool_layer.tools.document_reads import request_header_read
from bo19.tool_layer.tools.document_transition import document_create_draft
from bo19.tool_layer.tools.template_fetch import template_fetch

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


# ---- document_graph (B9a, ADR-039) -------------------------------------------------------------------------------------------------------------------------------

DOCUMENT_NAMESPACE = uuid.UUID("b0190000-0000-4000-8000-000000d0c001")  # hằng cố định: `document_id` xác định theo `request_id` (ADR-039 mục 1)
THREAD_NOT_WAITING = "THREAD_NOT_WAITING"


def document_id_for(request_id: uuid.UUID) -> uuid.UUID:
    """`document` đầu tiên của một `request` có id xác định — thử lại job không tạo `document` thứ hai."""
    return uuid.uuid5(DOCUMENT_NAMESPACE, str(request_id))


@dataclass(frozen=True)
class RenderOutcome:
    document_id: uuid.UUID
    status: str  # WAITING (đang chờ ở một `interrupt`) | ENDED (graph tới `END`)
    waiting_at: str | None
    already: bool  # True: không chạy gì — thread đã ở trạng thái này từ lần trước (thử lại job là no-op)


class RenderFailed(Exception):
    """Một lần chạy graph hỏng. Chỉ mang mã: `reason_code` của bảng mã `document_halt`, `permanent` (thử lại không đổi kết quả), `retry_after_s` của provider (nếu có) và mã gốc rời node."""

    def __init__(self, reason_code: str, *, permanent: bool, retry_after_s: int | None, raw_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code, self.permanent, self.retry_after_s, self.raw_code = reason_code, permanent, retry_after_s, raw_code


class DocumentRunner:
    def __init__(self, deps: DocumentDeps, graph: Graph, checkpointing: Checkpointing | None = None) -> None:
        self._deps, self._graph, self._checkpointing = deps, graph, checkpointing

    @classmethod
    def open(cls, *, pool: Pool, gateway: Gateway, storage: ObjectStorage, dsn: str, fingerprint_key: str) -> "DocumentRunner":
        """Composition root gọi một lần lúc khởi động `worker`: mở checkpointer (không `setup()`), dựng khoá dấu vân tay (A-097), biên dịch graph."""
        checkpointing = open_checkpointer(dsn)
        deps = DocumentDeps(pool=pool, gateway=gateway, storage=storage, fingerprinter=InputFingerprinter(fingerprint_key))
        return cls(deps, build_document_graph(deps, checkpointing.saver), checkpointing)

    def close(self) -> None:
        if self._checkpointing is not None:
            self._checkpointing.close()

    def snapshot(self, document_id: uuid.UUID) -> Snapshot:
        return self._graph.snapshot(document_thread_id(document_id))

    # ------------------------------------------------------------------------------------------------------------------------

    def run_render(self, *, request_id: uuid.UUID, trace_id: str | None = None, cancel: threading.Event | None = None) -> RenderOutcome:
        """Job `render_document`: tạo `DRAFT`, mở thread, chạy graph tới điểm dừng `await_content_review`. **Thử lại tiếp tục từ checkpoint** (ADR-039 mục 3). Ném `RenderFailed` — không ném gì khác."""
        trace = trace_id or new_trace_id()
        with trace_scope(trace):
            run = RenderRuntime(sys=system_context(trace), cancel=cancel or threading.Event())
            try:
                return self._render(request_id, trace, run)
            except RenderFailed:
                raise
            except NodeError as e:
                raise self._failed(e.code, run) from None
            except Exception as e:  # noqa: BLE001 — chỉ mã; thông điệp có thể mang giá trị
                raise self._failed(code_of(e), run, exception_type=type(e).__name__) from None

    def resume_document(self, *, document_id: uuid.UUID, decision_record_id: uuid.UUID, trace_id: str | None = None, cancel: threading.Event | None = None) -> RenderOutcome:
        """Đánh thức thread đang chờ ở một `interrupt` bằng id của `decision_record` (payload resume chỉ mang id). Graph đã `END` thì no-op (thử lại job)."""
        trace = trace_id or new_trace_id()
        with trace_scope(trace):
            run = RenderRuntime(sys=system_context(trace), cancel=cancel or threading.Event())
            try:
                thread_id = document_thread_id(document_id)
                snap = self._graph.snapshot(thread_id)
                if snap.finished:
                    return RenderOutcome(document_id, "ENDED", None, True)
                if not snap.waiting_at:
                    raise NodeError(THREAD_NOT_WAITING)
                out = self._graph.resume(thread_id, {"decision_record_id": str(decision_record_id)}, configurable={"run": run, "trace_id": trace}, recursion_limit=DOCUMENT_RECURSION_LIMIT)
                return self._after(document_id, thread_id, out, already=False)
            except RenderFailed:
                raise
            except NodeError as e:
                raise self._failed(e.code, run) from None
            except Exception as e:  # noqa: BLE001
                raise self._failed(code_of(e), run, exception_type=type(e).__name__) from None

    # ------------------------------------------------------------------------------------------------------------------------

    def _render(self, request_id: uuid.UUID, trace: str, run: RenderRuntime) -> RenderOutcome:
        document_id = document_id_for(request_id)
        thread_id = document_thread_id(document_id)
        snap = self._graph.snapshot(thread_id)
        if snap.finished:
            return RenderOutcome(document_id, "ENDED", None, True)
        if snap.waiting_at:  # job chạy lại sau khi graph đã tới điểm dừng: không có gì để làm
            mark_document_thread(self._deps.pool, document_id, waiting_at=snap.waiting_at)
            return RenderOutcome(document_id, "WAITING", snap.waiting_at, True)
        pool, sys = self._deps.pool, run.sys
        if snap.exists:
            state_input = None  # lần chạy trước bị ngắt giữa chừng: tiếp từ checkpoint cuối
        else:
            header = run.call_tool(request_header_read, pool, sys, request_id=request_id)
            template = run.call_tool(template_fetch, pool, sys, request_type=header.request_type_code)
            run.call_tool(document_create_draft, pool, sys, document_id=document_id, request_id=request_id, template_version_id=template.template_version_id)
            state_input = initial_document_state(trace_id=trace, document_id=str(document_id), request_id=str(request_id), request_type=header.request_type_code)
        touch_document_thread(pool, document_id, schema_version=DOCUMENT_SCHEMA_VERSION)
        out = self._graph.invoke(thread_id, state_input, configurable={"run": run, "trace_id": trace}, recursion_limit=DOCUMENT_RECURSION_LIMIT)
        return self._after(document_id, thread_id, out, already=False)

    def _after(self, document_id: uuid.UUID, thread_id: str, out: dict[str, Any], *, already: bool) -> RenderOutcome:
        snap = self._graph.snapshot(thread_id)
        if INTERRUPTED in out or snap.waiting_at:
            mark_document_thread(self._deps.pool, document_id, waiting_at=snap.waiting_at)
            return RenderOutcome(document_id, "WAITING", snap.waiting_at, already)
        if snap.finished:
            mark_document_thread(self._deps.pool, document_id, ended=True)
            return RenderOutcome(document_id, "ENDED", None, already)
        raise NodeError("NODE_UNEXPECTED")  # graph không dừng ở interrupt cũng không tới END: không xảy ra nếu graph đúng

    @staticmethod
    def _failed(raw_code: str, run: RenderRuntime, *, exception_type: str | None = None) -> RenderFailed:
        failure = classify(raw_code)
        log.warning("RENDER_FAILED", code=raw_code, reason_code=failure.reason_code, permanent=failure.permanent, exception_type=exception_type)
        return RenderFailed(failure.reason_code, permanent=failure.permanent, retry_after_s=run.scratch.get("retry_after_s"), raw_code=raw_code)
