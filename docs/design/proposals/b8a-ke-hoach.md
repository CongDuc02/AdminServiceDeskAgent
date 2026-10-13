# Kế hoạch B8a — hạ tầng dữ liệu của tài liệu: `jobs`, `queue_worker`, `numbering`, `object_storage`, `storage`

**Trạng thái:** ✅ **PO duyệt 2026-10-13** — Q1 đồng ý **kèm điều kiện: CI phải chứng minh SeaweedFS 4.47 trả `412` thật; bỏ qua header thì dừng và báo** (ADR-037); Q2, Q3, Q4, Q8 theo mặc định; Q5 đồng ý, ghi rủi ro ở R2-5 cạnh A-056; **Q6 đổi: chỉ fixture test, không đưa định dạng số giả vào data migration**; Q7 hoãn nhưng script contract phải có phép thử 412 · **Ngày:** 2026-10-13 · **Người đề xuất:** người triển khai · **Nhánh dự kiến:** `build/b8a-hang-doi-so-luu-tru` (tách từ `main` sau khi merge B7b) · **Thứ tự:** mục 4.7 của `12-roadmap.md` (risk-first) · **Đã đọc:** ADR-003, 004, 010, 011, 015, 031, 033; `04-data.md` mục Vận hành, Sổ số văn bản, Lưu trữ file; `06-structure.md` cây backend và bước kiểm khởi động; `11-ops.md` mục Background worker; `03-agents.md` mục 5.2, 5.3, 5.6

## 1. Mục tiêu và vì sao đứng ở đây

Dựng phần nền mà `document_graph` (B9) và `rendering` (B8b) sẽ dựa vào, và kiểm nó bằng PostgreSQL và SeaweedFS thật — chưa cần `soffice`, font hay LLM. Rủi ro cần lộ sớm: **số văn bản chạy đồng thời**, **giành job và lease khi worker chết**, **giao thức ghi một lần với 412**. Khi xong, job `render_document` mà B7 đưa vào hàng đợi **vẫn đứng `QUEUED`**: worker chỉ giành loại job đã có handler, và handler của `render_document` thuộc B9a.

## 2. Docs trước (bước 0)

| File | Việc |
|---|---|
| `04-data.md`, `11-ops.md` | Nghĩa của `release` và `reclaim` với `attempts`; giá trị lease/poll mới (Q3, Q4); hợp đồng payload `notification_send` **không** làm ở đây |
| `decisions/ADR-037-*` | Client S3 là `boto3` (Q1); luật import: `boto3`/`botocore` chỉ ở `bo19.object_storage` |
| `06-structure.md` | Mục Triển khai ở B8a; bước kiểm khởi động #14 (`object_storage` với tới được) có code |
| `ASSUMPTIONS.md` | WV mới mang nhãn "chưa hiệu chỉnh"; A-059 (thời lượng upload) ghi lại là chưa đo — đo ở B8b với bản render thật |
| `12-roadmap.md`, `CHANGELOG.md` | AC-1.2 phần "số lấy từ `document_register` dải `TRIAL`" có đường chạy; O1-5 |

Chỗ thiết kế đọc ra thiếu hoặc mơ hồ sẽ báo diff **trước** khi sửa — như ở B7.

## 3. Phạm vi mã

**3.1 `tool_layer.jobs`** (không `audit_event` — danh sách miễn, A-055; test quét văn bản giữ điều đó)

| Hàm | Làm gì |
|---|---|
| `claim(types, worker_id)` | `SELECT … FOR UPDATE SKIP LOCKED` job `QUEUED`, `run_after ≤ now()`, `job_type ∈ types`; đặt `RUNNING`, `attempts + 1`, `locked_by`, `locked_at`, `lease_expires_at`, `started_at`. Một câu, một giao dịch |
| `heartbeat(job, worker_id)` | Gia hạn lease; chỉ chủ lease hiện hành gia hạn được |
| `succeed(job, worker_id)` | `SUCCEEDED`, `finished_at` |
| `fail(job, worker_id, code, retry_after_s=None)` | Còn lượt thì về `QUEUED` với `run_after = now + max(base × 2^attempts, retry_after)`; hết lượt thì `FAILED`, `last_error_code`. `retry_after` vượt WV-19 (120 s) thì `FAILED` ngay với `PROVIDER_RATE_LIMITED` (mục Retry của `11-ops.md`) |
| `release(job, worker_id)` | Drain khi `SIGTERM`: về `QUEUED`, thả lease, **không tính một lượt thử** (Q4) |
| `reclaim_expired()` | Job `RUNNING` hết lease coi như thất bại một lượt — hết lượt thì `FAILED` (Q5) |

