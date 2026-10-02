-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0009
-- ADR-035 (PO duyệt 2026-10-02): reasoning_tokens tính vào token budget A-022 và được
-- ghi vào llm_usage. Diễn giải: docs/design/04-data.md, đoạn "Cột reasoning_tokens"
-- ở phần llm_usage; docs/design/11-ops.md mục Định cỡ A-022.
-- =============================================================================
--
-- Áp SAU 0008_temporary_permission_grant.sql, bằng bo19_migrator, trong một giao
-- dịch riêng (ADR-017). KHÔNG sửa 0001_initial.sql / contracts/schema.sql hay
-- migration nào trước.
--
-- NULL khi provider không trả số token suy luận — không suy ra.
-- Không GRANT mới: bo19_app đã có SELECT, INSERT trên cả bảng llm_usage (nhóm
-- "Chỉ thêm" của 04-data.md); cột mới nằm trong quyền đó.
-- =============================================================================

ALTER TABLE llm_usage ADD COLUMN reasoning_tokens integer;

ALTER TABLE llm_usage ADD CONSTRAINT ck_llm_usage_reasoning_tokens
    CHECK (reasoning_tokens IS NULL OR reasoning_tokens >= 0);
