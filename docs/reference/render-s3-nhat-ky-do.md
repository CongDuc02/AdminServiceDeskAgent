# Nhật ký đo — S3 của Spike 1 (A-050, A-025)

Ghi nguyên văn số đo của `tools/render-probes/probe.py` trên Web Service free của Render. Nhật ký sống: mỗi lượt đo thêm một mục ở cuối, không sửa mục cũ — chỗ sai thì ghi đính chính ở mục mới.

- **Đối tượng đo:** Web Service free, Docker, bản `8fdd1bbc725ca5a586eb91238b294933990525a6` trên nhánh `spike/s3-do`. `api_main` có khối `SPIKE S3` (`/api/_spike/{sse,sleep,commit}`).
- **Giờ:** UTC; trong ngoặc là giờ Hà Nội (UTC+7).
- **Host che:** mọi chuỗi chứa `onrender.com` và host của `BO19_SPIKE_BASE_URL` được thay bằng `<render-host>` trước khi ghi. `rndr-id` để nguyên (PO, 2026-10-04).
- **Kết luận là của cả chuỗi `client → Cloudflare → Render`, không quy riêng cho Render** (PO, 2026-10-04): mọi response đều có `Server: cloudflare`, `CF-RAY`, `cf-cache-status`. Mỗi lượt ghi `edge` (đuôi `CF-RAY`). Kết quả là của **Web Service free**; không đóng A-025 cho gói trả phí.
- **Giới hạn đã chấp nhận:** `probe.py` nói HTTP/1.1; trình duyệt qua Render có thể dùng HTTP/2. Giao thức của response thực nhận ghi trong từng lượt.
- **Ngưỡng kết luận gom đệm:** `tools/render-probes/README.md`, mục "Ngưỡng kết luận gom đệm", đặt trước khi đo Render; PO chỉnh ngày 2026-10-04 (một cặp lệch ≥ 2.5 s đơn lẻ là "không kết luận").
- **Dữ liệu thô:** `tools/render-probes/out/<label>/` — gitignore, nằm trên máy người triển khai. Các số dưới đây chép từ đó.

## 1. Lần khởi động của tiến trình (`boot_epoch`)

`boot_epoch` là giờ `api_main` nạp khối SPIKE, trả bởi `/api/_spike/commit`. Đổi giá trị = tiến trình đã khởi động lại (deploy, restart, hay thức dậy sau khi ngủ).

| `boot_epoch` | UTC | Hà Nội | Quan sát thấy ở đâu |
|---|---|---|---|
| 1791125091.522 | 14:44:51 | 21:44:51 | lần kiểm `/commit` đầu tiên sau deploy `8fdd1bb` |
| 1791127520.449 | 15:25:20 | 22:25:20 | lần gọi đầu của `short-1` (15:24:59Z) — service đang ngủ, tự thức |
| 1791128590.965 | 15:43:10 | 22:43:10 | lần gọi đầu của `short-2` (15:42:54Z); `commit_rtt` **22.328715 s** |
| 1791128590.965 | — | — | lượt vô hại trên runner, 16:11:03Z — **không đổi**, không thức |

**Chưa giải thích:** lần thức 15:43:10Z xảy ra sau khoảng 9–10 phút kể từ dòng log cuối của `short-1` (khoảng 15:33Z); `render-free-tier.md` ghi ngủ sau 15 phút không có traffic vào. PO sẽ đối chiếu log Render quanh 21:40–22:50 Hà Nội.

## 2. `short-1` — gián đoạn, không có dữ liệu — 2026-10-04 15:24:59Z

SSE nhịp 5 s, 10 phút, `enc=none` rồi `enc=browser`, từ máy nhà (`home-pc`). Tiến trình `probe.py` bị dừng cùng phiên điều khiển khi nó ở `t = 495.254 s`, tick 99 của lượt 1; log dừng ở đó, không có dòng `ended=` hay lỗi. **Không phải Render cắt.** Bản probe lúc đó chỉ ghi file khi lượt kết thúc nên không còn file kết quả; còn log `tee` có thời điểm nhận phía client, không có giờ máy chủ. Không là điểm dữ liệu; không áp ngưỡng. Từ đó probe ghi JSONL tăng dần.

