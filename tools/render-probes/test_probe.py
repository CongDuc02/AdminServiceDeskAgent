"""Test việc che host của probe.py — repo công khai, log và file kết quả ai cũng xem được. Gỡ cùng thư mục ở bước 7 của S3.

Chạy từ thư mục gốc repo:  python -m unittest discover -s tools/render-probes -p "test_probe.py" -v
Chỉ thư viện chuẩn. Test đầu-cuối chạy probe.py thật, trong tiến trình con, với một server giả trên 127.0.0.1.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROBE = Path(__file__).with_name("probe.py")
spec = importlib.util.spec_from_file_location("probe", PROBE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

HOST = "secret-svc.onrender.com"
LEAKS = ("onrender", "secret-svc")


class Redact(unittest.TestCase):
    def test_moi_dang_cua_onrender(self):
        for raw in (f"https://{HOST}/api/_spike/sse?x=1", HOST, f"http://{HOST}:443", "SECRET-SVC.ONRENDER.COM", "a.b.onrender.com/x",
                    f"host={HOST};other={HOST}", "onrender.com"):
            out = probe.redact(raw)
            self.assertNotIn("onrender", out.lower(), raw)
            self.assertIn(probe.MASK, out)

    def test_khong_kem_scheme(self):
        self.assertEqual(probe.redact(f"connect to {HOST} failed"), f"connect to {probe.MASK} failed")

    def test_host_cua_target_ke_ca_khong_phai_onrender(self):
        self.assertEqual(probe.redact("GET http://Example.Internal:8080/x", "example.internal"), f"GET http://{probe.MASK}:8080/x")

    def test_khong_dung_den_chuoi_khac(self):
        for raw in ("cf-ray 8a1b-SIN", "render", "onrender", "x-render", '{"seq":1,"server_epoch":1.5}', ""):
            self.assertEqual(probe.redact(raw), raw)


class Headers(unittest.TestCase):
    def test_header_rui_ro_khong_ghi_nguyen_van(self):
        for name in ("Location", "location", "Content-Location", "Alt-Svc", "Link", "Refresh", "Set-Cookie", "Report-To", "NEL",
                     "X-Render-Origin-Server", "x-render-routing", "Access-Control-Allow-Origin"):
            n, v = probe.header_row(name, f"https://{HOST}/path")
            self.assertEqual(n, name)
            self.assertTrue(v.startswith("<masked len="), (name, v))
            self.assertIn("contained_host=True", v)
            self.assertNotIn("onrender", v)

    def test_header_rui_ro_khong_chua_host_van_bi_che(self):
        self.assertEqual(probe.header_row("X-Render-Origin-Server", "uvicorn")[1], "<masked len=7 contained_host=False>")

    def test_header_thuong_giu_gia_tri_nhung_che_host(self):
        self.assertEqual(probe.header_row("Cf-Ray", "8a1b2c3d-SIN"), ["Cf-Ray", "8a1b2c3d-SIN"])
        self.assertEqual(probe.header_row("X-Echo", f"see {HOST}"), ["X-Echo", f"see {probe.MASK}"])


class Stream(unittest.TestCase):
    def test_host_bi_cat_doi_giua_hai_lan_write_van_bi_che(self):
        raw = io.StringIO()
        st = probe.RedactingStream(raw)
        st.write("lỗi nối tới secret-svc.onren")
        st.write("der.com sau 3 s\n")
        st.write("dòng hai: ")
        st.write(f"{HOST}")
        st.flush()
        out = raw.getvalue()
        self.assertNotIn("onrender", out)
        self.assertEqual(out, f"lỗi nối tới {probe.MASK} sau 3 s\ndòng hai: {probe.MASK}")


class _Handler(BaseHTTPRequestHandler):
    """Server giả — cố tình đặt host Render ở header, thân JSON và event."""

    def log_message(self, *a):  # im lặng
        pass

    def _common(self, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Location", f"https://{HOST}/x")
        self.send_header("Alt-Svc", f'h3="{HOST}:443"')
        self.send_header("X-Render-Origin-Server", HOST)
        self.send_header("X-Echo", f"http://localhost:{self.server.server_port}/echo")
        self.send_header("Cf-Ray", "8a1b2c3d-SIN")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/api/_spike/commit"):
            self._common("application/json")
            self.wfile.write(json.dumps({"commit": "abc1234", "branch": HOST, "boot_epoch": 1.0, "server_epoch": time.time()}).encode())
        elif self.path.startswith("/api/_spike/sleep"):
            self._common("application/json")
            self.wfile.write(json.dumps({"slept": 0, "note": HOST}).encode())
        elif self.path.startswith("/api/_spike/sse"):
            self._common("text/event-stream")
            for i, name in enumerate(("open", "tick", "end")):
                d = {"seq": i, "server_epoch": time.time(), "note": HOST}
                self.wfile.write(f"event: {name}\ndata: {json.dumps(d)}\n\n".encode())
                self.wfile.flush()
                time.sleep(0.05)
        else:
            self.send_error(404)


class DauCuoi(unittest.TestCase):
    def test_stdout_stderr_va_file_khong_lo_host(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                spec_f = Path(d) / "run.json"
                spec_f.write_text(json.dumps({"label": "e2e", "expect_commit": "abc1234", "runs": [
                    {"case": "sleep", "s": 0, "enc": "none"},
                    {"case": "sse-events", "interval": 1, "max": 5, "enc": "browser"},
                ]}), encoding="utf-8")
                env = {**os.environ, "BO19_SPIKE_BASE_URL": f"http://localhost:{srv.server_port}", "BO19_SPIKE_TOKEN": "tok"}
                r = subprocess.run([sys.executable, str(PROBE), "--spec", str(spec_f), "--out", str(Path(d) / "out"), "--emit"],
                                   env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
                self.assertEqual(r.returncode, 0, r.stderr)
                files = sorted((Path(d) / "out").rglob("*.json"))
                self.assertEqual(len(files), 2)
                texts = {"stdout": r.stdout, "stderr": r.stderr, **{f.name: f.read_text(encoding="utf-8") for f in files}}
                for where, text in texts.items():
                    for leak in LEAKS:
                        self.assertNotIn(leak, text.lower(), f"{leak} lộ ở {where}")
                    self.assertNotIn("localhost", text.lower(), f"host của target lộ ở {where}")
                self.assertIn("RESULT_JSON", r.stdout)
                rec = json.loads(files[0].read_text(encoding="utf-8"))
                hdr = {k.lower(): v for k, v in rec["response_headers"]}
                self.assertTrue(hdr["location"].startswith("<masked len="))
                self.assertTrue(hdr["alt-svc"].startswith("<masked len="))
                self.assertTrue(hdr["x-render-origin-server"].startswith("<masked len="))
                self.assertEqual(hdr["x-echo"], f"http://{probe.MASK}:{srv.server_port}/echo")  # host của target che, cổng giữ
                self.assertEqual(hdr["cf-ray"], "8a1b2c3d-SIN")  # header thường giữ nguyên
                self.assertEqual(rec["meta"]["branch"], probe.MASK)
                self.assertEqual(rec["body"]["note"], probe.MASK)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
