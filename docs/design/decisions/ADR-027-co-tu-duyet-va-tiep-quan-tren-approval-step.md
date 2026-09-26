# ADR-027 — Cờ tự duyệt và việc tiếp quản nằm trên `approval_step`

**Trạng thái:** Proposed · **Ngày:** 2026-09-26 · **Quyết định tại:** đợt sửa 3 sau Phase 13 (AUD-02 (d), AUD-23 (e)(f) của `13-audit.md`; A-044) · **Liên quan:** D-006 (mục Tách biệt trách nhiệm — quyết định D-006 của `00-domain.md`), ADR-010 (resume qua job), mục Duyệt và quyết định của `04-data.md`, mục Tách biệt trách nhiệm — D-006 và mục Tiếp quản sau `halt_for_human` của `08-hitl.md`, migration `0007_takeover_and_self_approval.sql`

---

## Context

D-006 điều kiện 2 ghi nguyên chỗ lưu: bản ghi tự duyệt mang cờ **`approval_step.self_approved = true`**. `GET /self-approvals` đọc đúng cờ đó qua `ix_approval_step_self_approved`. Nhưng `approval_step.step_kind` chỉ có `CONTENT_REVIEW`, `SIGNATURE`, `SEAL`, `BOOKING_CONFIRM`. Ba thao tác mà D-006 chặn không có bước nào để mang cờ:

- `document_issue` — contract đã nhận `self_approval_reason`, nhưng `ISSUE_ORDERED` không gắn bước nào (`ck_decision_record_step_kinds` không đòi).
- `document_revoke_initiate`, `document_revoke_confirm` — D-006 nói "cùng cơ chế áp dụng cho ràng buộc hai người ở bước thu hồi"; contract hôm nay trả `SEPARATION_OF_DUTIES_VIOLATION` và không có đường thoát (AUD-23 (f)).

Thao tác tiếp quản sau `halt_for_human` — chưa từng được thiết kế (AUD-02 (d)) — có một lối ra là từ chối yêu cầu, dùng `document.reject`, nên cũng thuộc D-006. Nó còn cần hai thứ nữa: một hàng đợi để người tiếp quản **tìm thấy** văn bản đang dừng (văn bản dừng ở `DRAFT` không nằm trong hàng đợi duyệt nào), và một khoá idempotency cho `document_halt_record` không gộp nhầm lần dừng thứ hai sau một lần thử lại (A-044).

## Options

- **A — Thêm loại bước trên `approval_step`.** `TAKEOVER` mở cùng giao dịch với `document_halt`; `REVOKE_CONFIRM` mở ở bước khởi tạo thu hồi; `ISSUE_ORDER`, `REVOKE_INITIATE` sinh ra đã `DECIDED` trong giao dịch của chính thao tác. `document_halt` trỏ tới bước `TAKEOVER` của nó.
- **B — Cột `self_approved`, `self_approval_reason` trên `decision_record`.** Mọi quyết định mang được cờ, không cần bước.
- **C — Bảng riêng `self_approval`** trỏ tới `decision_record`.
- **D — Giữ khoá `(document_id, at_node, revision_round)` của `document_halt`, thêm cột đếm số lần tiếp quản vào khoá** — lối A-044 tự gợi ý.

## Decision

**Chọn A.**

- D-006 điều kiện 2 giữ nguyên chữ: cờ nằm ở `approval_step`. `GET /self-approvals` và index của nó không đổi.
- Bước sinh ra đã `DECIDED` là chỗ mang cờ cho thao tác **không chờ ai** — lệnh phát hành, khởi tạo thu hồi. Nó không vào hàng đợi nào vì không bao giờ `OPEN`.
- Bước `TAKEOVER` `OPEN` **là** trạng thái "đang dừng": cờ `halted` = có bước `TAKEOVER` `OPEN`; hàng đợi tiếp quản đọc bước `OPEN` theo loại qua `ix_approval_step_open_by_kind`.
- Khoá idempotency của `document_halt_record` thành "bước `TAKEOVER` đang mở của `document`": có thì trả lại lần dừng của bước đó; không có thì tạo bước và lần dừng mới. `uq_approval_step_one_open` là lớp chặn ở DB. A-044 đóng theo hướng này, không theo D.
- `ck_decision_record_step_kinds` đòi `approval_step_id` với `ISSUE_ORDERED`, `TAKEOVER_RESOLVED`, `REVOKE_INITIATED`, `REVOKE_CONFIRMED`.

## Consequences

**Tích cực**

- Một chỗ duy nhất cho mọi lần tự duyệt, đúng như D-006 viết; mục tự duyệt riêng không phải gộp hai nguồn.
- Người tiếp quản có hàng đợi, có hạn (`due_at`) sẵn chỗ cho SLA khi A-002 đóng, có người được giao (`assignee_employee_id`) sẵn chỗ cho định tuyến.
- A-044 đóng mà không cần một bộ đếm do ứng dụng tự tính.

**Tiêu cực và cái phải chấp nhận**

- Nghĩa của `approval_step` giãn ra: từ "việc yêu cầu một người hành động" thành cả "chỗ ghi một hành động không chờ ai". Hai loại `ISSUE_ORDER`, `REVOKE_INITIATE` không bao giờ `OPEN` — `04-data.md` ghi rõ điều này để không ai dựng hàng đợi trên chúng.
- `document_issue` ghi thêm một dòng mỗi lần ra lệnh phát hành.
- `document_halt.takeover_step_id` là `NOT NULL`: migration `0007` chỉ áp được khi bảng rỗng — đúng ở mọi môi trường cho tới Sprint 2.

**Điều kiện đảo ngược**

- PO sửa D-006 để cờ tự duyệt không còn buộc vào `approval_step` — xét B.

## Rejected alternatives

**B — Cờ trên `decision_record`.** Đơn giản hơn cho thao tác không chờ ai, nhưng đổi chữ của D-006 điều kiện 2 — là đổi một quyết định đã chốt, không phải việc của một đợt sửa. Mục tự duyệt riêng sẽ phải đọc hai nguồn trong thời gian chuyển.

**C — Bảng `self_approval` riêng.** Thêm một bảng để giữ đúng hai cột, và vẫn lệch chữ của D-006 như B.

**D — Đếm số lần tiếp quản trong khoá.** Bộ đếm do ứng dụng tính lúc ghi; hai lần chạy lại của cùng một job có thể tính ra hai giá trị khác nhau nếu một lần tiếp quản commit ở giữa. A chặn bằng một ràng buộc DB đã có (`uq_approval_step_one_open`).
