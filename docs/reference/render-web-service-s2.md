# Render Web Service — S2 của Spike 1: deploy A, B, C

Kết quả chạy thật trên Render, PO gửi. Không có DSN hay host trong log.

## 1. Cấu hình Web Service — PO, 2026-10-04

Language Docker; branch `main`; Singapore, cùng region với DB chu kỳ 2; `./Dockerfile`, context `.`; Instance Free; Health Check Path `/healthz`; Auto-Deploy Off; Pre-Deploy Command trống. Biến môi trường **duy nhất** `BO19_DATABASE_URL` — host nội bộ, credential `bo19_app`, `sslmode=require` — nhập tay, không dùng "Add from .env". `BO19_ENVIRONMENT` không đặt: image S2 chưa có bước kiểm #16.

Image: `backend/`, `Dockerfile`, `.dockerignore` không đổi giữa commit `d873af4` và `0b4b102` — `git diff --stat` trống. File migration là LF ở cả index lẫn working tree (`git ls-files --eol`), nên sha256 trong image Render trùng image build ở local.

## 2. Deploy A — trước `migrate_main`

DB chu kỳ 2 chỉ qua bước 0: chưa có bảng, chưa có sổ (`docs/reference/render-postgres-s2-step0.md`).

Trạng thái cuối PO đọc trên dashboard: **`Deploy failed`**.

Mốc giờ PO gửi, nguyên văn: `Deployed-Oct 4, 2026at6:52:53 PM`.

Trang Events, PO gửi, nguyên văn:

```text
Deploy failed for d873af4: Merge branch 'spike/s2-ledger-step0' — S2: sổ schema_migration thành file DDL; migrate_main thật; công cụ bước 0 với credential bo19_admin ngoài repo; check_grants đọc sổ từ file
Exited with status 1 while running your code. Check your deploy logs for more information.
October 4, 2026 at 6:54 PM
First deploy started for d873af4: Merge branch 'spike/s2-ledger-step0' — S2: sổ schema_migration thành file DDL; migrate_main thật; công cụ bước 0 với credential bo19_admin ngoài repo; check_grants đọc sổ từ file
October 4, 2026 at 6:52 PM
```

Dashboard hiển thị giờ địa phương; log dưới đây là UTC. Hai bên khớp ở độ lệch 7 giờ: dòng `STARTUP_FAIL` đầu lúc 11:54:00 UTC, Events ghi `Deploy failed` lúc 6:54 PM.

Log, nguyên văn:

```text
==> Deploying...
==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-10-04 11:54:00,257 ERROR bo19.startup STARTUP_FAIL STARTUP_01_LEDGER_MISSING
2026-10-04 11:54:00,257 ERROR bo19.startup STARTUP_FAIL STARTUP_02_PROBE_ERROR:42P01
2026-10-04 11:54:00,257 ERROR bo19.startup STARTUP_ABORT 2 bước kiểm trượt — thoát mã 1
==> Exited with status 1
==> Common ways to troubleshoot your deploy: https://render.com/docs/troubleshooting-deploys
2026-10-04 11:54:05,544 ERROR bo19.startup STARTUP_FAIL STARTUP_01_LEDGER_MISSING
2026-10-04 11:54:05,545 ERROR bo19.startup STARTUP_FAIL STARTUP_02_PROBE_ERROR:42P01
2026-10-04 11:54:05,545 ERROR bo19.startup STARTUP_ABORT 2 bước kiểm trượt — thoát mã 1
```

**Đọc — chỉ những gì log cho thấy:**

- Mã trượt đúng như dự kiến khi chạy thử local trên DB chỉ qua bước 0: `#1` thiếu sổ, `#2` không thử được `UPDATE audit_event` vì bảng chưa có (`42P01`).
- Tiến trình thoát mã 1 → Render ghi `Exited with status 1` và trạng thái cuối là `Deploy failed`. Vế "Render có tính tiến trình thoát lúc khởi động là deploy hỏng không" của mục Bước kiểm khởi động, `06-structure.md`: **có**, với trạng thái cuối.
- Render **khởi động lại tiến trình một lần**, sau khoảng 5 giây, cùng kết quả. Sau đó log không còn dòng nào — PO gửi tới đây.
- **Mốc:** deploy bắt đầu 6:52 PM, `Deploy failed` 6:54 PM — cùng phút với lần thoát thứ hai. Render **không** chờ hết cửa sổ 15 phút của health check (`docs/reference/render-web-service-health-checks.md`) khi tiến trình thoát: thông báo của Events là `Exited with status 1 while running your code`. Độ phân giải của Events là phút.
- Chưa có bản deploy thành công trước đó, nên vế "giữ bản cũ" chưa thử được ở A — đó là việc của C.

## 3. Deploy B — chuẩn bị từ local, 2026-10-04

Image build ở local từ `main` `0b4b102` — `backend/` trùng commit Render build. Credential đọc từ `.env` trong subshell; biến không còn trong phiên shell sau đó. Host và tên database che bằng `<host>`, `bo19_<db>`; đếm `render.com|postgresql://|dpg-` trong mọi output: 0.

**B1 — `migrate_main` bằng `bo19_migrator`, hai lần.** Lệch có chủ ý so với ADR-022: chạy từ local, không từ CI (`.claude/commands/spike.md`, dòng S2).

