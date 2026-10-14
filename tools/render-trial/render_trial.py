"""Chạy job `render_document` với Groq THẬT — B9a. KHÔNG phải mã ứng dụng, không vào image runtime.

Chạy đường thật: `request_submit` → job `render_document` → `Dispatcher` → `DocumentRunner.run_render` (graph, checkpointer, tool, gateway, `soffice`, object storage — tất cả thật) trên một **PostgreSQL local DÙNG TẠM**
(database tự tạo rồi xoá, như `tools/turn-trial/`) và một bucket SeaweedFS tạm; chỉ P4 `draft_free_content` đi tới Groq. Đo: thời lượng cả job và từng lời gọi, token, kết quả `validate_free_content` (số lần sinh,
`PASSED`/`FAILED`), và kết quả kiểm bằng máy của M5 trên PDF vừa dựng (`pdfinfo`: `Subject` đúng chuỗi watermark, `Author` trung lập).

Luật (PO, 2026-10-13): CHỈ văn bản bịa có nhãn "(giả)" (A-080) — slot `purpose` và `recipient_org` đều mang nhãn; **tối đa 10 lời gọi Groq** (yêu cầu HTTP, gồm sửa parse và thử lại) mỗi lần chạy — `CountingTransport` đếm và CHẶN CỨNG ở tầng truyền tải; mỗi lượt chạy còn chừa 4 lời gọi cho sinh lại và sửa parse; tool CHỈ ghi số, mã và cờ đúng/sai — **không** ghi văn bản do LLM sinh, không ghi giá trị slot; khoá API CHỈ từ biến môi trường `BO19_LLM_API_KEY` (không trên dòng lệnh, không in, không ghi; tool không đọc `.env`);
giãn nhịp dưới 6.500 token/phút (gói Free). Gọi mạng thật CHỈ khi có `--confirm-real` (không có thì in kế hoạch và thoát mã 3). Cách chạy: tools/render-trial/README.md.

Mã thoát: `0` xong · `2` thiếu khoá, DSN hay storage · `3` chưa `--confirm-real`.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "src"))

_spec = importlib.util.spec_from_file_location("turn_trial", REPO / "tools" / "turn-trial" / "turn_trial.py")
tt = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("turn_trial", tt)
_spec.loader.exec_module(tt)

import boto3  # noqa: E402
import httpx  # noqa: E402
from botocore.config import Config  # noqa: E402
from docx import Document  # noqa: E402

from bo19.ai_gateway.budget import Budget  # noqa: E402
from bo19.ai_gateway.gateway import Gateway  # noqa: E402
from bo19.ai_gateway.providers import ProviderClient  # noqa: E402
from bo19.ai_gateway.routing.profiles import load_profiles  # noqa: E402
from bo19.config.settings import DEFAULT_LLM_BASE_URL  # noqa: E402
from bo19.observability.log import configure_logging  # noqa: E402
from bo19.orchestrator.runner import DocumentRunner, document_id_for  # noqa: E402
from bo19.persistence.pool import Pool  # noqa: E402
from bo19.queue_worker.dispatcher import Dispatcher  # noqa: E402
from bo19.queue_worker.handlers import build_handlers  # noqa: E402
from bo19.tool_layer import storage as store  # noqa: E402
from bo19.tool_layer.employee_ops.request_slot_confirm import Confirmation, request_slot_confirm  # noqa: E402
from bo19.tool_layer.endpoint_ops.chat import chat_message_append, chat_session_open  # noqa: E402
from bo19.tool_layer.gate_ops.request_submit import request_submit  # noqa: E402
from bo19.tool_layer.kernel.permission import employee_context  # noqa: E402
from bo19.tool_layer.tools.request_open import request_open  # noqa: E402
from bo19.tool_layer.tools.request_slots_propose import request_slots_propose  # noqa: E402
from bo19.tool_layer.tools.request_slots_write import SlotWrite, request_slots_write  # noqa: E402

MAX_CALLS = 10  # PO, 2026-10-13
HEADROOM_CALLS = 4  # một job dùng tối đa: một lần sinh + một lần sinh lại + hai lần sửa parse
TPM_SOFT = 6_500
JOB_TOKENS_EXPECTED = 3_000
LABEL = "b9a"
OUT = Path(__file__).resolve().parent / "out"
SESSION_SECRET = "BI_MAT_PHIEN_CUA_RENDER_TRIAL_KHONG_PHAI_BI_MAT_THAT"
FONT = "Times New Roman"
PURPOSES = (("(giả) bổ sung hồ sơ vay vốn tại ngân hàng", "(giả) Ngân hàng ABC"),
            ("(giả) làm thủ tục xin cấp thị thực đi công tác nước ngoài", "(giả) Sở Ngoại vụ"),
            ("(giả) mở thẻ tín dụng tại ngân hàng nơi nhân viên có tài khoản lương", "(giả) Ngân hàng TECHCOMBANK"))
HR_REQUIRED = ("contract_type", "department_name", "employment_start_date", "full_name", "job_title")
VARIABLES = (("full_name", "DIRECT_SLOT", "full_name", False, None, None, ()), ("department_name", "DIRECT_SLOT", "department_name", False, None, None, ()),
             ("job_title", "DIRECT_SLOT", "job_title", False, None, None, ()), ("recipient_org", "DIRECT_SLOT", "recipient_org", False, None, None, ()),
             ("purpose_statement", "FREE_CONTENT", None, False, "Một hai câu hành chính ngắn, văn phong trang trọng, nêu mục đích nhân viên xin giấy xác nhận công tác.", 400, ("purpose",)),
             ("document_number", "SYSTEM", None, True, None, None, ()), ("issued_date", "SYSTEM", None, True, None, None, ()), ("signer_user_id", "SYSTEM", None, True, None, None, ()))


class CountingTransport(httpx.AsyncBaseTransport):
    """Đếm — và **chặn cứng** — số yêu cầu HTTP tới provider (PO: tối đa 10 lời gọi Groq). Đếm ở tầng truyền tải nên gồm cả lần sửa parse và mọi lần thử lại của `ProviderClient`, thứ mà dòng `llm_usage` (một dòng mỗi lời gọi
    gateway) không đếm. Quá hạn mức thì yêu cầu KHÔNG được gửi đi (lỗi kết nối) — tool không thể vượt 10 dù logic phía trên sai."""

    def __init__(self, inner: httpx.AsyncBaseTransport, limit: int = MAX_CALLS) -> None:
        self.inner, self.limit, self.requests = inner, limit, 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self.requests >= self.limit:
            raise httpx.ConnectError("vượt hạn mức số lời gọi của render-trial")
        self.requests += 1
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()


def template_docx() -> bytes:
    doc = Document()
    for style in ("Normal", "Header", "Footer"):
        doc.styles[style].font.name = FONT
    for text in ("MẪU GIẢ — chỉ để thử, không phải mẫu của tổ chức", "{{ full_name }} — {{ department_name }} — {{ job_title }}", "Kính gửi: {{ recipient_org }}", "{{ purpose_statement }}",
                 "Số: {{ document_number }} ngày {{ issued_date }} — người ký {{ signer_user_id }}"):
        doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def install_template(db, pool, storage) -> uuid.UUID:
    key = f"templates/{uuid.uuid4()}/source.docx"
    store.put_once(pool, storage, object_key=key, purpose="TEMPLATE_SOURCE", content_type="application/octet-stream", data=template_docx(), lease_s=120)
    tid, vid = uuid.uuid4(), uuid.uuid4()
    with db.connect() as c:
        c.execute("set session_replication_role = replica")
        c.execute("insert into template (id, code, request_type_code, name) values (%s, %s, 'WORK_CONFIRMATION', '(GIẢ) MẪU')", (tid, f"GIA_{uuid.uuid4().hex[:8]}"))
        c.execute("insert into template_version (id, template_id, version_no, status, source_object_key, uploaded_by_employee_id, required_fonts, activated_at) values (%s, %s, 1, 'ACTIVE', %s, %s, %s, now())",
                  (vid, tid, key, uuid.uuid4(), [FONT]))
        for name, kind, source, after, guidance, max_len, inputs in VARIABLES:
            c.execute("insert into template_variable (template_version_id, variable_name, kind, source_slot_name, fill_after_approval, variable_guidance, max_length) values (%s, %s, %s, %s, %s, %s, %s)",
                      (vid, name, kind, source, after, guidance, max_len))
            for slot in inputs:
                c.execute("insert into template_variable_input (template_version_id, variable_name, slot_name) values (%s, %s, %s)", (vid, name, slot))
    return vid


def submitted_request(db, pool, purpose: str, recipient: str) -> tuple[uuid.UUID, uuid.UUID]:
    """Một request đủ điều kiện, đã SUBMITTED (job `render_document` đứng hàng đợi). Mọi giá trị mang nhãn \"(giả)\"."""
    eid = db.make_employee()
    with pool.acquire() as conn:
        ctx = employee_context(conn, eid)
    sid = chat_session_open(pool, ctx).chat_session_id
    opener, mid = uuid.uuid4(), uuid.uuid4()
    chat_message_append(pool, ctx, chat_session_id=sid, message_id=opener, author="EMPLOYEE", body="(giả) xin giấy xác nhận công tác")
    rid = request_open(pool, ctx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=eid, opened_by_message_id=opener).request_id
    text = f"(giả) xin giấy xác nhận công tác gửi {recipient}, mục đích {purpose}"
    chat_message_append(pool, ctx, chat_session_id=sid, message_id=mid, author="EMPLOYEE", body=text)
    request_slots_write(pool, ctx, request_id=rid, items=[SlotWrite("recipient_org", recipient, mid, recipient), SlotWrite("purpose", purpose, mid, purpose)])
    request_slots_propose(pool, ctx, request_id=rid, origin="HR_PROFILE")
    with db.connect("bo19_migrator") as c:
        versions = {r[0]: r[1] for r in c.execute("select slot_name, row_version from request_slot where request_id = %s", (rid,)).fetchall()}
    request_slot_confirm(pool, ctx, request_id=rid, items=[Confirmation(n, versions[n]) for n in HR_REQUIRED])
    with db.connect("bo19_migrator") as c:
        version = c.execute("select row_version from request where id = %s", (rid,)).fetchone()[0]
    request_submit(pool, ctx, request_id=rid, decision_id=uuid.uuid4(), expected_row_version=version)
    return rid, eid


