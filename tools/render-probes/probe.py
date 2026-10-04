#!/usr/bin/env python3
"""S3 của Spike 1 — đo từ ngoài Render: proxy có gom đệm response SSE không (A-050), một request sống được bao lâu (A-025).

Chỉ thư viện chuẩn. Gọi các endpoint /api/_spike/* của api_main (khối SPIKE S3, gỡ sau S3).

Môi trường — không bao giờ in, không ghi ra file kết quả:
  BO19_SPIKE_BASE_URL   gốc URL của Web Service, ví dụ http://127.0.0.1:10000
  BO19_SPIKE_TOKEN      giá trị của header X-BO19-Spike-Token

Cách dùng:
  probe.py --spec run.json [--out DIR]
  probe.py --case sse-events --interval 5 --max 600 --enc none [--expect-commit SHA] [--accel-no] [--label L]
  probe.py --case sleep --s 60 --enc browser

Spec JSON: {"label": "...", "expect_commit": "<sha>" | null, "runs": [{"case": ..., "interval": ..., "max": ..., "s": ..., "enc": ..., "accel_no": ...}]}
  case: sse-events (mỗi nhịp là event có số thứ tự và giờ máy chủ) · sse-silent (một event đầu rồi im lặng) ·
        sse-comment (nhịp là dòng comment, như stream tín hiệu ở mục 3.2 của 05-api.md) · sleep (không byte nào tới khi đủ s giây)
  enc:  none = không gửi Accept-Encoding · browser = "Accept-Encoding: gzip, deflate, br"

Mỗi lượt đo ghi một file JSON vào out/<label>/: header response thực nhận, giao thức, thời điểm nhận từng chunk và từng event
(giây tính từ lúc gửi request, và giờ máy khách), so khoảng cách nhận với khoảng cách gửi, và cách kết thúc. Probe chỉ ghi số đo —
không kết luận "gom đệm" hay "cắt". Trước khi đo, probe hỏi /commit: sai commit thì dừng (mã 3), không đo.

Giới hạn của probe: http.client chỉ nói HTTP/1.1, không HTTP/2 như trình duyệt; stdlib không giải nén được `br` — gặp `br` thì vẫn
ghi thời điểm và cỡ từng chunk nhưng không đọc được nội dung event.

Gặp 429 (chỗ thử đang bị giữ) probe chờ rồi thử lại, ghi vào busy_retries; lần 429 không bao giờ là điểm dữ liệu.

Mã thoát: 0 xong · 2 spec hỏng hoặc tổng thời lượng vượt trần · 3 sai commit · 4 endpoint spike không mở (404) · 5 không nối được · 6 có lượt bỏ cuộc vì 429 (không có dữ liệu).
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import platform
import re
import ssl
import statistics
import sys
import time
import urllib.parse
import zlib
from datetime import datetime, timezone
from pathlib import Path

PREFIX = "/api/_spike"
UA = "bo19-render-probe/1"
BROWSER_AE = "gzip, deflate, br"
CASES = ("sse-events", "sse-silent", "sse-comment", "sleep")
HEARTBEAT = re.compile(r"^: hb seq=(\d+) server_epoch=([0-9.]+)")
MASK = "<render-host>"
# Repo công khai: log và file kết quả ai cũng xem được; GitHub chỉ che đúng nguyên chuỗi secret. Mọi chuỗi chứa
# "onrender.com" — kể cả không kèm https:// — và chính host của BO19_SPIKE_BASE_URL bị thay bằng MASK ở stdout, stderr, file kết quả.
HOST_RE = re.compile(r"[A-Za-z0-9._-]*onrender\.com", re.IGNORECASE)
# Header có thể mang host: không ghi nguyên văn giá trị, chỉ ghi tên kèm giá trị đã che.
RISKY_HEADERS = {"location", "content-location", "alt-svc", "link", "refresh", "set-cookie", "referer", "origin",
                 "access-control-allow-origin", "report-to", "nel"}
_host = ""  # host của Target — đặt trong main() ngay sau khi đọc môi trường
OVERHEAD_S = 60.0  # ước tính nối, kiểm commit hai lần, ghi file — chỉ để tính trần tổng thời lượng


def redact(text: str, host: str = "") -> str:
    """Thay host của Target và mọi chuỗi chứa onrender.com bằng MASK. Không đụng gì khác."""
    if host:
        text = re.sub(re.escape(host), MASK, text, flags=re.IGNORECASE)
    return HOST_RE.sub(MASK, text)


def header_row(name: str, value: str, host: str = "") -> list[str]:
    """Một header response thực nhận. Header rủi ro (hoặc x-render-*): chỉ ghi độ dài và có chứa host hay không."""
    red = redact(value, host)
    if name.lower() in RISKY_HEADERS or name.lower().startswith("x-render-"):
        return [name, f"<masked len={len(value)} contained_host={red != value}>"]
    return [name, red]


class RedactingStream:
    """Bọc stdout/stderr: che từng dòng đầy đủ trước khi ra — một host không bao giờ bị cắt đôi giữa hai lần write."""

    def __init__(self, raw) -> None:
        self.raw, self.buf = raw, ""

    def write(self, s: str) -> int:
        *lines, self.buf = (self.buf + s).split("\n")
        for line in lines:
            self.raw.write(redact(line, _host) + "\n")
        return len(s)

    def flush(self) -> None:
        if self.buf:
            self.raw.write(redact(self.buf, _host))
            self.buf = ""
        self.raw.flush()

    def __getattr__(self, name: str):
        return getattr(self.raw, name)


class Target:
    def __init__(self, base: str, token: str) -> None:
        u = urllib.parse.urlsplit(base)
        self.https = u.scheme == "https"
        self.host = u.hostname or ""
        self.port = u.port or (443 if self.https else 80)
        self.token = token

    def conn(self, timeout: float) -> http.client.HTTPConnection:
        if self.https:
            return http.client.HTTPSConnection(self.host, self.port, timeout=timeout, context=ssl.create_default_context())
        return http.client.HTTPConnection(self.host, self.port, timeout=timeout)

    def scrub(self, text: str) -> str:
        return redact(text, self.host)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def send(t: Target, conn: http.client.HTTPConnection, path: str, enc: str, sse: bool) -> list[list[str]]:
    """Gửi GET. enc=none thì tuyệt đối không có Accept-Encoding (http.client mặc định thêm `identity` nếu không chặn)."""
    conn.putrequest("GET", path, skip_accept_encoding=True)
    headers = [("User-Agent", UA), ("Accept", "text/event-stream" if sse else "application/json"), ("X-BO19-Spike-Token", t.token)]
    if enc == "browser":
        headers.append(("Accept-Encoding", BROWSER_AE))
    for k, v in headers:
        conn.putheader(k, v)
    conn.endheaders()
    return [[k, "<redacted>" if k == "X-BO19-Spike-Token" else v] for k, v in headers]


def get_commit(t: Target, timeout: float) -> tuple[int, dict | None, float, float]:
    conn = t.conn(timeout)
    try:
        conn.connect()
        t0 = time.time()
        send(t, conn, f"{PREFIX}/commit", "none", False)
        r = conn.getresponse()
        body = r.read()
        t1 = time.time()
        return r.status, (json.loads(body) if r.status == 200 else None), t0, t1
    finally:
        conn.close()


def decoder_for(content_encoding: str):
    ce = content_encoding.lower().strip()
    if ce in ("", "identity"):
        return None, True
    if ce in ("gzip", "x-gzip"):
        return zlib.decompressobj(zlib.MAX_WBITS | 16), True
    if ce == "deflate":
        return zlib.decompressobj(), True
    return None, False  # br, zstd, ...: stdlib không giải được


def parse_block(raw: bytes) -> dict:
    text = raw.decode("utf-8", "replace")
    if text.startswith(":"):
        m = HEARTBEAT.match(text)
        return {"type": "comment", "seq": int(m[1]), "server_epoch": float(m[2])} if m else {"type": "comment"}
    name, data = None, None
    for line in text.split("\n"):
        if line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data = line[5:].strip()
    try:
        d = json.loads(data) if data else {}
    except ValueError:
        d = {}
    return {"type": "event", "name": name, "seq": d.get("seq"), "server_epoch": d.get("server_epoch")}


def stat3(xs: list[float]) -> dict | None:
    return {"min": round(min(xs), 6), "median": round(statistics.median(xs), 6), "max": round(max(xs), 6)} if xs else None


def summarize(rec: dict) -> dict:
    # Khoảng cách chỉ tính giữa các event có nhịp: bỏ `end` — máy chủ phát nó sát event cuối, không theo nhịp.
    ev = [e for e in rec["events"] if e.get("server_epoch") is not None and e.get("name") != "end"]
    pairs = list(zip(ev, ev[1:]))
    recv = [b["t"] - a["t"] for a, b in pairs]
    sent = [b["server_epoch"] - a["server_epoch"] for a, b in pairs]
    lag = [e["wall"] - e["server_epoch"] for e in ev]  # gồm lệch đồng hồ hai máy; time.time() trên Windows thô ~15 ms
    return {
        "events": len(rec["events"]),
        "chunks": len(rec["chunks"]),
        "first_event_s": rec["events"][0]["t"] if rec["events"] else None,
        "recv_gap_s": stat3(recv),
        "send_gap_s": stat3(sent),
        "abs_gap_error_max_s": round(max((abs(r - s) for r, s in zip(recv, sent)), default=0.0), 6) if pairs else None,
        # cặp event liên tiếp, máy chủ gửi cách nhau ≥ 0.1 s mà nhận cách nhau < nửa khoảng đó — event tới dồn
        "bunched_pairs": sum(1 for r, s in zip(recv, sent) if s >= 0.1 and r < 0.5 * s),
        "lag_s": {"first": round(lag[0], 6), "median": round(statistics.median(lag), 6), "last": round(lag[-1], 6)} if lag else None,
    }


MIN_PAIRS_INTERRUPTED = 60  # lượt gián đoạn có ít cặp hơn mức này thì không áp ngưỡng — nửa số cặp của lượt 10 phút nhịp 5 s


class Journal:
    """JSONL, một dòng cho mỗi sự kiện của lượt đo, flush ngay: lượt chết giữa chừng vẫn giữ dữ liệu tới điểm chết.
    Mỗi dòng qua redact. Một lượt hoàn tất luôn có dòng type=end; thiếu nó là lượt gián đoạn."""

    def __init__(self, path: Path, host: str) -> None:
        self.f = open(path, "a", encoding="utf-8", newline="\n")
        self.host = host

    def write(self, obj: dict) -> None:
        self.f.write(redact(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), self.host) + "\n")
        self.f.flush()

    def close(self) -> None:
        self.f.close()


def pair_errors(events: list[dict]) -> list[float]:
    """recv_gap − send_gap của từng cặp event liên tiếp có nhịp (bỏ `end`)."""
    ev = [e for e in events if e.get("server_epoch") is not None and e.get("name") != "end"]
    return [(b["t"] - a["t"]) - (b["server_epoch"] - a["server_epoch"]) for a, b in zip(ev, ev[1:])]


def verdict(events: list[dict], interval: float, state: str) -> str:
    """Áp ngưỡng ở mục Ngưỡng kết luận gom đệm của README cho MỘT lượt. Chạy lại / lặp lại giữa các lượt do người đọc quyết."""
    errs = [abs(x) for x in pair_errors(events)]
    first = events[0]["t"] if events else None
    if first is None:
        return "không có event"
    if state == "interrupted" and len(errs) < MIN_PAIRS_INTERRUPTED:
        return f"gián đoạn — không áp ngưỡng ({len(errs)} cặp < {MIN_PAIRS_INTERRUPTED})"
    part = " [dữ liệu một phần: lượt gián đoạn]" if state == "interrupted" else ""
    big = sum(1 for e in errs if e >= 0.5 * interval)
    if first >= interval or big >= 2:
        return "có gom đệm" + part
    if big == 1:
        return "không kết luận — một cặp lệch ≥ 0.5·I đơn lẻ: chạy lại" + part
    if first <= 2.0 and all(e <= 0.1 * interval for e in errs):
        return "không thấy gom đệm" + part
    return "không kết luận" + part


def classify(rec: dict) -> str:
    """completed · cut · restart · cut_unverified · busy_gave_up. `restart` (boot_epoch đổi) KHÔNG phải điểm cắt."""
    if rec["ended"] in ("end_event", "completed"):
        return "completed"
    if rec["ended"] == "busy_gave_up":
        return "busy_gave_up"
    after = rec.get("after") or {}
    if "error" in after or after.get("status") != 200:
        return "cut_unverified"  # không hỏi lại được /commit nên không biết có restart hay không
    return "restart" if after.get("restarted") else "cut"


def read_journal(path: Path) -> dict:
    j: dict = {"start": None, "response": None, "events": [], "chunks": [], "end": None, "after": None, "final": None, "bad_lines": 0}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(line)
        except ValueError:  # dòng cuối bị cắt dở khi tiến trình chết
            j["bad_lines"] += 1
            continue
        ty = o.get("type")
        if ty == "start":  # một lần thử mới (sau 429) — bỏ dữ liệu của lần thử trước
            j.update(start=o, response=None, events=[], chunks=[], end=None, after=None, final=None)
        elif ty == "event":
            j["events"].append({"type": o.get("kind"), "name": o.get("name"), "seq": o.get("seq"),
                                "server_epoch": o.get("server_epoch"), "t": o["t"], "wall": o["wall"]})
        elif ty == "chunk":
            j["chunks"].append(o)
        elif ty in ("response", "end", "after", "final"):
            j[ty] = o
    return j


def summarize_journal(path: Path) -> dict:
    j = read_journal(path)
    state = "complete" if j["end"] else "interrupted"
    start = j["start"] or {}
    case = start.get("case")
    interval = (start.get("params") or {}).get("interval")
    out = {"file": path.name, "state": state, "case": case, "enc": start.get("enc"), "events": len(j["events"]), "pairs": len(pair_errors(j["events"])),
           "bad_lines": j["bad_lines"], "classification": (j["final"] or {}).get("classification") or ("gián đoạn" if state == "interrupted" else None),
           "last_event_t": j["events"][-1]["t"] if j["events"] else None, "summary": summarize({"events": j["events"], "chunks": j["chunks"]})}
    if case in ("sse-events", "sse-comment") and interval:
        out["verdict"] = verdict(j["events"], float(interval), state)
    else:
        out["verdict"] = "không áp ngưỡng gom đệm cho ca này"
    return out


def plan(run: dict) -> tuple[str, float, bool]:
    """(đường dẫn + query, thời lượng tối đa dự kiến theo giây, có phải SSE)."""
    case = run["case"]
    if case not in CASES:
        raise ValueError(f"case không hợp lệ: {case}")
    if run.get("enc", "none") not in ("none", "browser"):
        raise ValueError("enc phải là none hoặc browser")
    if case == "sleep":
        return f"{PREFIX}/sleep?s={run['s']}", float(run["s"]), False
    interval = 0 if case == "sse-silent" else run["interval"]
    q = f"interval={interval}&max={run['max']}"
    if case == "sse-comment":
        q += "&kind=comment"
    if run.get("accel_no"):
        q += "&accel=no"
    return f"{PREFIX}/sse?{q}", float(run["max"]), True


def attempt(t: Target, run: dict, idx: int, boot_before: float | None, j: Journal, n: int) -> dict:
    path, dur, sse = plan(run)
    enc = run.get("enc", "none")
    rec: dict = {
        "run": idx, "case": run["case"], "params": {k: v for k, v in run.items() if k not in ("case", "enc")}, "enc": enc,
        "started_utc": utc(), "events": [], "chunks": [], "boot_epoch_before": boot_before,
    }
    j.write({"type": "start", "attempt": n, "run": idx, "case": rec["case"], "params": rec["params"], "enc": enc,
             "started_utc": rec["started_utc"], "boot_epoch_before": boot_before})
    conn = t.conn(30)
    t_req = time.perf_counter()
    body = bytearray()
    last_data = t_req
    try:
        conn.connect()
        conn.sock.settimeout(dur + 90)  # đủ để chờ byte đầu của sleep và khoảng im lặng dài nhất
        rec["tls_version"] = conn.sock.version() if t.https else None
        t_req = time.perf_counter()
        rec["request_headers"] = send(t, conn, path, enc, sse)
        resp = conn.getresponse()
        rec["headers_s"] = round(time.perf_counter() - t_req, 6)
        rec["status"] = resp.status
        rec["http_version"] = {10: "HTTP/1.0", 11: "HTTP/1.1"}.get(resp.version, str(resp.version))
        rec["response_headers"] = [header_row(k, v, t.host) for k, v in resp.getheaders()]
        j.write({"type": "response", "status": rec["status"], "http_version": rec["http_version"], "headers": rec["response_headers"],
                 "tls_version": rec["tls_version"], "headers_s": rec["headers_s"], "wall": time.time()})
        if resp.status == 429:  # chỗ thử đang bị giữ — không phải điểm dữ liệu, measure() sẽ chờ rồi thử lại
            resp.read()
            rec["ended"] = "busy"
            return rec
        dec, decodable = decoder_for(resp.getheader("Content-Encoding", ""))
        rec["body_decodable"] = decodable
        buf = b""
        while True:
            chunk = resp.read1(65536)
            now = time.perf_counter()
            if not chunk:
                break
            last_data = now
            rec["chunks"].append({"t": round(now - t_req, 6), "bytes": len(chunk)})
            j.write({"type": "chunk", "t": round(now - t_req, 6), "bytes": len(chunk), "wall": time.time()})
            data = dec.decompress(chunk) if dec else chunk
            if not decodable:
                continue
            if not sse:
                body += data
                continue
            buf += data
            while b"\n\n" in buf:
                raw, buf = buf.split(b"\n\n", 1)
                e = parse_block(raw)
                e.update({"t": round(now - t_req, 6), "wall": time.time()})
                rec["events"].append(e)
                j.write({"type": "event", "kind": e["type"], "name": e.get("name"), "seq": e.get("seq"),
                         "server_epoch": e.get("server_epoch"), "t": e["t"], "wall": e["wall"]})
                print(f"[run {idx}] t={e['t']:9.3f}s {e.get('name') or e['type']} seq={e.get('seq')}", flush=True)
        names = [e.get("name") for e in rec["events"]]
        if not sse:
            try:
                rec["body"] = json.loads(bytes(body)) if body else None
            except ValueError:
                rec["body"] = None
            rec["ended"] = "completed" if rec["status"] == 200 and rec["body"] else "eof_without_body"
        else:
            rec["ended"] = "end_event" if "end" in names else "eof_without_end_event"
    except Exception as e:  # noqa: BLE001 — mọi lỗi mạng đều là số đo
        rec["ended"] = "error"
        rec["error"] = {"type": type(e).__name__, "message": t.scrub(str(e))[:300]}
    finally:
        end = time.perf_counter()
        rec["elapsed_s"] = round(end - t_req, 6)
        rec["since_last_data_s"] = round(end - last_data, 6)
        conn.close()
        j.write({"type": "end", "ended": rec.get("ended"), "elapsed_s": rec["elapsed_s"], "since_last_data_s": rec["since_last_data_s"],
                 "error": rec.get("error"), "wall": time.time()})
    rec["summary"] = summarize(rec)
    # sau mỗi lượt: bản đang chạy còn đúng không, tiến trình có khởi động lại không (boot_epoch đổi). Có thể đánh thức service đang ngủ.
    try:
        st, c, _, _ = get_commit(t, 150)
        rec["after"] = {"status": st, "commit": c and c.get("commit"), "boot_epoch": c and c.get("boot_epoch"),
                        "restarted": bool(c and boot_before is not None and c.get("boot_epoch") != boot_before)}
    except Exception as e:  # noqa: BLE001
        rec["after"] = {"error": {"type": type(e).__name__, "message": t.scrub(str(e))[:300]}}
    j.write({"type": "after", **rec["after"], "wall": time.time()})
    return rec


def measure(t: Target, run: dict, idx: int, boot_before: float | None, busy_wait_s: float, j: Journal) -> dict:
    """Một lượt đo. Gặp 429 thì chờ 10 s rồi thử lại tới busy_wait_s; mỗi lần chờ ghi vào busy_retries, không phải điểm dữ liệu."""
    retries: list[dict] = []
    t0 = time.perf_counter()
    while True:
        rec = attempt(t, run, idx, boot_before, j, len(retries) + 1)
        if rec["ended"] != "busy":
            break
        waited = time.perf_counter() - t0
        retries.append({"utc": utc(), "waited_s": round(waited, 3)})
        print(f"[run {idx}] 429 SPIKE_BUSY — đã chờ {waited:.0f} s; không tính là điểm dữ liệu", flush=True)
        if waited + 10 > busy_wait_s:
            rec["ended"] = "busy_gave_up"
            rec["summary"] = summarize(rec)
            break
        time.sleep(10)
    rec["busy_retries"] = retries
    rec["classification"] = classify(rec)
    iv = (rec["params"] or {}).get("interval")
    rec["verdict"] = verdict(rec["events"], float(iv), "complete") if rec["case"] in ("sse-events", "sse-comment") and iv else None
    j.write({"type": "final", "classification": rec["classification"], "verdict": rec["verdict"], "summary": rec["summary"]})
    return rec


def main() -> int:
    global _host
    for name in ("stdout", "stderr"):  # trước mọi thứ khác: mọi dòng ra đều qua redact
        stream = getattr(sys, name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
        setattr(sys, name, RedactingStream(stream))
    ap = argparse.ArgumentParser(description="S3 của Spike 1 — đo từ ngoài Render")
    ap.add_argument("--spec")
    ap.add_argument("--case", choices=CASES)
    ap.add_argument("--interval", type=float)
    ap.add_argument("--max", type=float)
    ap.add_argument("--s", type=float)
    ap.add_argument("--enc", default="none", choices=("none", "browser"))
    ap.add_argument("--accel-no", action="store_true")
    ap.add_argument("--expect-commit")
    ap.add_argument("--label", default="manual")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "out"))
    ap.add_argument("--busy-wait-s", type=float, default=120.0, help="gặp 429 thì chờ tối đa chừng này giây (thử lại mỗi 10 s)")
    ap.add_argument("--emit", action="store_true", help="in mỗi kết quả thành một dòng RESULT_JSON — cho log của CI")
    ap.add_argument("--summarize", metavar="PATH", help="đọc file .jsonl (hoặc thư mục có .jsonl), in trạng thái hoàn tất/gián đoạn và kết luận theo ngưỡng; không nối mạng")
    ap.add_argument("--max-total-minutes", type=float, default=330.0, help="trần tổng thời lượng một lần chạy; job của GitHub-hosted tối đa 360 phút")
    a = ap.parse_args()

    if a.summarize:
        p = Path(a.summarize)
        for f in sorted(p.glob("*.jsonl")) if p.is_dir() else [p]:
            print(json.dumps(summarize_journal(f), ensure_ascii=False))
        return 0

    if a.spec:
        spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    elif a.case:
        run = {"case": a.case, "enc": a.enc, **{k: v for k, v in (("interval", a.interval), ("max", a.max), ("s", a.s)) if v is not None}}
        if a.accel_no:
            run["accel_no"] = True
        spec = {"label": a.label, "expect_commit": a.expect_commit, "runs": [run]}
    else:
        ap.error("cần --spec hoặc --case")
    try:
        total = sum(plan(r)[1] + OVERHEAD_S for r in spec["runs"])
    except (KeyError, ValueError) as e:
        print(f"SPEC_INVALID {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    if total > a.max_total_minutes * 60:
        print(f"SPEC_TOO_LONG ước tính {total / 60:.1f} phút > trần {a.max_total_minutes} phút — chia thành nhiều lượt", file=sys.stderr)
        return 2

    base, token = os.environ.get("BO19_SPIKE_BASE_URL", ""), os.environ.get("BO19_SPIKE_TOKEN", "")
    if not base or not token:
        print("THIẾU BO19_SPIKE_BASE_URL hoặc BO19_SPIKE_TOKEN", file=sys.stderr)
        return 2
    t = Target(base, token)
    _host = t.host
    label = re.sub(r"[^A-Za-z0-9._-]", "_", str(spec.get("label", "run")))
    out = Path(a.out) / label
    out.mkdir(parents=True, exist_ok=True)

    try:
        status, info, t0, t1 = get_commit(t, 150)
    except Exception as e:  # noqa: BLE001
        print(f"KHÔNG_NỐI_ĐƯỢC {type(e).__name__}: {t.scrub(str(e))[:200]}", file=sys.stderr)
        return 5
    if status != 200 or info is None:
        print(f"SPIKE_NOT_ENABLED status={status}", file=sys.stderr)
        return 4
    expect = spec.get("expect_commit")
    got = info.get("commit") or ""
    if expect and not (got and got.startswith(expect)):
        print(f"COMMIT_MISMATCH mong {expect[:12]} · máy chủ {got[:12] or '(không có)'} — dừng, không đo", file=sys.stderr)
        return 3
    boot = info.get("boot_epoch")
    meta = {
        "label": label, "started_utc": utc(), "client": os.environ.get("BO19_PROBE_CLIENT") or ("github-actions" if os.environ.get("GITHUB_ACTIONS") else "local"),
        "python": platform.python_version(), "platform": platform.platform(), "scheme": "https" if t.https else "http",
        "commit": got or None, "branch": info.get("branch"), "commit_checked": bool(expect), "boot_epoch": boot,
        "clock_skew_estimate_s": round(info["server_epoch"] - (t0 + t1) / 2, 6), "commit_rtt_s": round(t1 - t0, 6),
    }
    print(f"commit={got[:12] or '(không có)'} branch={meta['branch']} kiểm_commit={meta['commit_checked']} client={meta['client']} runs={len(spec['runs'])} python={meta['python']} boot_epoch={boot}", flush=True)

    rc = 0
    for i, run in enumerate(spec["runs"], 1):
        stem = f"{i:02d}-{run['case']}-{run.get('enc', 'none')}"
        j = Journal(out / f"{stem}.jsonl", t.host)
        j.write({"type": "meta", **meta})
        try:
            rec = measure(t, run, i, boot, a.busy_wait_s, j)
        finally:
            j.close()
        rec["meta"] = meta
        f = out / f"{stem}.json"
        f.write_text(redact(json.dumps(rec, indent=1, ensure_ascii=False), t.host), encoding="utf-8")
        if a.emit:
            print("RESULT_JSON " + json.dumps(rec, separators=(",", ":"), ensure_ascii=False), flush=True)
        s = rec["summary"]
        print(f"[run {i}] {rec['case']} enc={rec['enc']} status={rec.get('status')} ended={rec['ended']} elapsed={rec['elapsed_s']}s "
              f"events={s['events']} chunks={s['chunks']} bunched={s['bunched_pairs']} restarted={rec.get('after', {}).get('restarted')} "
              f"class={rec['classification']} verdict={rec['verdict']} -> {f.name}", flush=True)
        boot = (rec.get("after") or {}).get("boot_epoch") or boot
        if rec["ended"] == "busy_gave_up":
            rc = 6  # lượt này không có dữ liệu; các lượt sau vẫn chạy
    return rc


if __name__ == "__main__":
    sys.exit(main())
