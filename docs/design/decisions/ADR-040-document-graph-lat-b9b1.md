# ADR-040 — `document_graph` lát B9b1: bốn thao tác cổng ghi cột đi kèm qua kernel, resume theo loại quyết định, người ký do `signing_route` giao, `approved_content_hash` có định nghĩa chuẩn tắc

**Trạng thái:** Accepted · **Duyệt:** PO, 2026-10-20 (kế hoạch B9b — chia B9b1/B9b2, tám câu; `proposals/b9b-ke-hoach.md`, mục Quyết định của PO) · **Ngày:** 2026-10-20 · **Quyết định tại:** BUILD MODE, B9b1, trước mã thao tác cổng · **Liên quan:** ADR-039 (lát B9a), ADR-010 (resume qua job), ADR-008 (state chỉ mang tham chiếu), ADR-027 (tự duyệt), ADR-004 (job ít nhất một lần), D-006, INV-01, AUD-01

---

## Context

B9a dừng ở `PENDING_APPROVAL`. B9b1 đi tiếp qua hai cổng HITL tới `SEALED` rồi chờ lệnh phát hành. Năm chỗ thiết kế còn trống hoặc đòi chọn:

1. **Cột đi kèm của cạnh trạng thái.** `ck_document_approved_complete` đòi `approved_content_hash`, `approved_decision_id`, `approved_render_id` có mặt **trong cùng câu `UPDATE`** đổi sang `APPROVED`; `ck_document_signer_assigned` đòi `signer_employee_id` ở `PENDING_SIGNATURE`. Kernel (`transition`) hiện chỉ ghi `status`, `row_version`, mốc thời gian — `B9a` ghi rõ "cạnh sau cổng 1 chưa mở rộng `TableSpec`". Và `approval_step` chưa có máy trạng thái, trong khi thao tác cổng phải đóng bước (`OPEN → DECIDED`) và CI cấm câu `UPDATE … status =` ngoài kernel.
2. **`approved_content_hash`** (INV-01) được mô tả bằng lời ("hash của phiên bản template, `operating_mode` đã ghim, giá trị mọi biến không mang cờ điền-sau-duyệt") nhưng chưa có dạng chuẩn tắc. `finalize_issue` (B9b2) phải tính lại **đúng** hàm này; hai bên lệch một byte là văn bản không phát hành được.
3. **Resume sau nhiều thao tác.** Một thread có bốn `interrupt` (`await_content_review`, `await_signature`, `await_seal`, `await_issue`). Job `resume_document_graph` chạy ít nhất một lần (ADR-004): job APPROVED chạy lại sau khi thread đã tới `await_signature` mà giao nhầm id quyết định `APPROVED` cho `await_signature` thì graph đi sai. B9a `resume_document` chỉ biết "đang chờ ⇒ resume".
4. **Ai ký.** `signing_route` "xác định người ký" nhưng thiết kế không nêu quy tắc chọn khi nhiều người mang `document.sign`; và `document_sign` chỉ ghi permission `document.sign`, không nói người ký có phải người được giao không — trong khi tên người ký in trên bản `FINAL` (PO, 2026-10-20).
5. **Không có `halt_for_human` ở Sprint 1.** `NO_ELIGIBLE_SIGNER` phải đi đâu, và cán bộ thấy nó ở đâu.

## Options

