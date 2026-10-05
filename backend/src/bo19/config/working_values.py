"""Giá trị làm việc không phải biến môi trường — mỗi hằng một nguồn và nhãn "chưa hiệu chỉnh".

Khác `settings.py`: những giá trị này không có bước kiểm khởi động nào đòi chúng và không có biến để đặt trên Render
(kế hoạch B3, PO 2026-10-05: không thêm biến môi trường). Đổi một giá trị là đổi mã kèm `CHANGELOG.md`.
Nguồn: `docs/design/proposals/sprint1-working-values-a031-a048.md`, trừ khi ghi khác.
"""
from __future__ import annotations

# WV-12 — rate limit đăng nhập: cửa sổ cố định, ngưỡng mỗi `scope` `login_ip:{ip}`. Bộ đếm tăng ở mọi lần thử, kể cả lần đúng.
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 15 * 60
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 20

# WV-16b — trần số lần verify `argon2id` đồng thời trong MỘT tiến trình (ADR-034). Lần thứ năm chờ.
ARGON2_MAX_CONCURRENT_VERIFY = 4

# WV-17 — token phiên: 8 giờ, tính tuyệt đối, không gia hạn trượt.
SESSION_TOKEN_TTL_SECONDS = 8 * 60 * 60

# WV-07 — timeout lớp tool chỉ chạm `postgresql`: dùng làm thời gian chờ mượn connection của nghiệp vụ.
POOL_ACQUIRE_TIMEOUT_SECONDS = 5

# A-057 còn mở — kích thước pool phía `api` chưa có căn cứ: giá trị TẠM để chạy được, không phải số đã xác minh.
POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 5
