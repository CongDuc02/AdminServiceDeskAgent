# `contracts/` — contract của BO-19

Thư mục này giữ contract dạng khai báo: `openapi.yaml` (API) và `schema.sql` (DDL). Contract là nguồn, mã theo nó — mục Nguyên tắc của `06-structure.md`.

## `schema.sql` dừng ở trạng thái đóng Phase 6

**`schema.sql` không phải toàn bộ schema đang chạy.** Nó giữ nguyên byte từ lúc Phase 6 đóng, và trùng sha256 với `backend/migrations/schema/0001_initial.sql` — `937ca184…` cho file LF trong repo. *Đính chính 2026-10-02:* con số `0ce8dd…` ghi trước đây là sha của bản checkout CRLF trên Windows; `.gitattributes` nay giữ LF cho mọi `*.sql`. Từ đó, mỗi thay đổi schema là **một file migration mới** (ADR-017) — `schema.sql` không bị sửa.

**Schema đang có hiệu lực = `0001` → migration mới nhất**, áp theo thứ tự. Lệch giữa `schema.sql` và migration thì **migration đúng** (mục Thang mức độ và thứ bậc nguồn sự thật của `13-audit.md`).

Không sửa `schema.sql` — kể cả chỉ một dòng chú thích. Sửa thì sha256 đổi và nó hết trùng byte với `0001`; `tools/contract-checks/check_grants.py --local-migrated` dựa vào sự trùng đó để áp `0001` thay cho `schema.sql`. Quyết định của PO, 2026-09-26 (AUD-03 của `13-audit.md`).

## Migration schema sau `schema.sql`

| File trong `backend/migrations/schema/` | Thêm gì | Nguồn thiết kế |
|---|---|---|
| `0002_phase9_security.sql` | Bảng `employee_credential`, `rate_limit_window`; index `ix_rate_limit_window_start`; quyền của `bo19_app` trên hai bảng đó | Mục Migration bổ sung của Phase 9 trong `09-security.md` |
| `0003_job_failed_index.sql` | Index `ix_job_latest_by_document` | Mục Background worker & Cron của `11-ops.md` |
| `0004_observability_trace_id.sql` | `CHECK` định dạng UUID v4 trên `llm_usage.trace_id` | ADR-024 |
| `0005_rate_limit_window_column_grant.sql` | Thu hẹp quyền `UPDATE` của `bo19_app` trên `rate_limit_window` còn đúng cột `attempt_count` | `proposals/migration-0005-rate-limit-window-column-grant.md` |
| `0006_waiting_order_indexes.sql` | Index `ix_request_waiting`, `ix_document_awaiting_issue` | Mục Phân trang của `05-api.md`; mục Việc được giao cho Phase 13 của `13-audit.md` |
| `0007_takeover_and_self_approval.sql` | Bốn `step_kind` mới (`TAKEOVER`, `ISSUE_ORDER`, `REVOKE_INITIATE`, `REVOKE_CONFIRM`); index `ix_approval_step_open_by_kind`; cột `decision_record.takeover_resolution`; khoá idempotency mới của `document_halt` (cột `takeover_step_id`, bỏ `uq_document_halt_once`); bảng mã `reason_code`, `archive_reason`, `event_code` thành `CHECK`; đường vào `ARCHIVED` từ `DRAFT`, `APPROVED` | Mục Bảng mã, mục Tiếp quản sau `halt_for_human`, mục Tách biệt trách nhiệm — D-006 của `08-hitl.md`; AUD-02, AUD-07, AUD-23 của `13-audit.md` |
| `0008_temporary_permission_grant.sql` | Ba cột `employee_permission_grant.grant_reason`, `approved_by_employee_id`, `expected_revoke_on` và ba `CHECK` cho lần cấp permission tạm | A-078; mục Runbook — cấp và thu hồi permission tạm của `11-ops.md` |
| `0009_llm_usage_reasoning_tokens.sql` | Cột `llm_usage.reasoning_tokens` và `CHECK` không âm | ADR-035; mục Định cỡ A-022 của `11-ops.md` |

Diễn giải từng bảng, cột và index — kể cả phần do migration thêm — ở mục Bảng chi tiết của `04-data.md`. Ngoài schema, còn hai thư mục migration khác: `backend/migrations/data/` (dữ liệu danh mục) và `backend/migrations/library/` (quyền trên bảng của thư viện checkpointer). Thứ tự áp cả ba thư mục ở mục Migration và checkpointer của `06-structure.md`.

**Thêm migration mới thì cập nhật bảng trên trong cùng thay đổi**, rồi chạy `check_grants.py --local-migrated`.

## Extension `x-bo19-*` về quyền trong `openapi.yaml`

*Thêm ở đợt sửa 4 sau Phase 13 (AUD-27).*

| Extension | Kiểu | Nghĩa |
|---|---|---|
| `x-bo19-permission` | danh sách permission | **Any-of** — người gọi có **ít nhất một** permission trong danh sách thì qua lớp kiểm ở `api`. Không bao giờ nghĩa là cần tất cả |
| `x-bo19-permission-also` | danh sách **nhóm**, mỗi nhóm là danh sách permission | Mỗi nhóm là any-of; người gọi phải thoả **mọi** nhóm, **cộng** `x-bo19-permission`. Vắng mặt nghĩa là không có điều kiện thêm |

Điều kiện đầy đủ ở `api` = any-of(`x-bo19-permission`) **và** any-of(từng nhóm của `x-bo19-permission-also`).

| Operation | `x-bo19-permission` | `x-bo19-permission-also` | Đọc thành |
|---|---|---|---|
| `GET /review-queue` | `document.approve_content`, `document.sign`, `document.apply_seal` | `[[request.read_all, request.read_assigned]]` | Một permission của hàng đợi **và** một trong hai quyền xem |
| `GET /takeover-queue` | `document.approve_content`, `document.reject`, `document.issue` | `[[request.read_all]]` | Một permission tiếp quản **và** `request.read_all` |

**Ngoài phạm vi của hai extension — vẫn ở `description` và ở `tool_layer`:**

- Permission phụ thuộc giá trị tham số — ví dụ `GET /review-queue?status=PENDING_SEAL` cần đúng `document.apply_seal`.
- Phạm vi dòng thấy được — `request.read_all` thấy mọi dòng, `request.read_assigned` chỉ dòng có bước giao cho mình, `request.read_own` chỉ dòng do mình tạo.
- D-006 — cần dữ liệu của dòng, kiểm ở thao tác cổng (mục Phân quyền ở tầng API của `05-api.md`).

Lớp kiểm ở `api` là điều kiện cần, không phải lớp duy nhất: `tool_layer` kiểm lại (mục Phân quyền ở tầng API của `05-api.md`).
