# Kế hoạch B9a — kiểm watermark bằng máy (M5), rồi `document_graph` tới `PENDING_APPROVAL`

**Trạng thái:** ✅ **PO duyệt 2026-10-13, kèm sáu điều chỉnh — các mục A.2, A.4 và câu hỏi Q1–Q6 dưới đây được thay bởi `decisions/ADR-038-watermark-trong-metadata-pdf.md` và mục ngày 2026-10-13 (B9a) của `CHANGELOG.md`: không bộ đọc PDF trong runtime (không `WATERMARK_METADATA_MISSING`), chuỗi watermark vào khoá object, ghi đè `author`/`lastModifiedBy`, `combined_main` sang B9a2, thêm điểm dừng resume sau khởi động lại** · **Ngày:** 2026-10-13 · **Người đề xuất:** người triển khai · **Nhánh:** `build/b9a-document-graph-den-pending-approval` (tách từ `main` sau merge B8c `1c7354d`; chỉ có tài liệu cho tới khi duyệt) · **Vị trí:** lát B9a của mục 4.7 của `12-roadmap.md` · **Nguồn quyết định:** PO 2026-10-13 — watermark giữ `#808080` / `.5`; M5 làm ở **đầu B9a**, không lát riêng

Kế hoạch có hai phần: **phần A** (M5, đã đủ chi tiết để làm — có spike) và **phần B** (phần còn lại của B9a theo dòng B9a của `12-roadmap.md` — ở mức hạng mục và điểm dừng, vì chi tiết từng tool đã nằm ở mục Tool Registry của `03-agents.md` và không đổi).

---

## Phần A — M5: kiểm watermark ở PDF bằng máy

### A.1 Đã kiểm, trước khi đề xuất

**Spike (chạy trong image `bo19-test`, LibreOffice 25.2.3.2; chưa có mã trong repo).** Dựng `.docx` bằng `python-docx` với `core_properties` (`title`, `subject`, `keywords`, `comments`, `category`), chuyển bằng `convert.convert_to_pdf`, đọc bằng `pdfinfo` và `pdfinfo -meta`:

| Thuộc tính của `.docx` | Ra ở PDF | Kết luận |
|---|---|---|
| `subject` = `BẢN THỬ NGHIỆM — KHÔNG CÓ GIÁ TRỊ PHÁP LÝ` | `Subject:` của `pdfinfo` **đúng nguyên văn**; trong file là `/Subject<FEFF…>` (UTF-16BE) trong từ điển `Info`; và `dc:description` trong luồng XMP | **Dùng được** |
| `keywords` | Bị **tách** theo dấu phẩy/chấm phẩy/khoảng trắng thành danh sách | Không dùng — không giữ nguyên văn |
| `comments`, `category` | Không ra PDF | Không dùng |
| `title`, `author` (`creator`) | Ra `Title`, `Author` | Xem A.7 |

Thêm hai quan sát: từ điển `Info` ở dạng thường (không `ObjStm`), nên một bộ đọc nhỏ làm được; image `runtime` **không có poppler** (CI kiểm điều đó), nên bước kiểm trong tiến trình không dùng được `pdfinfo` — chỉ dùng được ở image `test` và trên máy PO.

**Kiểm 04-data.md và schema.** `document_render` đã có `operating_mode` (khoá ngoại ghép tới `document` — "watermark theo chế độ đã ghim"). Nó nói **chế độ**, không nói **chuỗi đã đóng vào bản render này**. Khoảng trống cụ thể: khoá object theo **input** (phiên bản template, bảng giá trị, `operating_mode` — mục 5.6 của `03-agents.md`), **không** gồm chuỗi watermark. Nếu về sau `WATERMARK_TEXT` đổi, cùng input sẽ cho `reused = True` và trả bản cũ mang chuỗi cũ — DB không có chỗ nào cho biết bản ấy mang chuỗi nào. Vậy **04-data.md chưa có chỗ** cho điều PO hỏi.

### A.2 Thiết kế đề xuất

