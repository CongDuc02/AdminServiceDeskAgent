"""Nền chung cho test endpoint hội thoại (B6b): `AuthBase` (app + client + đăng nhập) cộng `IntakeRunner` thật, `TurnSupervisor` và provider LLM giả theo tên lời gọi.

Không có test nào ở đây. `TestClient` chạy trọn một request ASGI rồi mới trả response, nên một stream SSE được đọc sau khi lượt kết thúc — thứ tự sự kiện kiểm được, nhịp thời gian thì không;
ca "client ngắt kết nối" dùng ASGI thô ở `test_chat_api_stream.py`.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi.testclient import TestClient

from bo19.ai_gateway.budget import Budget
from bo19.ai_gateway.gateway import Gateway
from bo19.ai_gateway.providers import ProviderClient
from bo19.ai_gateway.routing.profiles import load_profiles
from bo19.api.app import create_app
from bo19.api.deps.state import AppState
from bo19.api.turns import TurnSupervisor
from bo19.orchestrator.runner import IntakeRunner
from tests.auth_support import CSRF, SECRET, AuthBase
from tests.graph_support import KEY, FakeLlm

ACCEPT = {"Accept": "text/event-stream"}


def parse_sse(text: str) -> list[tuple[str, Any]]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


class ChatApiBase(AuthBase):
    DEADLINE_S = 20

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
        self.build_app(self.DEADLINE_S)
        self.eid, self.code = self.employee()
        self.headers = self.as_user(self.eid)

    def build_app(self, deadline_s: int, *, backstop_grace_s: float = 1.0) -> None:
        self.supervisor = TurnSupervisor(self.runner, self.pool, deadline_s=deadline_s, backstop_grace_s=backstop_grace_s)
        self.app = create_app(AppState(pool=self.pool, session_secret=SECRET, verifier=self.verifier, supervisor=self.supervisor, turn_deadline_s=deadline_s, turn_margin_s=10))
        self.client = TestClient(self.app, raise_server_exceptions=False, base_url="https://testserver", client=(self.ip, 50000))

    # --- thao tác qua HTTP ------------------------------------------------------------------------------------------------------

    def open_session(self, headers=None, key: uuid.UUID | None = None):
        return self.client.post("/api/v1/chat-sessions", headers={**CSRF, **(headers or self.headers), "Idempotency-Key": str(key or uuid.uuid4())})

    def new_session(self, headers=None) -> str:
        r = self.open_session(headers)
        self.assertIn(r.status_code, (200, 201), r.text)
        return r.json()["id"]

    def turn(self, session_id: str, text: str, *, key: uuid.UUID | None = None, headers=None, extra=None):
        return self.client.post(f"/api/v1/chat-sessions/{session_id}/turns", json={"text": text},
                                headers={**CSRF, **ACCEPT, **(headers or self.headers), "Idempotency-Key": str(key or uuid.uuid4()), **(extra or {})})

    def agent_rows(self, session_id: str) -> list[tuple]:
        with self.db.connect("bo19_migrator") as c:
            return c.execute("select seq, reply_template_id, in_reply_to_message_id from chat_message where chat_session_id = %s and author = 'AGENT' order by seq", (session_id,)).fetchall()

    def age_message(self, message_id, seconds: float) -> None:
        with self.db.connect("bo19_migrator") as c:
            c.execute("update chat_message set created_at = now() - make_interval(secs => %s) where id = %s", (seconds, message_id))

    def wait_for_agent(self, session_id: str, timeout: float = 10.0) -> list[tuple]:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            rows = self.agent_rows(session_id)
            if rows:
                return rows
            time.sleep(0.05)
        return []
