"""`POST` và `DELETE /auth/session`, `GET /me` trên PostgreSQL thật đã migrate (kế hoạch B3; mục 2.2 của 05-api.md).

Hasher dựng với tham số rẻ — test tự tạo, không hạ cấu hình của ứng dụng (bước kiểm khởi động #20). Mọi tài khoản là dữ liệu giả của test.
Yêu cầu an ninh của PO: sai mã và sai mật khẩu cùng một lỗi mà cả hai nhánh đều verify; token `alg=none` / thuật toán khác bị từ chối;
`GET /me` đọc lại `is_active` và permission từ DB mỗi request.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_auth_endpoints -v
"""
from __future__ import annotations

import datetime as dt
import unittest
import uuid
from unittest import mock

import jwt
from fastapi.testclient import TestClient

from bo19.api.app import create_app
from bo19.api.auth import token
from bo19.api.deps.state import AppState
from bo19.persistence.pool import Pool
from tests import pg_support
from tests.auth_support import CSRF, PASSWORD, SECRET, AuthBase

class DangNhap(AuthBase):
    def test_thanh_cong_204_khong_than_va_dat_cookie_dung_thuoc_tinh(self):
        _, code = self.employee()
        r = self.login(code)
        self.assertEqual((r.status_code, r.content), (204, b""))
        header = r.headers["set-cookie"]
        attrs = {a.strip().lower() for a in header.split(";")[1:]}
        self.assertIn("httponly", attrs)
        self.assertIn("secure", attrs)
        self.assertIn("samesite=strict", attrs)
        self.assertIn("path=/api", attrs)
        self.assertIn(f"max-age={8 * 3600}", attrs)  # WV-17

    def test_token_trong_cookie_la_cua_dung_nhan_vien_va_het_han_sau_8_gio(self):
        eid, code = self.employee()
        r = self.login(code)
        value = self.session_cookie(r).split("=", 1)[1]
        self.assertEqual(token.verify(SECRET, value), eid)
        exp = jwt.decode(value, options={"verify_signature": False})["exp"]
        self.assertAlmostEqual(exp, dt.datetime.now(dt.timezone.utc).timestamp() + 8 * 3600, delta=30)

    def test_thieu_csrf_la_403(self):
        _, code = self.employee()
        r = self.client.post("/api/v1/auth/session", json={"employee_code": code, "password": PASSWORD})
        self.assert_envelope(r, "CSRF_HEADER_MISSING", 403)
        self.assertNotIn("set-cookie", r.headers)

    def test_kiem_body(self):
        r = self.client.post("/api/v1/auth/session", json={"employee_code": ""}, headers=CSRF)
        body = self.assert_envelope(r, "VALIDATION_FAILED", 422)
        self.assertEqual(sorted((f["field"], f["code"]) for f in body["details"]["fields"]), [("employee_code", "BLANK"), ("password", "REQUIRED")])
        r = self.client.post("/api/v1/auth/session", json={"employee_code": "a", "password": ""}, headers=CSRF)
        self.assertEqual(self.assert_envelope(r, "VALIDATION_FAILED", 422)["details"]["fields"], [{"field": "password", "code": "BLANK"}])

    def test_mat_khau_khong_lo_ra_response_hay_log(self):
        secret_pw = "MAT_KHAU_KHONG_DUOC_LOT_RA_ANH_SANG"
        _, code = self.employee()
        responses = [
            self.login(code, secret_pw),  # sai mật khẩu
            self.login("khong-co-ma-nay", secret_pw),  # sai mã
            self.client.post("/api/v1/auth/session", json={"employee_code": "", "password": secret_pw, "la": secret_pw}, headers=CSRF),  # body sai
        ]
        for r in responses:
            self.assertNotIn(secret_pw, r.text)
        self.assertNotIn(secret_pw, self.out.getvalue())
        self.assertNotIn(SECRET, self.out.getvalue())


