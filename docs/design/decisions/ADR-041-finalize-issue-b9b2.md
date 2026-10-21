# ADR-041 — `finalize_issue` (B9b2): node sau `await_issue`, kiểm `approved_content_hash` trước khi cấp số, `VOIDED` do handler khi job bỏ cuộc, bản `FINAL` in họ tên và chức danh người đã ký

**Trạng thái:** Accepted · **Duyệt:** PO, 2026-10-20 (kế hoạch B9b — chia B9b1/B9b2, tám câu; `proposals/b9b-ke-hoach.md`) và 2026-10-21 (bắt đầu B9b2, docs-first) · **Ngày:** 2026-10-21 · **Quyết định tại:** BUILD MODE, B9b2, trước mã `finalize_issue` · **Liên quan:** ADR-040 (lát B9b1), ADR-011 (cấp số), ADR-010 (resume qua job), ADR-004 (job ít nhất một lần), ADR-038 (watermark), INV-01, AUD-01, A-098, A-100

---

## Context

B9b1 dừng ở `await_issue`. `document_issue` đã ghi lệnh phát hành (`decision_record` `ISSUE_ORDERED`, bước `ISSUE_ORDER` đã `DECIDED`) và enqueue job `finalize_issue` — job nằm `QUEUED` vì chưa có handler. B9b2 hoàn tất phát hành: số `TRIAL`, bản `FINAL`, `ISSUED`, `request → FULFILLED`. Thiết kế (mục 5.2 và 6.4 của `03-agents.md`) đã chốt *cái gì* (bốn bước), còn trống năm chỗ:

1. **`finalize_issue` là node của graph hay một job tự chạy?** Mục 6.4 vẽ nó là node sau `await_issue`; kế hoạch B9b gọi nó là "job riêng".
2. **Thứ tự kiểm `approved_content_hash`.** Mục 5.2 đặt kiểm hash *sau* khi đã cấp số và render, nên hash lệch tiêu một số rồi `VOIDED`. Hash chỉ phụ thuộc giá trị biến, không phụ thuộc số.
3. **Ai chuyển số sang `VOIDED` ở Sprint 1** khi chưa có `halt_for_human` (kế hoạch B9b, mục Không làm: "lỗi ở Sprint 1 làm job `FAILED`, số đã lấy thì `VOIDED`").
4. **Giá trị của ba biến `SYSTEM` điền-sau-duyệt** (`document_number`, `issued_date`, `signer_user_id`) ở bản `FINAL`; PO đã chốt in **họ tên + chức danh** người ký, không in mã.
5. **Chạy lại sau khi chết giữa chừng** ở từng điểm của chuỗi (số → render → kiểm → commit).

## Options

- **Chỗ chạy:** (A) node `finalize_issue` trong `document_graph`, `await_issue` đánh thức bằng `ISSUE_ORDERED`, job `finalize_issue` gọi `DocumentRunner.run_finalize_issue`; (B) job tự chạy các tool, không qua graph — loại: Sprint 2 cần `halt_for_human` với `at_node = finalize_issue` và lối ra `RETURN_TO_ISSUE_QUEUE` (mục Dừng có kiểm soát và tiếp quản của `08-hitl.md`), cả hai đều là cạnh của graph; làm (B) bây giờ là viết hai lần.
- **Thứ tự hash:** (A) kiểm hash **trước** `document_number_assign`, trên bảng giá trị sẽ được render; (B) giữ thứ tự mục 5.2 (sau render) — loại: hash lệch không có lối ra (A-077) nên mỗi lần lệch sinh một số `VOIDED` vô ích, và kiểm *trước* không mất gì vì hash là hàm thuần của giá trị (kiểm trên đúng bảng sẽ render thì không có khe hở giữa kiểm và render).
- **Ai `VOIDED`:** (A) handler của job `finalize_issue`, khi job sắp `FAILED` (lỗi vĩnh viễn, hoặc hết `max_attempts`); (B) node tự bắt mọi lỗi và `VOIDED` ngay lần đầu — loại: lỗi tạm (`soffice` quá giờ, storage chập chờn) sẽ đốt một số mỗi lần thử; (C) để số `ASSIGNED` treo — loại: thiết kế đòi `VOIDED` kèm lý do khi bỏ cuộc, và số treo che lệnh phát hành sau tiếp quản.
- **Tên in:** (A) `employee.full_name` + `employee.job_title` của người có `decision_record` `SIGNED` của `document`; (B) của `document.signer_employee_id` — cùng người theo B9b1 (chỉ người được giao ký được) nhưng (A) là *người đã ký*, không phải *người được giao*.

## Decision

