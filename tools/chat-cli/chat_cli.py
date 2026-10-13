"""CLI chat tối giản ở local — cho PO thử hội thoại thật với `intake_graph` qua Groq trước khi có client (R1-5, B7b). KHÔNG phải mã ứng dụng, không vào image.

Dùng lại `tools/turn-trial/turn_trial.py`: database tạm, nhân viên giả, `IntakeRunner` thật (graph, checkpointer, tool, gateway thật), nhịp gọi dưới hạn mức Groq gói Free. Đề xuất đã duyệt: `docs/design/proposals/chat-cli.md`.

Luật (PO, 2026-10-12 và 2026-10-13): CHỈ thông tin bịa (A-080); khoá API CHỈ từ biến môi trường `BO19_LLM_API_KEY` (không trên dòng lệnh, không in, không ghi; tool không đọc `.env`);
gọi mạng thật CHỈ khi có `--confirm-real` VÀ người chạy gõ `dong y` sau dòng nhắc; **không ghi nội dung hội thoại ra file, log hay history** — tin nhắn, câu trả lời, giá trị slot chỉ hiện trên màn hình;
CLI đọc stdin thô, KHÔNG nạp `readline`; database tạm bị xoá khi thoát, không có `--keep-db`. Tối đa 40 lời gọi mỗi lần chạy.

Lệnh: `/slots` · `/confirm <tên slot> …` (đích danh, không có "tất cả") · `/submit` · `/new` · `/quit`. Mọi lệnh đi qua đúng thao tác của `tool_layer`.
Mã thoát: `0` xong · `2` thiếu khoá hoặc DSN · `3` chưa `--confirm-real` · `4` không đồng ý.
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "src"))

_spec = importlib.util.spec_from_file_location("turn_trial", REPO / "tools" / "turn-trial" / "turn_trial.py")
tt = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("turn_trial", tt)
_spec.loader.exec_module(tt)

from bo19.ai_gateway.budget import Budget  # noqa: E402
from bo19.ai_gateway.gateway import Gateway  # noqa: E402
from bo19.ai_gateway.providers import ProviderClient  # noqa: E402
from bo19.ai_gateway.routing.profiles import load_profiles  # noqa: E402
from bo19.api.queries import requests as rq  # noqa: E402
from bo19.config.settings import DEFAULT_LLM_BASE_URL  # noqa: E402
from bo19.observability.log import configure_logging  # noqa: E402
from bo19.orchestrator.runner import IntakeRunner  # noqa: E402
from bo19.persistence.pool import Pool  # noqa: E402
from bo19.tool_layer.employee_ops.request_slot_confirm import Confirmation, NotProposed, StaleValue, request_slot_confirm  # noqa: E402
from bo19.tool_layer.gate_ops.request_submit import DecisionIdConflict, NotReady, StateConflict, request_submit  # noqa: E402
from bo19.tool_layer.kernel.permission import PermissionDenied  # noqa: E402
from bo19.tool_layer.tools._common import NotEditable, NotOwnRequest  # noqa: E402

MAX_CALLS = 40
NOTICE = "Mọi nội dung bạn gõ được gửi tới Groq ở nước ngoài (A-080). Chỉ gõ thông tin bịa."
CONSENT = "dong y"
EXIT_NO_CONSENT = 4
HELP = "Lệnh: /slots · /confirm <tên slot> … · /submit · /new · /quit. Gõ nội dung bình thường để chat."


def consented(answer: str) -> bool:
    return answer.strip().lower() == CONSENT


class Cli:
    """Một phiên chat: nhân viên giả hiện hành, vòng nhận dòng, các lệnh. Chỉ in ra `out`; không ghi gì khác."""

    def __init__(self, trial, pool: Pool, out, max_calls: int) -> None:
        self.trial, self.pool, self.out, self.max_calls = trial, pool, out, max_calls
        self.group = 0
        self.turns = 0

    def say(self, text: str = "") -> None:
        self.out.write(text + "\n")
        self.out.flush()

    # ---- phiên hiện hành -------------------------------------------------------------------------------------------------------

    def session(self) -> tuple:
        return self.trial.session_for(f"cli-{self.group}")  # (chat_session_id, employee_id, ctx)

    def request_id(self) -> uuid.UUID | None:
        sid, _, _ = self.session()
        with self.trial.db.connect("bo19_migrator") as c:
            row = c.execute("select id from request where chat_session_id = %s order by created_at desc limit 1", (sid,)).fetchone()
        return row[0] if row else None

    def detail(self) -> dict | None:
        rid = self.request_id()
        if rid is None:
            return None
        _, eid, _ = self.session()
        with self.pool.acquire() as conn:
            return rq.own_request_detail(conn, rid, eid)

    # ---- chat --------------------------------------------------------------------------------------------------------------------

    def budget_left(self) -> bool:
        return self.trial.calls_used + tt.HEADROOM_CALLS <= self.max_calls

    def chat(self, text: str) -> None:
        if not self.budget_left():
            self.say(f"Hết hạn mức {self.max_calls} lời gọi cho lần chạy này — không nhận thêm tin. Gõ /quit để xem tổng.")
            return
        try:
            turn = self.trial.run("chat", f"cli-{self.group}", text)
        except tt.Budget_ as e:
            self.say(f"Dừng: {e}.")
            return
        self.turns += 1
        sid, _, _ = self.session()
        with self.trial.db.connect("bo19_migrator") as c:
            row = c.execute("select body from chat_message where chat_session_id = %s and author = 'AGENT' order by seq desc limit 1", (sid,)).fetchone()
        self.say("agent> " + (row[0] if row else "(không có câu trả lời)"))
        calls = ", ".join(f"{c['call']} {c['duration_ms']} ms" for c in turn["calls"]) or "không gọi LLM"
        tokens = sum(c["tokens"] for c in turn["calls"])
        errors = "".join(f" · LỖI PROVIDER {e['subcode']}/{e['kind']} http={e['http_status']}" for e in turn["provider_errors"])
        self.say(f"[{turn['reply_template_id']} · ý định {turn['intent_result']} · {turn['elapsed_ms']} ms · {calls} · {tokens} token · còn {self.max_calls - self.trial.calls_used} lời gọi{errors}]")

    # ---- lệnh --------------------------------------------------------------------------------------------------------------------

    def slots(self) -> None:
        d = self.detail()
        if d is None:
            self.say("Chưa có yêu cầu nào trong phiên này.")
            return
        self.say(f"Yêu cầu {d['request_type_name']} — {d['status_label']} (row_version {d['row_version']}) · sẵn sàng gửi: {'có' if d['submit_ready'] else 'chưa'}")
        for s in d["slots"]:
            if s["value_status"] is None:
                continue
            shown = "(đã xoá)" if s["erased"] else repr(s["value"])  # CHỈ màn hình — PO, Q2
            self.say(f"  {s['slot_name']:<24} {s['value_status']:<10} v{s['row_version']:<3} [{s['sensitivity']}] {s['label']}: {shown}")
        if d["missing_slots"]:
            self.say("  còn thiếu: " + ", ".join(d["missing_slots"]))
        if d["unconfirmed_slots"]:
            self.say("  chưa xác nhận: " + ", ".join(d["unconfirmed_slots"]))
        if d["failed_rules"]:
            self.say("  trượt rule: " + ", ".join(f"{r['slot_name']}:{r['rule_code']}" for r in d["failed_rules"]))

    def confirm(self, names: list[str]) -> None:
        d = self.detail()
        if d is None:
            self.say("Chưa có yêu cầu nào trong phiên này.")
            return
        if not names:
            self.say("Dùng: /confirm <tên slot> [<tên slot> …] — đích danh từng slot, không có xác nhận tất cả.")
            return
        versions = {s["slot_name"]: s["row_version"] for s in d["slots"]}
        _, _, ctx = self.session()
        items = [Confirmation(n, versions.get(n) or 0) for n in names]
        try:
            result = request_slot_confirm(self.pool, ctx, request_id=uuid.UUID(str(d["id"])), items=items)
        except (NotProposed, StaleValue, NotEditable, NotOwnRequest, PermissionDenied) as e:
            self.say(f"Không xác nhận được ({e.code}{': ' + str(e.detail) if getattr(e, 'detail', None) else ''}) — không slot nào bị đổi.")
            return
        self.say(f"Đã xác nhận: {', '.join(result.confirmed) or '(không)'} · đã xác nhận từ trước: {', '.join(result.unchanged) or '(không)'} · trạng thái {result.status} · đủ điều kiện: {'có' if result.eligible else 'chưa'}")

    def submit(self) -> None:
        d = self.detail()
        if d is None:
            self.say("Chưa có yêu cầu nào trong phiên này.")
            return
        _, _, ctx = self.session()
        try:
            out = request_submit(self.pool, ctx, request_id=uuid.UUID(str(d["id"])), decision_id=uuid.uuid4(), expected_row_version=d["row_version"])
        except NotReady as e:
            self.say("REQUEST_NOT_READY — thiếu: " + (", ".join(e.missing_slots) or "(không)") + " · chưa xác nhận: " + (", ".join(e.unconfirmed_slots) or "(không)")
                     + " · trượt rule: " + (", ".join(f"{s}:{c}" for s, c in e.failed_rules) or "(không)"))
            return
        except (StateConflict, DecisionIdConflict, NotOwnRequest, PermissionDenied) as e:
            self.say(f"Không gửi được ({e.code}{': ' + str(e.detail) if getattr(e, 'detail', None) else ''}).")
            return
        self.say(f"Đã gửi — decision_record {out.decision_record_id}. Job render_document đứng ở hàng đợi (chưa có worker, B8a).")

    def new(self) -> None:
        self.group += 1
        self.session()
        self.say("Đã mở phiên mới với một nhân viên giả mới (GIẢ).")

    # ---- vòng đọc ----------------------------------------------------------------------------------------------------------------

    def handle(self, line: str) -> bool:
        """`False` khi cần thoát."""
        line = line.strip()
        if not line:
            return True
        if not line.startswith("/"):
            self.chat(line)
            return True
        cmd, *args = line.split()
        if cmd == "/quit":
            return False
        if cmd == "/slots":
            self.slots()
        elif cmd == "/confirm":
            self.confirm(args)
        elif cmd == "/submit":
            self.submit()
        elif cmd == "/new":
            self.new()
        else:
            self.say(HELP)
        return True

    def run(self, stdin) -> None:
        self.session()
        self.say(HELP)
        while True:
            self.out.write("> ")
            self.out.flush()
            line = stdin.readline()
            if line == "":  # EOF
                break
            if not self.handle(line):
                break

    def summary(self) -> None:
        errors = [e for t in self.trial.turns for e in t["provider_errors"]]
        kinds = ", ".join(sorted({f"{e['subcode']}/{e['kind']}" for e in errors})) or "không"
        self.say(f"\nTổng: {self.turns} lượt · {self.trial.calls_used} lời gọi · {self.trial.tokens_used} token · lỗi provider: {len(errors)} ({kinds}).")


def execute(*, admin_dsn: str, key: str, base_url: str, max_calls: int = MAX_CALLS, turn_deadline_s: float = 20.0, transport=None, pace: bool = True,
            stdin=None, out=None) -> int:
    """Một lần chạy. `transport` chỉ để test CI chạy tool với server giả — lần chạy thật không truyền. Đã qua `--confirm-real` và kiểm khoá ở `main`."""
    stdin, out = stdin or sys.stdin, out or sys.stdout
    out.write(NOTICE + f"\nGõ `{CONSENT}` để tiếp tục: ")
    out.flush()
    if not consented(stdin.readline()):
        out.write("Chưa đồng ý — không tạo database, không gọi mạng. Thoát mã 4.\n")
        return EXIT_NO_CONSENT
    profiles = load_profiles().profiles
    errors = tt.ProviderErrorLog()
    db = tt.TrialDb(admin_dsn)
    pool = Pool(db.dsn("bo19_app"), application_name="bo19-chat-cli", min_size=1, max_size=4)
    pool.open()
    runner = IntakeRunner.open(pool=pool, gateway=Gateway(profiles=profiles, client=ProviderClient(base_url=base_url, api_key=key, transport=transport), budget=Budget(pool)), dsn=db.dsn("bo19_app"))
    trial = tt.Trial(db, runner, pool, turn_deadline_s, pace=pace, errors=errors)
    previous = list(logging.getLogger().handlers)
    handler = configure_logging(errors)  # log kỹ thuật chỉ đi vào bộ lọc: giữ sáu trường lỗi provider, bỏ mọi thứ khác
    cli = Cli(trial, pool, out, max_calls)
    try:
        cli.run(stdin)
        cli.summary()
    finally:
        runner.close()
        pool.close()
        db.drop()
        logging.getLogger().removeHandler(handler)
        for h in previous:
            logging.getLogger().addHandler(h)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--confirm-real", action="store_true", help="gọi mạng thật")
    ap.add_argument("--max-calls", type=int, default=MAX_CALLS, help=f"trần số lời gọi (mặc định {MAX_CALLS})")
    ap.add_argument("--turn-deadline", type=float, default=20.0, help="WV-02, giây")
    args = ap.parse_args()
    if not 1 <= args.max_calls <= MAX_CALLS:
        print(f"--max-calls phải trong 1..{MAX_CALLS}. Thoát mã 2.")
        return 2
    print(f"Kế hoạch: chat với intake_graph thật qua Groq; tối đa {args.max_calls} lời gọi; database tạm; nhân viên giả.")
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
    return execute(admin_dsn=admin, key=key, base_url=base_url, max_calls=args.max_calls, turn_deadline_s=args.turn_deadline)


if __name__ == "__main__":
    sys.exit(main())