1. **Trường:** `/Subject` của từ điển `Info` (LibreOffice còn phản chiếu vào `dc:description` của XMP). Ghi nguyên văn `WATERMARK_TEXT`.
2. **Nơi đặt:** `docx_fill` đặt thuộc tính `subject` của `.docx` = `WATERMARK_TEXT` khi `operating_mode = NON_PRODUCTION`, cùng chỗ và cùng luật với shape ở tiêu đề — **không có tham số tắt**. LibreOffice chuyển nó sang PDF. `PRODUCTION`: không đặt (và `pdf_export` kiểm là **không có** chuỗi ấy).
3. **`pdf_export` kiểm sau khi chuyển đổi, trước khi giành khoá và upload:** PDF phải mang `/Subject` đúng chuỗi mong đợi cho `operating_mode`; sai hoặc thiếu thì `WATERMARK_METADATA_MISSING` (mã nội bộ của tool, như `FONT_MISSING` — không vào danh mục `error_code` của `05-api.md`; đi theo cạnh `render_draft` → `halt_for_human` đã có) và **không commit gì, không thêm dòng `document_render`**. Đây là phần "lúc `pdf_export`" của yêu cầu PO: ghi (qua `.docx`) và **chứng minh đã ghi** ở cùng một lần render.
4. **Bộ đọc:** `rendering/pdf_meta.py` — đọc `trailer` cuối → `/Info` → đối tượng → `/Subject` (chuỗi hex UTF-16BE hoặc literal). Hàm thuần trên byte, dùng chung cho `pdf_export` và cho phép kiểm sau UAT. Không đọc được thì **báo lỗi**, không coi là "không có watermark" một cách im lặng.
5. **DB:** thêm cột `document_render.watermark_text text` (nullable) và `CHECK (operating_mode <> 'NON_PRODUCTION' OR watermark_text IS NOT NULL)`. `pdf_export` ghi giá trị **vừa đọc ra từ chính PDF**, trong cùng `INSERT` của dòng `document_render` (bảng không có `UPDATE` — ghi một lần, đúng mục 5.1 của `04-data.md`). Migration `0014_document_render_watermark_text.sql` (schema; ADR-017) — **chưa làm, chờ PO duyệt cột (Q2)**. `ON CONFLICT DO NOTHING` giữ nguyên: dòng cũ đứng yên.
6. **Phép kiểm sau UAT** (thủ tục ở `11-ops.md`, mục Runbook mới), cho từng `document_render` — ba chân độc lập, **cả ba phải đạt**:
   - **DB:** không dòng `NON_PRODUCTION` nào có `watermark_text` NULL hay khác chuỗi của AC-1.3;
   - **Checksum:** tải byte PDF từ `object_storage`, sha256 **bằng** `stored_object_commit.checksum_sha256` đã lưu (không bằng thì dừng — metadata đọc từ byte khác với byte đã commit thì vô nghĩa);
   - **Metadata:** đọc `/Subject` bằng công cụ chuẩn (`pdfinfo`, trên máy PO) và so với `watermark_text` của dòng.
   Kèm một script `tools/render-audit/` làm đủ ba chân (credential qua biến môi trường đọc từ file, không trên dòng lệnh) — để thủ tục chạy được chứ không chỉ viết ra (Q3).
7. **Giới hạn nêu thẳng:** metadata PDF sửa được bằng công cụ PDF; đây là **bằng chứng kiểm sau UAT**, không chống giả mạo — cùng nghĩa "không gỡ được" của B8c (không có tham số tắt). Bản render ghi **trước** B9a không có metadata; hiện **chưa có đường nào ghi `document_render` ngoài test** (`pdf_export` chưa có handler), nên không cần dọn dữ liệu cũ — sẽ xác nhận bằng truy vấn trên DB trước khi PO áp `0014`.

### A.3 Nguồn tài liệu (luật trích dẫn ở mục 5 của `CLAUDE.md`)

