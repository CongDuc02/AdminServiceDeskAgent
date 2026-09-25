-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0003
-- Phase 11 — Ops, Cost & Deployment. Diễn giải đầy đủ: docs/design/11-ops.md
-- mục Background worker & Cron; docs/design/04-data.md mục 3.8 (bảng Index)
-- =============================================================================
--
-- Áp SAU 0002_phase9_security.sql, bằng bo19_migrator, trong một giao dịch
-- riêng (mục Trình tự migration của ADR-017). KHÔNG sửa 0001_initial.sql /
-- contracts/schema.sql — file đó đã đóng ở Phase 6, và KHÔNG sửa
-- 0002_phase9_security.sql — file đó đã đóng ở Phase 9 ("mỗi thay đổi một
-- file", mục 3 của 06-structure.md).
--
-- Một index mới trên bảng `job` (đã tồn tại từ 0001_initial.sql) — không tạo
-- bảng mới, không cần GRANT mới (quyền trên `job` đã cấp ở 0001). Phục vụ cờ
-- dẫn xuất `document.job_failed` (đề xuất docs/design/proposals/
-- diff-05-api-job-failed-and-reject-error.md, PO duyệt 2026-09-25): tìm dòng
-- `job` mới nhất trong {resume_document_graph, finalize_issue} cho một
-- document_id, kể cả dòng FAILED — ix_job_pending_by_document (đã có) là
-- partial trên QUEUED/RUNNING, không phủ được truy vấn này.
-- =============================================================================

CREATE INDEX ix_job_latest_by_document
    ON job (subject_document_id, enqueued_at DESC);