```text
### migrate_main lần 1
2026-10-04 12:04:11,879 INFO bo19.migrate MIGRATE_START user=bo19_migrator
2026-10-04 12:04:12,043 INFO bo19.migrate MIGRATE_LEDGER_READY
2026-10-04 12:04:14,265 INFO bo19.migrate MIGRATE_APPLIED schema/0001_initial.sql sha256=937ca18412af
2026-10-04 12:04:14,489 INFO bo19.migrate MIGRATE_APPLIED schema/0002_phase9_security.sql sha256=36347173d53c
2026-10-04 12:04:14,706 INFO bo19.migrate MIGRATE_APPLIED schema/0003_job_failed_index.sql sha256=6420a9a19f61
2026-10-04 12:04:14,923 INFO bo19.migrate MIGRATE_APPLIED schema/0004_observability_trace_id.sql sha256=8fa2a7e8e32e
2026-10-04 12:04:15,127 INFO bo19.migrate MIGRATE_APPLIED schema/0005_rate_limit_window_column_grant.sql sha256=dc32cd43059a
2026-10-04 12:04:15,383 INFO bo19.migrate MIGRATE_APPLIED schema/0006_waiting_order_indexes.sql sha256=9b1a17d3ce29
2026-10-04 12:04:15,656 INFO bo19.migrate MIGRATE_APPLIED schema/0007_takeover_and_self_approval.sql sha256=c1ec0f600d5a
2026-10-04 12:04:15,871 INFO bo19.migrate MIGRATE_APPLIED schema/0008_temporary_permission_grant.sql sha256=85af6a27b557
2026-10-04 12:04:16,076 INFO bo19.migrate MIGRATE_APPLIED schema/0009_llm_usage_reasoning_tokens.sql sha256=0102d7ebab1c
2026-10-04 12:04:16,076 INFO bo19.migrate MIGRATE_STEP_1 applied=9 already=0
2026-10-04 12:04:18,937 INFO bo19.migrate MIGRATE_STEP_2 checkpointer setup() max(v)=9
2026-10-04 12:04:19,533 INFO bo19.migrate MIGRATE_STEP_3 checkpointer_grants
2026-10-04 12:04:19,862 INFO bo19.migrate MIGRATE_APPLIED data/0001_permission_catalog.sql sha256=9274be5e91e0
2026-10-04 12:04:19,862 INFO bo19.migrate MIGRATE_STEP_4 applied=1 already=0
2026-10-04 12:04:19,863 INFO bo19.migrate MIGRATE_OK
exit=0
### migrate_main lần 2
2026-10-04 12:04:23,242 INFO bo19.migrate MIGRATE_START user=bo19_migrator
2026-10-04 12:04:23,400 INFO bo19.migrate MIGRATE_LEDGER_READY
2026-10-04 12:04:23,566 INFO bo19.migrate MIGRATE_STEP_1 applied=0 already=9
2026-10-04 12:04:25,463 INFO bo19.migrate MIGRATE_STEP_2 checkpointer setup() max(v)=9
2026-10-04 12:04:26,055 INFO bo19.migrate MIGRATE_STEP_3 checkpointer_grants
2026-10-04 12:04:26,436 INFO bo19.migrate MIGRATE_STEP_4 applied=0 already=1
2026-10-04 12:04:26,436 INFO bo19.migrate MIGRATE_OK
exit=0
```

**B2 — `api_main` ở local, `bo19_app` qua URL ngoài**, trên chính DB Render; dừng bằng `docker stop`:

```text
2026-10-04 12:04:39,374 INFO bo19.startup STARTUP_OK bước kiểm #1, #2 đạt
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
INFO:     172.17.0.1:36090 - "GET /healthz HTTP/1.1" 200 OK
INFO:     172.17.0.1:36104 - "GET /healthz HTTP/1.1" 200 OK
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [1]
exit=0
```

`GET /healthz`: `{"status":"ok"} http=200`

**B3 — `check_grants.py --app-dsn env:BO19_RENDER_APP_DSN --migrator-role bo19_migrator`:**

```text
schema.sql sha256: 937ca18412aff409f2dd429a50b550524994fab73579b12bc23f68bc71e242fd
Kỳ vọng đọc từ: 04-data.md, backend/migrations/schema/*.sql, checkpointer_grants.sql, ledger/schema_migration.sql — nhóm: 5 11 6 14 8 1 · checkpoint: 3 + 1 · sổ: 1 · số chiều: 1024
pgvector: 0.8.1
Bảng trong public: 52
checkpoint_migrations max(v): 9
KIỂM THÊM ĐẠT | bo19_app không sở hữu bảng nào
KIỂM THÊM ĐẠT | mọi bảng của schema.sql do bo19_migrator sở hữu
KIỂM THÊM ĐẠT | giao dịch READ ONLY chặn UPDATE có quyền
KIỂM THÊM ĐẠT | số chiều embedding đọc từ catalog = 1024
Kiểm phủ định — từ chối đúng: 180
Kiểm khẳng định — cho phép đúng: 69
Lệch: 0
exit=0
```

Đọc: sổ đủ 10 dòng, sha256 khớp image; `setup()` `max(v)` = 9; chạy lại không áp gì; bước kiểm #1, #2 đạt trên DB Render; bộ kiểm **180 / 69 / Lệch 0** — trùng số local.
