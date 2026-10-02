# Đề xuất — giai đoạn build chỉ dùng gói free: va chạm với thiết kế, và phương án

**Trạng thái:** ✅ Đã quyết hết — F1: ADR-033 `Accepted`; F3, F4, F5, F14: PO đồng ý 2026-10-02. Đã áp vào `12-roadmap.md`, `11-ops.md`, `ASSUMPTIONS.md`, ADR-032 · **Ngày:** 2026-10-02 · **Người đề xuất:** người triển khai · **Nguồn:** quyết định của PO 2026-10-02 (A-085); `docs/reference/render-free-tier.md`; `docs/reference/render-deploys-docker.md`; `docs/reference/render-instance-compute.md`; mục Entrypoint và deploy trên Render của `06-structure.md`; mục Môi trường Render và mục Backup & Restore của `11-ops.md`; ADR-004, ADR-005, ADR-015, ADR-022, ADR-023

---

## 1. Ràng buộc

PO, 2026-10-02: **Render và các dịch vụ khác, nếu dùng, đều ở gói free trong suốt giai đoạn build.** Chưa lên gói trả phí.

Mọi giới hạn dưới đây trích từ `docs/reference/render-free-tier.md`, lấy cùng ngày. Không giới hạn nào ghi từ trí nhớ.

## 2. Va chạm

**Mức:** **Chặn** — thiết kế hiện tại không chạy được. **Đổi** — chạy được nhưng phải đổi kế hoạch hay runbook. **Ghi nhận** — không đổi gì, chỉ cần biết.

| # | Giới hạn của gói free — theo nguồn | Thiết kế đang dựa vào | Mức |
|---|---|---|---|
| F1 | Chỉ Web Service, Postgres, Key Value và static site có instance free: *"Other service types don't support Free instances."* | `worker_main` chạy trên **Background Worker**, mỗi thao tác cron là một **Cron Job** (mục Entrypoint và deploy trên Render của `06-structure.md`). S5 của Spike 1 deploy một Background Worker | **Chặn** — S5 của Sprint 1; mọi thứ chạy trên Render từ Sprint 2 |
| F2 | Web Service free **ngủ sau 15 phút** không có traffic vào, mất khoảng một phút để thức; *"Render might restart a Free web service at any time."* | Lượt chat chạy trong task của `api` (ADR-016); drain khi `SIGTERM` | **Đổi** — A-056 xảy ra thường hơn; người dùng có thể gặp trang chờ khoảng một phút; nếu worker và cron gộp vào `api` (phương án A ở mục 3) thì chúng đứng khi service ngủ |
| F3 | Postgres free **hết hạn sau 30 ngày**; 14 ngày ân hạn rồi bị xoá cùng dữ liệu | Checkpointer giữ thread nhiều giờ, nhiều ngày; dữ liệu `dev` sống suốt các sprint | **Đổi** — dựng lại DB theo chu kỳ dưới 30 ngày: `migrate_main`, data migration, seed. Mọi dữ liệu trên Render mất ở mỗi chu kỳ |
| F4 | **Chỉ một** Postgres free đang hoạt động cho mỗi workspace | Ba môi trường `dev`, `staging`, `prod` với DB riêng (mục Môi trường Render của `11-ops.md`); Sprint 4 chạy UAT trên `staging` | **Đổi** — trong giai đoạn build, Render chỉ có **một** môi trường |
| F5 | Postgres free *"don't support any form of backups"* | Mục Backup & Restore của `11-ops.md` | **Đổi** — không thử được backup và restore trên Render trong giai đoạn build |
| F6 | Postgres free cố định **1 GB** | Dữ liệu giả, checkpoint, embedding của kho quy trình thử | Ghi nhận — chưa có số đo dung lượng; theo dõi ở mỗi chu kỳ |
| F7 | Postgres free không có managed connection pooling | Pool phía ứng dụng (`pool.py`, mục Cây backend của `06-structure.md`) | Ghi nhận — không chạm |
| F8 | Instance free: 512 MB RAM (`docs/reference/render-instance-compute.md`) | `api` mang LibreOffice trong cùng image (ADR-015); `argon2id` | **Đổi** — WV-16 đã tính theo 512 MB. Nếu chuyển đổi PDF chạy trong cùng tiến trình với `api` (phương án A), LibreOffice và `api` chia nhau 512 MB — chưa có số đo; S5 đo |
| F9 | 750 giờ instance free mỗi workspace mỗi tháng; hết thì mọi Web Service free bị tạm dừng tới tháng sau | Một Web Service cho một môi trường | Ghi nhận — một service chạy liên tục nằm trong mức này; hai service thì không. Service ngủ không tính giờ |
| F10 | Render có thể tạm dừng Web Service free tạo *"uncommonly high volume"* traffic ra internet — ví dụ gọi API ngoài, truyền dữ liệu tới object storage ngoài | Gọi provider LLM (A-026), `object_storage` ngoài Render (ADR-003) | Ghi nhận — khối lượng của giai đoạn build nhỏ; ngưỡng không được nêu |
| F11 | Web Service free không có shell, không chạy one-off job; pre-deploy command chỉ cho gói trả phí (`docs/reference/render-deploys-docker.md`) | Migrate qua CI (ADR-022); thao tác vận hành seed bằng `bo19_migrator` | Ghi nhận — ADR-022 đã không dựa vào shell hay one-off. Thao tác seed chạy từ CI hoặc máy người triển khai; Postgres free có cho kết nối từ ngoài Render hay không: `[CẦN XÁC MINH]` — trang gói free không nói |
| F12 | Không persistent disk | `object_storage` ngoài Render (ADR-003) | Ghi nhận — không chạm |
| F13 | Chặn cổng ra 25, 465, 587 (SMTP) | Kênh chỉ là chat trên web, không email (mục Input của `01-prd.md`) | Ghi nhận — không chạm |
| F14 | "Các gói khác" — PO áp cùng ràng buộc | Provider LLM (A-026), embedding (A-028), object storage (A-024), CI (ADR-022) | **Đổi** — ứng viên phải có gói free. Gói free có đáp ứng yêu cầu bắt buộc hay không — điều khoản dữ liệu của LLM, cơ chế T2 của object storage — `[CẦN XÁC MINH]` từng ứng viên, theo bản gốc |

