# Render — PostgreSQL free: phép thử S1 của Spike 1

- **Ngày chạy:** 2026-10-04. **Môi trường:** Postgres free trên Render, Singapore, chu kỳ 1 — PostgreSQL 18.6, pgvector 0.8.1 (`docs/reference/render-postgres-s0.md`).
- **Client:** `psql` 18.6 trong image `pgvector/pgvector:0.8.1-pg18`; `setup()` và `check_grants.py` chạy bằng venv của `tools/contract-checks/` — `langgraph-checkpoint-postgres` 3.1.2, `langgraph-checkpoint` 4.2.0, `psycopg` 3.3.5.
- **Credential:** ba DSN trong `.env` (gitignore) — `BO19_RENDER_ADMIN_DSN`, `BO19_RENDER_MIGRATOR_DSN`, `BO19_RENDER_APP_DSN`; đi vào container và tiến trình qua biến môi trường. Mật khẩu hai role sinh ngẫu nhiên trên máy người triển khai; server chỉ nhận **SCRAM-SHA-256 verifier**, qua `\getenv` của `psql`, không echo. Tên database, tên user mặc định đã che như S0.
- **Dùng cho:** A-047, A-045, A-060, A-040; cổng 2.10 của `docs/design/12-roadmap.md`; ADR-017, ADR-022.

## Phát hiện của spike — file grant của checkpointer rỗng

`backend/migrations/library/checkpointer_grants.sql` trong repo chỉ có hai dòng chú thích, không có câu `GRANT` nào — nội dung thật chỉ nằm trong mục Migration và checkpointer của `docs/design/06-structure.md`. `check_grants.py` không đọc file đó mà dùng **bản chép cứng** của hai câu `GRANT`, nên mọi lần kiểm local trước 2026-10-04 đều đạt. Lần đầu áp từ file thật — trên Render — bước 3 "đạt" mà không cấp gì; `check_grants.py --app-dsn` hỏng ở bảng checkpoint đầu tiên.

**Đã sửa:** file có đúng hai câu `GRANT` của thiết kế; `check_grants.py` đọc kỳ vọng từ file thật thay mọi bản chép cứng; luật mới của trình chạy migration — file không có câu SQL thực thi được thì dừng, không coi là đạt (ADR-017, cập nhật 2026-10-04). Áp lại bước 3 trên Render, rồi `check_grants.py --app-dsn` đạt.

## Đọc kết quả

| Câu hỏi | Kết quả |
|---|---|
| Chủ database, chủ schema `public` trên Render | **User mặc định, cả hai** — trực tiếp. Local, `public` thuộc `pg_database_owner` |
| Tạo role có `LOGIN` bằng user mặc định | **Được** — không superuser, không `CREATEROLE`, `CREATEDB` |
| User mặc định đọc `pg_authid` | **Không** — `permission denied`; thuộc tính role đọc qua `pg_roles` |
| Đăng nhập bằng mật khẩu, SSL | **Được**, `ssl = t` |
| Chủ schema `DROP` bảng của `bo19_migrator` | **Được** — xác nhận ranh giới tin cậy gồm user mặc định |
| Bước 1 — `0001` → `0009` | **Đạt**, 47 bảng, đều của `bo19_migrator`; `CREATE EXTENSION IF NOT EXISTS vector` của `0001` chỉ báo NOTICE |
| Bước 2 — `setup()` trên PostgreSQL 18.6 | **Đạt**, `max(v)` = 9, bốn bảng của thư viện |
| Bước 4 — data migration | **Đạt** — 25 permission, 3 role, 29 dòng `role_permission` |
| Sổ `schema_migration` | **Không có** — chưa có trình chạy `migrate_main` (ADR-017); không ghi gì, kể cả bản rỗng của file grant |
| `check_grants.py --app-dsn` — lần cuối | **176 từ chối đúng, 68 cho phép đúng, Lệch 0**, mã thoát 0 — trùng `--local-migrated` trên PostgreSQL 16.2 và 18.2 |
| Kết nối từ runner CI | **Đạt** — runner GitHub Actions `ubuntu-24.04`, bằng `bo19_app`, SSL bật; mục Kết nối từ runner CI |