class MotMaLoiChoMoiTruongHopSai(AuthBase):
    """INVALID_CREDENTIALS — cùng một mã cho sai mã nhân viên lẫn sai mật khẩu, và không phân biệt được ở thân response."""

    def failure(self, response):
        self.assertNotIn("set-cookie", response.headers)
        body = self.assert_envelope(response, "INVALID_CREDENTIALS", 401)
        return {k: v for k, v in body.items() if k != "trace_id"}

    def test_sai_ma_sai_mat_khau_nguoi_khong_hoat_dong_thieu_credential_deu_giong_het(self):
        _, code = self.employee()
        _, inactive = self.employee(active=False)
        _, no_credential = self.db.make_employee(roles=("EMPLOYEE",))  # có hồ sơ, không có dòng credential
        bodies = [
            self.failure(self.login("khong-co-ma-nay")),  # sai mã
            self.failure(self.login(code, "sai-mat-khau")),  # sai mật khẩu
            self.failure(self.login(inactive)),  # đúng mật khẩu nhưng đã bị tắt
            self.failure(self.login(no_credential)),  # thiếu credential
            self.failure(self.login(code.upper() if code != code.upper() else code.lower(), PASSWORD)),  # mã khác hoa/thường là mã khác
        ]
        self.assertTrue(all(b == bodies[0] for b in bodies), bodies)
        self.assertNotIn("details", bodies[0])

    def test_hai_nhanh_deu_chay_mot_lan_verify(self):
        eid, code = self.employee()
        _, inactive = self.employee(active=False)
        with mock.patch.object(self.verifier, "_argon_verify", wraps=self.verifier._argon_verify) as spy:
            self.login("khong-co-ma-nay")
            unknown_calls = list(spy.call_args_list)
            spy.reset_mock()
            self.login(code, "sai-mat-khau")
            wrong_calls = list(spy.call_args_list)
            spy.reset_mock()
            self.login(inactive)
            inactive_calls = list(spy.call_args_list)
        self.assertEqual((len(unknown_calls), len(wrong_calls), len(inactive_calls)), (1, 1, 1))
        self.assertEqual(unknown_calls[0].args[0], self.verifier._dummy_hash)  # mã không tồn tại → verify với hash giả
        self.assertTrue(wrong_calls[0].args[0].startswith("$argon2id$"))
        self.assertNotEqual(wrong_calls[0].args[0], self.verifier._dummy_hash)  # nhánh thật so với hash của chính nhân viên
        self.assertEqual(inactive_calls[0].args[0], self.verifier._dummy_hash)  # nhân viên bị tắt: không so mật khẩu thật

    def test_thanh_cong_cung_chi_mot_lan_verify(self):
        _, code = self.employee()
        with mock.patch.object(self.verifier, "_argon_verify", wraps=self.verifier._argon_verify) as spy:
            self.assertEqual(self.login(code).status_code, 204)
        self.assertEqual(spy.call_count, 1)


class Me(AuthBase):
    def test_hinh_dang_va_permission_cua_vai_tro(self):
        eid, code = self.employee(roles=("EMPLOYEE",))
        body = self.get_me(self.as_user(eid)).json()
        self.assertEqual(set(body), {"employee", "permissions", "operating_mode"})
        self.assertEqual(body["employee"], {"id": str(eid), "employee_code": code, "full_name": f"NGƯỜI GIẢ {code}", "department_code": "PB-GIA",
                                            "department_name": "Phòng giả", "job_title": "Chức danh giả"})
        self.assertEqual(body["permissions"], sorted(["request.create", "request.read_own", "request.supply_info", "request.cancel_own", "audit.read_own"]))
        self.assertEqual(body["operating_mode"], "NON_PRODUCTION")

    def test_khong_lo_hash_hay_truong_nhay_cam(self):
        eid, _ = self.employee()
        text = self.get_me(self.as_user(eid)).text
        for forbidden in ("argon2", "password", "national_id", "date_of_birth", "contract_type", "is_active"):
            self.assertNotIn(forbidden, text)

    def test_quyen_cap_le_cong_voi_vai_tro_va_quyen_da_thu_hoi_khong_tinh(self):
        eid, _ = self.employee(roles=("ADMIN_OFFICER",), grants=("document.sign",), revoked_grants=("document.revoke_confirm",))
        permissions = self.get_me(self.as_user(eid)).json()["permissions"]
        self.assertIn("document.sign", permissions)  # cấp lẻ
        self.assertIn("document.issue", permissions)  # gói ADMIN_OFFICER
        self.assertNotIn("document.revoke_confirm", permissions)  # đã thu hồi
        self.assertNotIn("operating_mode.change", permissions)  # lớp 1 của ADR-023: không cấp cho ai
        self.assertEqual(permissions, sorted(set(permissions)))

    def test_khong_trung_lap_khi_cung_quyen_tu_vai_tro_va_cap_le(self):
        eid, _ = self.employee(roles=("ADMIN_OFFICER",), grants=("document.issue",))
        self.assertEqual(self.get_me(self.as_user(eid)).json()["permissions"].count("document.issue"), 1)

    def test_nhan_vien_khong_co_vai_tro_nao_khong_co_permission(self):
        eid, _ = self.employee(roles=())
        self.assertEqual(self.get_me(self.as_user(eid)).json()["permissions"], [])

    def test_dang_nhap_roi_me_bang_cookie_tu_phan_hoi(self):
        eid, code = self.employee()
        cookie = self.session_cookie(self.login(code))
        r = self.get_me({"Cookie": cookie})
        self.assertEqual((r.status_code, r.json()["employee"]["id"]), (200, str(eid)))