## 3. F1 — `worker` và Cron trên gói free: ba phương án

| | A — một Web Service free chạy cả ba vai | B — giai đoạn build không lên Render | C — `worker` và cron chạy ngoài Render |
|---|---|---|---|
| Cách làm | Thêm một entrypoint gộp: `api`, vòng poll job và một bộ hẹn giờ gọi các thao tác của `cron_main`, trong **một** tiến trình. Module của worker và cron giữ nguyên; chỉ entrypoint mới | Toàn bộ build chạy local. Render chỉ dùng cho những bước Spike chạy được trên Web Service và Postgres free | `api` trên Web Service free; `worker_main`, `cron_main` chạy trên máy người triển khai, nối vào Postgres free |
| Còn chạy "trên Render" ở Sprint 2–4 | Có | **Không** — mục tiêu "lên Render `dev`" của Sprint 2 mất | Một nửa |
| Khi service ngủ (F2) | Job và cron **đứng**; chạy tiếp khi có request đánh thức | — | Không ảnh hưởng worker; phụ thuộc máy người triển khai bật |
| RAM (F8) | `api` và LibreOffice chung 512 MB | — | Không chung |
| Đường mã ở production | Giữ: entrypoint riêng cho gói trả phí vẫn là `api_main`, `worker_main`, `cron_main` | Giữ | Giữ |
| Cần ADR mới | Có — topology của giai đoạn build | Có — đổi mục tiêu Sprint 2 | Có, và F11 `[CẦN XÁC MINH]` |

**Khuyến nghị: A, cho tới khi lên gói trả phí.** Lý do:

1. **Giữ mục tiêu chạy trên Render** của Sprint 2–4 — thứ B bỏ mất. Những gì chỉ lộ ra trên Render (proxy, SIGTERM, cold start, A-062) vẫn được thấy sớm.
2. **Job đứng khi ngủ ít hại trong giai đoạn build.** Trong thiết kế, job sinh ra từ thao tác của người đang dùng: `render_document` sau khi nhân viên gửi, `resume_document_graph` sau khi người duyệt bấm. Lúc đó service đang thức. Cron trong thiết kế quét theo mốc thời gian lưu trong DB — `expire_request`, `object_claim_reconcile`, `chat_session_idle_close`… — nên lần chạy sau khi thức **bù** được lần bỏ lỡ. **Cần kiểm lại từng cron theo điều này trước khi chốt** — chưa kiểm hết.
3. **Không đổi đường mã của production.** Entrypoint gộp chỉ gọi lại đúng các module đã có. Lên gói trả phí là đổi lệnh khởi động, không sửa code.

**Cái giá của A:** LibreOffice và `api` chung 512 MB — S5 phải đo bộ nhớ chuyển đổi trên chính Web Service free, không phải Background Worker. A **không** sửa được F3, F4, F5.

### 3.1 Cập nhật 2026-10-02 — Docker Desktop chạy được

Docker Desktop 4.85.0, engine 29.6.2 `linux/amd64` trên WSL2; `docker run --rm hello-world` đạt (kiểm 2026-10-02). **Image không phải vấn đề**: `api`, `worker`, `cron` vốn dùng chung một image (ADR-015). Vấn đề là gói free của Render không có loại service để chạy container `worker` và `cron`. Docker chạy được ở local đổi hai phương án:

