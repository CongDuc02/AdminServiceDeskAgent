# ADR-033 — Topology của giai đoạn build: local ba container theo topology production; Render free một Web Service chạy entrypoint gộp

**Trạng thái:** Accepted · **Ngày:** 2026-10-02 · **Duyệt:** PO, 2026-10-02 — đồng ý khuyến nghị F1 ở mục Cập nhật 2026-10-02 — Docker Desktop chạy được của `proposals/build-phase-free-tier-impact.md` · **Quyết định tại:** A-085, cổng 1.15 của `12-roadmap.md` — vế `worker` và Cron · **Liên quan:** ADR-004 (hàng đợi bằng bảng job), ADR-005 (orchestrator trong tiến trình), ADR-015 (một image), ADR-016 (lượt chat tách khỏi kết nối), ADR-022 (migrate qua CI), ADR-023 (môi trường khoá `operating_mode`), ADR-031 (object storage local), mục Entrypoint và deploy trên Render, mục Tắt tiến trình êm và mục Bước kiểm khởi động của `06-structure.md`, `docs/reference/render-free-tier.md`

---

## Context

PO, 2026-10-02: suốt giai đoạn build, Render và mọi dịch vụ khác chỉ dùng **gói free** (A-085).

Topology production đã chốt có ba loại tiến trình từ **một image** (ADR-015, mục Entrypoint và deploy trên Render của `06-structure.md`):

- `api_main` chạy trên Web Service;
- `worker_main` chạy trên Background Worker;
- mỗi thao tác của `cron_main` chạy trên một Cron Job.

Bốn sự thật quyết định lựa chọn — ba điều đầu theo `docs/reference/render-free-tier.md`:

1. **Gói free chỉ có Web Service, Postgres, Key Value và static site** — *"Other service types don't support Free instances."* Background Worker và Cron Job không có bản free. Đây là va chạm F1 của đề xuất.
2. **Web Service free ngủ sau 15 phút** không có traffic vào, mất khoảng một phút để thức, và có thể bị restart bất kỳ lúc nào.
3. **Instance free có 512 MB RAM** (`docs/reference/render-instance-compute.md`).
4. **Docker Desktop chạy được trên máy người triển khai** — kiểm ngày 2026-10-02. Local chạy được chính image Linux của Render.

## Options

- **A — Render: một Web Service free chạy cả ba vai** qua một entrypoint gộp.
- **B — Không lên Render trong giai đoạn build.** Toàn bộ chạy local trong Docker, ba container theo topology production.
- **C — `api` trên Render free; `worker` và cron chạy trên máy người triển khai**, nối vào Postgres free.
- **D — Container `worker` thành Web Service free thứ hai.**
- **E — Đánh thức và gọi cron từ một lịch bên ngoài** — ví dụ một workflow theo lịch của CI gọi một endpoint của `api`.
- **F — Trả phí cho Background Worker và Cron Job.**

## Decision

**Chọn A cho Render, cộng B cho local.** Hai nơi, hai topology, một image và một bộ code.

### 1. Local — track build hằng ngày: đúng topology production

Chạy trong Docker, mọi container dùng **cùng image** sẽ lên Render:

| Container | Lệnh | Tương ứng production |
|---|---|---|
| `api` | `python -m bo19.entrypoints.api_main` | Web Service |
| `worker` | `python -m bo19.entrypoints.worker_main` | Background Worker |
| `cron` | `python -m bo19.entrypoints.cron_scheduler_main` — mỗi lần tới lịch, chạy `cron_main <thao tác>` thành **một tiến trình con mới** | Mỗi thao tác một Cron Job — Render cũng chạy mỗi lần một tiến trình mới |
| `postgres` | Image PostgreSQL có extension `vector`. Tên image và bản major phải khớp Postgres của Render: `[CẦN XÁC MINH]` | Postgres free |
| `object_storage` | SeaweedFS 4.47 `weed server` — đúng cấu hình của ADR-031. Chạy trong container hay native đều được; chạy trong container thì phải chạy lại bộ phép thử của ADR-031 trên container trước khi dùng. Tên image `[CẦN XÁC MINH]` | Nhà cung cấp của A-024 |

- `migrate_main` **không** phải container chạy thường trực: chạy một lần trước khi các container khác khởi động, bằng credential `bo19_migrator` — đúng luật của ADR-017 và ADR-022.
- Cổng của mọi container chỉ publish ra `127.0.0.1`.
- File mô tả các container — Compose hay tương đương — là việc của BUILD MODE. DESIGN MODE không viết file chạy được.

