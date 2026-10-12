"""Nền chung cho test `intake_graph` (B6b): PostgreSQL thật đã migrate (kèm cấu hình `WORK_CONFIRMATION` và checkpoint), provider LLM là transport giả theo tên lời gọi,
`IntakeRunner` thật (checkpointer thật, graph thật). Không có test nào ở đây. Mọi nhân viên, tin nhắn, giá trị là dữ liệu giả của test.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from typing import Any

import httpx

from bo19.ai_gateway.budget import Budget
from bo19.ai_gateway.gateway import Gateway
from bo19.ai_gateway.providers import ProviderClient
from bo19.ai_gateway.routing.profiles import load_profiles
from bo19.orchestrator.runner import IntakeRunner, TurnOutcome
from bo19.tool_layer.endpoint_ops.chat import chat_message_append, chat_session_open
from tests.tool_support import RES, ToolBase  # noqa: F401 — RES cho test dùng lại

USAGE = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150, "prompt_time": 0.01, "completion_time": 0.2, "completion_tokens_details": {"reasoning_tokens": 12}}
KEY = "KHOA_API_GIA_CUA_TEST"


def p1(intent: str = "WORK_CONFIRMATION", secondary: str | None = None, confidence: str = "high") -> dict[str, Any]:
    return {"intent": intent, "secondary_intent": secondary, "confidence": confidence, "retrieval_query": None}


def slot(name: str, value: Any, quote: str | None = None) -> dict[str, Any]:
    quote = quote if quote is not None else str(value)
    return {"slot_name": name, "value": value, "evidence_span": [0, len(quote)], "evidence_quote": quote}


class FakeLlm:
    """Transport giả: trả lần lượt các đầu ra đã dựng sẵn THEO TÊN lời gọi (`classify_intent`, `extract_slots`); ghi lại mọi request và thời điểm."""

    def __init__(self) -> None:
        self.script: dict[str, list[Any]] = {}
        self.delays: dict[str, float] = {}
        self.requests: list[tuple[str, float, dict[str, Any]]] = []  # (tên, thời điểm monotonic, thân)
        self.transport = httpx.MockTransport(self.handle)

    def will(self, name: str, *outputs: Any) -> "FakeLlm":
        self.script.setdefault(name, []).extend(outputs)
        return self

    def calls(self, name: str) -> list[dict[str, Any]]:
        return [body for n, _, body in self.requests if n == name]

    async def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        name = body["response_format"]["json_schema"]["name"]
        self.requests.append((name, time.monotonic(), body))
        delay = self.delays.get(name, 0)
        if delay:
            await asyncio.sleep(delay)
        queue = self.script.get(name)
        if not queue:
            return httpx.Response(500, json={"error": {"message": "không có kịch bản", "type": "server_error"}})
        step = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(step, httpx.Response):
            return step
        text = step if isinstance(step, str) else json.dumps(step, ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}], "usage": USAGE})


class GraphBase(ToolBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.llm = FakeLlm()
        client = ProviderClient(base_url="https://llm.example.test/openai/v1", api_key=KEY, transport=cls.llm.transport)
        cls.gateway = Gateway(profiles=load_profiles().profiles, client=client, budget=Budget(cls.pool))
        cls.runner = IntakeRunner.open(pool=cls.pool, gateway=cls.gateway, dsn=cls.db.dsn("bo19_app"))

    @classmethod
    def tearDownClass(cls):
        cls.runner.close()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.llm.script.clear()
        self.llm.delays.clear()
        self.llm.requests.clear()
        self.eid, self.ctx_ = self.employee()
        self.sid = chat_session_open(self.pool, self.ctx_).chat_session_id

    # --- một lượt -----------------------------------------------------------------------------------------------------------------

    def send(self, text: str, *, ctx=None, sid=None) -> uuid.UUID:
        mid = uuid.uuid4()
        chat_message_append(self.pool, ctx or self.ctx_, chat_session_id=sid or self.sid, message_id=mid, author="EMPLOYEE", body=text)
        return mid

    def turn(self, text: str, *, budget_s: float = 20.0, runner: IntakeRunner | None = None, cancel: threading.Event | None = None, progress: list | None = None,
             message_id: uuid.UUID | None = None) -> TurnOutcome:
        mid = message_id or self.send(text)
        self.last_mid = mid
        return (runner or self.runner).run_turn(chat_session_id=self.sid, message_id=mid, actor_employee_id=self.eid, trace_id=str(uuid.uuid4()),
                                                deadline=time.monotonic() + budget_s, cancel=cancel, on_progress=(progress.append if progress is not None else None))

    # --- đọc kiểm (bằng chủ bảng) -------------------------------------------------------------------------------------------------

    def agent_messages(self) -> list[tuple]:
        with self.db.connect("bo19_migrator") as c:
            return c.execute("select seq, reply_template_id, in_reply_to_message_id, body from chat_message where chat_session_id = %s and author = 'AGENT' order by seq", (self.sid,)).fetchall()

    def requests_of_session(self) -> list[dict]:
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select id, request_type_code, status from request where chat_session_id = %s order by created_at", (self.sid,))
            return [dict(zip(("id", "request_type_code", "status"), r)) for r in cur.fetchall()]

    def slots_of(self, request_id: uuid.UUID) -> dict[str, tuple]:
        with self.db.connect("bo19_migrator") as c:
            return {r[0]: (r[1], r[2]) for r in c.execute("select slot_name, value_status, value from request_slot where request_id = %s", (request_id,)).fetchall()}

    def graph_state(self) -> dict | None:
        return self.runner._graph.values(f"intake:{self.sid}")  # noqa: SLF001 — test đọc state của thread

    def checkpoint_dump(self) -> str:
        """Mọi byte của thread trong ba bảng checkpoint, để dò giá trị RES."""
        thread = f"intake:{self.sid}"
        parts: list[str] = []
        with self.db.connect("bo19_migrator") as c:
            for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
                for row in c.execute(f"select * from {table} where thread_id = %s", (thread,)).fetchall():  # noqa: S608
                    parts.append(repr([bytes(x).decode("utf-8", "replace") if isinstance(x, (bytes, memoryview)) else x for x in row]))
            parts.append(repr(c.execute("select * from graph_thread where thread_id = %s", (thread,)).fetchall()))
        return "\n".join(parts)
