"""Handler JSON duy nhất gắn vào root logger — stdout, một dòng một bản ghi (mục Log schema của 11-ops.md).

Hai nguồn bản ghi, một lối ra:
- Bản ghi của bo19 do `log.py` tạo — đã qua bước mask trong chuỗi processor — mang sẵn `bo19_event`.
- Bản ghi của thư viện bên thứ ba (chuỗi tự do) không phân loại được độ nhạy, nên **bỏ nội dung**: chỉ giữ tên logger,
  mức và kiểu lỗi (mục Nghĩa vụ kế thừa của 06-structure.md). Mất thông tin debug của thư viện — chấp nhận.

Mọi dòng có `timestamp` (UTC, `Z`), `level`, `component`, `trace_id`, `message`. Hàm `json.dumps` có `default` mà
một `Sensitive` lọt tới đây vẫn bị mask, và vật lạ không bao giờ được serialize nguyên.
Không import structlog: chỉ `log.py` được import (ADR-029).
"""
from __future__ import annotations

import enum
import json
import logging
import sys
from datetime import datetime, timezone
from typing import IO, Any

from bo19.observability.masking import Sensitive
from bo19.observability.trace import current_trace_id

THIRD_PARTY_MESSAGE = "THIRD_PARTY_LOG"
_BASE_KEYS = ("timestamp", "level", "component", "trace_id", "message")


def _fallback(value: object) -> Any:
    if isinstance(value, Sensitive):
        return value.masked()
    if isinstance(value, enum.Enum):
        return value.value
    return f"[UNSERIALIZABLE:{type(value).__name__}]"


def _utc_iso(created: float) -> str:
    return datetime.fromtimestamp(created, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class MaskedJsonHandler(logging.Handler):
    """Handler mask của `observability` — bước kiểm khởi động #10 tìm đúng lớp này trên root logger."""

    def __init__(self, stream: IO[str] | None = None) -> None:
        super().__init__()
        self._stream = stream

    def payload(self, record: logging.LogRecord) -> dict[str, Any]:
        event = record.__dict__.get("bo19_event")
        base: dict[str, Any] = {"timestamp": _utc_iso(record.created), "level": record.levelname, "component": record.name,
                                "trace_id": current_trace_id()}
        if isinstance(event, dict):
            base["message"] = str(event.get("event", ""))
            fields = {k: v for k, v in event.items() if k != "event" and k not in _BASE_KEYS}
        else:
            base["message"] = THIRD_PARTY_MESSAGE
            fields = {}
            if record.exc_info and record.exc_info[0] is not None:
                fields["error_type"] = record.exc_info[0].__qualname__
        return {**base, **fields}

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = json.dumps(self.payload(record), ensure_ascii=False, separators=(",", ":"), default=_fallback)
            stream = self._stream if self._stream is not None else sys.stdout
            stream.write(line + "\n")
            stream.flush()
        except Exception:  # noqa: BLE001 — logging không được làm hỏng tiến trình; lỗi ghi đi qua handleError
            self.handleError(record)


def install(stream: IO[str] | None = None, level: int = logging.INFO) -> MaskedJsonHandler:
    """Đặt handler mask làm handler DUY NHẤT của root logger — bỏ mọi handler khác, gọi lại bao nhiêu lần cũng chỉ còn một."""
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = MaskedJsonHandler(stream)
    root.addHandler(handler)
    root.setLevel(level)
    return handler


def root_handlers() -> tuple[logging.Handler, ...]:
    """Các handler hiện có trên root logger — cho bước kiểm khởi động #10, để `startup` không tự chạm `logging`."""
    return tuple(logging.getLogger().handlers)