## Script bước 0 — `s1_admin.sql`

```sql
\pset pager off
\set ON_ERROR_STOP 1
\set ECHO none
\echo '=== S1.A1 trước bước 0: chủ database, chủ schema public, quyền CREATE trên public'
SELECT current_user;
SELECT pg_get_userbyid(datdba) AS chu_database FROM pg_database WHERE datname = current_database();
SELECT nspname, pg_get_userbyid(nspowner) AS chu_schema FROM pg_namespace WHERE nspname = 'public';
SELECT r.rolname, has_schema_privilege(r.rolname, 'public', 'CREATE') AS create_tren_public
FROM pg_roles r WHERE r.rolname IN (current_user) ORDER BY 1;
SELECT extname, extversion FROM pg_extension ORDER BY 1;

\echo '=== S1.A2 bước 0: tạo bo19_migrator, bo19_app có LOGIN — chỉ gửi SCRAM-SHA-256 verifier (lệnh không echo)'
\getenv mig_v BO19_S1_MIGRATOR_VERIFIER
\getenv app_v BO19_S1_APP_VERIFIER
CREATE ROLE bo19_migrator LOGIN PASSWORD :'mig_v';
CREATE ROLE bo19_app LOGIN PASSWORD :'app_v';
\unset mig_v
\unset app_v
SELECT rolname, rolcanlogin, rolsuper, rolcreaterole, rolcreatedb,
       left(rolpassword, 14) AS dang_mat_khau
FROM pg_authid WHERE rolname IN ('bo19_migrator', 'bo19_app') ORDER BY 1;

\echo '=== S1.A3 bước 0: GRANT CREATE ON SCHEMA public TO bo19_migrator'
GRANT CREATE ON SCHEMA public TO bo19_migrator;
SELECT r.rolname, has_schema_privilege(r.rolname, 'public', 'USAGE') AS usage_public,
       has_schema_privilege(r.rolname, 'public', 'CREATE') AS create_public
FROM pg_roles r WHERE r.rolname IN ('bo19_migrator', 'bo19_app') ORDER BY 1;
```

Phần thuộc tính role của script này hỏng ở `pg_authid` — chạy lại bằng `pg_roles` ở mục kế. Hai `CREATE ROLE` đã thành công trước đó.

## Output nguyên văn

### Trước bước 0 và bước 0 — tạo role, bằng user mặc định

```text
Pager usage is off.
=== S1.A1 trước bước 0: chủ database, chủ schema public, quyền CREATE trên public
 current_user 
--------------
 <user_mac_dinh>
(1 row)

 chu_database 
--------------
 <user_mac_dinh>
(1 row)

 nspname | chu_schema 
---------+------------
 public  | <user_mac_dinh>
(1 row)

  rolname   | create_tren_public 
------------+--------------------
 <user_mac_dinh> | t
(1 row)

 extname | extversion 
---------+------------
 plpgsql | 1.0
 vector  | 0.8.1
(2 rows)

=== S1.A2 bước 0: tạo bo19_migrator, bo19_app có LOGIN — chỉ gửi SCRAM-SHA-256 verifier (lệnh không echo)
CREATE ROLE
CREATE ROLE
psql:/s1/s1_admin.sql:21: ERROR:  permission denied for table pg_authid
```

### Bước 0 — thuộc tính role, GRANT CREATE ON SCHEMA public

