"""Bốn endpoint hội thoại qua ASGI app thật, PostgreSQL thật, `IntakeRunner` và `TurnSupervisor` thật, provider LLM giả — B6b.

Điều được chứng minh: `POST /chat-sessions` idempotent theo khoá, lặp lại giữ mã HTTP của lần đầu, khoá của người khác là `IDEMPOTENCY_KEY_CONFLICT`; chỉ chủ phiên đọc được phiên và tin nhắn
(`NOT_FOUND` cho cả "không tồn tại" lẫn "của người khác"); keyset theo `seq` giảm dần và cursor gắn với phiên; `POST …/turns` phát đúng chuỗi sự kiện, từ chối trước khi mở stream bằng `ErrorEnvelope`,
lặp lại cùng khoá thì phát lại từ DB mà không chạy lại lượt, `TURN_IN_PROGRESS` và `TURN_NOT_FINISHED` theo hạn chót; lỗi và thông điệp lỗi không mang văn bản của người dùng.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_chat_api -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest
import uuid

from bo19.api.errors import CATALOG
from tests.auth_support import CSRF
from tests.chat_api_support import ACCEPT, ChatApiBase, parse_sse
from tests.graph_support import p1, slot

RES = "NOI_DUNG_RES_KHONG_DUOC_LOT_RA_9f3a"
MSG = "cho mình xin giấy xác nhận công tác, gửi Ngân hàng ABC"


class MoPhien(ChatApiBase):
    def test_tao_phien_moi_201_phien_dang_mo_200_cung_khoa_lap_lai_201_kem_header(self):
        key = uuid.uuid4()
        first = self.open_session(key=key)
        self.assertEqual(first.status_code, 201, first.text)
        body = first.json()
        self.assertEqual((body["id"], body["status"], body["closed_at"], body["close_reason"]), (str(key), "OPEN", None, None))  # khoá = id của phiên (mục 1.8)
        self.assertNotIn("idempotent-replayed", first.headers)
        again = self.open_session(key=key)
        self.assertEqual((again.status_code, again.headers["idempotent-replayed"], again.json()["id"]), (201, "true", str(key)))  # cùng mã HTTP của lần tạo đầu
        other_key = self.open_session()
        self.assertEqual((other_key.status_code, other_key.json()["id"]), (200, str(key)))  # đã có phiên đang mở: trả phiên đó, khoá khác không tạo phiên thứ hai

    def test_khoa_cua_nguoi_khac_la_conflict_khong_lo_gi(self):
        other, _ = self.employee()
        key = uuid.UUID(self.new_session(self.as_user(other)))
        r = self.open_session(key=key)
        self.assert_envelope(r, "IDEMPOTENCY_KEY_CONFLICT", 409)
        self.assertNotIn(str(other), r.text)

    def test_thieu_hoac_sai_khoa_va_thieu_quyen_va_thieu_csrf(self):
        r = self.client.post("/api/v1/chat-sessions", headers={**CSRF, **self.headers})
        self.assert_envelope(r, "IDEMPOTENCY_KEY_REQUIRED", 400)
        r = self.client.post("/api/v1/chat-sessions", headers={**CSRF, **self.headers, "Idempotency-Key": "khong-phai-uuid"})
        self.assertEqual(self.assert_envelope(r, "VALIDATION_FAILED", 422)["details"]["fields"], [{"field": "Idempotency-Key", "code": "INVALID_FORMAT"}])
        no_perm, _ = self.employee(roles=())
        r = self.open_session(self.as_user(no_perm))
        self.assertEqual(self.assert_envelope(r, "PERMISSION_DENIED", 403)["details"], {"permission": "request.create|request.create_on_behalf"})
        r = self.client.post("/api/v1/chat-sessions", headers={**self.headers, "Idempotency-Key": str(uuid.uuid4())})
        self.assert_envelope(r, "CSRF_HEADER_MISSING", 403)
        r = self.client.post("/api/v1/chat-sessions", headers={**CSRF, "Idempotency-Key": str(uuid.uuid4())})
        self.assert_envelope(r, "UNAUTHENTICATED", 401)


class DocPhienVaTinNhan(ChatApiBase):
    def test_chi_chu_phien_doc_duoc_phien(self):
        sid = self.new_session()
        r = self.client.get(f"/api/v1/chat-sessions/{sid}", headers=self.headers)
        self.assertEqual((r.status_code, r.json()["id"], r.json()["status"]), (200, sid, "OPEN"))
        other, _ = self.employee()
        for path in (sid, str(uuid.uuid4())):
            r = self.client.get(f"/api/v1/chat-sessions/{path}", headers=self.as_user(other))
            self.assert_envelope(r, "NOT_FOUND", 404)  # của người khác và không tồn tại: cùng một lỗi
        self.assert_envelope(self.client.get(f"/api/v1/chat-sessions/{sid}"), "UNAUTHENTICATED", 401)

    def test_tin_nhan_moi_nhat_truoc_keyset_theo_seq_va_cursor_gan_voi_phien(self):
        sid = self.new_session()
        for i in range(5):
            self.llm.set("classify_intent", p1("OUT_OF_SCOPE"))
            self.turn(sid, f"tin {i}")
        r = self.client.get(f"/api/v1/chat-sessions/{sid}/messages?limit=4", headers=self.headers)
        page = r.json()
        self.assertEqual([m["seq"] for m in page["items"]], [10, 9, 8, 7])  # 5 lượt × (tin nhân viên + tin agent), mới nhất trước
        self.assertEqual([m["author"] for m in page["items"]], ["AGENT", "EMPLOYEE"] * 2)
        self.assertEqual(set(page["items"][0]), {"id", "seq", "author", "request_id", "body", "content_erased", "reply_template_id", "created_at"})
        rest = self.client.get(f"/api/v1/chat-sessions/{sid}/messages?limit=100&cursor={page['next_cursor']}", headers=self.headers).json()
        self.assertEqual(([m["seq"] for m in rest["items"]], rest["next_cursor"]), ([6, 5, 4, 3, 2, 1], None))
        with self.db.connect("bo19_migrator") as c:  # phiên thứ hai của chính người này (phiên cũ đóng): cursor của phiên cũ không dùng được ở đây
            c.execute("update chat_session set status = 'CLOSED', closed_at = now(), close_reason = 'IDLE_TIMEOUT' where id = %s", (sid,))
        mine = self.new_session()
        self.assertNotEqual(mine, sid)
        r = self.client.get(f"/api/v1/chat-sessions/{mine}/messages?cursor={page['next_cursor']}", headers=self.headers)
        self.assert_envelope(r, "VALIDATION_FAILED", 422)  # cursor gắn với bộ lọc (phiên) đã dùng
        for bad in ("limit=0", "limit=101", "cursor=khong-hop-le"):
            self.assert_envelope(self.client.get(f"/api/v1/chat-sessions/{sid}/messages?{bad}", headers=self.headers), "VALIDATION_FAILED", 422)

    def test_tin_nhan_cua_nguoi_khac_la_not_found(self):
        sid = self.new_session()
        other, _ = self.employee()
        self.assert_envelope(self.client.get(f"/api/v1/chat-sessions/{sid}/messages", headers=self.as_user(other)), "NOT_FOUND", 404)


class LuotChat(ChatApiBase):
    def happy(self, sid: str, key: uuid.UUID | None = None, text: str = MSG):
        self.llm.set("classify_intent", p1()).set("extract_slots", {"slots": [slot("recipient_org", "Ngân hàng ABC")]})
        return self.turn(sid, text, key=key)

    def test_chuoi_su_kien_va_noi_dung(self):
        sid = self.new_session()
        key = uuid.uuid4()
        r = self.happy(sid, key)
        self.assertEqual((r.status_code, r.headers["content-type"].split(";")[0], r.headers["cache-control"]), (200, "text/event-stream", "no-cache"))
        self.assertNotIn("idempotent-replayed", r.headers)
        events = parse_sse(r.text)
        self.assertEqual([e for e, _ in events], ["turn.accepted", "turn.progress", "turn.progress", "turn.reply"])
        accepted, _, _, reply = [d for _, d in events]
        self.assertEqual((accepted["message"]["id"], accepted["message"]["author"], accepted["message"]["body"]), (str(key), "EMPLOYEE", MSG))
        self.assertEqual([d["stage"] for e, d in events if e == "turn.progress"], ["UNDERSTANDING", "PREPARING_REPLY"])
        self.assertEqual((reply["message"]["author"], reply["message"]["reply_template_id"]), ("AGENT", "ASK_SLOT"))
        self.assertEqual(reply["pending_question"]["kind"], "ASK_SLOT")
        self.assertIn("purpose", reply["pending_question"]["slot_names"])
        ar = reply["active_request"]
        self.assertEqual((ar["request_type_code"], ar["status"], ar["status_label"], ar["artifacts"], ar["chat_session_id"]), ("WORK_CONFIRMATION", "NEEDS_INFO", "Cần bổ sung thông tin", [], sid))
        self.assertEqual(ar["beneficiary"]["id"], str(self.eid))
        self.assertEqual(len(self.agent_rows(sid)), 1)

    def test_gui_lai_cung_khoa_sau_khi_xong_phat_lai_tu_db_khong_chay_lai_luot(self):
        sid = self.new_session()
        key = uuid.uuid4()
        first = parse_sse(self.happy(sid, key).text)
        calls = len(self.llm.requests)
        again = self.turn(sid, MSG, key=key)
        self.assertEqual((again.status_code, again.headers["idempotent-replayed"]), (200, "true"))
        events = parse_sse(again.text)
        self.assertEqual([e for e, _ in events], ["turn.accepted", "turn.reply"])
        self.assertEqual(events[1][1]["message"]["id"], first[-1][1]["message"]["id"])
        self.assertEqual(events[1][1]["message"]["body"], first[-1][1]["message"]["body"])
        self.assertEqual(len(self.llm.requests), calls)  # không gọi provider lần nữa
        self.assertEqual(len(self.agent_rows(sid)), 1)

    def test_loi_truoc_khi_mo_stream_la_json_error_envelope(self):
        sid = self.new_session()
        r = self.client.post(f"/api/v1/chat-sessions/{sid}/turns", json={"text": MSG}, headers={**CSRF, **self.headers, "Idempotency-Key": str(uuid.uuid4())})
        self.assert_envelope(r, "NOT_ACCEPTABLE", 406)
        r = self.client.post(f"/api/v1/chat-sessions/{sid}/turns", json={"text": MSG}, headers={**CSRF, **ACCEPT, **self.headers})
        self.assert_envelope(r, "IDEMPOTENCY_KEY_REQUIRED", 400)
        r = self.client.post(f"/api/v1/chat-sessions/{sid}/turns", json={"text": MSG}, headers={**ACCEPT, **self.headers, "Idempotency-Key": str(uuid.uuid4())})
        self.assert_envelope(r, "CSRF_HEADER_MISSING", 403)
        self.assert_envelope(self.client.post(f"/api/v1/chat-sessions/{sid}/turns", json={"text": MSG}, headers={**CSRF, **ACCEPT, "Idempotency-Key": str(uuid.uuid4())}), "UNAUTHENTICATED", 401)
        for body in ({"text": ""}, {"text": "x" * 2001}, {"text": MSG, "extra": 1}, {}):
            r = self.client.post(f"/api/v1/chat-sessions/{sid}/turns", json=body, headers={**CSRF, **ACCEPT, **self.headers, "Idempotency-Key": str(uuid.uuid4())})
            self.assert_envelope(r, "VALIDATION_FAILED", 422)
        self.assertEqual(self.llm.requests, [])  # từ chối trước khi chạm provider

    def test_phien_cua_nguoi_khac_la_not_found_khong_ghi_gi(self):
        sid = self.new_session()
        other, _ = self.employee()
        r = self.turn(sid, MSG, headers=self.as_user(other))
        self.assert_envelope(r, "NOT_FOUND", 404)
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select count(*) from chat_message where chat_session_id = %s", (sid,)).fetchone()[0], 0)

    def test_thieu_quyen_la_permission_denied(self):
        no_perm, _ = self.employee(roles=())
        r = self.turn(str(uuid.uuid4()), MSG, headers=self.as_user(no_perm))
        self.assert_envelope(r, "PERMISSION_DENIED", 403)

    def test_phien_da_dong_la_chat_session_closed_kem_ly_do(self):
        sid = self.new_session()
        with self.db.connect("bo19_migrator") as c:
            c.execute("update chat_session set status = 'CLOSED', closed_at = now(), close_reason = 'IDLE_TIMEOUT' where id = %s", (sid,))
        body = self.assert_envelope(self.turn(sid, MSG), "CHAT_SESSION_CLOSED", 409)
        self.assertEqual(body["details"], {"close_reason": "IDLE_TIMEOUT"})

    def test_khoa_da_dung_cho_tin_cua_nguoi_khac_la_conflict(self):
        sid = self.new_session()
        key = uuid.uuid4()
        other_headers = self.as_user(self.employee()[0])  # tin của người khác dùng `key` trước
        other_session = self.new_session(other_headers)
        self.llm.set("classify_intent", p1("OUT_OF_SCOPE"))
        self.turn(other_session, "tin của người khác", key=key, headers=other_headers)
        body = self.assert_envelope(self.turn(sid, MSG, key=key), "IDEMPOTENCY_KEY_CONFLICT", 409)
        self.assertNotIn("người khác", body["message"])  # không trả nội dung dòng đang có

    def test_turn_in_progress_khi_luot_truoc_chua_tra_loi_va_con_han(self):
        sid = self.new_session()
        self.add_unanswered(sid)
        r = self.turn(sid, "tin thứ hai")
        body = self.assert_envelope(r, "TURN_IN_PROGRESS", 409)
        self.assertTrue(1 <= body["details"]["retry_after_seconds"] <= 30)
        self.assertEqual(r.headers["retry-after"], str(body["details"]["retry_after_seconds"]))
        self.assertEqual(self.llm.requests, [])

    def add_unanswered(self, sid: str) -> uuid.UUID:
        from bo19.tool_layer.endpoint_ops.chat import chat_message_append
        from bo19.tool_layer.kernel.permission import employee_context
        with self.pool.acquire() as conn:
            ctx = employee_context(conn, self.eid)
        mid = uuid.uuid4()
        chat_message_append(self.pool, ctx, chat_session_id=uuid.UUID(sid), message_id=mid, author="EMPLOYEE", body="tin chưa có câu trả lời")
        return mid

    def test_het_han_chot_cong_bien_thi_nhan_luot_moi(self):
        sid = self.new_session()
        old = self.add_unanswered(sid)
        self.age_message(old, 31)  # WV-02 20 s + WV-03 10 s = 30 s
        r = self.happy(sid)
        self.assertEqual(r.status_code, 200, r.text)

    def test_gui_lai_tin_chua_co_cau_tra_loi_la_turn_not_finished_noi_tin_con_nguyen(self):
        sid = self.new_session()
        mid = self.add_unanswered(sid)
        r = self.turn(sid, "gui lai", key=mid)
        body = self.assert_envelope(r, "TURN_NOT_FINISHED", 409)
        self.assertEqual((body["details"]["message_saved"], body["details"]["turn_abandoned"]), (True, False))
        self.assertIn("đã được lưu", body["message"])
        self.assertIn("retry-after", r.headers)
        self.age_message(mid, 31)
        r = self.turn(sid, "gui lai", key=mid)
        body = self.assert_envelope(r, "TURN_NOT_FINISHED", 409)
        self.assertEqual((body["details"]["message_saved"], body["details"]["turn_abandoned"]), (True, True))
        self.assertIn("đã được lưu", body["message"])
        self.assertIn("gửi lại nội dung", body["message"])
        self.assertNotIn("retry-after", r.headers)

    def test_loi_va_thong_diep_loi_khong_mang_van_ban_nguoi_dung(self):
        sid = self.new_session()
        r = self.turn(sid, "x" * 2001 + RES)
        self.assertNotIn(RES, r.text)
        self.llm.script["classify_intent"] = []  # provider 5xx: lượt lỗi
        r = self.turn(sid, f"xin giấy {RES}")
        self.assertEqual(parse_sse(r.text)[-1][1]["message"]["reply_template_id"], "ERROR_BUSY")  # lượt lỗi vẫn kết thúc bằng khuôn "hệ thống đang bận" qua turn.reply
        self.assertNotIn(RES, parse_sse(r.text)[-1][1]["message"]["body"])
        self.assertEqual(len(self.agent_rows(sid)), 1)

    def test_danh_muc_ma_loi_cua_chat_khop_bang_http_cua_tai_lieu(self):
        for code, http in (("TURN_IN_PROGRESS", 409), ("TURN_NOT_FINISHED", 409), ("CHAT_SESSION_CLOSED", 409), ("IDEMPOTENCY_KEY_REQUIRED", 400), ("IDEMPOTENCY_KEY_CONFLICT", 409),
                           ("NOT_ACCEPTABLE", 406), ("PERMISSION_DENIED", 403)):
            self.assertEqual(CATALOG[code].http, http, code)


if __name__ == "__main__":
    unittest.main()
