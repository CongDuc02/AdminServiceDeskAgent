"""Bước kiểm khởi động #5 và #21 — trần budget và hồ sơ model của `ai_gateway` (06-structure.md, mục Bước kiểm khởi động và Triển khai ở B4).

#5 — mọi trần budget đã cấu hình, giá trị được phép mang nhãn "chưa hiệu chỉnh", không được vắng (ADR-019 ca 2: thiếu trần **không bao giờ** được hiểu là "không có trần").
Ở B4 chỉ phủ các trần của lời gọi LLM: mỗi lời gọi, mỗi `chat_session`, mỗi `request`, và số vòng `CHANGES_REQUESTED`. **Trần mỗi lần nạp kho không có giá trị
trong thiết kế** (A-090) — vào bước này khi dựng `procedure_ingest`.

#21 — hồ sơ model của mọi tier hợp schema (ADR-035, điều kiện 1) và `BO19_LLM_BASE_URL` hợp lệ. Mã lỗi mang tên tham số/tier, không mang giá trị.
Khoá `BO19_LLM_API_KEY` không có bước kiểm ở B4: `api` chưa gọi LLM.
"""
from __future__ import annotations

from bo19.ai_gateway.routing.profiles import load_profiles
from bo19.config import working_values as wv
from bo19.startup.model import Context, Result, code

# Tên lời gọi có trần mỗi lần gọi ở B4 — khớp `llm_usage.call_name` (trừ `embed_corpus_chunk`: trần nạp kho, A-090).
CEILED_CALLS = ("classify_intent", "extract_slots", "select_procedure_passages", "embed_query", "draft_free_content", "revise_free_content")


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def step_05(ctx: Context) -> Result:
    codes: list[str] = []
    per_call = wv.TOKEN_CEILING_PER_CALL
    for call in CEILED_CALLS:
        if not _positive_int(per_call.get(call)):
            codes.append(code("5", f"CEILING_MISSING:{call}"))
    if not _positive_int(wv.TOKEN_CEILING_CHAT_SESSION):
        codes.append(code("5", "CEILING_MISSING:chat_session"))
    if not _positive_int(wv.TOKEN_CEILING_REQUEST):
        codes.append(code("5", "CEILING_MISSING:request"))
    if not _positive_int(wv.CHANGES_REQUESTED_MAX_ROUNDS):
        codes.append(code("5", "CEILING_MISSING:changes_requested_rounds"))
    return Result(tuple(codes))


def step_21(ctx: Context) -> Result:
    codes = [code("21", p.removeprefix("CONFIG_")) for f in ("llm_base_url",) if (p := ctx.settings.problem(f))]
    check = load_profiles()
    codes += [code("21", c) for c in check.codes]
    return Result(tuple(codes))