1. **`finalize_issue` là node của `document_graph`**, sau `await_issue` và trước `END`. `await_issue` nay đọc id quyết định từ payload resume như ba điểm chờ kia; `ISSUE_ORDERED` đánh thức `await_issue` (`WAKES`). Job `finalize_issue` (`dedupe_key` = id lệnh phát hành, do `document_issue` enqueue ở B9b1) có handler riêng gọi `DocumentRunner.run_finalize_issue` = cùng đường `resume_document` nhưng chỉ nhận `ISSUE_ORDERED`; job `resume_document_graph` chỉ nhận ba loại cũ. Thread chưa tới `await_issue` thì `THREAD_NOT_WAITING`; đã qua thì no-op. Thread của B9b1 đang chờ ở `await_issue` resume được bằng mã mới (tên node là contract, ADR-040 mục 8).
2. **Thứ tự bên trong node** (sửa mục 5.2 của `03-agents.md`): (0) **`issue_prepare`** — đọc `document`, kiểm lệnh phát hành thuộc `document` và `document` ở `SIGNED` (không cần dấu) hay `SEALED`; dựng bảng giá trị bằng `build_values`; tính `approved_content_hash` từ các biến **không** điền-sau-duyệt bằng `domain.content_hash.approved_content_hash` (cùng hàm với thao tác duyệt) và so với `document.approved_content_hash` — lệch là `CONTENT_HASH_MISMATCH` (vĩnh viễn, **chưa tiêu số nào**); đã `ISSUED` đúng với lệnh này thì trả `already` và node kết thúc; (1) `document_number_assign` (B8a, idempotent theo `document_id`); (2) điền ba biến `SYSTEM` (mục 4) vào *chính bảng giá trị đã kiểm hash*, `docx_render` `FINAL` rồi `pdf_export`, hai object mang metadata `bo19-pin-reason = ISSUED` và `bo19-document-number` trong cùng lệnh `PUT` (`04-data.md` mục 5.1, 5.3); (3) `render_integrity_check` trên bản cuối; (4) `document_mark_issued` — **một giao dịch**: ghim bản cuối (`document_render_pin`, `ISSUED`, `decision_record_id` = lệnh phát hành), `document` `SIGNED`/`SEALED → ISSUED` với `issued_register_entry_id`, `final_render_id`, `issued_date` (`set_values`) và `issued_at` (mốc `now()` của kernel), `request APPROVED → FULFILLED` nếu mọi `document` của `request` đã tới trạng thái cuối của thân văn bản, `audit_event` với **người ra lệnh làm tác nhân** (mục 5.2 của `03-agents.md`) và payload mang thêm `executed_by = SYSTEM`.
3. **Bỏ cuộc ở Sprint 1 (chưa có `halt_for_human`).** Node chỉ ném `NodeError(mã)` như mọi node; `failure.classify` quyết vĩnh viễn hay tạm. **Handler `finalize_issue`** bắt `RenderFailed`; khi job sắp `FAILED` — `permanent`, hoặc `job.attempts >= job.max_attempts` (đúng điều kiện `final` của dispatcher) — và lỗi không phải `JOB_CANCELLED`, handler gọi `document_number_void_open(document_id, reason_code)` trước khi ném `JobFailure`: dòng sổ `ASSIGNED` của `document` (nếu có và `document` chưa `ISSUED`) chuyển `VOIDED` với `reason_code` = mã lỗi vĩnh viễn, hoặc `ISSUE_RETRIES_EXHAUSTED` khi hết lượt vì lỗi tạm. `document` đứng yên ở `SIGNED`/`SEALED`, thread ở `finalize_issue`, job `FAILED` có mã, `GET /issue-queue` hiện `job_failed` và `job_failed_code` (đã có từ B9b1). Không có đường phát hành lại ở Sprint 1 (mỗi `document` một lệnh); lối ra là `RETURN_TO_ISSUE_QUEUE` của Sprint 2, và lần phát hành sau nhận số **mới** (chỉ dòng `ASSIGNED` mới chặn). Worker chết đúng ở lượt cuối (lease hết hạn → `reclaim_expired` đặt `FAILED` mà handler không chạy) để lại số `ASSIGNED` chưa `VOIDED`: không sinh lỗ hổng — lần phát hành sau nhận lại chính số đó (idempotent theo `document_id`) — nên chấp nhận ở Sprint 1; Sprint 2 `halt_for_human` đóng khe này.
4. **Ba biến `SYSTEM` điền-sau-duyệt ở bản `FINAL`**, đổi theo *tên biến* (không theo thứ tự): `document_number` = `formatted_number` của dòng sổ; `issued_date` = ngày cấp số theo múi giờ tổ chức, `dd/mm/yyyy` (A-098); `signer_user_id` = `"<họ tên>, <chức danh>"` của người có `decision_record` `SIGNED` mới nhất của `document` (`employee.full_name`, `employee.job_title`; dữ liệu công vụ của người phát hành — mục AuthZ của `09-security.md`). Biến điền-sau-duyệt có tên khác, hoặc thiếu người ký → `RENDER_INPUT_INVALID` (vĩnh viễn). Dấu phân cách giữa họ tên và chức danh là mặc định làm việc (A-100) cho tới mẫu thật (M1.1); tên biến `signer_user_id` giữ nguyên để không đổi template/slot (nó in tên, không in mã — ghi ở `GLOSSARY.md`).
5. **Chạy lại sau khi chết (ADR-004).**

