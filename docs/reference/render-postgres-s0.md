# Render — PostgreSQL free: phép thử S0 của Spike 1

- **Ngày chạy:** 2026-10-04. **Môi trường:** Postgres free trên Render, region Singapore, chu kỳ 1 (nhật ký vận hành ở `docs/design/11-ops.md`).
- **Kết nối:** từ máy người triển khai, **qua internet, ngoài Render**, bằng External Database URL đặt trong `.env` — đã gitignore, không in ra đâu. Client: `psql` 18.6 trong image `pgvector/pgvector:pg18`.
- **Che định danh:** tên database và tên user mặc định do Render đặt được thay bằng `<ten_db>`, `<user_mac_dinh>` — chúng là một phần của DSN. Host và mật khẩu không có trong output.
- **Dọn sau phép thử:** schema thử, bảng thử, hai role thử đã xoá; extension `vector` giữ lại cho S1 — mặc định PO duyệt.
- **Dùng cho:** A-040, A-037, A-046, A-083; cổng 2.1 của `docs/design/12-roadmap.md`.

## Script — `s0.sql`, chạy bằng `psql -X -v ON_ERROR_STOP=0 -e -f`

```sql
\pset pager off
\set ON_ERROR_STOP 0
\echo '=== S0.1 version'
SELECT version();
SHOW server_version;

\echo '=== S0.2 pg_available_extensions: vector, btree_gist (A-037, A-046)'
SELECT name, default_version, installed_version FROM pg_available_extensions
WHERE name IN ('vector', 'btree_gist') ORDER BY name;

\echo '=== S0.3 user mặc định (A-040 vế 3)'
SELECT current_user, rolsuper, rolcreaterole, rolcreatedb, rolinherit, rolbypassrls
FROM pg_roles WHERE rolname = current_user;
SELECT current_database(), pg_catalog.pg_get_userbyid(datdba) AS db_owner
FROM pg_database WHERE datname = current_database();
SELECT r.rolname AS member_of FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid
WHERE m.member = (SELECT oid FROM pg_roles WHERE rolname = current_user) ORDER BY 1;

\echo '=== S0.4 CREATE EXTENSION vector bằng user mặc định (A-040 vế 3, A-037)'
CREATE EXTENSION IF NOT EXISTS vector;
SELECT extname, extversion, pg_catalog.pg_get_userbyid(extowner) AS ext_owner FROM pg_extension WHERE extname = 'vector';

\echo '=== S0.5 tạo hai role NOLOGIN (A-040 vế 1, 2)'
CREATE ROLE bo19_migrator NOLOGIN;
CREATE ROLE bo19_app NOLOGIN;
SELECT rolname, rolsuper, rolcreaterole, rolcanlogin FROM pg_roles WHERE rolname IN ('bo19_migrator', 'bo19_app') ORDER BY 1;

\echo '=== S0.6 cho bo19_migrator quyền tạo bảng trong schema thử, rồi tạo bảng bằng bo19_migrator (A-040 vế 2)'
CREATE SCHEMA s0_probe;
GRANT USAGE, CREATE ON SCHEMA s0_probe TO bo19_migrator;
GRANT USAGE ON SCHEMA s0_probe TO bo19_app;
GRANT bo19_migrator TO current_user;
SET ROLE bo19_migrator;
SELECT current_user AS dang_chay_voi;
CREATE TABLE s0_probe.t (id integer PRIMARY KEY, v text);
GRANT SELECT, INSERT ON s0_probe.t TO bo19_app;
RESET ROLE;
SELECT schemaname, tablename, tableowner FROM pg_tables WHERE schemaname = 's0_probe';

\echo '=== S0.7 bo19_app: có sở hữu bảng không; thử ALTER, DROP, UPDATE — phải bị từ chối (A-040 vế 1)'
GRANT bo19_app TO current_user;
SELECT count(*) AS so_bang_bo19_app_so_huu FROM pg_tables WHERE tableowner = 'bo19_app';
SET ROLE bo19_app;
SELECT current_user AS dang_chay_voi;
INSERT INTO s0_probe.t VALUES (1, 'thu');
SELECT * FROM s0_probe.t;
UPDATE s0_probe.t SET v = 'x' WHERE false;
ALTER TABLE s0_probe.t ADD COLUMN w text;
DROP TABLE s0_probe.t;
RESET ROLE;

\echo '=== S0.8 REVOKE rồi has_table_privilege (A-040 vế 1)'
SELECT has_table_privilege('bo19_app', 's0_probe.t', 'SELECT') AS select_truoc,
       has_table_privilege('bo19_app', 's0_probe.t', 'UPDATE') AS update_truoc;
SET ROLE bo19_migrator;
REVOKE ALL ON s0_probe.t FROM bo19_app;
RESET ROLE;
SELECT has_table_privilege('bo19_app', 's0_probe.t', 'SELECT') AS select_sau,
       has_table_privilege('bo19_app', 's0_probe.t', 'INSERT') AS insert_sau;

\echo '=== S0.9 pg_ts_config (A-083)'
SELECT cfgname FROM pg_ts_config ORDER BY 1;

\echo '=== S0.10 dọn: xoá bảng thử, schema thử, hai role (mặc định PO duyệt); giữ extension vector'
DROP SCHEMA s0_probe CASCADE;
REVOKE bo19_app FROM current_user;
REVOKE bo19_migrator FROM current_user;
DROP ROLE bo19_app;
DROP ROLE bo19_migrator;
SELECT count(*) AS role_con_lai FROM pg_roles WHERE rolname IN ('bo19_migrator', 'bo19_app');
SELECT count(*) AS schema_con_lai FROM pg_namespace WHERE nspname = 's0_probe';
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
```

