"""Đoạn SQL dùng chung về cờ dẫn xuất của `document` (mục 1.2 và 4.4 của 04-data.md; ADR-041 mục 9) — một nơi định nghĩa cho `GET /documents/{id}`, hàng đợi và `GET /requests/{id}`.

Các đoạn này dùng bí danh `d` (`document`) và `o` (`decision_record` `ISSUE_ORDERED` mới nhất, nối bằng `LEFT JOIN LATERAL ({ORDER}) o ON true`). Chỉ đọc; hằng số, không nhận tham số.
"""
from __future__ import annotations

ORDER = "SELECT o.id, o.created_at FROM decision_record o WHERE o.document_id = d.id AND o.kind = 'ISSUE_ORDERED' ORDER BY o.created_at DESC, o.id DESC LIMIT 1"
# `issue_in_progress`: có lệnh phát hành mà `document` chưa `ISSUED` và lệnh chưa bỏ cuộc (số `VOIDED`, hay `document_halt` tại `finalize_issue` sau lệnh — mục 4.4 của 04-data.md)
ISSUE_IN_PROGRESS = (
    "(d.status IN ('SIGNED', 'SEALED') AND o.id IS NOT NULL "
    "AND NOT EXISTS (SELECT 1 FROM document_register_entry v WHERE v.document_id = d.id AND v.issue_decision_id = o.id AND v.status = 'VOIDED') "
    "AND NOT EXISTS (SELECT 1 FROM document_halt hh WHERE hh.document_id = d.id AND hh.at_node = 'finalize_issue' AND hh.created_at > o.created_at))"
)
# Số văn bản, ngày và bản `FINAL` chỉ từ `ISSUED` trở đi (mục Dữ liệu trong response của 05-api.md)
ISSUED_OR_LATER = "('ISSUED', 'REVOKED', 'SUPERSEDED', 'ARCHIVED')"
