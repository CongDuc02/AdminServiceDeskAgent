# ADR-015 — Chuyển `.docx` sang `.pdf` bằng LibreOffice headless trong image; một image cho mọi tiến trình

**Trạng thái:** Accepted · **Ngày:** 2026-09-13 · **Quyết định tại:** Phase 6 — Project Structure · **Liên quan:** A-018, A-024, A-031, A-032, A-058, A-059, D-009, ADR-001, ADR-003, ADR-005, ADR-013, mục Tool Registry của `03-agents.md`, mục Lưu trữ file và bất biến bản render của `04-data.md` · **Nguồn:** `docs/reference/libreoffice-headless-convert.md`, `docs/reference/render-deploys-docker.md`

---

## Context

Tool `pdf_export` phải chạy được trên Render (A-032). Nó chỉ có hai nơi gọi, đều trong `queue_worker`: `render_draft` và `finalize_issue` (mục Tool Registry của `03-agents.md`). `api` không bao giờ chuyển đổi file.

Ba ràng buộc đi kèm:

1. **Font thiếu là điểm hỏng im lặng.** Bộ chuyển đổi thay font và bố cục đổi mà không có mã lỗi nào. Tổ chức **không có ai** nghiệm thu thể thức (A-018, D-009), nên không có lớp chặn nào phía sau một văn bản đổi bố cục vì font.
2. **Nguồn không khẳng định PDF xuất ra tất định theo byte.** Trang tham số của LibreOffice không nói gì về metadata thời điểm tạo, producer hay định danh tài liệu (`docs/reference/libreoffice-headless-convert.md`). Thiết kế coi PDF là **không tất định** — giả định bi quan, không phải điều đã đo.
3. **Filesystem của Render không bền vững** (mục Ràng buộc nền tảng Render của `02-architecture.md`): file trung gian chỉ là file tạm.

## Options

**Công cụ chuyển đổi**

- **A — LibreOffice headless trong image của ứng dụng**, gọi như một tiến trình con từ module render của `tool_layer`.
- **B — LibreOffice đóng gói thành một private service riêng** trên Render, `queue_worker` gọi qua HTTP.
- **C — Dịch vụ chuyển đổi bên ngoài** (SaaS).
- **D — Dựng PDF bằng thư viện Python** từ bảng giá trị biến, không qua trình dàn trang `.docx`.

**Đóng gói:** (i) một image, nhiều lệnh khởi động · (ii) hai target build từ một Dockerfile ngay từ đầu.

**PDF không tất định:** (a) ép tất định bằng cách cố định metadata nguồn · (b) chấp nhận, và đặt điều kiện cho lease.

## Decision

**Chọn A + (i) + (b).**

### Chuyển đổi

- Mỗi lần chuyển đổi là một tiến trình `soffice` riêng: `--headless`, `--convert-to pdf`, `--outdir` là thư mục tạm của lần đó, `-env:UserInstallation` trỏ tới hồ sơ người dùng tạm **riêng cho lần đó**, cộng `--norestore` và `--nolockcheck` — mọi tham số có nguyên văn trong nguồn đã ghim. Hồ sơ riêng để hai lần chuyển đổi đồng thời không dùng chung trạng thái; hành vi khi dùng chung nằm ngoài nguồn.
- Timeout là timeout của lớp tool chuyển đổi file (A-031). Quá hạn thì giết tiến trình con, xoá thư mục tạm, trả `TIMEOUT`. Số lần chuyển đổi đồng thời trong một worker là cấu hình, `TBD` (A-031).
- Deploy bằng Docker trên Render. Nguồn nói Render "fully supports Docker-based deploys", và cron job dùng lệnh khởi động của image. Background Worker dựng từ Dockerfile là **suy ra** từ câu "Your services can…" — `[CẦN XÁC MINH]` bằng một lần tạo service thật.

### Manifest font — ba chốt chặn, không có "TBD trống"

- **Manifest đi kèm phiên bản template.** `template_version.required_fonts` — danh sách tên họ font mà phiên bản cần, là dữ liệu cấu hình bất biến như danh mục biến, không phải hằng số trong code (mục Bảng chi tiết của `04-data.md`, `manifest.required_fonts` ở mục Endpoint của `05-api.md`).
- **Chốt 1 — lúc tải lên:** mọi font mà file `.docx` khai dùng phải có trong `required_fonts`, và mọi font trong `required_fonts` phải có mặt trong image. Lệch thì trả `TEMPLATE_FONTS_INVALID`.
- **Chốt 2 — lúc kích hoạt:** kiểm lại vế "có mặt trong image". Phép kiểm này chạy trong `api` và **chỉ đúng vì `api` và `queue_worker` dùng chung image** — xem mục Đóng gói.
- **Chốt 3 — bước kiểm khởi động của `queue_worker`, fail-closed:** tập font cần là hợp của `required_fonts` trên **mọi phiên bản `ACTIVE`**, **cộng** mọi phiên bản mà một `document` chưa tới trạng thái kết thúc đang dùng. Vế sau cần vì `finalize_issue` render bản cuối bằng đúng phiên bản đã duyệt, và phiên bản đó có thể đã `RETIRED` từ lúc duyệt. Thiếu bất kỳ font nào thì **không khởi động**. Deploy đó hỏng, Render giữ bản trước (`docs/reference/render-deploys-docker.md`).
- "Có mặt" nghĩa là **khớp chính xác tên họ font** trong danh sách font đã cài của image — không phải "tìm được một font gần nhất". Công cụ liệt kê font và luật so khớp của nó `[CẦN XÁC MINH]`: chưa có tài liệu nào trong `docs/reference/`.
- Bộ font cụ thể và giấy phép phân phối trong image: A-058, owner Product Owner. **Không** ghi tên giấy phép, số phiên bản hay điều khoản phân phối của LibreOffice và của font nào từ trí nhớ.