def pdf_checks(storage, db, rid: uuid.UUID) -> dict:
    """Kiểm bằng máy M5 trên PDF vừa dựng — cờ đúng/sai, không văn bản."""
    from bo19.tool_layer.rendering.doc_properties import SYSTEM_AUTHOR
    from bo19.tool_layer.rendering.watermark import WATERMARK_TEXT
    with db.connect("bo19_migrator") as c:
        row = c.execute("select pdf_object_key, watermark_text from document_render where document_id = %s", (document_id_for(rid),)).fetchone()
    if row is None:
        return {"render_row": False}
    data = storage.get(row[0])
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "x.pdf")
        Path(path).write_bytes(data)
        out = subprocess.run(["pdfinfo", "-enc", "UTF-8", path], capture_output=True, timeout=60)
    fields = {}
    for line in out.stdout.decode("utf-8", "replace").splitlines():
        k, sep, v = line.partition(":")
        if sep:
            fields[k.strip()] = v.strip()
    return {"render_row": True, "db_watermark_text_ok": row[1] == WATERMARK_TEXT, "pdf_subject_ok": fields.get("Subject") == WATERMARK_TEXT, "pdf_author_neutral": fields.get("Author") == SYSTEM_AUTHOR,
            "pdf_bytes": len(data), "pdfinfo_ran": out.returncode == 0}


