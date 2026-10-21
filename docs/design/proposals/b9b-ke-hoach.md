# Kế hoạch B9b — bốn thao tác cổng, hàng đợi duyệt và phát hành, `finalize_issue`

**Trạng thái:** PO duyệt 2026-10-20 — chia B9b1/B9b2, tám câu (mục Quyết định của PO) · **Ngày:** 2026-10-20 · **Căn cứ:** `12-roadmap.md` (Sprint 1, lát B9b; AC-1.2; O1-15), mục Thao tác cổng và `document_graph` của `03-agents.md`, mục Thao tác cổng trên văn bản của `05-api.md`, mục Hàng đợi và Thao tác của người duyệt của `08-hitl.md`, ADR-039 · **Migration:** dự kiến **không** (bảng `decision_record`, `approval_step`, `seal_action`, `document_register*`, `document_render_pin` đã có ở `schema.sql`; sẽ kiểm lại trước khi viết mã, có thì báo theo quy trình mục Migration của `11-ops.md`) · **Biến môi trường mới:** không · **Chặn bởi:** không (cổng 2.5 chỉ chặn việc chuyển Render, không chặn B9b — B9b chạy local)

## Mục tiêu

Sau B9a, `document` dừng ở `PENDING_APPROVAL`. B9b đi nốt: cán bộ duyệt nội dung → ký → đóng dấu → phát hành → số `TRIAL` → bản `FINAL` → `ISSUED`, `request → FULFILLED`; mọi bước đi qua `api` với người thật và để lại bằng chứng của AC-1.2 (hai `decision_record` riêng `APPROVED` và `SEALED`, mỗi cái một `audit_event`; số từ `document_register` dải `TRIAL`). Chưa có client (B10): kiểm bằng test tiến trình thật và HTTP.

## Đề xuất chia hai lát (hỏi PO — mặc định: chia)

| Lát | Nội dung |
|---|---|
| **B9b1 — cổng** | Bốn thao tác cổng `document_approve_content`, `document_sign`, `document_apply_seal`, `document_issue` (tool trong `tool_layer.gate_ops`, mỗi thao tác **một giao dịch**: kiểm permission → kiểm D-006 → chuyển trạng thái → `decision_record` + `approval_step` → `audit_event` → enqueue job). Bốn endpoint `POST /documents/{id}/actions/{approve-content,sign,apply-seal,issue}`, `GET /documents/{id}` (`DocumentReviewView`), `GET /review-queue?status=`, `GET /issue-queue` (keyset theo `status_changed_at`, `id`). Graph: `route_review` (nhánh duyệt), `route_signing` (`render_integrity_check` rồi `signing_route`, một cấp), `await_signature`, `route_after_signature`, `await_seal`; handler job `resume_document_graph`. |
| **B9b2 — phát hành** | `finalize_issue` (job riêng, `queue_worker`): `document_number_assign` → `docx_render` + `pdf_export` bản `FINAL` → kiểm `approved_content_hash` (INV-01) → `render_integrity_check` → `ISSUED` + `request → FULFILLED`; đường lỗi `VOIDED` (số đã lấy mà bỏ cuộc). `GET /issue-queue` hiện cờ `issue_in_progress`. Test đầu-cuối AC-1.2 qua HTTP; test giết tiến trình giữa các cổng và giữa `finalize_issue`. |

Lý do chia: B9b1 kiểm được độc lập tới `SEALED` (đủ cho "hai `decision_record`" của AC-1.2 trừ phần số); `finalize_issue` có phần rủi ro riêng (số, `soffice`, `VOIDED`) nên dễ báo cáo và đột biến riêng.

## Kỹ thuật — những chỗ cần nói trước

