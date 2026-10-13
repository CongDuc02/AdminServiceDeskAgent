# Kế hoạch B8b — `lease_id` cho job, rồi `rendering`, `stored_file_fetch`, image có `soffice` và font

**Trạng thái:** ✅ **PO duyệt 2026-10-13; đã làm — chờ PO duyệt merge và quyết O1-18 (mục 9)** — Q1 đồng ý với điều kiện **stage `runtime` luôn là stage cuối của `Dockerfile`** (build không `--target` phải ra image runtime — Render dựng mặc định); CI thêm bước build không `--target` và kiểm image không có gói dev (pytest, import-linter…) và không có poppler; đột biến đặt `test` làm stage cuối phải làm bước này đỏ. Q2–Q6 theo mặc định. **Thêm — bộ nhớ trên gói free (thay một phần S5):** giới hạn RAM của Web Service free lấy từ tài liệu Render vào `docs/reference/`; chạy test chuyển đổi trong container `--memory=<mức đó>`, đo RSS đỉnh của `soffice` và của cả tiến trình; ghi kích thước image runtime trước và sau khi thêm LibreOffice; Q4: trần kích thước file × số tải đồng thời phải vừa RAM đó, ghi phép tính; **vượt thì dừng, báo — chưa chọn phương án.** `request.read_assigned` thiếu dữ liệu thì dừng hỏi · **Ngày:** 2026-10-13 · **Người đề xuất:** người triển khai · **Nhánh dự kiến:** `build/b8b-lease-id-rendering` (đã tách từ `main` sau merge B8a; chỉ có tài liệu cho tới khi duyệt) · **Thứ tự:** mục 4.7 của `12-roadmap.md` (risk-first) · **Điều kiện cổng:** cổng 1.6 đạt cho giai đoạn thử nghiệm (ADR-036) · **Đã đọc:** ADR-001, 003, 004, 014, 015, 031, 036, 037; `03-agents.md` mục Tool Registry (`docx_render`, `pdf_export`, `render_integrity_check`) và 5.6; `04-data.md` mục Vận hành, Lưu trữ file và bất biến bản render; `05-api.md` mục Tải file và Mã lỗi; `06-structure.md` cây `rendering/`, đặc tả `Dockerfile`, bước kiểm #6/#7; `11-ops.md` mục Retry; `backend/migrations/schema/0001_initial.sql` (`job`, `template_version`, `template_variable`, `document_render`)

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

## 9. Kết quả (2026-10-13)

**Trạng thái mã:** xong trên `build/b8b-lease-id-rendering`; **dừng ở O1-18** (mục 9.4) — phần còn lại của B8b không phụ thuộc nó.

### 9.1 Đã làm so với kế hoạch

| Hạng mục kế hoạch | Kết quả |
|---|---|
| `job.lease_id` trước mọi thứ (mục 2) | Migration `0013`; bốn lệnh kiểm `lease_id`; test bốn lệnh sau `release` rồi giành lại, sau `reclaim` rồi giành lại, cùng `locked_at`, `locked_at` lùi, 16 worker khác token; **14/14 mẫu đột biến đỏ** |
| Tài liệu tham chiếu bằng `curl` (mục 3) | `fontconfig-debian-trixie.md` (trang man Debian — trang freedesktop trả kiểm tra bot), `docxtpl-0.20.1.md` (kèm mã nguồn bản khoá), `debian-trixie-goi-libreoffice-fontconfig-poppler.md` (`apt-cache` trong image nền — `packages.debian.org` trả kiểm tra bot), `render-free-web-service-ram.md` (+ hai bản gốc `render-docs-raw/`); bốn file font vào `fonts/`, sha256 khớp |
| `rendering`, `docx_render`, `pdf_export` | Xong (mục 4.1); **hai chỗ lệch kế hoạch, nói rõ:** (1) `docx_render` nhận **bảng giá trị biến làm tham số** thay vì tự dựng từ `document_id` — việc dựng là của B9a; (2) watermark là **một dòng chữ ở đầu mọi tiêu đề trang** (không phải hình chéo) |
| `stored_file_fetch` + hai endpoint | Xong; `read_assigned` **đủ dữ liệu** (`approval_step.assignee_employee_id`), nên không phải dừng hỏi — diễn giải ở `05-api.md` |
| Image, #6, #7, CI | Xong. **Lệch kế hoạch:** target `test` **không COPY `backend/tests`** — test mount vào lúc chạy (`docker run -v`), giữ `.dockerignore`; `runtime` luôn là stage cuối, có test và có bước CI + đột biến |
| Đo bộ nhớ (yêu cầu thêm của PO) | Mục 9.3–9.4 |
| Đo nợ của ADR-036 | 829 dòng, 26 trang: 0 lệch (ADR-036 mục Kết quả) |

### 9.2 Kiểm

