-- =============================================================================
-- BO-19 Admin Service Desk Agent — data migration 0002
-- Cấu hình loại yêu cầu của Sprint 1: catalog sáu loại, slot schema của WORK_CONFIRMATION, sổ văn bản.
-- Nguồn: mục Request Type Catalog và mục Slot schema (3.2) của docs/design/00-domain.md;
--        docs/design/proposals/validation-rules-vocabulary.md (PO duyệt 2026-10-09).
-- =============================================================================
--
-- Áp SAU mọi schema migration, bằng bo19_migrator (ADR-017, bước 4). Chỉ INSERT.
-- migrate_main áp thư mục này trên MỌI môi trường kể cả Render, nên file này KHÔNG mang dữ
-- liệu cá nhân và không mang employee nào. Mọi chuỗi dưới đây là CẤU HÌNH, không phải dữ liệu giả.
--
-- `example_phrases` và `description` của từng loại vào prompt P1; `description` của slot vào
-- slot_specs của P2. Chúng do người triển khai (Claude) soạn, viết tiếng Việt tự nhiên — KHÔNG
-- mang chữ "(giả)", vì chúng áp lên cả Render. PO duyệt trước UAT (cổng 4.7 của 12-roadmap.md).
--
-- Sprint 1 chỉ hỗ trợ WORK_CONFIRMATION (roadmap, Sprint 1). Năm loại còn lại là KNOWN_UNSUPPORTED:
-- chúng có mặt để P1 nhận ra và báo "chưa hỗ trợ" thay vì ép vào loại gần giống (EC-CV-03, EC-WC-03).
--
-- Giá trị làm việc, nhãn "chưa hiệu chỉnh": purpose.min_tokens = 3 (PO, 2026-10-09 — đếm đơn vị
-- cách nhau bởi khoảng trắng, với tiếng Việt là đếm tiếng); document_register.reset_policy = YEARLY
-- (A-009: cơ chế đánh số theo năm; định dạng số và ký hiệu là mốc M1.2, chưa có ở đây).
-- =============================================================================

INSERT INTO document_register (id, code, name, reset_policy) VALUES
    ('7c2f0e1a-5b3d-4c8e-9a41-1d6b7e90a001', 'WORK_CONFIRMATION', 'Sổ văn bản — Giấy xác nhận công tác', 'YEARLY');

INSERT INTO request_type (code, name_vi, description, support_status, artifact_kind, requires_seal_default, seal_type_default, document_register_id, example_phrases) VALUES
    ('WORK_CONFIRMATION', 'Giấy xác nhận công tác',
     'Giấy xác nhận nhân viên đang hoặc đã từng làm việc tại tổ chức, dùng cho hồ sơ vay vốn, làm thủ tục hành chính hoặc gửi cơ quan khác.',
     'SUPPORTED', 'DOCUMENT', true, 'ORGANIZATION_ROUND', '7c2f0e1a-5b3d-4c8e-9a41-1d6b7e90a001',
     ARRAY['xin giấy xác nhận công tác',
           'cho mình xin giấy xác nhận đang làm việc tại công ty',
           'cần giấy xác nhận công tác để làm hồ sơ vay vốn ngân hàng',
           'xác nhận giúp mình là nhân viên của công ty']),
    ('INTRODUCTION_LETTER', 'Giấy giới thiệu',
     'Giấy giới thiệu một nhân viên đến làm việc với cơ quan, tổ chức khác.',
     'KNOWN_UNSUPPORTED', 'DOCUMENT', true, 'ORGANIZATION_ROUND', NULL,
     ARRAY['xin giấy giới thiệu đi làm việc với đối tác',
           'cần giấy giới thiệu để liên hệ cơ quan nhà nước',
           'làm giúp mình giấy giới thiệu']),
    ('ROOM_BOOKING', 'Đặt phòng họp',
     'Đặt phòng họp theo thời gian và số người tham dự.',
     'KNOWN_UNSUPPORTED', 'ROOM_BOOKING', false, NULL, NULL,
     ARRAY['đặt phòng họp chiều mai',
           'mình muốn đặt phòng họp cho mười người',
           'book giúp mình phòng họp sáng thứ sáu']),
    ('SEAL_REQUEST', 'Yêu cầu đóng dấu cho văn bản ngoài',
     'Đóng dấu của tổ chức lên văn bản do nhân viên hoặc bên ngoài soạn.',
     'KNOWN_UNSUPPORTED', 'SEAL_ACTION', NULL, NULL, NULL,
     ARRAY['xin đóng dấu công ty vào hợp đồng',
           'cần đóng dấu cho văn bản do mình soạn',
           'đóng dấu giáp lai cho bộ hồ sơ này']),
    ('INCOME_CONFIRMATION', 'Giấy xác nhận thu nhập',
     'Giấy xác nhận mức lương, thu nhập của nhân viên, dùng để chứng minh thu nhập.',
     'KNOWN_UNSUPPORTED', 'DOCUMENT', true, 'ORGANIZATION_ROUND', NULL,
     ARRAY['xin giấy xác nhận thu nhập',
           'cần giấy xác nhận lương để vay ngân hàng',
           'xác nhận giúp mình mức lương hiện tại']),
    ('BUSINESS_TRIP_ORDER', 'Quyết định cử đi công tác',
     'Quyết định cử nhân viên đi công tác trong nước hoặc nước ngoài.',
     'KNOWN_UNSUPPORTED', 'DOCUMENT', true, 'ORGANIZATION_ROUND', NULL,
     ARRAY['làm quyết định cử mình đi công tác',
           'xin quyết định công tác tại chi nhánh',
           'cần quyết định đi công tác nước ngoài']);

