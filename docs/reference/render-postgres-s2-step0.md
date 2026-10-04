# Render Postgres — bước 0 của chu kỳ 2 (S2, 2026-10-04)

Kết quả chạy thật trên Render. Host được che là `<host>`, tên database là `bo19_<db>`.

## 1. Bối cảnh

- DB free mới, **chu kỳ 2** của nhật ký ở mục Runbook — dựng lại PostgreSQL free của giai đoạn build, `docs/design/11-ops.md`; lần thử đầu tiên của runbook đó cho cổng 2.11. PostgreSQL Version 18, Singapore. Tạo 2026-10-04, hết hạn 2026-11-03 — PO gửi.
- Bước 0 bằng `tools/db-bootstrap/`: người triển khai chạy `role_secrets.py generate`, `internal-dsn`; PO chạy `step0.sh` bằng credential `bo19_admin` ở `~/.bo19/admin.env`.

## 2. Lần chạy `step0.sh` đầu — hỏng trước khi kết nối

Output PO gửi, nguyên văn:

```text
docker: --env-file: open /tmp/bo19-step0/verifiers.env: The system cannot find the path specified.
```

Git Bash của PO đặt `TMP=/tmp`; docker là chương trình Windows, không mở được đường dẫn kiểu MSYS khi `MSYS_NO_PATHCONV=1`. Chưa kết nối DB. Sửa: `cygpath -w` trước `--env-file`.

## 3. Lần chạy `step0.sh` thứ hai — PO báo đạt

PO báo "kết quả đạt", không gửi output. Bằng chứng gián tiếp: file verifier đã bị xoá — `step0.sh` chỉ xoá nó sau khi `psql` thoát mã 0. Bằng chứng trực tiếp ở mục 5.

## 4. Phát hiện — tên database trong `.env` sai

Kiểm lại bằng `bo19_app` lần đầu hỏng:

```text
psql: error: connection to server at "<host>" (<ip>), port 5432 failed: FATAL:  database "bo19" does not exist
```

`BO19_RENDER_DB_NAME` trong `.env` của repo là `bo19`; Render đặt tên database khác — có hậu tố. Bước 0 không bị ảnh hưởng: nó dùng DSN của `bo19_admin`. Ba DSN do `role_secrets.py` sinh thì trỏ sai database. Xử lý:

- Tra tên bằng `bo19_app` nối vào database `postgres`: `select datname from pg_database where not datistemplate and datname <> 'postgres'` — đúng **một** dòng, bắt đầu bằng `bo19`. Ghi thẳng vào `.env`, không in.
- `role_secrets.py retarget` — lệnh mới: ghi lại host và database của hai DSN, **giữ credential**; rồi `internal-dsn`. Không phải chạy lại bước 0. Cả ba DSN trỏ đúng database mới: 3/3.

## 5. Xác nhận bước 0 — bằng `bo19_app`, chỉ đọc

Script:

```sql
\pset pager off
SELECT current_user, split_part(version(), ' ', 2) AS postgresql, current_setting('ssl') AS ssl_server,
       (SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()) AS ssl_ket_noi;
SELECT extname, extversion FROM pg_extension ORDER BY 1;
SELECT r.rolname, r.rolcanlogin, r.rolsuper, r.rolcreaterole, r.rolcreatedb,
       has_schema_privilege(r.rolname, 'public', 'USAGE')  AS usage_public,
       has_schema_privilege(r.rolname, 'public', 'CREATE') AS create_public
  FROM pg_roles r WHERE r.rolname IN ('bo19_migrator', 'bo19_app') ORDER BY 1;
SELECT count(*) AS bang_trong_public FROM pg_tables WHERE schemaname = 'public';
SELECT to_regclass('public.schema_migration') IS NOT NULL AS co_so;
```

Output, nguyên văn:

```text
 current_user | postgresql | ssl_server | ssl_ket_noi 
--------------+------------+------------+-------------
 bo19_app     | 18.6       | on         | t
(1 row)

 extname | extversion 
---------+------------
 plpgsql | 1.0
 vector  | 0.8.1
(2 rows)

    rolname    | rolcanlogin | rolsuper | rolcreaterole | rolcreatedb | usage_public | create_public 
---------------+-------------+----------+---------------+-------------+--------------+---------------
 bo19_app      | t           | f        | f             | f           | t            | f
 bo19_migrator | t           | f        | f             | f           | t            | t
(2 rows)

 bang_trong_public 
-------------------
                 0
(1 row)

 co_so 
-------
 f
(1 row)

exit=0
```

Đọc: đăng nhập `bo19_app` bằng mật khẩu ở `.env` thành công — verifier trên máy chủ khớp. PostgreSQL **18.6**, SSL. `vector` **0.8.1** đã cài. Hai role đúng: `LOGIN`, không superuser, không `CREATEROLE`, `CREATEDB`; chỉ `bo19_migrator` có `CREATE` trên `public`. Chưa có bảng, chưa có sổ — đúng trạng thái trước deploy A.