Chủ lease được so ở mọi hàm ghi: worker đã mất lease (bị `reclaim`) không `succeed` hay `fail` đè được. `base` theo `job_type` (10 s, riêng `procedure_ingest` 30 s) vào `working_values`.

**3.2 `queue_worker`:** `dispatcher.py` (vòng poll, một job một lúc, `heartbeat` bằng thread nền, drain `SIGTERM`), `handlers/` (đăng ký `job_type → hàm`; **production không đăng ký handler nào** — chỉ test dùng handler giả), `entrypoints/worker_main.py` (bước kiểm khởi động của cột `worker`, pool `bo19_app`, tắt êm). Gộp **O1-5**: log `SIGTERM_RECEIVED`, `PROCESS_EXIT` kèm giờ UTC cho `worker_main` **và** `api_main` (Q8). `combined_main` và Dockerfile: **không** ở B8a.

**3.3 `tool_layer.numbering`:** `document_number_assign` theo mục 4.2 của `04-data.md`, một giao dịch ngắn, chỉ tác nhân hệ thống, kiểm `issue_decision_id` là một `decision_record` `ISSUE_ORDERED` của đúng `document` đó; idempotent theo `document_id`; kỳ tính theo `Asia/Ho_Chi_Minh` (A-041) với đồng hồ truyền vào được để test sang năm. `document_number_void` (`VOIDED` kèm lý do không rỗng — chỗ gọi là `finalize_issue`, B9b). **Định dạng số `TRIAL` giả chỉ ở fixture test** (Q6, PO 2026-10-13): data migration chạy cả trên production nên **không** có dòng `document_register_format` giả; định dạng thật vào data migration khi có M1.2. `document` chưa có máy trạng thái (B9): test dựng hàng `document` bằng chủ bảng.

**3.4 `object_storage` + `tool_layer.storage`:** adapter `boto3`, path-style, mọi `PUT` mang `If-None-Match: *` (ADR-031), timeout WV-08 (30 s), thông tin kết nối từ biến môi trường (tên biến chốt ở bước 0, secret theo mục Secret management của `09-security.md`). `storage` cài giao thức ghi một lần mục 5.3–5.4 của `04-data.md`: giành claim → kiểm lease còn hạn lúc bắt đầu ghi → `PUT` → (412 thì đọc lại, so checksum: khớp là thành công, lệch là `STORAGE_WRITE_CONFLICT`) → commit checksum. Cộng `object_claim_reconcile` (nhặt claim hết lease, xoá object, xoá dòng). **Không** có `stored_file_fetch`, `docx_render`, `pdf_export` — B8b.

**3.5 Hạ tầng test:** SeaweedFS 4.47 (`linux_amd64.tar.gz`, sha256 ghim và ghi vào `docs/reference/`), chạy `weed server` đúng cờ của ADR-031 trong CI (một bước tải và kiểm sha256, chạy cạnh container PostgreSQL) và local (một container trên network `ci`, script trong `tools/`). Test cần S3 tự bỏ qua khi thiếu `BO19_TEST_S3_ENDPOINT`; CI luôn đặt nó và **đòi** các test S3 chạy (không được bỏ qua trong CI). **Test điều kiện duyệt Q1:** `PutObject` kèm `If-None-Match: *` lên khoá đã có phải trả `412 PreconditionFailed` thật và byte cũ còn nguyên — chạy ở mỗi lần CI trên đúng adapter; trả 200 hay đè thì **dừng, báo PO** (giao thức ghi một lần phải thiết kế lại). `tests/_guard.py` được phép nối host đó — như host PostgreSQL. `lint-imports`: thêm `boto3`, `botocore` vào `forbidden_modules` của contract `object-storage`.

## 4. Kiểm và đột biến