-- Slot schema của WORK_CONFIRMATION (00-domain.md, mục 3.2). Slot nguồn SYSTEM bắt buộc "khi ISSUED"
-- (document_number, issued_date, signer_user_id) có is_required = false: hàm "đủ điều kiện xử lý" chạy
-- TRƯỚC SUBMITTED, khi chúng chưa thể có. `language` [Could] không nạp ở Sprint 1 (V4, PO 2026-10-09).
INSERT INTO slot_definition (request_type_code, slot_name, data_type, source, sensitivity, is_required, validation_rules, description, label_vi, display_order) VALUES
    ('WORK_CONFIRMATION', 'requester_employee_code', 'STRING', 'SYSTEM',     'INT', true,  '{}', 'Mã nhân viên của người đang yêu cầu, lấy từ phiên đăng nhập.', 'Mã nhân viên người yêu cầu', 10),
    ('WORK_CONFIRMATION', 'beneficiary_employee_id',  'STRING', 'SYSTEM',     'INT', true,  '{}', 'Mã định danh của nhân viên được cấp giấy; mặc định là người yêu cầu.', 'Người được cấp giấy', 20),
    ('WORK_CONFIRMATION', 'full_name',                'STRING', 'HR_PROFILE', 'PER', true,  '{}', 'Họ và tên theo hồ sơ nhân sự.', 'Họ và tên', 30),
    ('WORK_CONFIRMATION', 'department_name',          'STRING', 'HR_PROFILE', 'INT', true,  '{}', 'Tên phòng ban theo hồ sơ nhân sự.', 'Phòng ban', 40),
    ('WORK_CONFIRMATION', 'job_title',                'STRING', 'HR_PROFILE', 'INT', true,  '{}', 'Chức danh theo hồ sơ nhân sự.', 'Chức danh', 50),
    ('WORK_CONFIRMATION', 'contract_type',            'ENUM',   'HR_PROFILE', 'PER', true,  '{"one_of": ["PROBATION", "FIXED_TERM", "INDEFINITE"]}', 'Loại hợp đồng lao động theo hồ sơ nhân sự; quyết định câu chữ trong văn bản.', 'Loại hợp đồng', 60),
    ('WORK_CONFIRMATION', 'employment_start_date',    'DATE',   'HR_PROFILE', 'PER', true,  '{}', 'Ngày bắt đầu làm việc theo hồ sơ nhân sự.', 'Ngày bắt đầu làm việc', 70),
    ('WORK_CONFIRMATION', 'employment_end_date',      'DATE',   'HR_PROFILE', 'PER', false, '{}', 'Ngày nghỉ việc theo hồ sơ nhân sự, nếu đã nghỉ.', 'Ngày nghỉ việc', 80),
    ('WORK_CONFIRMATION', 'date_of_birth',            'DATE',   'HR_PROFILE', 'PER', false, '{}', 'Ngày sinh theo hồ sơ nhân sự; chỉ đưa vào văn bản khi nơi nhận yêu cầu.', 'Ngày sinh', 90),
    ('WORK_CONFIRMATION', 'national_id',              'STRING', 'HR_PROFILE', 'RES', false, '{}', 'Số định danh cá nhân theo hồ sơ nhân sự.', 'Số định danh cá nhân', 100),
    ('WORK_CONFIRMATION', 'purpose',                  'TEXT',   'USER_INPUT', 'RES', true,  '{"non_blank": true, "min_tokens": 3}',
        'Mục đích nhân viên cần giấy xác nhận công tác, nêu cụ thể điều nhân viên nói (ví dụ: bổ sung hồ sơ vay vốn tại ngân hàng).', 'Mục đích sử dụng giấy', 110),
    ('WORK_CONFIRMATION', 'recipient_org',            'STRING', 'USER_INPUT', 'PER', true,  '{"non_blank": true}',
        'Tên cơ quan, tổ chức hoặc đơn vị nhận giấy xác nhận (phần Kính gửi).', 'Nơi nhận (Kính gửi)', 120),
    ('WORK_CONFIRMATION', 'copies_count',             'INT',    'USER_INPUT', 'INT', false, '{"int_range": {"min": 1}}',
        'Số bản giấy xác nhận cần cấp, là một số nguyên dương; mặc định một bản.', 'Số bản cần cấp', 130),
    ('WORK_CONFIRMATION', 'document_number',          'STRING', 'SYSTEM',     'INT', false, '{}', 'Số văn bản, hệ thống cấp khi phát hành.', 'Số văn bản', 140),
    ('WORK_CONFIRMATION', 'issued_date',              'DATE',   'SYSTEM',     'INT', false, '{}', 'Ngày cấp, bằng ngày cấp số.', 'Ngày cấp', 150),
    ('WORK_CONFIRMATION', 'signer_user_id',           'STRING', 'SYSTEM',     'INT', false, '{}', 'Người ký, do định tuyến duyệt quyết định.', 'Người ký', 160);
