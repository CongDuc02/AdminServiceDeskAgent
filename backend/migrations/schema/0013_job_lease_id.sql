-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0013
-- B8b, việc đầu tiên (PO duyệt 2026-10-13): token hàng rào chủ lease của job là một uuid ngẫu nhiên
-- do DB sinh mỗi lần giành, thay cho `locked_at` (mong manh: đồng hồ lùi khi NTP chỉnh; hai lần
-- giành cùng một mốc thời gian). Diễn giải: docs/design/04-data.md mục `job`; ADR-004 mục Bổ sung.
-- =============================================================================
--
-- Áp SAU 0012_chat_message_reply_link.sql, bằng bo19_migrator, trong một giao dịch riêng (ADR-017).
-- KHÔNG sửa 0001_initial.sql / contracts/schema.sql hay migration nào trước.
--
-- Không GRANT mới: bo19_app đã có SELECT, INSERT, UPDATE, DELETE trên cả bảng `job`.
--
-- `ck_job_running_has_lease` (0001) giữ nguyên: RUNNING <=> locked_at và lease_expires_at cùng có mặt.
-- Ràng buộc mới nói thêm: `lease_id` có mặt khi và chỉ khi RUNNING.
-- =============================================================================

ALTER TABLE job ADD COLUMN lease_id uuid;

-- Hàng RUNNING sẵn có (nếu có) được một token để thoả ràng buộc ngay; worker cũ không còn giữ nó nên
-- lease của chúng chỉ được thu hồi khi hết hạn.
UPDATE job SET lease_id = gen_random_uuid() WHERE status = 'RUNNING';

ALTER TABLE job ADD CONSTRAINT ck_job_lease_id_iff_running
    CHECK ((status = 'RUNNING') = (lease_id IS NOT NULL));
