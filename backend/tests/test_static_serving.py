"""Phục vụ bản build client và luật 404 phía `api` (B10a; mục 10.4 của 06-structure.md, ADR-013, ADR-018, O1-8). Không cần DB: app dựng với router của test, `pool` giả.

Điều được chứng minh, nói bằng hành vi:
- **bảng bốn dòng của mục 10.4:** endpoint thật → endpoint; đường lạ thuộc `/api` (kể cả `/api`, `/api/`, `/api/v1/…`) → `ErrorEnvelope` `NOT_FOUND` 404, KHÔNG `index.html`; file lạ dưới `/assets` → 404, KHÔNG `index.html`;
  mọi GET lạ còn lại (tuyến của SPA) → `index.html` 200;
- phương thức sai trên đường SPA (POST `/chat`) → không 200 `index.html`; trên `/api` vẫn `NOT_FOUND` của envelope;
- asset đã băm tên cache một năm `immutable`; `index.html` và tệp ở gốc `no-store`; `nosniff`; Content-Type đúng;
- đường dẫn thoát thư mục (`..`, mã hoá `%2e%2e`, đường tuyệt đối, liên kết biểu tượng) KHÔNG đọc được tệp ngoài thư mục build;
- `HEAD` được; `AppState.static_dir = None` (không client) thì `api` không có catch-all.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_static_serving -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi import APIRouter
from fastapi.testclient import TestClient

from bo19.api.app import create_app
from bo19.api.deps.state import AppState
from tests.static_support import CSS, INDEX, JS, make_build


def build_router() -> APIRouter:
    r = APIRouter()

    @r.get("/ping")
    def ping() -> dict[str, str]:
        return {"pong": "ok"}

    return r


def client_for(static_dir: Path | None) -> TestClient:
    app = create_app(AppState(pool=object(), session_secret="x" * 40, verifier=object(), static_dir=static_dir), routers=[build_router()])  # type: ignore[arg-type]
    return TestClient(app, raise_server_exceptions=False, base_url="https://testserver")


class Base(unittest.TestCase):
    def setUp(self):
        self.root = make_build()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.client = client_for(self.root)


class BangBonDong(Base):
    def test_endpoint_that_van_la_endpoint(self):
        r = self.client.get("/api/v1/ping")
        self.assertEqual((r.status_code, r.json()), (200, {"pong": "ok"}))
        self.assertEqual(self.client.get("/healthz").json(), {"status": "ok"})

    def test_duong_la_thuoc_api_la_error_envelope_not_found_khong_phai_index(self):
        for path in ("/api", "/api/", "/api/v1/khong-co", "/api/v1/khong-co/sau/hon", "/api/v2/x", "/api/ping"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 404, path)
            self.assertEqual(r.headers["content-type"].split(";")[0], "application/json", path)
            body = r.json()
            self.assertEqual(body["error_code"], "NOT_FOUND", path)
            self.assertEqual(set(body) - {"details"}, {"error_code", "message", "trace_id"}, path)
            self.assertNotIn("<html", r.text.lower(), path)

    def test_phuong_thuc_sai_tren_api_van_not_found_cua_envelope(self):
        r = self.client.post("/api/v1/ping", headers={"X-BO19-CSRF": "1"})
        self.assertEqual((r.status_code, r.json()["error_code"]), (404, "NOT_FOUND"))

    def test_file_la_duoi_assets_la_404_khong_phai_index(self):
        for path in ("/assets/khong-co.js", "/assets/sub/khong-co.css", "/assets/", "/assets"):
            r = self.client.get(path)
            if path == "/assets":  # không có dấu gạch cuối: đây là một tuyến SPA bình thường, không thuộc thư mục asset
                self.assertEqual(r.status_code, 200)
                continue
            self.assertEqual(r.status_code, 404, path)
            self.assertEqual(r.json()["error_code"], "NOT_FOUND", path)
            self.assertNotIn("<html", r.text.lower(), path)

    def test_get_la_con_lai_la_index_html(self):
        for path in ("/", "/login", "/chat", "/my-requests", "/my-requests/33333333-3333-4333-8333-333333333333", "/review/PENDING_APPROVAL", "/khong-co-trang-nay", "/index.html"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertEqual(r.text, INDEX, path)
            self.assertTrue(r.headers["content-type"].startswith("text/html"), path)

    def test_post_vao_tuyen_spa_khong_tra_index(self):
        r = self.client.post("/chat", headers={"X-BO19-CSRF": "1"})
        self.assertNotEqual(r.status_code, 200)
        self.assertNotIn("<html", r.text.lower())


class FileThat(Base):
    def test_asset_da_bam_ten_cache_mot_nam(self):
        r = self.client.get("/assets/app-a1b2c3.js")
        self.assertEqual((r.status_code, r.text), (200, JS))
        self.assertEqual(r.headers["cache-control"], "public, max-age=31536000, immutable")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertIn("javascript", r.headers["content-type"])
        css = self.client.get("/assets/app-d4e5f6.css")
        self.assertEqual((css.text, css.headers["content-type"].split(";")[0]), (CSS, "text/css"))

    def test_index_va_tep_goc_khong_cache(self):
        for path in ("/", "/chat", "/index.html", "/favicon.ico"):
            r = self.client.get(path)
            self.assertEqual(r.headers["cache-control"], "no-store", path)
            self.assertEqual(r.headers["x-content-type-options"], "nosniff", path)
        self.assertEqual(self.client.get("/favicon.ico").content, b"\x00\x00\x01\x00")

    def test_head(self):
        for path in ("/", "/assets/app-a1b2c3.js"):
            r = self.client.head(path)
            self.assertEqual((r.status_code, r.content), (200, b""), path)


class KhongThoatThuMuc(Base):
    def setUp(self):
        super().setUp()
        self.secret = Path(tempfile.mkdtemp(prefix="bo19-secret-"))
        self.addCleanup(shutil.rmtree, self.secret, ignore_errors=True)
        (self.secret / "bi-mat.txt").write_text("NOI_DUNG_BI_MAT", encoding="utf-8")
        (self.root / "assets" / "ngoai.txt").write_text("trong thư mục build", encoding="utf-8")

    def test_duong_dan_thoat(self):
        name = self.secret.name
        for path in ("/assets/../../" + name + "/bi-mat.txt", "/assets/%2e%2e/%2e%2e/" + name + "/bi-mat.txt", "/..%2f" + name + "/bi-mat.txt", "/%2e%2e/" + name + "/bi-mat.txt",
                     "/" + str(self.secret / "bi-mat.txt").replace("\\", "/"), "//" + str(self.secret / "bi-mat.txt").replace("\\", "/")):
            r = self.client.get(path)
            self.assertNotIn("NOI_DUNG_BI_MAT", r.text, path)

    def test_lien_ket_bieu_tuong_ra_ngoai_khong_doc_duoc(self):
        link = self.root / "assets" / "lien-ket.txt"
        try:
            os.symlink(self.secret / "bi-mat.txt", link)
        except (OSError, NotImplementedError):
            self.skipTest("môi trường không tạo được liên kết biểu tượng")
        r = self.client.get("/assets/lien-ket.txt")
        self.assertNotIn("NOI_DUNG_BI_MAT", r.text)
        self.assertEqual(r.status_code, 404)

    def test_tep_trong_thu_muc_build_van_doc_duoc(self):
        self.assertEqual(self.client.get("/assets/ngoai.txt").text, "trong thư mục build")


class KhongCoClient(unittest.TestCase):
    def test_static_dir_none_thi_khong_co_catch_all(self):
        c = client_for(None)
        self.assertEqual(c.get("/api/v1/ping").status_code, 200)
        self.assertEqual(c.get("/chat").status_code, 404)  # mặc định của framework, không phải index.html
        self.assertEqual(c.get("/api/v1/khong-co").json()["error_code"], "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