## Output nguyên văn

Lỗi của `psql` in sau dòng lệnh kế tiếp vì `stderr` và `stdout` đi hai luồng. Ba lỗi ở S0.7 thuộc dòng 47, 48, 49 của script — `UPDATE`, `ALTER TABLE`, `DROP TABLE` — đúng như số dòng `psql` báo.

```text
psql (PostgreSQL) 18.6 (Debian 18.6-1.pgdg12+2)
Pager usage is off.
=== S0.1 version
SELECT version();
                                                          version                                                           
----------------------------------------------------------------------------------------------------------------------------
 PostgreSQL 18.6 (Debian 18.6-1.pgdg12+2) on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit
(1 row)

SHOW server_version;
        server_version         
-------------------------------
 18.6 (Debian 18.6-1.pgdg12+2)
(1 row)

=== S0.2 pg_available_extensions: vector, btree_gist (A-037, A-046)
SELECT name, default_version, installed_version FROM pg_available_extensions
WHERE name IN ('vector', 'btree_gist') ORDER BY name;
    name    | default_version | installed_version 
------------+-----------------+-------------------
 btree_gist | 1.8             | 
 vector     | 0.8.1           | 
(2 rows)

=== S0.3 user mặc định (A-040 vế 3)
SELECT current_user, rolsuper, rolcreaterole, rolcreatedb, rolinherit, rolbypassrls
FROM pg_roles WHERE rolname = current_user;
 current_user | rolsuper | rolcreaterole | rolcreatedb | rolinherit | rolbypassrls 
--------------+----------+---------------+-------------+------------+--------------
 <user_mac_dinh>   | f        | t             | t           | t          | f
(1 row)

SELECT current_database(), pg_catalog.pg_get_userbyid(datdba) AS db_owner
FROM pg_database WHERE datname = current_database();
 current_database |  db_owner  
------------------+------------
 <ten_db>        | <user_mac_dinh>
(1 row)

SELECT r.rolname AS member_of FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid
WHERE m.member = (SELECT oid FROM pg_roles WHERE rolname = current_user) ORDER BY 1;
 member_of 
-----------
(0 rows)

=== S0.4 CREATE EXTENSION vector bằng user mặc định (A-040 vế 3, A-037)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION
SELECT extname, extversion, pg_catalog.pg_get_userbyid(extowner) AS ext_owner FROM pg_extension WHERE extname = 'vector';
 extname | extversion | ext_owner  
---------+------------+------------
 vector  | 0.8.1      | <user_mac_dinh>
(1 row)

=== S0.5 tạo hai role NOLOGIN (A-040 vế 1, 2)
CREATE ROLE bo19_migrator NOLOGIN;
CREATE ROLE
CREATE ROLE bo19_app NOLOGIN;
CREATE ROLE
SELECT rolname, rolsuper, rolcreaterole, rolcanlogin FROM pg_roles WHERE rolname IN ('bo19_migrator', 'bo19_app') ORDER BY 1;
    rolname    | rolsuper | rolcreaterole | rolcanlogin 
---------------+----------+---------------+-------------
 bo19_app      | f        | f             | f
 bo19_migrator | f        | f             | f
(2 rows)

=== S0.6 cho bo19_migrator quyền tạo bảng trong schema thử, rồi tạo bảng bằng bo19_migrator (A-040 vế 2)
CREATE SCHEMA s0_probe;
CREATE SCHEMA
GRANT USAGE, CREATE ON SCHEMA s0_probe TO bo19_migrator;
GRANT
GRANT USAGE ON SCHEMA s0_probe TO bo19_app;
GRANT
GRANT bo19_migrator TO current_user;
GRANT ROLE
SET ROLE bo19_migrator;
SET
SELECT current_user AS dang_chay_voi;
 dang_chay_voi 
---------------
 bo19_migrator
(1 row)

CREATE TABLE s0_probe.t (id integer PRIMARY KEY, v text);
CREATE TABLE
GRANT SELECT, INSERT ON s0_probe.t TO bo19_app;
GRANT
RESET ROLE;
RESET
SELECT schemaname, tablename, tableowner FROM pg_tables WHERE schemaname = 's0_probe';
 schemaname | tablename |  tableowner   
------------+-----------+---------------
 s0_probe   | t         | bo19_migrator
(1 row)

=== S0.7 bo19_app: có sở hữu bảng không; thử ALTER, DROP, UPDATE — phải bị từ chối (A-040 vế 1)
GRANT bo19_app TO current_user;
GRANT ROLE
SELECT count(*) AS so_bang_bo19_app_so_huu FROM pg_tables WHERE tableowner = 'bo19_app';
 so_bang_bo19_app_so_huu 
-------------------------
                       0
(1 row)

SET ROLE bo19_app;
SET
SELECT current_user AS dang_chay_voi;
 dang_chay_voi 
---------------
 bo19_app
(1 row)

INSERT INTO s0_probe.t VALUES (1, 'thu');
INSERT 0 1
SELECT * FROM s0_probe.t;
 id |  v  
----+-----
  1 | thu
(1 row)

UPDATE s0_probe.t SET v = 'x' WHERE false;
ALTER TABLE s0_probe.t ADD COLUMN w text;
psql:/s0/s0.sql:47: ERROR:  permission denied for table t
psql:/s0/s0.sql:48: ERROR:  must be owner of table t
DROP TABLE s0_probe.t;
psql:/s0/s0.sql:49: ERROR:  must be owner of table t
RESET ROLE;
RESET
=== S0.8 REVOKE rồi has_table_privilege (A-040 vế 1)
SELECT has_table_privilege('bo19_app', 's0_probe.t', 'SELECT') AS select_truoc,
       has_table_privilege('bo19_app', 's0_probe.t', 'UPDATE') AS update_truoc;
 select_truoc | update_truoc 
--------------+--------------
 t            | f
(1 row)

SET ROLE bo19_migrator;
SET
REVOKE ALL ON s0_probe.t FROM bo19_app;
REVOKE
RESET ROLE;
RESET
SELECT has_table_privilege('bo19_app', 's0_probe.t', 'SELECT') AS select_sau,
       has_table_privilege('bo19_app', 's0_probe.t', 'INSERT') AS insert_sau;
 select_sau | insert_sau 
------------+------------
 f          | f
(1 row)

=== S0.9 pg_ts_config (A-083)
SELECT cfgname FROM pg_ts_config ORDER BY 1;
  cfgname   
------------
 arabic
 armenian
 basque
 catalan
 danish
 dutch
 english
 estonian
 finnish
 french
 german
 greek
 hindi
 hungarian
 indonesian
 irish
 italian
 lithuanian
 nepali
 norwegian
 portuguese
 romanian
 russian
 serbian
 simple
 spanish
 swedish
 tamil
 turkish
 yiddish
(30 rows)

=== S0.10 dọn: xoá bảng thử, schema thử, hai role (mặc định PO duyệt); giữ extension vector
DROP SCHEMA s0_probe CASCADE;
psql:/s0/s0.sql:65: NOTICE:  drop cascades to table s0_probe.t
DROP SCHEMA
REVOKE bo19_app FROM current_user;
REVOKE ROLE
REVOKE bo19_migrator FROM current_user;
REVOKE ROLE
DROP ROLE bo19_app;
DROP ROLE
DROP ROLE bo19_migrator;
DROP ROLE
SELECT count(*) AS role_con_lai FROM pg_roles WHERE rolname IN ('bo19_migrator', 'bo19_app');
 role_con_lai 
--------------
            0
(1 row)

SELECT count(*) AS schema_con_lai FROM pg_namespace WHERE nspname = 's0_probe';
 schema_con_lai 
----------------
              0
(1 row)

SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
 extname | extversion 
---------+------------
 vector  | 0.8.1
(1 row)
```

