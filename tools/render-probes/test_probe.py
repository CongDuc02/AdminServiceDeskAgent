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
        elif self.path.startswith("/api/_spike/sse") and "interval=0.1" in self.path:
            # chế độ chậm cho test giết giữa chừng: một event mỗi 0.1 s tới khi client đi hoặc hết 60 s
            self._common("text/event-stream")
            t0, i = time.monotonic(), 0
            try:
                while time.monotonic() - t0 < 60:
                    d = {"seq": i, "server_epoch": time.time(), "note": HOST}
                    self.wfile.write(f"event: {'open' if i == 0 else 'tick'}\ndata: {json.dumps(d)}\n\n".encode())
                    self.wfile.flush()
                    i += 1
                    time.sleep(0.1)
            except OSError:
                pass
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
                jsonl = sorted((Path(d) / "out").rglob("*.jsonl"))
                self.assertEqual((len(files), len(jsonl)), (2, 2))
                texts = {"stdout": r.stdout, "stderr": r.stderr, **{f.name: f.read_text(encoding="utf-8") for f in files + jsonl}}
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
                # lượt hoàn tất: JSONL có dòng end và final; classification là completed
                s = probe.summarize_journal(jsonl[1])
                self.assertEqual((s["state"], s["classification"], s["case"]), ("complete", "completed", "sse-events"))
        finally:
            srv.shutdown()
            srv.server_close()