| Chết ở | Trạng thái còn lại | Lần chạy lại |
|---|---|---|
| Trước khi cấp số (kể cả `issue_prepare`) | Không có dòng sổ | Cấp số mới |
| Sau khi cấp số, trước/giữa render | Dòng sổ `ASSIGNED` | `document_number_assign` trả lại chính dòng đó; render trùng khoá nên `reused` |
| Sau render, trước/giữa kiểm toàn vẹn | Hai object và dòng `document_render` | Render `reused`; kiểm lại |
| Trong giao dịch cuối | Lăn hết | Như dòng trên |
| Sau giao dịch cuối, trước khi job `SUCCEEDED` | `document` `ISSUED` | `issue_prepare` thấy `ISSUED` với đúng lệnh này → node kết thúc không làm gì; `ISSUED` với lệnh khác → `STALE_STATUS` |

6. **Kernel.** `TableSpec` của `document` thêm `value_columns["ISSUED"]` = {`issued_register_entry_id`, `final_render_id`, `issued_date`} và `on_enter_now["ISSUED"]` = `issued_at`: `ck_document_issued_complete` đòi cả bốn cột có mặt trong cùng câu `UPDATE` đổi sang `ISSUED` (cùng lý do ADR-040 mục 1). `transition` vẫn là nơi duy nhất ghi `status`.
7. **Không migration.** Mọi bảng, cột, quyền `bo19_app` đã có ở `0001`–`0014` (kiểm trước khi viết mã: `document_register*`, `document_render_pin`, `document` các cột `issued_*`/`final_render_id`, `decision_record`, quyền `UPDATE`/`INSERT` của `bo19_app`). Dải `TRIAL` của sổ `WORK_CONFIRMATION` có sổ ở data migration `0002` nhưng **không có định dạng số** — định dạng giả vào `tools/seed-dev/` (chỉ local, PO 2026-10-20) và vào fixture test.
8. **Không đổi contract `openapi.yaml`.** `issue_in_progress`, `document_number`, `issued_date`, `final_render_id`, `job_failed`, `job_failed_code` đã có từ B9b1; tải bản `FINAL` đi qua `downloadRender` đã có.

## Consequences

**Tích cực**

- Hash lệch không tiêu số; mọi số `VOIDED` đều có nguyên nhân xảy ra *sau* khi số đã cần.
- `finalize_issue` là node thật: Sprint 2 thêm `halt_for_human` và `notify_issued` bằng hai cạnh, không viết lại.
- Chạy lại ở mọi điểm đều hội tụ về cùng một số, cùng một cặp object, cùng một `ISSUED`.

**Tiêu cực / phải chấp nhận**

- Một lệnh phát hành hỏng ở Sprint 1 không phát hành lại được cho tới Sprint 2 (một `document` một lệnh) — văn bản ở lại `SIGNED`/`SEALED` và hiện trong `GET /issue-queue` với `job_failed`.
- Object `FINAL` đã ghi cho một số về sau `VOIDED` mang metadata `ISSUED` của số đó; object mồ côi, không ghim. Đối soát sau khôi phục luôn so với `postgresql` (nguồn sự thật, `04-data.md` mục 5.1).
- Mặc định `"<họ tên>, <chức danh>"` và định dạng số giả không phải thể thức thật (`[CẦN XÁC MINH]`: Nghị định 30/2020/NĐ-CP và mẫu M1.1).

## Rejected alternatives

- **Job `finalize_issue` không qua graph** — viết hai lần khi Sprint 2 đưa nó vào `halt_for_human`.
- **Kiểm hash sau render** — tiêu số vì một điều đã biết trước khi cấp số.
- **`VOIDED` ở lần lỗi đầu tiên** — đốt một số mỗi lần `soffice` quá giờ.
- **In `signer_employee_id` hoặc mã nhân viên** — PO chốt in họ tên và chức danh (2026-10-20).
- **Tên của `document.signer_employee_id` thay vì người có quyết định `SIGNED`** — bằng nhau theo B9b1 nhưng "người đã ký" là sự kiện đã ghi, "người được giao" là kế hoạch; tên in lên văn bản lấy từ sự kiện.
