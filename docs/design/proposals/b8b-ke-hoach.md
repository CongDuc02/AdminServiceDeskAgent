# Kế hoạch B8b — `lease_id` cho job, rồi `rendering`, `stored_file_fetch`, image có `soffice` và font

**Trạng thái:** ⏳ **Chờ PO duyệt** · **Ngày:** 2026-10-13 · **Người đề xuất:** người triển khai · **Nhánh dự kiến:** `build/b8b-lease-id-rendering` (đã tách từ `main` sau merge B8a; chỉ có tài liệu cho tới khi duyệt) · **Thứ tự:** mục 4.7 của `12-roadmap.md` (risk-first) · **Điều kiện cổng:** cổng 1.6 đạt cho giai đoạn thử nghiệm (ADR-036) · **Đã đọc:** ADR-001, 003, 004, 014, 015, 031, 036, 037; `03-agents.md` mục Tool Registry (`docx_render`, `pdf_export`, `render_integrity_check`) và 5.6; `04-data.md` mục Vận hành, Lưu trữ file và bất biến bản render; `05-api.md` mục Tải file và Mã lỗi; `06-structure.md` cây `rendering/`, đặc tả `Dockerfile`, bước kiểm #6/#7; `11-ops.md` mục Retry; `backend/migrations/schema/0001_initial.sql` (`job`, `template_version`, `template_variable`, `document_render`)

## 1. Mục tiêu và vì sao đứng ở đây

PO, 2026-10-13: hàng rào lease bằng `locked_at` mong manh (đồng hồ lùi khi NTP chỉnh; hai lần giành cùng mốc thời gian). Sửa **trước khi B9a có handler đầu tiên**, vì từ B9a trở đi một lệnh ghi muộn của worker đã mất lease là lệnh ghi thật. Sau đó là rủi ro lớn kế tiếp của track build: **`soffice` và font trong image thật**, kèm đường tải file. Khi xong, B9a có đủ nền (`jobs`, `numbering`, `storage`, `rendering`) để viết `document_graph` mà không còn ẩn số hạ tầng.

## 2. Việc đầu tiên: `job.lease_id` (PO, 2026-10-13)

| Hạng mục | Nội dung |
|---|---|
| Migration `0013` | `job.lease_id uuid`; **bỏ** `ck_job_running_has_lease` cũ, thay bằng ràng buộc `RUNNING` ⇔ `locked_at`, `lease_expires_at`, `lease_id` cùng có mặt. Hàng `RUNNING` sẵn có (nếu có) được gán `gen_random_uuid()` trong cùng migration. Quyền cột của `bo19_app` trên `job` thêm `lease_id`; `check_grants.py` phải Lệch 0 |
| `claim` | Sinh `lease_id` ngẫu nhiên **ở DB** (`gen_random_uuid()`) mỗi lần giành, trả về trong `ClaimedJob` |
| `heartbeat`, `succeed`, `fail`, `release` | `WHERE id = … AND status = 'RUNNING' AND lease_id = <token>`. **Không** kiểm `locked_at`; `locked_by` giữ để chẩn đoán, không tham gia hàng rào. Mọi lối thoát khỏi `RUNNING` (`succeed`, `fail`, `release`, `reclaim_expired`) đặt `lease_id = NULL` |
| `reclaim_expired` | Giữ nguyên nghĩa (một lượt thử); đặt `lease_id` về `NULL` |
| Test | (1) giành → `release` → giành lại: token cũ bị từ chối ở **cả bốn lệnh**; (2) giành → lease hết → `reclaim` → giành lại: cùng kết luận; (3) ép hai lần giành cùng `locked_at` (và `locked_at` lùi) bằng `UPDATE` của chủ bảng trong test: token cũ vẫn bị từ chối vì `lease_id` khác; (4) 16 worker giành đồng thời: mọi `lease_id` khác nhau |
| Đột biến | Bỏ kiểm `lease_id` ở từng lệnh trong bốn lệnh (4 mẫu), `claim` dùng `lease_id` hằng số, `release`/`reclaim` không đặt `NULL`, thay kiểm `lease_id` bằng `locked_at` — **tất cả phải đỏ** |
| Tài liệu | `04-data.md` (cột mới, nghĩa của `RUNNING`), `11-ops.md` mục Retry (token hàng rào), `06-structure.md` mục B8a: sửa câu "hàng rào `(locked_by, locked_at)`" thành `lease_id`; `ADR-004` thêm mục bổ sung (không ADR mới — cùng quyết định lease, đổi token); `CHANGELOG.md`. **Ghi nhận PO:** lý do `object_claim_reconcile` ở `tool_layer.storage` đã có ở mục B8a của `06-structure.md`; tôi thêm một câu *vì sao không ở `ops/`* nếu chưa đủ rõ |

