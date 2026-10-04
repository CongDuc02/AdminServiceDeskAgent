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

## 4. Deploy B — trên Render, 2026-10-04

Manual Deploy → Deploy latest commit, `0b4b102`. Tên service che bằng `<service>` — không phải secret, nhưng không cần trong repo.

Log, PO gửi, nguyên văn:

```text
==> Deploying...
==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-10-04 12:29:34,730 INFO bo19.startup STARTUP_OK bước kiểm #1, #2 đạt
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
INFO:     127.0.0.1:35310 - "HEAD / HTTP/1.1" 404 Not Found
==> Your service is live 🎉
==>
==> ///////////////////////////////////////////////////////////
==>
==> Available at your primary URL https://<service>.onrender.com
==>
==> ///////////////////////////////////////////////////////////
```

Events, nguyên văn:

```text
Deploy live for 0b4b102: CLAUDE.md: mục 6 thêm backend/migrations/ledger/ — PO áp
October 4, 2026 at 7:29 PM
Deploy started for 0b4b102: CLAUDE.md: mục 6 thêm backend/migrations/ledger/ — PO áp
Manually triggered by you via Dashboard
October 4, 2026 at 7:28 PM
```

`curl -s -w '\nhttp=%{http_code} time=%{time_total}s\n' https://<service>.onrender.com/healthz`, hai lần liên tiếp:

```text
{"status":"ok"}
http=200 time=0.550544s
{"status":"ok"}
http=200 time=0.303003s
```

**Đọc:**

- Bước kiểm #1, #2 đạt trên Render, qua host nội bộ, credential `bo19_app`. Deploy bắt đầu 7:28 PM, Live 7:29 PM.
- `/healthz` 200 từ ngoài Internet.
- **Thời gian đánh thức chưa đo được.** `curl` chạy ngay sau khi deploy Live, nên instance đang thức: 0.55 s rồi 0.30 s là thời gian trả lời của một instance thức, không phải cold start. Đo đánh thức cần một lần `curl` sau khi service đã ngủ — chưa làm.
- Dòng `HEAD / … 404` đến từ `127.0.0.1` ngay trước `Your service is live`: một yêu cầu từ phía Render vào `/`, không phải health check `/healthz`. Không ảnh hưởng kết quả; ứng dụng chưa có route `/`. Nguồn tài liệu cho yêu cầu này chưa có — không diễn giải thêm.

## 5. Deploy C — `BO19_DATABASE_URL` mật khẩu sai, 2026-10-04

Cách làm, PO duyệt: sửa một ký tự trong phần mật khẩu của `BO19_DATABASE_URL`, giữ host; lưu bằng **Save and deploy** — deploy lại bản build đang có với giá trị mới (`docs/reference/render-env-vars-manual-deploy.md`), đúng một deploy. Một vòng `curl` `/healthz` mỗi khoảng 5 giây chạy từ trước khi lưu tới sau khi deploy hỏng; giờ là giờ máy PO, cùng múi với Events.

Log C, PO gửi, nguyên văn:

```text
==> Deploying...
==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-10-04 12:51:52,877 ERROR bo19.startup STARTUP_FAIL STARTUP_DB_CONNECT_FAILED class=OperationalError sqlstate=None
==> Exited with status 1
==> Common ways to troubleshoot your deploy: https://render.com/docs/troubleshooting-deploys
2026-10-04 12:51:59,537 ERROR bo19.startup STARTUP_FAIL STARTUP_DB_CONNECT_FAILED class=OperationalError sqlstate=None
```

Vòng `curl`, nguyên văn — lệnh `for i in $(seq 1 60); do printf '%s ' "$(date +%H:%M:%S)"; curl -s -o /dev/null -m 10 -w 'http=%{http_code} time=%{time_total}s\n' https://<service>.onrender.com/healthz; sleep 5; done`:

```text
19:49:01 http=200 time=0.765965s
19:49:07 http=200 time=0.343278s
19:49:13 http=200 time=0.355269s
19:49:19 http=200 time=0.218798s
19:49:24 http=200 time=0.392383s
19:49:30 http=200 time=0.244420s
19:49:36 http=200 time=0.283327s
19:49:41 http=200 time=0.279673s
19:49:47 http=200 time=0.244787s
19:49:52 http=200 time=0.249240s
19:49:57 http=200 time=0.197431s
19:50:03 http=200 time=0.186653s
19:50:08 http=200 time=0.244210s
19:50:14 http=200 time=0.276902s
19:50:19 http=200 time=0.191967s
19:50:25 http=200 time=0.160845s
19:50:30 http=200 time=0.231297s
19:50:35 http=200 time=0.174670s
19:50:41 http=200 time=0.169464s
19:50:46 http=200 time=0.354499s
19:50:52 http=200 time=0.201928s
19:50:57 http=200 time=0.328424s
19:51:03 http=200 time=0.159805s
19:51:08 http=200 time=0.196694s
19:51:13 http=200 time=0.170674s
19:51:19 http=200 time=0.370273s
19:51:24 http=200 time=0.199932s
19:51:30 http=200 time=0.248189s
19:51:35 http=200 time=1.300638s
19:51:42 http=200 time=1.358893s
19:51:48 http=200 time=0.183152s
19:51:54 http=200 time=0.301285s
19:51:59 http=200 time=0.206206s
19:52:05 http=200 time=0.182398s
19:52:10 http=200 time=0.168231s
19:52:16 http=200 time=0.275211s
19:52:21 http=200 time=0.167926s
19:52:26 http=200 time=0.187674s
19:52:32 http=200 time=0.182855s
19:52:37 http=200 time=0.351489s
19:52:43 http=200 time=0.160814s
19:52:48 http=200 time=0.180407s
19:52:54 http=200 time=0.162405s
19:52:59 http=200 time=0.178375s
19:53:04 http=200 time=0.173537s
19:53:10 http=200 time=0.164222s
19:53:15 http=200 time=0.218097s
19:53:20 http=200 time=0.264382s
19:53:26 http=200 time=0.167644s
19:53:31 http=200 time=0.293393s
19:53:37 http=200 time=0.315507s
19:53:42 http=200 time=0.189778s
19:53:48 http=200 time=0.172770s
19:53:53 http=200 time=0.202702s
19:53:59 http=200 time=0.163398s
19:54:04 http=200 time=0.160750s
19:54:09 http=200 time=0.186402s
19:54:15 http=200 time=0.220600s
19:54:20 http=200 time=0.204080s
19:54:26 http=200 time=0.187179s
```

Events của C và C5, nguyên văn, mới nhất ở trên:

```text
Deploy live for 0b4b102: CLAUDE.md: mục 6 thêm backend/migrations/ledger/ — PO áp
October 4, 2026 at 7:55 PM
Deploy started for 0b4b102: CLAUDE.md: mục 6 thêm backend/migrations/ledger/ — PO áp
Manually triggered by you via Dashboard
October 4, 2026 at 7:54 PM
Deploy failed for 0b4b102: CLAUDE.md: mục 6 thêm backend/migrations/ledger/ — PO áp
Exited with status 1 while running your code. Check your deploy logs for more information.
October 4, 2026 at 7:51 PM
Rollback
Deploy started for 0b4b102: CLAUDE.md: mục 6 thêm backend/migrations/ledger/ — PO áp
Environment updated
October 4, 2026 at 7:51 PM
```

**Đọc:**

- Tiến trình không kết nối được → `STARTUP_DB_CONNECT_FAILED`, thoát mã 1; Render chạy lại một lần sau khoảng 7 giây, cùng kết quả; `Deploy failed` trong cùng phút 7:51 PM. Log không có host, DSN hay mật khẩu.
- **Render giữ bản cũ suốt deploy hỏng:** 60 / 60 lần `curl` từ 19:49:01 tới 19:54:26 trả `200` — trước, trong và sau deploy C. Trong phút 19:51 có 12 lần. Hai lần chậm hơn hẳn — 1.300638 s lúc 19:51:35 và 1.358893 s lúc 19:51:42 — rơi vào lúc deploy C chạy; vẫn `200`. Nguyên nhân hai lần chậm chưa xác định — không diễn giải thêm.
- `sqlstate=None` khi sai mật khẩu: mã này **không phân biệt** được sai mật khẩu với host không tới được. Ghi nhận, chưa đổi thiết kế.
- Dòng `Rollback` nằm ngay dưới `Deploy failed`. Theo vị trí, có thể là nhãn nút của dashboard chứ không phải một sự kiện — chưa xác minh, không có nguồn trong `docs/reference/`. Không có sự kiện deploy nào khác giữa C và C5.