**Chỗ hở còn lại, nói thẳng:** chốt 1 dựa vào việc liệt kê **đủ** font mà một file `.docx` khai dùng. File có nhiều nơi khai font — bảng font, theme, kiểu định dạng, từng đoạn chạy; cách liệt kê đầy đủ theo đặc tả OOXML `[CẦN XÁC MINH]`, đặc tả chưa có trong `docs/reference/`. Một font dùng mà không bị liệt kê thì lọt khỏi manifest, và chốt 2, chốt 3 không thấy nó. Ghi ở A-058.

### Đóng gói — một image

- **Một Dockerfile, một image, nhiều lệnh khởi động:** `api`, `worker`, mỗi cron job, và `migrate`. Nội dung đặc tả ở mục Dockerfile của `06-structure.md`.
- **Lý do:** đơn giản hơn, ít đường lệch phiên bản hơn, đủ cho Sprint đầu. **Không** dùng ADR-005 làm lý do: ADR-005 buộc `api` và `queue_worker` chạy cùng phiên bản code, và điều đó thoả được bằng cùng một commit, cùng một lần build — không buộc phải cùng một image.
- **Cái giá có thật:** LibreOffice và bộ font chỉ `queue_worker` cần, nhưng `api` cũng phải mang theo. Theo hệ quả B1 của ADR-013, `client` do `api` phục vụ tĩnh, nên **cold start của `api` chính là cold start của trang người dùng nhìn thấy**. Cold start của `api` với image có LibreOffice được đo ở chỗ quan sát của Phase 11 (dòng ADR-015 trong `_PLAN.md`). Chưa có ngưỡng, không bịa số.

### PDF không tất định — chọn (b)

- **Ca thường chịu được.** Giao thức ghi một lần ở mục Lưu trữ file và bất biến bản render của `04-data.md`: khoá đã có object thì dùng object và checksum của lần ghi đầu, bỏ chuỗi byte vừa render. Byte khác nhau giữa hai lần render không bao giờ tới `object_storage`.
- **Ca không chịu được:** lease hết hạn khi một lệnh upload đang bay. `object_claim_reconcile` xoá claim treo, một worker khác giành lại khoá, ghi và commit **một chuỗi byte khác**. Rồi lệnh upload cũ tới sau và đè lên — trong khi `document_render` trỏ tới commit của lần ghi thứ hai. Với byte tất định, lệnh ghi muộn sẽ ghi đúng chuỗi byte cũ và vô hại. Với byte không tất định, object lệch checksum.
- **Thứ tự bên trong một lần render, chốt ở đây:** chuyển đổi xong **rồi mới** giành khoá. Kiểm khoá đã có commit chưa → nếu chưa, chuyển đổi vào thư mục tạm → giành khoá → upload → commit. Nhờ vậy lease chỉ phải phủ **thời lượng upload**; thời lượng chuyển đổi nằm ngoài cửa sổ nguy hiểm, và một lần chuyển đổi chậm chỉ lãng phí công chứ không đè được gì.
- **Điều kiện:** lease phải **dài hơn hẳn phần đuôi** của phân phối thời lượng upload một bản render, **đo thật** trên image và nhà cung cấp `object_storage` thật. Số đo đó là A-059. Giá trị lease (A-031) phải đặt **từ** A-059, không đoán; chưa đo thì lease mang nhãn "chưa hiệu chỉnh", và A-031 đã chặn việc lên `PRODUCTION` khi còn nhãn đó.
- **Khi điều kiện vẫn thủng:** không im lặng. `render_integrity_check` đọc lại byte và so với checksum đã commit ngay trước người ký và ngay trước phát hành; lệch thì `halt_for_human`. Cơ chế ở tầng lưu trữ bắt buộc với nhà cung cấp (A-024) đóng hẳn cửa sổ này.

## Consequences

**Tích cực**

- Không bên thứ ba nào nhận file văn bản chứa dữ liệu `PER`/`RES`.
- Font thiếu không còn là hỏng im lặng ở ba thời điểm có kiểm soát: tải lên, kích hoạt, khởi động worker.
- Bất biến của bản đã ghim không phụ thuộc vào một tính chất byte chưa xác minh của bộ chuyển đổi.

