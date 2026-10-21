"""Cấp số văn bản — `document_number_assign` và `document_number_void` (ADR-011; mục Sổ số văn bản và mục Giao dịch cấp số của 04-data.md; mục 5.2 của 03-agents.md).

**Một nơi gọi duy nhất: `finalize_issue`** (B9b), trong `queue_worker`, bước 1 — số phải có trước khi render vì nó in trên văn bản. Chỉ tác nhân hệ thống.

**Một giao dịch NGẮN, không chạm `object_storage`, không render, không chờ hệ thống nào ngoài `postgresql`:** khoá hàng `document` → ngày và kỳ → bảo đảm dòng bộ đếm → (đã có dòng `ASSIGNED` của `document` này thì trả chính nó)
→ tăng bộ đếm bằng MỘT câu `UPDATE … RETURNING` → định dạng → ghi dòng sổ → `audit_event` → commit. Khoá dòng bộ đếm không bao giờ bị giữ xuyên qua render hay upload.
**Tương đương phải giữ:** một giá trị `seq` tồn tại khi và chỉ khi có một dòng `document_register_entry` mang nó — tăng bộ đếm và ghi dòng sổ cùng commit hoặc cùng lăn. Lỗ hổng số chỉ sinh ra qua `VOIDED`, và luôn có lý do.

**Idempotent theo `document_id`:** hàng `document` bị khoá trước, nên hai lần gọi đồng thời cho cùng một `document` xếp hàng và lần sau thấy dòng của lần trước — không lấy số thứ hai. `uq_register_entry_one_assigned_per_document` là lớp thứ hai.
**Dải** (`TRIAL`/`OFFICIAL`) lấy từ `document.register_series` — cột sinh từ `operating_mode` đã ghim lúc tạo `DRAFT`; hai dải không bao giờ chung bộ đếm (D-009), và khoá ngoại ghép của DB buộc dải của dòng sổ khớp dải của `document`.
**Kỳ** tính từ ngày cấp số theo múi giờ của tổ chức (A-041, `Asia/Ho_Chi_Minh`); sổ `YEARLY` có kỳ là năm, `NEVER` có kỳ `ALL`. **Định dạng** là cấu hình (`document_register_format`, chỉ thêm; áp dòng có `effective_from` lớn nhất không sau thời điểm cấp);
chuỗi số lưu **nguyên** trên dòng sổ nên đổi mẫu không đổi số đã cấp. Mẫu thiếu `{year}` ở sổ `YEARLY` làm giao dịch HỎNG (`NUMBER_FORMAT_COLLISION`, `seq` không bị tiêu) thay vì phát số trùng năm trước.

`audit_event` chỉ mang mã, số đếm và id — không chuỗi số, không giá trị slot.

**`document_number_void_open` (B9b2, ADR-041 mục 3):** huỷ số `ASSIGNED` đang mở của một `document` chưa `ISSUED`, tìm theo `document_id` — cho handler `finalize_issue` khi job sắp `FAILED`
(Sprint 1 chưa có `halt_for_human`). Không có số `ASSIGNED`, hoặc `document` đã `ISSUED`, thì không làm gì (trả `None`).
"""
from __future__ import annotations

import datetime as dt
import re
import uuid
import zoneinfo
from dataclasses import dataclass

import psycopg

from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.kernel import audit
from bo19.tool_layer.kernel.context import ToolContext
from bo19.tool_layer.kernel.permission import require_system
from bo19.tool_layer.tools._common import ToolError

ORG_TIMEZONE = "Asia/Ho_Chi_Minh"  # A-041 `Đã chốt`; bước kiểm khởi động #13 chặn giá trị khác
_TOKEN = re.compile(r"\{([A-Za-z_]+)\}")
_KNOWN_TOKENS = frozenset({"seq", "year", "symbol"})
_REASON = re.compile(r"^[A-Z][A-Z0-9_]*$")


class DocumentNotFound(ToolError):
    code = "DOCUMENT_NOT_FOUND"


class NoIssueOrder(ToolError):
    code = "NO_ISSUE_ORDER"  # lệnh phát hành không có, hoặc không phải của `document` này — không cấp số khi chưa có người ra lệnh


class NoRegister(ToolError):
    code = "NO_REGISTER"


class NoFormat(ToolError):
    code = "NO_FORMAT"  # chưa có mẫu cho (sổ, dải) này — dải `TRIAL` giả ở fixture test; dải thật vào data migration khi có M1.2


