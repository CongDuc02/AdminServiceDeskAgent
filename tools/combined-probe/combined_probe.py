#!/usr/bin/env python3
"""Phía container của phép đo `combined_main` (B9a2, O1-6, A-095) — KHÔNG phải mã ứng dụng, không vào image runtime.

Chạy trong image `bo19-test` (có `soffice`, `openssl`, phụ thuộc của backend) trên network `ci`, do `run_probe.py` điều phối. Mọi dữ liệu là dữ liệu GIẢ (A-080); không có lời gọi Groq nào — provider LLM là
một máy chủ HTTPS giả (`llm`) trả P1/P2 hợp schema sau một độ trễ cố định (mặc định 2 s — PO 2026-10-16), nên `combined_main` chạy đúng đường thật của nó (httpx → TLS → provider), chỉ khác nội dung.

Lệnh con:
  setup   dựng DB tạm (migrate + seed năm nhân viên giả), bucket tạm, mẫu `.docx` giả KHÔNG có biến nội dung tự do (job render không gọi LLM), chứng chỉ TLS tự ký; ghi /out/probe.env và /out/state.json
  llm     máy chủ HTTPS giả (chạy tới khi bị dừng)
  health  chờ GET /healthz = 200
  turn    một lượt chat qua API thật: đăng nhập → mở phiên → POST …/turns (SSE) → đo tới `turn.reply`
  submit  dựng một request đủ điều kiện và gửi (job `render_document` vào hàng đợi); in request_id
  job     trạng thái job của một request
  cleanup xoá DB và bucket tạm
Credential chỉ qua biến môi trường / file env trong /out (thư mục `tools/combined-probe/out/` nằm trong .gitignore).
"""
from __future__ import annotations

import argparse
import http.server
import importlib.util
import io
import json
import os
import secrets
import ssl
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "src"))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, mod)
    spec.loader.exec_module(mod)
    return mod


OUT = Path(os.environ.get("PROBE_OUT", "/out"))
HOST_LLM = "llm.probe.test"
LLM_PORT = 8443
TEXT = "xin giấy xác nhận công tác gửi Công ty ABC, mục đích bổ sung hồ sơ vay vốn"
RECIPIENT, PURPOSE = "Công ty ABC", "bổ sung hồ sơ vay vốn"
LLM_DELAY_S = float(os.environ.get("PROBE_LLM_DELAY_S", "2.0"))
USAGE = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150, "prompt_time": 0.01, "completion_time": 0.2, "completion_tokens_details": {"reasoning_tokens": 12}}


def state() -> dict:
    return json.loads((OUT / "state.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------------------------- setup

def template_docx() -> bytes:
    from docx import Document
    doc = Document()
    for style in ("Normal", "Header", "Footer"):
        doc.styles[style].font.name = "Times New Roman"
    for text in ("MẪU GIẢ — chỉ để thử, không phải mẫu của tổ chức", "{{ full_name }} — {{ department_name }} — {{ job_title }}", "Kính gửi: {{ recipient_org }}",
                 "Số: {{ document_number }} ngày {{ issued_date }} — người ký {{ signer_user_id }}"):
        doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


NO_FREE = (("full_name", "DIRECT_SLOT", "full_name", False), ("department_name", "DIRECT_SLOT", "department_name", False), ("job_title", "DIRECT_SLOT", "job_title", False),
           ("recipient_org", "DIRECT_SLOT", "recipient_org", False), ("document_number", "SYSTEM", None, True), ("issued_date", "SYSTEM", None, True), ("signer_user_id", "SYSTEM", None, True))


def setup(admin_dsn: str) -> None:
    import boto3
    from botocore.config import Config
    from bo19.persistence.pool import Pool
    from bo19.tool_layer import storage as store

    tt = _load("turn_trial", "tools/turn-trial/turn_trial.py")
    seed = _load("seed_dev", "tools/seed-dev/seed_dev.py")
    OUT.mkdir(parents=True, exist_ok=True)
    s3 = {"endpoint": os.environ["BO19_TEST_S3_ENDPOINT"], "key": os.environ["BO19_TEST_S3_ACCESS_KEY_ID"], "secret": os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"]}
    db = tt.TrialDb(admin_dsn)
    seed.run(db.dsn("bo19_migrator"), OUT / "passwords.local.txt", allow_hosts=frozenset({"pg"}))
    bucket = f"bo19-probe-{uuid.uuid4().hex[:10]}"
    boto3.client("s3", endpoint_url=s3["endpoint"], region_name="us-east-1", aws_access_key_id=s3["key"], aws_secret_access_key=s3["secret"],
                 config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 1})).create_bucket(Bucket=bucket)
    pool = Pool(db.dsn("bo19_app"), application_name="bo19-probe-setup", min_size=1, max_size=2)
    pool.open()
    storage = store.ObjectStorage(store.ObjectStorageConfig(endpoint_url=s3["endpoint"], bucket=bucket, access_key_id=s3["key"], secret_access_key=s3["secret"]))
    key = f"templates/{uuid.uuid4()}/source.docx"
    store.put_once(pool, storage, object_key=key, purpose="TEMPLATE_SOURCE", content_type="application/octet-stream", data=template_docx(), lease_s=120)
    pool.close()
    tid, vid = uuid.uuid4(), uuid.uuid4()
    with db.connect() as c:
        c.execute("set session_replication_role = replica")
        c.execute("insert into template (id, code, request_type_code, name) values (%s, %s, 'WORK_CONFIRMATION', '(GIẢ) MẪU')", (tid, f"GIA_{uuid.uuid4().hex[:8]}"))
        c.execute("insert into template_version (id, template_id, version_no, status, source_object_key, uploaded_by_employee_id, required_fonts, activated_at) values (%s, %s, 1, 'ACTIVE', %s, %s, %s, now())",
                  (vid, tid, key, uuid.uuid4(), ["Times New Roman"]))
        for name, kind, source, after in NO_FREE:
            c.execute("insert into template_variable (template_version_id, variable_name, kind, source_slot_name, fill_after_approval) values (%s, %s, %s, %s, %s)", (vid, name, kind, source, after))
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(OUT / "llm-key.pem"), "-out", str(OUT / "llm-cert.pem"), "-days", "2", "-subj", f"/CN={HOST_LLM}",
                    "-addext", f"subjectAltName=DNS:{HOST_LLM}"], check=True, capture_output=True)
    env = {"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": db.dsn("bo19_app"), "BO19_SESSION_SECRET": secrets.token_urlsafe(48), "BO19_RENDER_FINGERPRINT_KEY": secrets.token_urlsafe(48),
           "BO19_LLM_API_KEY": "KHOA_GIA_CUA_COMBINED_PROBE", "BO19_LLM_BASE_URL": f"https://{HOST_LLM}:{LLM_PORT}/openai/v1", "BO19_OBJECT_STORAGE_ENDPOINT_URL": s3["endpoint"],
           "BO19_OBJECT_STORAGE_BUCKET": bucket, "BO19_OBJECT_STORAGE_ACCESS_KEY_ID": s3["key"], "BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY": s3["secret"]}
    (OUT / "probe.env").write_text("".join(f"{k}={v}\n" for k, v in env.items()), encoding="utf-8")
    (OUT / "state.json").write_text(json.dumps({"db": db.name, "admin_dsn": admin_dsn, "bucket": bucket, "app_dsn": db.dsn("bo19_app"), "migrator_dsn": db.dsn("bo19_migrator")}), encoding="utf-8")
    print(json.dumps({"db": db.name, "bucket": bucket}))


