"""Web Service — REST + 2 stream SSE + phục vụ client (06-structure.md mục Tiến trình) — composition root, không ai import entrypoints.

Bản S2 của Spike 1: chỉ bước kiểm khởi động #1, #2 và `GET /healthz`. Trượt bước kiểm nào thì ghi danh sách
mã trượt ra log rồi thoát mã 1 — không phục vụ request nào (mục Bước kiểm khởi động của 06-structure.md).
Không bao giờ ghi DSN hay mật khẩu ra log.
"""
from __future__ import annotations

import logging
import sys

import psycopg

from bo19.config.settings import ConfigError, load_settings
from bo19.startup.checks import run_s2_checks

log = logging.getLogger("bo19.startup")


def _startup() -> int | None:
    """Trả cổng để phục vụ, hoặc None khi trượt."""
    try:
        settings = load_settings()
    except ConfigError as e:
        log.error("STARTUP_FAIL %s", e)
        return None
    try:
        with psycopg.connect(settings.database_url, connect_timeout=10, application_name="bo19-api-startup") as conn:
            fails = run_s2_checks(conn)
    except psycopg.Error as e:
        # Thông điệp của driver có thể mang host — chỉ ghi lớp lỗi và SQLSTATE.
        log.error("STARTUP_FAIL STARTUP_DB_CONNECT_FAILED class=%s sqlstate=%s", type(e).__name__, e.sqlstate)
        return None
    if fails:
        for code in fails:
            log.error("STARTUP_FAIL %s", code)
        log.error("STARTUP_ABORT %d bước kiểm trượt — thoát mã 1", len(fails))
        return None
    log.info("STARTUP_OK bước kiểm #1, #2 đạt")
    return settings.port


# ===== SPIKE S3 (A-025, A-050) — GỠ HẲN ở bước 7 của S3: khối này, và hai dòng "SPIKE S3" trong main() =====
# Hai phép đo từ ngoài Render: một response SSE (/sse) và một request chậm (/sleep). Không thuộc thiết kế.
# Chỉ gắn khi BO19_SPIKE_PROBES=1 và có BO19_SPIKE_TOKEN; header X-BO19-Spike-Token phải khớp, nếu không thì 404
# giống hệt đường dẫn lạ. Thứ tự kiểm: cờ (lúc gắn) → token → trần tham số → kết nối thử thứ hai.
import asyncio  # noqa: E402
import hmac  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
from collections.abc import Mapping  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402

SPIKE_SLEEP_MAX_S = 1800.0  # trần cứng của /sleep
SPIKE_SSE_MAX_S = 3600.0  # trần cứng của /sse: 60 phút
SPIKE_STEP_S = 1.0  # nhịp tỉnh dậy để kiểm client còn nối không
SPIKE_SLOT_GRACE_S = 30.0  # chỗ thử tự hết hạn sau hạn của chính nó — phòng khi không ai trả chỗ
SPIKE_BOOT_EPOCH = time.time()


class _SpikeBadParam(Exception):
    def __init__(self, name: str, lo: float, hi: float) -> None:
        super().__init__(name)
        self.body = {"error": "SPIKE_BAD_PARAM", "param": name, "min": lo, "max": hi}


def _spike_num(q: Mapping[str, str], name: str, default: float | None, lo: float, hi: float) -> float:
    raw = q.get(name)
    if raw is None:
        if default is None:
            raise _SpikeBadParam(name, lo, hi)
        return default
    try:
        v = float(raw)
    except ValueError:
        raise _SpikeBadParam(name, lo, hi) from None
    if not math.isfinite(v) or v < lo or v > hi:
        raise _SpikeBadParam(name, lo, hi)
    return v


