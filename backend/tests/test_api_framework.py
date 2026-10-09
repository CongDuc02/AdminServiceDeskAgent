"""Khung `api` — luật 404 (O1-8), `ErrorEnvelope`, CSRF, lỗi kiểm body, lỗi không lường trước, trace_id, danh mục mã lỗi khớp `05-api.md`.

Không cần DB: app dựng với router của test, `pool` là một đối tượng giả (framework chưa chạm nó).
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_api_framework -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import io
import json
import logging
import re
import unittest
from pathlib import Path

from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

from bo19.api import errors as api_errors
from bo19.api.app import create_app
from bo19.api.deps.state import AppState
from bo19.observability.log import configure_logging
from bo19.observability.trace import is_trace_id

DESIGN_05 = Path(__file__).resolve().parents[2] / "docs" / "design" / "05-api.md"
SECRET_BODY = "MAT_KHAU_THU_NGHIEM_KHONG_DUOC_LOT_RA"


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    password: str = Field(min_length=1)
    count: int = Field(default=1, ge=1)


def build_router() -> APIRouter:
    r = APIRouter()

    @r.get("/_t/ping")
    def ping() -> dict[str, str]:
        return {"ok": "1"}

    @r.post("/_t/echo")
    def echo(body: Body) -> dict[str, str]:
        return {"ok": "1"}

    @r.delete("/_t/thing")
    def delete() -> dict[str, str]:
        return {"ok": "1"}

    @r.put("/_t/thing")
    def put() -> dict[str, str]:
        return {"ok": "1"}

    @r.patch("/_t/thing")
    def patch() -> dict[str, str]:
        return {"ok": "1"}

    @r.get("/_t/boom")
    def boom() -> None:
        raise RuntimeError("giá trị RES thật: 079123456789")

    @r.get("/_t/coded")
    def coded() -> None:
        e = RuntimeError("x")
        e.code = "TOOL_INTERNAL_CODE"  # type: ignore[attr-defined]
        raise e

    return r


class Base(unittest.TestCase):
    def setUp(self):
        self.out = io.StringIO()
        h = configure_logging(self.out)
        self.addCleanup(logging.getLogger().removeHandler, h)
        self.app = create_app(AppState(pool=object(), session_secret="x" * 40, verifier=object()), routers=[build_router()])  # type: ignore[arg-type]
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.csrf = {"X-BO19-CSRF": "1"}

    def assert_envelope(self, response, error_code: str, status: int):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(set(body) - {"details"}, {"error_code", "message", "trace_id"}, body)
        self.assertEqual(body["error_code"], error_code)
        self.assertTrue(is_trace_id(body["trace_id"]), body["trace_id"])
        self.assertNotIn("detail", body)  # không phải thân mặc định của FastAPI
        self.assertTrue(body["message"].strip())
        return body


class LuatBaMuoiBon404(Base):  # O1-8
    def test_duong_la_thuoc_api_tra_envelope_not_found(self):
        for path in ("/api", "/api/", "/api/khong-co", "/api/v1", "/api/v1/", "/api/v1/khong/co/endpoint", "/api/v2/me"):
            self.assert_envelope(self.client.get(path), "NOT_FOUND", 404)

    def test_post_vao_duong_la_cung_404_khong_phai_403_csrf(self):
        self.assert_envelope(self.client.post("/api/v1/khong-co", json={}), "NOT_FOUND", 404)  # chưa có route → chưa tới phép kiểm CSRF
        self.assert_envelope(self.client.post("/api/v1/khong-co", json={}, headers=self.csrf), "NOT_FOUND", 404)

    def test_phuong_thuc_sai_tren_duong_co_that_cung_la_not_found(self):
        self.assert_envelope(self.client.patch("/api/v1/_t/ping", headers=self.csrf), "NOT_FOUND", 404)
        self.assert_envelope(self.client.post("/api/v1/_t/ping", headers=self.csrf), "NOT_FOUND", 404)

    def test_duong_ngoai_api_khong_bi_luat_nay_chiem(self):
        r = self.client.get("/khong-co-gi")  # phục vụ tĩnh / index.html thuộc bước sau (chưa có bản build client)
        self.assertEqual(r.json(), {"detail": "Not Found"})

    def test_healthz_ngoai_api_van_chay(self):
        r = self.client.get("/healthz")
        self.assertEqual((r.status_code, r.json()), (200, {"status": "ok"}))

    def test_envelope_khong_lo_cau_truc_ben_trong(self):
        text = self.client.get("/api/v1/khong-co").text
        for forbidden in ("detail", "Traceback", "starlette", "fastapi", "routers"):
            self.assertNotIn(forbidden, text)


class Csrf(Base):
    def test_get_khong_can_header(self):
        self.assertEqual(self.client.get("/api/v1/_t/ping").status_code, 200)

    def test_lenh_khac_get_thieu_header_bi_chan(self):
        for method, path in (("post", "/api/v1/_t/echo"), ("delete", "/api/v1/_t/thing"), ("put", "/api/v1/_t/thing"), ("patch", "/api/v1/_t/thing")):
            r = getattr(self.client, method)(path)
            self.assert_envelope(r, "CSRF_HEADER_MISSING", 403)

    def test_header_rong_hoac_chi_khoang_trang_bi_chan(self):
        for value in ("", "   "):
            r = self.client.post("/api/v1/_t/echo", json={"name": "a", "password": "b"}, headers={"X-BO19-CSRF": value})
            self.assert_envelope(r, "CSRF_HEADER_MISSING", 403)

    def test_header_bat_ky_khong_rong_qua(self):
        r = self.client.post("/api/v1/_t/echo", json={"name": "a", "password": "b"}, headers={"X-BO19-CSRF": "bat-ky"})
        self.assertEqual(r.status_code, 200)

    def test_thieu_csrf_duoc_bao_truoc_loi_body(self):
        self.assert_envelope(self.client.post("/api/v1/_t/echo", json={}), "CSRF_HEADER_MISSING", 403)


class KiemBody(Base):
    def post(self, payload):
        return self.client.post("/api/v1/_t/echo", json=payload, headers=self.csrf)

    def test_thieu_truong_la_required(self):
        body = self.assert_envelope(self.post({"name": "a"}), "VALIDATION_FAILED", 422)
        self.assertEqual(body["details"], {"fields": [{"field": "password", "code": "REQUIRED"}]})

    def test_chuoi_rong_la_blank_va_so_ngoai_mien_la_out_of_range(self):
        body = self.assert_envelope(self.post({"name": "", "password": "p", "count": 0}), "VALIDATION_FAILED", 422)
        self.assertEqual(sorted((f["field"], f["code"]) for f in body["details"]["fields"]), [("count", "OUT_OF_RANGE"), ("name", "BLANK")])

    def test_truong_la_not_allowed_va_sai_kieu_invalid_format(self):
        body = self.assert_envelope(self.post({"name": "a", "password": "p", "la": 1, "count": "abc"}), "VALIDATION_FAILED", 422)
        self.assertEqual(sorted((f["field"], f["code"]) for f in body["details"]["fields"]), [("count", "INVALID_FORMAT"), ("la", "NOT_ALLOWED")])

    def test_khong_bao_gio_chep_gia_tri_da_gui(self):
        r = self.post({"name": "", "password": SECRET_BODY, "la": SECRET_BODY, "count": SECRET_BODY})
        self.assertEqual(r.status_code, 422)
        self.assertNotIn(SECRET_BODY, r.text)

    def test_json_hong_la_validation_failed_khong_lo_noi_dung(self):
        r = self.client.post("/api/v1/_t/echo", content=b'{"password": "' + SECRET_BODY.encode(), headers={**self.csrf, "Content-Type": "application/json"})
        self.assert_envelope(r, "VALIDATION_FAILED", 422)
        self.assertNotIn(SECRET_BODY, r.text)


class LoiKhongLuongTruoc(Base):
    def test_500_la_internal_error_co_trace_id_khong_lo_thong_diep(self):
        r = self.client.get("/api/v1/_t/boom")
        self.assert_envelope(r, "INTERNAL_ERROR", 500)
        self.assertNotIn("079123456789", r.text)
        self.assertNotIn("RES", r.text)

    def test_log_chi_co_kieu_loi_khong_co_thong_diep(self):
        self.client.get("/api/v1/_t/boom")
        text = self.out.getvalue()
        self.assertIn("API_UNHANDLED_ERROR", text)
        self.assertIn("RuntimeError", text)
        self.assertNotIn("079123456789", text)

    def test_trace_id_trong_envelope_khop_trace_id_trong_log(self):
        r = self.client.get("/api/v1/_t/boom")
        logged = [json.loads(x) for x in self.out.getvalue().splitlines() if "API_UNHANDLED_ERROR" in x]
        self.assertEqual(len(logged), 1)
        self.assertEqual(logged[0]["trace_id"], r.json()["trace_id"])

    def test_ma_noi_bo_khong_co_anh_xa_thi_internal_error_va_khong_lo_ma(self):
        r = self.client.get("/api/v1/_t/coded")
        self.assert_envelope(r, "INTERNAL_ERROR", 500)
        self.assertNotIn("TOOL_INTERNAL_CODE", r.text)
        self.assertIn("TOOL_INTERNAL_CODE", self.out.getvalue())  # chỉ log kỹ thuật thấy mã thật

    def test_ma_noi_bo_co_anh_xa_thi_ra_ma_cua_danh_muc(self):
        api_errors.INTERNAL_TO_API["TOOL_INTERNAL_CODE"] = "NOT_FOUND"
        self.addCleanup(api_errors.INTERNAL_TO_API.pop, "TOOL_INTERNAL_CODE")
        self.assert_envelope(self.client.get("/api/v1/_t/coded"), "NOT_FOUND", 404)


class TraceId(Base):
    def test_moi_request_mot_trace_id_rieng_hop_le(self):
        ids = {self.client.get("/api/v1/khong-co").json()["trace_id"] for _ in range(5)}
        self.assertEqual(len(ids), 5)
        self.assertTrue(all(is_trace_id(i) for i in ids))


class DanhMucMaLoi(unittest.TestCase):
    def test_khop_bang_o_05_api(self):
        rows = dict(re.findall(r"^\| `([A-Z_]+)` \| (\d{3}) \|", DESIGN_05.read_text(encoding="utf-8"), flags=re.M))
        self.assertGreater(len(rows), 20)  # đã đọc được bảng
        for code, spec in api_errors.CATALOG.items():
            self.assertIn(code, rows, f"{code} không có trong bảng Danh mục error_code của 05-api.md")
            self.assertEqual(spec.http, int(rows[code]), code)

    def test_ma_la_ngoai_danh_muc_bi_tu_choi(self):
        with self.assertRaises(ValueError):
            api_errors.ApiError("KHONG_CO_TRONG_DANH_MUC")

    def test_thong_diep_khong_mang_ten_ben_trong(self):
        for code, spec in api_errors.CATALOG.items():
            for forbidden in ("slot", "node", "prompt", "bảng", "table"):
                self.assertNotIn(forbidden, spec.message.lower(), code)


if __name__ == "__main__":
    unittest.main()
