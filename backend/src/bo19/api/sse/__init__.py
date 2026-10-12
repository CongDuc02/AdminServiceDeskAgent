"""Khung SSE của stream lượt chat (mục SSE của 05-api.md; ADR-013). Chỉ định dạng và vòng đọc kênh — không có logic nghiệp vụ.

Mỗi sự kiện là `event: <tên>\\ndata: <JSON một dòng>\\n\\n`. Sau `turn.reply` hoặc `turn.error` stream đóng. `data` là JSON của các model đã khớp `openapi.yaml`.
Client ngắt thì Starlette dừng lặp (hoặc huỷ) generator: generator **không** giữ lượt — lượt chạy ở task của bộ giám sát (`api/turns`, ADR-016) và không bị ảnh hưởng.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable
from typing import Any

from bo19.api.turns import TurnHandle

TERMINAL = ("turn.reply", "turn.error")
HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}  # không đệm: proxy phải chuyển từng sự kiện ngay


def frame(event: str, data: Any) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'), default=str)}\n\n".encode("utf-8")


async def relay(handle: TurnHandle, first: Iterable[tuple[str, Any]] = ()) -> AsyncIterator[bytes]:
    """Phát `first` (ví dụ `turn.accepted`) rồi chuyển tiếp sự kiện của lượt cho tới sự kiện cuối."""
    for event, data in first:
        yield frame(event, data)
    while True:
        event, data = await handle.events.get()
        yield frame(event, data)
        if event in TERMINAL:
            return


async def replay(events: Iterable[tuple[str, Any]]) -> AsyncIterator[bytes]:
    """Phát lại một lượt đã xong đọc từ DB (gửi lại cùng `Idempotency-Key`)."""
    for event, data in events:
        yield frame(event, data)
