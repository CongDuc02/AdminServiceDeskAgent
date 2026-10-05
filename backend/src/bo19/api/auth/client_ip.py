"""IP của client cho rate limit đăng nhập — **một hàm duy nhất** (mục Rate limit của 09-security.md; A-062, cổng 2.7 của 12-roadmap.md).

Mặc định **không tin** `X-Forwarded-For` hay bất kỳ header nào: header là thứ client tự đặt được, và tin nó thì kẻ tấn công đổi IP ở mỗi lần thử để
vượt ngưỡng. Hàm dùng địa chỉ của kết nối TCP trực tiếp — `request.client`. `entrypoints.api_main` chạy uvicorn với `proxy_headers=False`
để không có chỗ nào khác viết lại giá trị đó.

Hệ quả thật, nói thẳng: phía sau proxy của Render, địa chỉ kết nối trực tiếp là của proxy — mọi người dùng chung một ngưỡng (WV-12). Chấp nhận ở B3 vì chưa có
người dùng thật. Cách đọc đúng IP phía sau proxy là A-062 (`[CẦN XÁC MINH]`: header nào, vị trí nào trong chuỗi khi có nhiều proxy), đóng ở cổng 2.7, AC-2.9.
Khi đó chỉ sửa **hàm này**.
"""
from __future__ import annotations

from fastapi import Request

UNKNOWN = "unknown"  # không có địa chỉ (không xảy ra với kết nối TCP thật) — dồn vào một ngưỡng chung, không bỏ qua rate limit


def client_ip(request: Request) -> str:
    client = request.client
    return client.host if client is not None and client.host else UNKNOWN
