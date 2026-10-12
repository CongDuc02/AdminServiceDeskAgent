-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0012
-- B6b, câu Q6 (PO duyệt 2026-10-12): liên kết tin agent → tin nhân viên mà nó trả lời,
-- để DB giữ "đúng một tin agent cho mỗi tin nhân viên" khi bộ giám sát lượt và thread
-- của lượt cùng ghi lúc hạn chót. Diễn giải: docs/design/04-data.md, bảng chat_message.
-- =============================================================================
--
-- Áp SAU 0011_slot_definition_label.sql, bằng bo19_migrator, trong một giao dịch riêng
-- (ADR-017). KHÔNG sửa 0001_initial.sql / contracts/schema.sql hay migration nào trước.
--
-- Không GRANT mới: bo19_app đã có SELECT, INSERT trên cả bảng; cột mới chỉ ghi lúc INSERT
-- (GRANT UPDATE theo cột của chat_message không thêm cột này — không ai sửa liên kết).
--
-- ON DELETE của khoá ngoại ghép: NO ACTION (mặc định, ghi rõ ở 04-data.md). Luật xoá hội
-- thoại xoá NỘI DUNG (UPDATE body/retrieval_query/content_erased_at), không xoá dòng; không
-- vai trò runtime nào có DELETE. SET NULL sẽ lặng lẽ gỡ chốt chặn "một tin trả lời"; CASCADE
-- sẽ lặng lẽ xoá tin agent. NO ACTION kiểm ở cuối câu lệnh nên xoá cả phiên bằng MỘT câu
-- lệnh vẫn chạy.
--
-- "Tin được trả lời là của EMPLOYEE" KHÔNG ở đây — không trigger; do chat_message_append kiểm.
-- =============================================================================

ALTER TABLE chat_message ADD COLUMN in_reply_to_message_id uuid;

-- Đích của khoá ngoại ghép: DB giữ điều kiện "cùng phiên".
ALTER TABLE chat_message ADD CONSTRAINT uq_chat_message_session_id UNIQUE (chat_session_id, id);

-- MATCH SIMPLE (mặc định): in_reply_to_message_id NULL thì không kiểm — tin agent không trả lời tin nào hợp lệ.
ALTER TABLE chat_message ADD CONSTRAINT fk_chat_message_in_reply_to
    FOREIGN KEY (chat_session_id, in_reply_to_message_id) REFERENCES chat_message (chat_session_id, id);

ALTER TABLE chat_message ADD CONSTRAINT ck_chat_message_reply_only_agent
    CHECK (author = 'AGENT' OR in_reply_to_message_id IS NULL);

ALTER TABLE chat_message ADD CONSTRAINT ck_chat_message_reply_not_self
    CHECK (in_reply_to_message_id IS NULL OR in_reply_to_message_id <> id);

-- Một tin nhân viên có tối đa MỘT tin agent trả lời.
CREATE UNIQUE INDEX uq_chat_message_one_agent_reply ON chat_message (in_reply_to_message_id) WHERE author = 'AGENT';
