"""Token phiên — `bo19.api.auth.token` (ADR-028, mục Cập nhật B3): JWT `HS256`, hai claim `sub` và `exp`, kiểm token ghim thuật toán.

Yêu cầu an ninh của PO (2026-10-05): token `alg=none` và token ký bằng thuật toán khác bị từ chối — `alg` không bao giờ đọc từ header token.
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_session_token -v
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import unittest
import uuid
import warnings

import jwt

from bo19.api.auth import token
from bo19.config import working_values as wv

SECRET = "k" * 64  # đủ cho cả HS512 (64 byte) — để test "thuật toán khác" ký hợp lệ về độ dài khoá, chỉ sai thuật toán
EMPLOYEE = uuid.UUID("11111111-2222-4333-8444-555555555555")


def b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).rstrip(b"=").decode()


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class RoiVaoRa(unittest.TestCase):
    def test_phat_roi_kiem_tra_ra_dung_id(self):
        self.assertEqual(token.verify(SECRET, token.issue(SECRET, EMPLOYEE)), EMPLOYEE)

    def test_noi_dung_dung_hai_claim_sub_va_exp(self):
        claims = jwt.decode(token.issue(SECRET, EMPLOYEE), options={"verify_signature": False})
        self.assertEqual(set(claims), {"sub", "exp"})  # không iat, không permission, không trường nào khác (ADR-013, ADR-028)
        self.assertEqual(claims["sub"], str(EMPLOYEE))

    def test_thuat_toan_trong_header_la_hs256(self):
        self.assertEqual(jwt.get_unverified_header(token.issue(SECRET, EMPLOYEE))["alg"], "HS256")

    def test_han_la_8_gio_tuyet_doi_wv17(self):
        issued = dt.datetime(2026, 10, 5, 8, 0, tzinfo=dt.timezone.utc)
        claims = jwt.decode(token.issue(SECRET, EMPLOYEE, issued_at=issued), options={"verify_signature": False, "verify_exp": False})
        self.assertEqual(claims["exp"], int(issued.timestamp()) + 8 * 3600)
        self.assertEqual(wv.SESSION_TOKEN_TTL_SECONDS, 8 * 3600)

    def test_het_han_bi_tu_choi(self):
        self.assertIsNone(token.verify(SECRET, token.issue(SECRET, EMPLOYEE, issued_at=now() - dt.timedelta(hours=8, seconds=30))))

    def test_sap_het_han_van_dung_duoc(self):
        self.assertEqual(token.verify(SECRET, token.issue(SECRET, EMPLOYEE, issued_at=now() - dt.timedelta(hours=7, minutes=59))), EMPLOYEE)


class GhimThuatToan(unittest.TestCase):
    """Yêu cầu của PO: decode không đọc `alg` từ header token."""

    def payload(self):
        return {"sub": str(EMPLOYEE), "exp": int(now().timestamp()) + 3600}

    def test_alg_none_dung_tay_bi_tu_choi(self):
        for header in ({"alg": "none", "typ": "JWT"}, {"alg": "None", "typ": "JWT"}, {"alg": "NONE", "typ": "JWT"}):
            forged = f"{b64(header)}.{b64(self.payload())}."
            self.assertIsNone(token.verify(SECRET, forged), header)

    def test_alg_none_do_pyjwt_ky_bi_tu_choi(self):
        forged = jwt.encode(self.payload(), key=None, algorithm="none")
        self.assertEqual(jwt.get_unverified_header(forged)["alg"], "none")  # đúng là token alg=none
        self.assertIsNone(token.verify(SECRET, forged))

    def test_alg_none_voi_chu_ky_rong_hoac_chu_ky_rac_bi_tu_choi(self):
        for tail in ("", "AAAA", token.issue(SECRET, EMPLOYEE).split(".")[2]):
            self.assertIsNone(token.verify(SECRET, f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(self.payload())}.{tail}"))

    def test_ky_bang_thuat_toan_khac_voi_dung_secret_bi_tu_choi(self):
        for alg in ("HS384", "HS512"):
            forged = jwt.encode(self.payload(), SECRET, algorithm=alg)  # chữ ký HỢP LỆ với đúng secret — chỉ sai thuật toán
            self.assertEqual(jwt.get_unverified_header(forged)["alg"], alg)
            self.assertIsNone(token.verify(SECRET, forged), alg)
        # đối chứng: cùng secret, đúng thuật toán thì qua — để thấy các ca trên bị từ chối vì thuật toán, không vì lý do khác
        self.assertEqual(token.verify(SECRET, jwt.encode(self.payload(), SECRET, algorithm="HS256")), EMPLOYEE)

    def test_decode_dung_danh_sach_co_dinh_khong_doc_tu_token(self):
        self.assertEqual(token.ALGORITHMS, ["HS256"])


class TokenHong(unittest.TestCase):
    def test_sai_secret(self):
        self.assertIsNone(token.verify("z" * 64, token.issue(SECRET, EMPLOYEE)))

    def test_chu_ky_bi_sua(self):
        h, p, s = token.issue(SECRET, EMPLOYEE).split(".")
        self.assertIsNone(token.verify(SECRET, f"{h}.{p}.{s[:-2]}AA"))

    def test_payload_bi_doi_sang_nguoi_khac(self):
        h, p, s = token.issue(SECRET, EMPLOYEE).split(".")
        other = b64({"sub": str(uuid.uuid4()), "exp": int(now().timestamp()) + 3600})
        self.assertIsNone(token.verify(SECRET, f"{h}.{other}.{s}"))

    def test_thieu_exp_hoac_sub(self):
        self.assertIsNone(token.verify(SECRET, jwt.encode({"sub": str(EMPLOYEE)}, SECRET, algorithm="HS256")))
        self.assertIsNone(token.verify(SECRET, jwt.encode({"exp": int(now().timestamp()) + 3600}, SECRET, algorithm="HS256")))

    def test_sub_khong_phai_uuid(self):
        for sub in ("khong-phai-uuid", "", "123"):
            self.assertIsNone(token.verify(SECRET, jwt.encode({"sub": sub, "exp": int(now().timestamp()) + 3600}, SECRET, algorithm="HS256")), sub)

    def test_chuoi_rac(self):
        for junk in ("", "abc", "a.b", "a.b.c", "....", "\x00", "eyJ" * 100):
            self.assertIsNone(token.verify(SECRET, junk), junk)

    def test_khoa_ngan_hon_32_byte_khong_ky_khong_kiem_duoc(self):  # A-088 — lớp thứ hai sau bước kiểm khởi động #12
        short = "s" * 31
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # nếu chỉ cảnh báo (mặc định của PyJWT) thì test này đỏ: ta đòi từ chối hẳn
            with self.assertRaises(jwt.InvalidKeyError):
                token.issue(short, EMPLOYEE)
            good = token.issue("s" * 32, EMPLOYEE)
            self.assertEqual(token.verify("s" * 32, good), EMPLOYEE)
            self.assertIsNone(token.verify(short, good))

    def test_khoa_rong_khong_dung_duoc(self):
        with self.assertRaises(jwt.PyJWTError):
            token.issue("", EMPLOYEE)
        self.assertIsNone(token.verify("", token.issue(SECRET, EMPLOYEE)))


if __name__ == "__main__":
    unittest.main()