def cleanup() -> None:
    import boto3
    from botocore.config import Config
    import psycopg
    st = state()
    with psycopg.connect(st["admin_dsn"], autocommit=True) as c:
        c.execute(f"drop database if exists {st['db']} with (force)")
    s3 = boto3.client("s3", endpoint_url=os.environ["BO19_TEST_S3_ENDPOINT"], region_name="us-east-1", aws_access_key_id=os.environ["BO19_TEST_S3_ACCESS_KEY_ID"],
                      aws_secret_access_key=os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"], config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))
    for obj in s3.list_objects_v2(Bucket=st["bucket"]).get("Contents", []):
        s3.delete_object(Bucket=st["bucket"], Key=obj["Key"])
    s3.delete_bucket(Bucket=st["bucket"])
    print("đã dọn")


# ---------------------------------------------------------------------------------------------------------------- llm giả

def llm_reply(name: str) -> dict:
    if name == "classify_intent":
        return {"intent": "WORK_CONFIRMATION", "secondary_intent": None, "confidence": "high", "retrieval_query": None}
    if name == "extract_slots":
        def slot(slot_name: str, value: str) -> dict:
            at = TEXT.index(value)
            return {"slot_name": slot_name, "value": value, "evidence_span": [at, at + len(value)], "evidence_quote": value}
        return {"slots": [slot("recipient_org", RECIPIENT), slot("purpose", PURPOSE)]}
    raise KeyError(name)


class LlmHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # không log HTTP của thư viện chuẩn
        pass

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
        name = body["response_format"]["json_schema"]["name"]
        started = time.time()
        time.sleep(LLM_DELAY_S)
        data = json.dumps({"choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(llm_reply(name), ensure_ascii=False)}, "finish_reason": "stop"}], "usage": USAGE}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        with open(OUT / "llm.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"call": name, "start": started, "end": time.time()}) + "\n")


def llm() -> None:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(OUT / "llm-cert.pem", OUT / "llm-key.pem")
    server = http.server.ThreadingHTTPServer(("0.0.0.0", LLM_PORT), LlmHandler)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    print(f"llm giả {HOST_LLM}:{LLM_PORT}, trễ {LLM_DELAY_S} s", flush=True)
    server.serve_forever()


# ---------------------------------------------------------------------------------------------------------------- client

def health(base: str, timeout: float) -> None:
    import httpx
    start, last = time.monotonic(), None
    while time.monotonic() - start < timeout:
        try:
            if httpx.get(f"{base}/healthz", timeout=5).status_code == 200:
                print(json.dumps({"healthz_after_s": round(time.monotonic() - start, 1)}))
                return
        except httpx.HTTPError as e:
            last = type(e).__name__
        time.sleep(1)
    print(json.dumps({"healthz_after_s": None, "last_error": last}))
    sys.exit(1)


