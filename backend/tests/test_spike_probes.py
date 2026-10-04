"""Test endpoint đo của S3 — A-025, A-050. Gỡ cùng khối SPIKE S3 ở bước 7.

Chạy từ backend/:  python -m unittest tests.test_spike_probes -v   (cần fastapi, httpx — có trong lock)
Không cần PostgreSQL: chỉ dựng router, không chạy bước kiểm khởi động.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from bo19.entrypoints import api_main  # noqa: E402

TOKEN = "tok-for-test-only"
HDR = {"X-BO19-Spike-Token": TOKEN}
ENV_ON = {"BO19_SPIKE_PROBES": "1", "BO19_SPIKE_TOKEN": TOKEN, "RENDER_GIT_COMMIT": "abc1234", "RENDER_GIT_BRANCH": "spike/s3-do"}


def make_app(env: dict[str, str]) -> FastAPI:
    app = FastAPI(title="bo19", docs_url=None, redoc_url=None, openapi_url=None)
    api_main._mount_spike(app, env)
    return app


def events(body: str) -> list[dict]:
    out = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        if block.startswith(":"):
            out.append({"comment": block})
            continue
        name = next(l[7:] for l in block.split("\n") if l.startswith("event: "))
        data = json.loads(next(l[6:] for l in block.split("\n") if l.startswith("data: ")))
        out.append({"event": name, **data})
    return out


class Gate(unittest.TestCase):
    def test_co_tat_khong_gan_tuyen(self):
        self.assertIsNone(api_main.make_spike_router({}))
        self.assertIsNone(api_main.make_spike_router({"BO19_SPIKE_PROBES": "0", "BO19_SPIKE_TOKEN": TOKEN}))
        self.assertIsNone(api_main.make_spike_router({"BO19_SPIKE_PROBES": "true", "BO19_SPIKE_TOKEN": TOKEN}))

    def test_co_bat_thieu_token_khong_gan_tuyen(self):
        self.assertIsNone(api_main.make_spike_router({"BO19_SPIKE_PROBES": "1"}))
        self.assertIsNone(api_main.make_spike_router({"BO19_SPIKE_PROBES": "1", "BO19_SPIKE_TOKEN": ""}))

    def test_404_giong_het_duong_dan_la(self):
        paths = ["/api/_spike/commit", "/api/_spike/sleep?s=0", "/api/_spike/sse?interval=0&max=1"]
        sai = [None, {"X-BO19-Spike-Token": "sai"}, {"X-BO19-Spike-Token": TOKEN + "x"}, {"X-BO19-Spike-Token": ""}]
        for env, headers in (({}, [None, HDR]), (ENV_ON, sai)):  # cờ tắt: kể cả token đúng; cờ bật: token sai hoặc thiếu
            c = TestClient(make_app(env))
            ref = c.get("/api/_spike/khong-co")
            self.assertEqual(ref.status_code, 404)
            for hdr in headers:
                for p in paths:
                    r = c.get(p, headers=hdr)
                    got = (r.status_code, r.content, r.headers["content-type"], r.headers["content-length"])
                    want = (ref.status_code, ref.content, ref.headers["content-type"], ref.headers["content-length"])
                    self.assertEqual(got, want, (bool(env), hdr, p))

    def test_token_dung_vao_duoc(self):
        c = TestClient(make_app(ENV_ON))
        r = c.get("/api/_spike/commit", headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["commit"], r.json()["branch"]), ("abc1234", "spike/s3-do"))
        self.assertIn("boot_epoch", r.json())
        self.assertEqual(TestClient(make_app({**ENV_ON, "RENDER_GIT_COMMIT": ""})).get("/api/_spike/commit", headers=HDR).json()["commit"], "")

    def test_chi_duoi_prefix_api_spike(self):
        self.assertEqual(TestClient(make_app(ENV_ON)).get("/_spike/commit", headers=HDR).status_code, 404)


class Tran(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(make_app(ENV_ON))

    def test_sleep_tran_va_tham_so(self):
        for q in ("", "?s=abc", "?s=-1", "?s=1800.5", "?s=nan", "?s=inf"):
            r = self.c.get("/api/_spike/sleep" + q, headers=HDR)
            self.assertEqual(r.status_code, 400, q)
            self.assertEqual(r.json()["error"], "SPIKE_BAD_PARAM")

    def test_sse_tran_va_tham_so(self):
        for q in ("?max=3600.5", "?max=0", "?interval=0.05", "?interval=-1", "?interval=x", "?kind=nope"):
            r = self.c.get("/api/_spike/sse" + q, headers=HDR)
            self.assertEqual(r.status_code, 400, q)
        self.assertEqual(api_main.SPIKE_SLEEP_MAX_S, 1800.0)
        self.assertEqual(api_main.SPIKE_SSE_MAX_S, 3600.0)

    def test_sleep_ngu_that(self):
        t = time.monotonic()
        r = self.c.get("/api/_spike/sleep?s=0.3", headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(time.monotonic() - t, 0.3)
        self.assertEqual(r.json()["slept"], 0.3)


class Sse(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(make_app(ENV_ON))

    def test_event_co_open_ngay_nhip_tick_va_end(self):
        r = self.c.get("/api/_spike/sse?interval=0.1&max=0.55", headers=HDR)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers["content-type"].startswith("text/event-stream"))
        self.assertEqual(r.headers["cache-control"], "no-cache")
        self.assertNotIn("x-accel-buffering", r.headers)
        ev = events(r.text)
        self.assertEqual(ev[0]["event"], "open")
        self.assertEqual(ev[-1]["event"], "end")
        ticks = [e for e in ev if e["event"] == "tick"]
        self.assertGreaterEqual(len(ticks), 4)
        self.assertEqual([e["seq"] for e in ev], list(range(len(ev))))
        gaps = [b["server_epoch"] - a["server_epoch"] for a, b in zip(ticks, ticks[1:])]
        for g in gaps:
            self.assertAlmostEqual(g, 0.1, delta=0.06)

    def test_im_lang_chi_co_open_va_end(self):
        r = self.c.get("/api/_spike/sse?interval=0&max=0.3", headers=HDR)
        self.assertEqual([e["event"] for e in events(r.text)], ["open", "end"])

    def test_comment_la_nhip(self):
        r = self.c.get("/api/_spike/sse?interval=0.1&max=0.45&kind=comment", headers=HDR)
        ev = events(r.text)
        self.assertEqual(ev[0]["event"], "open")
        self.assertGreaterEqual(sum(1 for e in ev if "comment" in e), 3)
        self.assertFalse(any(e.get("event") == "tick" for e in ev))

    def test_accel_no_them_header(self):
        r = self.c.get("/api/_spike/sse?interval=0&max=0.2&accel=no", headers=HDR)
        self.assertEqual(r.headers["x-accel-buffering"], "no")


class MotKetNoi(unittest.IsolatedAsyncioTestCase):
    async def test_thu_tu_kiem_va_chi_cho_mot_ket_noi(self):
        app = make_app(ENV_ON)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            first = asyncio.create_task(c.get("/api/_spike/sleep?s=1", headers=HDR))
            await asyncio.sleep(0.2)
            # cờ → token → trần → kết nối thứ hai
            self.assertEqual((await c.get("/api/_spike/sleep?s=0", headers={"X-BO19-Spike-Token": "sai"})).status_code, 404)
            self.assertEqual((await c.get("/api/_spike/sleep?s=99999", headers=HDR)).status_code, 400)
            self.assertEqual((await c.get("/api/_spike/sleep?s=0", headers=HDR)).status_code, 429)
            self.assertEqual((await c.get("/api/_spike/sse?interval=0&max=1", headers=HDR)).status_code, 429)
            self.assertEqual((await c.get("/api/_spike/commit", headers=HDR)).status_code, 200)  # /commit không giữ chỗ
            self.assertEqual((await first).status_code, 200)
            self.assertEqual((await c.get("/api/_spike/sleep?s=0", headers=HDR)).status_code, 200)  # chỗ đã trả

    async def test_sse_tra_cho_khi_ket_thuc(self):
        app = make_app(ENV_ON)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            self.assertEqual((await c.get("/api/_spike/sse?interval=0&max=0.2", headers=HDR)).status_code, 200)
            self.assertEqual((await c.get("/api/_spike/sse?interval=0&max=0.2", headers=HDR)).status_code, 200)


if __name__ == "__main__":
    unittest.main()