def _sse_event(name: str, seq: int, **extra: object) -> str:
    now = time.time()
    data = {"seq": seq, "server_epoch": now, "server_utc": datetime.fromtimestamp(now, timezone.utc).isoformat(), **extra}
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def make_spike_router(env: Mapping[str, str]) -> APIRouter | None:
    """None khi cờ tắt hoặc thiếu token — khi đó không có tuyến nào, mọi đường dẫn spike là 404 của đường dẫn lạ."""
    if env.get("BO19_SPIKE_PROBES") != "1":
        return None
    expected = env.get("BO19_SPIKE_TOKEN", "").encode("utf-8")
    if not expected:
        log.error("SPIKE_PROBES_NO_TOKEN cờ bật nhưng thiếu token — không gắn tuyến")
        return None

    def gate(request: Request) -> None:
        got = request.headers.get("x-bo19-spike-token", "").encode("utf-8", "replace")
        if not hmac.compare_digest(got, expected):
            raise HTTPException(status_code=404)  # cùng thân và header với đường dẫn lạ

    router = APIRouter(dependencies=[Depends(gate)])
    slot = {"until": 0.0}  # tối đa một kết nối thử đồng thời

    def take(seconds: float) -> bool:
        if time.monotonic() < slot["until"]:
            return False
        slot["until"] = time.monotonic() + seconds + SPIKE_SLOT_GRACE_S
        return True

    @router.get("/commit")
    async def commit() -> dict[str, object]:
        # Không giữ chỗ thử: để probe kiểm bản đang chạy trước và sau mỗi lần đo. boot_epoch đổi = tiến trình đã khởi động lại.
        return {
            "commit": env.get("RENDER_GIT_COMMIT"),
            "branch": env.get("RENDER_GIT_BRANCH"),
            "boot_epoch": SPIKE_BOOT_EPOCH,
            "server_epoch": time.time(),
        }

    @router.get("/sleep")
    async def sleep(request: Request) -> object:
        try:
            s = _spike_num(request.query_params, "s", None, 0.0, SPIKE_SLEEP_MAX_S)
        except _SpikeBadParam as e:
            return JSONResponse(e.body, status_code=400)
        if not take(s):
            return JSONResponse({"error": "SPIKE_BUSY"}, status_code=429)
        t0, m0, reason = time.time(), time.monotonic(), "completed"
        log.info("SPIKE_START kind=sleep s=%s", s)
        try:
            while (left := s - (time.monotonic() - m0)) > 0:
                await asyncio.sleep(min(SPIKE_STEP_S, left))
                if await request.is_disconnected():
                    reason = "client_gone"
                    break
        except asyncio.CancelledError:
            reason = "cancelled"
            raise
        finally:
            slot["until"] = 0.0
            log.info("SPIKE_END kind=sleep reason=%s elapsed=%.3f", reason, time.monotonic() - m0)
        return {"slept": s, "start_epoch": t0, "end_epoch": time.time()}

    @router.get("/sse")
    async def sse(request: Request) -> object:
        # interval: giây giữa hai nhịp, 0 = im lặng sau sự kiện đầu. max: số giây stream sống, tối đa SPIKE_SSE_MAX_S.
        # kind=event: mỗi nhịp là một event "tick"; kind=comment: mỗi nhịp là một dòng comment — nhịp giữ kết nối của mục 3.2 của 05-api.md.
        # accel=no: thêm header X-Accel-Buffering: no — chỉ dùng khi đã thấy gom đệm.
        q = request.query_params
        try:
            interval = _spike_num(q, "interval", 5.0, 0.0, SPIKE_SSE_MAX_S)
            if 0.0 < interval < 0.1:
                raise _SpikeBadParam("interval", 0.1, SPIKE_SSE_MAX_S)
            mx = _spike_num(q, "max", 600.0, 0.1, SPIKE_SSE_MAX_S)
            kind = q.get("kind", "event")
            if kind not in ("event", "comment"):
                raise _SpikeBadParam("kind", 0, 0)
        except _SpikeBadParam as e:
            return JSONResponse(e.body, status_code=400)
        if not take(mx):
            return JSONResponse({"error": "SPIKE_BUSY"}, status_code=429)
        headers = {"Cache-Control": "no-cache"}
        if q.get("accel") == "no":
            headers["X-Accel-Buffering"] = "no"

        async def stream():
            m0, reason, seq = time.monotonic(), "server_cap", 0
            log.info("SPIKE_START kind=sse interval=%s max=%s mode=%s", interval, mx, kind)
            try:
                yield _sse_event("open", 0, interval=interval, max=mx, kind=kind)  # ngay khi kết nối
                next_at = interval
                while (now := time.monotonic() - m0) < mx:
                    wait = min(SPIKE_STEP_S, mx - now)
                    if interval > 0:
                        wait = min(wait, max(next_at - now, 0.0))
                    await asyncio.sleep(wait)
                    if await request.is_disconnected():
                        reason = "client_gone"
                        return
                    if interval > 0 and time.monotonic() - m0 >= next_at:
                        seq, next_at = seq + 1, next_at + interval
                        if kind == "event":
                            yield _sse_event("tick", seq)
                        else:
                            yield f": hb seq={seq} server_epoch={time.time():.6f}\n\n"
                yield _sse_event("end", seq + 1, reason="server_cap")
            except asyncio.CancelledError:
                reason = "cancelled"
                raise
            finally:
                slot["until"] = 0.0
                log.info("SPIKE_END kind=sse reason=%s elapsed=%.3f ticks=%d", reason, time.monotonic() - m0, seq)

        return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)

    return router


def _mount_spike(app: FastAPI, env: Mapping[str, str]) -> None:
    router = make_spike_router(env)
    if router is not None:
        app.include_router(router, prefix="/api/_spike")
        log.info("SPIKE_PROBES_ON commit=%s", env.get("RENDER_GIT_COMMIT", "unknown"))


# ===== hết khối SPIKE S3 =====


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    port = _startup()
    if port is None:
        sys.exit(1)

    import uvicorn
    from fastapi import FastAPI

    app = FastAPI(title="bo19", docs_url=None, redoc_url=None, openapi_url=None)
    _mount_spike(app, os.environ)  # SPIKE S3 — gỡ ở bước 7

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        # Tiến trình chỉ phục vụ sau khi bước kiểm khởi động đạt; healthz chỉ báo "đang sống".
        return {"status": "ok"}

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
