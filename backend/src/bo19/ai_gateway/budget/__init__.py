"""Sổ budget — MODULE DUY NHẤT của `ai_gateway` đọc và ghi `llm_usage` (ADR-019; ngoại lệ ghi số 3 của mục Tool Registry của 03-agents.md).

Ghi đúng một bảng, `llm_usage`; phép đọc duy nhất cũng trên bảng đó — tổng token đã tiêu của một chủ budget. Bảng không có cột nào cho văn bản prompt, văn bản output hay giá trị slot;
`prompt_module_version` và `trace_id` (hai cột `text` không có `CHECK` hình dạng) chỉ nhận định danh phiên bản và `trace_id` từ ngữ cảnh trace — không nhận chuỗi tự do.

**Fail-closed (ADR-019, ba ca):** không đọc được số đã tiêu → `BudgetUnavailable` (lời gọi bị từ chối, không tới provider); trần chủ budget đã chạm → `BudgetExceeded`;
thiếu chủ budget → `BudgetOwnerMissing` — lỗi lập trình, không ghi được dòng vì `ck_llm_usage_has_budget_owner`.
Trần là hằng số của `config.working_values` (bước kiểm khởi động #5 đòi chúng có mặt); trần mỗi LỜI GỌI chưa chặn được trước lời gọi (A-090) — chỉ trần theo chủ budget chặn.

**Token cộng dồn (O1-3 đã đóng, 2026-10-05):** tổng = `input_tokens + output_tokens`. `completion_tokens` của Groq **đã gồm** token suy luận (số đo B4b lần 2, `docs/reference/llm-groq-do-thuc-te-b4b-lan2.md`),
nên cộng thêm `reasoning_tokens` là đếm trùng. `reasoning_tokens` vẫn được ghi vào `llm_usage` để theo dõi, không cộng vào trần.
Ghi sổ lỗi (DB hỏng) không làm hỏng lời gọi đã có kết quả — token đã tiêu, đếm thiếu tối đa một lời gọi là cái ADR-019 chấp nhận; lỗi được log, không im lặng.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import psycopg

from bo19.config import working_values as wv
from bo19.observability.log import get_logger
from bo19.observability.trace import current_trace_id, new_trace_id
from bo19.persistence.pool import Pool, PoolExhausted
from bo19.persistence.read import read_only
from bo19.persistence.write import unit_of_work

log = get_logger("bo19.ai_gateway.budget")

OUTCOMES = ("OK", "PARSE_REPAIRED", "PARSE_FAILED", "PROVIDER_ERROR", "BUDGET_EXCEEDED", "BUDGET_UNAVAILABLE", "ALLOWLIST_REJECTED")


class BudgetOwnerMissing(Exception):
    code = "BUDGET_OWNER_MISSING"


class BudgetExceeded(Exception):
    code = "BUDGET_EXCEEDED"

    def __init__(self, dimension: str) -> None:
        super().__init__(self.code)
        self.dimension = dimension  # "chat_session" | "request" — tên, không số


class BudgetUnavailable(Exception):
    code = "BUDGET_UNAVAILABLE"


@dataclass(frozen=True)
class BudgetOwner:
    """Chủ budget — ít nhất một trong `request_id`, `chat_session_id`, `procedure_document_version_id` (`ck_llm_usage_has_budget_owner`)."""
    request_id: uuid.UUID | None = None
    chat_session_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    procedure_document_version_id: uuid.UUID | None = None

    def validate(self) -> None:
        if not any((self.request_id, self.chat_session_id, self.procedure_document_version_id)):
            raise BudgetOwnerMissing


_SPENT = "SELECT coalesce(sum(input_tokens + coalesce(output_tokens, 0)), 0) FROM llm_usage WHERE {col} = %s"


class Budget:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    def check(self, owner: BudgetOwner) -> None:
        """Từ chối khi tổng token đã tiêu của một chủ budget đã ≥ trần. Chạy đồng bộ — gateway gọi qua `asyncio.to_thread`."""
        owner.validate()
        dimensions = ((owner.chat_session_id, "chat_session_id", "chat_session", wv.TOKEN_CEILING_CHAT_SESSION),
                      (owner.request_id, "request_id", "request", wv.TOKEN_CEILING_REQUEST))
        try:
            with self._pool.acquire() as conn:
                for value, col, name, ceiling in dimensions:
                    if value is None:
                        continue
                    with read_only(conn):
                        spent = conn.execute(_SPENT.format(col=col), (value,)).fetchone()[0]
                    if spent >= ceiling:
                        raise BudgetExceeded(name)
        except (psycopg.Error, PoolExhausted):
            raise BudgetUnavailable from None  # không đọc được số đã tiêu thì không biết đã chạm trần chưa — từ chối, không gọi provider

    def record(self, *, call_name: str, tier: str, prompt_module_version: str | None, owner: BudgetOwner, input_tokens: int | None, output_tokens: int | None,
               reasoning_tokens: int | None, outcome: str, estimated: bool = False, duration_ms: int | None = None, provider_completion_ms: int | None = None) -> bool:
        """Một dòng, một giao dịch riêng, commit xong mới trả. Trả `False` (và log) nếu không ghi được — không ném. `input_tokens` thiếu thì 0 (cột NOT NULL), không suy ra.

        `estimated` (B5, ADR-019 mục Bổ sung B5): dòng có phần token ước lượng — đã tính vào `input_tokens`/`output_tokens`, nên truy vấn tổng không đổi và ước lượng được tính vào trần.
        Chỉ hợp lệ với bốn kết quả có lời gọi tới provider (`ck_llm_usage_estimated_shape`)."""
        assert outcome in OUTCOMES
        try:
            with self._pool.acquire() as conn, unit_of_work(conn):
                conn.execute(
                    "INSERT INTO llm_usage (id, call_name, model_tier, prompt_module_version, request_id, chat_session_id, document_id, "
                    "procedure_document_version_id, input_tokens, output_tokens, reasoning_tokens, outcome, trace_id, estimated, duration_ms, provider_completion_ms) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (uuid.uuid4(), call_name, tier, prompt_module_version, owner.request_id, owner.chat_session_id, owner.document_id,
                     owner.procedure_document_version_id, input_tokens or 0, output_tokens, reasoning_tokens, outcome, current_trace_id() or new_trace_id(),
                     estimated, duration_ms, provider_completion_ms))
            return True
        except Exception as e:  # noqa: BLE001 — mọi lỗi ghi sổ: log mã và kiểu, không nuốt im lặng
            log.error("LLM_USAGE_WRITE_FAILED", exc=e, call_name=call_name, outcome=outcome, internal_code=getattr(e, "code", None))
            return False
