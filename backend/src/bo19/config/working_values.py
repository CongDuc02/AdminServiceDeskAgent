"""Giá trị làm việc không phải biến môi trường — mỗi hằng một nguồn và nhãn "chưa hiệu chỉnh".

Khác `settings.py`: những giá trị này không có bước kiểm khởi động nào đòi chúng và không có biến để đặt trên Render
(kế hoạch B3, PO 2026-10-05: không thêm biến môi trường). Đổi một giá trị là đổi mã kèm `CHANGELOG.md`.
Nguồn: `docs/design/proposals/sprint1-working-values-a031-a048.md`, trừ khi ghi khác.
"""
from __future__ import annotations

# WV-12 — rate limit đăng nhập: cửa sổ cố định, ngưỡng mỗi `scope` `login_ip:{ip}`. Bộ đếm tăng ở mọi lần thử, kể cả lần đúng.
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 15 * 60
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 20

# O1-10 (PO duyệt 2026-10-09, `proposals/login-body-limits.md`) — giới hạn đầu vào của `POST /auth/session`. **Ba con số là đề xuất của người triển khai, chưa có căn cứ nguồn**
# (nhãn "chưa hiệu chỉnh"); `contracts/openapi.yaml` ghi 64 và 128 — `tests/test_login_limits.py` đối chiếu. Thay khi tổ chức có chính sách mật khẩu hay định dạng mã nhân viên.
LOGIN_EMPLOYEE_CODE_MAX_LENGTH = 64
LOGIN_PASSWORD_MAX_LENGTH = 128
LOGIN_BODY_MAX_BYTES = 4096

# `job.max_attempts` theo `job_type` — mục Retry, backoff và job lỗi vĩnh viễn của 11-ops.md, nhãn "chưa hiệu chỉnh" (A-031).
JOB_MAX_ATTEMPTS = {"render_document": 5, "resume_document_graph": 5, "finalize_issue": 5, "checkpoint_purge": 5, "notification_send": 5, "procedure_ingest": 3}
# Backoff `base × 2^attempts` (giây; `attempts` đã tăng lúc giành job) — cùng bảng mục Retry của 11-ops.md, "chưa hiệu chỉnh" (A-031). Thuộc `tool_layer.jobs`.
JOB_BACKOFF_BASE_S = {"render_document": 10, "resume_document_graph": 10, "finalize_issue": 10, "checkpoint_purge": 10, "notification_send": 10, "procedure_ingest": 30}
# WV-20 (PO duyệt 2026-10-13, B8a; "chưa hiệu chỉnh") — lease của job `RUNNING` và chu kỳ `heartbeat` (một phần ba lease). WV-21 — chu kỳ poll của `queue_worker`. WV-22 — số job một worker chạy cùng lúc.
JOB_LEASE_S = 120
JOB_HEARTBEAT_S = 40
JOB_POLL_S = 2
WORKER_CONCURRENCY = 1

# WV-15 — số ký tự tối đa của MỘT tin nhắn trong chat (A-031; roadmap O1-1: giữ 2.000). `chat_message_append` chặn lần cuối; `api` chặn ở `TurnBody`.
CHAT_MESSAGE_MAX_CHARS = 2000
# Trần body của `POST /chat-sessions/{id}/turns` (PO duyệt 2026-10-12, `proposals/turn-body-limit.md`). Tin hợp lệ lớn nhất là 2000 code point **sau NFC**; tiếng Việt viết ở dạng NFD thì một ký tự NFC
# thành tới 3 code point (chữ gốc + hai dấu tổ hợp), mỗi code point mã hoá JSON dạng `\uXXXX` = 6 byte → 18 byte mỗi ký tự; 1024 byte dư cho khung `{"text":"…"}` và khoảng trắng. Chưa hiệu chỉnh; đi theo WV-15.
TURN_BODY_MAX_BYTES = CHAT_MESSAGE_MAX_CHARS * 18 + 1024

# WV-14 — `limit` phân trang: mặc định 20, trần 100 (mục Phân trang của 05-api.md; chưa hiệu chỉnh — kích thước hàng đợi thật là A-002).
PAGE_LIMIT_DEFAULT = 20
PAGE_LIMIT_MAX = 100

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

# WV-23 (B8b; "chưa hiệu chỉnh") — hạn chuyển đổi `.docx` → `.pdf` của MỘT lần `soffice` (timeout của lớp tool chuyển đổi file, ADR-015, A-031). Đo thật trên image với `--cpus` của gói Free: báo cáo B8b.
RENDER_CONVERT_TIMEOUT_S = 120
# WV-24 (B8b; "chưa hiệu chỉnh") — trần kích thước MỘT object đọc vào bộ nhớ để kiểm checksum trước byte đầu tiên (`storage.fetch`, `stored_file_fetch`). Phép tính theo RAM của gói Free: báo cáo B8b.
FILE_FETCH_MAX_BYTES = 8 * 1024 * 1024
# WV-25 (B8b; "chưa hiệu chỉnh") — hạn của bước kiểm khởi động #6 (`soffice --headless` khởi động được, lần đầu có thể nạp cache): giây.
SOFFICE_STARTUP_CHECK_TIMEOUT_S = 90

# WV-26 đến WV-30 (B8c; PO 2026-10-13, O1-18; "chưa hiệu chỉnh") — tải file qua tệp tạm (`storage.fetch_verified`, endpoint tải file). WV-27, WV-28, WV-29 do PO chỉ định/duyệt; WV-26, WV-30 do người triển khai chọn.
FILE_FETCH_CHUNK_BYTES = 256 * 1024  # WV-26 — một khối khi tải object về tệp tạm và khi stream ra client
FILE_FETCH_MAX_CONCURRENT = 4  # WV-27 — số lượt tải đồng thời tối đa trong một tiến trình `api`; giữ suốt lượt (tải + stream)
FILE_FETCH_WAIT_S = 15  # WV-28 — chờ chỗ khi đủ WV-27 lượt; hết hạn thì 503 FILE_UNAVAILABLE kèm Retry-After
FILE_FETCH_DEADLINE_S = 60  # WV-29 — hạn chót tổng một lượt tải, tính từ lúc có chỗ, bao cả pha stream
FILE_FETCH_RETRY_AFTER_S = 5  # WV-30 — giá trị header Retry-After của 503 "bận"