### 2. Render free — từ Sprint 2: một Web Service chạy entrypoint gộp

- **Entrypoint mới `python -m bo19.entrypoints.combined_main`.** Trong **một** tiến trình, nó khởi động:
  - máy chủ của `api`;
  - vòng poll job của `worker`;
  - bộ hẹn giờ của `cron_scheduler_main`, gọi thẳng hàm của từng thao tác cron **trong tiến trình** — không sinh tiến trình con, để không tốn thêm RAM của 512 MB.
- **Không có nhánh mã riêng.** `combined_main` chỉ ghép các hàm khởi chạy sẵn có của ba entrypoint. Mọi logic nghiệp vụ, mọi tool, mọi job nằm đúng chỗ cũ. Lên gói trả phí là đổi Render sang ba loại service với ba lệnh cũ — không sửa code.
- **Chỉ chạy được ở `BO19_ENVIRONMENT = dev`.** `combined_main` từ chối khởi động ở `staging` hay `prod` — bước kiểm khởi động #18 mới. Topology gộp không bao giờ tới production do quên đổi lệnh.
- **Bước kiểm khởi động:** chạy **hợp** các bước của `api`, `worker` và cron — mọi bước có dấu ✔ ở bất kỳ cột nào của mục Bước kiểm khởi động của `06-structure.md` — cộng #18.
- **Một job một lúc, một lần chuyển đổi một lúc.** Vòng poll của `combined_main` chỉ giữ tối đa một job; LibreOffice chạy tối đa một lần chuyển đổi. Lý do: `api`, `worker` và LibreOffice chung 512 MB. Giá trị mang nhãn "chưa hiệu chỉnh" — A-031, số lần chuyển đổi đồng thời của một worker; S5 của Spike 1 đo bộ nhớ chuyển đổi **trên chính Web Service free**.
- **Ngủ và thức.** Khi service ngủ, vòng poll và bộ hẹn giờ dừng cùng tiến trình. Khi thức:
  - bước kiểm khởi động chạy lại;
  - vòng poll nhận tiếp các job đang `QUEUED`, và các job có lease đã hết;
  - bộ hẹn giờ chạy **mỗi thao tác cron một lần ngay khi khởi động**, rồi mới theo lịch.

  Bù được lần lỡ vì cả bảy thao tác cron đều chạy theo điều kiện "tới hạn" hay "cũ hơn N" so với mốc thời gian lưu trong DB (bản kê Cron Job ở `03-agents.md`). `needs_info_reminder` chỉ gửi nhắc muộn hơn, và vẫn idempotent theo (`request_id`, mốc).
- **Tắt tiến trình êm:** làm cả hai việc trong cùng shutdown delay:
  - việc của `api` — dừng nhận kết nối, drain lượt chat;
  - việc của `worker` — dừng giành job, trả job chưa xong về hàng đợi.

  Bộ hẹn giờ dừng ngay. Ràng buộc WV-01…WV-03 không đổi: hạn chót lượt cộng biên không dài hơn shutdown delay.

### 3. Một nguồn lịch cho cả ba nơi

Lịch của từng thao tác cron là **cấu hình**, đọc từ một nguồn duy nhất. `cron_scheduler_main` ở local và bộ hẹn giờ của `combined_main` đọc nó; khi lên gói trả phí, Render Cron Job được cấu hình từ chính nó. Giá trị lịch: A-031 — WV-13 cho `rate_limit_window_sweep`, các thao tác khác `TBD`.

## Consequences

**Tích cực**

- **Topology production được chạy mỗi ngày ở local.** Lỗi do tách tiến trình — ví dụ một job chỉ chạy đúng khi chung tiến trình với `api` — lộ ra trong giai đoạn build, không đợi tới lúc trả phí.
- **Render vẫn được thấy từ Sprint 2:** proxy, IP client (A-062), `SIGTERM`, ngủ và thức, cold start.
- **R1-3 thu hẹp thêm:** local chạy chính image Linux — font và `soffice` giống Render.
- **Đường lên gói trả phí là đổi cấu hình**, không sửa code.

**Tiêu cực và cái phải chấp nhận**

