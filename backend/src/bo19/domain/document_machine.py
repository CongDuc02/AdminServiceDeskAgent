"""Máy trạng thái của `document` — bảng chuyển dạng thuần, không IO (mục Vòng đời `document` của 00-domain.md; GLOSSARY.md, mục Trạng thái document).

Đủ mười ba trạng thái và mọi cạnh của sơ đồ. `tool_layer.kernel.transition` đọc bảng này; nó là nơi duy nhất sinh câu `UPDATE` đổi `document.status`. `tests/test_document_machine.py` đọc lại sơ đồ Mermaid
của 00-domain.md và đòi bảng khớp từng cạnh.

**Bảng cạnh không phải giấy phép dùng cạnh:** nhiều cạnh đòi cột đi kèm mà kernel chưa đặt (`approved_*` ở `APPROVED`, `signer_employee_id` ở `PENDING_SIGNATURE`, `issued_*` ở `ISSUED`, `archived_*` ở `ARCHIVED`);
ràng buộc `CHECK` của DB từ chối cạnh đó nếu thiếu cột. B9a chỉ dùng hai cạnh: tạo `DRAFT` (không phải một cạnh) và `DRAFT → PENDING_APPROVAL`. Cạnh nào cần cột thì lát dùng cạnh đó mở rộng `TableSpec` của kernel.
"""
from __future__ import annotations

DOCUMENT_STATUSES = ("DRAFT", "PENDING_APPROVAL", "CHANGES_REQUESTED", "REJECTED", "APPROVED", "PENDING_SIGNATURE", "SIGNED", "PENDING_SEAL", "SEALED", "ISSUED", "REVOKED", "SUPERSEDED", "ARCHIVED")

# Cạnh của sơ đồ — mỗi dòng một trạng thái nguồn, theo thứ tự xuất hiện ở sơ đồ.
DOCUMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"PENDING_APPROVAL", "ARCHIVED"}),
    "PENDING_APPROVAL": frozenset({"CHANGES_REQUESTED", "REJECTED", "APPROVED"}),
    "CHANGES_REQUESTED": frozenset({"DRAFT", "ARCHIVED"}),
    "REJECTED": frozenset({"ARCHIVED"}),
    "APPROVED": frozenset({"PENDING_SIGNATURE", "ARCHIVED"}),
    "PENDING_SIGNATURE": frozenset({"CHANGES_REQUESTED", "SIGNED"}),
    "SIGNED": frozenset({"PENDING_SEAL", "ISSUED"}),
    "PENDING_SEAL": frozenset({"SEALED"}),
    "SEALED": frozenset({"ISSUED"}),
    "ISSUED": frozenset({"REVOKED", "SUPERSEDED", "ARCHIVED"}),
    "REVOKED": frozenset({"ARCHIVED"}),
    "SUPERSEDED": frozenset({"ARCHIVED"}),
    "ARCHIVED": frozenset(),
}

DOCUMENT_TERMINAL = frozenset({"ARCHIVED"})


def can_transition(source: str, target: str) -> bool:
    return target in DOCUMENT_TRANSITIONS.get(source, frozenset())
