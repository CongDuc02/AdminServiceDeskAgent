# ADR-031 — `object_storage` chạy local bằng SeaweedFS `weed server`, adapter luôn ghi có điều kiện

**Trạng thái:** Accepted · **Ngày:** 2026-09-27 · **Duyệt:** PO, 2026-09-27 — duyệt có điều kiện: xác định cổng `33646` và tắt được hay chặn được. Điều kiện đã đạt: cổng thuộc admin của `weed mini`, tắt bằng cách dùng `weed server` (mục Decision). Kèm quyết định A-084 · **Quyết định tại:** A-072 (cổng 1.4 của `12-roadmap.md`) · **Liên quan:** ADR-003 (interface S3-compatible, bất biến ở tầng ứng dụng), A-024 (nhà cung cấp thật, yêu cầu T2), A-059 (thời lượng upload), mục Lưu trữ file và bất biến bản render của `04-data.md`, mục Xác minh contract của `06-structure.md`, `docs/reference/object-storage-local-s3.md`

---

## Context

Sprint 1 chạy end-to-end trên máy local (quyết định PO, 2026-09-25). `object_storage` là dịch vụ S3-compatible ngoài Render (ADR-003), còn nhà cung cấp thật chưa chọn (A-024). A-072 đòi local có một sản phẩm nói giao thức S3, để `bo19.object_storage` chỉ có **một** adapter cho mọi môi trường.

Năm ràng buộc, theo thứ tự loại phương án:

1. **Một adapter.** Giao thức ghi một lần ở mục Lưu trữ file và bất biến bản render của `04-data.md` phải chạy trên đúng đường mã mà Render dùng. Nếu không, AC về bản render bất biến của Sprint 1 chứng minh sai đường — hệ quả (1) của A-072.
2. **Chạy native trên Windows.** Docker Desktop trên máy người triển khai không khởi động được (mục Xác minh contract của `06-structure.md`).
3. **Có ít nhất một cơ chế của yêu cầu T2** (A-024): ghi có điều kiện, khoá đối tượng hoặc versioning. Thiếu cả ba thì ca "lệnh ghi treo quá lease rồi đè" không có đường mã để thử ở local.
4. **Dữ liệu bền qua khởi động lại tiến trình.** Hành trình của AC-1.1 dừng ở `interrupt` chờ người duyệt, có khi hàng giờ, rồi resume từ checkpointer. Khoá object và checksum đã commit nằm ở `postgresql`. Object mất khi storage khởi động lại thì `render_integrity_check` dừng văn bản — một lỗi giả, do môi trường.
5. **Bắt buộc credential**, như môi trường thật. Adapter đọc credential theo cùng một cách ở mọi môi trường (mục Secret management trên Render của `09-security.md`).

## Options

- **A — SeaweedFS**, binary Windows, thư mục dữ liệu trên đĩa local. Thử bằng hai lệnh: `weed mini` và `weed server`.
- **B — `moto_server`**, thư viện giả lập dịch vụ của AWS cho Python.
- **C — `rclone serve s3`**, phục vụ một thư mục local qua giao thức S3.
- **D — MinIO**, bản community.
- **E — adapter ghi đĩa**, không qua giao thức S3.
- **F — bucket của một nhà cung cấp thật**, gọi từ máy local.

Sản phẩm chỉ phát hành dạng container bị ràng buộc 2 loại mà không cần thử. ADR này không liệt kê tên các sản phẩm đó, vì không kiểm chúng.

### Đã thử — 2026-09-27

Toàn bộ số liệu, trích dẫn và cách chạy nằm ở `docs/reference/object-storage-local-s3.md`. Tóm tắt:

| Ràng buộc | A — SeaweedFS 4.47 | B — moto 5.2.3 | C — rclone v1.75.1 | D — MinIO |
|---|---|---|---|---|
| 2 — native Windows | Đạt | Đạt | Đạt | **Không tải được**: `410 Gone`, dự án đã archived |
| 3 — ghi có điều kiện `If-None-Match: *` | Đạt: T2, T6 (8 lệnh ghi đồng thời, đúng 1 thắng), T10 | Đạt | **Trượt**: T2 bị đè; T6 báo 8/8 thành công trong khi log server ghi lỗi | — |
| 3 — versioning, khoá đối tượng | Đạt, kể cả gắn khoá sau khi ghi (T9) | Versioning đạt; gắn khoá sau khi ghi lỗi (T9) | Không có (`NotImplemented`) | — |
| 4 — bền qua `taskkill /F` | Đạt | **Trượt**: mất toàn bộ bucket | Không thử | — |
| 5 — credential | Đạt với `-s3.config` | Không thử | Không thử | — |
| Chỉ nghe trên `127.0.0.1` | `weed server`: đạt. `weed mini`: **trượt** — `33646` nghe mọi giao diện | Không thử | Không thử | — |

## Decision

**Chọn A — SeaweedFS bản 4.47, lệnh `weed server`, cho môi trường local.**

- **Ghim bản:** SeaweedFS **4.47**, file `windows_amd64.zip` của bản phát hành, sha256 ghi ở tài liệu tham chiếu. Đổi bản thì chạy lại bộ phép thử của tài liệu tham chiếu trước khi dùng.
- **Không vào image, không lên Render.** Chỉ là công cụ trên máy người triển khai. `dev`, `staging`, `prod` dùng nhà cung cấp của A-024.
- **Lệnh và cấu hình local** — đúng lệnh đã chạy ở mục Cổng 33646 là gì, và cách tắt của `docs/reference/object-storage-local-s3.md`:

  ```text
  weed server -dir=<thư mục cố định> -ip=127.0.0.1 -ip.bind=127.0.0.1 -filer -s3 -s3.config=<file identity> -master.telemetry=false -master.volumeSizeLimitMB=64 -volume.max=200
  ```

  - **`weed server`, không phải `weed mini`.** `weed mini` luôn chạy thành phần admin, và giữ cổng gRPC worker của admin (`33646`) trên **mọi giao diện**, bỏ qua `-ip.bind`. Không có cờ nào tắt được: `-admin.ui=false` chỉ tắt giao diện. `weed server` không có admin — lượt chạy thử không mở cổng nào ngoài `127.0.0.1`. Căn cứ mã nguồn và số đo: cùng mục của tài liệu tham chiếu.
  - `-ip=127.0.0.1 -ip.bind=127.0.0.1` — không bind ra mạng.
  - `-master.telemetry=false` — mặc định là **bật**, gửi thống kê ẩn danh tới máy chủ của SeaweedFS. Công cụ local của dự án không gửi gì ra ngoài.
  - `-s3.config=<file identity>` với đúng một identity cho `tool_layer`. File identity nằm ngoài repo, như mọi secret.
  - `-master.volumeSizeLimitMB=64 -volume.max=200` — thiếu hai cờ này thì từ bucket thứ hai trở đi `PUT` hỏng vì hết volume. Hai giá trị là chọn; dự án chỉ cần một bucket, còn bộ phép thử tạo nhiều bucket.
  - Thư mục dữ liệu cố định, không phải thư mục tạm.