- **Topology trên Render khác production.** Những gì chỉ hỏng khi `api`, `worker` và cron chung tiến trình — tranh RAM, tranh CPU, một job dài làm chậm lượt chat — lộ ra trên Render mà không có ở production; và ngược lại. Local bù vế ngược lại.
- **Job và cron đứng khi service ngủ.** Trong giai đoạn build ít hại: job sinh ra từ thao tác của người đang dùng, nên service đang thức. Nhưng một job hỏng phải chờ backoff (`base` 10 giây trở lên) có thể rơi vào lúc service đã ngủ, và chỉ chạy tiếp khi có người truy cập.
- **512 MB chung cho `api`, `worker` và LibreOffice.** Chưa có số đo. S5 phải đo trên Web Service free; nếu không vừa thì Render free chỉ chạy được `api`, và phần render chỉ thử được ở local.
- **Một job một lúc** trên Render: hàng đợi chậm khi nhiều người thử cùng lúc. Chấp nhận ở quy mô thử.
- **A-032, vế "Background Worker dựng được từ Dockerfile", không thử được trên Render** cho tới khi trả phí. Local chạy `worker_main` trong container từ cùng image — gần nhất có thể.
- **Thêm hai entrypoint**: `combined_main`, `cron_scheduler_main`. `cron_scheduler_main` vẫn cần khi lên gói trả phí — ở local; trên Render thì Cron Job thay nó.

**Điều kiện đảo ngược**

- Lên gói trả phí → Render chuyển sang ba loại service với `api_main`, `worker_main`, `cron_main`; `combined_main` chỉ còn dùng ở `dev` nếu muốn, hoặc bỏ.
- S5 cho thấy `combined_main` không vừa 512 MB → Render free chỉ chạy `api_main`; `document_graph` chỉ thử ở local — tức B cho phần render, kèm ADR sửa.

## Rejected alternatives

**B một mình — không lên Render.** Mất mọi thứ chỉ Render mới có — proxy, IP client của A-062, `SIGTERM` thật, ngủ và thức — cho tới khi trả phí. Mục tiêu "lên Render `dev`" của Sprint 2 mất. Giữ B làm phần local của quyết định.

**C — `worker` và cron trên máy người triển khai, nối vào Render.** Một hệ thống đã deploy mà job phụ thuộc một máy cá nhân bật hay tắt: nhân viên gửi yêu cầu lúc máy tắt thì không có bản render, và không gì báo. Postgres free có nhận kết nối từ ngoài Render hay không cũng chưa xác minh (F11).

**D — `worker` thành Web Service free thứ hai.** Service đó ngủ sau 15 phút vì không có traffic vào, mà worker không nhận request nào. Hai service chạy liên tục vượt 750 giờ instance free mỗi workspace mỗi tháng. Web Service free không nhận traffic mạng riêng. Cron vẫn không có chỗ chạy.

**E — lịch bên ngoài gọi endpoint để đánh thức và chạy cron.** Thêm một endpoint ngoài `openapi.yaml` có quyền kích hoạt thao tác vận hành, kèm một secret mới, và một bên ngoài giữ service thức chỉ để lách giới hạn ngủ của gói free. Không cần: các thao tác cron bù được khi service thức (mục Decision).

**F — trả phí cho Background Worker và Cron Job.** Trái quyết định của PO (A-085).

## Open Questions

- Image PostgreSQL có `vector` cho local — **thu hẹp 2026-10-04:** Postgres free trên Render là **bản major 18** (PO). Docker Hub API cùng ngày có repo `pgvector/pgvector` với các tag `pg18`, `pg18-bookworm`, `pg18-trixie` và các tag ghim bản pgvector dạng `0.8.x-pg18`, mới nhất `0.8.7-pg18`. **Bản pgvector phải khớp bản Render cài** — **S0, 2026-10-04: Render là PostgreSQL 18.6, pgvector 0.8.1** (`docs/reference/render-postgres-s0.md`). Image local: **`pgvector/pgvector:0.8.1-pg18`** — tag có trên Docker Hub; ghim thêm digest khi viết file chạy container.
- Tên image SeaweedFS 4.47 nếu chạy trong container — `[CẦN XÁC MINH]`; chạy lại bộ phép thử của ADR-031 trên container.
- S5 của Spike 1 đổi đích: đo trên Web Service free bằng `combined_main`, không deploy Background Worker. `.claude/commands/spike.md` là file lệnh của PO — người triển khai không tự sửa; diff đề xuất ở báo cáo của lần sửa này.
- Các phần còn lại của cổng 1.15 — F3, F4, F5: một môi trường, chu kỳ dựng lại DB dưới 30 ngày, không backup — và F14: danh sách ngắn chỉ gồm gói free — vẫn chờ PO.
