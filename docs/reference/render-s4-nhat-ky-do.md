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

### 1.1 Đối chứng local của nhân chứng — bản `83591ee`, bộ poll `bab67b0`

Container app dựng từ `Dockerfile` nối DB Render bằng `bo19_app` (URL ngoài), `BO19_S4_HOLD_S=120`; bộ poll chạy trong container thứ hai, hỏi `pg_stat_activity` mỗi 0.25 s (140–220 lần hỏi mỗi ca, 0 lỗi, không khoảng cách > 1 s). Credential qua env-file tạm, đã xoá.

| `docker stop -t` | (a) `n` cuối đọc được | (b) kết nối biến mất | `n` cuối thấy / biến mất, so với `SIGTERM_RECEIVED` | Exit code |
|---|---|---|---|---|
| 10 | **10** | 0.997 s sau lần đổi `n` cuối | 9.191 s / **10.188 s** | 137 |
| 10 (lần khác) | 10 | 1.000 s sau lần đổi `n` cuối | T1 + 9.000 s / T1 + **10.000 s** | 137 |
| 30 | **30** | 1.000 s sau lần đổi `n` cuối | T1 + 28.997 s / T1 + **29.997 s** | 137 |

T1 là lúc bộ poll thấy `n=1` lần đầu — mốc không phụ thuộc lệch đồng hồ giữa máy và instance (`n=1` được đặt 0.12–0.17 s sau `SIGTERM`). Nhân chứng thấy đúng: `n` tăng tới T, kết nối biến mất đúng lúc kill, độ phân giải 0.25 s; phần lệch ≈ 0.19 s là độ trễ của poll và của máy chủ PostgreSQL phát hiện kết nối đóng. Bản này cũng ghi **mọi** tín hiệu: `SIGNAL_RECEIVED sig=SIGTERM nth=1 total=1 …` (kèm `SIGTERM_RECEIVED` ở lần đầu); `S4_ARMED` liệt kê các tín hiệu khác đã đặt handler ghi (`SIGHUP`, `SIGQUIT`, `SIGUSR1`, `SIGUSR2`, `SIGALRM`, `SIGCONT`, `SIGTSTP`); kết nối nhân chứng mở lúc khởi động (`WITNESS_OPEN … n=0`).

## 2. Sự kiện deploy — tab Events của Render (giờ Hà Nội)

| Deploy | Bấm | Kết quả |
|---|---|---|
| 1 | 11:42 | Live 11:43 |
| 2 | 11:54 | **Failed — Timed out, 12:12.** `Port scan timeout reached, no open ports detected`. Instance mới in `STARTUP_OK` 04:59:02.523Z rồi không in gì; không có `S4_ARMED` |
| (Render dựng lại deploy 1) | — | instance mới khởi động 05:12:49.8Z, đúng phút deploy 2 báo hỏng |
| 3 | 13:56 | Live 13:57 |

Deploy 2 bắt đầu **trước** `SIGTERM` ngủ lúc 04:58:43 của instance cũ (4 phút 43 giây sau khi bấm) và hỏng; cùng commit, cùng biến với deploy 1 đã chạy được. **Không biết nguyên nhân.** Hai luồng log cùng kết thúc đột ngột: instance cũ dừng ở 04:58:47.331, instance mới sau 04:59:02.523. Tài liệu Render đã lấy: deploy hỏng thì "your service continues running its most recent successful deploy".

## 3. Năm lần `SIGTERM`: dòng giữ cuối thấy được luôn là n=5

| Đường | Request cuối (access log) | `SIGTERM_RECEIVED` | Khoảng cách | `SHUTDOWN_HOLD` cuối |
|---|---|---|---|---|
| Ngủ, có deploy 2 chồng | 04:43:43.773 | 04:58:43.158 | 899.385 s | **n=5**, 4.174 s |
| Ngủ, sạch | 05:17:17.623 | 05:32:17.272 | 899.649 s | **n=5**, 4.148 s |
| Ngủ, sạch | 05:38:15.407 | 05:53:15.220 | 899.813 s | **n=5**, 4.139 s |
| **Deploy, sạch** | — (instance cũ phục vụ lần cuối khoảng 06:56:19) | 06:57:36.634 | — | **n=5**, 4.168 s |
| Ngủ, sạch (instance của deploy 3) | `GET /` của Render 06:57:37.944 | 07:12:37.214 | **899.270 s** | **n=5**, 4.107 s |