## 3. Docs trước (bước 0)

| File | Việc |
|---|---|
| `docs/reference/` | Lấy bằng `curl` (URL, ngày, sha256), **không** dùng công cụ tóm tắt: (a) tài liệu fontconfig — cú pháp file cấu hình, thư mục, `<alias>`/`<match>`, `fc-match`, `fc-list` (ADR-036 điểm 3 đang `[CẦN XÁC MINH]`); (b) tài liệu `docxtpl` — cú pháp biến, kiểm biến chưa khai báo, hành vi khi thiếu biến; (c) trang gói Debian của LibreOffice Writer không giao diện, `fontconfig`, `poppler-utils` theo image nền hiện có (tên gói đang `[CẦN XÁC MINH]` trong đặc tả `Dockerfile`); (d) file font Liberation Serif 2.1.5 và `LICENSE` — tải file `.ttf` thật vào `fonts/` và đối chiếu sha256 ở `font-liberation-serif-license.md` |
| `06-structure.md` mục 6.2 | Đặc tả `Dockerfile` thêm **target `test`** (Q1); giai đoạn build client vẫn hoãn tới B10 |
| `05-api.md` | Chốt: `Content-Disposition` không mang tên người hay giá trị slot; mã `FILE_UNAVAILABLE` đã có; trần kích thước bản đệm (Q4) |
| `ASSUMPTIONS.md`, `proposals/sprint1-working-values-a031-a048.md` | WV mới "chưa hiệu chỉnh": timeout chuyển đổi, trần kích thước file tải; A-059 ghi số đo **local** (không phải nhà cung cấp thật) |
| `12-roadmap.md`, `CHANGELOG.md` | AC-1.3 phần "bản `FINAL` mang watermark trong file" có đường chạy ở dạng test; phần tải file; bước kiểm #6, #7 hết "chưa có code" |

Chỗ thiết kế đọc ra thiếu hoặc mơ hồ sẽ báo diff **trước** khi sửa — như ở B7 và B8a.

## 4. Phạm vi mã

**4.1 `tool_layer.rendering`** (module hiện rỗng; cây ở `06-structure.md`)

| Module | Nội dung |
|---|---|
| `docx_fill.py` | Hàm thuần: (byte template, bảng giá trị, `operating_mode`) → byte `.docx`. Kiểm **trước khi điền**: biến template dùng mà bảng thiếu → `MISSING_VARIABLE`; bảng có biến template không khai → `UNKNOWN_VARIABLE`. Watermark `BẢN THỬ NGHIỆM — KHÔNG CÓ GIÁ TRỊ PHÁP LÝ` (AC-1.3) khi `NON_PRODUCTION` — **không có tham số tắt**, chế độ đọc từ `document` chứ không nhận từ caller. Mã lỗi chỉ mang tên biến, không mang giá trị |
| `fonts.py` | Liệt kê họ font mà `.docx` khai (bảng font, kiểu định dạng, mặc định, theme, từng đoạn chạy, tiêu đề/chân trang); kiểm "có mặt": họ có ánh xạ fontconfig (hiện chỉ "Times New Roman") thì `fc-match` phải ra **Liberation Serif**, họ khác thì khớp chính xác tên trong `fc-list` (ADR-015, ADR-036). **Chỗ hở của ADR-015 giữ nguyên và nói thẳng:** đặc tả OOXML chưa có trong `docs/reference/`, nên bộ liệt kê là "đủ theo những nơi đã biết", có test cho từng nơi, không khẳng định "đủ mọi nơi" |
| `convert.py` | Một tiến trình `soffice` cho mỗi lần chuyển đổi, đúng tham số của ADR-015 (hồ sơ người dùng tạm riêng, thư mục tạm, timeout WV mới), giết tiến trình và xoá thư mục tạm khi quá hạn. Không dùng shell |
| Tool `docx_render`, `pdf_export` | Theo mục Tool Registry của `03-agents.md` và **thứ tự của ADR-015**: kiểm khoá đã commit chưa → chuyển đổi vào thư mục tạm → giành khoá (`storage.put_once`) → upload → commit; `pdf_export` thêm dòng `document_render` khi cả hai object đã commit. Khoá `renders/{document_id}/{input_hash}.docx` và `.pdf`, hash trên **input**. `FONT_MISSING` kiểm **trước** khi gọi `soffice`. Audit theo luật A-055: đọc danh sách miễn ở bước 0 và báo nếu mơ hồ |
| Fixture | Mẫu `.docx` **giả, có nhãn giả** dựng trong test bằng `python-docx`/`docxtpl` (Times New Roman, tiếng Việt đủ dấu, biến, tiêu đề/chân trang); không có mẫu thật cho tới M1.1 |

