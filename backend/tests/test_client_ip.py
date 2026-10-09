"""IP cho rate limit — `bo19.api.auth.client_ip`: một hàm duy nhất, mặc định không tin `X-Forwarded-For` (A-062, cổng 2.7).

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_client_ip -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import re
import unittest
from pathlib import Path

from starlette.requests import Request

from bo19.api.auth.client_ip import UNKNOWN, client_ip

SRC = Path(__file__).resolve().parents[1] / "src" / "bo19"


def request(peer: tuple[str, int] | None, headers: dict[str, str] | None = None) -> Request:
    scope = {"type": "http", "method": "POST", "path": "/api/v1/auth/session", "query_string": b"",
             "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()], "client": peer}
    return Request(scope)


class MacDinhKhongTinHeader(unittest.TestCase):
    def test_dung_dia_chi_ket_noi_truc_tiep(self):
        self.assertEqual(client_ip(request(("203.0.113.9", 4444))), "203.0.113.9")

    def test_x_forwarded_for_bi_bo_qua(self):
        r = request(("203.0.113.9", 4444), {"X-Forwarded-For": "198.51.100.7, 192.0.2.1"})
        self.assertEqual(client_ip(r), "203.0.113.9")

    def test_cac_header_khac_cung_bi_bo_qua(self):
        for header in ("X-Real-IP", "Forwarded", "X-Client-IP", "CF-Connecting-IP", "True-Client-IP", "X-Forwarded-Host"):
            r = request(("203.0.113.9", 4444), {header: "198.51.100.7"})
            self.assertEqual(client_ip(r), "203.0.113.9", header)

    def test_ipv6(self):
        self.assertEqual(client_ip(request(("2001:db8::1", 4444))), "2001:db8::1")

    def test_khong_co_dia_chi_thi_dan_vao_mot_nguong_chung_khong_bo_qua(self):
        self.assertEqual(client_ip(request(None)), UNKNOWN)
        self.assertEqual(client_ip(request(("", 0))), UNKNOWN)

    def test_doi_header_khong_doi_scope_cua_rate_limit(self):
        # kẻ tấn công đổi X-Forwarded-For ở mỗi lần thử vẫn rơi vào cùng một scope
        scopes = {client_ip(request(("203.0.113.9", 4444), {"X-Forwarded-For": f"10.0.0.{i}"})) for i in range(50)}
        self.assertEqual(scopes, {"203.0.113.9"})


class MotHamDuyNhat(unittest.TestCase):
    def test_khong_noi_nao_khac_doc_header_chuyen_tiep(self):
        pattern = re.compile(r"""headers(?:\.get\(|\[)\s*["'](?:x-forwarded|forwarded|x-real-ip)""", re.IGNORECASE)
        offenders = [str(p.relative_to(SRC)) for p in SRC.rglob("*.py") if pattern.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])  # client_ip chỉ dùng `request.client`; sửa cách đọc IP (A-062) là sửa MỘT hàm đó

    def test_uvicorn_chay_voi_proxy_headers_false(self):
        text = (SRC / "entrypoints" / "api_main.py").read_text(encoding="utf-8")
        self.assertIn("proxy_headers=False", text)  # nếu không, uvicorn tự viết lại địa chỉ client từ X-Forwarded-For của peer được tin


if __name__ == "__main__":
    unittest.main()