## 6. Dọn dẹp — C4, C5 (ngoài phép đo)

C4: PO trả `BO19_DATABASE_URL` về giá trị đúng, lưu bằng **Save only** — không sinh deploy; Events không có dòng nào giữa `Deploy failed` 7:51 PM và `Deploy started` 7:54 PM.

C5: Manual Deploy → Deploy latest commit. Log, nguyên văn:

```text
Deploying...
==> Setting WEB_CONCURRENCY=1 by default, based on available CPUs in the instance
2026-10-04 12:55:08,572 INFO bo19.startup STARTUP_OK bước kiểm #1, #2 đạt
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
INFO:     127.0.0.1:43010 - "HEAD / HTTP/1.1" 404 Not Found
==> Your service is live 🎉
INFO:     10.25.98.2:0 - "GET / HTTP/1.1" 404 Not Found
==>
==> ///////////////////////////////////////////////////////////
==>
==> Available at your primary URL https://<service>.onrender.com
==>
==> ///////////////////////////////////////////////////////////
```

`curl` sau C5:

```text
{"status":"ok"}
http=200 time=0.189131s
```

Đọc: giá trị trả lại ở C4 đúng — `STARTUP_OK`, Live 7:55 PM. `GET /` từ `10.25.98.2` — nguồn chưa xác định, ứng dụng chưa có route `/`.

## 7. Đánh thức — chưa đo được

PO, sau ≥ 20 phút không gọi:

```text
{"status":"ok"}
http=200 time=0.303003s
{"status":"ok"}
http=200 time=0.362863s
```

Theo `docs/reference/render-free-tier.md`, Web Service free ngủ sau 15 phút không có traffic vào và mất khoảng một phút để thức lại. Lần đầu 0.30 s **không** có dấu hiệu instance đã ngủ — có thể đã có traffic vào trong khoảng đó (ví dụ yêu cầu `GET /` như ở C5), chưa xác định. **Thời gian đánh thức: chưa đo được.** Muốn đo: ghi giờ yêu cầu cuối, chờ quá 15 phút, xác nhận trong log không có yêu cầu nào khác, rồi `curl`.

## 8. Kết luận S2

| Câu hỏi | Kết quả |
|---|---|
| Image chạy trên Render free, user không root, bước kiểm #1, #2 | Đạt — B, C5 |
| Tiến trình thoát lúc khởi động có làm deploy hỏng | **Có** — `Exited with status 1 while running your code`, `Deploy failed` trong vài phút, không chờ 15 phút (A, C) |
| Deploy hỏng có giữ bản đang chạy | **Có** — 60 / 60 `curl` `200` suốt C |
| Thiếu sổ → #1 chặn | Đạt — A |
| Credential sai → không phục vụ | Đạt — C |
| Thời gian đánh thức | Một lần đo: 22.478055 s — điều kiện "không request 15 phút trước" chưa xác nhận; mục 9 |

## 9. Đánh thức — lần đo thứ hai, PO gửi trước khi đóng phiên 2026-10-04

```text
{"status":"ok"}
http=200 time=22.478055s
```

Lệnh như mục 4. **Đọc:** 22.478055 s — chậm hơn hẳn mọi lần gọi instance đang thức (0.16–1.36 s ở mục 4, 5, 7), nên nhiều khả năng instance đã ngủ và phải thức lại. `docs/reference/render-free-tier.md` nói việc thức lại "takes about one minute"; số đo thấp hơn. **Chưa đủ điều kiện của cách đo đã duyệt:** chưa xác nhận trong log Render không có request nào trong 15 phút trước lần gọi, và chưa ghi giờ gọi. Một lần đo, từ mạng nhà PO — không phải phân phối.
