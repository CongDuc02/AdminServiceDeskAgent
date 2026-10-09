"""Đo lời gọi Groq thật — B4b. KHÔNG phải mã ứng dụng, không vào image.

Đóng: O1-1 (usage thật của P1 trên tin nhắn trần), O1-3 (`completion_tokens` có gồm token suy luận không), A-089 (từ khoá schema dưới `strict`), A-091 (dạng thân lỗi),
ngữ nghĩa trần output `max_completion_tokens` (A-090), và tham số tắt việc trả nội dung suy luận. Cách chạy, hạn mức, vị trí file: tools/llm-probe/README.md.

Luật (PO, 2026-10-05):
  - CHỈ văn bản bịa có nhãn "(giả)" (A-080) — `fixtures.py`;
  - tool CHỈ ghi số và mã — không ghi `message.content`, không ghi nội dung suy luận; áp cho mọi thí nghiệm;
  - khoá API CHỈ từ biến môi trường BO19_LLM_API_KEY do người chạy export tường minh — tool KHÔNG đọc `.env`; không trên dòng lệnh, không in, không ghi;
  - thân response lưu vào docs/reference/ (repo public) phải được che định danh và `self_check` đạt trước khi ghi; tool báo ĐẠT/KHÔNG ĐẠT;
  - tối đa 40 lời gọi, dưới 60.000 token mỗi model (kể cả token suy luận); giãn nhịp theo TPM của gói Free (8K/phút/model).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402
import sanitize  # noqa: E402
from bo19.ai_gateway.json_contract.validator import validate  # noqa: E402
from bo19.ai_gateway.prompt_modules import CLASSIFY_INTENT, DRAFT_FREE_CONTENT, EXTRACT_SLOTS, VariableSpec  # noqa: E402
from bo19.ai_gateway.routing.profiles import load_profiles  # noqa: E402
from bo19.config.settings import DEFAULT_LLM_BASE_URL  # noqa: E402

MAX_CALLS = 40
MAX_TOKENS_PER_MODEL = 60_000
TPM_SOFT = 6_500  # dưới 8K của gói Free (docs/reference/llm-groq.md mục 5), chừa chỗ cho suy luận
OUT = Path(__file__).resolve().parent / "out"
REFERENCE = REPO / "docs" / "reference" / "llm-groq-do-thuc-te-b4b-lan2.md"  # lần 1 (ngoài kế hoạch) ở llm-groq-do-thuc-te-b4b.md — không ghi đè
VAR = VariableSpec("purpose_statement", 300, ("purpose",))


class Budget(Exception):
    pass


@dataclass
class Call:
    """Kết quả một lời gọi — chỉ số, cờ và mã ngắn. KHÔNG có trường cho nội dung."""
    label: str
    model: str
    status: int | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    visible_tokens: int | None = None  # đếm bằng tokenizer offline, nội dung bị vứt ngay
    finish_reason: str | None = None
    valid_schema: bool | None = None
    has_reasoning_field: bool | None = None
    reasoning_field_chars_bucket: str | None = None
    error_type: str | None = None
    error_code: str | None = None
    remaining_tokens_header: str | None = None
    client_ms: int | None = None  # B5 (PO, 2026-10-09): thời lượng phía client của request cuối cùng (không tính quãng chờ giữa hai lần thử hay giãn cách TPM)
    completion_time_ms: int | None = None  # B5: `usage.completion_time` của Groq đổi ra mili giây; None khi Groq không trả
    extra: dict[str, Any] = field(default_factory=dict)


class Probe:
    def __init__(self, key: str, base_url: str, transport: httpx.BaseTransport | None = None, pace: bool = True, max_calls: int = MAX_CALLS) -> None:
        self._key, self._base, self._transport, self._pace, self._max_calls = key, base_url.rstrip("/"), transport, pace, max_calls
        self.calls: list[Call] = []
        self.spent: dict[str, int] = {}
        self._window: list[tuple[float, int]] = []
        self.masked_errors: list[dict[str, Any]] = []
        self.cap_under_test: int | None = None
        try:
            import tiktoken
            self._enc = tiktoken.get_encoding("o200k_harmony")
        except Exception:  # noqa: BLE001 — thiếu tiktoken hay không tải được từ vựng: E2 ghi "không đếm được", không đoán
            self._enc = None

    # --- hạn mức -----------------------------------------------------------------------------------------------------------
    def _wait_for_tpm(self, expected: int) -> None:
        if not self._pace:
            return
        while True:
            now = time.monotonic()
            self._window = [(t, n) for t, n in self._window if now - t < 60]
            if sum(n for _, n in self._window) + expected <= TPM_SOFT:
                return
            time.sleep(max(1.0, 60 - (now - self._window[0][0])))

    def _guard(self, model: str) -> None:
        if len(self.calls) >= self._max_calls:
            raise Budget("hết hạn mức số lời gọi")
        if self.spent.get(model, 0) >= MAX_TOKENS_PER_MODEL:
            raise Budget("hết hạn mức token của model")

    # --- một lời gọi ---------------------------------------------------------------------------------------------------------
    def raw(self, label: str, model: str, messages: list[dict[str, str]], schema: dict[str, Any] | None, params: dict[str, Any], *, expected_tokens: int = 2500,
            keep_error_body: bool = False, auth: str | None = None) -> Call:
        self._guard(model)
        self._wait_for_tpm(expected_tokens)
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False, **params}
        if schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": label[:40].replace("-", "_"), "strict": True, "schema": schema}}
        headers = {"Authorization": f"Bearer {auth if auth is not None else self._key}", "Content-Type": "application/json"}
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        with httpx.Client(transport=self._transport, timeout=90, trust_env=False, follow_redirects=False) as client:
            t0 = time.monotonic()
            r = client.post(self._base + "/chat/completions", headers=headers, content=payload)
            client_ms = round((time.monotonic() - t0) * 1000)
            if r.status_code == 429:  # đúng một lần chờ `retry-after` — lời gọi thứ hai tính vào hạn mức
                wait = r.headers.get("retry-after", "")
                time.sleep(min(90, int(wait)) if wait.isdigit() else 30)
                self._guard(model)
                t0 = time.monotonic()
                r = client.post(self._base + "/chat/completions", headers=headers, content=payload)
                client_ms = round((time.monotonic() - t0) * 1000)  # chỉ request cuối: quãng chờ `retry-after` không phải thời lượng của lời gọi
        call = Call(label, model, r.status_code, remaining_tokens_header=r.headers.get("x-ratelimit-remaining-tokens"), client_ms=client_ms)
        data: Any = None
        try:
            data = r.json()
        except ValueError:
            pass
        if r.status_code == 200 and isinstance(data, dict):
            self._read_ok(call, data, schema)
        else:
            err = data.get("error") if isinstance(data, dict) and isinstance(data.get("error"), dict) else {}
            call.error_type = err.get("type") if isinstance(err.get("type"), str) and len(err["type"]) <= 64 else None
            call.error_code = str(err["code"]) if err.get("code") is not None and len(str(err["code"])) <= 64 else None
            if keep_error_body:
                self.masked_errors.append({"label": label, "status": r.status_code, "body": sanitize.mask(json.dumps(data, ensure_ascii=False, indent=2) if data is not None else r.text[:2000], [self._key, auth or ""])})
        used = (call.prompt_tokens or 0) + (call.completion_tokens or 0) + (call.reasoning_tokens or 0)
        self._window.append((time.monotonic(), used))
        self.spent[model] = self.spent.get(model, 0) + used
        self.calls.append(call)
        return call

    def _read_ok(self, call: Call, data: dict[str, Any], schema: dict[str, Any] | None) -> None:
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
        call.prompt_tokens, call.completion_tokens, call.reasoning_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens"), details.get("reasoning_tokens")
        ct = usage.get("completion_time")
        call.completion_time_ms = round(ct * 1000) if isinstance(ct, (int, float)) and not isinstance(ct, bool) and ct >= 0 else None
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        fr = choice.get("finish_reason")
        call.finish_reason = fr if isinstance(fr, str) and len(fr) <= 32 else None
        content = message.get("content")
        if isinstance(content, str):
            if self._enc is not None:
                call.visible_tokens = len(self._enc.encode(content))  # chỉ độ dài, nội dung bị vứt
            if schema is not None:
                try:
                    call.valid_schema = not validate(schema, json.loads(content))
                except ValueError:
                    call.valid_schema = False
        for key in ("reasoning", "reasoning_content"):
            if key in message:
                call.has_reasoning_field = True
                n = len(message[key]) if isinstance(message[key], str) else -1
                call.reasoning_field_chars_bucket = "rỗng" if n == 0 else "<=200" if 0 < n <= 200 else ">200" if n > 200 else "không phải chuỗi"  # chỉ nhóm độ dài
                break
        else:
            call.has_reasoning_field = False

    # --- thí nghiệm ----------------------------------------------------------------------------------------------------------
    def p1(self) -> tuple[list[dict[str, str]], dict[str, Any], dict[str, Any]]:
        inputs = {"current_turn_text": fixtures.bare_message(), "pending_question": None, "active_request_type": None, "request_type_catalog": fixtures.CATALOG}
        return [{"role": "system", "content": CLASSIFY_INTENT.instructions}, {"role": "user", "content": CLASSIFY_INTENT.render_user_message(inputs)}], CLASSIFY_INTENT.build_schema(inputs, None), inputs

    def p2(self) -> tuple[list[dict[str, str]], dict[str, Any]]:
        inputs = {"current_turn_text": fixtures.P2_MESSAGE, "pending_question": "ASK_SLOT", "slot_specs": fixtures.P2_SLOT_SPECS}
        return [{"role": "system", "content": EXTRACT_SLOTS.instructions}, {"role": "user", "content": EXTRACT_SLOTS.render_user_message(inputs)}], EXTRACT_SLOTS.build_schema(inputs, None)

    def p4(self) -> tuple[list[dict[str, str]], dict[str, Any]]:
        inputs = dict(fixtures.P4_INPUTS)
        return [{"role": "system", "content": DRAFT_FREE_CONTENT.instructions}, {"role": "user", "content": DRAFT_FREE_CONTENT.render_user_message(inputs)}], DRAFT_FREE_CONTENT.build_schema(inputs, VAR)

    def profile(self, tier: str, module: str, **over: Any) -> tuple[str, dict[str, Any]]:
        p = load_profiles().profiles.profile_for(module, tier)
        return p.model, {**p.params, **over}

    def e1_o1_1(self, n: int = 5) -> None:
        m, params = self.profile("CHEAP", "classify_intent")
        msgs, schema, _ = self.p1()
        for i in range(n):
            self.raw(f"E1-p1-{i + 1}", m, msgs, schema, params)

    def e2_o1_3(self, n: int = 3) -> None:
        for module, tier, build in (("classify_intent", "CHEAP", lambda: self.p1()[:2]), ("extract_slots", "CHEAP", self.p2), ("draft_free_content", "STRONG", self.p4)):
            m, params = self.profile(tier, module)
            msgs, schema = build()
            for i in range(n):
                self.raw(f"E2-{module}-{i + 1}", m, msgs, schema, params)

    def e4b_cap_semantics(self) -> None:
        """Ngữ nghĩa `max_completion_tokens` (A-090): P4 tier mạnh với trần ĐẶT GIỮA token nhìn thấy và tổng token sinh ra (nhìn thấy + suy luận), ba lần, lấy từ số đo E2.
        Qua được (HTTP 200, `finish_reason: stop`) dù tổng sinh ra > trần ⇒ trần chỉ đếm output nhìn thấy; HTTP 400 `json_validate_failed` hay `length` ⇒ trần gồm cả suy luận."""
        visible = [c.visible_tokens for c in self.calls if c.label.startswith("E2-draft_free_content") and c.status == 200 and c.visible_tokens is not None]
        if not visible:  # thiếu tiktoken hay E2 chưa chạy: không đoán
            self.cap_under_test = None
            return
        self.cap_under_test = max(visible) + 30
        m, params = self.profile("STRONG", "draft_free_content")
        msgs, schema = self.p4()
        for i in range(3):
            self.raw(f"E4b-p4-cap{self.cap_under_test}-{i + 1}", m, msgs, schema, {**params, "max_completion_tokens": self.cap_under_test}, expected_tokens=1200)

    def e3_a089(self) -> None:
        """Nếu mọi schema thật của E1/E2 trả 200 thì từ khoá đã được chấp nhận. Chỉ khi có 400 mới tách từng từ khoá."""
        rejected = [c for c in self.calls if c.label.startswith(("E1", "E2")) and c.status == 400]
        if not rejected:
            return
        m, params = self.profile("CHEAP", "classify_intent")
        base = {"type": "object", "additionalProperties": False, "required": ["a"]}
        cases = {
            "maxLength": {"a": {"type": "string", "maxLength": 20}}, "minLength": {"a": {"type": "string", "minLength": 2}},
            "maxItems": {"a": {"type": "array", "maxItems": 3, "items": {"type": "string"}}}, "minItems": {"a": {"type": "array", "minItems": 2, "items": {"type": "string"}}},
            "const": {"a": {"type": "string", "const": "x"}}, "type_array_null": {"a": {"type": ["string", "null"]}},
        }
        for name, prop in cases.items():
            self.raw(f"E3-{name}", m, [{"role": "user", "content": fixtures.PING}], {**base, "properties": prop}, {k: v for k, v in params.items() if k != "max_completion_tokens"} | {"max_completion_tokens": 64}, expected_tokens=200)

    def e4_cap(self) -> None:
        m1, p1 = self.profile("CHEAP", "classify_intent")
        msgs1, schema1, _ = self.p1()
        for cap in (48, 48, 128):
            self.raw(f"E4-p1-cap{cap}", m1, msgs1, schema1, {**p1, "max_completion_tokens": cap})
        m4, p4 = self.profile("STRONG", "draft_free_content")
        msgs4, schema4 = self.p4()
        for cap in (64, 256):
            self.raw(f"E4-p4-cap{cap}", m4, msgs4, schema4, {**p4, "max_completion_tokens": cap}, expected_tokens=1200)

    def e5_a091(self) -> None:
        m, params = self.profile("CHEAP", "classify_intent")
        ping = [{"role": "user", "content": fixtures.PING}]
        small = {"max_completion_tokens": 32}
        self.raw("E5-khoa-sai", m, ping, None, small, expected_tokens=100, keep_error_body=True, auth="gsk_KHOA_GIA_KHONG_TON_TAI_0123456789abcdef")
        self.raw("E5-model-khong-ton-tai", "openai/model-khong-ton-tai", ping, None, small, expected_tokens=100, keep_error_body=True)
        self.raw("E5-reasoning-effort-ngoai-mien", m, ping, None, {**small, "reasoning_effort": "extreme"}, expected_tokens=100, keep_error_body=True)
        self.raw("E5-schema-sai", m, ping, {"type": "text"}, small, expected_tokens=100, keep_error_body=True)

    def e6_reasoning_off(self) -> None:
        ping = [{"role": "user", "content": fixtures.PING}]
        for tier, module in (("CHEAP", "classify_intent"), ("STRONG", "draft_free_content")):
            m, params = self.profile(tier, module)
            base = {k: v for k, v in params.items() if k not in ("max_completion_tokens", "include_reasoning")} | {"max_completion_tokens": 128}  # hồ sơ đã có include_reasoning=false: thí nghiệm này so sánh với mặc định provider
            self.raw(f"E6-{tier}-mac-dinh", m, ping, None, base, expected_tokens=300)
            self.raw(f"E6-{tier}-include_reasoning-false", m, ping, None, {**base, "include_reasoning": False}, expected_tokens=300, keep_error_body=True)
            self.raw(f"E6-{tier}-reasoning_format-hidden", m, ping, None, {**base, "reasoning_format": "hidden"}, expected_tokens=300, keep_error_body=True)


def suggest_o1_3(calls: list[Call]) -> dict[str, Any]:
    """Gợi ý (không phải kết luận): so `completion_tokens` với token nhìn thấy và token suy luận của cùng lời gọi (điều kiện 3 của ADR-035)."""
    rows = []
    for c in calls:
        if c.label.startswith("E2") and c.status == 200 and None not in (c.completion_tokens, c.reasoning_tokens, c.visible_tokens):
            tol = max(5, int(0.05 * c.completion_tokens))
            incl = abs(c.completion_tokens - (c.visible_tokens + c.reasoning_tokens)) <= tol
            excl = abs(c.completion_tokens - c.visible_tokens) <= tol
            rows.append({"label": c.label, "completion": c.completion_tokens, "reasoning": c.reasoning_tokens, "visible": c.visible_tokens,
                         "da_gom_reasoning": incl and not excl, "chua_gom_reasoning": excl and not incl, "khong_ro": incl == excl})
    verdict = ("KHÔNG ĐO ĐƯỢC" if not rows else "ĐÃ GỒM reasoning" if all(r["da_gom_reasoning"] for r in rows) else
               "CHƯA GỒM reasoning" if all(r["chua_gom_reasoning"] for r in rows) else "KHÔNG RÕ / LẪN LỘN")
    return {"gợi_ý": verdict, "dung_sai": "max(5 token, 5%) — do người triển khai chọn", "dòng": rows}


def suggest_cap(calls: list[Call], cap: int | None) -> dict[str, Any]:
    """Gợi ý (không phải kết luận) ngữ nghĩa trần output từ các lời gọi E4b."""
    rows = [c for c in calls if c.label.startswith("E4b")]
    if cap is None or not rows:
        return {"gợi_ý": "KHÔNG ĐO ĐƯỢC", "trần": cap}
    cut = [c for c in rows if (c.status == 400 and c.error_code == "json_validate_failed") or (c.status == 200 and c.finish_reason == "length")]
    passed_over = [c for c in rows if c.status == 200 and c.finish_reason == "stop" and None not in (c.visible_tokens, c.reasoning_tokens)
                   and c.visible_tokens + c.reasoning_tokens > cap]
    verdict = ("CÓ TÍNH reasoning vào trần" if len(cut) == len(rows) else "KHÔNG tính reasoning vào trần" if len(passed_over) == len(rows) else "KHÔNG RÕ / LẪN LỘN")
    return {"gợi_ý": verdict, "trần": cap, "bị_cắt": len(cut), "qua_dù_tổng_sinh_ra_vượt_trần": len(passed_over), "số_lời_gọi": len(rows),
            "dòng": [{"label": c.label, "http": c.status, "finish": c.finish_reason, "completion": c.completion_tokens, "reasoning": c.reasoning_tokens, "visible": c.visible_tokens} for c in rows]}


def publish(probe: Probe, secrets: list[str]) -> tuple[bool, list[str]]:
    """Ghi `docs/reference/llm-groq-do-thuc-te-b4b.md` (chỉ số, mã và thân lỗi ĐÃ CHE). Chỉ ghi khi `self_check` đạt. Trả (đạt, vấn đề)."""
    lines = ["# Groq — số đo lời gọi thật ở B4b, lần 2 (có `tiktoken`; số và mã; không có nội dung model trả về)", "",
             f"- **Ngày đo:** {time.strftime('%Y-%m-%d')}. **Công cụ:** `tools/llm-probe/llm_probe.py`. Nội dung gửi đi: văn bản bịa có nhãn \"(giả)\" (A-080). Lần 1 (ngoài kế hoạch, không có `tiktoken`): `llm-groq-do-thuc-te-b4b.md`.",
             "- Bảng dưới chỉ có số token, mã HTTP, `finish_reason` và cờ. Thân lỗi bên dưới đã che định danh bằng `<masked>` và `self_check` của tool đạt trước khi ghi.", "",
             "## Lời gọi", "", "| nhãn | model | HTTP | prompt | completion | reasoning | nhìn thấy | finish | hợp schema | có trường suy luận | loại lỗi | code | client ms | completion_time ms |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in probe.calls:
        lines.append(f"| {c.label} | {c.model} | {c.status} | {c.prompt_tokens} | {c.completion_tokens} | {c.reasoning_tokens} | {c.visible_tokens} | {c.finish_reason} | {c.valid_schema} | "
                     f"{c.has_reasoning_field} ({c.reasoning_field_chars_bucket}) | {c.error_type} | {c.error_code} | {c.client_ms} | {c.completion_time_ms} |")
    lines += ["", "## Gợi ý O1-3 (không phải kết luận)", "", "```json", json.dumps(suggest_o1_3(probe.calls), ensure_ascii=False, indent=2), "```", "",
              "## Gợi ý ngữ nghĩa trần output — E4b (không phải kết luận)", "", "```json", json.dumps(suggest_cap(probe.calls, probe.cap_under_test), ensure_ascii=False, indent=2), "```", "",
              "## Thân lỗi (E5, E6) — đã che", ""]
    for e in probe.masked_errors:
        lines += [f"### {e['label']} — HTTP {e['status']}", "", "```json", e["body"], "```", ""]
    text = "\n".join(lines) + "\n"
    problems = sanitize.self_check(text, secrets)
    if not problems:
        REFERENCE.write_text(text.replace("\n", "\r\n") if os.name == "nt" else text, encoding="utf-8", newline="")
    return not problems, problems


def read_key() -> str | None:
    """Khoá CHỈ vào qua biến môi trường mà người chạy đặt tường minh (PO, 2026-10-05). Tool **không** đọc `.env` hay bất kỳ file nào — nên một lần chạy nhầm
    không thể tự tìm thấy khoá."""
    return os.environ.get("BO19_LLM_API_KEY", "").strip() or None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Đo lời gọi Groq thật — B4b (tools/llm-probe/README.md)")
    ap.add_argument("--experiments", default="E1,E2,E3,E4,E5,E6", help="E1…E6, E4B (ngữ nghĩa trần output — cần E2 chạy trước và `tiktoken`)")
    ap.add_argument("--base-url", default=os.environ.get("BO19_LLM_BASE_URL", DEFAULT_LLM_BASE_URL))
    ap.add_argument("--no-publish", action="store_true", help="chỉ ghi out/results.json, không ghi docs/reference/")
    ap.add_argument("--confirm-real", action="store_true", help="BẮT BUỘC để gọi mạng thật. Không có cờ này tool chỉ in kế hoạch rồi thoát (mã 3) — chống chạy nhầm")
    ap.add_argument("--prior-calls", type=int, default=0, help="số lời gọi thật đã tiêu ở các lần chạy trước (tính vào hạn mức 40)")
    ap.add_argument("--max-calls", type=int, default=MAX_CALLS, help="hạn mức riêng của lần chạy này (không vượt 40)")
    args = ap.parse_args(argv)
    wanted = [x.strip() for x in args.experiments.split(",") if x.strip()]
    if not args.confirm_real:
        print(f"LLM_PROBE_PLAN thí_nghiệm={wanted} hạn_mức_còn={min(MAX_CALLS - args.prior_calls, args.max_calls)} — KHÔNG gọi mạng. Thêm --confirm-real để chạy thật.")
        return 3
    key = read_key()
    if not key:
        print("LLM_PROBE_CONFIG_MISSING BO19_LLM_API_KEY", file=sys.stderr)
        return 2
    probe = Probe(key, args.base_url, max_calls=max(0, min(MAX_CALLS - args.prior_calls, args.max_calls)))
    print(f"LLM_PROBE_START tiktoken={'có' if probe._enc else 'KHÔNG'} tối_đa_lời_gọi={MAX_CALLS}")
    try:
        for name, fn in (("E1", probe.e1_o1_1), ("E2", probe.e2_o1_3), ("E3", probe.e3_a089), ("E4", probe.e4_cap), ("E4B", probe.e4b_cap_semantics), ("E5", probe.e5_a091), ("E6", probe.e6_reasoning_off)):
            if name in wanted:
                fn()
                print(f"LLM_PROBE_DONE {name} lời_gọi_tích_luỹ={len(probe.calls)}")
    except Budget as e:
        print(f"LLM_PROBE_BUDGET_STOP {e}", file=sys.stderr)
    OUT.mkdir(parents=True, exist_ok=True)
    results = {"calls": [c.__dict__ for c in probe.calls], "spent_tokens_per_model": probe.spent, "o1_3": suggest_o1_3(probe.calls),
               "cap": suggest_cap(probe.calls, probe.cap_under_test)}
    text = json.dumps(results, ensure_ascii=False, indent=2)
    problems = sanitize.self_check(text, [key])
    if problems:
        print(f"LLM_PROBE_SELF_CHECK_RESULTS KHÔNG ĐẠT {problems}", file=sys.stderr)
        return 1
    (OUT / "results.json").write_text(text, encoding="utf-8")
    print(f"LLM_PROBE_SELF_CHECK_RESULTS ĐẠT sha256={hashlib.sha256(text.encode()).hexdigest()}")
    print(f"LLM_PROBE_SPENT {json.dumps(probe.spent)} calls={len(probe.calls)}")
    if not args.no_publish:
        ok, problems = publish(probe, [key])
        print(f"LLM_PROBE_SELF_CHECK_REFERENCE {'ĐẠT' if ok else 'KHÔNG ĐẠT ' + str(problems)}")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
