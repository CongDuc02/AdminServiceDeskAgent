"""Chốt chặn của bộ test — `tests/_guard.py`: khoá API bị xoá trước từng test; kết nối mạng thật bị chặn; mọi file test đều nhập chốt chặn.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_guard -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401

import asyncio
import os
import re
import socket
import unittest
from pathlib import Path
from unittest import mock

from tests import _guard as guard

ROOT = Path(__file__).resolve().parents[2]
TEST_FILES = sorted((ROOT / "backend" / "tests").glob("test_*.py")) + sorted((ROOT / "tools").glob("*/test_*.py"))
os.environ["BO19_LLM_API_KEY"] = "gsk_KHOA_DAT_O_CAP_LOP_PHAI_BI_XOA_TRUOC_TUNG_TEST"  # đặt lúc import — test dưới đây phải thấy nó đã bị xoá


class KhoaApi(unittest.TestCase):
    def test_khoa_bi_xoa_truoc_test(self):
        self.assertNotIn("BO19_LLM_API_KEY", os.environ)

    def test_khoa_do_test_khac_dat_khong_song_sang_test_ke_tiep(self):
        os.environ["BO19_LLM_API_KEY"] = "gsk_DO_MOT_TEST_DAT"
        self.assertIn("BO19_LLM_API_KEY", os.environ)  # trong chính test này vẫn đặt được

    def test_khoa_van_bi_xoa_sau_do(self):
        self.assertNotIn("BO19_LLM_API_KEY", os.environ)


class KhoaApiAsync(unittest.IsolatedAsyncioTestCase):
    async def test_test_async_cung_bi_xoa_khoa(self):
        self.assertNotIn("BO19_LLM_API_KEY", os.environ)


class ChanMang(unittest.TestCase):
    def test_noi_host_ngoai_bi_chan(self):
        for host, port in (("api.groq.com", 443), ("93.184.216.34", 443), ("8.8.8.8", 53)):
            with self.assertRaises(guard.NetworkBlocked, msg=host):
                socket.create_connection((host, port), timeout=1)

    def test_phan_giai_ten_host_ngoai_bi_chan(self):
        with self.assertRaises(guard.NetworkBlocked):
            socket.getaddrinfo("api.groq.com", 443)

    def test_connect_ex_va_asyncio_cung_bi_chan(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(s.close)
        with self.assertRaises(guard.NetworkBlocked):
            s.connect_ex(("93.184.216.34", 443))

        async def go():
            await asyncio.open_connection("93.184.216.34", 443)

        with self.assertRaises(guard.NetworkBlocked):
            asyncio.run(go())

    def test_thong_diep_chan_khong_chua_ten_host(self):
        with self.assertRaises(guard.NetworkBlocked) as cm:
            socket.getaddrinfo("bi-mat.example.test", 443)
        self.assertNotIn("bi-mat", str(cm.exception))

    def test_loopback_van_duoc(self):
        srv = socket.socket()
        self.addCleanup(srv.close)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        c = socket.create_connection(srv.getsockname(), timeout=2)
        c.close()

    def test_host_postgresql_thu_duoc_qua_chot_nhung_host_khac_thi_khong(self):
        with mock.patch.dict(os.environ, {"BO19_TEST_PG_SUPERUSER_DSN": "postgresql://postgres@db.test.invalid:5432/postgres"}):
            try:
                socket.getaddrinfo("db.test.invalid", 5432)
            except guard.NetworkBlocked:
                self.fail("host của PostgreSQL thử phải qua chốt chặn")
            except OSError:
                pass  # phân giải thật thất bại vì tên không tồn tại — đã qua chốt
            with self.assertRaises(guard.NetworkBlocked):
                socket.getaddrinfo("api.groq.com", 443)

    def test_httpx_mock_transport_khong_dung_socket(self):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"ok": 1})

        with httpx.Client(transport=httpx.MockTransport(handler)) as c:
            self.assertEqual(c.get("https://api.groq.com/openai/v1/x").json(), {"ok": 1})  # URL "thật" nhưng không có kết nối nào

    def test_httpx_that_toi_host_ngoai_bi_chan(self):
        import httpx
        with self.assertRaises(Exception) as cm:
            httpx.get("https://api.groq.com/openai/v1/models", timeout=2)
        chain, e = [], cm.exception
        while e is not None:
            chain.append(type(e).__name__)
            e = e.__cause__ or e.__context__
        self.assertIn("NetworkBlocked", chain)


class MoiFileTestNhapChotChan(unittest.TestCase):
    def test_moi_file_test_trong_backend_va_tools_nhap_chot_chan(self):
        self.assertGreater(len(TEST_FILES), 20)
        missing = [str(p.relative_to(ROOT)) for p in TEST_FILES if not re.search(r"^from tests import _guard\b", p.read_text(encoding="utf-8"), re.M)
                   and p.name != "test_guard.py"]
        self.assertEqual(missing, [], "file test không nhập tests._guard — chốt chặn mạng và khoá không áp cho nó")

    def test_chot_chan_dung_dau_file_truoc_moi_import_khac_cua_du_an(self):
        for p in TEST_FILES:
            text = p.read_text(encoding="utf-8")
            m = re.search(r"^from tests import _guard\b", text, re.M)
            if not m:
                continue
            first_bo19 = re.search(r"^(?:from|import) bo19\b", text, re.M)
            if first_bo19:
                self.assertLess(m.start(), first_bo19.start(), p.name)  # chốt chặn cài TRƯỚC khi mã dự án được nhập


if __name__ == "__main__":
    unittest.main()