- **Đồng hồ ngủ:** `SIGTERM` đến 899.4–899.8 s sau request cuối, tính từ lúc instance **phục vụ** request. Lần 3: tôi gửi lúc 05:37:52.956 nhưng service đang ngủ, request chờ 22.5 s để dậy và được phục vụ lúc 05:38:15.407; `SIGTERM` đến 899.813 s sau giờ phục vụ, không phải sau giờ gửi.
- **Hold dừng ở n=5 (4.11–4.17 s sau `SIGTERM`) ở cả năm lần**, hai đường khác nhau, lệch nhau 0.07 s. Kill hay đường log bị cắt xảy ra trong (4.17, 5.17] s sau `SIGTERM`. **Log ứng dụng không phân biệt được hai khả năng.** Shutdown delay mặc định 30 s theo tài liệu Render; nếu n=5 là kill thật thì drain window chỉ ≈ 5 s.
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

## 6. Lần `SIGTERM` ngủ thứ năm — kết quả

Log PO dán 2026-10-05: `SIGTERM_RECEIVED utc=2026-10-05T07:12:37.214+00:00 pid=1 boot_utc=2026-10-05T06:57:28.483+00:00`, rồi `Shutting down`, `SHUTDOWN_HOLD` n=1..5 (`since_sigterm` 0.107 → 4.107 s) và **không có dòng nào sau n=5**. Không có `SIGNAL_RECEIVED` (bản `37fa504` chưa ghi), không có request nào khác giữa 06:57:37.944 và `SIGTERM`.

| Mốc | Khoảng tới `SIGTERM_RECEIVED` |
|---|---|
| `GET /` của Render, 06:57:37.944 (qua mạng Render, sau khi Live) | **899.270 s** |
| `HEAD /` từ 127.0.0.1, 06:57:32.236 (Render dò cổng) | 904.978 s |
| dòng "Your service is live" (≈ `SHUTDOWN_HOLD` n=1, 06:57:36.801; nằm trong 06:57:36.8–37.8) | 899.4–900.4 s |

**So với dự đoán đã commit (07:11:54Z):** nếu `GET /` của Render tính là request, `SIGTERM` ≈ 07:12:37Z; nếu chỉ `HEAD /`, ≈ 07:12:32Z. Quan sát 07:12:37.214 — **khớp dự đoán thứ nhất**, không khớp thứ hai (lệch 5.0 s).

**`GET /` của Render lúc 06:57:37.944 có làm mới đồng hồ ngủ không?** Dữ liệu **ủng hộ có**: khoảng 899.270 s từ nó nằm trong dải 899.27–899.81 s của bốn lần trước tính từ request cuối; từ `HEAD /` thì 904.978 s, ngoài dải. **Một quan sát chưa đủ loại cách giải thích khác:** đồng hồ tính từ lúc instance **Live** (06:57:36.8–37.8) cũng khớp (899.4–900.4 s), vì `GET /` đến chỉ 0.1–1.1 s sau Live. Cách giải thích đó **bị lần 3 bác** ở đường đánh thức: instance dậy 05:38:07, request lúc 05:38:15.407, `SIGTERM` lúc 05:53:15.220 — tức 15 phút sau **request**, không sau lúc dậy (nếu tính từ lúc dậy thì là 05:53:07) — nhưng chưa bác ở đường deploy-Live. Kết luận hẹp: **`GET /` của Render rất có thể tính; `HEAD /` từ 127.0.0.1 không (hoặc không phải request cuối); chưa phân biệt được "tính từ `GET /`" với "tính từ lúc Live" ở đường deploy.**

## 7. Kết quả nhân chứng — deploy 5, 2026-10-05

Bản `edf3687` (kết nối nhân chứng mở lúc khởi động, ghi mọi tín hiệu). Deploy 4 đưa bản này lên (07:31–07:32Z, instance cũ chưa có nhân chứng); **deploy 5** (instance cũ `boot_utc` 07:32:33.036, đã `WITNESS_OPEN` và `S4_ARMED … witness=True`) là phép đo. Bộ poll (`bab67b0`) bật 07:33:00Z từ máy người đo, hỏi `pg_stat_activity` mỗi 0.25 s: 1549 lần hỏi, 0 lỗi; một khoảng cách 1.219 s lúc 07:33:03.