class BadFormat(ToolError):
    code = "BAD_FORMAT"  # token lạ trong `format_pattern`


class NumberFormatCollision(ToolError):
    code = "NUMBER_FORMAT_COLLISION"  # chuỗi số đã có trong (sổ, dải) — mẫu cấu hình sai; giao dịch lăn, không số nào bị tiêu


class EntryNotFound(ToolError):
    code = "ENTRY_NOT_FOUND"


class NotVoidable(ToolError):
    code = "NOT_VOIDABLE"  # đã `VOIDED`, hoặc số đang gắn với một `document` đã `ISSUED`


@dataclass(frozen=True)
class NumberAssigned:
    entry_id: uuid.UUID
    seq: int
    formatted_number: str
    series: str
    period_key: str
    issued_date: dt.date  # ngày cấp số theo múi giờ tổ chức — chính là `issued_date` in trên văn bản (slot `issued_date` của `WORK_CONFIRMATION`)
    created: bool  # False: `document` đã có số, trả lại chính dòng đó


def render_number(pattern: str, *, seq: int, min_digits: int, year: int, symbol: str) -> str:
    """Thay token trong `format_pattern`. Token lạ → `BadFormat`. Giá trị thay vào không được diễn giải lại (không `str.format`)."""
    unknown = {m for m in _TOKEN.findall(pattern)} - _KNOWN_TOKENS
    if unknown:
        raise BadFormat
    values = {"seq": str(seq).zfill(min_digits), "year": str(year), "symbol": symbol}
    return _TOKEN.sub(lambda m: values[m.group(1)], pattern)


