# Render — hạn chờ service mở cổng khi deploy/khởi động

- **Nguồn — lấy bằng `curl`, ngày 2026-10-20** (trích dòng nguyên văn từ bản tải về; bản HTML gốc không vào repo, chỉ sha256 và bản chữ trong `render-docs-raw/*-20261020.txt`):
  - `https://render.com/docs/web-services` — sha256 `814f53a0649437a7455c6497a0b1ab208af54a3c6ce271dd942f6c6c6c60d833`
  - `https://render.com/docs/troubleshooting-deploys` — sha256 `2751064c95283165b65bd15a4c38f83c7fcf163ec043e4da1d07bcf4881659e3`
  - `https://render.com/docs/deploys` — sha256 `9f228f0e92643abf4f7858a33a0bf2a0eacbcf6d1a6d2378d762c79d1dc1b4c6`
  - `https://render.com/docs/health-checks` — sha256 `45ca28643f0fcbef066367e2b5da4e4f8ded791582ef6b404e60ebdea447a706`
- **Dùng cho:** rủi ro "khởi động 45–79 s ở 0,1 CPU" của B9a2 (PO 2026-10-20), cổng 4.9 và R4-4 của `docs/design/12-roadmap.md`. Tài liệu sống — có thể đổi sau ngày lấy.

## Điều tài liệu NÓI

> If Render fails to detect a bound port, your web service's deploy fails and displays an error in your logs. *(web-services)*

> **Port scan timeout reached** — Render failed to detect at least one open port on your service's host before its scan timed out. This error is specific to web services and private services. *(troubleshooting-deploys)*

> Render's port scan timed out before your service started listening on a port. Keep your start command simple and defer any non-essential work until after your server starts listening. Make sure to bind your host and port as early as possible in your application code. *(troubleshooting-deploys)*

> **Timed out** — Your instance was not ready before the deploy timed out. Common causes include: Slow or blocking database queries or third-party API calls. Slow or failing custom health checks. CPU exhaustion, which can slow your service's startup. *(troubleshooting-deploys)*

> If any command fails or times out, the entire deploy fails. … Command timeouts are as follows: Build command 120 minutes · Pre-deploy command 30 minutes · **Start command 15 minutes**. *(deploys)*

> Whenever all of the new instances are passing their health checks at the same time, Render considers the deploy successful … **If this condition is not met within 15 minutes, Render cancels the deploy** and continues routing traffic to your service's existing instances. *(health-checks)*

> For HTTP checks, Render considers a check successful if the instance responds with a 2xx or 3xx status code within five seconds. *(health-checks)*

## Điều tài liệu KHÔNG nói

**Không có con số nào cho "port scan timeout".** Tài liệu chỉ nêu hai hạn **15 phút**: lệnh khởi động (Start command) và cửa sổ để instance mới qua health check. Hạn quét cổng không được công bố bằng giây hay phút.

## Quan sát trong dự án (không phải tài liệu Render)

- **S4, 2026-10-05** (`render-s4-nhat-ky-do.md`, mục Sự kiện deploy): một deploy báo `Port scan timeout reached, no open ports detected` — **Timed out** lúc 12:12, bấm lúc 11:54 (18 phút, gồm cả dựng image). Nguyên nhân khi đó không biết.
- **2026-10-16:** khi `api_main` thoát ở bước kiểm #1, log Render in `No open ports detected, continuing to scan...` ≈ 32 s sau lúc tiến trình thoát — việc quét cổng chạy liên tục trong lúc instance còn sống.

## Biên so với khởi động đo được ở B9a2

| | Giây |
|---|---|
| Khởi động `combined_main` ở 0,1 CPU, **lớn nhất đo được** (`/healthz`; image "sau", lần chạy xen kẽ thứ hai; cùng một image dao động 44,9–78,8 s; ba lần trên mã có ghim CPU: 39,7–47,0 s) | **78,8** |
| Khởi động khi ghim một CPU: thử nghiệm `--cpuset-cpus` / bằng mã (WV-34) | 38,8–43,8 / 39,7–47,0 |
| Hạn đã công bố gần nhất (Start command; cửa sổ health check) | 900 (15 phút) |
| **Biên so với 78,8 s theo hạn đã công bố** | **821 s ≈ 11,4 lần** |

Kết luận: so với các hạn **đã công bố** thì không sát (≈ 11 lần). Điều **chưa biết** là hạn quét cổng thật — có thể ngắn hơn 15 phút; quan sát S4 (18 phút từ lúc bấm, gồm dựng image) không cho thấy nó ngắn hơn vài phút. Cộng thêm: số 78,8 s là Docker Desktop, không gồm thời gian kéo image và khởi động container trên Render. Số quyết định là log Render lúc chuyển sang `combined_main` (đo thời gian từ lúc khởi động tới lúc có cổng).

## Phương án nếu sát (CHƯA áp — đề xuất)

1. **Mở cổng trước, chạy bước kiểm nặng sau:** bind `0.0.0.0:$PORT` ngay đầu tiến trình với một listener tối thiểu trả `503` cho mọi đường dẫn (kể cả `/healthz`, `{"status":"starting"}`), rồi chạy bước kiểm khởi động, dựng pool và app, và chuyển sang app thật. Đúng lời khuyên "bind your host and port as early as possible". Giữ nguyên nguyên tắc "không phục vụ request nào trước khi bước kiểm đạt" (mục Bước kiểm khởi động của `06-structure.md`) vì listener tạm không phục vụ gì ngoài `503`; bước kiểm trượt vẫn thoát mã 1. Cần quyết định với `healthz` health check của Render: trả `503` trong lúc khởi động có nghĩa instance chưa qua health check (đúng).
2. **Giảm khởi động:** nạp chậm các module nặng (`langgraph`, `docx`…) hoặc tách bước kiểm không cần DB — đo ở 0,1 CPU trước (phần lớn 40+ s là import Python).
3. **Ghim CPU** (WV-34, đã làm) cũng làm khởi động ổn định ≈ 40–47 s (so với 45–79 s) — số đo bằng mã thật ở `combined-main-b9a2.md`.
