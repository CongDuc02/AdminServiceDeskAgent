-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0014
-- B9a / M5 (PO duyệt 2026-10-13, ADR-038): bản render ghi nhận chuỗi watermark đã đưa vào input của nó,
-- để sau UAT còn nói được "bản này mang chuỗi nào". Diễn giải: docs/design/04-data.md mục 5.1;
-- phép kiểm sau UAT: docs/design/11-ops.md mục 18.
-- =============================================================================
--
-- Áp SAU 0013_job_lease_id.sql, bằng bo19_migrator, trong một giao dịch riêng (ADR-017).
-- KHÔNG sửa 0001_initial.sql / contracts/schema.sql hay migration nào trước.
--
-- Không GRANT mới: bo19_app đã có quyền INSERT trên cả bảng `document_render`; cột mới thuộc cùng quyền cấp
-- cho bảng, và bảng vẫn không có UPDATE (ghi một lần — mục 5.1 của 04-data.md).
--
-- Cột nullable: PRODUCTION không có watermark nên NULL. Với NON_PRODUCTION, `ck_document_render_watermark`
-- bắt buộc có và không rỗng. Cột là LỜI KHAI của tool về input đã ra lệnh — không phải kết quả đọc lại từ file
-- (runtime không đọc lại PDF, ADR-038); bằng chứng về file là phép kiểm sau UAT.
--
-- Nếu bảng đã có dòng NON_PRODUCTION khi áp (không có đường ghi nào ngoài test trước B9a), ADD CONSTRAINT
-- THẤT BẠI to tiếng thay vì gán giá trị bịa; khi đó dừng và báo PO, không tự điền.
-- =============================================================================

ALTER TABLE document_render ADD COLUMN watermark_text text;

ALTER TABLE document_render ADD CONSTRAINT ck_document_render_watermark
    CHECK (operating_mode <> 'NON_PRODUCTION' OR (watermark_text IS NOT NULL AND watermark_text <> ''));
