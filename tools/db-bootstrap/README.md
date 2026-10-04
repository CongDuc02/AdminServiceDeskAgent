# `tools/db-bootstrap/` — bước 0 của migration

Bước 0 ở mục Migration và checkpointer của `docs/design/06-structure.md`: `CREATE EXTENSION vector`, tạo `bo19_migrator` và `bo19_app` có `LOGIN`, `GRANT CREATE ON SCHEMA public TO bo19_migrator`. Trên Render, bước này chạy bằng user mặc định `bo19_admin`, **do PO**, không ở CI (ADR-022). Dùng ở bước 5 của mục Runbook — dựng lại PostgreSQL free của giai đoạn build, `docs/design/11-ops.md`.

Không phải mã ứng dụng: nằm ngoài `backend/`, không vào image.

| File | Việc |
|---|---|
| `role_secrets.py` | `generate`: đọc `BO19_RENDER_EXTERNAL_HOST`, `BO19_RENDER_DB_NAME` từ `.env` của repo — không đọc credential `bo19_admin`, và dừng nếu `.env` của repo còn `BO19_RENDER_ADMIN_DSN`; sinh mật khẩu mới cho hai role, ghi `BO19_RENDER_MIGRATOR_DSN`, `BO19_RENDER_APP_DSN` vào `.env` (thay tại chỗ), ghi SCRAM-SHA-256 verifier ra file tạm **ngoài repo**. `internal-dsn`: ghi `BO19_RENDER_APP_INTERNAL_DSN` — credential `bo19_app` trên host nội bộ, giá trị cho `BO19_DATABASE_URL` của Web Service. Không in giá trị bí mật nào |
| `step0.sql` | Bước 0. Dừng nếu máy chủ không phải PostgreSQL 18. Verifier đọc bằng `\getenv`, không echo; thiếu hay sai dạng thì dừng trước `CREATE ROLE` |
| `step0.sh` | Chạy `step0.sql` bằng `psql` trong image ghim của ADR-033, `--single-transaction`, `ON_ERROR_STOP`. DSN của `bo19_admin` đọc từ `~/.bo19/admin.env` — file ngoài repo; nằm trong repo thì dừng — vào biến môi trường. Đạt thì xoá file verifier |

**Máy chủ chỉ nhận verifier** — mật khẩu thô của `bo19_migrator`, `bo19_app` chỉ nằm trong DSN ở `.env` của repo, trên máy này (PO, 2026-10-04). Mật khẩu 40 ký tự chữ và số; verifier `SCRAM-SHA-256$4096:<salt>$<StoredKey>:<ServerKey>`, salt 16 byte.

## Trình tự — DB free mới

Chạy từ gốc repo, trong Git Bash. Cần Docker Desktop đang chạy.

1. **PO** tạo DB free mới trên Render — **PostgreSQL Version 18** (ADR-033). Rồi:
   - **External Database URL** vào file **ngoài repo** `~/.bo19/admin.env`, dòng `BO19_RENDER_ADMIN_DSN=`. Người triển khai không đọc, không ghi file này (PO, 2026-10-04).
   - `.env` của repo: **xoá** dòng `BO19_RENDER_ADMIN_DSN` nếu còn; thêm ba giá trị không bí mật — `BO19_RENDER_EXTERNAL_HOST=` (host:cổng của URL ngoài), `BO19_RENDER_DB_NAME=`, `BO19_RENDER_INTERNAL_HOST=` (host của URL nội bộ ở trang Info của DB — `docs/reference/render-web-service-health-checks.md`). Không user, không mật khẩu.
2. **Người triển khai** sinh mật khẩu và verifier — `.env` chỉ được ghi, không in:

   ```bash
   python tools/db-bootstrap/role_secrets.py generate
   python tools/db-bootstrap/role_secrets.py internal-dsn
   ```

3. **PO** chạy bước 0:

   ```bash
   bash tools/db-bootstrap/step0.sh
   ```

   Đạt khi bảng cuối có hai dòng `bo19_app`, `bo19_migrator`: `rolcanlogin = t`, `rolsuper`, `rolcreaterole`, `rolcreatedb` đều `f`; chỉ `bo19_migrator` có `create_public = t`. Dòng cuối: `bước 0 đạt — đã xoá file verifier`.

   Hỏng giữa chừng thì không còn gì — một giao dịch. Chạy lại cả bước 2 lẫn bước 3: verifier dùng một lần.
4. `migrate_main` bằng `BO19_MIGRATOR_DATABASE_URL`, rồi `check_grants.py --app-dsn` — bước 7, 8 của runbook.

Thử trên container local, không TLS: `role_secrets.py generate --env-file <file thử> --verifier-file <file tạm> --sslmode disable`, rồi `ADMIN_ENV_FILE=<file admin thử, ngoài repo> VERIFIER_FILE=<file tạm> bash tools/db-bootstrap/step0.sh`. DSN của container phải dùng `host.docker.internal` — `psql` chạy trong container khác.
