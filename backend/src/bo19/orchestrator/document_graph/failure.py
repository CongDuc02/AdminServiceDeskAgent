"""Mã lỗi của `document_graph` ở Sprint 1: từ mã exception rời node sang `reason_code` của bảng mã `document_halt` và cách job xử lý (ADR-039 mục 5; mục Bảng mã của 08-hitl.md; mục 3.2 của 11-ops.md).

Ở Sprint 1 không có `halt_for_human`: lỗi làm job `FAILED`. Mã giữ **tên của bảng mã** để Sprint 2 đổi "ném lỗi" thành "dừng có kiểm soát" mà không đổi tên. `permanent` — thử lại không đổi được kết quả (job `FAILED` ngay);
không `permanent` — lỗi tạm, hàng đợi thử lại theo backoff. Mã lạ là `SYSTEM_DEFECT` thử lại được (có thể là lỗi tạm của hạ tầng); hết lượt thì `FAILED`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Failure:
    reason_code: str  # khớp `^[A-Z][A-Z0-9_]*$` của `job.last_error_code`
    permanent: bool


_TABLE: dict[str, Failure] = {}


def _add(failure: Failure, *codes: str) -> None:
    for c in codes:
        _TABLE[c] = failure


# ---- vĩnh viễn: thử lại cho cùng kết quả (và tốn lời gọi LLM) ----
_add(Failure("FREE_CONTENT_INVALID", True), "FREE_CONTENT_INVALID")
_add(Failure("PARSE_FAILED", True), "PARSE_FAILED")
_add(Failure("BUDGET_EXCEEDED", True), "BUDGET_EXCEEDED")
_add(Failure("REVIEW_NOT_READY", True), "REVIEW_NOT_READY", "NOT_READY")
_add(Failure("RENDER_INPUT_INVALID", True), "MISSING_VARIABLE", "UNKNOWN_VARIABLE", "INVALID_VARIABLE_VALUE", "TEMPLATE_UNREADABLE", "RENDER_INPUT_INVALID")
_add(Failure("NO_ELIGIBLE_SIGNER", True), "NO_ELIGIBLE_SIGNER")  # B9b1 (ADR-040 mục 7): không ai ký được — thử lại không đổi kết quả cho tới khi cấp `document.sign`; Sprint 2 là `halt_for_human`
_add(Failure("CONTENT_HASH_MISMATCH", True), "CONTENT_HASH_MISMATCH")  # B9b2 (INV-01): nội dung hiện hành khác nội dung đã duyệt — không có lối ra (A-077); dừng trước khi cấp số
_add(Failure("PLACEHOLDER_REMAINS", True), "PLACEHOLDER_REMAINS")  # bản FINAL còn dấu giữ chỗ (A-098): thử lại cho cùng kết quả
_add(Failure("TEMPLATE_NOT_ACTIVE", True), "TEMPLATE_NOT_ACTIVE", "NO_ACTIVE_TEMPLATE", "TEMPLATE_AMBIGUOUS", "TEMPLATE_VERSION_NOT_FOUND")
_add(Failure("FONT_MISSING", True), "FONT_MISSING")
_add(Failure("SYSTEM_DEFECT", True), "ALLOWLIST_REJECTED", "INPUT_INVALID", "SLOT_NOT_DECLARED", "BUDGET_OWNER_MISSING", "DECISION_NOT_FOUND", "NOT_DRAFT", "ROUND_MISMATCH",
     "UNSUPPORTED_DECISION", "NO_ISSUE_ORDER", "NO_REGISTER", "NO_FORMAT", "BAD_FORMAT", "NUMBER_FORMAT_COLLISION", "RENDER_NOT_FOUND", "DOCUMENT_NOT_FOUND", "DOCUMENT_CONFLICT", "REQUEST_NOT_FOUND", "REQUEST_NOT_SUBMITTED", "DRAFT_RENDER_NOT_FOUND", "ILLEGAL_TRANSITION", "STALE_STATUS", "THREAD_SCHEMA_MISMATCH",
     "THREAD_NOT_ACTIVE", "SYSTEM_ACTOR_REQUIRED", "AUDIT_INVALID", "SYSTEM_DEFECT")
# ---- tạm: thử lại theo backoff ----
_add(Failure("PROVIDER_UNAVAILABLE", False), "PROVIDER_RATE_LIMITED", "PROVIDER_CALL_FAILED")
_add(Failure("BUDGET_UNAVAILABLE", False), "BUDGET_UNAVAILABLE")
_add(Failure("RENDER_CONVERSION_FAILED", False), "CONVERSION_FAILED", "TIMEOUT")
_add(Failure("RENDER_CHECKSUM_MISMATCH", False), "STORAGE_WRITE_CONFLICT", "RENDER_CHECKSUM_MISMATCH")  # cũng là mã của `render_integrity_check` ở `route_signing` (B9b1)
_add(Failure("RENDER_OBJECT_MISSING", False), "RENDER_OBJECT_MISSING", "FILE_UNAVAILABLE")
_add(Failure("STORAGE_CLAIM_BUSY", False), "CLAIM_HELD", "CLAIM_STALE", "CLAIM_LEASE_EXPIRED", "CLAIM_LOST")
_add(Failure("JOB_CANCELLED", False), "JOB_CANCELLED")

UNKNOWN = Failure("SYSTEM_DEFECT", False)


def classify(code: str) -> Failure:
    """`code` có thể mang hậu tố `:xyz` của biên node — chỉ phần đầu quyết định."""
    return _TABLE.get(code.split(":", 1)[0], UNKNOWN)
