# Render — giới hạn thời gian request, response dạng stream, đường đi của request

- **Nguồn — lấy bằng `curl`, ngày 2026-10-04** (tài liệu sống, không số phiên bản; Render có thể đổi sau ngày lấy):
  - `https://render.com/docs/web-services` — sha256 `d777f64f75d8b53e12c9213c27bb565dbfc05a9343d6f49ded7d2e22c80d9ba8` (khác sha của lần lấy sáng cùng ngày ở `render-web-service-health-checks.md` — trang động; câu chữ dưới đây chép từ bản này)
  - `https://render.com/docs/uptime-best-practices` — sha256 `8d30b5a1955c8677c25a064ec0f4eeef7610f0e90a330e3d7e62aeab2f1f0d48`
  - `https://render.com/docs/websocket` — sha256 `e11519d853ca5c753c582e0b19b2f10e3f7b77e16c2247a9759fe0009edcfef0`
  - `https://render.com/articles/real-time-ai-chat-websockets-infrastructure` — bài blog của Render, **không phải tài liệu**, đề ngày 13 tháng 1 năm 2026 — sha256 `5a89b18fe32e88cec2660e90ae27a2154588bb3c4059b8c4da65c50641fae332`
- **Trang đã lấy và đọc, không có gì về timeout request hay gom đệm response** (không chép):
  - `https://render.com/docs/faq` — `a7e4c0fd5e62af9f20d45686fa37b5974f3a8c562cf684f74d66e33a968f50d7`
  - `https://render.com/docs/outbound-connection-resets` — `c5f6022b48bdcde616682dd4a85ec9ad9889aa2cf74f5d933da5b7b40eaae8e7`
  - `https://render.com/docs/platform-features-by-plan` — `8244ce92986e1d72c0d6dcd6976048119e005d94cf69e3d6af68588d54f99c89`
  - `https://render.com/docs/troubleshooting-deploys` — `23bf60b8aaee055474056ea81caec29f00a4d11a4a23e570be1ce5914159e577` — chỉ có lời khuyên về `server.keepAliveTimeout` của Node và `gunicorn timeout`, thuộc về tiến trình của người dùng, không phải Render
  - `https://render.com/docs/service-types` — `e59ee4dbb45960c3f982c361941d2280426652810c19837a4297dee5420a3d10`
  - `https://render.com/docs/web-service-caching` — `c47fb8cba34e108faa9a9db833637d50706c527662ea96d7a1d7e3ff6bcec32c`
  - `https://render.com/docs/free` — đã có ở `render-free-tier.md`, không lấy lại
- **Danh mục trang dùng để tìm:** `https://render.com/docs/sitemap.xml` — `a315f90a70277543366087ab5b0f23c8dbd4be23851c9f00f94b932ed1932804`; `https://render.com/docs/llms.txt` — `f42b05c9b130864315ee27b6d6a4ccbe4873533bc90af9277c8fa3a03fc39c4e`. Không có trang riêng về "request timeout", "streaming" hay "proxy" trong danh mục.
- **Cách tách:** như các tài liệu Render khác trong thư mục này — bỏ thẻ HTML, giữ câu chữ nguyên văn.
- **Dùng cho:** S3 của Spike 1 — A-025 (giới hạn thời gian request), A-050 (proxy gom đệm response dạng stream).

---

## 1. Tài liệu chính thức — những gì có nói

**`web-services` — đường đi của request vào:**

> Render's load balancer terminates SSL for inbound HTTPS requests, then forwards those requests to your web service over HTTP. If an inbound request uses HTTP, Render first redirects it to HTTPS and then terminates SSL for it.

Danh sách "Additional features" của cùng trang gồm: `WebSocket connections`, `HTTP/2`, `DDoS protection`, `Brotli compression`. Trang **không** nói Brotli hay HTTP/2 áp cho response nào, hay áp thế nào với `text/event-stream`.

**`uptime-best-practices` — mọi request vào đều qua Cloudflare:**

> All inbound requests to Render web services pass through Cloudflare for DDoS protection:
> Cloudflare assigns a unique ID to each request and sets it as the value of the CF-Ray HTTP header. Render includes this header in the request it sends along to your service.

> If you maintain long-lived connections to your service (such as over WebSocket), make sure to implement retry logic for those connections. Render routes each connection to a particular instance of your service running on a particular machine, and Render might replace an instance at any time as part of a deploy or standard maintenance.
> Replacing an instance this way is a zero-downtime event, but terminating the old instance does by necessity terminate all connections to it.

**`websocket` — chỉ nói về WebSocket, không về HTTP stream thường:**

> Render does not enforce a maximum duration for WebSocket connections. However, a variety of factors can cause a connection to be interrupted (instance shutdowns, network issues, platform maintenance, and so on).

> As part of shutting down an instance, Render sends it a SIGTERM signal and gives it a 30-second window to shut down gracefully. You can extend this window to a maximum of 300 seconds by setting a shutdown delay.

## 2. Bài blog của Render — nguồn thứ cấp, không dùng để đóng giả định

Bài "Building Real-Time AI Chat: Infrastructure for WebSockets, LLM Streaming, and Session Management", đề ngày 13 tháng 1 năm 2026:

> Render offers out-of-the-box infrastructure designed for AI workloads, including persistent services for stateful WebSockets, extended request timeouts to support long-running LLM streams, …

Một bảng trong bài ghi cột `Maximum request duration` của Render là **`100 minutes`**, và một đoạn văn:

> Render web services are built for this reality, providing a generous 100-minute maximum request duration. This isn't a brief inactivity window. It's a high ceiling for the total connection lifetime.

Bài **không** nói con số này áp cho gói nào, **không** có trong tài liệu docs nào đã lấy, và là bài tiếp thị so sánh với nền tảng khác. Ghi lại để S3 có thứ đối chiếu; **không** coi là nguồn của A-025.

## 3. Nguồn này **không** nói

| Câu hỏi | Theo nguồn |
|---|---|
| Giới hạn thời gian một request HTTP của Web Service (A-025) | **Không có** trong tài liệu docs đã lấy. Chỉ có con số của bài blog ở mục 2 — không phải tài liệu, không nói gói nào |
| Có giới hạn thời gian im lặng (idle) trên một response đang mở không | **Không có** |
| Proxy có gom đệm response `text/event-stream` không (A-050) | **Không có** |
| `Content-Encoding` áp thế nào lên response dạng stream (Brotli, gzip) | **Không có** — chỉ có tên "Brotli compression" trong danh sách tính năng |
| Gói free có khác gói trả phí về các giới hạn trên không | **Không có** — trừ việc ngủ sau 15 phút không có traffic vào (`render-free-tier.md`) |
| Việc Cloudflare đứng trước có tự thêm giới hạn riêng không | **Không có** — chỉ nói request đi qua Cloudflare để chống DDoS |

Hệ quả: A-025 và A-050 chỉ đóng được bằng phép đo ở S3. Kết quả đo là của **Web Service free** — không suy ra cho gói trả phí.
