# Nhật ký đo — S4 của Spike 1 (A-031, A-086)

Ghi nguyên văn số đo của S4: shutdown delay thật của Web Service free và `SIGTERM` khi ngủ. Nhật ký sống: mỗi lượt đo thêm một mục ở cuối, không sửa mục cũ — chỗ sai thì ghi đính chính ở mục mới. Cùng định dạng với `render-s3-nhat-ky-do.md`.

- **Đối tượng đo:** Web Service free, Docker. **Start command là `api_main`** (`CMD` của `Dockerfile`), không phải `combined_main` như ADR-033: log Render có `STARTUP_OK bước kiểm #1, #2 đạt`, chuỗi chỉ tồn tại ở `api_main.py`; `combined_main.py` và `worker_main.py` chỉ là khung một dòng. Kết quả S4 **chỉ còn đúng cho `combined_main` nếu nó xử lý `SIGTERM` như `api_main`** — điều kiện khi track build chuyển start command.
- **Mã đo:** nhánh `spike/s4-sigterm`. Handler ghi `SIGTERM_RECEIVED`; vòng giữ không thoát ghi `SHUTDOWN_HOLD n=<k>` mỗi giây tới trần `BO19_S4_HOLD_S` = 120 s; log uvicorn mang giờ UTC. Bản `37fa504` chưa có kết nối nhân chứng.
- **Giờ:** UTC; giờ Hà Nội = UTC+7. Giờ trong log là giờ đồng hồ của instance; giờ Events của Render có độ chính xác phút.
- **Host, địa chỉ nội bộ và header nội bộ không được ghi** (như S3).
- **Dữ liệu thô:** log Render do PO dán; chép dòng ứng dụng có giờ vào các bảng dưới.

## 1. Đối chứng local — vòng giữ ghi đủ tới SIGKILL

`docker stop -t T` trên container dựng từ `Dockerfile`, `BO19_S4_HOLD_S=120`:

| `-t` | Dòng `SHUTDOWN_HOLD` cuối trong `docker logs` | Kill thật nằm trong | Có dòng n+1? | Exit code |
|---|---|---|---|---|
| 10 | n=10, 9.179 s sau `SIGTERM_RECEIVED` | (9.179, 10.179] s ∋ 10 | không | 137 |
| 30 | n=30, 29.101 s | (29.101, 30.101] s ∋ 30 | không | 137 |

Số thứ tự liên tục 1..10 và 1..30. Không đặt biến: `docker stop` mất 1.0 s, **exit code 0** — `api_main` là PID 1 nên `signal.raise_signal` mà uvicorn 0.34.2 gọi lại sau khi tắt êm bị bỏ qua. **Mở cho track build:** PID 1 trong container không có init thường không reap tiến trình con; worker sẽ chạy `soffice` làm tiến trình con (ADR-015).

## 2. Sự kiện deploy — tab Events của Render (giờ Hà Nội)

| Deploy | Bấm | Kết quả |
|---|---|---|
| 1 | 11:42 | Live 11:43 |
| 2 | 11:54 | **Failed — Timed out, 12:12.** `Port scan timeout reached, no open ports detected`. Instance mới in `STARTUP_OK` 04:59:02.523Z rồi không in gì; không có `S4_ARMED` |
| (Render dựng lại deploy 1) | — | instance mới khởi động 05:12:49.8Z, đúng phút deploy 2 báo hỏng |
| 3 | 13:56 | Live 13:57 |

Deploy 2 bắt đầu **trước** `SIGTERM` ngủ lúc 04:58:43 của instance cũ (4 phút 43 giây sau khi bấm) và hỏng; cùng commit, cùng biến với deploy 1 đã chạy được. **Không biết nguyên nhân.** Hai luồng log cùng kết thúc đột ngột: instance cũ dừng ở 04:58:47.331, instance mới sau 04:59:02.523. Tài liệu Render đã lấy: deploy hỏng thì "your service continues running its most recent successful deploy".

## 3. Bốn lần `SIGTERM`: dòng giữ cuối thấy được luôn là n=5

| Đường | Request cuối (access log) | `SIGTERM_RECEIVED` | Khoảng cách | `SHUTDOWN_HOLD` cuối |
|---|---|---|---|---|
| Ngủ, có deploy 2 chồng | 04:43:43.773 | 04:58:43.158 | 899.385 s | **n=5**, 4.174 s |
| Ngủ, sạch | 05:17:17.623 | 05:32:17.272 | 899.649 s | **n=5**, 4.148 s |
| Ngủ, sạch | 05:38:15.407 | 05:53:15.220 | 899.813 s | **n=5**, 4.139 s |
| **Deploy, sạch** | — (instance cũ phục vụ lần cuối khoảng 06:56:19) | 06:57:36.634 | — | **n=5**, 4.168 s |

- **Đồng hồ ngủ:** `SIGTERM` đến 899.4–899.8 s sau request cuối, tính từ lúc instance **phục vụ** request. Lần 3: tôi gửi lúc 05:37:52.956 nhưng service đang ngủ, request chờ 22.5 s để dậy và được phục vụ lúc 05:38:15.407; `SIGTERM` đến 899.813 s sau giờ phục vụ, không phải sau giờ gửi.
- **Hold dừng ở n=5 (4.14–4.17 s sau `SIGTERM`) ở cả bốn lần**, hai đường khác nhau, lệch nhau 0.04 s. Kill hay đường log bị cắt xảy ra trong (4.17, 5.17] s sau `SIGTERM`. **Log ứng dụng không phân biệt được hai khả năng.** Shutdown delay mặc định 30 s theo tài liệu Render; nếu n=5 là kill thật thì drain window chỉ ≈ 5 s.
- **Handler của bản `37fa504` chỉ ghi lần `SIGTERM` đầu, không ghi lần hai và không ghi SIGINT**, nên bốn log không loại trừ được tín hiệu thứ hai trong 5 s đầu. Theo mã nguồn uvicorn 0.34.2, chỉ SIGINT thứ hai đặt `force_exit` và nó không cắt được vòng giữ nằm trong `lifespan.shutdown()`.

