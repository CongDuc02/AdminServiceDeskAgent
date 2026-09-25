-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0005
-- Vòng duyệt Phase 12. Diễn giải: docs/design/proposals/
-- migration-0005-rate-limit-window-column-grant.md
-- =============================================================================
--
-- Áp SAU 0004_observability_trace_id.sql, bằng bo19_migrator, trong một giao
-- dịch riêng (mục Trình tự migration của ADR-017). KHÔNG sửa 0002 — mỗi thay
-- đổi một file (mục 3 của 06-structure.md).
--
-- Thu hẹp quyền UPDATE của bo19_app trên rate_limit_window từ cả bảng xuống
-- đúng cột attempt_count, khớp nhóm "Đếm và dọn theo cửa sổ" ở mục Nguyên tắc
-- dữ liệu của 04-data.md. scope và window_start là khoá chính: không thao tác
-- nào cần sửa chúng tại chỗ.
--
-- Áp CÙNG COMMIT với bản sửa tools/contract-checks/check_grants.py (nhóm
-- MIGRATION_COLUMN_UPDATE) — tách hai thay đổi thì bộ kiểm báo lệch ở giữa.
-- =============================================================================

REVOKE UPDATE ON rate_limit_window FROM bo19_app;
GRANT UPDATE (attempt_count) ON rate_limit_window TO bo19_app;
