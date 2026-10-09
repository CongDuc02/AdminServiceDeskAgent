"""O1-10 (PO duyệt 2026-10-09): giới hạn đầu vào của `POST /auth/session` — `maxLength` của hai trường và trần body 4096 byte → `PAYLOAD_TOO_LARGE`.

Hai tầng: (1) `BodyLimitMiddleware` dưới dạng ASGI thuần, không DB — dòng chảy byte, stream không có `Content-Length`, `Content-Length` nói dối; (2) qua app thật trên PostgreSQL thật —
không verify argon2, không tăng bộ đếm rate limit, `TOO_LONG` ở 422, và khớp với `openapi.yaml` và `05-api.md`.

Cần BO19_TEST_PG_SUPERUSER_DSN cho tầng 2. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_login_limits -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import asyncio
import json
import re
import unittest
from pathlib import Path
from unittest import mock

import yaml

from bo19.api.auth.hasher import PasswordVerifier
from bo19.api.body_limit import BodyLimitMiddleware
from bo19.config import working_values as wv
from tests.auth_support import CSRF, PASSWORD, AuthBase

LIMIT = wv.LOGIN_BODY_MAX_BYTES
PATH = "/api/v1/auth/session"
ROOT = Path(__file__).resolve().parents[2]


class FakeApp:
    """Ứng dụng giả: đọc hết body mà middleware giao, ghi lại, trả 204."""

    def __init__(self) -> None:
        self.bodies: list[bytes] = []
        self.messages: list[list[dict]] = []

    async def __call__(self, scope, receive, send) -> None:
        body, seen = b"", []
        while True:
            m = await receive()
            seen.append(m)
            body += m.get("body", b"")
            if not m.get("more_body", False):
                break
        self.bodies.append(body)
        self.messages.append(seen)
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


def run(mw, *, method="POST", path=PATH, headers=(), chunks=(b"{}",), disconnect_after=True, scope_type="http"):
    """Chạy middleware một lần. Trả (trạng thái, thân response, số message `receive` đã bị lấy)."""
    sent: list[dict] = []
    queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]
    taken = 0

    async def receive():
        nonlocal taken
        taken += 1
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(m):
        sent.append(m)

    scope = {"type": scope_type, "method": method, "path": path, "headers": [(k.lower().encode(), v.encode()) for k, v in headers], "query_string": b"", "http_version": "1.1"}
    asyncio.run(mw(scope, receive, send))
    status = next((m["status"] for m in sent if m["type"] == "http.response.start"), None)
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body, taken


class MiddlewareASGI(unittest.TestCase):
    def setUp(self):
        self.app = FakeApp()
        self.mw = BodyLimitMiddleware(self.app, {("POST", PATH): LIMIT})

    def assert_413(self, status, body):
        self.assertEqual(status, 413)
        data = json.loads(body)
        self.assertEqual(data["error_code"], "PAYLOAD_TOO_LARGE")
        self.assertEqual(self.app.bodies, [])  # ứng dụng không bao giờ thấy request

    def test_dung_bang_tran_qua_va_duoc_phat_lai_nguyen_van(self):
        data = b"x" * LIMIT
        status, _, _ = run(self.mw, chunks=(data,))
        self.assertEqual((status, self.app.bodies), (204, [data]))

    def test_nhieu_manh_cong_lai_bang_tran_van_qua(self):
        parts = (b"a" * 1000, b"b" * 1000, b"c" * 1000, b"d" * (LIMIT - 3000))
        status, _, _ = run(self.mw, chunks=parts)
        self.assertEqual((status, self.app.bodies), (204, [b"".join(parts)]))
        self.assertEqual(len(self.app.messages[0]), 1)  # phát lại thành MỘT message trọn vẹn

    def test_vuot_tran_mot_byte_la_413(self):
        status, body, _ = run(self.mw, chunks=(b"x" * (LIMIT + 1),))
        self.assert_413(status, body)

    def test_stream_khong_content_length_dung_doc_khi_da_vuot_tran(self):
        chunks = tuple(b"x" * 1000 for _ in range(10))  # 10.000 byte, không header Content-Length (chunked)
        status, body, taken = run(self.mw, chunks=chunks)
        self.assert_413(status, body)
        self.assertEqual(taken, 5)  # vượt 4096 ở manh thứ năm → dừng, không đọc 5 mảnh còn lại

    def test_content_length_lon_hon_tran_tu_choi_som_khong_doc_byte_nao(self):
        status, body, taken = run(self.mw, headers=[("Content-Length", str(LIMIT + 1))], chunks=(b"{}",))
        self.assert_413(status, body)
        self.assertEqual(taken, 0)

    def test_content_length_noi_doi_nho_hon_thuc_te_van_bi_chan(self):  # không tin header: đếm byte thực nhận
        status, body, _ = run(self.mw, headers=[("Content-Length", "10")], chunks=(b"x" * 6000,))
        self.assert_413(status, body)

    def test_content_length_noi_doi_lon_hon_thuc_te_thi_chan_theo_header(self):
        status, body, taken = run(self.mw, headers=[("Content-Length", "999999")], chunks=(b"{}",))
        self.assert_413(status, body)
        self.assertEqual(taken, 0)

    def test_content_length_hong_bi_bo_qua_va_dem_byte_thuc(self):
        for bad in ("abc", "-1", "1e9", "", "9" * 40, " 5"):
            self.app.bodies.clear()
            status, _, _ = run(self.mw, headers=[("Content-Length", bad)], chunks=(b"{}",))
            self.assertEqual((status, self.app.bodies), (204, [b"{}"]), repr(bad))

    def test_nhieu_header_content_length_lay_gia_tri_lon_nhat(self):
        status, body, _ = run(self.mw, headers=[("Content-Length", "5"), ("Content-Length", str(LIMIT + 1))], chunks=(b"{}",))
        self.assert_413(status, body)

    def test_duong_khac_phuong_thuc_khac_va_scope_khac_di_thang(self):
        big = b"x" * (LIMIT * 4)
        for kwargs in ({"method": "GET"}, {"path": "/api/v1/me"}, {"path": PATH + "/"}):
            self.app.bodies.clear()
            status, _, _ = run(self.mw, chunks=(big,), **kwargs)
            self.assertEqual((status, self.app.bodies), (204, [big]), kwargs)

    def test_scope_khong_phai_http_di_thang(self):
        seen = []

        async def app(scope, receive, send):
            seen.append(scope["type"])

        run(BodyLimitMiddleware(app, {("POST", PATH): LIMIT}), scope_type="lifespan")
        self.assertEqual(seen, ["lifespan"])

    def test_client_bo_di_truoc_khi_gui_xong_khong_goi_ung_dung(self):
        status, _, _ = run(self.mw, chunks=())  # receive trả http.disconnect ngay
        self.assertEqual((status, self.app.bodies), (None, []))

    def test_than_413_chi_co_ma_va_khong_chua_noi_dung_da_gui(self):
        secret = "MAT_KHAU_KHONG_DUOC_LOT_RA_9f3a"
        status, body, _ = run(self.mw, chunks=(secret.encode() * 600,))
        self.assert_413(status, body)
        self.assertNotIn(secret, body.decode())
        self.assertEqual(set(json.loads(body)), {"error_code", "message", "trace_id"})


class DangNhapQuaApp(AuthBase):
    def counter(self) -> list[int]:
        with self.db.connect("bo19_migrator") as c:
            return [r[0] for r in c.execute("select attempt_count from rate_limit_window where scope = %s order by window_start", (f"login_ip:{self.ip}",)).fetchall()]

    def verify_calls(self):
        return mock.patch.object(PasswordVerifier, "verify", autospec=True, side_effect=PasswordVerifier.verify)

    def test_body_qua_tran_la_413_khong_verify_khong_tang_bo_dem(self):
        _, code = self.employee()
        with self.verify_calls() as verify:
            r = self.client.post(PATH, content=json.dumps({"employee_code": code, "password": "x" * (LIMIT + 1)}), headers={**CSRF, "Content-Type": "application/json"})
        body = self.assert_envelope(r, "PAYLOAD_TOO_LARGE", 413)
        self.assertNotIn("details", body)
        self.assertEqual((verify.call_count, self.counter()), (0, []))  # chưa chạm credential, chưa đếm
        self.assertNotIn("set-cookie", r.headers)

    def test_413_khong_dem_nhung_lan_hop_le_ngay_sau_van_dem(self):
        _, code = self.employee()
        self.client.post(PATH, content=b"x" * (LIMIT + 1), headers={**CSRF, "Content-Type": "application/json"})
        self.assertEqual(self.counter(), [])
        self.assertEqual(self.login(code).status_code, 204)
        self.assertEqual(self.counter(), [1])

    def test_stream_chunked_khong_content_length_cung_bi_chan(self):
        def gen():
            for _ in range(8):
                yield b"x" * 1000

        r = self.client.post(PATH, content=gen(), headers={**CSRF, "Content-Type": "application/json"})
        self.assert_envelope(r, "PAYLOAD_TOO_LARGE", 413)
        self.assertEqual(self.counter(), [])

    def test_content_length_noi_doi_qua_app_that(self):
        r = self.client.post(PATH, content=b"x" * 6000, headers={**CSRF, "Content-Type": "application/json", "Content-Length": "10"})
        self.assert_envelope(r, "PAYLOAD_TOO_LARGE", 413)

    def test_kiem_than_truoc_csrf(self):  # thứ tự: trần body → CSRF → rate limit → verify; rẻ nhất đứng trước
        r = self.client.post(PATH, content=b"x" * (LIMIT + 1), headers={"Content-Type": "application/json"})
        self.assert_envelope(r, "PAYLOAD_TOO_LARGE", 413)

    def test_413_mang_trace_id_va_khong_lo_mat_khau(self):
        pw = "MAT_KHAU_KHONG_DUOC_LOT_RA_ANH_SANG_" + "z" * LIMIT
        r = self.login("a", pw)
        self.assert_envelope(r, "PAYLOAD_TOO_LARGE", 413)
        self.assertNotIn(pw[:40], r.text)
        self.assertNotIn(pw[:40], self.out.getvalue())

    def test_employee_code_65_ky_tu_la_422_too_long(self):
        r = self.login("a" * (wv.LOGIN_EMPLOYEE_CODE_MAX_LENGTH + 1))
        body = self.assert_envelope(r, "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"]["fields"], [{"field": "employee_code", "code": "TOO_LONG"}])

    def test_mat_khau_129_ky_tu_la_422_too_long_va_khong_toi_argon2(self):
        _, code = self.employee()
        with self.verify_calls() as verify:
            r = self.login(code, "p" * (wv.LOGIN_PASSWORD_MAX_LENGTH + 1))
        body = self.assert_envelope(r, "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"]["fields"], [{"field": "password", "code": "TOO_LONG"}])
        self.assertEqual((verify.call_count, self.counter()), (0, []))  # 422 không chạm DB, không verify
        self.assertNotIn("p" * 20, r.text)

    def test_dung_bang_gioi_han_thi_qua_validation(self):  # biên: 64 và 128 ký tự đi tiếp tới kiểm credential
        with self.verify_calls() as verify:
            r = self.login("a" * wv.LOGIN_EMPLOYEE_CODE_MAX_LENGTH, "p" * wv.LOGIN_PASSWORD_MAX_LENGTH)
        self.assert_envelope(r, "INVALID_CREDENTIALS", 401)
        self.assertEqual(verify.call_count, 1)

    def test_trong_ky_tu_co_dau_dem_theo_ky_tu_khong_theo_byte(self):  # maxLength của OpenAPI đếm ký tự; trần body mới đếm byte
        r = self.login("ế" * wv.LOGIN_EMPLOYEE_CODE_MAX_LENGTH, "ậ" * wv.LOGIN_PASSWORD_MAX_LENGTH)  # 192 + 384 byte — còn xa 4096
        self.assert_envelope(r, "INVALID_CREDENTIALS", 401)

    def test_dang_nhap_binh_thuong_khong_bi_anh_huong(self):
        _, code = self.employee()
        self.assertEqual(self.login(code).status_code, 204)


class KhopHopDong(unittest.TestCase):
    """Giới hạn trong code khớp `openapi.yaml` và `05-api.md` — đổi một nơi mà quên nơi kia thì đỏ."""

    @classmethod
    def setUpClass(cls):
        cls.spec = yaml.safe_load((ROOT / "docs" / "design" / "contracts" / "openapi.yaml").read_text(encoding="utf-8"))

    def test_max_length_khop_openapi(self):
        props = self.spec["components"]["schemas"]["LoginBody"]["properties"]
        self.assertEqual(props["employee_code"]["maxLength"], wv.LOGIN_EMPLOYEE_CODE_MAX_LENGTH)
        self.assertEqual(props["password"]["maxLength"], wv.LOGIN_PASSWORD_MAX_LENGTH)

    def test_openapi_khai_413_cho_dang_nhap_va_nhac_dung_tran_byte(self):
        op = self.spec["paths"]["/auth/session"]["post"]
        self.assertEqual(op["responses"]["413"], {"$ref": "#/components/responses/PayloadTooLarge"})
        self.assertIn(f"{wv.LOGIN_BODY_MAX_BYTES} byte", self.spec["components"]["responses"]["PayloadTooLarge"]["description"])

    def test_05_api_ghi_dung_tran_byte_o_dong_payload_too_large(self):
        text = (ROOT / "docs" / "design" / "05-api.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| `PAYLOAD_TOO_LARGE`"))
        self.assertIn("| 413 |", row)
        self.assertRegex(row, rf"\b{wv.LOGIN_BODY_MAX_BYTES} byte\b")

    def test_tran_body_du_lon_cho_than_hop_le_lon_nhat(self):
        biggest = json.dumps({"employee_code": "ế" * wv.LOGIN_EMPLOYEE_CODE_MAX_LENGTH, "password": "ậ" * wv.LOGIN_PASSWORD_MAX_LENGTH}, ensure_ascii=False).encode("utf-8")
        self.assertLess(len(biggest), wv.LOGIN_BODY_MAX_BYTES)
        escaped = json.dumps({"employee_code": "ế" * wv.LOGIN_EMPLOYEE_CODE_MAX_LENGTH, "password": "ậ" * wv.LOGIN_PASSWORD_MAX_LENGTH}).encode("ascii")  # \uXXXX: 6 byte/ký tự
        self.assertLess(len(escaped), wv.LOGIN_BODY_MAX_BYTES)  # kể cả client mã hoá mọi ký tự thành \uXXXX


if __name__ == "__main__":
    unittest.main()
