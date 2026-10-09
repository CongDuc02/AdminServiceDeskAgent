"""Nhãn tiếng Việt của trạng thái `request` — danh mục phía server duy nhất (S2 của `proposals/reply-templates.md`, PO duyệt 2026-10-09; mục Quy ước chung của `05-api.md`).

`client` không giữ bản sao thứ hai và không hiển thị mã trần (NFR-04). Câu chữ do người triển khai (Claude) soạn; PO sửa trước UAT.
"""
from __future__ import annotations

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
