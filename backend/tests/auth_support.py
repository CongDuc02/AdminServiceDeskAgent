"""Nền chung cho test endpoint xác thực (B3): PostgreSQL thật đã migrate, pool, hasher tham số rẻ, app và client với IP riêng cho mỗi test.

Không có test nào ở đây. Mỗi test dùng một IP riêng (`pg_support.unique_ip`) để các `scope` rate limit không đè lên nhau trên DB dùng chung.
"""
from __future__ import annotations

import io
import logging
import unittest
import uuid

from fastapi.testclient import TestClient

from bo19.api.app import create_app
from bo19.api.auth import token
from bo19.api.auth.hasher import PasswordVerifier
from bo19.api.deps.state import AppState
from bo19.observability.log import configure_logging
from bo19.observability.trace import is_trace_id
from bo19.persistence.pool import Pool
from tests import pg_support

SECRET = "b3-test-" + "s" * 40  # ≥ 32 byte
PASSWORD = "Mật-khẩu-GIẢ-của-test-1"
CSRF = {"X-BO19-CSRF": "1"}


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class AuthBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.get_db()
        cls.verifier = PasswordVerifier(time_cost=1, memory_cost_kib=8, parallelism=1)
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-auth", min_size=1, max_size=5)
        cls.pool.open()

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()

    def setUp(self):
        self.out = io.StringIO()
        h = configure_logging(self.out)
        self.addCleanup(logging.getLogger().removeHandler, h)
        self.ip = pg_support.unique_ip()
        self.app = create_app(AppState(pool=self.pool, session_secret=SECRET, verifier=self.verifier))
        self.client = TestClient(self.app, raise_server_exceptions=False, base_url="https://testserver", client=(self.ip, 50000))

    # --- tiện ích --------------------------------------------------------------------------------------------------------------

    def employee(self, **kw):
        kw.setdefault("roles", ("EMPLOYEE",))
        kw.setdefault("password_hash", self.verifier.hash(PASSWORD))
        return self.db.make_employee(**kw)

    def login(self, code: str, password: str = PASSWORD, **headers):
        return self.client.post("/api/v1/auth/session", json={"employee_code": code, "password": password}, headers={**CSRF, **headers})

    def session_cookie(self, response) -> str:
        cookie = response.headers["set-cookie"].split(";")[0]
        self.assertTrue(cookie.startswith("bo19_session="))
        return cookie

    def as_user(self, employee_id: uuid.UUID, **issue_kw) -> dict[str, str]:
        return {"Cookie": f"bo19_session={token.issue(SECRET, employee_id, **issue_kw)}"}

    def get_me(self, headers: dict[str, str] | None = None):
        return self.client.get("/api/v1/me", headers=headers or {})

    def assert_envelope(self, r, error_code: str, status: int):
        self.assertEqual(r.status_code, status, r.text)
        body = r.json()
        self.assertEqual(body["error_code"], error_code)
        self.assertTrue(is_trace_id(body["trace_id"]))
        self.assertEqual(set(body) - {"details"}, {"error_code", "message", "trace_id"})
        return body