## 3. `short-2` — hai lượt hoàn tất — 2026-10-04 15:42:54Z đến 16:03:20Z

SSE `sse-events`, `interval=5`, `max=600`, từ máy nhà (`home-pc`), Python 3.11.9, TLSv1.3, HTTP/1.1. `expect_commit` đúng. Bản probe là `99b4fd4` — chưa có JSONL, nên kết quả là file JSON cuối của từng lượt.

| | `enc=none` | `enc=browser` |
|---|---|---|
| Request `Accept-Encoding` | không gửi | `gzip, deflate, br` |
| Bắt đầu (`Date` của response) | 15:43:18Z | 15:53:19Z |
| Thời gian tới header / `open` | 0.085630 s / 0.085739 s | 0.437334 s / 0.437527 s |
| Event / chunk | 122 / 121 | 122 / 121 |
| Cặp event | 120 | 120 |
| `recv_gap` min / median / max | 4.610412 / 5.000139 / 5.539526 s | 4.738139 / 5.001549 / 5.351686 s |
| `send_gap` min / median / max | 4.997265 / 5.000014 / 5.002756 s | 4.992796 / 5.000019 / 5.006764 s |
| Lệch `\|recv_gap − send_gap\|` lớn nhất / median | **0.5398 s** / 0.0289 s | 0.3517 s / 0.0194 s |
| Cặp lệch ≥ 0.5 s / ≥ 2.5 s | 1 / 0 | 0 / 0 |
| `bunched_pairs` | 0 | 0 |
| `lag` (giờ nhận − giờ máy chủ) first / median / last | 0.372511 / 0.361656 / 0.321877 s | 0.653409 / 0.314840 / 0.374297 s |
| Kết thúc | `end_event`, 600.112291 s | `end_event`, 600.215550 s |
| `/commit` sau lượt | 200, cùng commit, `boot_epoch` không đổi, `restarted=False` | như bên trái |
| Edge (đuôi `CF-RAY`) | HKG | HKG |
| **Theo ngưỡng** | **không kết luận** — một cặp lệch 0.5398 s, vượt mốc 0.5 s | **không thấy gom đệm** |

Hai lượt lệch nhau ⇒ theo README phải lặp lại; chưa kết luận A-050 từ điểm nhìn này. `clock_skew_estimate` = 10.758668 s và `commit_rtt` = 22.328715 s: ước tính độ lệch đồng hồ **không dùng được** vì lần gọi `/commit` đầu mất 22 s do service thức dậy.

**Header response thực nhận** (giống nhau ở cả hai lượt, trừ `Date`, `rndr-id`, `CF-RAY`) — lượt `enc=none`:

```text
Date: Sun, 04 Oct 2026 15:43:18 GMT
Content-Type: text/event-stream; charset=utf-8
Transfer-Encoding: chunked
Connection: keep-alive
Cache-Control: no-cache
rndr-id: 943c0307-33c7-4a89
Server: cloudflare
x-render-origin-server: <masked len=7 contained_host=False>
cf-cache-status: DYNAMIC
CF-RAY: a4554d2aad4fef7b-HKG
alt-svc: <masked len=19 contained_host=False>
```

Lượt `enc=browser`: `Date` 15:53:19 GMT, `rndr-id` `40de2db2-0226-439a`, `CF-RAY` `a4555bd65f5e85b5-HKG`, còn lại như trên.

- **Không có `Content-Encoding`** ở cả hai lượt, kể cả khi request gửi `Accept-Encoding: gzip, deflate, br` — Render/Cloudflare không nén `text/event-stream` trong phép đo này. Không có `Content-Length`; `Transfer-Encoding: chunked`.
- `Cache-Control: no-cache` do máy chủ đặt, còn nguyên.

## 4. Lượt vô hại trên runner — 2026-10-04 16:10:53Z

Mục đích: đóng điểm 1 và 2 của tài liệu GitHub (`docs/reference/github-actions-push-trigger.md`).

