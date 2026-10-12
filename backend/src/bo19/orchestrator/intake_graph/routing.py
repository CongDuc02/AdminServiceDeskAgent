"""Ánh xạ output của `classify_intent` (P1) sang `intent_result` — tám dòng của mục `intake_graph` của 03-agents.md (thêm ở đợt sửa A-075). Hàm thuần, không IO, chỉ mã.

`route_intent` xét theo thứ tự, **dòng đầu tiên khớp thì dừng**. `catalog` là bản `request_type_catalog` đã nạp cho CHÍNH lời gọi P1 đó (ADR-025). `open_type` là loại của `request` mà chat còn sửa được
(`DRAFT`, `NEEDS_INFO`, `CHANGES_REQUESTED`), hoặc `None` — ở mọi trạng thái khác phiên coi như chưa có `request` đang mở.

Sprint 1 cài đủ tám dòng và test đủ tám dòng, nhưng `MULTIPLE` và `TYPE_CHANGED` thuộc Sprint 2 (AC-2.8): `graph.py` rẽ hai kết quả đó sang `ask_clarification` (PO duyệt G2, B6b).
`retrieval_query` bị bỏ ở Sprint 1: chưa có nhánh retrieval, và nó là văn bản từ lời nhân viên (`RES`) nên không có chỗ nào để giữ nó.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SUPPORTED, KNOWN_UNSUPPORTED = "SUPPORTED", "KNOWN_UNSUPPORTED"
OUT_OF_SCOPE, NEED_CLARIFICATION = "OUT_OF_SCOPE", "NEED_CLARIFICATION"
EDITABLE_BY_CHAT = frozenset({"DRAFT", "NEEDS_INFO", "CHANGES_REQUESTED"})


@dataclass(frozen=True)
class Mapped:
    intent_result: str  # SUPPORTED | AMBIGUOUS | OUT_OF_SCOPE | TYPE_CHANGED | MULTIPLE | UNPARSEABLE
    primary_type: str | None = None  # loại SUPPORTED để mở/đối chiếu (SUPPORTED, TYPE_CHANGED, MULTIPLE)
    unsupported_type: str | None = None  # mã KNOWN_UNSUPPORTED để khuôn nêu tên (EC-WC-03)
    candidate_types: tuple[str, ...] = ()  # mã P1 đã trả (AMBIGUOUS), hoặc hai nhu cầu (MULTIPLE)
    pending_type: str | None = None  # nhu cầu còn lại của MULTIPLE (None = ngoài phạm vi) — Sprint 2 đưa vào `pending_intents`
    row: int = 0  # dòng của bảng ánh xạ đã khớp — để test và log


def map_intent(output: Mapping[str, Any] | None, catalog: Sequence[Mapping[str, Any]], open_type: str | None) -> Mapped:
    """`output` là dict đã validate theo schema, hoặc `None` khi JSON hỏng lần hai."""
    status = {e["code"]: e["support_status"] for e in catalog}
    if output is None:
        return Mapped("UNPARSEABLE", row=1)
    intent, secondary, confidence = output.get("intent"), output.get("secondary_intent"), output.get("confidence")

    def known(code: Any) -> bool:
        return code in status or code in (OUT_OF_SCOPE, NEED_CLARIFICATION)

    # 1 — mã không có trong catalog (lớp thứ hai cho nhánh provider không ép được schema)
    if not known(intent) or (secondary is not None and (not known(secondary) or secondary == NEED_CLARIFICATION)):
        return Mapped("UNPARSEABLE", row=1)
    # 2 — NEED_CLARIFICATION hoặc độ tin cậy thấp
    if intent == NEED_CLARIFICATION or confidence == "low":
        codes = tuple(c for c in (intent, secondary) if c in status)
        return Mapped("AMBIGUOUS", candidate_types=codes, row=2)
    # 3, 4 — hai nhu cầu khác nhau
    if secondary is not None and secondary != intent:
        supported = [c for c in (intent, secondary) if status.get(c) == SUPPORTED]
        if supported:  # 3
            primary = intent if status.get(intent) == SUPPORTED else secondary
            other = secondary if primary == intent else intent
            return Mapped("MULTIPLE", primary_type=primary, candidate_types=tuple(c for c in (intent, secondary) if c in status),
                          pending_type=other if other in status else None, row=3)
        unsupported = intent if status.get(intent) == KNOWN_UNSUPPORTED else None  # 4
        return Mapped("OUT_OF_SCOPE", unsupported_type=unsupported, row=4)
    # 5, 6 — loại đang hỗ trợ
    if status.get(intent) == SUPPORTED:
        if open_type is None or open_type == intent:
            return Mapped("SUPPORTED", primary_type=intent, row=5)
        return Mapped("TYPE_CHANGED", primary_type=intent, row=6)
    # 7 — loại đã biết là chưa hỗ trợ
    if status.get(intent) == KNOWN_UNSUPPORTED:
        return Mapped("OUT_OF_SCOPE", unsupported_type=intent, row=7)
    # 8 — ngoài phạm vi
    return Mapped("OUT_OF_SCOPE", row=8)