```text
Pager usage is off.
=== S1.A2b hai role vừa tạo (pg_roles — user mặc định không đọc được pg_authid)
SELECT rolname, rolcanlogin, rolsuper, rolcreaterole, rolcreatedb, rolinherit
FROM pg_roles WHERE rolname IN ('bo19_migrator', 'bo19_app') ORDER BY 1;
    rolname    | rolcanlogin | rolsuper | rolcreaterole | rolcreatedb | rolinherit 
---------------+-------------+----------+---------------+-------------+------------
 bo19_app      | t           | f        | f             | f           | t
 bo19_migrator | t           | f        | f             | f           | t
(2 rows)

=== S1.A3 bước 0: GRANT CREATE ON SCHEMA public TO bo19_migrator
GRANT CREATE ON SCHEMA public TO bo19_migrator;
GRANT
SELECT r.rolname, has_schema_privilege(r.rolname, 'public', 'USAGE') AS usage_public,
       has_schema_privilege(r.rolname, 'public', 'CREATE') AS create_public
FROM pg_roles r WHERE r.rolname IN ('bo19_migrator', 'bo19_app') ORDER BY 1;
    rolname    | usage_public | create_public 
---------------+--------------+---------------
 bo19_app      | t            | f
 bo19_migrator | t            | t
(2 rows)
```

### Đăng nhập bằng bo19_migrator; chủ schema DROP bảng của bo19_migrator

```text
=== S1.B1 bo19_migrator đăng nhập bằng mật khẩu (SCRAM), tạo bảng thử trong public
SELECT current_user, (SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()) AS ssl;
 current_user  | ssl 
---------------+-----
 bo19_migrator | t
(1 row)

CREATE TABLE public.s1_probe_drop (id int);
CREATE TABLE
SELECT tablename, tableowner FROM pg_tables WHERE tablename = 's1_probe_drop';
   tablename   |  tableowner   
---------------+---------------
 s1_probe_drop | bo19_migrator
(1 row)

=== S1.B2 user mặc định — chủ schema public — thử DROP bảng của bo19_migrator
DROP TABLE public.s1_probe_drop;
DROP TABLE
=== S1.B3 còn bảng thử không; nếu còn thì bo19_migrator dọn
SELECT count(*) AS con_lai FROM pg_tables WHERE tablename = 's1_probe_drop';
 con_lai 
---------
       0
(1 row)

DROP TABLE IF EXISTS public.s1_probe_drop;
NOTICE:  table "s1_probe_drop" does not exist, skipping
DROP TABLE
```

### Bước 1 — 0001 → 0009

```text
=== bước 1: 0001_initial.sql sha256 937ca18412af ... ĐẠT
psql:/m/schema/0001_initial.sql:27: NOTICE:  extension "vector" already exists, skipping
=== bước 1: 0002_phase9_security.sql sha256 36347173d53c ... ĐẠT
=== bước 1: 0003_job_failed_index.sql sha256 6420a9a19f61 ... ĐẠT
=== bước 1: 0004_observability_trace_id.sql sha256 8fa2a7e8e32e ... ĐẠT
=== bước 1: 0005_rate_limit_window_column_grant.sql sha256 dc32cd43059a ... ĐẠT
=== bước 1: 0006_waiting_order_indexes.sql sha256 9b1a17d3ce29 ... ĐẠT
=== bước 1: 0007_takeover_and_self_approval.sql sha256 c1ec0f600d5a ... ĐẠT
=== bước 1: 0008_temporary_permission_grant.sql sha256 85af6a27b557 ... ĐẠT
=== bước 1: 0009_llm_usage_reasoning_tokens.sql sha256 0102d7ebab1c ... ĐẠT
=== sau bước 1
 so_bang_public | cua_migrator 
----------------+--------------
             47 |           47
(1 row)
```

### Bước 2, 3 (lần đầu — file rỗng), 4

```text
=== bước 2: setup() của langgraph-checkpoint-postgres, autocommit, bằng bo19_migrator
langgraph-checkpoint-postgres 3.1.2 | langgraph-checkpoint 4.2.0 | psycopg 3.3.5
setup(): ĐẠT
checkpoint_migrations max(v): 9
bảng của thư viện: ['checkpoint_blobs', 'checkpoint_migrations', 'checkpoint_writes', 'checkpoints']
=== bước 3: checkpointer_grants.sql sha256 6d52843f57ef ... ĐẠT
=== bước 4: 0001_permission_catalog.sql sha256 9274be5e91e0 ... ĐẠT
 permission | role | role_permission 
------------+------+-----------------
         25 |    3 |              29
(1 row)
```

