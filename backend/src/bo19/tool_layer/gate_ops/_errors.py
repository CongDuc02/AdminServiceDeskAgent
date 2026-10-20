"""Lỗi dùng chung của các thao tác cổng (`request_submit` và bốn thao tác trên `document` của B9b1) — một nơi, để `request_submit` và `_gate` không import vòng nhau.

Chỉ mang mã và (ở `StateConflict`) trạng thái hiện tại — không giá trị, không văn bản. `api` dịch sang `error_code` của 05-api.md.
"""
from __future__ import annotations

from bo19.tool_layer.tools._common import ToolError


class StateConflict(ToolError):
    """Trạng thái hay `row_version` không còn như lúc người dùng nhìn (mục 1.9 của 05-api.md)."""

    code = "STATE_CONFLICT"

    def __init__(self, current_status: str) -> None:
        super().__init__(current_status)
        self.current_status = current_status


class DecisionIdConflict(ToolError):
    code = "DECISION_ID_CONFLICT"  # `Idempotency-Key` đã là một `decision_record` khác người, khác đối tượng hay khác loại — không trả gì về dòng đó


class AwaitingTakeover(ToolError):
    code = "DOCUMENT_AWAITING_TAKEOVER"  # `document` đang có bước `TAKEOVER` `OPEN` — thread chờ ở `await_human_takeover`, không ở `interrupt` mà thao tác này nhắm tới
