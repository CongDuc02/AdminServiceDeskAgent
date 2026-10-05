# `tools/seed-dev/` — seed dữ liệu **giả** cho DB local

Nạp tài khoản giả có nhãn để đăng nhập thử trên Postgres **local**. Không phải mã ứng dụng, không vào image, không phải data migration.
Quyết định: PO, 2026-10-05 (kế hoạch B3) — seed chỉ trên Postgres local; Render seed ở mốc riêng của Sprint 2, sau A-062 (`12-roadmap.md`, mục Vận hành seed).

## Nạp gì

| Bảng | Dòng |
|---|---|
| `employee` | 5 nhân viên giả: `GIA-0001`…`GIA-0003` (vai trò `EMPLOYEE`), `GIA-0101`, `GIA-0102` (vai trò `ADMIN_OFFICER`). `source = 'SEED_DEV_FAKE'`, tên có "(GIẢ)", không `national_id`, không ngày sinh |
| `employee_role` | mỗi nhân viên một vai trò như trên |
| `employee_credential` | hash `argon2id` (tham số WV-16 của cấu hình) của mật khẩu sinh ngẫu nhiên |
| `employee_permission_grant` | **một** dòng: `document.sign` cho `GIA-0101`. **Không** cấp `operating_mode.change` cho ai — lớp 1 của ADR-023 |

## Mật khẩu — ở đâu, và ai đọc

- Sinh ngẫu nhiên (`secrets.token_urlsafe`), **không in ra màn hình hay log**.
- Ghi vào **`tools/seed-dev/out/passwords.local.txt`** (mỗi dòng: `mã<TAB>mật khẩu`). Thư mục `tools/seed-dev/out/` nằm trong `.gitignore`.
- **Người triển khai không đọc file này.** Mật khẩu giao cho người thử ngoài hệ thống (`docs/testing/nguoi-thu.md`).
- Mất file thì chạy lại với `--reset-passwords` (đặt lại mật khẩu của cả năm tài khoản).

## Chạy

Credential `bo19_migrator` đọc từ **biến môi trường** `BO19_MIGRATOR_DATABASE_URL` — không bao giờ trên dòng lệnh. DB phải đã `migrate_main` xong.

```bash
# từ thư mục gốc repo; trong cùng môi trường đã cài phụ thuộc của backend
BO19_MIGRATOR_DATABASE_URL=... python tools/seed-dev/seed_dev.py
python tools/seed-dev/seed_dev.py --reset-passwords        # đặt lại mật khẩu
python tools/seed-dev/seed_dev.py --allow-host pg          # host không phải localhost — ví dụ tên container (CI)
```

Chạy lại không đổi gì đã có. Mọi lệnh ghi nằm trong một giao dịch. Mã thoát: `0` xong · `1` bị chặn hoặc lỗi DB · `2` thiếu biến môi trường.

## Những gì chặn chạy nhầm

1. **Host của DSN** phải là `localhost`, `127.0.0.1`, `::1` hay socket Unix; host khác phải khai `--allow-host`. Một DSN trỏ vào Render bị từ chối **trước khi nối** (`SEED_HOST_NOT_LOCAL`).
2. **Role đang nối** phải là `bo19_migrator` (`SEED_ROLE_NOT_MIGRATOR`).
3. **`operating_mode` hiện hành** của DB phải là `NON_PRODUCTION` (`SEED_DB_NOT_NON_PRODUCTION`) — dữ liệu giả không vào DB đang ở `PRODUCTION`.
4. Tham số `argon2id` trong cấu hình thấp hơn WV-16 thì seed từ chối hash (`SEED_ARGON2_PARAMS_BELOW_WV16`) — cùng luật không ngoại lệ của bước kiểm khởi động #20.

`--allow-host` chỉ nới chặn 1. Hai chặn còn lại không có cờ nào tắt.

## Kiểm contract sau seed (AC-1.6)

```bash
python tools/contract-checks/check_grants.py --app-dsn env:BO19_APP_DSN_LOCAL   # DSN của bo19_app, đọc từ biến môi trường
```

`backend/tests/test_seed_dev.py` chạy đúng chuỗi migrate → seed → `check_grants.py --app-dsn` trên PostgreSQL thật ở mỗi lần CI.
