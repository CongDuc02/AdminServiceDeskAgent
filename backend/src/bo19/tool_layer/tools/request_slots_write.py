"""`request_slots_write` — ghi giá trị slot `USER_INPUT` do `extract_slots` (P2) trích (mục Tool Registry của 03-agents.md).

**Kiểm bằng chứng nằm TRONG tool, không trong node:** bỏ qua node thì không bỏ qua được kiểm tra. Mỗi mục phải có `evidence_quote` nằm **nguyên văn** trong tin nhắn bằng chứng (tin của chính
nhân viên, trong chính phiên của `request`; so khớp trên NFC — `chat_message_append` lưu `body` dạng NFC). Đoạn trích không khớp là **suy diễn** → `EVIDENCE_MISMATCH`, mục bị loại, không ghi.
Với slot `STRING`/`TEXT`, `value` cũng phải nằm nguyên văn trong đoạn trích. Vị trí `evidence_span` do tool tính lại từ đoạn trích — chỉ số model đếm không đáng tin.

Không ghi xác nhận của nhân viên — việc đó là `request_slot_confirm`. Kết quả từng mục: ghi, không đổi (đã có từ chính tin nhắn này — idempotent theo (`request_id`, tin nhắn bằng chứng)),
hay bị loại kèm mã (`SLOT_NOT_ALLOWED`, `EVIDENCE_MISMATCH`, `RULE_FAILED` cộng mã rule). Cả lời gọi lỗi khi: không phải `request` của mình, thiếu `request.supply_info`, `NOT_EDITABLE`.
`audit_event` chỉ khi có slot được ghi, payload chỉ mang tên slot và mã — không giá trị.
"""
from __future__ import annotations

import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any

from psycopg.types.range import Range

from bo19.domain import slot_rules
from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.checks.eligibility import load_definitions
from bo19.tool_layer.kernel import audit
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require
from bo19.tool_layer.tools._common import jsonb, load_own_request, require_editable

MAX_QUOTE_CHARS = 300  # khớp `maxLength` của `evidence_quote` trong schema P2


@dataclass(frozen=True)
class SlotWrite:
    slot_name: str
    value: Any
    evidence_message_id: uuid.UUID
    evidence_quote: str
    evidence_span: tuple[int, int] | None = None  # chỉ số do model đếm — chỉ dùng nếu đúng, không bao giờ tin


@dataclass(frozen=True)
class Rejection:
    slot_name: str
    code: str  # SLOT_NOT_ALLOWED | EVIDENCE_MISMATCH | RULE_FAILED
    rule_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class WriteResult:
    written: tuple[str, ...]
    unchanged: tuple[str, ...]
    rejected: tuple[Rejection, ...]


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _evidence_span(body: str, quote: str, claimed: tuple[int, int] | None) -> tuple[int, int] | None:
    """`(đầu, cuối)` nếu `quote` nằm nguyên văn trong `body`; ưu tiên chỉ số model đưa khi nó đúng, không thì vị trí đầu tiên tìm thấy."""
    if not quote or len(quote) > MAX_QUOTE_CHARS:
        return None
    if claimed is not None and 0 <= claimed[0] < claimed[1] <= len(body) and body[claimed[0]:claimed[1]] == quote:
        return claimed
    at = body.find(quote)
    return None if at < 0 else (at, at + len(quote))


def request_slots_write(pool: Pool, ctx: ToolContext, *, request_id: uuid.UUID, items: list[SlotWrite]) -> WriteResult:
    require(ctx, "request.supply_info")
    with pool.acquire() as conn, unit_of_work(conn):
        row = load_own_request(conn, ctx, request_id)
        require_editable(row)
        definitions = {d.name: d for d in load_definitions(conn, row.request_type_code)}
        written: list[str] = []
        unchanged: list[str] = []
        rejected: list[Rejection] = []
        for item in items:
            d = definitions.get(item.slot_name)
            if d is None or d.source != "USER_INPUT":
                rejected.append(Rejection(item.slot_name, "SLOT_NOT_ALLOWED"))
                continue
            message = conn.execute("SELECT body FROM chat_message WHERE id = %s AND chat_session_id = %s AND author = 'EMPLOYEE'",
                                   (item.evidence_message_id, row.chat_session_id)).fetchone()
            body = _nfc(message[0]) if message is not None and message[0] is not None else None
            quote = _nfc(item.evidence_quote)
            span = _evidence_span(body, quote, item.evidence_span) if body is not None else None
            value_ok = not isinstance(item.value, str) or d.data_type not in ("STRING", "TEXT") or _nfc(item.value) in quote
            if span is None or not value_ok:
                rejected.append(Rejection(item.slot_name, "EVIDENCE_MISMATCH"))
                continue
            value = _nfc(item.value) if isinstance(item.value, str) else item.value  # chuỗi lưu dạng NFC (cùng body của tin nhắn)
            failed = slot_rules.check_value(d.data_type, d.rules, value)
            if failed:
                rejected.append(Rejection(item.slot_name, "RULE_FAILED", failed))
                continue
            existing = conn.execute("SELECT evidence_message_id FROM request_slot WHERE request_id = %s AND slot_name = %s FOR UPDATE", (request_id, item.slot_name)).fetchone()
            if existing is not None and existing[0] == item.evidence_message_id:
                unchanged.append(item.slot_name)  # cùng tin nhắn đã ghi slot này: chạy lại lượt không đổi gì
                continue
            if existing is None:
                conn.execute("INSERT INTO request_slot (request_id, request_type_code, slot_name, value, value_status, evidence_message_id, evidence_span) "
                             "VALUES (%s, %s, %s, %s, 'PROVIDED', %s, %s)", (request_id, row.request_type_code, item.slot_name, jsonb(value), item.evidence_message_id, Range(*span)))
            else:  # nhân viên nói lại: giá trị mới thay giá trị cũ và mọi dấu vết xác nhận/đề xuất của nó
                conn.execute("UPDATE request_slot SET value = %s, value_status = 'PROVIDED', evidence_message_id = %s, evidence_span = %s, confirmed_at = NULL, provenance_source = NULL, "
                             "provenance_synced_at = NULL, proposed_from_request_id = NULL, row_version = row_version + 1, updated_at = now() WHERE request_id = %s AND slot_name = %s",
                             (jsonb(value), item.evidence_message_id, Range(*span), request_id, item.slot_name))
            written.append(item.slot_name)
        if written:
            audit.record(conn, ctx, action="request.slots_write", entity_type="request", entity_id=request_id, request_id=request_id,
                         payload={"written": written, "rejected": [f"{r.slot_name}:{r.code}" for r in rejected]})
        return WriteResult(tuple(written), tuple(unchanged), tuple(rejected))
