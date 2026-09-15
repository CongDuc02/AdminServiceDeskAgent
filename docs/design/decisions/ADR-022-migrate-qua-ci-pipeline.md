# ADR-022 — Migrate qua CI pipeline, không qua thao tác one-off của Render

**Trạng thái:** Accepted · **Ngày:** 2026-09-15 · **Quyết định tại:** Phase 11 — Ops, Cost & Deployment · **Liên quan:** ADR-017, A-060, mục Secret management trên Render của `09-security.md`, mục Migration và checkpointer của `06-structure.md`

---

## Context

ADR-017 đã chốt: migration chạy bằng `bo19_migrator`, một role không được nằm trong biến môi trường của bất kỳ service runtime nào (`api`, `queue_worker`) — nếu không, mọi bất biến bằng `GRANT`/`REVOKE` ở mục Nguyên tắc dữ liệu của `04-data.md` chỉ còn là chữ. Cái ADR-017 chưa trả lời — và A-060 để ngỏ — là **ngữ cảnh cụ thể** nơi bước `migrate` (`python -m bo19.entrypoints.migrate_main`) thực thi. Phase 9 thêm một ràng buộc (mục Secret management trên Render của `09-security.md`) nhưng không tự chọn, vì cần đọc tài liệu Render về phạm vi biến môi trường theo dịch vụ trước — nguồn đã ghim (`docs/reference/render-deploys-docker.md`) chỉ nói pre-deploy command "executes on a separate instance", không nói gì về phạm vi biến môi trường của instance đó.

## Options

- **A — CI pipeline.** Một bước riêng trong pipeline CI/CD (ví dụ GitHub Actions), chạy trước khi trigger deploy Render. Credential `bo19_migrator` là secret của CI, không bao giờ chạm tới Render.
- **B — Render one-off Job/Shell.** Dùng tính năng chạy lệnh một lần của Render (Job, hoặc Shell trên Web Service) để chạy `migrate_main`.

## Decision

**Chọn A.**

1. **Phạm vi biến môi trường của cơ chế one-off trên Render — `[CẦN XÁC MINH]`, chưa xác minh được (A-060 gốc).** Nguồn đã ghim không nói rõ một Job/Shell one-off có dùng chung biến môi trường với service gốc hay không. Chọn B trước khi biết điều này là đặt cược đúng thứ ADR-017 dựng lên để tránh: nếu Job one-off dùng chung biến môi trường với Web Service, credential `bo19_migrator` coi như đã nằm trong biến môi trường của `api` — vi phạm trực tiếp ràng buộc mà Phase 9 đặt ra.
2. **CI pipeline tách credential khỏi Render tuyệt đối, không phụ thuộc hành vi chưa xác minh của Render.** Secret `bo19_migrator` sống trong secret store của CI (ví dụ GitHub Actions Secrets), không bao giờ được Render nhìn thấy dưới bất kỳ hình thức nào — kể cả gián tiếp qua biến môi trường dùng chung của một tính năng one-off.
3. **Thứ tự tự nhiên khớp với quy trình đã có.** Migration phải chạy **trước** khi tiến trình runtime mới khởi động với schema mới (mục Migration của `11-ops.md`) — một bước CI chạy trước khi trigger deploy diễn đạt đúng thứ tự đó bằng cấu trúc pipeline, không cần thêm cơ chế chờ/khoá nào giữa hai bước.
4. **`tools/contract-checks/` đã có sẵn hai chế độ cho đúng mô hình này** (mục Chạy lại của `06-structure.md`): `--local` cho CI, `--app-dsn` cho kiểm tra sau khi migrate — không cần công cụ mới.

**Điều kiện đi kèm quyết định:**

- CI có quyền trigger deploy Render (qua API deploy hook hoặc tương đương) **chỉ sau khi** cả migration và `tools/contract-checks/ --app-dsn` đều đạt — hai bước này là **gate**, không phải bước song song.
- Secret `bo19_migrator` không bao giờ ghi vào log CI, artifact build, hay biến môi trường truyền cho bước build image — chỉ bước migrate mới đọc nó.
- Migration chạy **một lần cho mỗi môi trường** (`dev`/`staging`/`prod`) mà pipeline đang nhắm tới — ba database riêng, ba lần chạy độc lập, không migration nào chạy chéo môi trường.

## Consequences

**Tích cực**

- Đáp ứng ràng buộc Phase 9 mà không cần biết trước hành vi chưa xác minh của Render (A-060 gốc) — quyết định đứng được bất kể câu trả lời của A-060 gốc là gì.
- Không thêm phụ thuộc hạ tầng mới: hầu hết pipeline CI đã có sẵn secret store và khả năng chạy một bước tuần tự trước khi trigger dịch vụ khác.
- Nhất quán với `tools/contract-checks/` đã thiết kế sẵn hai chế độ cho đúng mô hình "kiểm ở CI, xác nhận lại trên môi trường đích".

**Tiêu cực và cái phải chấp nhận**

- CI trở thành một **ranh giới tin cậy mới**, ngang hàng với credential `bo19_migrator` chính nó — quyền truy cập vào secret store của CI phải được quản lý chặt, ngoài phạm vi DESIGN MODE (thuộc người triển khai).
- Deploy phụ thuộc CI khả dụng — nếu CI down, không migrate được, nên không deploy được. Đây là đánh đổi chấp nhận được: cùng loại phụ thuộc mọi pipeline CI/CD hiện đại đã có.
- A-060 gốc (phạm vi biến môi trường của cơ chế one-off Render) **không còn cần xác minh** để deploy được — nhưng câu hỏi tự nó không biến mất khỏi việc tìm hiểu Render nói chung; chỉ là thiết kế không còn phụ thuộc câu trả lời của nó.

## Rejected alternatives

**B — Render one-off Job/Shell.** Gọn hơn về mặt hạ tầng (không cần CI pipeline riêng nếu tổ chức chưa có), nhưng đặt cược vào một hành vi Render chưa xác minh đúng vào chỗ nhạy cảm nhất của thiết kế bảo mật (ranh giới credential `bo19_migrator`/`bo19_app`). Nếu A-060 gốc sau này được xác minh là "an toàn" (one-off không dùng chung biến môi trường), phương án B vẫn có thể được cân nhắc lại như một tối ưu vận hành — nhưng đó là một quyết định mới, cần ADR riêng, không phải đảo ADR này.
