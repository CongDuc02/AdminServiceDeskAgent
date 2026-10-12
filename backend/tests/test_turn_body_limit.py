"""Trần body và độ dài của `POST /chat-sessions/{id}/turns` — B6b (PO duyệt 2026-10-12, `proposals/turn-body-limit.md`).

Ba tầng: (1) `BodyLimitMiddleware` với mẫu đường dẫn, ASGI thuần, không DB — trần lấy từ `BODY_LIMITS` của app thật; (2) qua app thật trên PostgreSQL thật — 413 trước xác thực, không ghi tin nhắn,
không gọi LLM; độ dài tính bằng **code point sau NFC** (NFD ~1.500 chữ có dấu được nhận, > 2000 sau NFC bị từ chối); (3) khớp `openapi.yaml`, `05-api.md` và `working_values`.

Cần BO19_TEST_PG_SUPERUSER_DSN cho tầng 2. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_turn_body_limit -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import json
import unicodedata
import unittest
import uuid
from pathlib import Path

import yaml

from bo19.api.app import BODY_LIMITS
from bo19.api.body_limit import BodyLimitMiddleware
from bo19.config import working_values as wv
from tests.auth_support import CSRF
from tests.chat_api_support import ACCEPT, ChatApiBase, parse_sse
from tests.graph_support import p1
from tests.test_login_limits import FakeApp, run

LIMIT = wv.TURN_BODY_MAX_BYTES
SID = "6f0c1f0e-0b9a-4b8e-9a43-6b1b2d1c0f11"
PATH = f"/api/v1/chat-sessions/{SID}/turns"
ROOT = Path(__file__).resolve().parents[2]
E_NFC = "ệ"
E_NFD = unicodedata.normalize("NFD", E_NFC)  # e + dấu nặng + dấu mũ: 3 code point


class MiddlewareMauDuong(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp()
        self.mw = BodyLimitMiddleware(self.app, BODY_LIMITS)  # cấu hình thật của app

    def assert_413(self, status, body):
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(body)["error_code"], "PAYLOAD_TOO_LARGE")
        self.assertEqual(self.app.bodies, [])

    def test_tran_la_cong_thuc_gan_wv15(self):
        self.assertEqual(LIMIT, wv.CHAT_MESSAGE_MAX_CHARS * 18 + 1024)
        self.assertEqual(LIMIT, 37024)

    def test_dung_bang_tran_qua_vuot_mot_byte_la_413(self):
        status, _, _ = run(self.mw, path=PATH, chunks=(b"x" * LIMIT,))
        self.assertEqual((status, self.app.bodies), (204, [b"x" * LIMIT]))
        self.app.bodies.clear()
        status, body, _ = run(self.mw, path=PATH, chunks=(b"x" * (LIMIT + 1),))
        self.assert_413(status, body)

    def test_stream_khong_content_length_dung_doc_khi_da_vuot_tran(self):
        piece = LIMIT // 4 + 1
        status, body, taken = run(self.mw, path=PATH, chunks=tuple(b"x" * piece for _ in range(10)))
        self.assert_413(status, body)
        self.assertEqual(taken, 4)  # vượt ở mảnh thứ tư → không đọc sáu mảnh còn lại

    def test_content_length_lon_tu_choi_som_va_khong_tin_header_noi_doi(self):
        status, body, taken = run(self.mw, path=PATH, headers=[("Content-Length", str(LIMIT + 1))], chunks=(b"{}",))
        self.assert_413(status, body)
        self.assertEqual(taken, 0)
        status, body, _ = run(self.mw, path=PATH, headers=[("Content-Length", "10")], chunks=(b"x" * (LIMIT + 5),))  # header nói dối: đếm byte thực
        self.assert_413(status, body)

    def test_id_la_mot_doan_bat_ky_ke_ca_id_hong(self):
        for bad in ("khong-phai-uuid", "1", SID.upper(), "%E1%BB%87"):
            self.app.bodies.clear()
            status, body, _ = run(self.mw, path=f"/api/v1/chat-sessions/{bad}/turns", chunks=(b"x" * (LIMIT + 1),))
            self.assert_413(status, body)

    def test_duong_khac_phuong_thuc_khac_di_thang(self):
        big = b"x" * (LIMIT * 2)
        cases = [{"method": "GET", "path": PATH}, {"method": "POST", "path": f"/api/v1/chat-sessions/{SID}/messages"}, {"method": "POST", "path": "/api/v1/chat-sessions"},
                 {"method": "POST", "path": PATH + "/"}, {"method": "POST", "path": f"/api/v1/chat-sessions/{SID}/x/turns"}, {"method": "POST", "path": f"/api/v1/chat-sessions//turns"},
                 {"method": "POST", "path": f"/chat-sessions/{SID}/turns"}, {"method": "POST", "path": f"/api/v1/chat-sessions/{SID}/turns/extra"}]
        for kwargs in cases:
            self.app.bodies.clear()
            status, _, _ = run(self.mw, chunks=(big,), **kwargs)
            self.assertEqual((status, self.app.bodies), (204, [big]), kwargs)

    def test_dang_nhap_giu_tran_rieng_4096(self):
        status, body, _ = run(self.mw, path="/api/v1/auth/session", chunks=(b"x" * (wv.LOGIN_BODY_MAX_BYTES + 1),))
        self.assert_413(status, body)
        status, _, _ = run(self.mw, path="/api/v1/auth/session", chunks=(b"x" * wv.LOGIN_BODY_MAX_BYTES,))
        self.assertEqual(status, 204)


def escaped_body(text: str) -> bytes:
    """Body JSON mà client mã hoá MỌI ký tự thành `\\uXXXX` (xấu nhất: 6 byte mỗi code point, kể cả chữ ASCII)."""
    return ('{"text":"' + "".join(f"\\u{ord(c):04x}" for c in text) + '"}').encode("ascii")


class QuaAppThat(ChatApiBase):
    def raw(self, session_id: str, content: bytes, *, headers=None):
        return self.client.post(f"/api/v1/chat-sessions/{session_id}/turns", content=content,
                                headers={**CSRF, **ACCEPT, "Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4()), **(self.headers if headers is None else headers)})

    def message_rows(self, session_id: str) -> int:
        with self.db.connect("bo19_migrator") as c:
            return c.execute("select count(*) from chat_message where chat_session_id = %s", (session_id,)).fetchone()[0]

    def test_body_qua_tran_la_413_khong_ghi_tin_khong_goi_llm(self):
        sid = self.new_session()
        r = self.raw(sid, b'{"text":"' + b"x" * LIMIT + b'"}')
        body = self.assert_envelope(r, "PAYLOAD_TOO_LARGE", 413)
        self.assertNotIn("details", body)
        self.assertEqual((self.message_rows(sid), self.llm.requests), (0, []))

    def test_413_dung_truoc_xac_thuc(self):  # trần body → CSRF → xác thực: rẻ nhất đứng trước
        sid = self.new_session()
        r = self.client.post(f"/api/v1/chat-sessions/{sid}/turns", content=b"x" * (LIMIT + 1), headers={"Content-Type": "application/json"})
        self.assert_envelope(r, "PAYLOAD_TOO_LARGE", 413)

    def test_stream_chunked_vuot_tran_cung_bi_chan(self):
        sid = self.new_session()

        def gen():
            for _ in range(10):
                yield b"x" * (LIMIT // 4)

        self.assert_envelope(self.raw(sid, gen()), "PAYLOAD_TOO_LARGE", 413)
        self.assertEqual(self.message_rows(sid), 0)

    def test_413_khong_lo_noi_dung_da_gui(self):
        sid = self.new_session()
        secret = "NOI_DUNG_KHONG_DUOC_LOT_RA_7c1e"
        r = self.raw(sid, ('{"text":"' + secret * 4000 + '"}').encode())
        self.assert_envelope(r, "PAYLOAD_TOO_LARGE", 413)
        self.assertNotIn(secret, r.text)
        self.assertNotIn(secret, self.out.getvalue())

    def test_nfd_1500_chu_co_dau_qua_2000_code_point_tho_van_duoc_nhan_va_luu_nfc(self):
        sid = self.new_session()
        self.llm.set("classify_intent", p1("OUT_OF_SCOPE"))
        text = E_NFD * 1500
        self.assertGreater(len(text), wv.CHAT_MESSAGE_MAX_CHARS)  # 4500 code point thô
        self.assertLessEqual(len(unicodedata.normalize("NFC", text)), wv.CHAT_MESSAGE_MAX_CHARS)  # 1500 sau NFC
        r = self.turn(sid, text)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([e for e, _ in parse_sse(r.text)][-1], "turn.reply")
        with self.db.connect("bo19_migrator") as c:
            stored = c.execute("select body from chat_message where chat_session_id = %s and author = 'EMPLOYEE'", (sid,)).fetchone()[0]
        self.assertEqual(stored, E_NFC * 1500)

    def test_dung_2000_sau_nfc_qua_2001_sau_nfc_bi_tu_choi_dung_khi_nhap_nfd(self):
        sid = self.new_session()
        self.llm.set("classify_intent", p1("OUT_OF_SCOPE"))
        self.assertEqual(self.turn(sid, E_NFD * wv.CHAT_MESSAGE_MAX_CHARS).status_code, 200)  # 6000 code point thô, đúng 2000 sau NFC
        before = self.message_rows(sid)  # cùng nhân viên → cùng phiên đang mở
        r = self.turn(sid, E_NFD * (wv.CHAT_MESSAGE_MAX_CHARS + 1))
        body = self.assert_envelope(r, "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"]["fields"], [{"field": "text", "code": "TOO_LONG"}])
        self.assertEqual(self.message_rows(sid), before)  # bị từ chối trước khi ghi

    def test_2001_nfc_thuan_cung_bi_tu_choi(self):
        sid = self.new_session()
        self.assert_envelope(self.turn(sid, E_NFC * (wv.CHAT_MESSAGE_MAX_CHARS + 1)), "VALIDATION_FAILED", 422)

    def test_than_hop_le_lon_nhat_ma_hoa_het_thanh_u_xxxx_van_qua_tran(self):
        sid = self.new_session()
        self.llm.set("classify_intent", p1("OUT_OF_SCOPE"))
        body = escaped_body(E_NFD * wv.CHAT_MESSAGE_MAX_CHARS)  # 6000 code point × 6 byte = 36 000 byte + khung
        self.assertEqual(len(body), 6000 * 6 + len('{"text":""}'))
        self.assertLess(len(body), LIMIT)
        r = self.raw(sid, body)
        self.assertEqual(r.status_code, 200, r.text[:300])

    def test_id_hong_voi_body_lon_van_la_413_khong_doc_body(self):
        r = self.client.post("/api/v1/chat-sessions/khong-phai-uuid/turns", content=b"x" * (LIMIT + 1), headers={**CSRF, **self.headers, "Content-Type": "application/json"})
        self.assert_envelope(r, "PAYLOAD_TOO_LARGE", 413)

    def test_text_rong_hoac_toan_khoang_trang_la_422_blank_khong_ghi_tin(self):  # `min_length` của API và `MessageInvalid` của tool cho cùng một mã: hai lớp, một kết quả
        sid = self.new_session()
        for text in ("", "   "):
            body = self.assert_envelope(self.turn(sid, text), "VALIDATION_FAILED", 422)
            self.assertEqual(body["details"]["fields"], [{"field": "text", "code": "BLANK"}])
        self.assertEqual(self.message_rows(sid), 0)

    def test_tin_binh_thuong_khong_bi_anh_huong(self):
        sid = self.new_session()
        self.llm.set("classify_intent", p1("OUT_OF_SCOPE"))
        self.assertEqual(self.turn(sid, "cho mình hỏi giờ làm việc").status_code, 200)


class KhopHopDong(unittest.TestCase):
    """Giới hạn trong code khớp `openapi.yaml` và `05-api.md` — đổi một nơi mà quên nơi kia thì đỏ."""

    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load((ROOT / "docs" / "design" / "contracts" / "openapi.yaml").read_text(encoding="utf-8"))
        cls.api_md = (ROOT / "docs" / "design" / "05-api.md").read_text(encoding="utf-8")

    def test_openapi_turn_body_max_length_va_mo_ta_nfc(self):
        text = self.spec["components"]["schemas"]["TurnBody"]["properties"]["text"]
        self.assertEqual(text["maxLength"], wv.CHAT_MESSAGE_MAX_CHARS)
        self.assertIn("NFC", text["description"])
        self.assertIn("code point", text["description"])

    def test_openapi_khai_413_cho_turns_va_nhac_dung_tran_byte(self):
        op = self.spec["paths"]["/chat-sessions/{chat_session_id}/turns"]["post"]
        self.assertEqual(op["responses"]["413"], {"$ref": "#/components/responses/PayloadTooLarge"})
        self.assertIn(f"{LIMIT} byte", self.spec["components"]["responses"]["PayloadTooLarge"]["description"])

    def test_05_api_ghi_dung_tran_byte_va_cach_dem_cua_client(self):
        row = next(line for line in self.api_md.splitlines() if line.startswith("| `PAYLOAD_TOO_LARGE`"))
        self.assertRegex(row, rf"\b{LIMIT} byte\b")
        self.assertIn("37 024 byte", self.api_md)
        self.assertIn("normalize('NFC')", self.api_md)  # quy tắc đếm của client
        self.assertIn(".length", self.api_md)

    def test_tran_byte_du_cho_than_hop_le_lon_nhat_theo_moi_cach_ma_hoa(self):
        nfd = E_NFD * wv.CHAT_MESSAGE_MAX_CHARS
        for body in (json.dumps({"text": nfd}).encode("ascii"), json.dumps({"text": nfd}, ensure_ascii=False).encode("utf-8"), escaped_body(nfd), escaped_body(E_NFC * wv.CHAT_MESSAGE_MAX_CHARS)):
            self.assertLess(len(body), LIMIT)
        astral = "😀" * wv.CHAT_MESSAGE_MAX_CHARS  # cặp surrogate: 12 byte mỗi ký tự — nhỏ hơn xấu nhất của NFD
        self.assertLess(len(json.dumps({"text": astral}).encode("ascii")), LIMIT)


if __name__ == "__main__":
    unittest.main()