def execute(*, admin_dsn: str, key: str, base_url: str, s3: dict, runs: int, transport=None, pace: bool = True, echo=print) -> dict:
    profiles = load_profiles().profiles
    db = tt.TrialDb(admin_dsn)
    pool = Pool(db.dsn("bo19_app"), application_name="bo19-render-trial", min_size=1, max_size=4)
    pool.open()
    bucket = f"bo19-trial-{uuid.uuid4().hex[:10]}"
    client = boto3.client("s3", endpoint_url=s3["endpoint"], region_name="us-east-1", aws_access_key_id=s3["key"], aws_secret_access_key=s3["secret"],
                          config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 1}))
    client.create_bucket(Bucket=bucket)
    storage = store.ObjectStorage(store.ObjectStorageConfig(endpoint_url=s3["endpoint"], bucket=bucket, access_key_id=s3["key"], secret_access_key=s3["secret"]))
    errors = tt.ProviderErrorLog()
    counter = CountingTransport(transport or httpx.AsyncHTTPTransport())
    runner = DocumentRunner.open(pool=pool, gateway=Gateway(profiles=profiles, client=ProviderClient(base_url=base_url, api_key=key, transport=counter), budget=Budget(pool)), storage=storage,
                                 dsn=db.dsn("bo19_app"), session_secret=SESSION_SECRET)
    previous = list(logging.getLogger().handlers)
    handler = configure_logging(errors)
    results: list[dict] = []
    tokens_used, window = 0, []
    try:
        install_template(db, pool, storage)
        dispatcher = Dispatcher(pool, build_handlers(document_runner=runner), poll_s=0.05, heartbeat_s=5, lease_s=300, drain_s=5)
        for n in range(runs):
            if counter.requests + HEADROOM_CALLS > MAX_CALLS:
                echo(f"Dừng: hạn mức {MAX_CALLS} lời gọi.")
                break
            while pace:
                now = time.monotonic()
                window = [(t, k) for t, k in window if now - t < 60]
                if sum(k for _, k in window) + JOB_TOKENS_EXPECTED <= TPM_SOFT:
                    break
                time.sleep(max(1.0, 60 - (now - window[0][0])))
            purpose, recipient = PURPOSES[n % len(PURPOSES)]
            rid, _ = submitted_request(db, pool, purpose, recipient)
            errors.drain()
            started = time.monotonic()
            handled = dispatcher.run_once()
            elapsed_ms = round((time.monotonic() - started) * 1000)
            with db.connect("bo19_migrator") as c:
                job = c.execute("select status, attempts, last_error_code from job where payload->>'request_id' = %s", (str(rid),)).fetchone()
                usage = c.execute("select call_name, outcome, duration_ms, provider_completion_ms, input_tokens, output_tokens, estimated from llm_usage where request_id = %s order by created_at, id", (rid,)).fetchall()
                free = c.execute("select attempt_no, validation_outcome, prompt_module_version, char_length(body) from document_free_content where document_id = %s order by attempt_no", (document_id_for(rid),)).fetchall()
                doc_status = c.execute("select status from document where id = %s", (document_id_for(rid),)).fetchone()
            tokens = sum((r[4] or 0) + (r[5] or 0) for r in usage)
            tokens_used += tokens
            window.append((time.monotonic(), tokens))
            result = {"run": n + 1, "job_handled": handled, "job_status": job[0], "job_attempts": job[1], "job_error_code": job[2], "document_status": doc_status[0] if doc_status else None, "elapsed_ms": elapsed_ms,
                      "calls": [{"call": r[0], "outcome": r[1], "duration_ms": r[2], "provider_completion_ms": r[3], "tokens": (r[4] or 0) + (r[5] or 0), "estimated": r[6]} for r in usage],
                      "free_content": [{"attempt_no": r[0], "outcome": r[1], "prompt_module_version": r[2], "body_chars": r[3]} for r in free],  # chỉ độ dài — không văn bản
                      "pdf": pdf_checks(storage, db, rid), "provider_errors": errors.drain()}
            results.append(result)
            echo(f"Lượt {n + 1}: job {job[0]} ({job[2] or 'ok'}) · document {result['document_status']} · {elapsed_ms} ms · " + ", ".join(f"{c['call']} {c['duration_ms']} ms/{c['tokens']} token" for c in result["calls"]))
    finally:
        runner.close()
        pool.close()
        db.drop()
        try:
            for obj in client.list_objects_v2(Bucket=bucket).get("Contents", []):
                client.delete_object(Bucket=bucket, Key=obj["Key"])
            client.delete_bucket(Bucket=bucket)
        except Exception:  # noqa: BLE001 — dọn bucket tạm là cố gắng tối đa
            pass
        logging.getLogger().removeHandler(handler)
        for h in previous:
            logging.getLogger().addHandler(h)
    profile = profiles.profile_for("draft_free_content", "STRONG")
    return {"runs": results, "calls_used": counter.requests, "tokens_used": tokens_used, "model": profile.model, "max_completion_tokens": profile.params["max_completion_tokens"]}


