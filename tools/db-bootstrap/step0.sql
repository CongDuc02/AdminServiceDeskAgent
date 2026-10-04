-- =============================================================================
-- BO-19 — bước 0 của ADR-017: chạy bằng user mặc định của Render (bo19_admin), do PO.
-- Mục Migration và checkpointer của 06-structure.md; runbook dựng lại DB ở 11-ops.md.
--
-- Chạy qua step0.sh: psql --single-transaction, ON_ERROR_STOP — hỏng một câu thì không còn gì.
-- Verifier đọc từ biến môi trường bằng \getenv; lệnh không echo. Máy chủ chỉ nhận verifier.
-- btree_gist KHÔNG ở đây — chỉ thêm khi A-046 chốt là cần.
-- =============================================================================
\pset pager off
\set ECHO none

\echo '=== trước bước 0'
SELECT current_user, current_database(), split_part(version(), ' ', 2) AS postgresql;
SELECT pg_get_userbyid(nspowner) AS chu_schema_public FROM pg_namespace WHERE nspname = 'public';
SELECT count(*) AS role_bo19_da_co FROM pg_roles WHERE rolname IN ('bo19_migrator', 'bo19_app');
-- PostgreSQL 18 — khớp image pg18 ghim ở ADR-033 mà bộ kiểm local dùng (runbook dựng lại DB, 11-ops.md).
SELECT current_setting('server_version_num')::int / 10000 = 18 AS la_pg18 \gset
\if :la_pg18
\else
  \echo 'DỪNG: máy chủ không phải PostgreSQL 18 — tạo lại DB với PostgreSQL Version 18'
  \quit 3
\endif

\echo '=== extension vector'
CREATE EXTENSION IF NOT EXISTS vector;

\echo '=== tạo bo19_migrator, bo19_app — LOGIN, mật khẩu là SCRAM-SHA-256 verifier'
\getenv mig_v BO19_STEP0_MIGRATOR_VERIFIER
\getenv app_v BO19_STEP0_APP_VERIFIER
SELECT :'mig_v' LIKE 'SCRAM-SHA-256$4096:%' AND :'app_v' LIKE 'SCRAM-SHA-256$4096:%' AS verifier_dung_dang \gset
\if :verifier_dung_dang
\else
  \echo 'DỪNG: thiếu verifier hoặc sai dạng — chạy role_secrets.py generate trước'
  \quit 3
\endif
CREATE ROLE bo19_migrator LOGIN PASSWORD :'mig_v';
CREATE ROLE bo19_app LOGIN PASSWORD :'app_v';
\unset mig_v
\unset app_v

\echo '=== GRANT CREATE ON SCHEMA public TO bo19_migrator'
GRANT CREATE ON SCHEMA public TO bo19_migrator;

\echo '=== sau bước 0'
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
SELECT r.rolname, r.rolcanlogin, r.rolsuper, r.rolcreaterole, r.rolcreatedb,
       has_schema_privilege(r.rolname, 'public', 'USAGE')  AS usage_public,
       has_schema_privilege(r.rolname, 'public', 'CREATE') AS create_public
  FROM pg_roles r WHERE r.rolname IN ('bo19_migrator', 'bo19_app') ORDER BY 1;
