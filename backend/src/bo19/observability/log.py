"""Lối ghi log duy nhất — sự kiện là MÃ, trường có kiểu, giá trị slot phải bọc `Sensitive` (06-structure.md, mục Nghĩa vụ kế thừa).

Chỉ file này import `structlog` (ADR-029). Chuỗi processor: mask theo `slot_sensitivity` → chuyển `(args, kwargs)` cho `logging`;
handler duy nhất của root logger (`handler.py`) xuất JSON. Tài liệu: docs/reference/structlog-25.4.0.md.

    log = get_logger("bo19.startup")
    log.error("STARTUP_FAIL", code="STARTUP_02_SUPERUSER")
    log.info("SLOT_READ", slot_name="bearer_national_id", value=Sensitive(v, SlotSensitivity.RES))
"""
from __future__ import annotations

import enum
import logging
import re
from typing import IO, Any

import structlog

from bo19.observability import handler as _handler
from bo19.observability.masking import Sensitive, mask_fields

_EVENT_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_RESERVED = frozenset({"event", "timestamp", "level", "component", "trace_id", "message", "exc", "error_type"})
_MAX_STR = 300


class LogUsageError(Exception):
    """Gọi API log sai khuôn — lỗi của người viết code, không phải của dữ liệu."""


def _to_logging(_logger: object, _method: str, event_dict: dict[str, Any]) -> tuple[tuple[str], dict[str, Any]]:
    event = event_dict.pop("event")
    return (event,), {"extra": {"bo19_event": {"event": event, **event_dict}}}


def configure_logging(stream: IO[str] | None = None, level: int = logging.INFO) -> _handler.MaskedJsonHandler:
    """Cài handler mask làm handler duy nhất của root logger và cấu hình chuỗi processor. Gọi một lần ở mỗi entrypoint, đầu tiên."""
    h = _handler.install(stream, level)
    structlog.configure(processors=[mask_fields, _to_logging], logger_factory=structlog.stdlib.LoggerFactory(),
                        wrapper_class=structlog.stdlib.BoundLogger, cache_logger_on_first_use=False)
    return h


def _check_fields(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in fields.items():
        if not _KEY_RE.match(key) or key in _RESERVED:
            raise LogUsageError(f"tên trường không hợp lệ hoặc dành riêng: {key!r}")
        if isinstance(value, enum.Enum):
            value = value.value
        if value is None or isinstance(value, (bool, int, float, Sensitive)):
            out[key] = value
        elif isinstance(value, str):
            if len(value) > _MAX_STR:
                raise LogUsageError(f"trường {key!r} dài quá {_MAX_STR} ký tự — log chỉ nhận mã và trường có kiểu, không nhận văn bản tự do")
            out[key] = value
        else:
            raise LogUsageError(f"trường {key!r} kiểu {type(value).__name__} không được ghi — dùng kiểu cơ bản hoặc Sensitive")
    return out


class Log:
    def __init__(self, component: str, bound: dict[str, Any] | None = None) -> None:
        self._component = component
        self._bound = dict(bound or {})
        self._logger = structlog.get_logger(component)

    def bind(self, **fields: Any) -> "Log":
        return Log(self._component, {**self._bound, **_check_fields(fields)})

    def _emit(self, level: str, event: str, exc: BaseException | None, fields: dict[str, Any]) -> None:
        if not _EVENT_RE.match(event):
            raise LogUsageError(f"sự kiện phải là mã dạng SU_KIEN_VIET_HOA, không phải văn bản: {event!r}")
        merged = {**self._bound, **_check_fields(fields)}
        if exc is not None and not isinstance(exc, BaseException):
            raise LogUsageError("exc phải là một exception")
        if exc is not None:
            # Chỉ kiểu lỗi — thông điệp của exception có thể mang giá trị RES (mục Mask trong log kỹ thuật của 09-security.md).
            merged["error_type"] = type(exc).__qualname__
        getattr(self._logger, level)(event, **merged)

    def debug(self, event: str, /, *, exc: BaseException | None = None, **fields: Any) -> None:
        self._emit("debug", event, exc, fields)

    def info(self, event: str, /, *, exc: BaseException | None = None, **fields: Any) -> None:
        self._emit("info", event, exc, fields)

    def warning(self, event: str, /, *, exc: BaseException | None = None, **fields: Any) -> None:
        self._emit("warning", event, exc, fields)

    def error(self, event: str, /, *, exc: BaseException | None = None, **fields: Any) -> None:
        self._emit("error", event, exc, fields)

    def critical(self, event: str, /, *, exc: BaseException | None = None, **fields: Any) -> None:
        self._emit("critical", event, exc, fields)


def get_logger(component: str) -> Log:
    return Log(component)