Trước khi dựa vào ngữ nghĩa của `/Subject`, **lấy bản gốc bằng `curl` vào `docs/reference/`** (URL, ngày lấy, sha256; không dùng công cụ tóm tắt):

- ISO 32000-1:2008 (PDF 1.7), bản Adobe công bố: `https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/PDF32000_2008.pdf` — đã kiểm `HTTP 200`, 22.491.828 byte. Trích phần từ điển `Info` thành `docs/reference/pdf-document-information-dictionary.md` (không commit nguyên file 22 MB; ghi sha256 của file gốc).
- ISO 32000-2 (PDF 2.0): `pdfa.org/norm-refs/ISO_32000-2.pdf` trả `403` — **chưa có bản gốc**. Điều "từ điển `Info` ở PDF 2.0 còn được dùng ra sao" ghi **`[CẦN XÁC MINH]`** (A-096 mới); đây là lý do giữ cả hai nơi LibreOffice đã ghi (`Info` và XMP) và chọn kiểm `Info`, đọc được bằng mọi công cụ.
- Mô tả LibreOffice ánh xạ thuộc tính tài liệu sang PDF: **chưa có bản gốc** — hiện chỉ có số đo của spike (25.2.3.2). Không viết thành quy tắc; test trong CI giữ cho nó đúng ở bản dùng thật, và `pdf_export` báo lỗi nếu đổi.

### A.4 Test (có đột biến — PO yêu cầu)

| Test | Chứng minh |
|---|---|
| PDF thật do `soffice` dựng từ `fill_docx(NON_PRODUCTION)` | `/Subject` = chuỗi; **`pdfinfo` độc lập** cho cùng kết quả với `pdf_meta` (hai bộ đọc, một đáp án) |
| `PRODUCTION` | Không có `/Subject` mang chuỗi; `pdf_export` đạt |
| **PDF thiếu metadata** | `pdf_meta` / phép kiểm **báo lỗi**; `pdf_export` ném `WATERMARK_METADATA_MISSING`, **không** có object commit, **không** có dòng `document_render` |
| PDF mang chuỗi khác (một ký tự lệch) | Báo lỗi |
| PDF hỏng / không có `Info` | Báo lỗi, không im lặng |
| DB | Dòng `NON_PRODUCTION` ghi `watermark_text`; `INSERT` với `NULL` bị `CHECK` chặn; `ON CONFLICT` giữ dòng cũ |
| Phép kiểm sau UAT | Đạt trên dữ liệu đúng; **báo lỗi** khi: metadata thiếu · checksum lệch · cột NULL · cột khác chuỗi |
| Thủ tục trên image `runtime` | `pdf_meta` chạy không cần poppler |

**Đột biến dự kiến (đều phải đỏ):** bỏ đặt `subject` trong `docx_fill` · bỏ bước kiểm ở `pdf_export` · kiểm xong nhưng vẫn commit · không ghi cột · ghi cột bằng hằng thay vì giá trị đọc từ PDF · bỏ `CHECK` · bộ đọc bỏ qua so sánh chuỗi (luôn đạt) · bộ đọc trả "không có" khi lỗi parse · phép kiểm sau UAT bỏ chân checksum · bỏ chân metadata · `PRODUCTION` vẫn đặt `subject`. Mẫu sống thì sửa test, như B8c.

### A.5 Tài liệu phải sửa trước mã (luật BUILD MODE)

`04-data.md` (cột mới ở mục Bảng chi tiết và mục 5.1), `03-agents.md` (dòng `pdf_export`, `docx_render`: mã `WATERMARK_METADATA_MISSING`), `11-ops.md` (runbook), `08-hitl.md` mục Bảng mã (kiểm có cần mã tiếp quản riêng không — mặc định **không**: gộp vào cạnh lỗi render đã có), `contracts/README.md` (danh sách migration), `ASSUMPTIONS.md` (A-096), `CHANGELOG.md`, `GLOSSARY.md` nếu có thuật ngữ mới. `contracts/schema.sql` **không đổi** (dừng ở Phase 6).

### A.6 Khi merge B9a

