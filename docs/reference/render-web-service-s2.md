# Render Web Service — S2 của Spike 1: deploy A, B, C

Kết quả chạy thật trên Render, PO gửi. Không có DSN hay host trong log.

## 1. Cấu hình Web Service — PO, 2026-10-04

Language Docker; branch `main`; Singapore, cùng region với DB chu kỳ 2; `./Dockerfile`, context `.`; Instance Free; Health Check Path `/healthz`; Auto-Deploy Off; Pre-Deploy Command trống. Biến môi trường **duy nhất** `BO19_DATABASE_URL` — host nội bộ, credential `bo19_app`, `sslmode=require` — nhập tay, không dùng "Add from .env". `BO19_ENVIRONMENT` không đặt: image S2 chưa có bước kiểm #16.

Image: `backend/`, `Dockerfile`, `.dockerignore` không đổi giữa commit `d873af4` và `0b4b102` — `git diff --stat` trống. File migration là LF ở cả index lẫn working tree (`git ls-files --eol`), nên sha256 trong image Render trùng image build ở local.

## 2. Deploy A — trước `migrate_main`

DB chu kỳ 2 chỉ qua bước 0: chưa có bảng, chưa có sổ (`docs/reference/render-postgres-s2-step0.md`).

Trạng thái cuối PO đọc trên dashboard: **`Deploy failed`**.

Mốc giờ PO gửi, nguyên văn: `Deployed-Oct 4, 2026at6:52:53 PM`. Múi giờ của dashboard không ghi; log dưới đây theo UTC — dòng `logging` của image không đổi múi giờ.

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
- **Chưa đo:** mốc Render chuyển sang `Deploy failed`, nên chưa biết Render dừng ngay sau vài lần thoát hay chờ hết cửa sổ 15 phút của health check (`docs/reference/render-web-service-health-checks.md`). Chưa có bản deploy thành công trước đó, nên vế "giữ bản cũ" chưa thử được ở A — đó là việc của C.
