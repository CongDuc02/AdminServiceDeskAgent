-- =============================================================================
-- BO-19 Admin Service Desk Agent — data migration 0001
-- Danh mục permission, vai trò, gói permission theo vai trò.
-- Nguồn: mục Permission và vai trò của docs/design/00-domain.md (D-005),
-- cập nhật ở Phase 9 (docs/design/09-security.md, mục AuthZ).
-- =============================================================================
--
-- Áp SAU mọi schema migration (0001_initial.sql, 0002_phase9_security.sql),
-- bằng bo19_migrator, trong một giao dịch riêng (mục Trình tự migration của
-- ADR-017, bước 4). File này chỉ INSERT — không tạo bảng, không GRANT.
--
-- KHÔNG có ở đây: employee_role, employee_permission_grant. Hai bảng đó cần
-- employee_id thật; không có nhân viên nào được seed ở Sprint đầu (import CSV
-- là việc của employee_import, D-002). Cấp permission cho một nhân viên cụ thể
-- — kể cả sáu permission cấp lẻ dưới đây — là thao tác vận hành riêng, chạy
-- sau khi đã import employee và đã biết ai nhận quyền gì (mục AuthZ của
-- 09-security.md; chưa có ai được chỉ định ở Sprint đầu).
-- =============================================================================

INSERT INTO permission (code, description) VALUES
    ('request.create',            'Tạo yêu cầu qua chat cho chính mình'),
    ('request.create_on_behalf',  'Tạo yêu cầu với beneficiary_employee_id khác người tạo'),
    ('request.read_own',          'Xem yêu cầu do mình tạo'),
    ('request.read_assigned',     'Xem yêu cầu được định tuyến tới mình'),
    ('request.read_all',          'Xem mọi yêu cầu trong tổ chức'),
    ('request.supply_info',       'Bổ sung thông tin cho yêu cầu của mình'),
    ('request.cancel_own',        'Huỷ yêu cầu của mình khi chưa APPROVED'),
    ('document.approve_content',  'Duyệt nội dung tại cổng PENDING_APPROVAL'),
    ('document.request_changes',  'Trả lại kèm yêu cầu sửa'),
    ('document.reject',           'Từ chối kèm lý do'),
    ('document.sign',             'Ký văn bản tại PENDING_SIGNATURE'),
    ('document.apply_seal',       'Đóng dấu tại cổng PENDING_SEAL'),
    ('document.issue',            'Cấp số và phát hành'),
    ('document.revoke_initiate',  'Khởi tạo thu hồi văn bản đã phát hành'),
    ('document.revoke_confirm',   'Xác nhận thu hồi'),
    ('template.manage',           'Quản lý mẫu văn bản và phiên bản mẫu'),
    ('procedure.manage',          'Nạp, thay phiên bản và gỡ tài liệu của kho quy trình hành chính; người nạp cam kết tài liệu không chứa dữ liệu cá nhân'),
    ('employee.import',           'Import CSV hồ sơ nhân viên'),
    ('booking.confirm',           'Xác nhận hoặc từ chối đặt phòng'),
    ('delegation.manage',         'Lập và thu hồi uỷ quyền'),
    ('audit.read_own',            'Xem nhật ký của yêu cầu liên quan tới mình'),
    ('audit.read_all',            'Xem toàn bộ nhật ký kiểm toán'),
    ('request_type.manage',       'Thêm/sửa request_type, slot_definition — trừ đổi độ nhạy của một slot đã có'),
    ('procedure.read_all',        'Xem mọi procedure_document qua procedure_retrieval, bất kể department_scope'),
    ('operating_mode.change',     'Đổi operating_mode giữa NON_PRODUCTION và PRODUCTION');

INSERT INTO role (code, name_vi) VALUES
    ('EMPLOYEE',      'Nhân viên'),
    ('ADMIN_OFFICER', 'Cán bộ hành chính'),
    ('SIGNER',        'Người ký cấp trên');

-- EMPLOYEE
INSERT INTO role_permission (role_code, permission_code) VALUES
    ('EMPLOYEE', 'request.create'),
    ('EMPLOYEE', 'request.read_own'),
    ('EMPLOYEE', 'request.supply_info'),
    ('EMPLOYEE', 'request.cancel_own'),
    ('EMPLOYEE', 'audit.read_own');

-- ADMIN_OFFICER — toàn bộ của EMPLOYEE, cộng phần riêng
INSERT INTO role_permission (role_code, permission_code) VALUES
    ('ADMIN_OFFICER', 'request.create'),
    ('ADMIN_OFFICER', 'request.read_own'),
    ('ADMIN_OFFICER', 'request.supply_info'),
    ('ADMIN_OFFICER', 'request.cancel_own'),
    ('ADMIN_OFFICER', 'audit.read_own'),
    ('ADMIN_OFFICER', 'request.create_on_behalf'),
    ('ADMIN_OFFICER', 'request.read_all'),
    ('ADMIN_OFFICER', 'document.approve_content'),
    ('ADMIN_OFFICER', 'document.request_changes'),
    ('ADMIN_OFFICER', 'document.reject'),
    ('ADMIN_OFFICER', 'document.apply_seal'),
    ('ADMIN_OFFICER', 'document.issue'),
    ('ADMIN_OFFICER', 'document.revoke_initiate'),
    ('ADMIN_OFFICER', 'template.manage'),
    ('ADMIN_OFFICER', 'employee.import'),
    ('ADMIN_OFFICER', 'audit.read_all'),
    ('ADMIN_OFFICER', 'booking.confirm');

-- SIGNER — [Should]. Gói tồn tại trong danh mục; không ai được employee_role
-- này ở Sprint đầu (mục Permission và vai trò của 00-domain.md).
INSERT INTO role_permission (role_code, permission_code) VALUES
    ('SIGNER', 'request.read_assigned'),
    ('SIGNER', 'document.approve_content'),
    ('SIGNER', 'document.request_changes'),
    ('SIGNER', 'document.reject'),
    ('SIGNER', 'document.sign'),
    ('SIGNER', 'document.revoke_confirm'),
    ('SIGNER', 'audit.read_own');

-- Cấp lẻ, KHÔNG vào role_permission của bất kỳ vai trò nào (mục Permission và
-- vai trò của 00-domain.md; mục AuthZ của 09-security.md):
--   document.sign, document.revoke_confirm  — cấp lẻ cho một vài ADMIN_OFFICER
--                                              cụ thể (D-006), ngoài SIGNER
--   procedure.manage, request_type.manage,
--   procedure.read_all, operating_mode.change — cấp lẻ, không thuộc gói nào
-- Cấp cho ai: employee_permission_grant, thao tác vận hành bằng bo19_migrator,
-- sau khi có nhân viên thật và người có tên được chỉ định. Không seed ở đây.