class MeDocLaiDbMoiRequest(AuthBase):
    """ADR-013: token chỉ mang `sub` và `exp`; `is_active` và permission đọc lại từ DB ở mỗi request."""

    def test_tat_is_active_thi_request_ke_tiep_la_unauthenticated(self):
        eid, code = self.employee()
        headers = {"Cookie": self.session_cookie(self.login(code))}
        self.assertEqual(self.get_me(headers).status_code, 200)
        self.db.set_active(eid, False)
        self.assert_envelope(self.get_me(headers), "UNAUTHENTICATED", 401)
        self.assert_envelope(self.client.delete("/api/v1/auth/session", headers={**headers, **CSRF}), "UNAUTHENTICATED", 401)
        self.db.set_active(eid, True)  # token không bị thu hồi: bật lại thì dùng lại được — không có cache nào
        self.assertEqual(self.get_me(headers).status_code, 200)

    def test_cap_va_thu_hoi_quyen_co_hieu_luc_o_request_ke_tiep(self):
        eid, _ = self.employee(roles=("EMPLOYEE",))
        headers = self.as_user(eid)
        self.assertNotIn("document.sign", self.get_me(headers).json()["permissions"])
        with self.db.connect("bo19_migrator") as c:
            gid = uuid.uuid4()
            c.execute("insert into employee_permission_grant (id, employee_id, permission_code) values (%s, %s, 'document.sign')", (gid, eid))
        self.assertIn("document.sign", self.get_me(headers).json()["permissions"])
        with self.db.connect("bo19_migrator") as c:
            c.execute("update employee_permission_grant set revoked_at = now() where id = %s", (gid,))
        self.assertNotIn("document.sign", self.get_me(headers).json()["permissions"])
        with self.db.connect("bo19_migrator") as c:
            c.execute("delete from employee_role where employee_id = %s", (eid,))
        self.assertEqual(self.get_me(headers).json()["permissions"], [])