1. **Resume dùng quyết định trong DB, không dùng payload** (đã chốt ở B9a): thao tác cổng enqueue `resume_document_graph` mang `document_id`, `decision_record_id`; `route_review` đọc `decision_record` từ DB. `interrupt` đã kiểm bằng tiến trình thật ở B9a — B9b thêm ba điểm chờ (`await_signature`, `await_seal`, và ngoài graph là `finalize_issue`).
2. **`approved_content_hash`** (INV-01) tính ở `document_approve_content` từ phiên bản template, `operating_mode` đã ghim và giá trị mọi biến **không** mang cờ điền-sau-duyệt; `finalize_issue` tính lại từ đúng các giá trị dùng cho bản `FINAL` và **không phát hành** nếu lệch (A-098: dấu giữ chỗ không vào hash; bản `FINAL` còn dấu thì `PLACEHOLDER_REMAINS` — đã có).
3. **Số văn bản chỉ cấp trong `finalize_issue`** (`document_number_assign` đã có từ B8a, idempotent theo `document`); `document_issue` chỉ ghi lệnh (`ISSUE_ORDER` đã `DECIDED`, `decision_record` `ISSUE_ORDERED`).
4. **Giá trị biến `SYSTEM` của bản `FINAL`:** `document_number`, `issued_date` (múi giờ tổ chức, `dd/mm/yyyy` — A-098 mặc định), `signer_user_id` — in tên người ký hay mã? Xem câu 5.
5. **Idempotency:** khoá = id của `decision_record` (05-api); gọi lại cùng khoá trả cùng kết quả; hai cán bộ cùng bấm duyệt: một thắng, một `STATE_CONFLICT`.

## Rà `request.read_assigned` (PO yêu cầu)

- **Thiết kế:** `GET /documents/{id}` cho `request.read_all` **hoặc** `request.read_assigned` "với bước duyệt giao cho mình" (mục Thao tác cổng trên văn bản và mục Tải file của `05-api.md`). B8b hiện thực: có `approval_step` giao cho chính mình, trạng thái `OPEN` hoặc `DECIDED` (diễn giải của người triển khai, đã ghi ở `05-api.md`).
- **Điều rà thấy:** (a) B9a mở bước `CONTENT_REVIEW` với `assignee_employee_id = NULL` — đúng thiết kế của hàng đợi (ai có `document.approve_content` cũng xem được hàng đợi), nhưng với định nghĩa trên thì **không ai** "được giao" bước này; (b) trong Sprint đầu mọi người thao tác là `ADMIN_OFFICER`, mang `request.read_all` (A-061) nên `read_assigned` chưa quyết định gì; (c) `read_assigned` chỉ thật sự cần khi có vai trò `SIGNER` (không ở Sprint đầu) — người đó chỉ nên thấy văn bản của bước **chữ ký giao cho mình**.
- **Đề xuất mặc định:** giữ định nghĩa B8b; bước `SIGNATURE` do `signing_route` giao cho `signer_user_id` (đây là bước duy nhất có người được giao); `CONTENT_REVIEW`, `SEAL`, `ISSUE_ORDER` giữ `NULL` và đi theo hàng đợi + permission cổng. Thêm test: người ký (không có `read_all`) xem được đúng văn bản của bước giao cho mình và không xem được văn bản khác; ghi quy ước vào `09-security.md` (mục AuthZ) thay vì để ở `05-api.md`. Không đổi quyền của ai.

## O1-15 — `CHANGES_REQUESTED` ca `SLOT_DATA` còn `NOT_EDITABLE`

Nay có `document`, ca xác định được: `request.status = CHANGES_REQUESTED` **và** `decision_record` mới nhất của `document` mang `change_scope = SLOT_DATA`. Nhưng thao tác làm `request` sang `CHANGES_REQUESTED` (`document_request_changes`) là **Sprint 2** theo roadmap, nên không có đường tự nhiên để vào trạng thái này trong B9b. **Mặc định:** hiện thực vị từ "còn sửa được" (`request_slots_write`/`request_slot_confirm`/`request_submit` ở ca `SLOT_DATA`) và test bằng dữ liệu dựng trực tiếp ở fixture; **đóng O1-15 ở mức mã** và để phần tích hợp với `document_request_changes` cho Sprint 2. Hỏi PO nếu muốn kéo `document_request_changes`/`document_reject` vào B9b (mỗi cái nhỏ: một thao tác + một endpoint, nhưng cần nhánh `reopen_draft`/`revise_free_content` của graph — không nhỏ).

## Không làm

`document_request_changes`, `document_reject`, `document_takeover_resolve`, thu hồi (Sprint 2–3); `halt_for_human` và bảng `document_halt` (Sprint 2 — lỗi ở Sprint 1 làm job `FAILED`, số đã lấy thì `VOIDED`); đường thoát tự duyệt (`self_approval_reason`, Sprint 3 — người thụ hưởng làm thao tác bị chặn thì trả `SELF_APPROVAL_BLOCKED`); `notification_send`/`notify_issued` (Sprint 2); client (B10); chuyển Render sang `combined_main` (chờ cổng 2.5).

## Câu cần PO quyết (mặc định in đậm)

