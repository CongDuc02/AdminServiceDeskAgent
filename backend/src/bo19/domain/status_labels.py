"""Nhãn tiếng Việt của trạng thái `request` — danh mục phía server duy nhất (S2 của `proposals/reply-templates.md`, PO duyệt 2026-10-09; mục Quy ước chung của `05-api.md`).

`client` không giữ bản sao thứ hai và không hiển thị mã trần (NFR-04). Câu chữ do người triển khai (Claude) soạn; PO sửa trước UAT.
"""
from __future__ import annotations

from bo19.domain.document_machine import DOCUMENT_STATUSES
from bo19.domain.request_machine import REQUEST_STATUSES

REQUEST_STATUS_LABELS: dict[str, str] = {
    "DRAFT": "Đang soạn",
    "NEEDS_INFO": "Cần bổ sung thông tin",
    "SUBMITTED": "Đã gửi, chờ tiếp nhận",
    "IN_REVIEW": "Đang được xem xét",
    "CHANGES_REQUESTED": "Cần chỉnh sửa",
    "APPROVED": "Đã ký, đang hoàn tất",
    "FULFILLED": "Đã hoàn tất",
    "REJECTED": "Bị từ chối",
    "CANCELLED": "Đã huỷ",
    "EXPIRED": "Đã hết hạn",
}
assert tuple(REQUEST_STATUS_LABELS) == REQUEST_STATUSES  # thêm trạng thái mà quên nhãn thì import đã hỏng


def request_status_label(code: str) -> str:
    return REQUEST_STATUS_LABELS[code]


# Nhãn của `document` (B9b1, mục 1.2 của 05-api.md: `status_label` do server tính theo cặp (`status`, `issue_in_progress`)). Hai đoạn của khoảng hoàn tất phát hành hiện giống hệt nhau (mục Duyệt dấu và khoảng hoàn tất
# phát hành của 08-hitl.md). Câu chữ do người triển khai soạn; PO sửa trước UAT.
DOCUMENT_STATUS_LABELS: dict[str, str] = {
    "DRAFT": "Đang soạn văn bản",
    "PENDING_APPROVAL": "Chờ duyệt nội dung",
    "CHANGES_REQUESTED": "Cần chỉnh sửa",
    "REJECTED": "Bị từ chối",
    "APPROVED": "Đã duyệt nội dung, chờ ký",
    "PENDING_SIGNATURE": "Chờ ký",
    "SIGNED": "Đã ký, chờ phát hành",
    "PENDING_SEAL": "Chờ đóng dấu",
    "SEALED": "Đã đóng dấu, chờ phát hành",
    "ISSUED": "Đã phát hành",
    "REVOKED": "Đã thu hồi",
    "SUPERSEDED": "Đã được thay thế",
    "ARCHIVED": "Đã lưu trữ",
}
assert tuple(DOCUMENT_STATUS_LABELS) == DOCUMENT_STATUSES
ISSUE_IN_PROGRESS_LABEL = "Đang cấp số và phát hành"


def document_status_label(status: str, issue_in_progress: bool = False) -> str:
    return ISSUE_IN_PROGRESS_LABEL if issue_in_progress else DOCUMENT_STATUS_LABELS[status]
