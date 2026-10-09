"""Máy trạng thái của `request` — bảng chuyển dạng thuần, không IO (mục Vòng đời `request` của 00-domain.md; GLOSSARY.md, mục Trạng thái request).

Một máy cho mọi loại yêu cầu. `tool_layer.kernel.transition` đọc bảng này: nó là nơi duy nhất sinh câu `UPDATE` đổi `status`, nên không cạnh nào ngoài bảng này ghi được.
`tests/test_request_machine.py` đọc lại sơ đồ Mermaid của 00-domain.md và đòi bảng khớp từng cạnh — sơ đồ đổi mà bảng không đổi (hay ngược lại) thì đỏ.
"""
from __future__ import annotations

REQUEST_STATUSES = ("DRAFT", "NEEDS_INFO", "SUBMITTED", "IN_REVIEW", "CHANGES_REQUESTED", "APPROVED", "FULFILLED", "REJECTED", "CANCELLED", "EXPIRED")

# Cạnh của sơ đồ — mỗi dòng một cạnh, cùng thứ tự với sơ đồ để đối chiếu bằng mắt.
REQUEST_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"NEEDS_INFO", "SUBMITTED", "CANCELLED"}),
    "NEEDS_INFO": frozenset({"DRAFT", "EXPIRED"}),
    "SUBMITTED": frozenset({"REJECTED", "IN_REVIEW"}),
    "IN_REVIEW": frozenset({"CHANGES_REQUESTED", "REJECTED", "APPROVED"}),
    "CHANGES_REQUESTED": frozenset({"SUBMITTED", "CANCELLED", "REJECTED"}),
    "APPROVED": frozenset({"FULFILLED"}),
    "FULFILLED": frozenset(),
    "REJECTED": frozenset(),
    "CANCELLED": frozenset(),
    "EXPIRED": frozenset(),
}

# Trạng thái cuối — `request.closed_at` có giá trị khi và chỉ khi `status` ở đây (`ck_request_closed_iff_terminal`).
REQUEST_TERMINAL = frozenset({"FULFILLED", "REJECTED", "CANCELLED", "EXPIRED"})


def can_transition(source: str, target: str) -> bool:
    return target in REQUEST_TRANSITIONS.get(source, frozenset())
