# ADR-010 — Resume graph sau quyết định của người thật qua job ghi cùng giao dịch

**Trạng thái:** Accepted · **Ngày:** 2026-09-12 · **Quyết định tại:** Phase 3 — Agent & Tool Architecture · **Liên quan:** ADR-004, ADR-005, mục Component diagram và sequence diagram (c) của `02-architecture.md`

---

## Context

`document_graph` dừng ở `interrupt` tại mỗi điểm chờ người thật (duyệt nội dung, ký, đóng dấu, phát hành, nhân viên gửi lại). Quyết định của người đi vào qua `api` → `tool_layer`: kiểm permission, chuyển trạng thái, ghi `audit_event`. Sau đó graph phải được resume để chạy tiếp các node tất định.

Sequence diagram (c) của `02-architecture.md` vẽ `tool_layer` gọi thẳng `orchestrator` để resume. Nhưng component diagram của cùng file có cạnh `orchestrator → tool_layer` và **không** có cạnh ngược lại. Vẽ theo (c) nghĩa là tạo vòng phụ thuộc `orchestrator → tool_layer → orchestrator`, trái với cam kết "không tồn tại vòng phụ thuộc".

## Options

**A — `tool_layer` gọi `orchestrator` để resume** (như sequence diagram (c) đang vẽ).

**B — `api` gọi `orchestrator` resume** ngay sau khi `tool_layer` commit.

**C — `tool_layer` ghi một job resume vào bảng job trong cùng giao dịch với việc chuyển trạng thái; `queue_worker` lấy job và resume graph.**

## Decision

**Chọn C.**

- Mọi thao tác cổng (danh sách ở mục Tool Registry của `03-agents.md`) ghi trong **cùng một giao dịch**: chuyển trạng thái, `audit_event`, và một job `resume_document_graph` mang `document_id` cùng id bản ghi quyết định.
- `queue_worker` resume thread `document:{document_id}` với payload chỉ gồm tham chiếu. Node đầu tiên sau `interrupt` **đọc lại trạng thái từ DB**. DB là nguồn sự thật; payload resume chỉ là tín hiệu đánh thức.
- Resume là idempotent: nếu graph đã qua điểm `interrupt` tương ứng, job kết thúc mà không làm gì.

## Consequences

**Tích cực**

- Không có vòng phụ thuộc: `tool_layer` chỉ ghi `postgresql`, `queue_worker` gọi `orchestrator` — hai cạnh đã có trong component diagram.
- Quyết định của người và việc lên lịch bước tiếp theo nguyên tử với nhau, cùng lý do ADR-004 dùng cho D-010. Không có thread nào kẹt vĩnh viễn ở `interrupt` vì tiến trình chết giữa commit và resume.
- Luồng request của `api` không phải chờ graph chạy tiếp (liên quan A-025).

**Tiêu cực và cái phải chấp nhận**

- Có độ trễ bằng một chu kỳ poll giữa quyết định của người và trạng thái kế tiếp (ví dụ `APPROVED → PENDING_SIGNATURE`). Chấp nhận được vì bước kế tiếp cũng chờ người.
- Sequence diagram (c) của `02-architecture.md` đang vẽ hướng gọi không khớp ADR này — xem Open Questions của `03-agents.md`.

**Điều kiện đảo ngược** — đo ở `observability`, dùng lại metric đã yêu cầu cho ADR-004: độ trễ từ lúc enqueue tới lúc bắt đầu xử lý, **tách riêng loại job `resume_document_graph`**. Nếu độ trễ này thành thứ người dùng phàn nàn, thì phần phải xét lại là chu kỳ poll của ADR-004, không phải quay về Option A hay B.

## Rejected alternatives

**A — `tool_layer` gọi `orchestrator`.** Bị loại vì tạo vòng phụ thuộc giữa hai thành phần, trái với component diagram đã chốt ở Phase 2 — một lỗi cấu trúc, không phải một đánh đổi.

**B — `api` resume sau commit.** Không tạo vòng (`api → orchestrator` đã có), nhưng không nguyên tử: tiến trình `api` chết sau commit và trước resume thì document nằm ở trạng thái mới trong DB, còn graph vẫn chờ ở `interrupt` cũ. Muốn vá thì phải thêm một bộ quét đối soát — tức tự dựng lại cái bảng job đã có sẵn. Cùng lý do ADR-004 loại Redis.