Có migration mới (`0014`) nên **deploy Render sẽ trượt bước kiểm #1 cho tới khi PO áp migration lên DB**. Báo kèm lệnh áp khi xin merge — người triển khai không đọc `~/.bo19/admin.env`.

### A.7 Quan sát ngoài phạm vi (không làm, ghi để PO quyết)

`title` và `author` của `.docx` đi thẳng vào `Title`, `Author` của PDF (spike: `Author: python-docx`). Mẫu giả không có hại; **mẫu thật (M1.1) có thể mang tên người soạn** — dữ liệu cá nhân nằm trong metadata của văn bản phát hành, ngoài tầm mắt người xem. Đề xuất ghi vào danh sách việc của M1.1 (kiểm thuộc tính tài liệu của mẫu thật), **không** xoá/ghi đè trong B9a.

---

## Phần B — `document_graph` tới `PENDING_APPROVAL`

Theo dòng B9a: `draft_free_content` với Groq thật, `validate_free_content`, `render_draft`, `check_review_readiness`. Đóng **AC-1.11**.

### B.1 Hiện trạng (đã kiểm trong cây mã)

Đã có: `ai_gateway` với P4 `draft_free_content` ở catalog (tier `STRONG`, trần output 2048), `docx_render` và `pdf_export`, `request_submit` (đưa job `render_document` vào hàng đợi, payload chỉ id), `tool_layer.rendering`, checkpointer và `runtime`. **Chưa có:** handler `render_document` (`queue_worker/handlers` rỗng — worker chưa giành loại job này), nội dung `document_graph/`, các tool `template_fetch`, `document_draft_save`, `review_readiness_check`, `document_transition`, `document_halt_record`, `notification_send`, bộ **dựng bảng giá trị biến** (`docx_render` nhận nó làm tham số — việc dựng thuộc B9a), `combined_main` (hiện một dòng docstring).

### B.2 Hạng mục

| # | Hạng mục | Ghi chú |
|---|---|---|
| 1 | Phần A | Làm đầu tiên |
| 2 | Tool mới theo mục Tool Registry: `template_fetch`, `document_transition` (tạo `DRAFT` ghim `operating_mode`; `DRAFT → PENDING_APPROVAL`), `document_draft_save`, `review_readiness_check`, `document_halt_record`, `notification_send` | Mỗi tool: `audit_event` cùng giao dịch (A-055), kiểm quyền hệ thống, test PostgreSQL thật |
| 3 | Bộ dựng bảng giá trị biến: `DIRECT_SLOT` từ slot đã xác nhận, `FREE_CONTENT` từ `document_free_content`, `SYSTEM` | Biến *điền sau duyệt* **không** vào bản nháp — kiểm theo cờ của `template_fetch` |
| 4 | `validate_free_content` — bốn chất lượng + ba an ninh (mục Output validation trước khi render của `09-security.md`) | **AC-1.11**: đầu ra giả chứa `{{ … }}`; đầu ra giả chứa nguyên văn slot `RES` khác — cả hai trượt. Có đột biến |
| 5 | Nodes: `prepare_draft`, `draft_free_content`, `validate_free_content`, `render_draft`, `check_review_readiness`, `submit_for_review`, `halt_for_human`; điểm dừng `await_content_review` (`interrupt`) | Sinh lại **một lần** biến trượt (ADR-009), rồi `halt_for_human` (`FREE_CONTENT_INVALID`); mã halt theo mục Bảng mã của `08-hitl.md` |
| 6 | Handler `render_document` ở `queue_worker`, đăng ký ở `worker_main` | Idempotent theo ADR-004; `thread_id` theo `graph_thread` |
| 7 | Một lượt chạy **Groq thật** từ `SUBMITTED` đến `PENDING_APPROVAL` trên mẫu giả, đo số lời gọi, token, thời lượng | Ghi vào `10-eval.md`/O1-13 theo chỗ đã có; không bịa số |
| 8 | Trần `max_length` thật của biến `FREE_CONTENT` theo thời lượng chuyển đổi (nợ từ O1-19 / B8c mục 6) | Đo trên image, ghi WV mới "chưa hiệu chỉnh" |

