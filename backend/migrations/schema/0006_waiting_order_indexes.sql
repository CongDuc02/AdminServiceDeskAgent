-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0006
-- Đợt sửa 1 sau Phase 13. Diễn giải: docs/design/13-audit.md mục Việc được
-- giao cho Phase 13; docs/design/05-api.md mục Phân trang; docs/design/04-data.md
-- mục Bảng chi tiết (bảng Index của Hội thoại và request, và của Văn bản)
-- =============================================================================
--
-- Áp SAU 0005_rate_limit_window_column_grant.sql, bằng bo19_migrator, trong một
-- giao dịch riêng (ADR-017). KHÔNG sửa 0001_initial.sql / contracts/schema.sql
-- hay migration nào trước — mỗi thay đổi một file.
--
-- Hai index do 05-api.md đề xuất ở Phase 5, PO nhận ở Phase 13 (2026-09-26).
-- Chỉ thêm index trên bảng đã có — không tạo bảng, không cần GRANT mới.
--
-- ix_request_waiting — GET /requests?scope=ALL (AC Must của F4): danh sách gộp
--   bốn trạng thái mở sau SUBMITTED, sắp theo status_changed_at tăng dần — chờ
--   lâu nhất trước. Cột thời gian đứng đầu để danh sách gộp đi thẳng theo index;
--   id ở cuối để keyset không phải sắp thêm ở chỗ trùng.
-- ix_document_awaiting_issue — GET /issue-queue: văn bản SIGNED hoặc SEALED,
--   cùng hình dạng. Dòng SIGNED cần dấu chỉ tồn tại thoáng qua vì document_sign
--   chuyển tiếp sang PENDING_SEAL trong cùng thao tác.
-- =============================================================================

CREATE INDEX ix_request_waiting
    ON request (status_changed_at, id)
    WHERE status IN ('SUBMITTED', 'IN_REVIEW', 'CHANGES_REQUESTED', 'APPROVED');

CREATE INDEX ix_document_awaiting_issue
    ON document (status_changed_at, id)
    WHERE status IN ('SIGNED', 'SEALED');
