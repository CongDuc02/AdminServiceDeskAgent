-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0015
-- M1.2 / ADR-043 (PO duyệt 2026-10-21): chuỗi số văn bản duy nhất trong (sổ, dải, KỲ), không phải trong cả đời của (sổ, dải).
-- Lý do: khuôn số của PO `{seq}/GXN-{symbol}` không có năm, và Nghị định 30/2020/NĐ-CP đánh lại từ 01 mỗi năm
-- ("duy nhất trong một năm" — docs/reference/nghi-dinh-30-2020-so-ky-hieu-van-ban.md). Khoá cũ làm `finalize_issue`
-- hỏng ngay lần phát hành đầu tiên của năm sau.
-- Diễn giải: docs/design/04-data.md mục 4 (Sổ số văn bản); docs/design/decisions/ADR-043-so-van-ban-duy-nhat-theo-ky.md.
-- =============================================================================
--
-- Áp SAU 0014_document_render_watermark_text.sql, bằng bo19_migrator, trong một giao dịch riêng (ADR-017).
-- KHÔNG sửa 0001_initial.sql / contracts/schema.sql hay migration nào trước.
--
-- Không GRANT mới: ràng buộc không phải quyền; bo19_app vẫn chỉ INSERT dòng sổ và UPDATE status/voided_at/void_reason.
--
-- TƯƠNG THÍCH NGƯỢC: khoá mới RỘNG hơn khoá cũ (thêm một cột) nên mọi tập dòng thoả khoá cũ đều thoả khoá mới —
-- ADD CONSTRAINT không thể trượt trên dữ liệu đang có. Tên ràng buộc GIỮ NGUYÊN: mã đang live bắt UniqueViolation
-- theo `constraint_name = 'uq_register_entry_number'` (tool_layer/numbering) nên chạy nguyên trên schema mới.
-- Bỏ rồi thêm lại cùng tên trong CÙNG giao dịch: không có khoảnh khắc nào thiếu ràng buộc cho bên khác thấy
-- (DROP CONSTRAINT lấy ACCESS EXCLUSIVE tới hết giao dịch).
--
-- QUAY LUI (nếu cần): DROP rồi ADD UNIQUE (document_register_id, series, formatted_number). Chỉ làm được khi chưa có hai dòng
-- cùng chuỗi số ở hai kỳ khác nhau — tức trước ngày đầu năm đầu tiên dùng khuôn số không có năm.
-- =============================================================================

ALTER TABLE document_register_entry DROP CONSTRAINT uq_register_entry_number;

ALTER TABLE document_register_entry ADD CONSTRAINT uq_register_entry_number
    UNIQUE (document_register_id, series, period_key, formatted_number);
