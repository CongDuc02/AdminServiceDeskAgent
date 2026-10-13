"""Đo thời lượng một lượt `intake_graph` với Groq thật — O1-13, B6b. KHÔNG phải mã ứng dụng, không vào image.

Chạy `IntakeRunner.run_turn` thật (graph thật, checkpointer thật, tool thật, gateway thật) trên một PostgreSQL local DÙNG TẠM: tool tự tạo một database riêng, áp `migrate_main`, dựng một nhân viên giả, chạy các lượt,
rồi xoá database. Đo: thời lượng từng lời gọi P1/P2 (`llm_usage.duration_ms` và `provider_completion_ms`) so với WV-04 (8 s) và thời lượng cả lượt so với WV-02 (20 s) — phân phối, không một lần chạy;
và **hai tỷ lệ riêng** của `request_slots_write`: `QUOTE_NOT_IN_MESSAGE` và `VALUE_NOT_IN_QUOTE` (PO, 2026-10-09).

Luật (PO): CHỈ văn bản bịa có nhãn "(giả)" (A-080); tool CHỈ ghi số và mã — không ghi nội dung tin nhắn, không ghi nội dung trả lời, không ghi giá trị slot; khoá API CHỈ từ biến môi trường `BO19_LLM_API_KEY`
(không trên dòng lệnh, không in, không ghi; tool không đọc `.env`); tối đa 24 lời gọi, dưới 60.000 token mỗi model; giãn nhịp dưới 6.500 token/phút (gói Free: 8K TPM mỗi model).
Gọi mạng thật CHỈ khi có `--confirm-real` (không có thì in kế hoạch và thoát mã 3). Cách chạy: tools/turn-trial/README.md.

**Từ B7 (O1-17, PO 2026-10-12):** mỗi lượt ghi thêm (1) **tên slot** bị loại — tên cấu hình, không phải giá trị; (2) các trường của mỗi sự kiện `LLM_PROVIDER_ERROR` trong log kỹ thuật —
CHỈ `call_name`, `kind`, `subcode`, `http_status`, `attempts`, `retry_after_seconds` (mã và số); mọi trường khác của dòng log bị bỏ, kể cả khi log đã mask.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import statistics
import sys
from collections import Counter
import time
import unicodedata
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "src"))

import psycopg  # noqa: E402
from psycopg.conninfo import conninfo_to_dict, make_conninfo  # noqa: E402

from bo19.ai_gateway.budget import Budget  # noqa: E402
from bo19.ai_gateway.gateway import Gateway  # noqa: E402
from bo19.ai_gateway.providers import ProviderClient  # noqa: E402
from bo19.ai_gateway.routing.profiles import load_profiles  # noqa: E402
from bo19.config import working_values as wv  # noqa: E402
from bo19.config.settings import DEFAULT_LLM_BASE_URL  # noqa: E402
from bo19.entrypoints import migrate_main  # noqa: E402
from bo19.observability.log import configure_logging  # noqa: E402
from bo19.orchestrator.runner import IntakeRunner  # noqa: E402
from bo19.persistence.pool import Pool  # noqa: E402
from bo19.tool_layer.endpoint_ops.chat import chat_message_append, chat_session_open  # noqa: E402
from bo19.tool_layer.kernel.permission import employee_context  # noqa: E402

MAX_CALLS = 24
MAX_TOKENS_PER_MODEL = 60_000
TPM_SOFT = 6_500
TURN_TOKENS_EXPECTED = 3_500  # P1 ~1.7K vào + P2 ~1K vào + đầu ra — chừa chỗ cho suy luận
HEADROOM_CALLS = 4  # một lượt dùng tối đa hai lời gọi, cộng hai lần sửa parse
OUT = Path(__file__).resolve().parent / "out"
RUN_LABEL = "b7"  # tên file kết quả: docs/reference/turn-trial-<nhãn>.md — mỗi lát một file, lần chạy sau không ghi đè số đo cũ
PROVIDER_ERROR_FIELDS = ("call_name", "kind", "subcode", "http_status", "attempts", "retry_after_seconds")  # chỉ mã và số (O1-17)
WV04_MS, WV02_MS = wv.LLM_CALL_DEADLINE_CHEAP_SECONDS * 1000, 20_000

# Kịch bản. Mỗi mục: (mã kịch bản, mã nhóm phiên, văn bản). Cùng nhóm = cùng một phiên và cùng một nhân viên. Mọi văn bản mang nhãn "(giả)".
SCENARIOS: list[tuple[str, str, str]] = [
    ("S1", "A", "(giả) cho mình xin giấy xác nhận công tác, gửi Ngân hàng ABC để làm hồ sơ vay vốn mua nhà"),
    ("S2", "B", "(giả) xin giấy xác nhận công tác gửi ngân hàng  Vietcombank"),
    ("S2b", "B", "(giả) mục đích là bổ sung hồ sơ vay vốn tại ngân hàng"),
    ("S3", "C", "(giả) cần giấy xác nhận công tác, nơi nhận NGÂN HÀNG TECHCOMBANK, mục đích bổ sung hồ sơ mở thẻ tín dụng"),
    ("S4", "D", unicodedata.normalize("NFD", "(giả) mình cần giấy xác nhận công tác gửi Công ty Cổ phần ABC, mục đích làm thủ tục xin cấp thị thực")),
    ("S5", "E", "(giả) xin giấy xác nhận công tác gửi Sở Ngoại vụ, mục đích xin visa"),
    ("S5b", "E", "(giả) mục đích là làm hồ sơ xin thị thực đi công tác nước ngoài"),
    ("S6", "F", "(giả) hôm nay thời tiết thế nào nhỉ"),
    ("S7", "G", "(giả) mình cần giấy xác nhận thu nhập để vay ngân hàng"),
    ("S8", "H", "(giả) cho mình xin cái giấy đó với"),
    ("S9", "I", "(giả) xin giấy xác nhận công tác và đặt phòng họp chiều mai luôn"),
]


class Budget_(Exception):
    pass


class ProviderErrorLog:
    """Đích của handler log duy nhất (`configure_logging`) trong lúc đo: đọc từng dòng JSON, giữ ĐÚNG các trường của `PROVIDER_ERROR_FIELDS` ở dòng `LLM_PROVIDER_ERROR`,
    bỏ mọi dòng và mọi trường khác. Các lượt chạy nối tiếp nên `drain()` sau mỗi lượt trả đúng lỗi của lượt đó."""

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def write(self, text: str) -> int:
        for line in text.splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("message") == "LLM_PROVIDER_ERROR":
                self.entries.append({k: record.get(k) for k in PROVIDER_ERROR_FIELDS})
        return len(text)

    def flush(self) -> None:
        pass

    def drain(self) -> list[dict]:
        out, self.entries = self.entries, []
        return out


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(p * (len(s) - 1))))]


def dist(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"n": 0}
    return {"n": len(values), "min": round(min(values)), "p50": round(pct(values, 0.5)), "p90": round(pct(values, 0.9)), "max": round(max(values)), "mean": round(statistics.mean(values))}


class TrialDb:
    """Database tạm trên một PostgreSQL local — cùng cách dựng của `tests/pg_support.py` (role, extension, `migrate_main`)."""

    def __init__(self, admin_dsn: str) -> None:
        self.admin = admin_dsn
        self.name = f"trial_{uuid.uuid4().hex[:8]}"
        with psycopg.connect(admin_dsn, autocommit=True) as c:
            for role in ("bo19_migrator", "bo19_app"):
                if not c.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone():
                    c.execute(f"create role {role} login")
            c.execute(f"create database {self.name}")
        with psycopg.connect(self.dsn(), autocommit=True) as c:
            c.execute("create extension if not exists vector")
            c.execute("grant create on schema public to bo19_migrator")
        import logging
        logging.disable(logging.CRITICAL)
        try:
            migrate_main.run(self.dsn("bo19_migrator"), migrate_main.MIGRATIONS_DIR)
        finally:
            logging.disable(logging.NOTSET)

    def dsn(self, user: str | None = None) -> str:
        d = {**conninfo_to_dict(self.admin), "dbname": self.name}
        if user:
            d["user"] = user
            d.pop("password", None)
        return make_conninfo(**d)

    def connect(self, user: str | None = None) -> psycopg.Connection:
        return psycopg.connect(self.dsn(user), autocommit=True)

    def drop(self) -> None:
        with psycopg.connect(self.admin, autocommit=True) as c:
            c.execute(f"drop database if exists {self.name} with (force)")

    def make_employee(self) -> uuid.UUID:
        eid, code = uuid.uuid4(), f"GIA{uuid.uuid4().hex[:8]}"
        with self.connect("bo19_migrator") as c:
            c.execute("insert into employee (id, employee_code, full_name, department_code, department_name, job_title, contract_type, employment_start_date, is_active, source, synced_at) "
                      "values (%s, %s, %s, 'PB-GIA', 'Phòng giả', 'Chức danh giả', 'INDEFINITE', date '2020-01-01', true, 'TRIAL_FAKE', now())", (eid, code, f"(GIẢ) {code}"))
            c.execute("insert into employee_role (employee_id, role_code) values (%s, 'EMPLOYEE')", (eid,))
        return eid


class Trial:
    def __init__(self, db: TrialDb, runner: IntakeRunner, pool: Pool, turn_deadline_s: float, *, pace: bool = True, errors: ProviderErrorLog | None = None) -> None:
        self.db, self.runner, self.pool, self.deadline_s, self._pace = db, runner, pool, turn_deadline_s, pace
        self.errors = errors or ProviderErrorLog()
        self.turns: list[dict] = []
        self.window: list[tuple[float, int]] = []
        self.calls_used = 0
        self.tokens_used = 0
        self.sessions: dict[str, tuple] = {}

    def session_for(self, group: str) -> tuple:
        """Mỗi nhóm một nhân viên và một phiên (`chat_session_open` chỉ trả MỘT phiên đang mở cho mỗi nhân viên)."""
        if group not in self.sessions:
            eid = self.db.make_employee()
            with self.pool.acquire() as conn:
                ctx = employee_context(conn, eid)
            self.sessions[group] = (chat_session_open(self.pool, ctx).chat_session_id, eid, ctx)
        return self.sessions[group]

    def pace(self) -> None:
        while self._pace:
            now = time.monotonic()
            self.window = [(t, n) for t, n in self.window if now - t < 60]
            if sum(n for _, n in self.window) + TURN_TOKENS_EXPECTED <= TPM_SOFT:
                return
            time.sleep(max(1.0, 60 - (now - self.window[0][0])))

    def run(self, scenario: str, group: str, text: str) -> dict:
        if self.calls_used + HEADROOM_CALLS > MAX_CALLS:
            raise Budget_("hết hạn mức số lời gọi")
        if self.tokens_used + TURN_TOKENS_EXPECTED > MAX_TOKENS_PER_MODEL:
            raise Budget_("hết hạn mức token của model")
        self.pace()
        sid, eid, ctx = self.session_for(group)
        mid, trace = uuid.uuid4(), str(uuid.uuid4())
        chat_message_append(self.pool, ctx, chat_session_id=sid, message_id=mid, author="EMPLOYEE", body=text)
        self.errors.drain()  # lỗi trước lượt (nếu có) không thuộc lượt này
        started = time.monotonic()
        outcome = self.runner.run_turn(chat_session_id=sid, message_id=mid, actor_employee_id=eid, trace_id=trace, deadline=started + self.deadline_s)
        elapsed_ms = round((time.monotonic() - started) * 1000)
        with self.db.connect("bo19_migrator") as c:
            usage = c.execute("select call_name, outcome, duration_ms, provider_completion_ms, input_tokens, output_tokens, estimated from llm_usage where trace_id = %s order by created_at, id", (trace,)).fetchall()
            written = c.execute("select count(*) from request_slot where evidence_message_id = %s", (mid,)).fetchone()[0]
        tokens = sum((r[4] or 0) + (r[5] or 0) for r in usage)
        self.calls_used += len(usage)
        self.tokens_used += tokens
        self.window.append((time.monotonic(), tokens))
        codes = list(outcome.rejection_codes)
        turn = {"scenario": scenario, "reply_template_id": outcome.reply_template_id, "intent_result": outcome.intent_result, "error_code": outcome.error_code, "elapsed_ms": elapsed_ms,
                "calls": [{"call": r[0], "outcome": r[1], "duration_ms": r[2], "provider_completion_ms": r[3], "tokens": (r[4] or 0) + (r[5] or 0), "estimated": r[6]} for r in usage],
                "slots_written": written, "rejection_codes": codes, "rejected_slots": list(outcome.rejected_slots), "slots_produced": written + len(codes),
                "provider_errors": self.errors.drain()}
        self.turns.append(turn)
        return turn


def summarise(turns: list[dict]) -> dict:
    p1 = [c["duration_ms"] for t in turns for c in t["calls"] if c["call"] == "classify_intent" and c["duration_ms"] is not None]
    p2 = [c["duration_ms"] for t in turns for c in t["calls"] if c["call"] == "extract_slots" and c["duration_ms"] is not None]
    both = [t["elapsed_ms"] for t in turns if {c["call"] for c in t["calls"]} >= {"classify_intent", "extract_slots"}]
    allturns = [t["elapsed_ms"] for t in turns]
    bad_calls = sum(1 for t in turns for c in t["calls"] if c["outcome"] not in ("OK", "PARSE_REPAIRED"))
    produced = sum(t["slots_produced"] for t in turns)
    quote = sum(1 for t in turns for c in t["rejection_codes"] if c.endswith(":QUOTE_NOT_IN_MESSAGE"))
    value = sum(1 for t in turns for c in t["rejection_codes"] if c.endswith(":VALUE_NOT_IN_QUOTE"))
    p2_turns = [t for t in turns if any(c["call"] == "extract_slots" for c in t["calls"])]
    return {
        "turns": len(turns), "calls": sum(len(t["calls"]) for t in turns), "calls_not_ok": bad_calls,
        "p1_ms": dist(p1), "p2_ms": dist(p2), "turn_ms_with_p1_and_p2": dist(both), "turn_ms_all": dist(allturns),
        "p1_over_wv04": sum(1 for v in p1 if v > WV04_MS), "p2_over_wv04": sum(1 for v in p2 if v > WV04_MS), "turns_over_wv02": sum(1 for v in allturns if v > WV02_MS),
        "turns_with_error": sum(1 for t in turns if t["error_code"]),
        "slots_produced": produced, "quote_not_in_message": quote, "value_not_in_quote": value,
        "rate_quote_not_in_message": round(quote / produced, 3) if produced else None, "rate_value_not_in_quote": round(value / produced, 3) if produced else None,
        "p2_turns": len(p2_turns), "p2_turns_with_evidence_mismatch": sum(1 for t in p2_turns if any(c.startswith("EVIDENCE_MISMATCH") for c in t["rejection_codes"])),
        "provider_errors": sum(len(t["provider_errors"]) for t in turns),
        "provider_errors_by_kind": dict(sorted(Counter(f"{e['subcode']}:{e['kind']}" for t in turns for e in t["provider_errors"]).items())),
    }


def _provider_error(e: dict) -> str:
    return f"{e['call_name']}: {e['subcode']}/{e['kind']} http={e['http_status']} lần thử={e['attempts']} retry-after={e['retry_after_seconds']}"


def render(summary: dict, turns: list[dict], model_profile: dict, label: str = RUN_LABEL) -> str:
    lines = [f"# Đo thời lượng một lượt `intake_graph` với Groq thật — {label} (O1-13, O1-17)", "",
             "- **Công cụ:** `tools/turn-trial/turn_trial.py`. **Chỉ số và mã** — không văn bản tin nhắn, không văn bản trả lời, không giá trị slot. Mọi tin nhắn thử mang nhãn \"(giả)\".",
             f"- **Hồ sơ model:** {json.dumps(model_profile, ensure_ascii=False)}. **n nhỏ** ({summary['turns']} lượt, {summary['calls']} lời gọi): phân phối dưới đây là số đo, không phải kết luận thống kê.", "",
             "## Thời lượng (ms)", "", "| Đại lượng | n | min | p50 | p90 | max | mean |", "|---|---|---|---|---|---|---|"]
    for title, key in (("P1 `classify_intent` — mỗi lời gọi (WV-04 = 8.000)", "p1_ms"), ("P2 `extract_slots` — mỗi lời gọi (WV-04 = 8.000)", "p2_ms"),
                       ("Cả lượt có P1 + P2 (WV-02 = 20.000)", "turn_ms_with_p1_and_p2"), ("Cả lượt, mọi lượt (WV-02 = 20.000)", "turn_ms_all")):
        d = summary[key]
        lines.append(f"| {title} | {d.get('n', 0)} | " + " | ".join(str(d.get(k, "—")) for k in ("min", "p50", "p90", "max", "mean")) + " |")
    lines += ["", f"Lời gọi vượt WV-04: P1 **{summary['p1_over_wv04']}**, P2 **{summary['p2_over_wv04']}**. Lượt vượt WV-02: **{summary['turns_over_wv02']}**. Lời gọi không `OK`/`PARSE_REPAIRED`: **{summary['calls_not_ok']}**. Lượt đi nhánh lỗi: **{summary['turns_with_error']}**.", "",
              "## `EVIDENCE_MISMATCH` — hai tỷ lệ riêng (PO, 2026-10-09)", "",
              f"- Slot P2 trả về (đã ghi + bị loại): **{summary['slots_produced']}** trong {summary['p2_turns']} lượt gọi P2.",
              f"- `QUOTE_NOT_IN_MESSAGE`: **{summary['quote_not_in_message']}** — tỷ lệ **{summary['rate_quote_not_in_message']}**.",
              f"- `VALUE_NOT_IN_QUOTE`: **{summary['value_not_in_quote']}** — tỷ lệ **{summary['rate_value_not_in_quote']}**.",
              f"- Lượt có ít nhất một `EVIDENCE_MISMATCH`: **{summary['p2_turns_with_evidence_mismatch']}** / {summary['p2_turns']}.", "",
              "## Lỗi provider — trường của `LLM_PROVIDER_ERROR` (O1-17)", "",
              f"- Số sự kiện: **{summary['provider_errors']}**; theo `subcode:kind`: {json.dumps(summary['provider_errors_by_kind'], ensure_ascii=False)}.", "",
              "## Từng lượt", "",
              "| Kịch bản | Khuôn trả lời | `intent_result` | Lỗi | Cả lượt (ms) | Lời gọi (tên: ms / ms phía provider) | Slot trả về | Mã loại | Slot bị loại | Lỗi provider |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for t in turns:
        calls = "; ".join(f"{c['call']}: {c['duration_ms']} / {c['provider_completion_ms']}{' (ước lượng)' if c['estimated'] else ''}{'' if c['outcome'] in ('OK', 'PARSE_REPAIRED') else ' [' + c['outcome'] + ']'}" for c in t["calls"])
        lines.append(f"| {t['scenario']} | {t['reply_template_id']} | {t['intent_result']} | {t['error_code'] or ''} | {t['elapsed_ms']} | {calls} | {t['slots_produced']} | "
                     f"{', '.join(t['rejection_codes'])} | {', '.join(t['rejected_slots'])} | {'; '.join(_provider_error(e) for e in t['provider_errors'])} |")
    lines += ["", "Điều kiện O1-13 (`12-roadmap.md`): P1 + P2 nối tiếp phải vừa WV-04 cho từng lời gọi và WV-02 cho cả lượt — PO quyết trên số đo này nếu chưa vừa."]
    return "\n".join(lines) + "\n"


def execute(chosen: list[tuple[str, str, str]], *, admin_dsn: str, key: str, base_url: str, turn_deadline_s: float = 20.0, prior_calls: int = 0, keep_db: bool = False,
            transport=None, pace: bool = True, echo=print) -> tuple[dict, list[dict], dict]:
    """Toàn bộ một lần đo. `transport` chỉ để test CI chạy tool với server giả — lần chạy thật không truyền."""
    profiles = load_profiles().profiles
    errors = ProviderErrorLog()
    db = TrialDb(admin_dsn)
    pool = Pool(db.dsn("bo19_app"), application_name="bo19-turn-trial", min_size=1, max_size=4)
    pool.open()
    runner = IntakeRunner.open(pool=pool, gateway=Gateway(profiles=profiles, client=ProviderClient(base_url=base_url, api_key=key, transport=transport), budget=Budget(pool)), dsn=db.dsn("bo19_app"))
    trial = Trial(db, runner, pool, turn_deadline_s, pace=pace, errors=errors)
    trial.calls_used = prior_calls
    previous = list(logging.getLogger().handlers)
    handler = configure_logging(errors)  # log kỹ thuật chỉ đi vào bộ lọc: tool chỉ giữ trường lỗi provider, chỉ mã và số
    try:
        for scenario, group, text in chosen:
            try:
                turn = trial.run(scenario, group, text)
            except Budget_ as e:
                echo(f"Dừng: {e}.")
                break
            echo(f"{scenario}: {turn['reply_template_id']} · {turn['elapsed_ms']} ms · " + ", ".join(f"{c['call']} {c['duration_ms']}" for c in turn["calls"]) + (f" · lỗi {turn['error_code']}" if turn["error_code"] else ""))
    finally:
        runner.close()
        pool.close()
        if not keep_db:
            db.drop()
        logging.getLogger().removeHandler(handler)
        for h in previous:  # trả lại handler của tiến trình gọi (test, hay `main`)
            logging.getLogger().addHandler(h)
    profile = {name: {"model": p.model, **p.params} for name in ("classify_intent", "extract_slots") for p in [profiles.profile_for(name, "CHEAP")]}
    return summarise(trial.turns), trial.turns, profile


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--confirm-real", action="store_true", help="gọi mạng thật")
    ap.add_argument("--prior-calls", type=int, default=0, help="số lời gọi đã tiêu ở lần chạy trước — trừ vào hạn mức 24")
    ap.add_argument("--turn-deadline", type=float, default=20.0, help="WV-02, giây")
    ap.add_argument("--keep-db", action="store_true")
    ap.add_argument("--no-publish", action="store_true", help="không ghi docs/reference/")
    ap.add_argument("--only", default="", help="danh sách mã kịch bản, phân cách bằng dấu phẩy")
    ap.add_argument("--label", default=RUN_LABEL, help="nhãn lần đo: kết quả ghi docs/reference/turn-trial-<nhãn>.md")
    args = ap.parse_args()
    if not args.label.replace("-", "").isalnum():
        print("Nhãn chỉ gồm chữ, số và dấu gạch ngang. Thoát mã 2.")
        return 2
    chosen = [s for s in SCENARIOS if not args.only or s[0] in args.only.split(",")]
    print(f"Kế hoạch: {len(chosen)} lượt ({', '.join(s[0] for s in chosen)}); hạn mức {MAX_CALLS - args.prior_calls} lời gọi, dưới {MAX_TOKENS_PER_MODEL} token mỗi model; WV-04 = {WV04_MS} ms, WV-02 = {args.turn_deadline * 1000:.0f} ms.")
    if not args.confirm_real:
        print("Chưa có --confirm-real: không gọi mạng. Thoát mã 3.")
        return 3
    key, admin = os.environ.get("BO19_LLM_API_KEY", "").strip(), os.environ.get("BO19_TRIAL_PG_ADMIN_DSN", "").strip()
    if not key:
        print("Thiếu BO19_LLM_API_KEY (biến môi trường). Thoát mã 2.")
        return 2
    if not admin:
        print("Thiếu BO19_TRIAL_PG_ADMIN_DSN (DSN superuser của PostgreSQL local dùng tạm). Thoát mã 2.")
        return 2
    base_url = os.environ.get("BO19_LLM_BASE_URL", "").strip() or DEFAULT_LLM_BASE_URL
    summary, turns, profile = execute(chosen, admin_dsn=admin, key=key, base_url=base_url, turn_deadline_s=args.turn_deadline, prior_calls=args.prior_calls, keep_db=args.keep_db)
    reference = REPO / "docs" / "reference" / f"turn-trial-{args.label}.md"
    text_md = render(summary, turns, profile, args.label)
    OUT.mkdir(exist_ok=True)
    (OUT / "results.json").write_text(json.dumps({"summary": summary, "turns": turns}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.no_publish:
        reference.write_text(text_md, encoding="utf-8")
        print(f"Đã ghi {reference.relative_to(REPO)} — sha256 {hashlib.sha256(text_md.encode('utf-8')).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
