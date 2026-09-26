-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0007
-- Đợt sửa 3 sau Phase 13. Diễn giải: docs/design/08-hitl.md mục Tiếp quản sau
-- halt_for_human, mục Bảng mã, mục Tách biệt trách nhiệm — D-006 và mục Thu hồi
-- văn bản; docs/design/13-audit.md AUD-02, AUD-07, AUD-23 (e)(f); A-044.
-- =============================================================================
--
-- Áp SAU 0006_waiting_order_indexes.sql, bằng bo19_migrator, trong một giao
-- dịch riêng (ADR-017). KHÔNG sửa 0001_initial.sql / contracts/schema.sql hay
-- migration nào trước — mỗi thay đổi một file.
--
-- Không GRANT mới: bo19_app đã có INSERT cả bảng trên decision_record,
-- document_halt và INSERT, UPDATE cả bảng trên approval_step, document (J.2, J.4
-- của schema.sql) — cột mới được phủ sẵn.
--
-- document_halt.takeover_step_id là NOT NULL: bảng phải rỗng khi áp. Dòng
-- document_halt đầu tiên chỉ có khi halt_for_human được dựng ở Sprint 2 (AC-2.3),
-- sau migration này. Bảng có dòng thì migration hỏng ngay — không tự điền.
-- =============================================================================

-- 1. Loại bước mới -------------------------------------------------------------
-- TAKEOVER: việc tiếp quản một lần dừng, mở cùng giao dịch với document_halt.
-- ISSUE_ORDER, REVOKE_INITIATE: sinh ra đã DECIDED trong giao dịch của thao tác —
--   chỗ mang cờ self_approved (D-006 điều kiện 2) cho thao tác không chờ ai.
-- REVOKE_CONFIRM: mở ở revoke_initiate, đóng ở revoke_confirm.
ALTER TABLE approval_step DROP CONSTRAINT ck_approval_step_kind;
ALTER TABLE approval_step ADD CONSTRAINT ck_approval_step_kind
    CHECK (step_kind IN ('CONTENT_REVIEW', 'SIGNATURE', 'SEAL', 'BOOKING_CONFIRM',
                         'TAKEOVER', 'ISSUE_ORDER', 'REVOKE_INITIATE', 'REVOKE_CONFIRM'));

-- Hàng đợi tiếp quản và dấu vân tay tín hiệu REVIEW_QUEUE: bước OPEN theo loại,
-- mở lâu nhất trước.
CREATE INDEX ix_approval_step_open_by_kind
    ON approval_step (step_kind, opened_at, id) WHERE status = 'OPEN';

-- 2. decision_record: lối ra của tiếp quản; bước bắt buộc với thao tác mang D-006
ALTER TABLE decision_record ADD COLUMN takeover_resolution text;
ALTER TABLE decision_record ADD CONSTRAINT ck_decision_record_takeover_resolution
    CHECK ((kind = 'TAKEOVER_RESOLVED') = (takeover_resolution IS NOT NULL));
ALTER TABLE decision_record ADD CONSTRAINT ck_decision_record_takeover_resolution_value
    CHECK (takeover_resolution IS NULL
           OR takeover_resolution IN ('RETRY', 'REJECT_REQUEST', 'RETURN_TO_ISSUE_QUEUE'));

ALTER TABLE decision_record DROP CONSTRAINT ck_decision_record_step_kinds;
ALTER TABLE decision_record ADD CONSTRAINT ck_decision_record_step_kinds
    CHECK (kind NOT IN ('APPROVED', 'CHANGES_REQUESTED', 'SIGNED', 'SEALED', 'BOOKING_CONFIRMED',
                        'ISSUE_ORDERED', 'TAKEOVER_RESOLVED', 'REVOKE_INITIATED', 'REVOKE_CONFIRMED')
           OR approval_step_id IS NOT NULL);