**4.2 `stored_file_fetch` và endpoint tải file** (ADR-014; mục Tải file của `05-api.md`)

- `tool_layer.storage` thêm `fetch`: đọc object, **so checksum với `stored_object_commit` trước khi gửi byte đầu tiên**, lệch hoặc mất → `FILE_UNAVAILABLE` (gộp, không nói lệch hay mất; chi tiết ở log), ghi `audit_event` của lần tải.
- `GET /documents/{document_id}/renders/{render_id}/file?format=pdf|docx` và `GET /templates/{template_id}/versions/{template_version_id}/source`; `Cache-Control: no-store`; lớp timeout `SYNC_OBJECT_STORAGE`.
- Quyền: `request.read_all`, `request.read_assigned` — mọi bản, hai định dạng; người tạo yêu cầu (`request.read_own`) — **chỉ `FINAL`, chỉ `pdf`, chỉ khi `document` đã `ISSUED` hoặc sau đó**; `template.manage` cho `/source`. Cách đánh giá `read_assigned` đọc ở `kernel/permission.py` lúc làm; nếu thiếu dữ liệu để đánh giá (vì `GET /documents/{id}` và hàng đợi duyệt là B9b) thì **báo và hỏi**, không tự suy.
- Không thêm `GET /documents/{id}`, không UI.

**4.3 Image và bước kiểm khởi động**

- `Dockerfile`: thêm LibreOffice Writer (chỉ phần cần), `fontconfig`, `fonts/` (4 file Liberation Serif + `LICENSE`, **ghim sha256 bằng test**), file cấu hình fontconfig tường minh ánh xạ "Times New Roman" → Liberation Serif, làm mới bộ đệm font. Image vẫn chạy bằng `bo19` không đặc quyền; `soffice` ghi vào thư mục tạm mà `bo19` ghi được.
- Bước kiểm **#6** (`soffice` headless chạy được trong timeout) và **#7** (font + `fc-match`), cột `worker`, `Chặn`. #7 đọc `required_fonts` của mọi phiên bản `ACTIVE` cộng phiên bản mà `document` chưa kết thúc đang dùng (DB hiện chưa có hàng nào → tập rỗng hợp lệ; test với dữ liệu giả). Thiếu công cụ thì không khởi động.
- **CI:** job mới dựng image từ `Dockerfile` thật và chạy các test rendering **bên trong image** (với `pg` và SeaweedFS như job backend). Thời gian dựng ghi lại; không có job này thì không chứng minh được `soffice` và font trong image thật.

## 5. Kiểm và đột biến

| Nhóm | Điều được chứng minh |
|---|---|
| `lease_id` | Mục 2 |
| Điền biến | Thiếu / thừa biến → mã đúng, không có giá trị trong thông điệp; biến tiếng Việt đủ dấu giữ nguyên; biến chứa ký tự điều khiển Jinja/XML không phá file; tiêu đề và chân trang cũng được điền |
| Watermark | `NON_PRODUCTION` → có trong `.docx` **và** trong PDF (đọc chữ từ PDF thật); không đường nào tắt (test AST: chữ ký hàm không có tham số watermark) |
| `soffice` trong image thật | PDF hợp lệ ra từ `.docx` fixture; timeout giết tiến trình con và dọn thư mục; hai lần chuyển đổi đồng thời không dùng chung hồ sơ |
| Font | `fc-match "Times New Roman"` = Liberation Serif; **PDF nhúng Liberation Serif** (tên font đọc từ PDF); font thiếu → `FONT_MISSING` **trước** khi gọi `soffice`; sha256 bốn file font khớp `docs/reference/`; bộ liệt kê thấy font ở từng nơi đã biết (đoạn chạy, kiểu, mặc định, theme, tiêu đề/chân trang) |
| Đo còn nợ của ADR-036 | Trên image thật: kerning và ngắt dòng/ngắt trang của một văn bản tiếng Việt dài (bốn kiểu chữ) — ghi số đo và nói rõ **không so được với Times New Roman/Word thật** vì không có bản đó |
| Ghi một lần ở tầng render | Cùng input hai lần → một cặp object, một `document_render`; hai worker cùng input → một thắng, bên kia dùng object đã commit; claim hết lease giữa chừng; byte PDF khác nhau giữa hai lần chuyển đổi không tới `object_storage` |
| Tải file | Ma trận quyền (nhân viên chỉ `FINAL` + `pdf` + sau `ISSUED`; `.docx` và bản nháp → lỗi quyền); checksum lệch → `FILE_UNAVAILABLE` trước byte đầu tiên (sửa object trong bucket test để kiểm); `no-store`; `audit_event` mỗi lần tải; header không mang giá trị slot |
| Rò dữ liệu | Log, `audit_event`, thông điệp lỗi không chứa giá trị biến hay chữ của văn bản |
| Đột biến | Dự kiến 40–50 mẫu: bốn kiểm `lease_id`; bỏ kiểm thiếu/thừa biến; bỏ watermark hoặc để caller tắt được; bỏ kiểm `FONT_MISSING`; đổi thứ tự (chuyển đổi sau khi giành khoá); bỏ so checksum khi tải; bỏ lọc `FINAL`/`pdf` cho nhân viên; bỏ `no-store`; bỏ `audit_event` khi tải; bỏ giết tiến trình khi timeout; dùng chung hồ sơ `soffice`; bỏ `fc-match` ở #7… — tất cả phải đỏ, mẫu sống thì thêm test |