- **CI xanh cả ba job:** `backend` 3 phút 23 giây (dựng image runtime không `--target` + bước kiểm 41 s trên runner nguội, dựng `--target test` 7 s, `lint-imports` 9/9, **1324 test OK** trong 129 s trong image `test`); `contracts` Lệch 0; `lock` đạt. Không dùng cache lớp (Q3): đủ nhanh.
- **Đột biến:** 14 mẫu `lease_id` + 66 mẫu render/tải file/khởi động = 80 mẫu; **62/66 đỏ ngay**, 4 sống: `C04` (không tách nhóm tiến trình) và `E03` (người tạo tải bản chưa phát hành) do test yếu — đã thêm test rồi chạy lại đỏ; `F07` (xuống dòng thành ngắt dòng) là **mẫu tương đương**: docxtpl 0.20.1 tự làm, mã thừa đã xoá; `T05` (mở phân giải thực thể) là **mẫu tương đương**: mã chỉ đọc thuộc tính, mà XML cấm thực thể ngoài trong giá trị thuộc tính, và `load_dtd=False`, `no_network=True`, `huge_tree=False` chồng lên nhau (phòng thủ nhiều lớp) — test kiểm file ngoài không lọt. **Đột biến image (PO: đặt `test` làm stage cuối):** 5 mẫu, cả 5 đỏ bằng `check_runtime_image.sh` — `test` làm stage cuối (5 chỗ đỏ), poppler vào `base`, lock dev vào `base`, bỏ quy tắc fontconfig, bỏ `USER bo19`.
- **Test chạy trong image thật có `soffice`:** worker startup (AC-1.7) nay chạy #6, #7 thật.

### 9.3 Số đo bộ nhớ và thời lượng (ADR-015 mục Bổ sung có bảng đầy đủ; công cụ `tools/mem-probe/measure_convert.py`, sha256 `8cf7e9d4d94383c7b6b57af3cfac62a973f142efff2969894d76da32eb7b2207`)

| Phép đo (container `--memory=512m --memory-swap=512m`) | Kết quả |
|---|---|
| Giới hạn RAM Render Free | **512 MB RAM, 0,1 CPU** (`render-free-web-service-ram.md`; chưa biết khi vượt thì thế nào) |
| Một lần chuyển đổi, 1–300 đoạn (38–40 KB `.docx`) | cgroup đỉnh **211–212 MiB**; `soffice.bin` RSS đỉnh **217–221 MiB**; tiến trình Python 74 MiB; không đổi theo kích thước trong khoảng đó |
| Hai lần đồng thời | cgroup **357–362 MiB** (RSS cộng dồn 523–582 MiB, đếm trùng thư viện) |
| Mức tối thiểu | 224 MiB qua, **192 MiB OOM-kill** (`CONVERSION_FAILED` sạch) |
| Tiến trình Python nạp mọi module api + worker | RSS **111 MiB** sau import (chưa tính tăng theo thời gian) |
| Một lần tải file 8 MiB | RSS tăng **18,4 MiB** (≈ 2,3 × kích thước); `tracemalloc` đỉnh 12 MiB |
| Thời lượng ở `--cpus=0.1` | **32–47 s** (nhỏ), **88 s** (300 đoạn); máy phát triển: 2–4 s. Văn bản có **800 dòng ngắt trong một giá trị: 26 s ở CPU đầy đủ; 3000 dòng: 305 s** (superlinear) |
| Kích thước image runtime | đã nén 133.057.330 → 276.966.137 byte (×2,08); chưa nén 406 → 759 MiB (×1,87); CI `.Size` 751.759.234 byte |

### 9.4 Phép tính bộ nhớ tải file (Q4) — **vượt, dừng, chưa chọn phương án** (O1-18)

Một container 512 MB cho `combined_main` (ADR-033), trường hợp xấu nhất xảy ra cùng lúc (dùng 512 MiB; nếu "MB" của Render là thập phân thì 488 MiB):

| Khoản | MiB |
|---|---|
| Tiến trình Python nạp api + worker (đo, chưa tính tăng theo thời gian) | 111 |
| `argon2id` đồng thời tối đa 4 × 19 MiB (WV-16b, A-048) | 76 |
| Một lần chuyển đổi (RSS đỉnh của `soffice.bin`; WV-22 = 1) | 221 |
| **Cộng** | **408** |
| **Còn lại cho bộ đệm tải file** | **104** (488 → 80) |

Mỗi lần tải file `S` giữ ≈ 2,3 × `S`. Với `FILE_FETCH_MAX_BYTES` = 8 MiB: 18,4 MiB mỗi lần ⇒ vừa **5** lần tải đồng thời (4 nếu 488 MiB), không dư địa. **Nhưng số tải đồng thời hiện không bị chặn:** `api` chạy endpoint đồng bộ trên threadpool mặc định của Starlette (40 luồng) ⇒ trần lý thuyết 40 × 18,4 = **736 MiB > 512** — vượt, kể cả không có chuyển đổi nào. File thật đo được rất nhỏ (`.docx` ≈ 40 KB, PDF ≤ 289 KB cho 300 đoạn): 8 MiB là trần cao hơn 30–200 lần, và ở trần 1 MiB thì 40 lần tải = 92 MiB — vẫn vượt phần 80–104 MiB còn lại khi cộng đủ mọi khoản. **Người triển khai không chọn phương án** theo chỉ đạo của PO. Các hướng để PO chọn (không theo thứ tự): chặn số tải đồng thời (semaphore), hạ `FILE_FETCH_MAX_BYTES`, đọc hai lượt (băm rồi stream — đổi cách so checksum của ADR-014), hoặc chấp nhận với lý do quy mô Sprint 1 (vài người, một máy) và ghi lại.

### 9.5 Điều cần PO xác nhận

O1-18 (mục 9.4); O1-19 (thời lượng ở 0,1 CPU và bước kiểm #6 chuyển đổi thật mỗi lần khởi động); A-094 (gói apt không ghim); bốn diễn giải của người triển khai: `read_assigned` tính bước `OPEN` và `DECIDED`; `TEMPLATE_NOT_ACTIVE` (DRAFT chỉ `ACTIVE`, FINAL thêm `RETIRED`); watermark là dòng chữ ở tiêu đề; `docx_render` nhận bảng giá trị.