**Tiêu cực và cái phải chấp nhận**

- Image lớn hơn; `api` cõng LibreOffice mà không dùng.
- **Thay thế tương thích số đo không phải là giống nhau.** Có những họ font được thiết kế trùng số đo với font thương mại phổ biến, nhưng giống số đo không có nghĩa là giống hình chữ, và không ai trong tổ chức nghiệm thu được sự khác biệt đó (A-018). Chọn font thay thế là quyết định của Product Owner ở A-058, không phải mặc định kỹ thuật.
- Bản PDF mà người duyệt thấy do LibreOffice dàn trang, còn người soạn template thấy file `.docx` trong trình soạn thảo của họ. Hai trình dàn trang có thể khác nhau. Người duyệt duyệt trên bản PDF — bản sẽ phát hành — nên sai khác hiện ra ở đúng chỗ có người nhìn, nhưng chỉ khi người đó để ý.

**Điều kiện đảo ngược**

- *Đóng gói — tín hiệu vận hành, đo ở `observability`:* cold start của `api` sau khi image có LibreOffice, đặt cạnh cold start của một image không có nó. Vượt ngưỡng — ngưỡng để trống tới khi có số đo — thì tách thành **hai target build từ một Dockerfile, một commit**. Bảo đảm cùng phiên bản của ADR-005 giữ nguyên.

  **Điều kiện đảo ngược này phá một chốt an toàn của chính ADR này — ghi ở đây để người tách image đọc được.** Tách image thì `api` không còn font để kiểm, và **chốt 2 mất**. Khi đó phép kiểm `FONT_MISSING` theo từng job trong `pdf_export` (mục Tool Registry của `03-agents.md`) chuyển từ lớp phòng thủ thêm thành **bắt buộc**: nó là chốt duy nhất còn bắt được một phiên bản template được kích hoạt sau khi worker đã khởi động. **Tách image mà không bật nó là hạ một lớp phòng thủ mà không ai quyết.** Việc tách vì vậy phải kèm, trong cùng thay đổi: bật `FONT_MISSING` theo từng job, và sửa phép kiểm `NOT_INSTALLED` của `activate` ở mục Endpoint của `05-api.md` — trong `api` nó không còn nghĩa.
- *PDF — tín hiệu vận hành:* phần đuôi thời lượng upload (A-059) tiến sát lease; hoặc `render_integrity_check` trượt với mã `RENDER_CHECKSUM_MISMATCH` ở một bản không có sự cố lưu trữ nào khác. Khi đó xét lại phương án (a).
- *Công cụ — tín hiệu vận hành:* bộ nhớ hay thời lượng chuyển đổi của worker tiến sát giới hạn của gói Render đang dùng. Khi đó xét phương án B để cô lập tiến trình chuyển đổi.

## Rejected alternatives

**B — Private service riêng.** Không sai; cô lập được bộ nhớ và sự cố của trình chuyển đổi. Loại cho Sprint đầu vì thêm một service phải deploy, giám sát và bảo vệ, đổi lấy một lợi ích — cô lập tài nguyên — mà chưa có số đo nào cho thấy cần (A-002). Giữ ở điều kiện đảo ngược.

**C — Dịch vụ chuyển đổi bên ngoài.** Loại vì file render chứa giá trị `HR_PROFILE` và biến nội dung tự do — dữ liệu `PER`/`RES`. Gửi nó đi là thêm một bên thứ ba vào data flow diagram của `02-architecture.md` chỉ để đổi định dạng file, với nghĩa vụ chuyển dữ liệu theo Nghị định 13/2023/NĐ-CP `[CẦN XÁC MINH]`.

**D — Dựng PDF bằng thư viện Python.** Loại vì bỏ qua file `.docx` — nơi duy nhất giữ khung thể thức (ADR-001). PDF dựng lại bố cục bằng code là một bản thể thức thứ hai, không ai kiểm, và sẽ lệch khỏi template ở chính những chỗ pháp luật quy định.

**Microsoft Word điều khiển tự động.** Loại vì cần môi trường Windows có Word; Render chạy container. Ghi để không ai dựng lại.

**(ii) — Hai target build ngay từ đầu.** Loại cho Sprint đầu vì hai image là hai đường lệch phiên bản phải canh, đổi lấy một cold start nhỏ hơn mà chưa ai đo. Giữ ở điều kiện đảo ngược.

**(a) — Ép tất định.** Loại vì hai lý do. (1) Nó dựa vào hành vi chưa xác minh: LibreOffice có tham số cố định metadata hay không, và nếu phải chuẩn hoá byte sau khi xuất thì bộ chuẩn hoá có tất định hay không — cả hai nằm ngoài `docs/reference/`. (2) Chuẩn hoá sau khi xuất nghĩa là mã của dự án viết lại byte của một văn bản hành chính ngay trước khi nó được ghim — thêm một đường có thể làm hỏng chính file mà người ký dựa vào. File `.docx` cũng có cùng câu hỏi về tính tất định. Giữ ở điều kiện đảo ngược.