class BiGietGiuaChung(unittest.TestCase):
    """Probe bị giết (TerminateProcess) giữa lượt: JSONL giữ dữ liệu tới điểm chết, gắn nhãn gián đoạn, không áp ngưỡng."""

    def test_luot_bi_giet_giu_du_lieu_va_khong_ap_nguong(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d:
                out = Path(d) / "out"
                spec_f = Path(d) / "run.json"
                spec_f.write_text(json.dumps({"label": "killed", "runs": [{"case": "sse-events", "interval": 0.1, "max": 60, "enc": "none"}]}), encoding="utf-8")
                env = {**os.environ, "BO19_SPIKE_BASE_URL": f"http://localhost:{srv.server_port}", "BO19_SPIKE_TOKEN": "tok"}
                proc = subprocess.Popen([sys.executable, str(PROBE), "--spec", str(spec_f), "--out", str(out)], env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
                jl = out / "killed" / "01-sse-events-none.jsonl"
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if jl.exists() and jl.read_text(encoding="utf-8").count('"type":"event"') >= 8:
                        break
                    time.sleep(0.1)
                proc.kill()  # TerminateProcess trên Windows, SIGKILL trên Linux: không có dọn dẹp nào
                stdout, stderr = proc.communicate(timeout=30)
                self.assertTrue(jl.exists())
                self.assertFalse((out / "killed" / "01-sse-events-none.json").exists())  # file kết quả cuối chưa kịp ghi
                text = jl.read_text(encoding="utf-8")
                for leak in LEAKS + ("localhost",):
                    self.assertNotIn(leak, (text + stdout + stderr).lower(), leak)
                lines = [json.loads(l) for l in text.splitlines() if l.strip().endswith("}")]
                types = [l["type"] for l in lines]
                self.assertEqual(types[:2], ["meta", "start"])
                self.assertGreaterEqual(types.count("event"), 8)
                self.assertNotIn("end", types)  # không có dòng end ⇒ gián đoạn
                self.assertNotIn("final", types)
                ev = [l for l in lines if l["type"] == "event"]
                self.assertTrue(all(e["server_epoch"] is not None and e["wall"] and e["t"] >= 0 for e in ev))  # giờ server và giờ nhận
                s = probe.summarize_journal(jl)
                self.assertEqual(s["state"], "interrupted")
                self.assertEqual(s["classification"], "gián đoạn")
                self.assertGreaterEqual(s["events"], 8)
                self.assertTrue(s["verdict"].startswith("gián đoạn — không áp ngưỡng"), s["verdict"])
        finally:
            srv.shutdown()
            srv.server_close()

    def test_dong_cuoi_bi_cat_do_van_doc_duoc(self):
        with tempfile.TemporaryDirectory() as d:
            jl = Path(d) / "x.jsonl"
            jl.write_text('{"type":"start","case":"sse-events","params":{"interval":5},"enc":"none"}\n'
                          '{"type":"event","kind":"event","name":"open","seq":0,"server_epoch":100.0,"t":0.01,"wall":1.0}\n'
                          '{"type":"event","kind":"event","name":"tick","seq":1,"server_ep', encoding="utf-8")
            s = probe.summarize_journal(jl)
            self.assertEqual((s["state"], s["events"], s["bad_lines"]), ("interrupted", 1, 1))


def _ev(n: int, interval: float = 5.0, first: float = 0.01, jitter: dict[int, float] | None = None) -> list[dict]:
    """n event: open rồi các tick đúng nhịp; jitter[i] là độ trễ cộng thêm khi nhận event thứ i."""
    jitter = jitter or {}
    return [{"type": "event", "name": "open" if i == 0 else "tick", "seq": i, "server_epoch": 1000.0 + i * interval,
             "t": (first if i == 0 else i * interval + first) + jitter.get(i, 0.0), "wall": 0.0} for i in range(n)]


class Nguong(unittest.TestCase):
    def test_khong_thay_gom_dem(self):
        self.assertEqual(probe.verdict(_ev(100, jitter={7: 0.3}), 5.0, "complete"), "không thấy gom đệm")

    def test_mot_cap_don_le_la_khong_ket_luan_va_chay_lai(self):
        # event 10 tới trễ 3 s: cặp (9,10) lệch +3 s và cặp (10,11) lệch −3 s ⇒ hai cặp ≥ 2.5 s — đó là gom đệm theo ngưỡng
        v = probe.verdict(_ev(100, jitter={10: 3.0}), 5.0, "complete")
        self.assertEqual(v, "có gom đệm")
        # trễ 2.6 s ở event CUỐI: chỉ một cặp lệch ≥ 2.5 s
        v = probe.verdict(_ev(100, jitter={99: 2.6}), 5.0, "complete")
        self.assertTrue(v.startswith("không kết luận — một cặp"), v)

    def test_event_dau_den_muon_la_gom_dem(self):
        self.assertEqual(probe.verdict(_ev(100, first=5.0), 5.0, "complete"), "có gom đệm")

    def test_giua_hai_nhom_la_khong_ket_luan(self):
        self.assertEqual(probe.verdict(_ev(100, jitter={7: 0.8}), 5.0, "complete"), "không kết luận")  # lệch 0.8 s: > 0.5, < 2.5
        self.assertEqual(probe.verdict(_ev(100, first=3.0), 5.0, "complete"), "không kết luận")  # open sau 3 s: > 2, < 5

    def test_gian_doan_chua_du_cap_khong_ap_nguong(self):
        v = probe.verdict(_ev(30), 5.0, "interrupted")
        self.assertTrue(v.startswith("gián đoạn — không áp ngưỡng (29 cặp < 60)"), v)
        # kể cả khi dữ liệu có vẻ xấu
        self.assertTrue(probe.verdict(_ev(30, first=9.0), 5.0, "interrupted").startswith("gián đoạn — không áp ngưỡng"))

    def test_gian_doan_du_cap_van_gan_nhan_mot_phan(self):
        self.assertEqual(probe.verdict(_ev(70), 5.0, "interrupted"), "không thấy gom đệm [dữ liệu một phần: lượt gián đoạn]")


class Classify(unittest.TestCase):
    def test_restart_khong_phai_diem_cat(self):
        cut = {"ended": "eof_without_end_event", "after": {"status": 200, "restarted": False}}
        self.assertEqual(probe.classify(cut), "cut")
        self.assertEqual(probe.classify({**cut, "after": {"status": 200, "restarted": True}}), "restart")
        self.assertEqual(probe.classify({"ended": "error", "after": {"status": 200, "restarted": True}}), "restart")

    def test_khong_hoi_lai_duoc_thi_khong_khang_dinh(self):
        self.assertEqual(probe.classify({"ended": "error", "after": {"error": {"type": "TimeoutError"}}}), "cut_unverified")
        self.assertEqual(probe.classify({"ended": "error", "after": {"status": 502}}), "cut_unverified")

    def test_hoan_tat_va_bo_cuoc(self):
        self.assertEqual(probe.classify({"ended": "end_event", "after": {"status": 200, "restarted": False}}), "completed")
        self.assertEqual(probe.classify({"ended": "completed"}), "completed")
        self.assertEqual(probe.classify({"ended": "busy_gave_up"}), "busy_gave_up")


if __name__ == "__main__":
    unittest.main()