def password_of(code: str) -> str:
    for line in (OUT / "passwords.local.txt").read_text(encoding="utf-8").splitlines():
        c, _, p = line.partition("\t")
        if c == code:
            return p
    raise SystemExit("không có mật khẩu")


def turn(base: str, employee: str, budget_s: float) -> None:
    """Một lượt chat qua API thật. `turn_s`: từ lúc gửi POST …/turns tới event `turn.reply`. Hạn chót lượt WV-02 là 20 s, biên WV-03 là 10 s."""
    import httpx
    out: dict = {"employee": employee}
    with httpx.Client(base_url=base, timeout=httpx.Timeout(budget_s + 30, connect=10)) as client:
        t0 = time.monotonic()
        api = "/api/v1"
        r = client.post(f"{api}/auth/session", headers={"X-BO19-CSRF": "1"}, json={"employee_code": employee, "password": password_of(employee)})
        out["login_ms"] = round((time.monotonic() - t0) * 1000)
        out["login_status"] = r.status_code
        cookie = r.headers.get("set-cookie", "").split(";")[0]  # cookie `Secure`: gửi tay vì client không nối HTTPS
        headers = {"Cookie": cookie, "X-BO19-CSRF": "1"}
        r = client.post(f"{api}/chat-sessions", headers={**headers, "Idempotency-Key": str(uuid.uuid4())})
        session_id = r.json()["id"] if "id" in r.json() else r.json().get("chat_session_id")
        out["session_status"] = r.status_code
        t1 = time.monotonic()
        events: list[tuple[str, float]] = []
        with client.stream("POST", f"{api}/chat-sessions/{session_id}/turns", headers={**headers, "Idempotency-Key": str(uuid.uuid4()), "Accept": "text/event-stream"}, json={"text": TEXT}) as resp:
            out["turn_http_status"] = resp.status_code
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    events.append((line[6:].strip(), time.monotonic() - t1))
                    if events[-1][0] in ("turn.reply", "turn.error", "turn.abandoned"):
                        break
        out["events"] = [(n, round(s, 2)) for n, s in events]
        reply = next((s for n, s in events if n == "turn.reply"), None)
        out["turn_s"] = round(reply, 2) if reply is not None else None
        out["within_wv02"] = reply is not None and reply <= 20.0
    print(json.dumps(out))


def submit() -> None:
    from bo19.persistence.pool import Pool
    rt = _load("render_trial", "tools/render-trial/render_trial.py")
    st = state()

    class _Db:  # `submitted_request` chỉ cần `make_employee` và `connect`
        def __init__(self) -> None:
            self.tt = _load("turn_trial", "tools/turn-trial/turn_trial.py")
            self.inner = self.tt.TrialDb.__new__(self.tt.TrialDb)
            self.inner.admin, self.inner.name = st["admin_dsn"], st["db"]

        def make_employee(self):
            return self.inner.make_employee()

        def connect(self, user=None):
            return self.inner.connect(user)

    pool = Pool(st["app_dsn"], application_name="bo19-probe-submit", min_size=1, max_size=2)
    pool.open()
    rid, _ = rt.submitted_request(_Db(), pool, "(giả) bổ sung hồ sơ vay vốn", "(giả) Công ty ABC")
    pool.close()
    print(json.dumps({"request_id": str(rid)}))


def job(request_id: str) -> None:
    import psycopg
    st = state()
    with psycopg.connect(st["migrator_dsn"], autocommit=True) as c:
        row = c.execute("select status, attempts, last_error_code from job where payload->>'request_id' = %s", (request_id,)).fetchone()
        doc = c.execute("select status from document where request_id = %s", (request_id,)).fetchone()
    print(json.dumps({"job": row[0] if row else None, "attempts": row[1] if row else None, "error": row[2] if row else None, "document": doc[0] if doc else None}))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("setup"); p.add_argument("--admin-dsn", default=os.environ.get("BO19_TRIAL_PG_ADMIN_DSN", ""))
    sub.add_parser("llm"); sub.add_parser("cleanup"); sub.add_parser("submit")
    p = sub.add_parser("health"); p.add_argument("--base", required=True); p.add_argument("--timeout", type=float, default=300)
    p = sub.add_parser("turn"); p.add_argument("--base", required=True); p.add_argument("--employee", required=True); p.add_argument("--budget", type=float, default=20)
    p = sub.add_parser("job"); p.add_argument("--request", required=True)
    a = ap.parse_args()
    if a.cmd == "setup":
        if not a.admin_dsn:
            print("Thiếu BO19_TRIAL_PG_ADMIN_DSN.", file=sys.stderr)
            return 2
        setup(a.admin_dsn)
    elif a.cmd == "llm":
        llm()
    elif a.cmd == "health":
        health(a.base, a.timeout)
    elif a.cmd == "turn":
        turn(a.base, a.employee, a.budget)
    elif a.cmd == "submit":
        submit()
    elif a.cmd == "job":
        job(a.request)
    elif a.cmd == "cleanup":
        cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