- **Cột đi kèm:** (A) kernel nhận `set_values` có danh sách cho phép theo trạng thái đích; (B) tool tự `UPDATE document SET approved_… ` rồi kernel đổi `status` — loại vì `ck_document_approved_complete` không thoả giữa hai câu; (C) nới `CHECK` bằng migration — loại, đổi bất biến của DB để tiện mã.
- **Hash:** (A) JSON chuẩn tắc có phiên bản, SHA-256; (B) HMAC có khoá (như dấu vân tay input, A-097) — loại: hash này phải tính lại được bởi mọi tiến trình mà không thêm secret, và không cần che giá trị (chúng nằm trong `request_slot` cùng DB).
- **Resume:** (A) lớp chạy graph đọc loại `decision_record` rồi so với node đang chờ; (B) graph tự đọc DB sau resume và bỏ qua nếu lệch — loại: node đã chạy lại `interrupt` rồi mới bỏ qua, đồng thời state đã bị ghi đè `last_signal`.
- **Người ký:** (A) `signing_route` giao cho **một** người, `document_sign` chỉ nhận chính người đó; (B) mọi người mang `document.sign` đều ký được — loại: tên in trên bản `FINAL` có thể khác người đã ký.
- **`NO_ELIGIBLE_SIGNER`:** (A) job `FAILED` vĩnh viễn, `document` ở `APPROVED`, hiện ở hàng đợi `status=APPROVED` cho người có `document.approve_content` (Sprint 1, tạm); (B) tự chọn người thụ hưởng làm người ký — loại: chính là đường tự duyệt mà Sprint 3 mới mở.

## Decision

1. **Kernel mở rộng hai chỗ.** (a) `transition(..., set_values={...})` — mỗi cột phải nằm trong `TableSpec.value_columns[trạng thái đích]`, đúng một câu `UPDATE`, đúng một nơi sinh ra: `APPROVED` ← `approved_content_hash`, `approved_decision_id`, `approved_render_id`; `PENDING_SIGNATURE` ← `signer_employee_id`. Trạng thái đích có cột bắt buộc mà thiếu thì `ExtraColumnNotAllowed`/`SET_VALUES_REQUIRED`. (b) `approval_step` có máy trạng thái: `OPEN → DECIDED`, `OPEN → CANCELLED`; `closed_at` đặt khi vào trạng thái cuối; không có `status_changed_at`.
2. **Thao tác cổng theo khuôn `request_submit`**, một hàm một giao dịch: permission → khoá `document` (`FOR UPDATE`) rồi `request` (cùng thứ tự với `document_submit_for_review`) → `decision_record` trùng khoá (lặp lại hợp lệ hoặc `DecisionIdConflict`) → trạng thái và `row_version` (`StateConflict`) → D-006 → nghiệp vụ → ghi `decision_record`, đóng `approval_step`, đổi trạng thái, `audit_event`, enqueue. `decision_record.id` là `Idempotency-Key`.
3. **D-006 ở Sprint 1.** Người thao tác là người thụ hưởng thì bị chặn; `E(P, d)` tính đúng như mục Tách biệt trách nhiệm của `08-hitl.md`. Đường thoát (`self_approval_reason`, bước `self_approved`) là Sprint 3 (kế hoạch B9b): bị chặn là **luôn `SELF_APPROVAL_BLOCKED`** — kể cả khi `E` rỗng và có lý do. Trường `self_approval_reason` của body vẫn nhận (contract) và bị bỏ qua khi không bị chặn.
4. **`approved_content_hash = SHA-256(JSON chuẩn tắc)`** với JSON `{"v":1,"template_version_id":"<uuid>","operating_mode":"<mã>","values":{"<tên biến>":"<giá trị>",…}}`, khoá sắp tăng dần, UTF-8, không khoảng trắng thừa, `ensure_ascii = false`. `values` = mọi biến của phiên bản template **không** mang cờ điền-sau-duyệt, giá trị đúng như bảng giá trị của `docx_render`. Hàm thuần `domain.content_hash.approved_content_hash`; `finalize_issue` (B9b2) gọi lại **đúng hàm này**. Đổi dạng chuẩn tắc là đổi `v`.
5. **Resume theo loại quyết định.** Payload job `resume_document_graph` = `{document_id, decision_record_id}`, `dedupe_key` = id quyết định. `DocumentRunner.resume_document` đọc `decision_record.kind` rồi: `APPROVED` ↔ chờ ở `await_content_review`, `SIGNED` ↔ `await_signature`, `SEALED` ↔ `await_seal`. Thread chờ đúng node → resume; thread đã qua node đó (chờ ở node sau hay đã `END`) → no-op (job chạy lại); thread chưa tới node đó → `NodeError(THREAD_NOT_WAITING)`. Thread **không chờ mà còn node kế** (lần chạy trước chết giữa chừng sau khi `interrupt` đã trả) → tiếp bằng `invoke(None)` từ checkpoint.
6. **Người ký.** `signing_route` chọn người nhỏ nhất theo `employee.employee_code` trong `E(document.sign, d)` (đang hoạt động, mang `document.sign`, không phải người thụ hưởng) — quy tắc làm việc của Sprint 1 (A-099), thay khi có định tuyến nhiều cấp. Ghi `document.signer_employee_id`, mở bước `SIGNATURE` giao cho người đó. **`document_sign` chỉ nhận chính người được giao** (khác người: `PermissionDenied`, `details` = `assignee`). Quy ước `read_assigned`: người được giao bước `SIGNATURE` xem được đúng văn bản đó (mục AuthZ của `09-security.md`).
7. **`NO_ELIGIBLE_SIGNER` ở Sprint 1** = job `resume_document_graph` `FAILED` vĩnh viễn, `document` ở `APPROVED`, `job_failed = true`. Hàng đợi `GET /review-queue?status=APPROVED` (thêm cho Sprint 1, người có `document.approve_content`) hiện nó. Thay bằng `halt_for_human` + `GET /takeover-queue` ở Sprint 2; khi đó `status=APPROVED` bỏ.
8. **Graph B9b1** dừng ở `await_issue` (`interrupt`): `await_signature`, `await_seal`, `await_issue` là ba điểm chờ mới; `finalize_issue` và `END` là B9b2. Tên node `interrupt` là contract (mục Schema state đổi giữa chừng) nên `await_issue` có mặt từ B9b1 để B9b2 không đổi hình dạng graph của thread đang chờ.

