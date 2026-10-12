"""Model request/response của nhóm Hội thoại — khớp `ChatSession`, `ChatMessage`, `ChatMessagePage`, `TurnBody` ở `contracts/openapi.yaml` (mục Hội thoại của 05-api.md)."""
from __future__ import annotations

import datetime as dt
import unicodedata
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from bo19.api.queries.chat import MessageRow, SessionRow
from bo19.config import working_values as wv


class TurnBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=wv.CHAT_MESSAGE_MAX_CHARS)  # WV-15; `chat_message_append` chặn lần cuối

    @field_validator("text", mode="before")
    @classmethod
    def _nfc_before_length(cls, value: Any) -> Any:
        """Độ dài tính bằng code point **sau NFC** (PO, 2026-10-12): chuẩn hoá chạy trước `min_length`/`max_length`, không đếm trên chuỗi thô."""
        return unicodedata.normalize("NFC", value) if isinstance(value, str) else value


class ChatSessionOut(BaseModel):
    id: uuid.UUID
    status: Literal["OPEN", "CLOSED"]
    opened_at: dt.datetime
    last_message_at: dt.datetime
    closed_at: dt.datetime | None
    close_reason: Literal["IDLE_TIMEOUT", "REQUEST_EXPIRED"] | None


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    seq: int
    author: Literal["EMPLOYEE", "AGENT"]
    request_id: uuid.UUID | None
    body: str | None  # RES; null khi đã bị xoá theo luật
    content_erased: bool
    reply_template_id: str | None
    created_at: dt.datetime


class ChatMessagePageOut(BaseModel):
    items: list[ChatMessageOut]
    next_cursor: str | None


def session_out(row: SessionRow) -> ChatSessionOut:
    return ChatSessionOut(id=row.id, status=row.status, opened_at=row.opened_at, last_message_at=row.last_message_at, closed_at=row.closed_at, close_reason=row.close_reason)


def message_out(row: MessageRow) -> ChatMessageOut:
    return ChatMessageOut(id=row.id, seq=row.seq, author=row.author, request_id=row.request_id, body=row.body, content_erased=row.content_erased,
                          reply_template_id=row.reply_template_id, created_at=row.created_at)


def jsonable(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")
