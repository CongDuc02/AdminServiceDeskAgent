-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0008
-- Quyết định PO sau đợt sửa 3b (A-078 chọn (a)). Diễn giải: docs/design/11-ops.md
-- mục Runbook — cấp và thu hồi permission tạm; docs/design/08-hitl.md mục Tách
-- biệt trách nhiệm — D-006; docs/design/ASSUMPTIONS.md A-078.
-- =============================================================================
--
-- Áp SAU 0007_takeover_and_self_approval.sql, bằng bo19_migrator, trong một giao
-- dịch riêng (ADR-017). KHÔNG sửa 0001_initial.sql / contracts/schema.sql hay
-- migration nào trước.
--
-- Lần cấp tạm một permission — khi mọi người khác mang permission đó vắng dài
-- ngày — là một dòng employee_permission_grant mang đủ ba trường: lý do, người
-- duyệt, ngày dự kiến thu hồi. Dòng cấp lẻ thường xuyên (document.sign,
-- document.revoke_confirm…) không mang trường nào trong ba. Không có dòng nửa vời.
--
-- Không GRANT mới: bo19_app chỉ có SELECT trên bảng này (J.1). Cấp và thu hồi là
-- thao tác vận hành chạy bằng bo19_migrator.
-- =============================================================================

ALTER TABLE employee_permission_grant ADD COLUMN grant_reason text;
ALTER TABLE employee_permission_grant ADD COLUMN approved_by_employee_id uuid REFERENCES employee (id);
ALTER TABLE employee_permission_grant ADD COLUMN expected_revoke_on date;

-- Cấp tạm có đủ cả ba trường, hoặc là cấp thường xuyên và không có trường nào.
ALTER TABLE employee_permission_grant ADD CONSTRAINT ck_permission_grant_temporary_complete
    CHECK ((grant_reason IS NULL) = (approved_by_employee_id IS NULL)
           AND (grant_reason IS NULL) = (expected_revoke_on IS NULL));

ALTER TABLE employee_permission_grant ADD CONSTRAINT ck_permission_grant_reason_not_blank
    CHECK (grant_reason IS NULL OR btrim(grant_reason) <> '');

-- Người duyệt không phải người được cấp.
ALTER TABLE employee_permission_grant ADD CONSTRAINT ck_permission_grant_approver_not_grantee
    CHECK (approved_by_employee_id IS DISTINCT FROM employee_id);
