# ADR-039 — `document_graph` lát B9a: id `document` xác định theo `request`, `run_render` tạo `DRAFT` rồi chạy graph, thử lại tiếp tục từ checkpoint, lỗi Sprint 1 là job `FAILED` mang mã halt

**Trạng thái:** Accepted · **Duyệt:** PO, 2026-10-13 (kế hoạch B9a — phần B, kèm điểm dừng resume sau khởi động lại; ba điểm lệch kế hoạch ở mục Decision 2, 6, 7 được **báo ở báo cáo cuối lát để PO xác nhận**) · **Ngày:** 2026-10-13 · **Quyết định tại:** BUILD MODE, B9a, trước mã `document_graph` · **Liên quan:** ADR-004 (job ít nhất một lần), ADR-005, ADR-008 (state chỉ mang tham chiếu), ADR-009 (một biến một lời gọi, dấu vân tay input), ADR-010 (resume qua job), ADR-016, ADR-019, D-010, INV-01, A-097, A-098 · **Nguồn:** mục `document_graph` và Tool Registry của `03-agents.md`; mục Bảng mã của `08-hitl.md`; deliverable `document_graph` của Sprint 1 trong `12-roadmap.md`

---

## Context

Thiết kế vẽ `prepare_draft` (tạo `DRAFT`) là node đầu của `document_graph`, và thread theo `document` (`document:{document_id}`). Ba điều làm hai câu ấy không đứng cùng nhau:

1. `graph_thread` có khoá ngoại `document_id` và `ck_graph_thread_document_id` đòi `thread_id = 'document:' || document_id` — thread chỉ tồn tại sau khi `document` có dòng, mà graph chưa chạy nên node chưa tạo được.
2. Job `render_document` chạy **ít nhất một lần** (ADR-004). Một lần thử hỏng giữa chừng rồi thử lại không được tạo `document` thứ hai, không được gọi LLM lại cho biến đã sinh xong, không được dựng lại graph từ đầu trên checkpoint đã có.
3. Roadmap (deliverable `document_graph`, Sprint 1): `reopen_draft` và `halt_for_human` thuộc Sprint 2; ở Sprint 1 lỗi làm **job `FAILED`**.

Bốn khoảng trống của thiết kế mà lát này buộc phải đóng bằng một mặc định có lý do (không bịa số, không mở rộng phạm vi): (a) bản nháp hiển thị gì ở biến *điền sau duyệt* (A-098); (b) khoá của dấu vân tay input của ADR-009 (A-097); (c) ai mở bước `approval_step` loại `CONTENT_REVIEW` mà thao tác cổng của B9b cần (`decision_record` loại `APPROVED` đòi `approval_step_id`); (d) cách định dạng giá trị `DIRECT_SLOT` kiểu `DATE` (A-098).

## Options

- **A — Tạo `document` trong node `prepare_draft`** với id ngẫu nhiên; thread id tạo sau.
- **B — `document_id` xác định theo `request` (`uuid5`); `DocumentRunner.run_render` tạo `DRAFT` (idempotent) rồi mở thread rồi chạy graph; `prepare_draft` đọc lại và dựng state.**
- **C — Thread theo `request`** thay vì theo `document`.
- **D — Khi lỗi, job `SUCCEEDED` và ghi lỗi vào một bảng khác.**

## Decision

**Chọn B**, với các điểm sau.