def document_number_assign(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID, issue_decision_id: uuid.UUID, at: dt.datetime | None = None) -> NumberAssigned:
    """`at` — đồng hồ truyền vào để test kỳ (năm); thật thì để trống: lấy `now()` của DB."""
    require_system(ctx)
    with pool.acquire() as conn, unit_of_work(conn):
        doc = conn.execute("SELECT d.request_id, d.register_series, t.document_register_id FROM document d JOIN request r ON r.id = d.request_id JOIN request_type t ON t.code = r.request_type_code "
                           "WHERE d.id = %s FOR UPDATE OF d", (document_id,)).fetchone()  # khoá hàng `document`: hai lần gọi cùng `document` xếp hàng
        if doc is None:
            raise DocumentNotFound
        request_id, series, register_id = doc
        if register_id is None:
            raise NoRegister
        order = conn.execute("SELECT 1 FROM decision_record WHERE id = %s AND kind = 'ISSUE_ORDERED' AND document_id = %s", (issue_decision_id, document_id)).fetchone()
        if order is None:
            raise NoIssueOrder
        existing = conn.execute("SELECT id, seq, formatted_number, series, period_key, (assigned_at AT TIME ZONE %s)::date FROM document_register_entry WHERE document_id = %s AND status = 'ASSIGNED'",
                                (ORG_TIMEZONE, document_id)).fetchone()
        if existing is not None:  # idempotent theo `document_id`: lần thử lại của `finalize_issue` không lấy số mới
            return NumberAssigned(*existing, created=False)
        now = at or conn.execute("SELECT now()").fetchone()[0]
        local = now.astimezone(zoneinfo.ZoneInfo(ORG_TIMEZONE))
        reset = conn.execute("SELECT reset_policy FROM document_register WHERE id = %s", (register_id,)).fetchone()[0]
        period = str(local.year) if reset == "YEARLY" else "ALL"
        fmt = conn.execute("SELECT id, format_pattern, symbol, seq_min_digits FROM document_register_format WHERE document_register_id = %s AND series = %s AND effective_from <= %s "
                           "ORDER BY effective_from DESC LIMIT 1", (register_id, series, now)).fetchone()
        if fmt is None:
            raise NoFormat
        format_id, pattern, symbol, min_digits = fmt
        conn.execute("INSERT INTO document_register_counter (document_register_id, series, period_key) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (register_id, series, period))
        seq = conn.execute("UPDATE document_register_counter SET next_seq = next_seq + 1, updated_at = now() WHERE document_register_id = %s AND series = %s AND period_key = %s "
                           "RETURNING next_seq - 1", (register_id, series, period)).fetchone()[0]  # một câu: khoá dòng bộ đếm tới commit
        number = render_number(pattern, seq=seq, min_digits=min_digits, year=local.year, symbol=symbol)
        entry_id = uuid.uuid4()
        try:
            with conn.transaction():  # savepoint: trùng chuỗi số làm hỏng giao dịch ngoài — và `seq` vừa tăng cũng lăn theo
                conn.execute("INSERT INTO document_register_entry (id, document_register_id, series, period_key, seq, formatted_number, format_id, document_id, issue_decision_id) "
                             "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", (entry_id, register_id, series, period, seq, number, format_id, document_id, issue_decision_id))
        except psycopg.errors.UniqueViolation as e:
            if e.diag.constraint_name == "uq_register_entry_number":
                raise NumberFormatCollision from None
            raise
        audit.record(conn, ctx, action="document.number_assign", entity_type="document", entity_id=document_id, request_id=request_id, document_id=document_id, decision_record_id=issue_decision_id,
                     payload={"entry_id": str(entry_id), "series": series, "period_key": period, "seq": seq})
        return NumberAssigned(entry_id, seq, number, series, period, local.date(), created=True)


def document_number_void(pool: Pool, ctx: ToolContext, *, entry_id: uuid.UUID, reason_code: str) -> None:
    """Chuyển một số sang `VOIDED` kèm lý do — số **không bao giờ tái sử dụng**. Chỉ từ `ASSIGNED`, và không khi số đang gắn với `document` đã `ISSUED`
    (`ck_document_issued_complete` chỉ bảo đảm `ISSUED` luôn trỏ tới một dòng sổ; chặn việc huỷ số của văn bản đã phát hành là việc của hàm này — mục Nguyên tắc dữ liệu của 04-data.md)."""
    require_system(ctx)
    if not _REASON.match(reason_code):
        raise ValueError("reason_code")  # chỉ mã — không văn bản tự do, không giá trị
    with pool.acquire() as conn, unit_of_work(conn):
        row = conn.execute("SELECT e.status, e.document_id, d.request_id, d.issued_register_entry_id FROM document_register_entry e JOIN document d ON d.id = e.document_id WHERE e.id = %s "
                           "FOR UPDATE OF e", (entry_id,)).fetchone()
        if row is None:
            raise EntryNotFound
        status, document_id, request_id, issued_entry = row
        if status != "ASSIGNED" or issued_entry == entry_id:
            raise NotVoidable
        conn.execute("UPDATE document_register_entry SET status = 'VOIDED', voided_at = now(), void_reason = %s WHERE id = %s", (reason_code, entry_id))
        audit.record(conn, ctx, action="document.number_void", entity_type="document", entity_id=document_id, request_id=request_id, document_id=document_id,
                     payload={"entry_id": str(entry_id), "reason_code": reason_code}, severity="WARNING")


def document_number_void_open(pool: Pool, ctx: ToolContext, *, document_id: uuid.UUID, reason_code: str) -> uuid.UUID | None:
    """Số `ASSIGNED` đang mở của `document` → `VOIDED` kèm `reason_code`; trả id dòng sổ đã huỷ, hoặc `None` nếu không có gì để huỷ. Khoá hàng `document` trước, như `document_number_assign`."""
    require_system(ctx)
    if not _REASON.match(reason_code):
        raise ValueError("reason_code")
    with pool.acquire() as conn, unit_of_work(conn):
        doc = conn.execute("SELECT request_id, status FROM document WHERE id = %s FOR UPDATE", (document_id,)).fetchone()
        if doc is None:
            raise DocumentNotFound
        request_id, status = doc
        if status == "ISSUED":
            return None  # đã phát hành: số đang gắn với văn bản, không bao giờ huỷ ở đây (`NOT_VOIDABLE` của `document_number_void`)
        entry = conn.execute("SELECT id FROM document_register_entry WHERE document_id = %s AND status = 'ASSIGNED' FOR UPDATE", (document_id,)).fetchone()
        if entry is None:
            return None
        conn.execute("UPDATE document_register_entry SET status = 'VOIDED', voided_at = now(), void_reason = %s WHERE id = %s", (reason_code, entry[0]))
        audit.record(conn, ctx, action="document.number_void", entity_type="document", entity_id=document_id, request_id=request_id, document_id=document_id,
                     payload={"entry_id": str(entry[0]), "reason_code": reason_code}, severity="WARNING")
        return entry[0]
