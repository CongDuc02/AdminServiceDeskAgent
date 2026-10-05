"""Chống CSRF lớp thứ hai: header `X-BO19-CSRF` bắt buộc trên mọi lệnh không phải `GET` — kể cả đăng nhập (mục Xác thực và chống CSRF của 05-api.md).

Giá trị là chuỗi không rỗng bất kỳ; server chỉ kiểm sự có mặt. Lớp này không dựa vào bí mật mà vào việc một header tuỳ biến trên request khác origin
buộc trình duyệt hỏi trước (A-051). `HEAD` và `OPTIONS` không đổi trạng thái nên được miễn cùng `GET`; app không bật CORS nên preflight không có thật.
"""
from __future__ import annotations

from fastapi import Request

from bo19.api.errors import ApiError

CSRF_HEADER = "X-BO19-CSRF"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def require_csrf_header(request: Request) -> None:
    if request.method in _SAFE_METHODS:
        return
    if not request.headers.get(CSRF_HEADER, "").strip():
        raise ApiError("CSRF_HEADER_MISSING")