## Đọc kết quả

| Câu hỏi | Kết quả | Mục |
|---|---|---|
| Bản PostgreSQL | **18.6** | S0.1 |
| Kết nối từ ngoài Render | **Được** — F11 của `docs/design/proposals/build-phase-free-tier-impact.md` | Cả phép thử |
| `vector` có sẵn, bản nào | **Có, 0.8.1** | S0.2, S0.4 |
| `btree_gist` có sẵn | **Có, 1.8** — chưa cài | S0.2 |
| User mặc định là superuser không | **Không** — `rolsuper = f`; có `CREATEROLE`, `CREATEDB`; sở hữu database | S0.3 |
| User mặc định tạo được `vector` không | **Được** — `CREATE EXTENSION` thành công, chủ extension là user mặc định | S0.4 |
| Tạo được role riêng không | **Được** — `CREATE ROLE` hai role, không superuser, không `CREATEROLE` | S0.5 |
| Role migrate sở hữu bảng do nó tạo | **Có** — `tableowner = bo19_migrator` | S0.6 |
| Role runtime không sở hữu bảng, bị chặn đúng | **Có** — sở hữu 0 bảng; `INSERT`, `SELECT` được cấp thì chạy; `UPDATE` không được cấp: `permission denied`; `ALTER`, `DROP`: `must be owner` | S0.7 |
| `REVOKE` có hiệu lực | **Có** — `has_table_privilege` từ `t` thành `f` | S0.8 |
| Cấu hình text search | 30 cấu hình có sẵn, **có `simple`**, **không có cấu hình tiếng Việt** | S0.9 |

**Chưa thử ở S0 — để S1:** role có `LOGIN` và mật khẩu, đăng nhập thật bằng từng role; quyền `CREATE` trên schema `public` cho `bo19_migrator` — S0 dùng một schema thử riêng; extension xếp hạng BM25 cho A-083 — không nằm trong lệnh S0.
