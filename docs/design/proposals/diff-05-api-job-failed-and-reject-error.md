# Đề xuất diff — `05-api.md` + `contracts/openapi.yaml`

**Trạng thái:** Chờ duyệt · **Nguồn:** mục Background worker & Cron (`job_failed`) và ADR-023 (mã lỗi Lớp 3) của `11-ops.md` · **Không tự áp** — `05-api.md` là phase đã đóng (☑ ở `_PLAN.md`), theo đúng tiền lệ Phase 9 đã tự thêm endpoint 2.2b khi thiết kế của chính nó cần

---

## 1. Trường `job_failed` trên hàng đợi duyệt

**Vì sao:** mục 3.2 của `11-ops.md` thiết kế cờ dẫn xuất `job_failed` (document có job `render_document`/`resume_document_graph`/`finalize_issue` mới nhất ở trạng thái `FAILED` vĩnh viễn) nhưng chưa endpoint nào trả nó.

**Diff đề xuất — response của `GET /review-queue` và `GET /issue-queue`:** thêm trường `job_failed: boolean` cạnh `halted`, `issue_in_progress` đã có (mục Hàng đợi duyệt của `08-hitl.md`).

```yaml
job_failed:
  type: boolean
  description: >
    Job hạ tầng (render/resume/finalize) mới nhất cho document này đã FAILED
    vĩnh viễn (hết max_attempts). Dẫn xuất, không lưu cột — mục Background
    worker & Cron của 11-ops.md.
```

**Cách tính (server, tại thời điểm trả response) — không cache, không lưu bảng:**

```sql
-- Với mỗi document trong trang kết quả: dòng job mới nhất theo job_type liên quan
SELECT status = 'FAILED' AS job_failed
FROM job
WHERE subject_document_id = :document_id
  AND job_type IN ('render_document', 'resume_document_graph', 'finalize_issue')
ORDER BY enqueued_at DESC
LIMIT 1;
```

**Index mới cần, chưa có:** `ix_job_pending_by_document` hiện chỉ là partial trên `QUEUED`/`RUNNING` (mục Vận hành của `04-data.md`) — không phủ truy vấn trên. Đề xuất thêm `ix_job_latest_by_document (subject_document_id, job_type, enqueued_at DESC)`, không điều kiện partial (cần đọc cả dòng `FAILED`). **Đây là một thay đổi tới `04-data.md`/`schema.sql`, cần duyệt cùng lượt**, không tự thêm.

## 2. Mã lỗi cho Lớp 3 (ADR-023) từ chối chuyển `operating_mode`

**Vì sao:** ADR-023 Lớp 3 — `POST /operating-mode/transitions` từ chối khi `BO19_ENVIRONMENT ≠ prod` và yêu cầu chuyển sang `PRODUCTION` — chưa có mã lỗi trong danh mục `error_code` của `05-api.md`.

**Diff đề xuất — thêm vào mục Mã lỗi của `05-api.md`:**

| `error_code` | HTTP status | Khi nào | Thông điệp |
|---|---|---|---|
| `ENVIRONMENT_NOT_ALLOWED` | 403 | `POST /operating-mode/transitions` với `to_mode = PRODUCTION` khi `BO19_ENVIRONMENT ≠ prod` | *"Không thể chuyển sang chế độ sản xuất ở môi trường này."* |

**Không dùng mã lỗi chung `FORBIDDEN`** — phân biệt với từ chối do thiếu permission (AuthZ thường), vì đây là một luật nghiệp vụ khác, và Phase 13 cần truy vết được hai loại từ chối riêng.

## Không tự áp — lý do

Cả hai thay đổi đụng `05-api.md`/`contracts/openapi.yaml` (đã đóng) và một thay đổi kéo theo `04-data.md` (index mới). Theo tiền lệ Phase 9 (tự thêm endpoint 2.2b khi thiết kế của chính nó cần), đây là con đường đúng — nhưng cần PO duyệt nội dung trước khi áp, không phải một ngoại lệ mới cho "endpoint có thể tự thêm bất cứ lúc nào".