- Push `a155cc9` (đổi `tools/render-probes/run.json`, `runs: []`) lúc 16:10:53Z. Run `37215817015`, job `probe`, bắt đầu 16:11:01Z, xong 16:11:06Z, **`success`**. Runner `ubuntu-24.04`, image `20260927.320.1`, Python **3.12.3**.
- Bước "Kiểm secret": `success` — hai secret có giá trị khi chạy theo `push` trên nhánh của chính repo. **Điểm 2 đóng.**
- Workflow chưa từng có trên nhánh mặc định mà vẫn chạy khi push đổi file `paths`, theo bản workflow ở chính commit được push. **Điểm 1 đóng** (cùng lượt thất bại `37210992837` ở `3ba669c`, chạy bản có bước "Kiểm secret").
- Probe: `commit=8fdd1bbc725c branch=spike/s3-do kiểm_commit=True client=github-actions runs=0 python=3.12.3 boot_epoch=1791128590.9654794` — cùng `boot_epoch` với `short-2`, nên **lượt này không đánh thức service**.
- `curl` chưa được dùng (`keepwarm_s` không đặt) — sự có mặt của `curl` trên runner chưa kiểm.
- Log của run: 194 dòng; host 0, token 0, `onrender` 0 lần khớp.

## 5. `short-3` — một lượt `enc=none`, hoàn tất — 2026-10-04 16:16:55Z đến 16:26:56Z

SSE `sse-events`, `interval=5`, `max=600`, `enc=none`, từ máy nhà (`home-pc`) do PO chạy trong Git Bash riêng, Python 3.11.9, TLSv1.3, HTTP/1.1, bản probe có JSONL. Lệnh: `--case sse-events --interval 5 --max 600 --enc none --label s3-local-short-3 --expect-commit 8fdd1bb…`. Không có gì chạy trên runner trong lúc đo. JSONL hoàn tất (`state = complete`, 0 dòng hỏng).

| | `short-3`, `enc=none` | (so: `short-2`, `enc=none`) |
|---|---|---|
| Thời gian tới header / `open` | 0.238236 s / 0.239181 s | 0.085630 s / 0.085739 s |
| Event / chunk / cặp | 122 / 121 / 120 | 122 / 121 / 120 |
| `recv_gap` min / median / max | 4.392151 / 5.016614 / 5.599411 s | 4.610412 / 5.000139 / 5.539526 s |
| `send_gap` min / median / max | 4.989331 / 4.999989 / 5.010243 s | 4.997265 / 5.000014 / 5.002756 s |
| Lệch `\|recv_gap − send_gap\|` lớn nhất / median | **0.6083 s** / 0.0308 s | 0.5398 s / 0.0289 s |
| Cặp lệch ≥ 0.5 s / ≥ 2.5 s | **2** / 0 | 1 / 0 |
| `bunched_pairs` | 0 | 0 |
| `lag` first / median / last | 0.281721 / 0.223471 / 0.195526 s (min 0.175, max 0.795) | 0.372511 / 0.361656 / 0.321877 s |
| Kết thúc | `end_event`, 600.182158 s | `end_event`, 600.112291 s |
| `/commit` sau lượt | 200, cùng commit, `boot_epoch` 1791128590.965 không đổi, `restarted=False` | như bên trái |
| `commit_rtt` đầu lượt | 0.245006 s (service đang thức) | 22.328715 s (đang ngủ) |
| Edge | HKG | HKG |
| **Theo ngưỡng** | **không kết luận** | **không kết luận** |

Các cặp có `|lệch| ≥ 0.3 s` (chỉ số cặp: lệch có dấu):

- `short-3`, `none`: 35: +0.388 · 36: −0.389 · 38: +0.338 · 39: −0.329 · 56: +0.325 · **108: +0.600 · 109: −0.608**.
- `short-2`, `none`: 10: +0.308 · 11: −0.307 · 16: +0.324 · 17: −0.323 · **24: +0.540** · 26: −0.390 · 57: +0.323 · 84: +0.313 · 85: −0.320 · 93: +0.302 · 94: −0.305.
- `short-2`, `browser`: 12: +0.352 · 84: +0.309.

Header response: như `short-2` — `Server: cloudflare`, `Transfer-Encoding: chunked`, `Cache-Control: no-cache`, không `Content-Encoding`, `CF-RAY` `a4557e6cdaf58623-HKG`, `rndr-id` `543c7940-8ce0-4628`, `Date` 16:16:55 GMT.