## Consequences

**Tích cực**

- Mỗi cạnh của máy trạng thái vẫn chỉ do một hàm sinh ra; cột đi kèm không ghi ngoài kernel; CI quét văn bản vẫn có nghĩa.
- Job resume chạy lại, chạy muộn, hay chạy hai lần đều không đưa nhầm quyết định cho node khác.
- `finalize_issue` không có chỗ nào để tính hash khác thao tác duyệt.

**Tiêu cực / phải chấp nhận**

- `APPROVED` trong hàng đợi duyệt là một giá trị `status` ngoài thiết kế gốc (3 giá trị); bỏ ở Sprint 2.
- Chỉ một người ký mỗi văn bản: người được giao vắng thì không ai khác ký được cho tới khi có uỷ quyền `[Should]` hoặc tiếp quản (Sprint 2–3). Chấp nhận — thà dừng còn hơn tên in trên văn bản sai.
- Chọn người ký theo mã nhân viên là tuỳ ý (không công bằng, không theo tải); chỉ phù hợp khi mỗi tổ chức có vài người mang `document.sign`.
- `SELF_APPROVAL_BLOCKED` luôn chặn cho tới Sprint 3: người thụ hưởng là người duy nhất mang một permission thì kẹt, đúng như kế hoạch (cấp permission tạm, A-078).

## Rejected alternatives

- **Nới `CHECK` bằng migration** để `UPDATE` hai bước — đổi bất biến DB chỉ vì mã khó viết; cũng cần migration tương thích ngược.
- **HMAC có khoá cho `approved_content_hash`** — thêm secret mà mọi nơi tính hash đều cần, không thêm bảo mật nào (INV-01 chống sửa nội dung sau duyệt, không chống đọc).
- **Resume chỉ dựa vào payload** — payload chỉ mang id (ADR-008); kiểm kind phải đọc DB, nên lớp chạy graph làm, không phải node.
- **Mọi người mang `document.sign` đều ký được** — tên người ký in trên bản `FINAL` (PO, 2026-10-20) phải là người đã ký.
- **Tự đặt người thụ hưởng làm người ký khi không còn ai** — là đường tự duyệt (D-006), mở ở Sprint 3 với `self_approval_reason`.