| Nhóm | Điều được chứng minh |
|---|---|
| Giành job | N worker giành đồng thời M job: mỗi job đúng một người; job `run_after` tương lai không bị giành; chỉ loại có handler |
| Lease | Heartbeat gia hạn; worker mất lease không `succeed`/`fail` được; `reclaim` đúng; hết lượt thì `FAILED`; không job nào `RUNNING` mà thiếu lease (ràng buộc DB) |
| Retry | Backoff `base × 2^attempts`; `retry_after` lấy max; vượt WV-19 thì `FAILED`; `release` không tiêu lượt |
| Đồng thời `render_document` | Hai `request_submit` (B7) rồi N worker: đúng một job được chạy một lần |
| Số văn bản | N luồng, N `document` cùng sổ: `seq` đúng 1…N, **không lỗ, không trùng**; cùng `document` gọi lại cùng dòng; giao dịch lăn thì không tiêu số; sang năm reset (YEARLY); `TRIAL` không chạm bộ đếm `OFFICIAL`; mẫu thiếu `{year}` ở sổ YEARLY hỏng chứ không phát số trùng; `VOIDED` không tái sử dụng |
| Ghi một lần | Cùng khoá hai lần: lần hai dùng object đã commit; claim hết lease; khoá chính cho đúng một người thắng; 8 luồng cùng khoá: một thắng; 412 khớp/lệch; commit muộn của claim cũ bị khoá ngoại từ chối; `object_claim_reconcile` |
| Rò dữ liệu | Payload job, `audit_event` và log không chứa nội dung file hay giá trị slot |
| Đột biến | Dự kiến 30–40 mẫu: bỏ `SKIP LOCKED`, bỏ so chủ lease, `release` tiêu lượt, bỏ `max(retry_after)`, bỏ khoá dòng bộ đếm, tăng bộ đếm ngoài giao dịch của dòng sổ, bỏ kiểm khớp series, bỏ `If-None-Match`, bỏ kiểm lease lúc ghi, bỏ so checksum ở 412, commit không khoá ngoại… — tất cả phải đỏ; mẫu sống thì thêm test |

## 5. Không làm ở B8a

`rendering` (điền `.docx`, `soffice`, font, watermark), `stored_file_fetch` và endpoint tải file, handler `render_document` và `document_graph` (B9a), cấp số **thật** (chờ M1.2), `combined_main`, Dockerfile và Render, cron `object_claim_reconcile` như lịch chạy (chỉ có thao tác), `notification_send`, `checkpoint_purge`.

## 6. Rủi ro

- **SeaweedFS ≠ nhà cung cấp thật** (A-072 hệ quả 2): bất biến ở tầng lưu trữ chỉ được chứng minh trên SeaweedFS 4.47; nhà cung cấp thật ở cổng 2.5.
- **Thời lượng upload chưa đo** (A-059) — lease 120 s (WV-10) vẫn là số đoán; B8a không đo vì chưa có bản render thật.
- **`document` chưa có máy trạng thái** nên `numbering` kiểm điều kiện bằng `decision_record` và hàng `document`, chưa bằng trạng thái; B9b siết thêm.
- **CI thêm một bước tải binary** (≈ 46 MB) — thêm thời gian chạy; kiểm sha256 để không tin mạng.

## 7. Câu hỏi cho PO — kèm mặc định

| # | Câu hỏi | Mặc định |
|---|---|---|
| Q1 | Client S3 | **`boto3` 1.37.3** — đã ghim trong lock, đã dùng ở bộ phép thử của ADR-031; ADR-037 ghi phương án loại (`httpx` + tự ký SigV4) |
| Q2 | Hạ tầng test S3 | SeaweedFS 4.47 như mục 3.5; test bỏ qua khi thiếu endpoint, CI luôn có |
| Q3 | Giá trị mới, "chưa hiệu chỉnh" | **WV-20** lease job 120 s, heartbeat mỗi 40 s · **WV-21** chu kỳ poll 2 s · **WV-22** một job một lúc |
| Q4 | `release` khi drain | **Không tiêu lượt thử** (job không lỗi — chỉ bị ngắt) |
| Q5 | Lease job hết hạn | **Tính một lượt thử**, để worker chết lặp lại không tạo vòng vô hạn. **Rủi ro ghi ở R2-5 của `12-roadmap.md` cạnh A-056:** drain ≈ 5 s trên gói free không kịp `release`; deploy nhiều lần có thể đốt hết lượt thử |
| Q6 | `document_register_format` `TRIAL` giả | ~~Data migration `0003`~~ **PO: chỉ fixture test.** Định dạng thật vào data migration khi có M1.2 |
| Q7 | Script kiểm contract S3 dùng chung cho nhà cung cấp thật (T2, T6, T8, T10) | **Hoãn tới trước cổng 2.5**; B8a có test cùng khẳng định ở mức adapter. **PO: script phải có phép thử `412` của điều kiện Q1** |
| Q8 | O1-5 (log `SIGTERM_RECEIVED`/`PROCESS_EXIT`) | **Làm ở B8a** cho `worker_main` và `api_main` |

Ước lượng: một lát lớn nhất của track build tới nay (ba mảng độc lập). Nếu PO muốn nhỏ hơn, cắt được theo thứ tự: (1) `object_claim_reconcile`, (2) O1-5, (3) tách `numbering` thành B8a-2 — hai mảng còn lại không phụ thuộc nhau.