1. **`document_id = uuid5(NAMESPACE_DOCUMENT, request_id)`** cho `document` đầu tiên của một `request`. `document` thay thế (`supersedes_document_id`, `[Should]`) sẽ có id riêng khi được dựng; lát này không có.
2. **`run_render` làm ba việc ngoài graph, theo thứ tự:** `template_fetch` (chọn phiên bản `ACTIVE`) → `document_transition` tạo `DRAFT` (idempotent theo id; ghim `operating_mode` hiện hành, `template_version_id`, `requires_seal`/`seal_type` theo mặc định của `request_type`) → `graph_thread` (ghi bởi lớp chạy graph, không bởi node) → `graph.invoke`. **Lệch thiết kế một chỗ:** việc *tạo* `DRAFT` do `run_render` làm, không phải node `prepare_draft`; node này giữ phần còn lại (đọc lại phiên bản template đã ghim, dựng `free_content_variables`, `pending_targets`). Bản chất không đổi: tool `document_transition` tạo `DRAFT`, hệ thống là tác nhân, trước cổng 1.
3. **Thử lại tiếp tục từ checkpoint.** `run_render` đọc `snapshot` của thread: chưa có → input ban đầu; đang chờ ở `await_content_review` hoặc đã `END` → không làm gì (job thành công, không gọi lại tool nào); còn dở → `invoke(None)` tiếp từ checkpoint cuối. Mọi tool idempotent theo khoá của nó (`docx_render`/`pdf_export` theo khoá input, `document_draft_save` theo `UNIQUE (document, biến, vòng, lần)`).
4. **Văn bản LLM không vào state** (ADR-008). Output của `draft_free_content` nằm ở `scratch` của lần chạy trong tiến trình; `validate_free_content` đọc từ đó rồi ghi `document_free_content`. Mất `scratch` (tiến trình chết giữa hai node) thì `validate_free_content` không có gì để kiểm và đưa về `draft_free_content` **mà không tính vào `regenerated_variables`** — mất một lời gọi, không mất đúng đắn.
5. **Lỗi ở Sprint 1 = job `FAILED` kèm mã** (roadmap). Node ném `NodeError(mã)` — mã là `reason_code` của bảng mã `document_halt` (mục Bảng mã của `08-hitl.md`) để Sprint 2 đổi "ném lỗi" thành `halt_for_human` mà không đổi tên mã. Handler đổi mã thành `JobFailure`: lỗi **tạm** (provider không với tới, 429, chuyển đổi hỏng/quá hạn, storage không với tới, claim đang giữ) thử lại theo backoff của hàng đợi; lỗi **vĩnh viễn** (`FREE_CONTENT_INVALID`, `PARSE_FAILED`, `BUDGET_*`, `REVIEW_NOT_READY`, `RENDER_INPUT_INVALID`, `TEMPLATE_NOT_ACTIVE`, `FONT_MISSING`, `SYSTEM_DEFECT`) làm job `FAILED` ngay (`JobFailure(permanent=True)`; `jobs.fail` thêm tham số `permanent`) — thử lại không đổi được kết quả và tốn lời gọi LLM.
5b. **Sinh lại đúng một lần** (`regenerated_variables`) vẫn đúng như thiết kế: biến trượt `validate_free_content` lần đầu được sinh lại một lần; trượt lần hai thì `FREE_CONTENT_INVALID` (Sprint 1: job `FAILED`).
6. **`interrupt` qua mặt tiền hẹp.** Chỉ `orchestrator.runtime` import `langgraph`: `runtime.builder` thêm `wait_for_human(payload)` (bọc `interrupt`) và `Graph.resume(thread_id, value)`, `Graph.snapshot(thread_id)` (state, node kế, có đang chờ không). `await_content_review` ghi `graph_thread` `WAITING` / `waiting_at_node = 'await_content_review'` ở lớp chạy graph. Payload `interrupt` và giá trị resume chỉ mang id (ADR-008).
   **Node `route_review` tối thiểu (lệch kế hoạch — để chứng minh điểm dừng resume):** sau resume, đọc `decision_record` theo `decision_record_id` trong payload, kiểm nó thuộc `document` này, rồi ghi `last_signal` (`kind`, `decision_record_id`) và kết thúc graph. **Bốn nhánh thật** (`APPROVED` → phần 2, `REJECTED`, `FREE_CONTENT`, `SLOT_DATA`) là B9b. Không có node nào sau `route_review` ở lát này.