- **C, dạng Docker** — container `worker` và `cron` chạy trên máy người triển khai, cùng image với Render, nối vào Postgres free. Giờ dựng được. Vẫn còn hai điểm yếu: job chỉ chạy khi máy bật — nhân viên gửi yêu cầu lúc máy tắt thì không có bản render; và Postgres free có cho kết nối từ ngoài Render hay không vẫn `[CẦN XÁC MINH]` (F11).
- **B, dạng Docker** — toàn bộ giai đoạn build chạy local trong Docker, **đúng topology production**: ba container từ một image, cộng PostgreSQL và SeaweedFS. Gần Render hơn nhiều so với chạy native (R1-3 thu hẹp), nhưng vẫn không thấy proxy, SIGTERM, ngủ khi rảnh của Render.
- **Biến thể đã cân nhắc — container `worker` thành Web Service free thứ hai.** Loại: service đó cũng ngủ sau 15 phút không có traffic vào, mà worker không nhận request nào; hai service chạy liên tục vượt 750 giờ mỗi workspace mỗi tháng; Web Service free không nhận traffic mạng riêng; và vẫn không có chỗ cho `cron`.

**Khuyến nghị sửa: A trên Render, cộng B dạng Docker ở local.**

- **Local — track build hằng ngày:** ba container từ một image, đúng topology production. Lỗi do tách tiến trình — ví dụ job chỉ chạy được khi chung tiến trình với `api` — lộ ra ở đây, trước khi lên gói trả phí.
- **Render free — từ Sprint 2:** một Web Service chạy entrypoint gộp (A), để thấy những gì chỉ Render mới có.

Như vậy entrypoint gộp chỉ dùng trên Render free; code và topology production được thử hằng ngày ở local. Bỏ C: một hệ thống đã deploy mà job phụ thuộc máy cá nhân bật hay tắt là điểm hỏng khó thấy.

## 4. F3, F4, F5 — một môi trường, DB sống tối đa 30 ngày, không backup

Đề xuất cho giai đoạn build:

- **Một môi trường Render duy nhất**, `BO19_ENVIRONMENT = dev`. `staging` của Sprint 4 chạy trên chính môi trường đó. Khoá `operating_mode` theo môi trường (ADR-023) không bị ảnh hưởng: suốt giai đoạn build hệ thống ở `NON_PRODUCTION`.
- **Chu kỳ dựng lại DB dưới 30 ngày**, theo một runbook: tạo DB free mới, `migrate_main`, data migration, seed. Gói free chỉ cho **một** DB hoạt động, nên phải bỏ DB cũ trước — có khoảng gián đoạn.
- **Buổi UAT của Sprint 4 phải nằm trọn trong vòng đời một DB.** Bằng chứng nghiệm thu — kết quả M1–M8, `audit_event`, bản render — phải được **xuất ra trước khi DB hết hạn**. Không có backup để lấy lại.
- **Backup & Restore của `11-ops.md` không được thử trên Render** cho tới khi lên gói trả phí. Ghi thành rủi ro chấp nhận ở mục Rủi ro chính của Sprint 4 nếu PO đồng ý.

## 5. Cần PO quyết

1. **F1:** chọn A, B hay C. Khuyến nghị đã sửa ở mục 3.1: A trên Render, cộng B dạng Docker ở local. Theo khuyến nghị thì người triển khai viết ADR-033 — topology của giai đoạn build.
2. **F4:** chấp nhận một môi trường Render duy nhất trong giai đoạn build.
3. **F3, F5:** chấp nhận chu kỳ dựng lại DB dưới 30 ngày, và xuất bằng chứng UAT trước khi DB hết hạn.
4. **F14:** danh sách ngắn của A-024, A-026 — và A-028 khi tới lúc — chỉ gồm ứng viên có gói free. Yêu cầu bắt buộc **không hạ**: gói free nào không đáp ứng thì không vào danh sách.

## 6. Nếu PO quyết — việc áp

- ADR-033 mới, nếu chọn A — có phương án bị loại.
- `06-structure.md`: mục Entrypoint và deploy trên Render thêm entrypoint gộp và điều kiện dùng nó.
- `12-roadmap.md`: S5 chạy trên Web Service; Sprint 2, Sprint 4 theo một môi trường; runbook dựng lại DB; rủi ro Backup & Restore.
- `.claude/commands/spike.md`: S5 không deploy Background Worker.
- `11-ops.md`: runbook dựng lại DB free; ghi chú Backup & Restore.
- `ASSUMPTIONS.md`: A-085 → `Đã chốt` cách xử lý; A-002, A-024, A-026, A-028, A-040, A-047 thêm ghi chú gói free.

## Open Questions

- Postgres free có cho kết nối từ ngoài Render không — cần cho thao tác seed và cho phương án C. `[CẦN XÁC MINH]` theo tài liệu của Render.
- Postgres free có cho tạo role và extension `vector` như A-040, A-047 cần không — S0 và S1 của Spike 1 trả lời, giờ phải chạy trên chính DB free.
- Shutdown delay có cấu hình được trên Web Service free không — WV-01 dùng mặc định 30 giây nên không phụ thuộc, nhưng chưa xác minh.