### 7.1 Hai số, báo riêng

| | Giá trị |
|---|---|
| **(a) `n` cuối đọc được** (nhân chứng) | **5** — `SHUTDOWN_HOLD` cuối trong log cũng n=5 (4.167 s sau `SIGTERM`); `n=6` chưa từng xuất hiện ở cả hai |
| **(b) lúc kết nối biến mất** | lần hỏi cuối **còn** thấy 07:37:00.159, lần hỏi đầu **không** thấy 07:37:00.409 — **1.000 s sau lần đổi `n` cuối** (n=5 thấy 07:36:59.409) |

`SIGTERM_RECEIVED` trong log: 07:36:54.936. Bộ poll thấy `n=1..5` lần lượt lúc +0.473, +1.473, +2.473, +3.473, +4.473 s so với giờ đó; `n=k` được đặt `0.167 + (k−1)` s sau `SIGTERM` theo đồng hồ instance, nên độ lệch (đồng hồ hai máy cộng lượng tử hoá của poll) khoảng **0.31 s**. Trừ độ lệch đó, kết nối biến mất trong khoảng **(4.92, 5.17] s sau `SIGTERM`** — sau lần đặt `n=5` (4.167 s) và trước lần đặt `n=6` (5.167 s). Độ phân giải 0.25 s.

### 7.2 Nhãn theo khai báo trước (mục 5)

| Điều thấy | Nhãn đã khai báo | Khớp? |
|---|---|---|
| `n` cuối = 5, kết nối biến mất 1.000 s sau lần đổi `n` cuối (≤ 2 s) | **Kill ≈ 5 s sau `SIGTERM`** | **Có** |
| `n` tiếp tục tăng tới ≈ 30 | Log bị cắt, delay 30 s | Không (`n` dừng ở 5) |
| `n` dừng ở 5, kết nối còn ≥ 10 s | Treo | Không (biến mất ngay) |

**Kết luận theo nhãn khai báo trước: kill ≈ 5 s sau `SIGTERM`.** Đường log **không** bị cắt: nhân chứng độc lập với log cho cùng `n` cuối và cùng thời điểm. Đây là một lần đo có nhân chứng ở đường deploy (cộng sáu lần chỉ-log ở cả hai đường, mọi lần n=5).

### 7.3 `SIGNAL_RECEIVED` của instance cũ

Chỉ **một** dòng, trong toàn bộ 4.17 s log nhìn thấy được:

```text
SIGNAL_RECEIVED sig=SIGTERM nth=1 total=1 utc=2026-10-05T07:36:54.936+00:00 pid=1
```

Không có `SIGTERM` thứ hai, không SIGINT, và không có `SIGHUP`, `SIGQUIT`, `SIGUSR1`, `SIGUSR2`, `SIGALRM`, `SIGCONT`, `SIGTSTP` (đã đặt handler ghi — `S4_ARMED … extra_signals=…`). **Giả thuyết "uvicorn ép thoát vì tín hiệu lần hai" bị loại cho khoảng 0–4.17 s.** `SIGKILL` không bắt được nên không có dòng — kill được suy từ việc kết nối nhân chứng biến mất.

### 7.4 Điều kèm theo

- **`SIGTERM` đến cùng lúc instance mới Live, ba lần ở đường deploy.** `SIGTERM` của instance cũ đứng trước `GET /` của Render (dò sau khi Live) 1.31 s (deploy 3), 1.78 s (deploy 4), 0.70 s (deploy 5). Không có 60 s nào.
- **Deploy 4** (instance cũ boot 07:31:04.807, do lệnh đánh thức dựng lên): `SIGTERM_RECEIVED` 07:32:42.747, hold dừng n=5 (4.155 s) — lần chỉ-log thứ sáu.
- Instance mới của deploy 5 (`boot_utc` 07:36:46.021) giữ nguyên, bộ poll vẫn chạy; `SIGTERM` ngủ của nó, nếu đến (khoảng 15 phút sau `GET /` 07:36:55.640, tức khoảng 07:51:55Z), sẽ có nhân chứng — lần ngủ đầu tiên có nhân chứng.
- **Chưa sửa** WV-01, bước kiểm khởi động #11 hay ADR-016. Theo chỉ thị: xác nhận kill ≈ 5 s thì dừng và báo người quyết.