## 4. `SIGTERM` đến cùng lúc instance mới Live, không phải 60 s sau — ghi 2026-10-05

Deploy 3 (sạch). Giờ trong log của hai instance:

| Giờ (UTC) | Sự kiện |
|---|---|
| 06:57:28.483 | instance mới khởi động (`boot_utc`) |
| 06:57:31.277 | uvicorn của instance mới lên |
| 06:57:32.236 | Render dò cổng instance mới (`HEAD /` từ 127.0.0.1) |
| **06:57:36.634** | **`SIGTERM_RECEIVED` của instance cũ** — 8.151 s sau khi instance mới khởi động, 4.398 s sau lần dò cổng |
| 06:57:36.801 → 06:57:37.803 | dòng "Your service is live" nằm giữa `SHUTDOWN_HOLD` n=1 và n=2 trong log gộp |

- **`SIGTERM` đến trong khoảng 0.17–1.17 s trước dòng "Your service is live"** (theo thứ tự trong log gộp; dòng nền tảng không mang giờ). Không có khoảng 60 s.
- **`06-structure.md` mục Tắt tiến trình êm và ADR-016 viết** "`SIGTERM` tới instance cũ 60 giây sau khi instance mới nhận traffic", dẫn `docs/reference/render-deploys-docker.md`. Đo trên Web Service free cho thấy **không có 60 s đó** ở deploy này. Một lần quan sát, một gói; chưa sửa `06-structure.md` hay ADR-016.

## 5. Khai báo trước kết quả của nhân chứng — 2026-10-05, TRƯỚC khi deploy mã mới

**Vì sao cần:** bốn lần cùng một kết quả (n=5) mà log không phân biệt được kill với cắt log. Chỉ dòng log là đường duy nhất đã dùng.

**Cách đo:** bản mã mới mở một kết nối PostgreSQL riêng **lúc khởi động** (không phải lúc `SIGTERM`), `application_name` = `s4 boot=<boot_utc> n=0`. Trong vòng giữ, mỗi giây sau khi ghi dòng `SHUTDOWN_HOLD n=<k>`, đặt `application_name` = `s4 boot=<boot_utc> n=<k>` trên kết nối đó. Từ máy người triển khai, bằng credential `bo19_app` đọc từ `.env`, poll `pg_stat_activity` mỗi 0.25 s, ghi (giờ máy, `n`, `state`). Hai số đo **báo riêng**: (a) **`n` cuối đọc được**, (b) **lúc kết nối biến mất** (lần poll đầu tiên không thấy dòng, sau khi đã thấy). Handler ghi **mọi** tín hiệu (SIGTERM kèm số lần, SIGINT, và các tín hiệu khác).

**Kết quả đã khai báo — áp đúng như viết, không sửa sau khi có số:**

| Điều thấy (nhân chứng) | Kết luận |
|---|---|
| `n` cuối ≈ 5 (4–6), kết nối **biến mất ngay** (≤ 2 s sau lần đổi `n` cuối, tức ≤ khoảng 6.5 s sau `SIGTERM`) | **Kill ≈ 5 s** sau `SIGTERM` |
| `n` **tiếp tục tăng** tới ≈ 30 (≥ 25), dù log dừng ở n=5 | **Đường log bị cắt**; shutdown delay thật ≈ 30 s |
| `n` dừng ≈ 5, kết nối **còn đó** ≥ 10 s sau lần đổi `n` cuối (`state` không đổi) | **Treo** — cắt mạng hoặc đóng băng; với lượt chat tương đương kill. **Ghi thời gian treo** (tới lúc kết nối biến mất hoặc tới hết poll, trần 10 phút) |
| `n` cuối ở giữa (6–24), hoặc kết quả không rơi vào ba dòng trên | **Không gán nhãn**; ghi số, báo người quyết |

Khoảng thời gian tính từ `SIGTERM_RECEIVED` trong log. `n` của nhân chứng có thể chậm hơn `n` của log tới một lần đổi (một giây) vì `SET` chạy sau dòng log. Poll bị gián đoạn quá 1 s thì khoảng đó ghi "không biết".

**Chưa sửa** WV-01, bước kiểm khởi động #11 hay ADR-016. Nếu xác nhận kill ≈ 5 s: dừng, báo người quyết; bước kế có thể là thử `maxShutdownDelaySeconds` trên gói free (PO quyết lúc đó).

## 6. Lần `SIGTERM` ngủ thứ năm

Instance của deploy 3 (`boot_utc` 06:57:28.483). **Request mà nó thấy:** `HEAD /` từ 127.0.0.1 lúc 06:57:32.236 (Render dò cổng, không qua proxy) và `GET /` 404 lúc 06:57:37.944 (Render, sau khi Live). Request lúc 06:56:19Z của người đo do instance **cũ** phục vụ — nó không tính cho instance này. **Dự đoán, khai báo trước khi có số:** nếu lần `GET /` của Render tính là request và đồng hồ là 899.4–899.8 s như ba lần trước, `SIGTERM` đến khoảng **07:12:37Z**; nếu lần `GET /` không tính, từ `HEAD /` là khoảng 07:12:32Z. Không ai gọi service trong khoảng này. **Để diễn ra, ghi thành quan sát thứ năm** (chưa có số — chờ log); nó còn trả lời việc dò của Render có làm mới đồng hồ ngủ hay không.
