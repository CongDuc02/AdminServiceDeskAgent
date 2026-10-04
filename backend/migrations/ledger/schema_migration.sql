-- =============================================================================
-- BO-19 — sổ migration schema_migration (ADR-017). PO duyệt tên cột 2026-10-04.
-- migrate_main tạo bảng này TRƯỚC bước 1, bằng bo19_migrator, mỗi lần chạy — idempotent.
-- Không phải migration đánh số: không tự ghi vào chính nó.
--
-- Sổ ghi file của bước 1 (kind = schema) và bước 4 (kind = data). Bước 3 —
-- library/checkpointer_grants.sql — nằm ngoài sổ, chạy lại được (ADR-017).
-- filename tương đối với backend/migrations/, ví dụ schema/0001_initial.sql.
-- bo19_app chỉ SELECT — bước kiểm khởi động #1 đọc sổ (06-structure.md).
-- =============================================================================

CREATE TABLE IF NOT EXISTS schema_migration (
    filename    text        PRIMARY KEY,
    kind        text        NOT NULL,
    sha256      text        NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_schema_migration_kind CHECK (kind IN ('schema', 'data')),
    CONSTRAINT ck_schema_migration_sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_schema_migration_filename CHECK (filename ~ '^(schema|data)/[0-9]{4}_[a-z0-9_]+\.sql$'),
    CONSTRAINT ck_schema_migration_kind_matches_dir CHECK (split_part(filename, '/', 1) = kind)
);

REVOKE ALL ON schema_migration FROM PUBLIC;
GRANT SELECT ON schema_migration TO bo19_app;
