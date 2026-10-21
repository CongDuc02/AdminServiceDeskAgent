"""`tools/render-probes/render_probe_measure.py` — phép đo từ xa trên Render bằng tài khoản giả có thời hạn (ngoại lệ cổng 2.7, PO 2026-10-21).

Máy chủ giả trên 127.0.0.1 (stdlib, theo `tools/render-probes/test_probe.py`): đăng nhập, mở phiên chat, SSE `turn.reply`. Mật khẩu và cookie là dữ liệu giả; test kiểm chúng không lọt ra đầu ra hay file kết quả.
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_render_probe_measure -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import datetime as dt
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("render_probe_measure", REPO / "tools" / "render-probes" / "render_probe_measure.py")
rpm = importlib.util.module_from_spec(spec)
sys.modules["render_probe_measure"] = rpm
spec.loader.exec_module(rpm)

PASSWORD = "MAT-KHAU-GIA-CUA-TEST-KHONG-DUOC-LOT-RA"
COOKIE = "bo19_session=COOKIE-GIA-KHONG-DUOC-LOT-RA"
T0 = dt.datetime(2026, 10, 22, 8, 0, tzinfo=dt.timezone.utc)


RID = "22222222-2222-4222-8222-222222222222"


class Fake(BaseHTTPRequestHandler):
    logins = 0
    rate_limit_after: int | None = None
    lock = threading.Lock()
    reply_has_request = True
    submit_ready = True
    confirmed = False
    submitted = False
    polls_after_submit = 0
    done_after_polls = 3
    confirm_calls = 0

    def log_message(self, *a):  # im lặng
        pass

    def _json(self, code: int, body: dict, headers: dict | None = None) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/healthz":
            return self._json(200, {"status": "ok"})
        if self.path == f"/api/v1/requests/{RID}":
            if Fake.submitted:
                Fake.polls_after_submit += 1
                done = Fake.polls_after_submit > Fake.done_after_polls
                return self._json(200, {"status": "IN_REVIEW" if done else "SUBMITTED", "documents": [{"status": "PENDING_APPROVAL" if done else "DRAFT"}], "row_version": 5, "slots": [], "submit_ready": True})
            slots = [] if Fake.confirmed else [{"slot_name": "full_name", "value_status": "PROPOSED", "row_version": 2}, {"slot_name": "job_title", "value_status": "PROPOSED", "row_version": 3}]
            return self._json(200, {"status": "DRAFT", "documents": [], "row_version": 4, "slots": slots, "submit_ready": Fake.confirmed and Fake.submit_ready})
        self._json(404, {})

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/v1/auth/session":
            with Fake.lock:
                Fake.logins += 1
                n = Fake.logins
            if Fake.rate_limit_after is not None and n > Fake.rate_limit_after:
                return self._json(429, {"error_code": "RATE_LIMITED"})
            if body.get("password") != PASSWORD:
                return self._json(401, {"error_code": "INVALID_CREDENTIALS"})
            return self._json(200, {"employee_code": body.get("employee_code")}, {"set-cookie": COOKIE + "; Path=/; Secure; HttpOnly"})
        if self.headers.get("Cookie") != COOKIE:
            return self._json(401, {"error_code": "UNAUTHENTICATED"})
        if self.path == "/api/v1/chat-sessions":
            return self._json(201, {"id": "11111111-1111-4111-8111-111111111111"})
        if self.path == f"/api/v1/requests/{RID}/actions/confirm-slots":
            Fake.confirm_calls += 1
            Fake.confirmed = True
            return self._json(200, {"status": "DRAFT", "documents": [], "row_version": 4, "slots": [], "submit_ready": Fake.submit_ready})
        if self.path == f"/api/v1/requests/{RID}/actions/submit":
            if body.get("expected_row_version") != 4 or not self.headers.get("Idempotency-Key"):
                return self._json(409, {"error_code": "ROW_VERSION_STALE"})
            Fake.submitted = True
            return self._json(200, {"decision_record_id": "x"})
        if self.path.endswith("/turns"):
            reply = {"active_request": {"id": RID}} if Fake.reply_has_request else {"active_request": None}
            data = ("event: turn.accepted\ndata: {}\n\nevent: turn.reply\ndata: " + json.dumps(reply) + "\n\n").encode()
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._json(404, {})


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Fake.logins, Fake.rate_limit_after = 0, None
        Fake.reply_has_request, Fake.submit_ready, Fake.confirmed, Fake.submitted, Fake.polls_after_submit, Fake.done_after_polls, Fake.confirm_calls = True, True, False, False, 0, 3, 0
        self.tmp = tempfile.TemporaryDirectory(prefix="bo19-measure-")
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        (self.out / "probe_window.json").write_text(json.dumps({"seeded_at": "2026-10-22T07:00:00+00:00", "expires_at": "2026-10-25T07:00:00+00:00", "accounts": ["DO-0001"], "torn_down_at": None}), encoding="utf-8")
        (self.out / "probe_passwords.txt").write_text(f"# giả\nDO-0001\t{PASSWORD}\n", encoding="utf-8")
        self.lines: list[str] = []

    def everything_written(self) -> str:
        parts = list(self.lines)
        parts += [p.read_text(encoding="utf-8") for p in self.out.glob("measure-*.jsonl")]
        budget = self.out / "probe_budget.json"
        if budget.exists():
            parts.append(budget.read_text(encoding="utf-8"))
        return " ".join(parts)


class Chan(Base):
    def test_khong_co_cua_so_hoac_da_thu_hoi_hoac_het_han_thi_tu_choi(self):
        (self.out / "probe_window.json").unlink()
        with self.assertRaises(rpm.Refused) as cm:
            rpm.login_burst(self.url, "DO-0001", 2, out=self.out, at=T0, echo=self.lines.append)
        self.assertEqual(str(cm.exception), "MEASURE_NO_WINDOW")
        window = {"seeded_at": "x", "expires_at": "2026-10-25T07:00:00+00:00", "accounts": [], "torn_down_at": "2026-10-22T09:00:00+00:00"}
        (self.out / "probe_window.json").write_text(json.dumps(window), encoding="utf-8")
        with self.assertRaises(rpm.Refused) as cm:
            rpm.login_burst(self.url, "DO-0001", 2, out=self.out, at=T0, echo=self.lines.append)
        self.assertEqual(str(cm.exception), "MEASURE_WINDOW_TORN_DOWN")
        window["torn_down_at"] = None
        (self.out / "probe_window.json").write_text(json.dumps(window), encoding="utf-8")
        with self.assertRaises(rpm.Refused) as cm:
            rpm.login_burst(self.url, "DO-0001", 2, out=self.out, at=T0 + dt.timedelta(days=4), echo=self.lines.append)
        self.assertEqual(str(cm.exception), "MEASURE_WINDOW_EXPIRED")
        self.assertEqual(Fake.logins, 0)  # từ chối TRƯỚC khi chạm máy chủ

    def test_khong_co_mat_khau_thi_tu_choi(self):
        (self.out / "probe_passwords.txt").write_text("# trống\n", encoding="utf-8")
        with self.assertRaises(rpm.Refused) as cm:
            rpm.turns(self.url, "DO-0001", 1, out=self.out, at=T0, echo=self.lines.append)
        self.assertEqual(str(cm.exception), "MEASURE_NO_PASSWORD")

    def test_main_chi_do_len_https(self):
        sys.argv = ["x", "login-burst", "--url", "http://x.example.test"]
        self.assertEqual(rpm.main(), 1)


class LoginBurst(Base):
    def test_n_lan_dang_nhap_dong_thoi_ghi_thoi_gian_va_trang_thai(self):
        res = rpm.login_burst(self.url, "DO-0001", 4, out=self.out, stamp="t1", at=T0, echo=self.lines.append)
        self.assertEqual((res["n"], res["all_ok"], res["rate_limited"]), (4, True, False))
        self.assertEqual([r["status"] for r in res["results"]], [200] * 4)
        self.assertEqual(Fake.logins, 4)
        self.assertEqual(len((self.out / "measure-t1.jsonl").read_text(encoding="utf-8").splitlines()), 1)

    def test_gap_rate_limited_thi_bao_va_khong_coi_la_dat(self):
        Fake.rate_limit_after = 2
        res = rpm.login_burst(self.url, "DO-0001", 4, out=self.out, stamp="t2", at=T0, echo=self.lines.append)
        self.assertTrue(res["rate_limited"])
        self.assertFalse(res["all_ok"])

    def test_mat_khau_va_cookie_khong_lot_ra_dau_ra_hay_file(self):
        rpm.login_burst(self.url, "DO-0001", 2, out=self.out, stamp="t3", at=T0, echo=self.lines.append)
        everything = self.everything_written()
        self.assertNotIn(PASSWORD, everything)
        self.assertNotIn("COOKIE-GIA", everything)


class Turns(Base):
    def run_turns(self, n, **kw):
        return rpm.turns(self.url, "DO-0001", n, out=self.out, stamp="t4", at=T0, echo=self.lines.append, sleep=lambda s: self.slept.append(s), **kw)

    def setUp(self):
        super().setUp()
        self.slept: list[float] = []

    def test_do_tung_luot_tom_tat_va_nguong_15s(self):
        res = self.run_turns(3, label="baseline", pause_s=5)
        self.assertEqual((res["n"], res["replies"], res["within_15s"], res["label"]), (3, 3, True, "baseline"))
        self.assertLess(res["max_s"], 15)
        self.assertEqual(self.slept, [5, 5])  # nghỉ giữa các lượt, không nghỉ sau lượt cuối
        rows = [json.loads(line) for line in (self.out / "measure-t4.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["measure"] for r in rows], ["turn", "turn", "turn", "turns_summary"])
        self.assertTrue(all(r["events"][-1][0] == "turn.reply" for r in rows[:3]))

    def test_tran_luot_cho_ca_phep_do_dem_qua_nhieu_lan_chay(self):
        self.run_turns(5, max_total=8)
        self.assertEqual(rpm.read_budget(self.out)["turns_done"], 5)
        with self.assertRaises(rpm.Refused) as cm:
            self.run_turns(4, max_total=8)  # 5 + 4 > 8
        self.assertEqual(str(cm.exception), "MEASURE_LLM_BUDGET")
        self.assertEqual(rpm.read_budget(self.out)["turns_done"], 5)  # từ chối không đếm thêm, không gọi máy chủ
        self.run_turns(3, max_total=8)
        self.assertEqual(rpm.read_budget(self.out)["turns_done"], 8)

    def test_mac_dinh_tran_la_tam_luot(self):
        self.assertEqual(rpm.MAX_TURNS_TOTAL, 8)  # ≈ 16 lời gọi Groq (2 mỗi lượt) trong trần 20 của PO

    def test_sai_mat_khau_thi_dung_o_dang_nhap_va_khong_ton_luot(self):
        (self.out / "probe_passwords.txt").write_text("DO-0001\tSAI\n", encoding="utf-8")
        with self.assertRaises(rpm.Refused) as cm:
            self.run_turns(2)
        self.assertEqual(str(cm.exception), "MEASURE_LOGIN_FAILED_401")
        self.assertEqual(rpm.read_budget(self.out)["turns_done"], 0)


class JobWindow(Base):
    def run_window(self, turns_during=2, **kw):
        return rpm.job_window(self.url, "DO-0001", turns_during, out=self.out, stamp="t5", at=T0, echo=self.lines.append, sleep=lambda s: None, wait_s=3, **kw)

    def test_dung_request_xac_nhan_slot_de_xuat_gui_roi_do_cac_luot_trong_luc_job(self):
        Fake.done_after_polls = 100  # job "chưa xong" trong lúc các lượt đo chạy
        res = self.run_window(turns_during=2, label="soffice")
        self.assertEqual(Fake.confirm_calls, 1)  # slot PROPOSED được xác nhận (như giao diện)
        self.assertEqual(len(res["turns"]), 2)
        self.assertTrue(all(t["http_status"] == 200 and t["turn_s"] is not None for t in res["turns"]))
        self.assertTrue(all(t["start_after_submit_s"] >= 0 for t in res["turns"]))
        self.assertEqual([e["request"] for e in res["request_status_timeline"]][:1], ["SUBMITTED"])
        self.assertEqual(rpm.read_budget(self.out)["turns_done"], 3)  # một lượt dựng request + hai lượt đo

    def test_job_xong_thi_ghi_gio_va_danh_dau_luot_sau_do_khong_con_trong_luc_job(self):
        Fake.done_after_polls = 0  # lần hỏi đầu sau submit đã thấy IN_REVIEW
        res = self.run_window(turns_during=1)
        self.assertIsNotNone(res["job_done_after_submit_s"])
        self.assertEqual(rpm.read_budget(self.out)["turns_done"], 2)

    def test_tran_luot_tinh_ca_luot_dung_request(self):
        (self.out / "probe_budget.json").write_text(json.dumps({"turns_done": 6}), encoding="utf-8")
        with self.assertRaises(rpm.Refused) as cm:
            self.run_window(turns_during=2)  # 6 + 1 + 2 > 8
        self.assertEqual(str(cm.exception), "MEASURE_LLM_BUDGET")
        self.assertEqual(rpm.read_budget(self.out)["turns_done"], 6)

    def test_luot_dung_request_khong_ra_request_thi_dung_khong_them_luot(self):
        Fake.reply_has_request = False
        with self.assertRaises(rpm.Refused) as cm:
            self.run_window()
        self.assertEqual(str(cm.exception), "MEASURE_NO_ACTIVE_REQUEST")
        self.assertEqual(rpm.read_budget(self.out)["turns_done"], 1)  # chỉ đếm lượt đã chạy

    def test_chua_du_dieu_kien_gui_thi_dung_truoc_khi_submit(self):
        Fake.submit_ready = False
        with self.assertRaises(rpm.Refused) as cm:
            self.run_window()
        self.assertEqual(str(cm.exception), "MEASURE_NOT_SUBMIT_READY")
        self.assertFalse(Fake.submitted)

    def test_mat_khau_va_cookie_khong_lot_ra(self):
        self.run_window(turns_during=1)
        everything = self.everything_written()
        self.assertNotIn(PASSWORD, everything)
        self.assertNotIn("COOKIE-GIA", everything)


class Health(Base):
    def test_healthz_200_in_so_giay(self):
        res = rpm.health(self.url, 10, echo=self.lines.append)
        self.assertIsNotNone(res["healthz_after_s"])

    def test_khong_toi_duoc_thi_none(self):
        res = rpm.health("http://127.0.0.1:1", 2, echo=self.lines.append)
        self.assertIsNone(res["healthz_after_s"])


if __name__ == "__main__":
    unittest.main()
