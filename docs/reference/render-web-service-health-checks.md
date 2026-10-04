# Render — Web Service: health check, cổng, auto-deploy, kết nối Postgres nội bộ

- **Nguồn — lấy bằng `curl`, ngày 2026-10-04:**
  - `https://render.com/docs/health-checks` — sha256 `453f0f655a61703cf713a36b8908a1b32f417cb2b14aec108584df800ae31f2d`
  - `https://render.com/docs/web-services` — sha256 `a1f505671c12a7592a8db2341057bd9016473772c0916faa376c0f1de6410e2d`
  - `https://render.com/docs/deploys` — sha256 `1163bb9f58687aab0b704b21d74bb558a6a81499926bc63eab0049dde2ebb8f3`
  - `https://render.com/docs/postgresql-creating-connecting` — sha256 `e0db3a5b5b9628294a1d511b3963edcded2fece6658bb23a7a71ad10eaed1db7`
- **Cách tách:** như các tài liệu Render khác trong thư mục này; câu chữ giữ nguyên. Tài liệu sống — có thể đổi sau ngày lấy.
- **Dùng cho:** S2 của Spike 1; `BO19_DATABASE_URL` ở mục Biến môi trường theo môi trường của `docs/design/11-ops.md`; mục Bước kiểm khởi động của `docs/design/06-structure.md`.

---

## 1. Health check

> Every few seconds, Render sends health checks to each running web service and private service instance to confirm it's healthy and able to receive traffic:
>
> Health checks serve the following purposes:
>
> To identify unresponsive instances and automatically restart them
>
> To confirm when a newly deployed version of your service is ready to start receiving traffic
>
> Health checks only apply to web services and private services.
>
> These checks are specific to service types that receive incoming network traffic.
>
> By default, health checks are TCP socket probes to one of your service's open ports. For web services, this is usually the port of your public-facing HTTP server (default 10000).
>
> Web services can enable HTTP health checks to determine application-level readiness. Private services only support default TCP checks.
>
> ## HTTP health checks (web services only)
>
> Web services can receive health checks as HTTP GET requests to a path you specify:
>
> By defining a health check endpoint in your service, you can execute custom logic to verify instance health:
>
> To indicate a healthy instance, your endpoint can respond with any 2xx or 3xx status code.
>
> To indicate an unhealthy instance, your endpoint can respond with any 4xx or 5xx status code.
>
> If your service has any verified custom domains, Render sets one of those domains as the value of the Host header for all HTTP health checks. Otherwise, Render uses the service's onrender.com subdomain.

> How should my endpoint verify instance health?
>
> This varies from service to service. We recommend performing operation-critical checks, such as executing a simple database query to confirm connectivity.

> ## Success criteria
>
> For default TCP checks, Render considers a check successful if the instance accepts the attempted TCP connection within five seconds.
>
> For HTTP checks, Render considers a check successful if the instance responds with a 2xx or 3xx status code within five seconds.
>
> In all other cases, Render considers the check failed.
>
> ## Handling failures
>
> Render handles health check failures for new deploys and actively running services in different ways:

> Whenever you deploy a new version of your service, Render does not immediately start routing traffic to the new instances. Instead, Render starts sending them health checks:
>
> Whenever all of the new instances are passing their health checks at the same time, Render considers the deploy successful and starts routing traffic to the new instances.
>
> If this condition is not met within 15 minutes, Render cancels the deploy and continues routing traffic to your service's existing instances.
>
> In this case, Render notifies you according to your settings.

> If a running service instance fails consecutive health checks for 15 seconds, Render temporarily stops routing traffic to it to give it an opportunity to recover.
>
> If your service has other instances that are healthy, Render continues routing traffic to them.
>
> If an instance fails consecutive health checks for 60 seconds, Render automatically restarts the instance.

## 2. Cổng

> ## Port binding
>
> Every Render web service must bind to a port on host 0.0.0.0 to serve HTTP requests. Render forwards inbound requests to your web service at this port (it is not directly reachable via the public internet).
>
> We recommend binding your HTTP server to the port defined by the PORT environment variable. Here's a basic Express example:
>
> Adapted ever-so-slightly from here
>
> The default value of PORT is 10000 for all Render web services. You can override this value by setting the environment variable for your service in the Render Dashboard.
>
> If you bind your HTTP server to a different port, Render is usually able to detect and use it.
>
> If Render fails to detect a bound port, your web service's deploy fails and displays an error in your logs.
>
> The following ports are reserved by Render and cannot be used:
>
> 18012
>
> 18013
>
> 19099

## 3. Auto-deploy

> Auto-deploys require a connected Git provider. Services that use a prebuilt Docker image or a public Git repository URL must be deployed manually.
>
> ## Configuring auto-deploys
>
> Configure a service's auto-deploy behavior from its Settings page in the Render Dashboard:
>
> Under Auto-Deploy, select one of the following:
>
> Option
> Description
>
> On Commit
>
> Render triggers a deploy as soon as you push or merge a change to your linked branch.
>
> This is the default behavior for a new service.
>
> After CI Checks Pass
>
> With each change to your linked branch, Render triggers a deploy only after all of your repo's CI checks pass.
>
> For details, see Integrating with CI.
>
> Off
>
> Disables auto-deploys for the service.
>
> Choose this option if you only want to trigger deploys manually.

## 4. Lệnh của deploy hỏng

> If any command fails or times out, the entire deploy fails. Any remaining commands do not run. Your service continues running its most recent successful deploy (if any), with zero downtime.

## 5. Kết nối Postgres — URL nội bộ và ngoài

> An internal URL for connections from your other Render services hosted in the same region
>
> An external URL for connections from everything else

> ## Internal connections
>
> To use the internal URL, your connecting service and your database must belong to the same account and region.
>
> Wherever possible, connect to your database using its internal URL. Internal connection details are available on your database's Info page in the Render Dashboard:

> ## SSL modes for internal connections
>
> Internal connections optionally support TLS using self-signed certificates.
>
> Because these certificates are self-signed, internal connections do not support sslmode=verify-ca or sslmode=verify-full. To require TLS and prevent plaintext fallback, set sslmode=require.
>
> For more details on sslmode, see the PostgreSQL documentation.

## 6. Đọc cho BO-19

| Câu hỏi | Theo nguồn | Chưa nói |
|---|---|---|
| Deploy mới mà tiến trình chết lúc khởi động | Deploy chỉ thành công khi mọi instance mới qua health check cùng lúc; không đạt trong 15 phút thì Render **huỷ deploy và tiếp tục chuyển traffic tới instance đang chạy** | Tiến trình thoát mã khác 0 có bị tính hỏng ngay hay chờ hết 15 phút — S2 đo |
| Health check mặc định | TCP vào cổng; HTTP khi đặt đường dẫn; 2xx hoặc 3xx trong 5 giây | Gói free có HTTP health check không — S2 đo |
| Cổng | Bind `0.0.0.0`, theo biến `PORT`, mặc định 10000 | — |
| Auto-deploy | Cấu hình được là Off | — |
| URL nội bộ | Cùng account và region; TLS tự ký — `sslmode=require` được, `verify-ca`, `verify-full` không | — |
