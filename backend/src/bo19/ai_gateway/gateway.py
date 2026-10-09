"""Lối vào DUY NHẤT tới provider: `call(module, inputs, budget_owner)` — mục Nghĩa vụ kế thừa của 06-structure.md; ADR-008, ADR-019, ADR-025, ADR-035.

Thứ tự (mục Triển khai ở B4 của 06-structure.md): chủ budget → **allowlist** → kiểm kiểu input → **budget** → provider (kèm ép JSON, sửa parse đúng một lần) → **ghi sổ** → trả.
Từ chối ở allowlist hay budget **không** có lời gọi nào tới provider; hai ca từ chối do chính gateway ghi dòng `llm_usage` trong giao dịch riêng, commit trước khi ném lỗi (ADR-019, ca 3).

**Hạn chót tổng** (PO, 2026-10-05): WV-04 (tier rẻ) hoặc WV-06 (tier mạnh), hoặc hạn chót lượt `turn_deadline` nếu đến trước, bao CẢ lời gọi — lần thử đầu, quãng nghỉ, mọi lần chờ
`retry-after` và lần sửa parse. Mỗi lần gọi provider nhận phần thời gian còn lại.

**Sổ ước lượng (B5, ADR-019 mục Bổ sung B5):** lần thử mà provider có thể đã sinh token nhưng không trả `usage` (400 `json_validate_failed`, 5xx, hết hạn chót hay mất kết nối sau khi
thân request ghi xong, 200 thân hỏng) được cộng vào dòng sổ: input = số byte UTF-8 của thân request, output = `max_completion_tokens` của module; dòng mang `estimated = true`.
Adapter đếm số lần thử (`unmetered_attempts`); gateway nhân.

**Log:** chỉ mã, tên module, tier, số token, thời lượng — không bao giờ giá trị input, nội dung output hay thân response. `ProviderError` chỉ mang mã HTTP, loại lỗi và code.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from bo19.ai_gateway import allowlist
from bo19.ai_gateway.allowlist import AllowlistRejected
from bo19.ai_gateway.budget import Budget, BudgetExceeded, BudgetOwner, BudgetOwnerMissing, BudgetUnavailable
from bo19.ai_gateway.json_contract.validator import Violation, validate
from bo19.ai_gateway.prompt_modules import CLASSIFY_INTENT, InputInvalid, PromptModule, VariableSpec, catalog_fingerprint
from bo19.ai_gateway.providers import CALL_FAILED, JSON_VALIDATE_FAILED_CODE, ProviderClient, ProviderError, ProviderResponse
from bo19.ai_gateway.routing.profiles import Profiles, load_profiles
from bo19.config import working_values as wv
from bo19.observability.log import get_logger
from bo19.persistence.pool import Pool

log = get_logger("bo19.ai_gateway")


JSON_VALIDATE_FAILED = "JSON_VALIDATE_FAILED"  # mã vi phạm trong `ParseFailed.violations` và trong lời nhắn sửa


class ParseFailed(Exception):
    """Output không hợp schema sau lần sửa duy nhất. Mang đường dẫn trường và mã (không giá trị)."""

    code = "PARSE_FAILED"

    def __init__(self, violations: tuple[Violation, ...]) -> None:
        super().__init__(self.code)
        self.violations = violations


@dataclass(frozen=True)
class GatewayResult:
    output: dict[str, Any]  # đã validate theo schema dựng lúc gọi
    outcome: str  # OK | PARSE_REPAIRED
    model: str
    prompt_module_version: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    catalog_fingerprint: str | None = field(default=None)  # chỉ P1
    duration_ms: int = 0  # thời lượng phía client của cả `call` (B5)
    estimated: bool = False  # có phần token ước lượng trong dòng sổ của lời gọi này (B5)


def _names(items: tuple[str, ...]) -> str:
    return ",".join(items)[:250]


def _sum(*values: int | None) -> int | None:
    seen = [v for v in values if v is not None]
    return sum(seen) if seen else None  # provider không trả thì để trống — không suy ra


class Gateway:
    def __init__(self, *, profiles: Profiles, client: ProviderClient, budget: Budget) -> None:
        self._profiles, self._client, self._budget = profiles, client, budget

    def __repr__(self) -> str:
        return "Gateway()"

    # ------------------------------------------------------------------------------------------------------------------------

    async def call(self, module: PromptModule, inputs: dict[str, Any], budget_owner: BudgetOwner, *, variable: VariableSpec | None = None,
                   turn_deadline: float | None = None) -> GatewayResult:
        """`turn_deadline` — thời điểm tuyệt đối (`asyncio` loop time) của hạn chót lượt chat (WV-02); `None` ở `worker`."""
        loop = asyncio.get_running_loop()
        started = loop.time()
        budget_owner.validate()  # thiếu chủ budget: lỗi lập trình — không gọi provider, không ghi được dòng (ck_llm_usage_has_budget_owner)

        try:
            allowlist.check(module, inputs, variable)
        except AllowlistRejected as e:
            log.warning("LLM_ALLOWLIST_REJECTED", call_name=module.call_name, missing=_names(e.missing), extra=_names(e.extra), forbidden=_names(e.forbidden))
            await self._record(module, budget_owner, None, None, None, "ALLOWLIST_REJECTED")
            raise
        module.check_inputs(inputs)
        schema = module.build_schema(inputs, variable)

        try:
            await asyncio.to_thread(self._budget.check, budget_owner)
        except BudgetExceeded as e:
            log.warning("LLM_BUDGET_EXCEEDED", call_name=module.call_name, dimension=e.dimension)
            await self._record(module, budget_owner, None, None, None, "BUDGET_EXCEEDED")
            raise
        except BudgetUnavailable:
            log.error("LLM_BUDGET_UNAVAILABLE", call_name=module.call_name)
            await self._record(module, budget_owner, None, None, None, "BUDGET_UNAVAILABLE")
            raise

        profile = self._profiles.profile_for(module.call_name, module.tier)  # tham số của tier cộng trần output của module (A-090)
        tier_deadline = wv.LLM_CALL_DEADLINE_CHEAP_SECONDS if module.tier == "CHEAP" else wv.LLM_CALL_DEADLINE_STRONG_SECONDS
        total = float(tier_deadline) if turn_deadline is None else min(float(tier_deadline), turn_deadline - started)
        retry_cap = float(wv.LLM_RETRY_AFTER_CEILING_SECONDS) if turn_deadline is None else None  # trong lượt chat, WV-02 đã chặn mọi lần chờ
        messages = [{"role": "system", "content": module.instructions}, {"role": "user", "content": module.render_user_message(inputs)}]
        spent: dict[str, Any] = {"in": None, "out": None, "reasoning": None, "estimated": False, "ct": 0.0, "ct_ok": True}
        cap = profile.params["max_completion_tokens"]  # trần output cứng của module — cũng là output ước lượng của một lần thử không có `usage`

        def add_estimate(count: int, request_bytes: int) -> None:
            """ADR-019 mục Bổ sung B5: mỗi lần thử có thể đã sinh token mà không có `usage` được ước lượng riêng — input = byte của thân request, output = trần output."""
            if count > 0:
                spent["in"], spent["out"] = _sum(spent["in"], count * request_bytes), _sum(spent["out"], count * cap)
                spent["estimated"], spent["ct_ok"] = True, False

        def ledger() -> dict[str, Any]:
            """Phần B5 của dòng sổ: cờ ước lượng, thời lượng phía client, tổng `completion_time`. `ct_ok` tắt khi có phản hồi thiếu `completion_time`, có lần thử ước lượng
            hay lỗi provider — khi đó tổng sẽ thiếu, nên để trống thay vì ghi một số sai."""
            return {"estimated": spent["estimated"], "duration_ms": round((loop.time() - started) * 1000),
                    "provider_completion_ms": round(spent["ct"] * 1000) if spent["ct_ok"] else None}

        def remaining() -> float:
            return total - (loop.time() - started)

        async def ask(msgs: list[dict[str, str]], attempt: int) -> ProviderResponse | None:
            """`None` khi provider trả HTTP 400 `json_validate_failed`: output bị cắt hay không hợp schema — đi đường sửa parse, không phải lỗi provider (PO, 2026-10-05)."""
            try:
                left = remaining()
                if left <= 0:
                    raise ProviderError(CALL_FAILED, "DEADLINE", attempts=0)  # hạn chót đã hết (kể cả đã hết trước lần gọi đầu)
                response = await self._client.call(profile=profile, messages=msgs, schema_name=module.call_name, schema=schema, total_deadline_s=left,
                                                   retry_after_cap_s=retry_cap)
            except ProviderError as e:
                add_estimate(e.unmetered_attempts, e.request_bytes)  # kể cả lần thử gây ra chính lỗi này, nếu theo bảng phân loại nó có thể đã sinh token
                if e.http_status == 400 and e.error_code == JSON_VALIDATE_FAILED_CODE:
                    # Tín hiệu có mã con riêng: trần `max_completion_tokens` quá thấp làm output bị cắt hiện ra ở đây. Chỉ mã và số — không thân lỗi (`failed_generation` có thể mang input).
                    log.warning("LLM_PROVIDER_JSON_VALIDATE_FAILED", call_name=module.call_name, tier=module.tier, attempt=attempt, provider_error_code=e.error_code,
                                max_completion_tokens=cap, estimated_attempts=e.unmetered_attempts)
                    return None
                log.error("LLM_PROVIDER_ERROR", call_name=module.call_name, tier=module.tier, **e.log_fields())  # mã HTTP, loại lỗi, code — không thân response
                spent["ct_ok"] = False
                await self._record(module, budget_owner, spent["in"], spent["out"], spent["reasoning"], "PROVIDER_ERROR", **ledger())
                raise
            spent["in"], spent["out"], spent["reasoning"] = (_sum(spent["in"], response.prompt_tokens), _sum(spent["out"], response.completion_tokens),
                                                             _sum(spent["reasoning"], response.reasoning_tokens))
            add_estimate(response.unmetered_attempts, response.request_bytes)
            if response.completion_time is None:
                spent["ct_ok"] = False
            else:
                spent["ct"] += response.completion_time
            # số đo cho A-092: so số byte thân request với `prompt_tokens` thật — chỉ số, không nội dung
            log.info("LLM_ATTEMPT_MEASURED", call_name=module.call_name, tier=module.tier, attempt=attempt, request_bytes=response.request_bytes,
                     prompt_tokens=response.prompt_tokens, unmetered_attempts=response.unmetered_attempts)
            return response

        first = await ask(messages, 1)
        violations = self._violations(first.content, schema) if first is not None else [Violation("$", JSON_VALIDATE_FAILED)]
        outcome, response = "OK", first
        if violations:
            # Không có output cũ để gửi lại khi lần đầu là `json_validate_failed` (provider không trả nội dung).
            repair = [*messages, *([{"role": "assistant", "content": first.content}] if first is not None else []),
                      {"role": "user", "content": self._repair_message(violations)}]  # đúng một lần (mục Chiến lược ép JSON của 07-prompts.md)
            response = await ask(repair, 2)
            violations = self._violations(response.content, schema) if response is not None else [Violation("$", JSON_VALIDATE_FAILED)]
            outcome = "PARSE_FAILED" if violations else "PARSE_REPAIRED"

        led = ledger()  # một lần đo: dòng sổ và log cùng một số
        await self._record(module, budget_owner, spent["in"], spent["out"], spent["reasoning"], outcome, **led)
        total_tokens = (spent["in"] or 0) + (spent["out"] or 0)  # `completion_tokens` đã gồm suy luận (O1-3): không cộng `reasoning` lần nữa
        fingerprint = catalog_fingerprint(inputs["request_type_catalog"]) if module is CLASSIFY_INTENT else None
        log.info("LLM_CALL_DONE", call_name=module.call_name, tier=module.tier, model=profile.model, outcome=outcome, prompt_module_version=module.version,
                 input_tokens=spent["in"], output_tokens=spent["out"], reasoning_tokens=spent["reasoning"], estimated=spent["estimated"], duration_ms=led["duration_ms"],
                 prompt_time=response.prompt_time if response else None,
                 completion_time=response.completion_time if response else None, finish_reason=response.finish_reason if response else None, catalog_fingerprint=fingerprint)
        ceiling = wv.TOKEN_CEILING_PER_CALL.get(module.call_name)
        if ceiling is not None and total_tokens > ceiling:
            log.warning("LLM_CALL_OVER_CEILING", call_name=module.call_name, total_tokens=total_tokens, ceiling=ceiling, estimated=spent["estimated"])  # A-090: đo và cảnh báo, chưa chặn trước được
        if violations:
            raise ParseFailed(tuple(violations))
        return GatewayResult(json.loads(response.content), outcome, profile.model, module.version, spent["in"] or 0, spent["out"] or 0, spent["reasoning"] or 0, fingerprint,
                             led["duration_ms"], spent["estimated"])

    # ------------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def _violations(content: str, schema: dict[str, Any]) -> list[Violation]:
        try:
            value = json.loads(content)
        except ValueError:
            return [Violation("$", "NOT_JSON")]
        return validate(schema, value)

    @staticmethod
    def _repair_message(violations: list[Violation]) -> str:
        # Đường dẫn trường và mã — không giá trị (Violation không mang giá trị).
        listed = "; ".join(f"{v.path}: {v.code}" for v in violations[:20])
        extra = " Có thể output đã bị cắt vì quá dài: trả JSON ngắn gọn." if any(v.code == JSON_VALIDATE_FAILED for v in violations) else ""
        return f"Output trước không hợp schema ({listed}). Chỉ trả JSON đúng schema, không thêm gì khác.{extra}"

    async def _record(self, module: PromptModule, owner: BudgetOwner, input_tokens: int | None, output_tokens: int | None, reasoning_tokens: int | None, outcome: str, *,
                      estimated: bool = False, duration_ms: int | None = None, provider_completion_ms: int | None = None) -> None:
        await asyncio.to_thread(self._budget.record, call_name=module.call_name, tier=module.tier, prompt_module_version=module.version, owner=owner,
                                input_tokens=input_tokens, output_tokens=output_tokens, reasoning_tokens=reasoning_tokens, outcome=outcome, estimated=estimated,
                                duration_ms=duration_ms, provider_completion_ms=provider_completion_ms)


def build_gateway(settings: Any, pool: Pool) -> Gateway:
    """Dựng gateway từ cấu hình đã qua bước kiểm khởi động #21 — composition root gọi, không module nào khác. Khoá có thể thiếu ở B4 (`api` chưa gọi LLM):
    lời gọi đầu tiên khi đó trả `ProviderError` `NO_API_KEY`."""
    check = load_profiles()
    if check.profiles is None or settings.llm_base_url is None:
        raise RuntimeError("HO_SO_MODEL_KHONG_HOP_LE")  # bước kiểm #21 đã chặn khởi động trước đó; đây là lớp phòng thủ thứ hai
    return Gateway(profiles=check.profiles, client=ProviderClient(base_url=settings.llm_base_url, api_key=settings.llm_api_key), budget=Budget(pool))
