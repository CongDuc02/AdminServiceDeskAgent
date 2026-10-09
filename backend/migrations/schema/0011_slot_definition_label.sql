-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0011
-- R4 của docs/design/proposals/reply-templates.md (PO duyệt 2026-10-09):
-- nhãn tiếng Việt của slot, đi cùng cấu hình DB như request_type.name_vi.
-- Diễn giải: docs/design/04-data.md, bảng slot_definition.
-- =============================================================================
--
-- Áp SAU 0010_llm_usage_estimated_duration.sql, bằng bo19_migrator, trong một giao
-- dịch riêng (ADR-017). KHÔNG sửa 0001_initial.sql / contracts/schema.sql hay
-- migration nào trước.
--
-- NOT NULL không có giá trị mặc định: bảng slot_definition còn rỗng ở thời điểm
-- migration này (cấu hình loại yêu cầu nạp bằng data migration 0002, áp SAU).
-- Không GRANT mới: bo19_app đã có SELECT, INSERT, UPDATE trên cả bảng (nhóm J.4).
-- =============================================================================

ALTER TABLE slot_definition ADD COLUMN label_vi text NOT NULL;

ALTER TABLE slot_definition ADD CONSTRAINT ck_slot_definition_label_not_blank
    CHECK (btrim(label_vi) <> '');