**Kết quả:** hai lượt `enc=none` liên tiếp đều "không kết luận" (lệch lớn nhất 0.540 s rồi 0.608 s, vượt mốc 0.5 s); lượt `enc=browser` duy nhất là "không thấy gom đệm" (0.352 s). Ngưỡng **không đổi**. Không cặp nào ≥ 2.5 s; `bunched_pairs = 0` ở cả ba lượt. Điều kiện dừng của PO ("không kết luận" lặp lại) đã đạt — dừng, chờ PO.

`boot_epoch` 1791128590.965 giữ nguyên từ 15:43:10Z tới ít nhất 16:27Z — gồm lượt vô hại trên runner lúc 16:11:03Z, `short-2` và `short-3`.

## 6. Lượt đo cuối trên runner — 2026-10-04 16:40:07Z đến 17:13:55Z (00:40–01:13 Hà Nội, 2026-10-05)

Phạm vi thu hẹp theo PO (2026-10-04): thang dài, chia đôi và ca ≥ 15 phút **không chạy — không quyết định nào cần**. Chạy một job trên runner `ubuntu-24.04` (Python 3.12.3, `Linux-6.17.0-1022-azure-x86_64-with-glibc2.39`): run `37217611319`, commit `b0dc3af`, `expect_commit` `8fdd1bb…` khớp (`kiểm_commit=True`), `commit_rtt` 0.804039 s. Chín lượt, `enc=none` trừ lượt 2. `boot_epoch` 1791128590.965 không đổi ở cả chín lượt (`restarted=False`). Không lượt nào gặp 429. Edge của mọi lượt: **IAD** (máy nhà: HKG). HTTP/1.1, TLS qua Cloudflare. Log của run: 1020 dòng; host 0, token 0, `onrender` 0 lần khớp; `BO19_SPIKE_BASE_URL` và `BO19_SPIKE_TOKEN` hiện `***` ở phần `env` của GitHub. Dữ liệu dựng lại từ các dòng `JOURNAL` và `RESULT_JSON` của log vào `tools/render-probes/out/s3-gha-final/` (gitignore).

### 6.1 SSE 10 phút, nhịp 5 s — A-050, điểm nhìn thứ hai

| | lượt 1, `enc=none` | lượt 2, `enc=browser` |
|---|---|---|
| Bắt đầu | 16:40:13.882Z | 16:50:15.016Z |
| Thời gian tới header / `open` | 0.777 s / 0.777318 s | 0.787 s / 0.786963 s |
| Event / chunk / cặp | 122 / 121 / 120 | 122 / 121 / 120 |
| `recv_gap` min / median / max | 4.987156 / 4.999955 / 5.012271 s | 4.994270 / 4.999994 / 5.005871 s |
| Lệch `abs(recv_gap − send_gap)` lớn nhất / median | **0.0064 s** / 0.0006 s | **0.0068 s** / 0.0005 s |
| Cặp lệch ≥ 0.5 s / ≥ 1.0 s / ≥ 2.5 s | 0 / 0 / 0 | 0 / 0 / 0 |
| `bunched_pairs` | 0 | 0 |
| `lag` first / median / last | 0.126619 / 0.124309 / 0.124451 s | 0.137000 / 0.135553 / 0.137238 s |
| Kết thúc | `end_event`, 600.776143 s | `end_event`, 600.789866 s |
| **Ngưỡng gốc** | **không thấy gom đệm** | **không thấy gom đệm** |
| **Tiêu chí phụ** | **không thấy gom đệm** | **không thấy gom đệm** |

Không `Content-Encoding` ở cả hai lượt (lượt 2 gửi `Accept-Encoding: gzip, deflate, br`) — như máy nhà.

### 6.2 SSE im lặng sau `open` — A-025, `enc=none`, `ladder: silent`

| Nấc `max` | Kết thúc | `elapsed` | Nhận được |
|---|---|---|---|
| 30 s | `end_event`, `completed` | 30.263275 s | `open` ở 0.264684 s; `end` ở 30.262827 s |
| 60 s | `end_event`, `completed` | 60.860251 s | `open` ở 0.861422 s; `end` ở 60.859511 s |
| 120 s | `end_event`, `completed` | 120.279688 s | `open` ở 0.278000 s; `end` ở 120.275868 s |
| **300 s** | **`error`, `TimeoutError`: "The read operation timed out"** | **390.331852 s** | **chỉ `open`** ở 0.259375 s; `since_last_data` 390.072 s |

