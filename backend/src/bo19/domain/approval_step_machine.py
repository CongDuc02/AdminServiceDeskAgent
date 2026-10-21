"""Máy trạng thái của `approval_step` — bảng chuyển dạng thuần, không IO (mục Duyệt và quyết định của 04-data.md; B9b1, ADR-040).

Việc **yêu cầu** một người hành động: mở ở `OPEN`, rồi hoặc `DECIDED` (người đó đã quyết — `decision_record` ghi kết quả) hoặc `CANCELLED` (việc không còn cần). Không có cạnh quay lại: `uq_approval_step_one_open`
chặn hai bước cùng loại cùng mở cho một văn bản, và vòng sửa mở bước **mới** chứ không mở lại bước cũ. `ISSUE_ORDER` và `REVOKE_INITIATE` sinh ra đã `DECIDED` (INSERT, không phải một cạnh).
`tool_layer.kernel.transition` đọc bảng này; nó là nơi duy nhất sinh câu `UPDATE` đổi `approval_step.status`.
"""
from __future__ import annotations

APPROVAL_STEP_STATUSES = ("OPEN", "DECIDED", "CANCELLED")

APPROVAL_STEP_TRANSITIONS: dict[str, frozenset[str]] = {
    "OPEN": frozenset({"DECIDED", "CANCELLED"}),
    "DECIDED": frozenset(),
    "CANCELLED": frozenset(),
}

# Trạng thái cuối — `closed_at` có giá trị khi và chỉ khi không còn `OPEN` (`ck_approval_step_closed_iff_not_open`).
APPROVAL_STEP_TERMINAL = frozenset({"DECIDED", "CANCELLED"})


def can_transition(source: str, target: str) -> bool:
    return target in APPROVAL_STEP_TRANSITIONS.get(source, frozenset())
