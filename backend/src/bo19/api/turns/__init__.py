"""Bộ giám sát lượt: task lượt tách khỏi vòng đời request (ADR-016; mục SSE của 05-api.md; mục Triển khai ở B6b của 06-structure.md).

Handler của `POST /chat-sessions/{id}/turns` ghi tin nhắn nhân viên và commit, rồi `start` một task ở đây — task **không** thuộc phạm vi của request. Response stream chỉ đọc kênh sự kiện của task (`api/sse`):
client ngắt thì stream dừng, task chạy tiếp tới cuối và ghi đúng một tin của agent. Một lượt = một lời gọi `runner.run_turn` (graph sync) trong một thread của executor riêng.

**Hạn chót.** Thread tự dừng ở `deadline` (cờ + mốc tuyệt đối đi vào từng lời gọi tool và gateway). Bộ giám sát giữ thêm một hạn chót phụ — `deadline_s + backstop_grace_s` — cho ca thread **treo** ở chỗ không kiểm cờ (ví dụ một câu SQL):
khi tới đó, nó đặt cờ huỷ, ghi khuôn `ERROR_BUSY` qua `runner.write_error_reply` và phát `turn.reply`. Thread có thể ghi **cùng lúc**; DB bảo đảm đúng một tin (migration `0012`) và sự kiện cuối luôn đọc tin thật từ DB.
**Đóng êm (`aclose`)** — SIGTERM: đợi các lượt đang chạy tới hết `grace_s`, rồi đặt cờ huỷ cho phần còn lại và đợi thêm một nhịp ngắn cho chúng tự ghi khuôn lỗi (ADR-016, hệ quả 2).
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from bo19.api.errors import error_envelope
from bo19.api.queries import chat as queries
from bo19.api.schemas.chat import jsonable, message_out
from bo19.observability.log import get_logger
from bo19.orchestrator.runner import IntakeRunner, TurnOutcome, error_template
from bo19.persistence.pool import Pool

log = get_logger("bo19.api.turns")

BACKSTOP_GRACE_S = 1.0  # sau hạn chót của lượt, chờ thêm chừng này cho thread tự ghi khuôn lỗi trước khi bộ giám sát ghi thay
WORKERS = 8  # số lượt chạy đồng thời tối đa trong một tiến trình — giá trị TẠM "chưa hiệu chỉnh" (A-057); lượt thứ chín xếp hàng, hạn chót vẫn tính từ lúc nhận
CLOSE_FLUSH_S = 2.0


@dataclass
class TurnHandle:
    events: asyncio.Queue[tuple[str, Any]] = field(default_factory=asyncio.Queue)


class TurnSupervisor:
    def __init__(self, runner: IntakeRunner, pool: Pool, *, deadline_s: float, backstop_grace_s: float = BACKSTOP_GRACE_S, workers: int = WORKERS) -> None:
        self._runner, self._pool = runner, pool
        self.deadline_s, self._grace_s = float(deadline_s), backstop_grace_s
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bo19-turn")
        self._running: dict[asyncio.Task[None], threading.Event] = {}

    @property
    def active(self) -> int:
        return len(self._running)

    def start(self, *, chat_session_id: uuid.UUID, message_id: uuid.UUID, actor_employee_id: uuid.UUID, trace_id: str) -> TurnHandle:
        """Phải gọi trong event loop của `api`. Trả ngay; lượt chạy ở task riêng."""
        handle, cancel = TurnHandle(), threading.Event()
        task = asyncio.get_running_loop().create_task(self._run(handle, cancel, chat_session_id, message_id, actor_employee_id, trace_id), name=f"turn:{message_id}")
        self._running[task] = cancel
        task.add_done_callback(lambda t: self._running.pop(t, None))
        return handle

    async def aclose(self, grace_s: float) -> None:
        tasks = set(self._running)
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=max(grace_s, 0.0))
            if pending:
                for t in pending:
                    self._running[t].set()  # hết cửa sổ drain: huỷ hợp tác — thread dừng ở lần kiểm kế tiếp và tự ghi khuôn lỗi
                await asyncio.wait(pending, timeout=CLOSE_FLUSH_S)
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------------------------------------------------------------

    async def _run(self, handle: TurnHandle, cancel: threading.Event, sid: uuid.UUID, mid: uuid.UUID, actor: uuid.UUID, trace_id: str) -> None:
        loop = asyncio.get_running_loop()
        try:
            deadline = time.monotonic() + self.deadline_s

            def on_progress(stage: str) -> None:
                loop.call_soon_threadsafe(handle.events.put_nowait, ("turn.progress", {"stage": stage}))

            work = loop.run_in_executor(self._executor, lambda: self._runner.run_turn(chat_session_id=sid, message_id=mid, actor_employee_id=actor, trace_id=trace_id,
                                                                                    deadline=deadline, cancel=cancel, on_progress=on_progress))
            done, _ = await asyncio.wait({work}, timeout=self.deadline_s + self._grace_s)
            if work in done:
                outcome = work.result()
            else:
                cancel.set()  # thread treo ở chỗ không kiểm cờ: chặn nó ghi thêm, ghi khuôn lỗi thay nó
                work.add_done_callback(lambda f: f.exception())
                log.warning("TURN_BACKSTOP", message_id=str(mid))
                reply_id = await asyncio.to_thread(self._runner.write_error_reply, chat_session_id=sid, message_id=mid, trace_id=trace_id, error_code="TURN_DEADLINE")
                outcome = TurnOutcome(reply_id, error_template("TURN_DEADLINE"), "TURN_DEADLINE")
            event = await asyncio.to_thread(self.terminal_event, outcome, sid, trace_id)
        except Exception as e:  # noqa: BLE001 — task lượt không được chết im lặng
            log.error("TURN_SUPERVISOR_FAILED", exception_type=type(e).__name__)
            event = ("turn.error", error_envelope(trace_id, "INTERNAL_ERROR"))
        handle.events.put_nowait(event)

    def terminal_event(self, outcome: TurnOutcome, chat_session_id: uuid.UUID, trace_id: str) -> tuple[str, Any]:
        """`turn.reply` đọc tin THẬT từ DB (bản có thẩm quyền, kể cả khi bên kia thắng cuộc đua ghi); không đọc được thì `turn.error`."""
        with self._pool.acquire() as conn:
            reply = queries.get_message(conn, chat_session_id, outcome.reply_message_id) if outcome.reply_message_id else None
            if reply is None:
                return "turn.error", error_envelope(trace_id, "INTERNAL_ERROR")
            active = queries.request_summary(conn, outcome.active_request_id) if outcome.active_request_id else None
        return "turn.reply", {"message": jsonable(message_out(reply)), "active_request": active, "pending_question": outcome.pending_question}