Lượt 300 s bắt đầu 17:03:50.334Z. Probe đặt thời gian chờ đọc `max + 90 s` = 390 s: nó **thoát vì hết thời gian chờ**, không phải vì kết nối đóng — client không thấy FIN, không thấy reset, và event `end` (do máy chủ gửi khi hết 300 s) không bao giờ tới. Sau lượt, `/commit` trả 200, cùng commit, `boot_epoch` không đổi: **không phải restart**. Phân loại của probe: `cut`. Thang dừng ở nấc này (nấc cuối của thang). **Một lần quan sát**, một điểm nhìn (runner, edge IAD); không chạy lại (phạm vi thu hẹp). **Không biết thời điểm thật kết nối chết** — chỉ biết `end` ở 300 s không tới trong 390 s. Log Render của lượt này — các dòng `SPIKE_START` và `SPIKE_END` (`reason=client_gone`/`cancelled` hay `server_cap`, và `elapsed`) — cho biết máy chủ có thấy client đi hay không; **chưa có** (PO sẽ lấy).

### 6.3 `/sleep` — byte đầu chậm — A-025, `enc=none`, `ladder: sleep`

| `s` | Kết thúc | Header (byte đầu) tới sau | `elapsed` | Thân |
|---|---|---|---|---|
| 30 | `completed` | 30.274251 s | 30.274904 s | `slept: 30.0` |
| 60 | `completed` | 60.281730 s | 60.282261 s | `slept: 60.0` |
| 120 | `completed` | 120.265256 s | 120.265976 s | `slept: 120.0` |

Cả ba hoàn tất, byte đầu tới đúng hạn. Không đo nấc cao hơn — **không chạy, không quyết định nào cần**.

## 7. Điều đã đo và điều không đo

- **Đã đo (Web Service free, chuỗi client → Cloudflare → Render, HTTP/1.1):** stream có event mỗi 5 s sống đủ 600 s — **5/5 lượt** (ba từ máy nhà qua HKG, hai từ runner qua IAD). Im lặng sau `open`: 120 s sống, 300 s thì `end` không tới trong 390 s. Byte đầu chậm: tới 120 s đều hoàn tất. Không thấy gom đệm event nhỏ (~117 byte, mỗi 5 s) ở cả hai điểm nhìn; không nén `text/event-stream`.
- **Không đo:** HTTP/2 (trình duyệt); event lớn hơn; nấc `sleep` trên 120 s; nấc im lặng giữa 120 và 300 s; thời điểm thật của lần chết ở lượt 300 s; mọi ca ≥ 15 phút; gói trả phí. Không giá trị nào ở trên là "giới hạn thật" của Render.

## 8. Giả thuyết ngủ 15 phút — chưa kiểm, chuyển Sprint 4

Giả thuyết: Web Service free ngủ sau 15 phút **không có request vào, tính từ request cuối** (`docs/reference/render-free-tier.md`). Chưa rõ: một response hay stream **đang mở** có được tính là traffic không; ngưỡng thực tế có đúng 15 phút không.

Bốn mốc `boot_epoch` (bảng mục 1): 1791125091.522 (14:44:51Z), 1791127520.449 (15:25:20Z), 1791128590.965 (15:43:10Z), rồi **không đổi** ở 1791128590.965 qua mọi lần quan sát tới 17:14Z — gồm lượt vô hại lúc 16:11Z, `short-3` 16:17–16:27Z và job runner 16:40–17:14Z (traffic liên tục). Lần thức 15:43:10Z (lần gọi đầu mất 22.328715 s) xảy ra sau khoảng 9–10 phút kể từ dòng log cuối của `short-1` (≈ 15:33Z), chưa khớp 15 phút; chưa giải thích. Log Render quanh 21:40–22:50 Hà Nội (14:40–15:50Z) PO sẽ xem — **chưa nhận**. Lần gọi đầu sau khi ngủ mất ≈ 22 s: 22.478055 s ở S2, 22.328715 s ở S3. Ghi ở A-086 của `docs/design/ASSUMPTIONS.md`.