### B.3 Không làm ở B9a

Nhánh sau `PENDING_APPROVAL`: `await_content_review` **không có đường đánh thức** (B9b); `revise_free_content`, `compute_targets`, `reopen_draft`, `await_resubmission` (B9b, O1-15); bốn thao tác cổng, `GET /documents/{document_id}`, `finalize_issue`, tách biệt trách nhiệm (B9b); client (B10). Mẫu `.docx` thật (M1.1) — dùng mẫu giả có nhãn.

### B.4 Thứ tự

Tài liệu (A.5) → lấy tài liệu PDF vào `docs/reference/` → **phần A** (mã + test + đột biến) → tool mới → bộ dựng giá trị + `validate_free_content` (AC-1.11) → graph + handler → lượt Groq thật → đột biến → CI → báo cáo. **Dừng và hỏi** nếu: `/Subject` không đủ (spike cho kết quả khác trên image CI); `WATERMARK_METADATA_MISSING` cần mã tiếp quản riêng; thời lượng một lượt vượt hạn chót worker; hạn mức Groq không đủ cho lượt thật.

## Câu hỏi cho PO (kèm mặc định)

| # | Câu hỏi | Mặc định |
|---|---|---|
| Q1 | Bộ đọc PDF trong tiến trình: viết bộ đọc nhỏ (`pdf_meta`) hay thêm `pypdf` (cần ADR, một phương án bị loại, lock có hash)? | **Bộ đọc nhỏ**: chỉ đọc một trường của một dạng file mà LibreOffice ghi; lỗi thì **báo lỗi** chứ không im lặng; `pdfinfo` là đáp án độc lập trong test. Đổi sang `pypdf` nếu bộ đọc cần lớn hơn |
| Q2 | Thêm cột `document_render.watermark_text` + `CHECK`, migration `0014` (PO phải áp lên Render trước khi deploy)? | **Có.** Phương án bỏ cột (chỉ dựa `operating_mode`) bị loại: DB không chứng minh được chuỗi nào đã đóng, và đổi `WATERMARK_TEXT` về sau không để lại dấu vết |
| Q3 | Làm `tools/render-audit/` (script chạy đủ ba chân kiểm)? | **Có** — để thủ tục trong `11-ops.md` chạy được và có test |
| Q4 | `title`/`author` của mẫu thật chảy vào metadata PDF (A.7) | Ghi vào việc của M1.1, **không** xử lý ở B9a |
| Q5 | Lượt Groq thật (mục 7): trần số lời gọi | **10 lời gọi** (đề xuất, chưa hiệu chỉnh); hết trần thì dừng và báo |
| Q6 | Dựng `combined_main` và đo O1-6 (chat dưới `--cpus=0.1` lúc `soffice` chạy) ở B9a? | **Cuối B9a, nếu handler chạy được trong một tiến trình** — nếu không thì giữ O1-6 mở và nói rõ |

## Open Questions

Q1–Q6 ở trên. Mục mở mới nếu được duyệt: **A-096** (`[CẦN XÁC MINH]` — địa vị của từ điển `Info` ở PDF 2.0 và ánh xạ thuộc tính của LibreOffice; có bản gốc thì đóng).

---

## Kết quả (2026-10-14)

Xong trên `build/b9a-document-graph-den-pending-approval`; **kết quả, bằng chứng và các lệch kế hoạch** ở mục Triển khai ở B9a của `06-structure.md` và mục B9a — kết quả mã của `CHANGELOG.md`. Các điều chỉnh của PO ở đầu file này đều đã làm: không bộ đọc PDF trong runtime (ADR-038); chuỗi watermark vào khoá object; `tools/render-audit/`; `author`/`lastModifiedBy` trung lập; 10 lời gọi Groq với `--confirm-real` (đã chạy 3 job, 3 yêu cầu); `combined_main` sang B9a2; điểm dừng resume bằng tiến trình thật.