## 6. Câu hỏi cần PO quyết (kèm mặc định)

| # | Câu hỏi | Mặc định đề xuất |
|---|---|---|
| Q1 | Test chạy **trong image thật** cần dev deps và test, mà image triển khai không mang chúng. Thêm một **target `test`** vào `Dockerfile` (từ `runtime` + lock dev + `backend/tests`), không dùng để deploy — có sửa ADR-015 không? | Có target `test`; ADR-015 thêm một câu bổ sung. Image deploy không đổi vai trò (một image, nhiều lệnh khởi động) |
| Q2 | Đọc chữ và tên font từ PDF trong test cần công cụ. | `poppler-utils` (`pdftotext`, `pdffonts`) chỉ ở target `test`, không vào image deploy, không thêm phụ thuộc Python. Thay thế là thư viện PDF thuần Python — cần ADR |
| Q3 | CI dựng image mỗi lần push có thể mất vài phút (tải LibreOffice). | Dựng ở **mọi** push lên `build/*` và `main`, dùng cache lớp của Actions; ghi thời gian thật vào báo cáo. Chưa đủ nhanh thì chỉ dựng khi file liên quan đổi — tôi hỏi lại, không tự đổi |
| Q4 | Tải file phải so checksum **trước** byte đầu tiên, nên phải đọc cả file vào bộ nhớ (hoặc đọc hai lần). | Đọc cả file, **trần kích thước** theo WV mới (chưa hiệu chỉnh); vượt trần → `FILE_UNAVAILABLE` + log. Bản render hành chính nhỏ; không stream ở B8b |
| Q5 | Timeout chuyển đổi và số chuyển đổi đồng thời (A-031 còn `TBD`). | Timeout theo WV mới "chưa hiệu chỉnh", đo thật trên image rồi ghi; đồng thời = 1 mỗi worker (WV-22) |
| Q6 | A-059 (thời lượng upload) chỉ đo được trên SeaweedFS **local**. | Ghi rõ là số local; không dùng để chốt lease production. Đo lại ở cổng 2.5 với nhà cung cấp thật |

## 7. Ghi nhận PO, 2026-10-13 — phạm vi Nghị định 30/2020

PO xác nhận công ty là **doanh nghiệp tư nhân**. Nghị định 30/2020 theo bản đã lưu (`docs/reference/nghi-dinh-30-2020-phong-chu-va-pham-vi.md`) áp dụng cho cơ quan, tổ chức nhà nước và doanh nghiệp nhà nước (Điều 2), không nêu doanh nghiệp tư nhân. Hệ quả đã ghi vào tài liệu (nhánh này, chỉ tài liệu): điều kiện "giấy phép Times New Roman cho server hoặc cách render khác" **không bị kích hoạt bởi phạm vi này**; nó **mở lại** nếu tình trạng tổ chức đổi hoặc văn bản của hệ thống phải theo Nghị định vì lý do khác (PO xác nhận). Người triển khai không phán pháp lý — đây là xác nhận của PO về tình trạng tổ chức. **Việc kiểm Nghị định có bị sửa đổi hay thay thế sau 2020 vẫn giữ trước M1.1**: nó trả lời "văn bản còn hiệu lực không", không phải câu hỏi phạm vi.

## 8. Không làm ở B8b

`document_graph`, handler `render_document` và mọi handler (B9a), `render_integrity_check` (B9a/B9b — dựa trên `fetch` của B8b), `GET /documents/{id}` và hàng đợi duyệt (B9b), mẫu `.docx` thật (M1.1), giai đoạn build client của `Dockerfile` (B10), `combined_main`, Render và cold start thật (cổng 2.x), script kiểm contract S3 dùng chung (cổng 2.5), `notification_send`, `checkpoint_purge`, ghim `document_render_pin`.