- **Bucket local bật versioning.** Không bật khoá đối tượng khi chưa có quyết định của A-024. Lý do: khoá đối tượng chỉ bật được **lúc tạo bucket** (trích ở mục Khoá đối tượng — trang `S3-Object-Lock-and-Retention` của `docs/reference/object-storage-local-s3.md`), và thời hạn giữ gắn với A-010, chưa có giá trị. Local chỉ có dữ liệu giả, nên tạo lại bucket khi A-024 chọn khoá đối tượng là việc rẻ.
- **Luật của adapter, áp ở mọi môi trường — không riêng local:** **mọi** lệnh `PUT` lên `object_storage` mang `If-None-Match: *`. T8 cho thấy thiếu header thì cả ba sản phẩm đều để bị đè: bảo vệ nằm ở header mà adapter gửi, không ở sản phẩm.
- **Khi `PUT` nhận `412 PreconditionFailed` — quyết định của PO, A-084:** **không** trả job về hàng đợi. Người giữ claim đọc object đang có trên storage, tính checksum, so với checksum của đúng chuỗi byte mình vừa gửi:
  - **Khớp** → coi là ghi thành công. Đây là ca lần ghi trước của chính người giữ claim đã tới storage, còn response thì bị mất — lệnh `PUT` được gửi lại. Đi tiếp tới bước commit của giao thức ghi một lần.
  - **Lệch** → không commit, **dừng chờ tiếp quản**, khôi phục byte theo cơ chế tầng lưu trữ của A-024. Byte trên storage là của người khác — theo phân tích ở A-084, là lệnh ghi trễ của một claim cũ.
  - Checksum tính trên **byte đọc lại**, cùng cách tính với checksum mà bước commit ghi vào `stored_object_commit` — không dựa vào trường nào storage tự trả về.
- **Bộ phép thử thành kiểm contract ở BUILD MODE.** Script của tài liệu tham chiếu viết lại thành một kiểm trong `tools/contract-checks/`, chạy được trên mọi endpoint S3: local ở Sprint 1, và nhà cung cấp của A-024 trước cổng 2.5. Kết quả trên nhà cung cấp thật là căn cứ đóng yêu cầu T2 của A-024 — thay cho việc đọc tài liệu của nhà cung cấp.

## Consequences

**Tích cực**

- Giao thức ghi một lần — kể cả nhánh ghi có điều kiện — chạy trên đúng adapter của Render ngay từ Sprint 1. Hệ quả (1) của A-072 đóng cho local.
- Cả ba cơ chế của yêu cầu T2 có ở local. A-024 chọn cơ chế nào thì local dựng lại được.
- T10 cho thấy ghi có điều kiện khớp với đối soát `object_claim_reconcile` trên bucket có versioning: sau khi xoá, claim mới ghi lại được; lệnh ghi trễ của claim cũ bị từ chối.
- Không có credential trong repo; adapter dùng credential theo cùng một cách ở mọi môi trường.

**Tiêu cực và cái phải chấp nhận**

- **Nhánh "lệch" của 412 mở thêm một đường vào `halt_for_human`** ở chỗ trước đây chỉ có lỗi render. Tên mã lỗi của tool, dòng trong bảng mã lý do dừng, và câu chữ ở mục Lưu trữ file và bất biến bản render của `04-data.md` **chưa ghi** — PO giới hạn lần sửa này ở A-084 và ADR này. Mục Open Questions.
- **Local không phải nhà cung cấp thật.** Ngữ nghĩa ghi có điều kiện mới được chứng minh trên SeaweedFS 4.47, chưa trên nhà cung cấp của A-024 — hệ quả (2) của A-072 **vẫn còn** tới khi kiểm contract chạy trên nhà cung cấp đó (cổng 2.5).
- **`weed server` vẫn mở những cổng dự án không dùng** — trong lượt thử có `8181` và `9101`, trùng cổng mặc định của Iceberg và Lance mà `weed help mini` in ra. Tất cả ở `127.0.0.1`. Không tìm cách tắt từng cổng: chúng không ra khỏi máy.
- Binary tải về là biến thể "30GB" (`weed version`). Ý nghĩa của biến thể với dự án: không có, ở quy mô dữ liệu thử. Không kiểm thêm.
- Thêm một công cụ vào môi trường người triển khai. Giấy phép Apache-2.0 theo `LICENSE` ở tag 4.47. Công cụ không được phân phối trong image, nên nghĩa vụ phân phối không phát sinh.
- **Wiki của SeaweedFS không gắn phiên bản.** Kết luận của ADR dựa trên phép thử trên binary và mã nguồn ở tag `4.47`, không dựa trên wiki.
- **Các lượt thử `weed mini` hôm 2026-09-27 chạy với telemetry bật** — có thể đã gửi thống kê ẩn danh của cụm thử ra ngoài. Không có dữ liệu dự án trong đó; ghi ra cho đủ.

