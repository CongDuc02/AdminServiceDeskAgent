-- Chạy bằng bo19_migrator, SAU setup() của thư viện checkpointer.
-- Bảng do thư viện tạo (docs/reference/langgraph-checkpoint-postgres.md).
-- Nội dung đúng như mục Migration và checkpointer của docs/design/06-structure.md.
-- Chạy lại được — GRANT idempotent; nằm ngoài sổ schema_migration (ADR-017, bước 3).
GRANT SELECT, INSERT, UPDATE, DELETE ON checkpoints, checkpoint_blobs, checkpoint_writes TO bo19_app;
GRANT SELECT ON checkpoint_migrations TO bo19_app;
