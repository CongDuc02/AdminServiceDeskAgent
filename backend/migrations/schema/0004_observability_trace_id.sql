-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0004
-- Phase 11 — Ops, Cost & Deployment. Diễn giải đầy đủ: docs/design/11-ops.md
-- mục Log schema (6.1); docs/design/decisions/ADR-024-dinh-dang-trace-id.md
-- =============================================================================
--
-- Áp SAU 0003_job_failed_index.sql, bằng bo19_migrator, trong một giao dịch
-- riêng (mục Trình tự migration của ADR-017). KHÔNG sửa 0001_initial.sql /
-- contracts/schema.sql — file đó đã đóng ở Phase 6. KHÔNG sửa
-- 0002_phase9_security.sql hay 0003_job_failed_index.sql — mỗi thay đổi một
-- file (mục 3 của 06-structure.md).
--
-- Đóng câu bỏ ngỏ của ADR-019 ("Thêm CHECK hình dạng cần định dạng của
-- trace_id, mà chưa phase nào chốt — không bịa ở đây"): định dạng UUID v4,
-- chữ thường, có gạch nối (ADR-024). Cột llm_usage.trace_id đã NOT NULL từ
-- 0001_initial.sql — migration này chỉ thêm hình dạng, không đổi tính NULL.
-- Không áp cho audit_event.trace_id (cột đó nullable, ngoài phạm vi câu bỏ
-- ngỏ của ADR-019 — chỉ nói về llm_usage). Không cấp GRANT mới — CHECK
-- không đổi nhóm quyền của bo19_app trên llm_usage.
--
-- Điều kiện đảo ngược (ADR-024, buộc chéo vào A-069): nếu công cụ APM chọn
-- sau này ép một định dạng trace_id khác, quyết định này phải mở lại.
-- =============================================================================

ALTER TABLE llm_usage
    ADD CONSTRAINT ck_llm_usage_trace_id
    CHECK (trace_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$');
