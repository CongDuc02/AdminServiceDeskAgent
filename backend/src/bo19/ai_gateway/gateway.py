"""Lối vào DUY NHẤT tới provider: `call(module, inputs, budget_owner)` — mục Nghĩa vụ kế thừa của 06-structure.md; ADR-008, ADR-019, ADR-025, ADR-035.

Thứ tự (mục Triển khai ở B4 của 06-structure.md): chủ budget → **allowlist** → kiểm kiểu input → **budget** → provider (kèm ép JSON, sửa parse đúng một lần) → **ghi sổ** → trả.
Từ chối ở allowlist hay budget **không** có lời gọi nào tới provider; hai ca từ chối do chính gateway ghi dòng `llm_usage` trong giao dịch riêng, commit trước khi ném lỗi (ADR-019, ca 3).

**Hạn chót tổng** (PO, 2026-10-05): WV-04 (tier rẻ) hoặc WV-06 (tier mạnh), hoặc hạn chót lượt `turn_deadline` nếu đến trước, bao CẢ lời gọi — lần thử đầu, quãng nghỉ, mọi lần chờ
`retry-after` và lần sửa parse. Mỗi lần gọi provider nhận phần thời gian còn lại.

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
from bo19.ai_gateway.providers import CALL_FAILED, ProviderClient, ProviderError, ProviderResponse
from bo19.ai_gateway.routing.profiles import Profiles, load_profiles
from bo19.config import working_values as wv
from bo19.observability.log import get_logger
from bo19.persistence.pool import Pool

log = get_logger("bo19.ai_gateway")


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
        spent = {"in": None, "out": None, "reasoning": None}

        def remaining() -> float:
            return total - (loop.time() - started)

        async def ask(msgs: list[dict[str, str]]) -> ProviderResponse:
            try:
                left = remaining()
                if left <= 0:
                    raise ProviderError(CALL_FAILED, "DEADLINE", attempts=0)  # hạn chót đã hết (kể cả đã hết trước lần gọi đầu)
                response = await self._client.call(profile=profile, messages=msgs, schema_name=module.call_name, schema=schema, total_deadline_s=left,
                                                   retry_after_cap_s=retry_cap)
            except ProviderError as e:
                log.error("LLM_PROVIDER_ERROR", call_name=module.call_name, tier=module.tier, **e.log_fields())  # mã HTTP, loại lỗi, code — không thân response
                await self._record(module, budget_owner, spent["in"], spent["out"], spent["reasoning"], "PROVIDER_ERROR")
                raise
            spent["in"], spent["out"], spent["reasoning"] = (_sum(spent["in"], response.prompt_tokens), _sum(spent["out"], response.completion_tokens),
                                                             _sum(spent["reasoning"], response.reasoning_tokens))
            return response

        first = await ask(messages)
        violations = self._violations(first.content, schema)
        outcome, response = "OK", first
        if violations:
            repair = [*messages, {"role": "assistant", "content": first.content},
                      {"role": "user", "content": self._repair_message(violations)}]  # đúng một lần (mục Chiến lược ép JSON của 07-prompts.md)
            response = await ask(repair)
            violations = self._violations(response.content, schema)
            outcome = "PARSE_FAILED" if violations else "PARSE_REPAIRED"

        await self._record(module, budget_owner, spent["in"], spent["out"], spent["reasoning"], outcome)
        total_tokens = sum(v or 0 for v in spent.values())
        fingerprint = catalog_fingerprint(inputs["request_type_catalog"]) if module is CLASSIFY_INTENT else None
        log.info("LLM_CALL_DONE", call_name=module.call_name, tier=module.tier, model=profile.model, outcome=outcome, prompt_module_version=module.version,
                 input_tokens=spent["in"], output_tokens=spent["out"], reasoning_tokens=spent["reasoning"], prompt_time=response.prompt_time,
                 completion_time=response.completion_time, finish_reason=response.finish_reason, catalog_fingerprint=fingerprint)
        ceiling = wv.TOKEN_CEILING_PER_CALL.get(module.call_name)
        if ceiling is not None and total_tokens > ceiling:
            log.warning("LLM_CALL_OVER_CEILING", call_name=module.call_name, total_tokens=total_tokens, ceiling=ceiling)  # A-090: đo và cảnh báo, chưa chặn trước được
        if violations:
            raise ParseFailed(tuple(violations))
        return GatewayResult(json.loads(response.content), outcome, profile.model, module.version, spent["in"] or 0, spent["out"] or 0, spent["reasoning"] or 0, fingerprint)

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
        return f"Output trước không hợp schema ({listed}). Chỉ trả JSON đúng schema, không thêm gì khác."

    async def _record(self, module: PromptModule, owner: BudgetOwner, input_tokens: int | None, output_tokens: int | None, reasoning_tokens: int | None, outcome: str) -> None:
        await asyncio.to_thread(self._budget.record, call_name=module.call_name, tier=module.tier, prompt_module_version=module.version, owner=owner,
                                input_tokens=input_tokens, output_tokens=output_tokens, reasoning_tokens=reasoning_tokens, outcome=outcome)


def build_gateway(settings: Any, pool: Pool) -> Gateway:
    """Dựng gateway từ cấu hình đã qua bước kiểm khởi động #21 — composition root gọi, không module nào khác. Khoá có thể thiếu ở B4 (`api` chưa gọi LLM):
    lời gọi đầu tiên khi đó trả `ProviderError` `NO_API_KEY`."""
    check = load_profiles()
    if check.profiles is None or settings.llm_base_url is None:
        raise RuntimeError("HO_SO_MODEL_KHONG_HOP_LE")  # bước kiểm #21 đã chặn khởi động trước đó; đây là lớp phòng thủ thứ hai
    return Gateway(profiles=check.profiles, client=ProviderClient(base_url=settings.llm_base_url, api_key=settings.llm_api_key), budget=Budget(pool))