7. **Bước `CONTENT_REVIEW` mở lúc vào `PENDING_APPROVAL`.** `document_transition` (`DRAFT → PENDING_APPROVAL`) mở `approval_step` `CONTENT_REVIEW` `OPEN` trong cùng giao dịch, gắn `current_draft_render_id`, và đưa `request` `SUBMITTED → IN_REVIEW` (mục Tool Registry đã nói vế cuối). Thiết kế chưa nói ai mở bước này; thao tác cổng B9b cần nó (`decision_record.approval_step_id`).
8. **Khoá dấu vân tay input (A-097):** HMAC-SHA256 với khoá dẫn xuất bằng HKDF từ `BO19_SESSION_SECRET` (`info = "bo19/input-fingerprint/v1"`), `fingerprint_key_id = "session-hkdf-v1"`. Không thêm biến môi trường mới trên Render; đổi `BO19_SESSION_SECRET` làm dấu vân tay cũ không còn khớp — chỉ khiến `compute_targets` (B9b) coi biến là "đã đổi" và sinh lại: an toàn, chỉ tốn một lời gọi.
9. **Bản nháp và biến *điền sau duyệt* (A-098):** giá trị hiển thị là dấu giữ chỗ cố định `[sẽ được cấp khi phát hành]`; chúng **không** vào `approved_content_hash` và **không** qua kiểm "không placeholder" của `review_readiness_check` (INV-01: tập biến `SYSTEM` được phép khác giữa bản duyệt và bản phát hành). Định dạng `DATE` ở biến `DIRECT_SLOT`: `dd/mm/yyyy`. Kiểu slot `ENUM`, `LIST`, `BOOL`, `FILE` làm giá trị biến `DIRECT_SLOT` **chưa hỗ trợ** — `RENDER_INPUT_INVALID` — vì câu chữ theo loại hợp đồng là việc của đoạn điều kiện của template thật (M1.1; EC-WC-01, EC-WC-02), không phải của lát này.

## Consequences

**Tích cực**

- Thử lại job an toàn ở mọi điểm: không `document` thứ hai, không LLM lặp cho biến đã lưu, graph tiếp từ checkpoint.
- Thread, `document` và checkpoint khớp nhau từ bước đầu; `graph_thread` không bao giờ trỏ vào một `document` chưa có.
- Sprint 2 đổi lỗi → `halt_for_human` bằng cách thay một `raise` bằng một cạnh; mã không đổi tên.
- Điểm dừng resume kiểm được bằng tiến trình thật: thread chờ ở `await_content_review`, tiến trình bị giết, tiến trình mới resume đúng và không gọi LLM lại.

**Tiêu cực / phải chấp nhận**

- `document` tồn tại ở `DRAFT` trước khi node đầu chạy; nếu graph không bao giờ chạy tiếp (job `FAILED` vĩnh viễn) thì có `document` `DRAFT` mồ côi ở Sprint 1. Sprint 2 (`halt_for_human`, tiếp quản) là nơi xử lý — chấp nhận vì chưa có người dùng thật (roadmap).
- Một vòng sinh lại bị mất `scratch` tốn thêm một lời gọi LLM so với lý tưởng (mục 4).
- `uuid5` làm id đoán được từ `request_id` — id không phải bí mật; mọi truy cập đều qua kiểm quyền (mục Phân quyền của `05-api.md`).
- Khoá dấu vân tay phụ thuộc `BO19_SESSION_SECRET` (mục 8).

## Rejected alternatives

- **A — Tạo trong node với id ngẫu nhiên.** Thread id phải biết trước khi node đầu chạy, mà `graph_thread` cần `document` có dòng; muốn vậy lại phải có hàm tạo ngoài graph — tức B, chỉ khác là id không đoán được và thử lại không idempotent (hai lần chạy → hai `document`).
- **C — Thread theo `request`.** Vi phạm `ck_graph_thread_document_id` và mục `document_graph` (thread theo `document`); vòng `supersedes` về sau cần thread riêng cho `document` mới.
- **D — Job `SUCCEEDED` khi lỗi.** Mất tín hiệu vận hành (`job_failed` ở hàng đợi, chỉ số của `11-ops.md`); và ADR-004 cần job `FAILED` để người vận hành thấy.
- **Khoá dấu vân tay là biến môi trường riêng.** Đúng hướng lâu dài (xoay khoá độc lập), nhưng thêm một secret trên Render mà PO phải đặt trước khi lát này chạy; hoãn tới khi Phase 9 giao quản lý khoá (A-097) — mặc định HKDF không chặn việc gì và đổi được bằng một migration dữ liệu nhỏ (`fingerprint_key_id` đã có cột).
