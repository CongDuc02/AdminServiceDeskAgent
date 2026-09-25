# Đề xuất diff — `05-api.md` + `contracts/openapi.yaml`

**Trạng thái:** ✅ Đã áp — 2026-09-25, PO duyệt · **Nguồn:** mục Background worker & Cron (`job_failed`) và ADR-023 (mã lỗi Lớp 3) của `11-ops.md` · Xem `05-api.md` mục Mã lỗi + mục 1.10, `contracts/openapi.yaml` (`DocumentSummary.job_failed`, `ErrorCode.ENVIRONMENT_NOT_ALLOWED`), `04-data.md` mục 3.8 (v0.9), `backend/migrations/schema/0003_job_failed_index.sql`, và mục ngày 2026-09-25 của `CHANGELOG.md`

---

## 1. Trường `job_failed` trên hàng đợi duyệt

**Vì sao:** mục 3.2 của `11-ops.md` thiết kế cờ dẫn xuất `job_failed` cho document có job `resume_document_graph`/`finalize_issue` mới nhất ở trạng thái `FAILED` vĩnh viễn, nhưng chưa endpoint nào trả nó.

**Sửa so với bản trước — phát hiện khi kiểm DDL thật:** bản đầu gồm cả `render_document` trong danh sách `job_type`. Sai: `contracts/schema.sql` — `CONSTRAINT ck_job_document_subject CHECK (job_type NOT IN ('resume_document_graph', 'finalize_issue') OR subject_document_id IS NOT NULL)` — chỉ ép `subject_document_id` cho hai loại đó; `render_document` **không có** `document_id` khi enqueue (document chưa tồn tại). Lọc theo `subject_document_id = :document_id AND job_type IN (..., 'render_document', ...)` sẽ không bao giờ khớp dòng `render_document` nào — cờ vẫn tính đúng cho hai loại kia, chỉ là "phủ cả `render_document`" trong mô tả cũ là sai, không phải lỗi tính toán. Đã sửa mục 3.2 của `11-ops.md`: `render_document` thất bại vĩnh viễn đi đường khác (`notification_send` tham chiếu `request_id`), không qua cờ này — một document mà `render_document` thất bại sẽ không bao giờ tồn tại hoặc không bao giờ tới `PENDING_APPROVAL` để xuất hiện trên hai endpoint dưới đây, nên việc loại nó khỏi cờ `document.job_failed` không mất khả năng quan sát nào, chỉ đúng lại phạm vi.

**Diff đề xuất — response của `GET /review-queue` và `GET /issue-queue`:** thêm trường `job_failed: boolean` cạnh `halted`, `issue_in_progress` đã có (mục Hàng đợi duyệt của `08-hitl.md`).

```yaml
job_failed:
  type: boolean
  description: >
    Job resume_document_graph hoặc finalize_issue mới nhất cho document này
    đã FAILED vĩnh viễn (hết max_attempts). Dẫn xuất, không lưu cột — mục
    Background worker & Cron của 11-ops.md. Không phủ render_document (xem
    ghi chú cùng mục — document chưa tồn tại nếu job đó thất bại).
```

**Cách tính (server, tại thời điểm trả response) — không cache, không lưu bảng:**

```sql
-- Với mỗi document trong trang kết quả: dòng job mới nhất trong hai loại có subject_document_id bắt buộc
SELECT status = 'FAILED' AS job_failed
FROM job
WHERE subject_document_id = :document_id
  AND job_type IN ('resume_document_graph', 'finalize_issue')
ORDER BY enqueued_at DESC
LIMIT 1;
```

**Index mới cần, chưa có:** `ix_job_pending_by_document` hiện chỉ là partial trên `QUEUED`/`RUNNING` (mục Vận hành của `04-data.md`) — không phủ truy vấn trên. Đề xuất `ix_job_latest_by_document (subject_document_id, enqueued_at DESC)` — **không** gồm `job_type` trong index: với mỗi `document_id`, tổng số job đời nó rất nhỏ (`resume_document_graph`/`finalize_issue` là hai trong sáu loại, không phải job lặp lại nhiều lần bình thường), nên lọc `job_type` như một điều kiện phụ sau khi tra `subject_document_id` rẻ hơn việc giữ index rộng hơn cho một trường ít chọn lọc. Không điều kiện partial (cần đọc cả dòng `FAILED`, không chỉ `QUEUED`/`RUNNING` như index đã có). **Đây là một thay đổi tới `04-data.md`/`schema.sql`, duyệt cùng lượt với đề xuất này** — không tự thêm.

## 2. Mã lỗi cho Lớp 3 (ADR-023) từ chối chuyển `operating_mode`

**Vì sao:** ADR-023 Lớp 3 — `POST /operating-mode/transitions` từ chối khi `BO19_ENVIRONMENT ≠ prod` và yêu cầu chuyển sang `PRODUCTION` — chưa có mã lỗi trong danh mục `error_code` của `05-api.md`.

**Diff đề xuất — thêm vào mục Mã lỗi của `05-api.md`:**

| `error_code` | HTTP status | Khi nào | Thông điệp |
|---|---|---|---|
| `ENVIRONMENT_NOT_ALLOWED` | 403 | `POST /operating-mode/transitions` với `to_mode = PRODUCTION` khi `BO19_ENVIRONMENT ≠ prod` | *"Không thể chuyển sang chế độ sản xuất ở môi trường này."* |

**Không dùng mã lỗi chung `FORBIDDEN`** — phân biệt với từ chối do thiếu permission (AuthZ thường), vì đây là một luật nghiệp vụ khác, và Phase 13 cần truy vết được hai loại từ chối riêng.

## Không tự áp — lý do

Cả hai thay đổi đụng `05-api.md`/`contracts/openapi.yaml` (đã đóng) và một thay đổi kéo theo `04-data.md` (index mới). Theo tiền lệ Phase 9 (tự thêm endpoint 2.2b khi thiết kế của chính nó cần), đây là con đường đúng — nhưng cần PO duyệt nội dung trước khi áp, không phải một ngoại lệ mới cho "endpoint có thể tự thêm bất cứ lúc nào".
