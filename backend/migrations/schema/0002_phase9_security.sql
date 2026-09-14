-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0002
-- Phase 9 — Security & Guardrails. Diễn giải đầy đủ: docs/design/09-security.md
-- =============================================================================
--
-- Áp SAU 0001_initial.sql, bằng bo19_migrator, trong một giao dịch riêng (mục
-- Trình tự migration của ADR-017). KHÔNG sửa 0001_initial.sql / contracts/schema.sql
-- — file đó đã đóng ở Phase 6 ("0001_initial.sql = contracts/schema.sql ở trạng
-- thái đóng Phase 6; về sau mỗi thay đổi một file", mục 3 của 06-structure.md).
--
-- Hai bảng bổ sung, cả hai tầng kỹ thuật (GLOSSARY.md mục 12):
--   * employee_credential — credential đăng nhập, tách khỏi employee (A-048).
--   * rate_limit_window   — đếm rate limit đăng nhập theo cửa sổ cố định
--                           (mục Rate limit của 09-security.md).
-- =============================================================================

-- Tách khỏi employee để import CSV (D-002) không bao giờ chạm tới credential.
-- Ghi bằng thao tác vận hành seed, chạy bằng bo19_migrator; bo19_app chỉ đọc (H1).
CREATE TABLE employee_credential (
    employee_id     uuid        PRIMARY KEY REFERENCES employee (id),
    password_hash   text        NOT NULL,
    hash_algorithm  text        NOT NULL DEFAULT 'argon2id',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_employee_credential_hash_not_blank CHECK (btrim(password_hash) <> '')
);

-- Sổ đếm rate limit theo cửa sổ cố định. Sổ sách kỹ thuật, không phải nghiệp vụ
-- (A-055 thêm ở Phase 9): không audit_event, không actor.
CREATE TABLE rate_limit_window (
    scope          text        NOT NULL,   -- vi du 'login_ip:1.2.3.4'
    window_start   timestamptz NOT NULL,
    attempt_count  integer     NOT NULL DEFAULT 1,
    CONSTRAINT pk_rate_limit_window PRIMARY KEY (scope, window_start),
    CONSTRAINT ck_rate_limit_window_count_positive CHECK (attempt_count > 0)
);

CREATE INDEX ix_rate_limit_window_start ON rate_limit_window (window_start);

-- Quyền của bo19_app — tiếp nối mục J của 0001_initial.sql. Không chỉnh GRANT
-- đã cấp ở 0001; chỉ cấp quyền cho hai bảng mới của chính migration này.
GRANT SELECT ON employee_credential TO bo19_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limit_window TO bo19_app;