**Điều kiện đảo ngược**

- SeaweedFS ngừng phát hành bản Windows, hoặc dự án bị archived như MinIO → dùng bản đã ghim tới hết Sprint 2, rồi chọn lại theo cùng bộ phép thử.
- Một bản mới trượt bộ phép thử → giữ bản 4.47.
- Nhà cung cấp của A-024 có bộ giả lập local chạy native trên Windows và đạt bộ phép thử → xét thay, vì local gần môi trường thật hơn.

## Rejected alternatives

**`weed mini` — cùng sản phẩm, lệnh khác.** Loại vì cổng `33646`: bind mọi giao diện, không tắt được bằng cờ nào. Các phép thử T1–T10 của nó vẫn là căn cứ, vì kết quả trùng với `weed server`.

**B — `moto_server`.** Mất toàn bộ dữ liệu khi tiến trình dừng (ràng buộc 4): sau `taskkill /F` và khởi động lại, bucket trả `NoSuchBucket`. Gắn khoá đối tượng sau khi ghi (T9) lỗi ở cả hai lượt chạy. moto vẫn có thể có chỗ trong **test** ở BUILD MODE, nơi dữ liệu sống trong một phiên chạy. ADR này không quyết chuyện đó.

**C — `rclone serve s3`.** Trượt ràng buộc 3 ở chính cơ chế cần nhất: `PUT` kèm `If-None-Match: *` lên khoá đã có **vẫn đè** (T2). Với 8 lệnh ghi đồng thời, client nhận 8 lần HTTP 200, trong khi log server ghi lỗi `rename … Access is denied` (T6). Một storage báo thành công cho lệnh ghi hỏng thì làm hỏng đúng bước commit checksum của giao thức. Không có versioning (`NotImplemented`).

**D — MinIO.** Trang phân phối chính thức trả `410 Gone`, kèm thông báo rằng bản community đã archived, không còn bảo trì hay bản vá bảo mật, và mọi bản phát hành không còn được phục vụ. GitHub API xác nhận repo archived. Không có bản phân phối chính thức để ghim, không có bản vá.

**E — adapter ghi đĩa.** Trái ràng buộc 1: thêm một đường mã mà Render không dùng — đúng hệ quả (1) của A-072. Bất biến của Sprint 1 sẽ được chứng minh trên code không lên production.

**F — bucket của nhà cung cấp thật từ local.** Chọn bucket là chọn nhà cung cấp — giành trước quyết định của A-024, owner Product Owner. Sprint 1 là local theo quyết định PO. Mọi lần chạy thử của người triển khai còn phụ thuộc mạng và credential của môi trường ngoài.

## Open Questions

- ~~Áp quyết định A-084 vào các file khác~~ — **đã áp 2026-10-02** (PO duyệt): mục Lưu trữ file và bất biến bản render của `04-data.md`; mã nội bộ `STORAGE_WRITE_CONFLICT` của `docx_render`, `pdf_export` ở `03-agents.md`, `05-api.md`, `10-eval.md`; ánh xạ vào `reason_code` `RENDER_CHECKSUM_MISMATCH` sẵn có ở `08-hitl.md` — không thêm `reason_code`, không đổi DDL hay `openapi.yaml`.
- ~~Thao tác ghi không chạy trong graph~~ — **PO duyệt 2026-10-02**: trả lỗi, không commit, thành `INTERNAL_ERROR` ở `api`; `object_claim_reconcile` dọn.
- Không còn câu hỏi mở nào khác.