class TokenKhongHopLe(AuthBase):
    def test_khong_cookie_cookie_rac_het_han_nguoi_la_sai_secret_deu_unauthenticated(self):
        eid, _ = self.employee()
        cases = {
            "không cookie": {},
            "cookie rỗng": {"Cookie": "bo19_session="},
            "cookie rác": {"Cookie": "bo19_session=abc.def.ghi"},
            "cookie tên khác": {"Cookie": "session=" + token.issue(SECRET, eid)},
            "hết hạn": self.as_user(eid, issued_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=9)),
            "nhân viên không tồn tại": self.as_user(uuid.uuid4()),
            "sai secret": {"Cookie": "bo19_session=" + token.issue("sai-" * 16, eid)},
        }
        for name, headers in cases.items():
            body = self.assert_envelope(self.get_me(headers), "UNAUTHENTICATED", 401)
            self.assertNotIn("details", body, name)

    def payload(self, eid: uuid.UUID) -> dict:
        return {"sub": str(eid), "exp": int(dt.datetime.now(dt.timezone.utc).timestamp()) + 3600}

    def test_token_alg_none_cua_nhan_vien_that_bi_tu_choi_o_endpoint(self):
        eid, _ = self.employee()
        forged = jwt.encode(self.payload(eid), key=None, algorithm="none")
        self.assert_envelope(self.get_me({"Cookie": f"bo19_session={forged}"}), "UNAUTHENTICATED", 401)

    def test_token_ky_bang_thuat_toan_khac_voi_dung_secret_bi_tu_choi_o_endpoint(self):
        eid, _ = self.employee()
        secret64 = (SECRET * 2)[:64]
        # AppState là frozen dataclass — dựng app riêng với secret 64 byte để token HS512 hợp lệ về độ dài khoá
        app = create_app(AppState(pool=self.pool, session_secret=secret64, verifier=self.verifier))
        client = TestClient(app, raise_server_exceptions=False, base_url="https://testserver")
        for alg in ("HS384", "HS512"):
            forged = jwt.encode(self.payload(eid), secret64, algorithm=alg)
            r = client.get("/api/v1/me", headers={"Cookie": f"bo19_session={forged}"})
            self.assert_envelope(r, "UNAUTHENTICATED", 401)
        good = jwt.encode(self.payload(eid), secret64, algorithm="HS256")  # đối chứng: đúng thuật toán thì qua
        self.assertEqual(client.get("/api/v1/me", headers={"Cookie": f"bo19_session={good}"}).status_code, 200)


class DangXuat(AuthBase):
    def test_xoa_cookie_dung_path_va_thuoc_tinh(self):
        eid, _ = self.employee()
        r = self.client.delete("/api/v1/auth/session", headers={**self.as_user(eid), **CSRF})
        self.assertEqual((r.status_code, r.content), (204, b""))
        header = r.headers["set-cookie"].lower()
        self.assertIn("bo19_session=", header)
        self.assertIn("max-age=0", header)
        self.assertIn("path=/api", header)
        self.assertIn("httponly", header)
        self.assertIn("secure", header)
        self.assertIn("samesite=strict", header)

    def test_chua_dang_nhap_la_401(self):
        self.assert_envelope(self.client.delete("/api/v1/auth/session", headers=CSRF), "UNAUTHENTICATED", 401)

    def test_thieu_csrf_la_403(self):
        eid, _ = self.employee()
        self.assert_envelope(self.client.delete("/api/v1/auth/session", headers=self.as_user(eid)), "CSRF_HEADER_MISSING", 403)

    def test_token_da_phat_khong_bi_thu_hoi_truoc_han(self):  # rủi ro có chủ — A-048, ADR-013: đăng xuất chỉ xoá cookie ở trình duyệt
        eid, _ = self.employee()
        headers = self.as_user(eid)
        self.client.delete("/api/v1/auth/session", headers={**headers, **CSRF})
        self.assertEqual(self.get_me(headers).status_code, 200)


class LoiHeThong(AuthBase):
    def test_pool_can_la_500_internal_error_khong_lo_gi(self):
        small = Pool(self.db.dsn("bo19_app"), application_name="bo19-test-small", min_size=1, max_size=1, acquire_timeout_s=0.2)
        small.open()
        self.addCleanup(small.close)
        app = create_app(AppState(pool=small, session_secret=SECRET, verifier=self.verifier))
        client = TestClient(app, raise_server_exceptions=False, base_url="https://testserver")
        eid, _ = self.employee()
        with small.acquire():  # giữ connection duy nhất
            r = client.get("/api/v1/me", headers=self.as_user(eid))
        body = self.assert_envelope(r, "INTERNAL_ERROR", 500)
        self.assertNotIn("POOL_EXHAUSTED", r.text)
        self.assertIn("POOL_EXHAUSTED", self.out.getvalue())  # chỉ log kỹ thuật thấy mã thật
        self.assertNotIn("bo19_app", r.text)
        self.assertTrue(body["trace_id"])


if __name__ == "__main__":
    unittest.main()