### check_grants.py --app-dsn — lần đầu, hỏng

```text
schema.sql sha256: 937ca18412aff409f2dd429a50b550524994fab73579b12bc23f68bc71e242fd
pgvector: 0.8.1
Bảng trong public: 51
Traceback (most recent call last):
  File "<stdin>", line 5, in <module>
  File "<frozen runpy>", line 291, in run_path
  File "<frozen runpy>", line 98, in _run_module_code
  File "<frozen runpy>", line 88, in _run_code
  File "check_grants.py", line 374, in <module>
    sys.exit(main())
             ^^^^^^
  File "check_grants.py", line 357, in main
    run_checks(app_dsn, rep, args.migrator_role, local, migrated)
  File "check_grants.py", line 275, in run_checks
    rep.expect(f"{t} UPDATE", probe(a, upd(t)), "ALLOW")
                                       ^^^^^^
  File "check_grants.py", line 224, in upd
    col = col or columns(t)[0]
                 ~~~~~~~~~~^^^
IndexError: list index out of range
```

### Đổi mật khẩu bo19_app

```text
ALTER ROLE bo19_app: xong
```

### Bước 3 — áp lại sau khi sửa file; sổ schema_migration

```text
=== bước 3 (áp lại): checkpointer_grants.sql sha256 18179add03af ... ĐẠT
           t           | s | i | u | d 
-----------------------+---+---+---+---
 checkpoints           | t | t | t | t
 checkpoint_blobs      | t | t | t | t
 checkpoint_writes     | t | t | t | t
 checkpoint_migrations | t | f | f | f
(4 rows)

 so_schema_migration 
---------------------
 
(1 row)
```

### check_grants.py --app-dsn env:BO19_RENDER_APP_DSN — lần cuối

```text
schema.sql sha256: 937ca18412aff409f2dd429a50b550524994fab73579b12bc23f68bc71e242fd
Kỳ vọng đọc từ: 04-data.md, backend/migrations/schema/*.sql, checkpointer_grants.sql — nhóm: 5 11 6 14 8 1 · checkpoint: 3 + 1 · số chiều: 1024
pgvector: 0.8.1
Bảng trong public: 51
checkpoint_migrations max(v): 9
KIỂM THÊM ĐẠT | bo19_app không sở hữu bảng nào
KIỂM THÊM ĐẠT | mọi bảng của schema.sql do bo19_migrator sở hữu
KIỂM THÊM ĐẠT | giao dịch READ ONLY chặn UPDATE có quyền
KIỂM THÊM ĐẠT | số chiều embedding đọc từ catalog = 1024
Kiểm phủ định — từ chối đúng: 176
Kiểm khẳng định — cho phép đúng: 68
Lệch: 0
```

## Kết nối từ runner CI — 2026-10-04

- **Workflow:** `.github/workflows/s1-ci-connect-probe.yml` ở commit `40d7e6e` — chỉ `workflow_dispatch`, `permissions: contents: read`, đòi `sslmode=require`, không echo DSN. **Đã xoá** sau lần chạy này.
- **Lần chạy:** run `37186094663`, `workflow_dispatch`, tạo lúc `2026-10-04T07:32:26Z`, kết luận `success`. PO thêm secret `BO19_S1_CI_PROBE_DSN` — DSN của `bo19_app` — trước khi chạy và **xoá ngay sau** (PO xác nhận; `gh secret list` không còn tên này).
- **Runner**, theo log: `Image: ubuntu-24.04`, `Version: 20260927.320.1`; `platform.platform()` = `Linux-6.17.0-1022-azure-x86_64-with-glibc2.39`.
- **Log:** biến môi trường của secret hiện `***`; không dòng nào chứa host hay chuỗi `postgresql://` — đã đếm trên log tải về bằng `gh run view --log`.

Dòng kết quả, nguyên văn:

```text
KẾT NỐI ĐẠT | user: bo19_app | server_version: 18.6 (Debian 18.6-1.pgdg12+2) | ssl: True | select 1: 1
```
