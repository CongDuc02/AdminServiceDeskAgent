#!/usr/bin/env python3
"""Phép đo từ xa `combined_main` trên Render bằng tài khoản giả có thời hạn (O1-6, A-095; ngoại lệ cổng 2.7, PO 2026-10-21; `docs/design/11-ops.md` mục 20, bước 4 và 4b).

KHÔNG phải mã ứng dụng, không vào image. Chạy ở máy người triển khai (chỉ cần `httpx`), **sau** khi PO chạy `render_probe_accounts.py seed`.
Mật khẩu đọc từ `tools/render-probes/out/probe_passwords.txt` (ghi bởi `seed`) — không in, không ghi vào kết quả; cookie phiên cũng không in.
Kết quả mỗi lần chạy: một dòng JSON mỗi phép đo ở `tools/render-probes/out/measure-<UTC>.jsonl` và tóm tắt in ra.

Lệnh con:
  health        chờ `GET /healthz` = 200, in số giây (đánh thức sau ngủ, hoặc sau deploy)
  login-burst   N lần `POST /auth/session` ĐỒNG THỜI (mặc định 4 = trần WV-16b của argon2id đồng thời) — thời gian từng lần và mã trạng thái.
                Mỗi lần tính vào ngưỡng 20 lần đăng nhập / 15 phút dùng chung của cả hệ thống (A-062): công cụ dừng ngay khi gặp `RATE_LIMITED`
  turns         N lượt chat tuần tự (mỗi lượt một phiên chat mới): thời gian từ lúc gửi `POST …/turns` tới `turn.reply`. Ngưỡng của runbook: lớn nhất ≤ 15 s
                (WV-02 − 5 s) khi `soffice` đang chạy; lượt KHÔNG có `soffice` chạy là số tham chiếu (baseline)

  job-window    MỘT request thật từ chat tới `submit` (job `render_document` vào hàng đợi, `soffice` chạy trên instance), rồi `--turns-during` lượt chat đo NGAY trong lúc đó.
                Mỗi lượt ghi thời điểm bắt đầu/kết thúc so với lúc `submit` và so với lúc request/văn bản đổi trạng thái (≈ job render xong) → `overlaps_job`.
                **Nói thẳng:** công cụ không nhìn thấy `soffice` — "trong lúc job chạy" là khoảng [submit, văn bản đổi trạng thái], cận trên của khoảng `soffice` thật (gồm cả chờ hàng đợi);
                đối chiếu với log Render (`render_document` bắt đầu/xong) khi đọc kết quả. Cần template `ACTIVE` (`render_probe_template.py install`)

**Trần lời gọi Groq cho cả phép đo: 28 (PO, 2026-10-22; trước đó 20).** Mỗi lượt gọi LLM ít nhất `classify_intent` và `extract_slots` (hai lời gọi; có thể nhiều hơn khi sửa/ thử lại). Công cụ đếm số LƯỢT đã chạy ở `out/probe_budget.json`
và từ chối quá 14 lượt (≈ 28 lời gọi). Kế hoạch: 2 lượt baseline + 6 cửa sổ job × (1 dựng request + 1 đo) = 14 → n = 6 lượt chat khi `soffice` chạy. **Số thật** đo bằng `render_probe_accounts.py usage` (đếm `llm_usage` từ lúc seed) — PO chạy sau mỗi lần.

Chặn: không có cửa sổ (`probe_window.json`), cửa sổ đã thu hồi hoặc hết hạn → từ chối. Chỉ đo lên URL do `--url` khai (HTTPS).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("PROBE_OUT", str(REPO / "tools" / "render-probes" / "out")))
API = "/api/v1"
CSRF = {"X-BO19-CSRF": "1"}
TEXT = "xin giấy xác nhận công tác gửi Công ty ABC, mục đích bổ sung hồ sơ vay vốn"
MAX_TURNS_TOTAL = 14  # PO 2026-10-22: trần 28 lời gọi Groq cho cả phép đo (≈ 2 mỗi lượt) để đủ n = 6 lượt chat khi `soffice` chạy; dừng và báo nếu `usage` cho thấy > 2 lời gọi mỗi lượt
DONE_EVENTS = ("turn.reply", "turn.error", "turn.abandoned")


class Refused(Exception):
    """Mã từ chối, không chứa URL hay giá trị."""


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def load_window(out: Path, at: dt.datetime) -> dict:
    p = out / "probe_window.json"
    if not p.exists():
        raise Refused("MEASURE_NO_WINDOW")
    w = json.loads(p.read_text(encoding="utf-8"))
    if w.get("torn_down_at"):
        raise Refused("MEASURE_WINDOW_TORN_DOWN")
    if dt.datetime.fromisoformat(w["expires_at"]) < at:
        raise Refused("MEASURE_WINDOW_EXPIRED")
    return w


def password_of(out: Path, code: str) -> str:
    p = out / "probe_passwords.txt"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            c, _, secret = line.partition("\t")
            if c == code and secret:
                return secret
    raise Refused("MEASURE_NO_PASSWORD")


def login(client: httpx.Client, code: str, password: str) -> tuple[httpx.Response, float]:
    t0 = time.monotonic()
    r = client.post(f"{API}/auth/session", headers=CSRF, json={"employee_code": code, "password": password})
    return r, time.monotonic() - t0


def cookie_of(r: httpx.Response) -> str:
    return r.headers.get("set-cookie", "").split(";")[0]


def record(out: Path, stamp: str, obj: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / f"measure-{stamp}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def health(url: str, timeout: float, *, echo=print) -> dict:
    t0, last = time.monotonic(), None
    with httpx.Client(base_url=url, timeout=10) as client:
        while time.monotonic() - t0 < timeout:
            try:
                if client.get("/healthz").status_code == 200:
                    res = {"measure": "health", "healthz_after_s": round(time.monotonic() - t0, 1)}
                    echo(json.dumps(res))
                    return res
            except httpx.HTTPError as e:
                last = type(e).__name__
            time.sleep(1)
    res = {"measure": "health", "healthz_after_s": None, "last_error": last}
    echo(json.dumps(res))
    return res


def login_burst(url: str, account: str, n: int, *, out: Path = OUT, stamp: str = "", at: dt.datetime | None = None, echo=print) -> dict:
    load_window(out, at or now())
    password = password_of(out, account)

    def one(_i: int) -> dict:
        with httpx.Client(base_url=url, timeout=30) as client:
            r, secs = login(client, account, password)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return {"status": r.status_code, "ms": round(secs * 1000), "error_code": body.get("error_code")}

    with cf.ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(one, range(n)))
    res = {"measure": "login_burst", "n": n, "results": results, "all_ok": all(200 <= r["status"] < 300 for r in results), "max_ms": max(r["ms"] for r in results),
           "rate_limited": any(r["error_code"] == "RATE_LIMITED" for r in results)}
    record(out, stamp or now().strftime("%Y%m%dT%H%M%SZ"), res)
    echo(json.dumps(res))
    return res


def read_budget(out: Path) -> dict:
    p = out / "probe_budget.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"turns_done": 0}


def turns(url: str, account: str, n: int, *, label: str = "", pause_s: float = 8.0, max_total: int = MAX_TURNS_TOTAL, out: Path = OUT, stamp: str = "",
          at: dt.datetime | None = None, echo=print, sleep=time.sleep) -> dict:
    load_window(out, at or now())
    budget = read_budget(out)
    if budget["turns_done"] + n > max_total:
        raise Refused("MEASURE_LLM_BUDGET")  # trần 20 lời gọi Groq cho cả phép đo (≈ 2 lời gọi mỗi lượt)
    password = password_of(out, account)
    stamp = stamp or now().strftime("%Y%m%dT%H%M%SZ")
    rows: list[dict] = []
    with httpx.Client(base_url=url, timeout=httpx.Timeout(60, connect=15)) as client:
        r, _ = login(client, account, password)
        if not r.is_success:  # đăng nhập thành công là 204 No Content (openapi, POST /auth/session)
            raise Refused("MEASURE_LOGIN_FAILED_" + str(r.status_code))
        headers = {"Cookie": cookie_of(r), **CSRF}
        for i in range(n):
            s = client.post(f"{API}/chat-sessions", headers={**headers, "Idempotency-Key": str(uuid.uuid4())})
            body = s.json()
            session_id = body.get("id") or body.get("chat_session_id")
            t1 = time.monotonic()
            events: list[tuple[str, float]] = []
            status = None
            with client.stream("POST", f"{API}/chat-sessions/{session_id}/turns", headers={**headers, "Idempotency-Key": str(uuid.uuid4()), "Accept": "text/event-stream"}, json={"text": TEXT}) as resp:
                status = resp.status_code
                for line in resp.iter_lines():
                    if line.startswith("event:"):
                        events.append((line[6:].strip(), time.monotonic() - t1))
                        if events[-1][0] in DONE_EVENTS:
                            break
            reply = next((t for name, t in events if name == "turn.reply"), None)
            row = {"measure": "turn", "label": label, "i": i + 1, "http_status": status, "turn_s": None if reply is None else round(reply, 2), "events": [(nm, round(t, 2)) for nm, t in events]}
            rows.append(row)
            record(out, stamp, row)
            budget["turns_done"] += 1
            (out / "probe_budget.json").write_text(json.dumps(budget), encoding="utf-8")  # ghi sau MỖI lượt: dừng giữa chừng vẫn đếm đúng
            echo(json.dumps(row))
            if i + 1 < n:
                sleep(pause_s)  # gói Free của Groq giới hạn token mỗi phút
    ok = [r["turn_s"] for r in rows if r["turn_s"] is not None]
    summary = {"measure": "turns_summary", "label": label, "n": n, "replies": len(ok), "max_s": max(ok) if ok else None, "median_s": sorted(ok)[len(ok) // 2] if ok else None,
               "within_15s": bool(ok) and len(ok) == n and max(ok) <= 15.0, "turns_done_total": budget["turns_done"]}
    record(out, stamp, summary)
    echo(json.dumps(summary))
    return summary


def stream_turn(client: httpx.Client, headers: dict, session_id: str, text: str) -> tuple[list[tuple[str, float]], dict | None, int, float]:
    """Một lượt: (sự kiện với giờ tương đối, dữ liệu `turn.reply`, mã HTTP, giờ bắt đầu monotonic)."""
    t1 = time.monotonic()
    events: list[tuple[str, float]] = []
    reply: dict | None = None
    with client.stream("POST", f"{API}/chat-sessions/{session_id}/turns", headers={**headers, "Idempotency-Key": str(uuid.uuid4()), "Accept": "text/event-stream"}, json={"text": text}) as resp:
        status, name = resp.status_code, ""
        for line in resp.iter_lines():
            if line.startswith("event:"):
                name = line[6:].strip()
                events.append((name, time.monotonic() - t1))
                if name in DONE_EVENTS and name != "turn.reply":
                    break
            elif line.startswith("data:") and name == "turn.reply":
                try:
                    reply = json.loads(line[5:].strip())
                except ValueError:
                    reply = None
                break
    return events, reply, status, t1


def _job_done(entry: dict) -> bool:
    return bool(entry["documents"] and entry["documents"][0] != "DRAFT") or entry["request"] == "IN_REVIEW"


def job_window(url: str, account: str, turns_during: int, *, concurrent_logins: int = 0, label: str = "soffice", wait_s: float = 90.0, doc_wait_s: float = 15.0, max_total: int = MAX_TURNS_TOTAL, out: Path = OUT, stamp: str = "",
               at: dt.datetime | None = None, echo=print, sleep=time.sleep) -> dict:
    import threading

    load_window(out, at or now())
    budget = read_budget(out)
    if budget["turns_done"] + 1 + turns_during > max_total:  # một lượt dựng request + các lượt đo
        raise Refused("MEASURE_LLM_BUDGET")
    password = password_of(out, account)
    stamp = stamp or now().strftime("%Y%m%dT%H%M%SZ")
    timeline: list[dict] = []
    stop = threading.Event()
    with httpx.Client(base_url=url, timeout=httpx.Timeout(60, connect=15)) as client:
        r, _ = login(client, account, password)
        if not r.is_success:  # đăng nhập thành công là 204 No Content (openapi, POST /auth/session)
            raise Refused("MEASURE_LOGIN_FAILED_" + str(r.status_code))
        headers = {"Cookie": cookie_of(r), **CSRF}

        def new_session() -> str:
            body = client.post(f"{API}/chat-sessions", headers={**headers, "Idempotency-Key": str(uuid.uuid4())}).json()
            return body.get("id") or body.get("chat_session_id")

        def spend() -> None:
            budget["turns_done"] += 1
            (out / "probe_budget.json").write_text(json.dumps(budget), encoding="utf-8")  # ghi sau MỖI lượt

        events, reply, status, _ = stream_turn(client, headers, new_session(), TEXT)
        spend()
        builder_s = next((round(t, 2) for n, t in events if n == "turn.reply"), None)
        rid = ((reply or {}).get("active_request") or {}).get("id")
        if not rid:
            raise Refused("MEASURE_NO_ACTIVE_REQUEST")  # lượt dựng request không ra request (có thể agent hỏi lại): dừng, không tự thêm lượt
        detail = client.get(f"{API}/requests/{rid}", headers=headers).json()
        proposed = [{"slot_name": x["slot_name"], "expected_row_version": x["row_version"]} for x in detail.get("slots", []) if x.get("value_status") == "PROPOSED" and x.get("row_version") is not None]
        if proposed:
            detail = client.post(f"{API}/requests/{rid}/actions/confirm-slots", headers=headers, json={"confirmations": proposed}).json()
        if not detail.get("submit_ready"):
            raise Refused("MEASURE_NOT_SUBMIT_READY")
        t_submit = time.monotonic()
        sub = client.post(f"{API}/requests/{rid}/actions/submit", headers={**headers, "Idempotency-Key": str(uuid.uuid4())}, json={"expected_row_version": detail["row_version"]})
        if sub.status_code >= 400:
            raise Refused("MEASURE_SUBMIT_FAILED_" + str(sub.status_code))

        def watch() -> None:
            last = None
            while not stop.is_set():
                try:
                    d = client.get(f"{API}/requests/{rid}", headers=headers).json()
                    state = (d.get("status"), tuple(x.get("status") for x in d.get("documents", [])))
                    if state != last:
                        timeline.append({"t": round(time.monotonic() - t_submit, 2), "request": state[0], "documents": list(state[1])})
                        last = state
                except (httpx.HTTPError, ValueError):
                    pass
                stop.wait(1.0)

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        # Lần đo đầu (2026-10-22) bắt đầu 0,7 s sau `submit` và xong lúc 1,3 s — TRƯỚC khi `document` có dòng (≈ 2 s) nên không trùng job. Nay đợi tới khi văn bản xuất hiện (job đã vào hàng đợi) rồi mới đo.
        t_wait = time.monotonic()
        while time.monotonic() - t_wait < doc_wait_s and not any(e["documents"] for e in timeline):
            time.sleep(0.2)
        logins: dict | None = None
        if concurrent_logins:  # bước 4b: N đăng nhập argon2id ĐỒNG THỜI ngay khi job đã vào hàng đợi (trần WV-16b = 4); mỗi lần tính vào ngưỡng 20/15 phút
            def one(_i: int) -> dict:
                with httpx.Client(base_url=url, timeout=30) as other:
                    resp, secs = login(other, account, password)
                body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                return {"status": resp.status_code, "ms": round(secs * 1000), "error_code": body.get("error_code")}

            t_login = time.monotonic()
            with cf.ThreadPoolExecutor(max_workers=concurrent_logins) as pool:
                results = list(pool.map(one, range(concurrent_logins)))
            logins = {"n": concurrent_logins, "start_after_submit_s": round(t_login - t_submit, 2), "results": results, "all_ok": all(200 <= r["status"] < 300 for r in results),
                      "max_ms": max(r["ms"] for r in results), "rate_limited": any(r["error_code"] == "RATE_LIMITED" for r in results)}
        rows = []
        for i in range(turns_during):
            events, reply, status, t1 = stream_turn(client, headers, new_session(), TEXT)
            spend()
            done = next((t for n, t in events if n == "turn.reply"), None)
            start_rel = t1 - t_submit
            rows.append({"i": i + 1, "http_status": status, "turn_s": None if done is None else round(done, 2), "start_after_submit_s": round(start_rel, 2),
                         "end_after_submit_s": round(start_rel + (events[-1][1] if events else 0), 2)})
            if i + 1 < turns_during:
                sleep(0.5)  # các lượt đo nằm trong cùng cửa sổ `soffice` (≈ 13 s): không nghỉ dài giữa chúng
        t_end = time.monotonic()
        while time.monotonic() - t_end < wait_s and not any(_job_done(e) for e in timeline):
            time.sleep(1)
        stop.set()
        watcher.join(timeout=5)
    changed = next((e["t"] for e in timeline if _job_done(e)), None)
    doc_at = next((e["t"] for e in timeline if e["documents"]), None)  # văn bản có dòng ≈ job `render_document` vào hàng đợi
    for row in rows:
        # trùng khoảng [văn bản xuất hiện, job xong]: lượt nào kết thúc trước khi văn bản xuất hiện, hay bắt đầu sau khi job xong, thì KHÔNG tính là "khi soffice chạy"
        row["overlaps_job"] = (doc_at is not None and row["end_after_submit_s"] > doc_at) and (changed is None or row["start_after_submit_s"] < changed)
    res = {"measure": "job_window", "label": label, "concurrent_logins": logins, "request_status_timeline": timeline, "job_visible_after_submit_s": doc_at, "job_done_after_submit_s": changed, "turns": rows, "builder_turn_s": builder_s,
           "turns_done_total": budget["turns_done"]}
    record(out, stamp, res)
    echo(json.dumps(res))
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("health", "login-burst", "turns", "job-window"):
        p = sub.add_parser(name)
        p.add_argument("--url", required=True, help="https://<service>.onrender.com")
        if name == "health":
            p.add_argument("--timeout", type=float, default=180)
        else:
            p.add_argument("--account", default="DO-0001")
            p.add_argument("--n", type=int, default=4 if name == "login-burst" else 6)
        if name == "job-window":
            p.add_argument("--turns-during", type=int, default=2, help="số lượt chat đo ngay sau submit")
            p.add_argument("--concurrent-logins", type=int, default=0, help="bước 4b: số đăng nhập đồng thời trong lúc job chạy (4 = trần argon2id đồng thời)")
        if name == "turns":
            p.add_argument("--label", default="", help="baseline (không soffice) hoặc soffice")
            p.add_argument("--pause", type=float, default=8.0)
    a = ap.parse_args()
    if not a.url.startswith("https://"):
        print("MEASURE_REFUSED MEASURE_URL_NOT_HTTPS", file=sys.stderr)
        return 1
    try:
        if a.cmd == "health":
            return 0 if health(a.url, a.timeout)["healthz_after_s"] is not None else 1
        if a.cmd == "login-burst":
            login_burst(a.url, a.account, a.n)
        elif a.cmd == "job-window":
            job_window(a.url, a.account, a.turns_during, concurrent_logins=a.concurrent_logins)
        else:
            turns(a.url, a.account, a.n, label=a.label, pause_s=a.pause)
    except Refused as e:
        print(f"MEASURE_REFUSED {e}", file=sys.stderr)
        return 1
    except httpx.HTTPError as e:
        print(f"MEASURE_HTTP_ERROR {type(e).__name__}", file=sys.stderr)  # chỉ tên lớp lỗi
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
