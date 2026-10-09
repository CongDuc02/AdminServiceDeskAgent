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

# WV-04 / WV-06 — HẠN CHÓT TỔNG của một lời gọi `ai_gateway.call` (PO, 2026-10-05): bao mọi lần thử, quãng nghỉ WV-05 và mọi lần chờ `retry-after`.
LLM_CALL_DEADLINE_CHEAP_SECONDS = 8
LLM_CALL_DEADLINE_STRONG_SECONDS = 60
# WV-05 — một lần thử lại (tổng hai lần gọi), nghỉ cố định 1 s.
LLM_RETRY_COUNT = 1
LLM_RETRY_PAUSE_SECONDS = 1
# WV-19 — `retry-after` của 429 vượt ngưỡng này thì không chờ (coi là hết hạn mức theo ngày). Trong lượt chat WV-02 đã chặn mọi lần chờ.
LLM_RETRY_AFTER_CEILING_SECONDS = 120

# Trần budget (mục Định cỡ A-022 của 11-ops.md, mục 10.2 và 10.4) — bước kiểm khởi động #5. Nhãn: "chưa hiệu chỉnh" (A-031), trừ khi ghi "cận trên cứng".
# Trần MỖI LỜI GỌI chưa chặn được trước lời gọi (A-090): B4 chỉ đo và cảnh báo. Trần theo CHỦ BUDGET (chat_session, request) chặn.
TOKEN_CEILING_PER_CALL = {
    "classify_intent": 1800,  # đo thật (B4b): `prompt_tokens` 1.640–1.642 trên tin nhắn trần 2.000 ký tự có dấu + ~10% (PO, 2026-10-05) — O1-1 đã đóng
    "extract_slots": 3500,  # ước lượng
    "select_procedure_passages": 6000,  # ước lượng
    "embed_query": 500,  # ước lượng có căn cứ
    "draft_free_content": 4000,  # cận trên cứng
    "revise_free_content": 4000,  # cận trên cứng
}
TOKEN_CEILING_CHAT_SESSION = 51_900  # 3×5×1.800 + 3×1.800 + 3×6.500 (mục 10.4; P1 1.800, PO 2026-10-05; trước đó 46.500)
TOKEN_CEILING_REQUEST = 92_000  # 64.000 (drafting, cận trên cứng) + 27.700 (intake, điển hình) = 91.700, làm tròn lên bội của 2.000 (mục 10.2)
CHANGES_REQUESTED_MAX_ROUNDS = 3  # R — cận trên cứng (A-022, ADR-009)

# WV-07 — timeout lớp tool chỉ chạm `postgresql`: dùng làm thời gian chờ mượn connection của nghiệp vụ.
POOL_ACQUIRE_TIMEOUT_SECONDS = 5

# A-057 còn mở — kích thước pool phía `api` chưa có căn cứ: giá trị TẠM để chạy được, không phải số đã xác minh.
POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 5
