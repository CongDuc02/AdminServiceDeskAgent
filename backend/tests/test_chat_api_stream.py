"""Bộ giám sát lượt và stream SSE — B6b (ADR-016).

Điều được chứng minh: **client ngắt kết nối thì lượt KHÔNG dừng** — task lượt chạy tới cuối và ghi đúng một tin của agent (ASGI thô: `TestClient` không mô phỏng được ngắt giữa chừng);
thread treo ở chỗ không kiểm cờ thì bộ giám sát ghi `ERROR_BUSY` ở hạn chót phụ, đúng một tin, và stream nhận `turn.reply` đọc từ DB; đóng êm (SIGTERM) chờ lượt đang chạy rồi huỷ hợp tác phần còn lại;
lifespan của app gọi đóng êm với cửa sổ drain đã cấu hình.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_chat_api_stream -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import asyncio
import json
import threading
import time
import unittest
import uuid
from unittest import mock

from fastapi.testclient import TestClient

from bo19.orchestrator.runner import TurnOutcome
from tests.chat_api_support import ChatApiBase, parse_sse
from tests.graph_support import p1, slot

MSG = "cho mình xin giấy xác nhận công tác, gửi Ngân hàng ABC"


class NgatKetNoi(ChatApiBase):
    def raw_turn(self, session_id: str, key: uuid.UUID, *, disconnect_after: bytes | None):
        """Gọi ASGI app thô. `disconnect_after` — khi frame đầu ra chứa chuỗi này thì client "ngắt" (`http.disconnect`). Trả (các frame đã nhận, app đã trả về chưa)."""
        body = json.dumps({"text": MSG}).encode()
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1", "method": "POST", "scheme": "https",
                 "path": f"/api/v1/chat-sessions/{session_id}/turns", "raw_path": f"/api/v1/chat-sessions/{session_id}/turns".encode(), "query_string": b"", "root_path": "",
                 "client": (self.ip, 50000), "server": ("testserver", 443),
                 "headers": [(b"host", b"testserver"), (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"accept", b"text/event-stream"),
                             (b"x-bo19-csrf", b"1"), (b"idempotency-key", str(key).encode()), (b"cookie", self.headers["Cookie"].encode())]}
        frames: list[bytes] = []
        disconnect = asyncio.Event()
        sent_request = False

        async def receive():
            nonlocal sent_request
            if not sent_request:
                sent_request = True
                return {"type": "http.request", "body": body, "more_body": False}
            await disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and message.get("body"):
                frames.append(message["body"])
                if disconnect_after and disconnect_after in message["body"]:
                    disconnect.set()

        async def run():
            await self.app(scope, receive, send)
            # app đã trả về (stream bị cắt) — lượt vẫn phải chạy tới cuối trong CÙNG event loop
            end = time.monotonic() + 10
            while time.monotonic() < end and not await asyncio.to_thread(self.agent_rows, session_id):
                await asyncio.sleep(0.05)
            return await asyncio.to_thread(self.agent_rows, session_id)

        return frames, asyncio.run(run())

    def test_client_ngat_sau_turn_accepted_thi_luot_van_chay_toi_cuoi_va_ghi_dung_mot_tin(self):
        sid = self.new_session()
        self.llm.set("classify_intent", p1()).set("extract_slots", {"slots": [slot("recipient_org", "Ngân hàng ABC")]})
        self.llm.delays.update(classify_intent=0.5)
        key = uuid.uuid4()
        frames, agent_rows = self.raw_turn(sid, key, disconnect_after=b"turn.accepted")
        text = b"".join(frames).decode()
        self.assertIn("turn.accepted", text)
        self.assertNotIn("turn.reply", text)  # client đã ngắt trước khi có câu trả lời
        self.assertEqual([(r[1], r[2]) for r in agent_rows], [("ASK_SLOT", key)])  # nhưng lượt vẫn chạy xong: một tin agent, trả lời đúng tin đó
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select count(*) from request where chat_session_id = %s", (sid,)).fetchone()[0], 1)  # và việc nghiệp vụ của lượt đã làm

    def test_khong_ngat_thi_stream_day_du(self):
        sid = self.new_session()
        self.llm.set("classify_intent", p1("OUT_OF_SCOPE"))
        frames, rows = self.raw_turn(sid, uuid.uuid4(), disconnect_after=None)
        self.assertEqual([e for e, _ in parse_sse(b"".join(frames).decode())], ["turn.accepted", "turn.progress", "turn.progress", "turn.reply"])
        self.assertEqual(len(rows), 1)


class ThreadTreo(ChatApiBase):
    DEADLINE_S = 1

    def setUp(self):
        super().setUp()
        self.build_app(1, backstop_grace_s=0.5)
        self.release = threading.Event()
        self.addCleanup(self.release.set)

        def hang(**kw):  # thread KHÔNG kiểm cờ, KHÔNG tự dừng — mô phỏng một câu SQL treo
            self.cancel_seen = kw["cancel"]
            self.release.wait(6)
            return TurnOutcome(None, None, "NODE_UNEXPECTED")

        patcher = mock.patch.object(self.runner, "run_turn", side_effect=hang)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_bo_giam_sat_ghi_error_busy_o_han_chot_phu_va_stream_nhan_turn_reply_tu_db(self):
        sid = self.new_session()
        started = time.monotonic()
        r = self.turn(sid, MSG)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 3.5, elapsed)  # deadline 1 s + grace 0.5 s, không phải 6 s của thread treo
        events = parse_sse(r.text)
        self.assertEqual([e for e, _ in events], ["turn.accepted", "turn.reply"])
        reply = events[-1][1]
        self.assertEqual((reply["message"]["reply_template_id"], reply["message"]["author"]), ("ERROR_BUSY", "AGENT"))
        self.assertEqual([x[1] for x in self.agent_rows(sid)], ["ERROR_BUSY"])  # đúng một tin
        self.assertTrue(self.cancel_seen.is_set())  # bộ giám sát đã đặt cờ huỷ: thread treo, khi tỉnh, không ghi thêm gì
        self.release.set()  # thread treo được thả: nó không ghi thêm gì (run_turn đã bị patch trả TurnOutcome rỗng)
        time.sleep(0.3)
        self.assertEqual(len(self.agent_rows(sid)), 1)

    def test_sau_do_phien_nhan_luot_moi_khong_bi_ket_o_turn_in_progress(self):
        sid = self.new_session()
        self.turn(sid, MSG)  # lượt trên có tin agent (ERROR_BUSY) → không còn "chưa trả lời"
        self.release.set()
        self.llm.set("classify_intent", p1("OUT_OF_SCOPE"))
        with mock.patch.object(self.runner, "run_turn", wraps=None) as m:
            m.side_effect = lambda **kw: TurnOutcome(None, None, "NODE_UNEXPECTED")
            r = self.turn(sid, "tin thứ hai")
        self.assertEqual(r.status_code, 200)


class DongEm(ChatApiBase):
    def start(self, sid: str, text: str = MSG):
        from bo19.tool_layer.endpoint_ops.chat import chat_message_append
        from bo19.tool_layer.kernel.permission import employee_context
        with self.pool.acquire() as conn:
            ctx = employee_context(conn, self.eid)
        mid = uuid.uuid4()
        chat_message_append(self.pool, ctx, chat_session_id=uuid.UUID(sid), message_id=mid, author="EMPLOYEE", body=text)
        return mid, self.supervisor.start(chat_session_id=uuid.UUID(sid), message_id=mid, actor_employee_id=self.eid, trace_id=str(uuid.uuid4()))

    def test_dong_em_cho_luot_dang_chay_xong_trong_cua_so_drain(self):
        sid = self.new_session()
        self.llm.set("classify_intent", p1("OUT_OF_SCOPE")).delays.update(classify_intent=0.6)

        async def run():
            mid, handle = self.start(sid)
            await asyncio.sleep(0.2)
            self.assertEqual(self.supervisor.active, 1)
            await self.supervisor.aclose(5.0)
            return mid, handle

        mid, handle = asyncio.run(run())
        self.assertEqual(self.supervisor.active, 0)
        self.assertEqual([(r[1], r[2]) for r in self.agent_rows(sid)], [("OUT_OF_SCOPE_GENERIC", mid)])  # lượt đã xong tự nhiên, không bị huỷ

    def test_het_cua_so_drain_thi_huy_hop_tac_va_luot_tu_ghi_khuon_loi(self):
        sid = self.new_session()
        self.llm.set("classify_intent", p1()).delays.update(classify_intent=1.0)

        async def run():
            mid, handle = self.start(sid)
            await asyncio.sleep(0.2)
            await self.supervisor.aclose(0.1)  # hết cửa sổ: đặt cờ huỷ
            return mid

        mid = asyncio.run(run())
        rows = self.wait_for_agent(sid)
        self.assertEqual([(r[1], r[2]) for r in rows], [("ERROR_BUSY", mid)])  # thread dừng ở lần kiểm cờ kế tiếp và tự ghi khuôn lỗi
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select count(*) from request where chat_session_id = %s", (sid,)).fetchone()[0], 0)  # cờ bật trước `request_open`: không ghi nghiệp vụ nào

    def test_lifespan_goi_dong_em_voi_cua_so_drain_cua_cau_hinh(self):
        from bo19.api.app import create_app
        from bo19.api.deps.state import AppState
        from tests.auth_support import SECRET
        fake = mock.Mock()
        fake.aclose = mock.AsyncMock()
        app = create_app(AppState(pool=self.pool, session_secret=SECRET, verifier=self.verifier, supervisor=fake, drain_s=7.5))
        with TestClient(app):
            fake.aclose.assert_not_called()
        fake.aclose.assert_awaited_once_with(7.5)

    def test_hai_luot_cua_hai_phien_chay_dong_thoi_moi_phien_dung_mot_tin(self):
        other = self.db.make_employee(roles=("EMPLOYEE",))[0]
        s1, s2 = self.new_session(), self.new_session(self.as_user(other))
        self.llm.set("classify_intent", p1("OUT_OF_SCOPE")).delays.update(classify_intent=0.4)

        async def run():
            a = self.start(s1)
            from bo19.tool_layer.endpoint_ops.chat import chat_message_append
            from bo19.tool_layer.kernel.permission import employee_context
            with self.pool.acquire() as conn:
                octx = employee_context(conn, other)
            mid = uuid.uuid4()
            chat_message_append(self.pool, octx, chat_session_id=uuid.UUID(s2), message_id=mid, author="EMPLOYEE", body=MSG)
            self.supervisor.start(chat_session_id=uuid.UUID(s2), message_id=mid, actor_employee_id=other, trace_id=str(uuid.uuid4()))
            await self.supervisor.aclose(5.0)
            return a

        asyncio.run(run())
        self.assertEqual((len(self.agent_rows(s1)), len(self.agent_rows(s2))), (1, 1))


if __name__ == "__main__":
    unittest.main()