def render_md(summary: dict) -> str:
    lines = [f"# Chạy `render_document` với Groq thật — {LABEL} (B9a)", "",
             "- **Công cụ:** `tools/render-trial/render_trial.py`. **Chỉ số, mã và cờ đúng/sai** — không văn bản do LLM sinh, không giá trị slot. Mọi văn bản đầu vào mang nhãn \"(giả)\" (A-080).",
             f"- **Hồ sơ model của P4:** `{summary['model']}`, `max_completion_tokens` {summary['max_completion_tokens']}. **n nhỏ** ({len(summary['runs'])} job, {summary['calls_used']} lời gọi, {summary['tokens_used']} token): số đo, không phải thống kê.", "",
             "| Job | Job `status` | Lỗi | `document` | Cả job (ms) | Lời gọi (tên: ms / ms phía provider / token) | Lần sinh (số · kết quả · độ dài) | `Subject` đúng | `Author` trung lập | DB `watermark_text` đúng |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in summary["runs"]:
        calls = "; ".join(f"{c['call']}: {c['duration_ms']} / {c['provider_completion_ms']} / {c['tokens']}{' (ước lượng)' if c['estimated'] else ''}{'' if c['outcome'] in ('OK', 'PARSE_REPAIRED') else ' [' + c['outcome'] + ']'}" for c in r["calls"])
        free = "; ".join(f"{f['attempt_no']} · {f['outcome']} · {f['body_chars']}" for f in r["free_content"])
        p = r["pdf"]
        lines.append(f"| {r['run']} | {r['job_status']} | {r['job_error_code'] or ''} | {r['document_status']} | {r['elapsed_ms']} | {calls} | {free} | {p.get('pdf_subject_ok')} | {p.get('pdf_author_neutral')} | {p.get('db_watermark_text_ok')} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--confirm-real", action="store_true", help="gọi mạng thật")
    ap.add_argument("--runs", type=int, default=3, help="số job thử (mỗi job một lời gọi P4 nếu nội dung đạt); tổng lời gọi không vượt 10")
    ap.add_argument("--no-publish", action="store_true", help="không ghi docs/reference/")
    ap.add_argument("--label", default=LABEL)
    args = ap.parse_args()
    if not args.label.replace("-", "").isalnum() or not 1 <= args.runs <= 6:
        print("Nhãn chỉ gồm chữ, số, gạch ngang; --runs từ 1 tới 6. Thoát mã 2.")
        return 2
    print(f"Kế hoạch: {args.runs} job `render_document` thật qua Dispatcher; hạn mức {MAX_CALLS} lời gọi Groq (chừa {HEADROOM_CALLS} mỗi job); văn bản \"(giả)\".")
    if not args.confirm_real:
        print("Chưa có --confirm-real: không gọi mạng. Thoát mã 3.")
        return 3
    key = os.environ.get("BO19_LLM_API_KEY", "").strip()
    admin = os.environ.get("BO19_TRIAL_PG_ADMIN_DSN", "").strip()
    s3 = {"endpoint": os.environ.get("BO19_TEST_S3_ENDPOINT", ""), "key": os.environ.get("BO19_TEST_S3_ACCESS_KEY_ID", ""), "secret": os.environ.get("BO19_TEST_S3_SECRET_ACCESS_KEY", "")}
    missing = [n for n, v in (("BO19_LLM_API_KEY", key), ("BO19_TRIAL_PG_ADMIN_DSN", admin), ("BO19_TEST_S3_ENDPOINT", s3["endpoint"]), ("BO19_TEST_S3_ACCESS_KEY_ID", s3["key"]),
                              ("BO19_TEST_S3_SECRET_ACCESS_KEY", s3["secret"])) if not v]
    if missing:
        print("Thiếu biến môi trường: " + ", ".join(missing) + ". Thoát mã 2.")
        return 2
    base_url = os.environ.get("BO19_LLM_BASE_URL", "").strip() or DEFAULT_LLM_BASE_URL
    summary = execute(admin_dsn=admin, key=key, base_url=base_url, s3=s3, runs=args.runs)
    text = render_md(summary)
    OUT.mkdir(exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(text)
    if not args.no_publish:
        path = REPO / "docs" / "reference" / f"render-trial-{args.label}.md"
        path.write_text(text, encoding="utf-8")
        print(f"Đã ghi {path.relative_to(REPO)} — sha256 {hashlib.sha256(text.encode('utf-8')).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
