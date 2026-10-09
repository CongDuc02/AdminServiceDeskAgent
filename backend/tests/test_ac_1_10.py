"""AC-1.10 (12-roadmap.md, Sprint 1): vượt ngưỡng rate limit trong một cửa sổ thì `POST /auth/session` trả `RATE_LIMITED` mà không kiểm mật khẩu;
sai mã nhân viên và sai mật khẩu trả cùng `INVALID_CREDENTIALS`.

Trên PostgreSQL thật đã migrate bằng `migrate_main`, qua ASGI app thật; role `bo19_app` (chỉ có `UPDATE (attempt_count)` trên `rate_limit_window`).
WV-12: cửa sổ 15 phút, 20 lần thử mỗi `scope` `login_ip:{ip}`; bộ đếm tăng ở mọi lần thử, kể cả lần đúng.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_ac_1_10 -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import threading
import time
import unittest
import uuid
from unittest import mock

from fastapi.testclient import TestClient

from bo19.api.app import create_app
from bo19.api.deps.state import AppState
from bo19.config import working_values as wv
from bo19.tool_layer.endpoint_ops.rate_limit import rate_limit_window_increment
from tests import pg_support
from tests.auth_support import CSRF, PASSWORD, SECRET, AuthBase

LIMIT = 20
PATH = "/api/v1/auth/session"


class AC110(AuthBase):
    def rows(self, scope: str) -> list[tuple[int]]:
        with self.db.connect("bo19_migrator") as c:
            return c.execute("select attempt_count from rate_limit_window where scope = %s order by window_start", (scope,)).fetchall()

    def exhaust(self, code: str, password: str = "sai-mat-khau", n: int = LIMIT):
        for i in range(n):
            r = self.login(code, password)
            self.assertEqual((i, r.status_code), (i, 401), r.text)

    def client_from(self, ip: str) -> TestClient:
        return TestClient(self.app, raise_server_exceptions=False, base_url="https://testserver", client=(ip, 50000))

    # --- vế 1: vượt ngưỡng thì RATE_LIMITED mà không kiểm mật khẩu -------------------------------------------------------------------

    def test_lan_thu_21_la_rate_limited_va_khong_kiem_mat_khau(self):
        _, code = self.employee()
        self.exhaust(code)
        with mock.patch.object(self.verifier, "_argon_verify", wraps=self.verifier._argon_verify) as verify, \
                mock.patch("bo19.api.routers.auth.find_login_candidate", wraps=None) as credential:
            r = self.login(code, PASSWORD)  # KỂ CẢ khi mật khẩu đúng
        self.assertEqual(r.status_code, 429, r.text)
        body = r.json()
        self.assertEqual(body["error_code"], "RATE_LIMITED")
        self.assertEqual(verify.call_count, 0)  # không kiểm mật khẩu: không một lần verify argon2id
        self.assertEqual(credential.call_count, 0)  # kiểm TRƯỚC khi chạm employee_credential (mục Rate limit của 09-security.md)
        self.assertNotIn("set-cookie", r.headers)

    def test_429_mang_retry_after_trong_cua_so(self):
        _, code = self.employee()
        self.exhaust(code)
        r = self.login(code)
        retry = r.json()["details"]["retry_after_seconds"]
        self.assertTrue(1 <= retry <= wv.LOGIN_RATE_LIMIT_WINDOW_SECONDS, retry)
        self.assertEqual(r.headers["retry-after"], str(retry))
        self.assertEqual(set(r.json()) - {"details"}, {"error_code", "message", "trace_id"})
        self.assertEqual(r.json()["details"], {"retry_after_seconds": retry})  # chỉ số đếm, không giá trị nào khác

    def test_ngung_la_20_lan_thu_moi_cua_so(self):
        self.assertEqual((wv.LOGIN_RATE_LIMIT_MAX_ATTEMPTS, wv.LOGIN_RATE_LIMIT_WINDOW_SECONDS), (20, 15 * 60))  # WV-12
        _, code = self.employee()
        self.exhaust(code, n=LIMIT)  # hai mươi lần đầu: chưa bị chặn
        self.assertEqual(self.login(code).status_code, 429)  # lần thứ 21

    def test_van_bi_chan_o_cac_lan_sau(self):
        _, code = self.employee()
        self.exhaust(code)
        self.assertEqual([self.login(code).status_code for _ in range(5)], [429] * 5)

    def test_bo_dem_tang_o_moi_lan_thu_ke_ca_lan_dung(self):  # WV-12
        eid, code = self.employee()
        for i in range(LIMIT):
            self.assertEqual(self.login(code, PASSWORD).status_code, 204, i)  # hai mươi lần ĐÚNG mật khẩu
        self.assertEqual(self.login(code, PASSWORD).status_code, 429)  # lần 21 bị chặn dù đúng

    def test_lan_that_bai_van_duoc_dem_du_request_ket_thuc_bang_loi(self):
        _, code = self.employee()
        self.login(code, "sai")
        self.login("khong-co-ma-nay", "sai")
        self.assertEqual(self.rows(f"login_ip:{self.ip}"), [(2,)])  # giao dịch đếm đã commit trước khi request thất bại

    # --- vế 2: sai mã và sai mật khẩu cùng INVALID_CREDENTIALS -----------------------------------------------------------------------

    def test_sai_ma_va_sai_mat_khau_cung_invalid_credentials(self):
        _, code = self.employee()
        wrong_code, wrong_password = self.login("khong-co-ma-nay", PASSWORD), self.login(code, "sai-mat-khau")
        self.assertEqual((wrong_code.status_code, wrong_password.status_code), (401, 401))
        strip = lambda r: {k: v for k, v in r.json().items() if k != "trace_id"}  # noqa: E731
        self.assertEqual(strip(wrong_code), strip(wrong_password))
        self.assertEqual(wrong_code.json()["error_code"], "INVALID_CREDENTIALS")

    # --- khoá theo IP, không theo mã nhân viên ---------------------------------------------------------------------------------------

    def test_scope_la_login_ip_va_mot_dong_moi_cua_so(self):
        _, code = self.employee()
        for _ in range(7):
            self.login(code, "sai")
        self.assertEqual(self.rows(f"login_ip:{self.ip}"), [(7,)])  # một dòng, tăng tại chỗ — không bơm dòng
        with self.db.connect("bo19_migrator") as c:
            scopes = {r[0] for r in c.execute("select distinct scope from rate_limit_window where scope like %s", (f"%{code}%",))}
        self.assertEqual(scopes, set())  # không scope nào chứa mã nhân viên

    def test_doi_ma_lien_tuc_tu_cung_mot_ip_khong_thoat_duoc_nguong(self):
        for i in range(LIMIT):
            self.assertEqual(self.login(f"ma-gia-{i}-{uuid.uuid4().hex[:6]}").status_code, 401)
        _, fresh = self.employee()
        self.assertEqual(self.login(fresh, PASSWORD).status_code, 429)  # mã mới tinh, cùng IP — vẫn bị chặn

    def test_ip_khac_van_dang_nhap_duoc_va_ma_nan_nhan_khong_bi_khoa(self):
        _, victim = self.employee()
        self.exhaust(victim)  # kẻ tấn công từ self.ip dò mã của nạn nhân
        self.assertEqual(self.login(victim, PASSWORD).status_code, 429)
        other = self.client_from(pg_support.unique_ip())
        r = other.post(PATH, json={"employee_code": victim, "password": PASSWORD}, headers=CSRF)
        self.assertEqual(r.status_code, 204)  # nạn nhân từ IP của mình đăng nhập bình thường: không có ACCOUNT_LOCKED, không khoá theo mã

    def test_doi_x_forwarded_for_khong_ne_duoc_nguong(self):  # A-062, cổng 2.7: mặc định không tin header
        _, code = self.employee()
        for i in range(LIMIT):
            self.assertEqual(self.login(code, "sai", **{"X-Forwarded-For": f"10.{i}.0.1"}).status_code, 401)
        self.assertEqual(self.login(code, PASSWORD, **{"X-Forwarded-For": "10.250.0.1"}).status_code, 429)

    # --- những gì không đếm ---------------------------------------------------------------------------------------------------------

    def test_thieu_csrf_va_body_hong_khong_dem(self):
        for _ in range(LIMIT + 5):
            self.client.post(PATH, json={"employee_code": "a", "password": "b"})  # 403: thiếu header
            self.client.post(PATH, json={"employee_code": "a"}, headers=CSRF)  # 422
        self.assertEqual(self.rows(f"login_ip:{self.ip}"), [])
        _, code = self.employee()
        self.assertEqual(self.login(code).status_code, 204)

    def test_khong_sinh_audit_event(self):  # A-055: sổ sách kỹ thuật
        with self.db.connect("bo19_migrator") as c:
            before = c.execute("select count(*) from audit_event").fetchone()[0]
        _, code = self.employee()
        self.exhaust(code, n=5)
        self.login(code)
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select count(*) from audit_event").fetchone()[0], before)

    def test_verify_khong_giu_connection_cua_pool(self):
        """Verify chạy ngoài `with pool.acquire()`: pool một connection vẫn phục vụ được nhiều đăng nhập chạy đồng thời."""
        pool = type(self.pool)(self.db.dsn("bo19_app"), application_name="bo19-test-one", min_size=1, max_size=1, acquire_timeout_s=3)
        pool.open()
        self.addCleanup(pool.close)
        slow = mock.patch.object(self.verifier, "_argon_verify", side_effect=lambda h, p: (time.sleep(0.4), False)[1])
        app = create_app(AppState(pool=pool, session_secret=SECRET, verifier=self.verifier))
        results: list[int] = []

        def attempt(i: int) -> None:
            c = TestClient(app, raise_server_exceptions=False, base_url="https://testserver", client=(pg_support.unique_ip(), 1))
            results.append(c.post(PATH, json={"employee_code": f"x{i}", "password": "p"}, headers=CSRF).status_code)

        with slow:
            threads = [threading.Thread(target=attempt, args=(i,)) for i in range(4)]
            t0 = time.monotonic()
            [t.start() for t in threads]
            [t.join(10) for t in threads]
            elapsed = time.monotonic() - t0
        self.assertEqual(results, [401] * 4)  # không ai hết hạn mượn connection
        self.assertLess(elapsed, 1.4)  # bốn lần verify 0.4 s chạy song song, không xếp hàng sau một connection


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class ThaoTacTangBoDem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.get_db()

    def test_tang_dan_va_tra_thoi_gian_con_lai(self):
        scope = f"t:{uuid.uuid4()}"
        with self.db.connect("bo19_app") as c:
            got = [rate_limit_window_increment(c, scope, window_seconds=900) for _ in range(3)]
        self.assertEqual([g.attempt_count for g in got], [1, 2, 3])
        self.assertTrue(all(1 <= g.retry_after_seconds <= 900 for g in got))

    def test_scope_khac_dem_rieng(self):
        a, b = f"t:{uuid.uuid4()}", f"t:{uuid.uuid4()}"
        with self.db.connect("bo19_app") as c:
            rate_limit_window_increment(c, a, window_seconds=900)
            rate_limit_window_increment(c, a, window_seconds=900)
            self.assertEqual(rate_limit_window_increment(c, b, window_seconds=900).attempt_count, 1)

    def test_cua_so_moi_dem_lai_tu_mot(self):
        scope = f"t:{uuid.uuid4()}"
        with self.db.connect("bo19_app") as c:
            first = rate_limit_window_increment(c, scope, window_seconds=1)
            seen_reset = False
            for _ in range(40):  # cửa sổ 1 giây: sang cửa sổ kế tiếp thì bộ đếm về 1
                time.sleep(0.1)
                if rate_limit_window_increment(c, scope, window_seconds=1).attempt_count == 1:
                    seen_reset = True
                    break
        self.assertEqual(first.attempt_count, 1)
        self.assertTrue(seen_reset)
        with self.db.connect("bo19_migrator") as c:
            self.assertGreaterEqual(c.execute("select count(*) from rate_limit_window where scope = %s", (scope,)).fetchone()[0], 2)  # mỗi cửa sổ một dòng

    def test_dong_thoi_khong_mat_lan_dem_nao(self):
        scope, n = f"t:{uuid.uuid4()}", 24
        counts: list[int] = []
        lock = threading.Lock()

        def hit() -> None:
            with self.db.connect("bo19_app") as c:
                got = rate_limit_window_increment(c, scope, window_seconds=3600).attempt_count
            with lock:
                counts.append(got)

        threads = [threading.Thread(target=hit) for _ in range(n)]
        [t.start() for t in threads]
        [t.join(15) for t in threads]
        self.assertEqual(sorted(counts), list(range(1, n + 1)))  # mỗi request một số riêng, không trùng, không thiếu

    def test_bo19_app_chi_sua_duoc_attempt_count(self):  # 0005: UPDATE (attempt_count) — thao tác không đòi quyền nào rộng hơn
        scope = f"t:{uuid.uuid4()}"
        with self.db.connect("bo19_app") as c:
            rate_limit_window_increment(c, scope, window_seconds=900)
            from psycopg import errors
            with self.assertRaises(errors.InsufficientPrivilege):
                c.execute("update rate_limit_window set scope = 'x' where scope = %s", (scope,))


if __name__ == "__main__":
    unittest.main()