1. **Chia B9b1 / B9b2:** **chia** — hay một lát?
2. **Người ký (`signing_route`) khi người đủ quyền duy nhất là người thụ hưởng:** Sprint 1 chưa có `halt_for_human`. Mặc định: **job `FAILED` với `NO_ELIGIBLE_SIGNER`/`SELF_APPROVAL_BLOCKED`, `document` ở `APPROVED`** (đường thoát là Sprint 2–3).
3. **Số `TRIAL` ở lần chạy đầu-cuối cần `document_register` và định dạng số.** B8a chốt định dạng giả "chỉ ở fixture test" nên không vào data migration (nó lên Render). Mặc định: **`tools/seed-dev/` thêm một `document_register` dải `TRIAL` và một định dạng giả có nhãn** (chỉ local, cùng luật mật khẩu giả); test dùng fixture như B8a.
4. **Thể thức và định dạng thật của số văn bản** vẫn là mẫu thật M1.1 + Nghị định 30/2020 `[CẦN XÁC MINH]` — B9b dùng định dạng giả; chấp nhận?
5. **Biến `SYSTEM` `signer_user_id` trong bản `FINAL`:** in **họ tên** người ký (`employee.full_name`, dữ liệu `PER`) hay mã? Mặc định: **họ tên** (một văn bản phát hành cần tên người ký; đây là dữ liệu `PER` nằm trong bản render, nên cần PO xác nhận) — xác nhận. Ngày `issued_date`: `dd/mm/yyyy` theo múi giờ tổ chức (A-098).
6. **`read_assigned`:** theo mục rà ở trên — mặc định **giữ định nghĩa B8b, chỉ bước `SIGNATURE` có người được giao**.
7. **O1-15:** mặc định **đóng ở mức mã + fixture**, tích hợp ở Sprint 2.
8. **Test đầu-cuối có gọi Groq thật không?** Mặc định: **không** — provider giả, như B9a2; AC-1.1 (Groq thật, hành trình trọn vẹn) chạy sau B10 (client). Hạn mức Groq còn 3/10 lời gọi PO cho phép.

## Điều kiện xong (mỗi lát)

Test mới đạt trên PostgreSQL, SeaweedFS và `soffice` thật; test tiến trình thật cho resume giữa các cổng; đột biến ≥ một mẫu cho mỗi quy tắc (permission, D-006, trạng thái chuyển, hash, idempotency, `VOIDED`, một-giao-dịch); `lint-imports`, `check_grants`; CI xanh; tài liệu sửa trước (kể cả mục Triển khai ở B9b của `06-structure.md`); báo cáo kèm bằng chứng AC-1.2 (B9b2), rồi xin merge.

## Quyết định của PO (2026-10-20)

Chia **B9b1 / B9b2**. Tám câu:

1. **Chia hai lát:** chia. B9b1 bắt đầu ngay; kiểm "không migration" trước khi viết mã — có migration thì báo kèm lệnh áp và lý do tương thích ngược.
2. **Người ký chỉ còn người thụ hưởng:** job `FAILED` với mã riêng `NO_ELIGIBLE_SIGNER`, **hiện được trong hàng đợi cho cán bộ**; ghi "thay bằng `halt_for_human` khi có". Seed giả luôn có ≥ 2 người đủ quyền ký. *(Cách hiện — `GET /review-queue?status=APPROVED` — ở ADR-040 mục 7.)*
3. **`document_register` và định dạng số giả:** vào `tools/seed-dev/`, chỉ local (B9b2).
4. **Định dạng số thật:** vẫn `[CẦN XÁC MINH]` (M1.1 + Nghị định 30/2020); B9b dùng định dạng giả.
5. **Bản `FINAL` in HỌ TÊN + CHỨC DANH người ký** (như văn bản hành chính thật), **không in mã**. Ghi ở mục AuthZ của `09-security.md`: dữ liệu công vụ của người phát hành, đúng mục đích. Ngày `issued_date`: `dd/mm/yyyy` theo múi giờ tổ chức (A-098).
6. **`read_assigned`:** giữ định nghĩa B8b; chỉ bước `SIGNATURE` có người được giao; quy ước ghi ở `09-security.md`; test người ký.
7. **O1-15:** mã + fixture ở B9b, tích hợp ở Sprint 2.
8. **Test đầu-cuối dùng provider giả**, không gọi Groq.

Quyết định kỹ thuật phát sinh khi viết B9b1 (cột đi kèm của cạnh trạng thái, dạng chuẩn tắc của `approved_content_hash`, resume theo loại quyết định, người ký chỉ ký được khi được giao): **ADR-040**.
