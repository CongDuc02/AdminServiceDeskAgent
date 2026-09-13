# Render — deploy bằng Docker, pre-deploy command, tắt tiến trình êm

- **Nguồn:**
  - `https://render.com/docs/docker` — "Docker on Render"
  - `https://render.com/docs/deploys` — "Deploying on Render"
  - `https://render.com/docs/cronjobs` — "Cron Jobs"
  - `https://render.com/docs/background-workers` — "Background Workers"
- **Ngày lấy:** 2026-09-13, bằng `curl`. Văn bản HTML được tách thẻ; câu chữ giữ nguyên; `|` trong bản tách là ranh giới khối.
- **Phiên bản:** tài liệu của dịch vụ, không ghi số phiên bản. Ngày lấy là mốc duy nhất; Render có thể đổi hành vi sau ngày này.
- **Dùng cho:** ADR-015 (Docker), ADR-016 (SIGTERM, drain), ADR-017 (migration ở pre-deploy), mục Entrypoint của `06-structure.md`.

---

## Docker — `docs/docker`

> Render fully supports Docker-based deploys. Your services can:
> Pull and run a prebuilt image from a registry such as Docker Hub, or
> Build their own image at deploy time based on the Dockerfile in your project repo.

> Set the Language field to Docker (even if your application uses a language listed in the dropdown):
> If your Dockerfile is not in your repo's root directory, specify its path (e.g., my-subdirectory/Dockerfile) in the Dockerfile Path field:

> Note that you can't customize the command that Render uses to build your image.

> Every time a deploy is triggered for your service, Render uses BuildKit to generate an updated image based on your repo's Dockerfile.

## Lệnh khởi động với Docker — `docs/deploys`

> By default, Render runs the CMD defined in your Dockerfile. You can specify a different command in the Docker Command field on your service's Settings page.

## Cron job với Docker — `docs/cronjobs`

> This field is not present for Docker-based cron jobs.
> Instead, Render defaults to running your Docker image's startup command (as defined by ENTRYPOINT and/or CMD in your Dockerfile).
> You can override this by setting a custom Docker Command under Advanced in the creation flow.

> Cron jobs can't provision or access a persistent disk.

## Pre-deploy command — `docs/deploys`

> If defined, the pre-deploy command runs after your service's build finishes, but before that build is deployed. Recommended for tasks that should always precede a deploy but are not tied to building your code, such as:
> Database migrations
> Uploading assets to a CDN
> The pre-deploy command executes on a separate instance from your running service.

> The pre-deploy command is available for paid web services, private services, and background workers.
> If you don't define a pre-deploy command for a service, Render proceeds directly from the build command to the start command.

> If any command fails or times out, the entire deploy fails. Any remaining commands do not run. Your service continues running its most recent successful deploy (if any), with zero downtime.
> Command timeouts are as follows:
> Command | Timeout
> Build command | 120 minutes
> Pre-deploy command | 30 minutes
> Start command | 15 minutes

## Tắt tiến trình êm — `docs/deploys`

> For web services and private services, Render also updates its networking configuration so that your new instance begins receiving all incoming traffic:
> After 60 seconds, Render sends a SIGTERM signal to your app's process on the original instance.
> This signals your app to perform a graceful shutdown.
> If your app's process doesn't exit within its specified shutdown delay (default 30 seconds), Render sends a SIGKILL signal to force the process to terminate.

> As part of deploying your service to a new instance, Render triggers a shutdown of the current instance by sending your application a SIGTERM signal. Your application should define logic to perform a graceful shutdown in response to this signal.
> Common shutdown actions include:
> Responding to remaining in-flight HTTP requests
> Completing in-progress worker tasks (or marking them as failed so they're retried by other workers)
> Terminating outbound connections to external services
> Exiting with a zero status after other cleanup actions are complete
> If your service is still running after its configured shutdown delay (default 30 seconds), Render sends your application a SIGKILL signal. This terminates the application immediately with a non-zero status.

> If your service needs more than 30 seconds to complete a graceful shutdown, you can specify a longer shutdown delay (up to a maximum of 300 seconds) in one of the following ways:
> Call the Render API's Update service endpoint and set the maxShutdownDelaySeconds field to the desired value.
> Add the maxShutdownDelaySeconds field to your service's associated render.yaml configuration.

---

## Nguồn này **không** nói

- Trang Background Workers không có câu nào nói riêng về Docker; trang Docker nói "Your services can…" chung cho mọi service. Background Worker dựng từ Dockerfile được là **suy ra**, chưa có câu nguyên văn — `[CẦN XÁC MINH]` bằng một lần tạo service thật.
- Pre-deploy command chỉ có ở **gói trả phí** của web service, private service và background worker; không có ở cron job.
- Giới hạn thời gian của một request HTTP (A-025), việc gom đệm response dạng stream (A-050), trần kết nối PostgreSQL (A-057), phiên bản pgvector (A-037), quyền tạo role (A-040) — không có trong bốn trang này.