-- 3. document_halt: khoá idempotency mới (A-044) và bảng mã reason_code --------
-- Khoá cũ (document_id, at_node, revision_round) gộp nhầm lần dừng thứ hai ở cùng
-- node, cùng vòng sau một lần RETRY. Khoá mới: mỗi lần dừng đúng một bước TAKEOVER;
-- uq_approval_step_one_open chặn hai bước TAKEOVER cùng OPEN trên một document.
ALTER TABLE document_halt DROP CONSTRAINT uq_document_halt_once;
ALTER TABLE document_halt ADD COLUMN takeover_step_id uuid NOT NULL REFERENCES approval_step (id);
ALTER TABLE document_halt ADD CONSTRAINT uq_document_halt_takeover_step UNIQUE (takeover_step_id);
ALTER TABLE document_halt ADD CONSTRAINT ck_document_halt_reason_code_value
    CHECK (reason_code IN (
        'FREE_CONTENT_INVALID', 'PARSE_FAILED', 'PROVIDER_UNAVAILABLE', 'BUDGET_EXCEEDED',
        'BUDGET_UNAVAILABLE', 'SYSTEM_DEFECT', 'TEMPLATE_NOT_ACTIVE', 'RENDER_INPUT_INVALID',
        'RENDER_CONVERSION_FAILED', 'FONT_MISSING', 'REVIEW_NOT_READY', 'MAX_ROUNDS_EXCEEDED',
        'NO_ELIGIBLE_SIGNER', 'RENDER_CHECKSUM_MISMATCH', 'RENDER_OBJECT_MISSING',
        'CONTENT_HASH_MISMATCH', 'ISSUE_RETRIES_EXHAUSTED'));

-- 4. document: bản nháp bị bỏ khi tiếp quản từ chối (AUD-07) -------------------
-- Đường vào ARCHIVED thứ hai mở rộng từ CHANGES_REQUESTED sang DRAFT và APPROVED:
-- văn bản chưa từng ký, chưa từng có hiệu lực.
ALTER TABLE document DROP CONSTRAINT ck_document_archived_from;
ALTER TABLE document ADD CONSTRAINT ck_document_archived_from
    CHECK (archived_from_status IS NULL
           OR archived_from_status IN ('ISSUED', 'REVOKED', 'SUPERSEDED', 'REJECTED',
                                       'CHANGES_REQUESTED', 'DRAFT', 'APPROVED'));

ALTER TABLE document DROP CONSTRAINT ck_document_archive_reason_abandoned_draft;
ALTER TABLE document ADD CONSTRAINT ck_document_archive_reason_abandoned_draft
    CHECK (archived_from_status IS NULL
           OR archived_from_status NOT IN ('DRAFT', 'CHANGES_REQUESTED', 'APPROVED')
           OR archive_reason IS NOT NULL);

-- Bảng mã archive_reason, và mỗi mã chỉ đi với đường vào của nó.
ALTER TABLE document ADD CONSTRAINT ck_document_archive_reason_value
    CHECK (archive_reason IS NULL
           OR (archive_reason = 'REQUEST_CANCELLED'
               AND archived_from_status = 'CHANGES_REQUESTED')
           OR (archive_reason = 'TAKEOVER_REJECTED'
               AND archived_from_status IN ('DRAFT', 'CHANGES_REQUESTED', 'APPROVED'))
           OR (archive_reason = 'RETENTION_DUE'
               AND archived_from_status IN ('ISSUED', 'REVOKED', 'SUPERSEDED', 'REJECTED')));

-- Bản nháp bỏ ngay từ DRAFT có thể chưa từng xác định requires_seal.
ALTER TABLE document DROP CONSTRAINT ck_document_seal_determined;
ALTER TABLE document ADD CONSTRAINT ck_document_seal_determined
    CHECK (status IN ('DRAFT', 'CHANGES_REQUESTED')
           OR (status = 'ARCHIVED' AND archived_from_status = 'DRAFT')
           OR requires_seal IS NOT NULL);

-- 5. notification.event_code: bảng mã ------------------------------------------
ALTER TABLE notification ADD CONSTRAINT ck_notification_event_code_value
    CHECK (event_code IN ('DOCUMENT_ISSUED', 'DOCUMENT_HALTED', 'NEEDS_INFO_REMINDER',
                          'DOCUMENT_JOB_FAILED', 'RENDER_JOB_FAILED'));
