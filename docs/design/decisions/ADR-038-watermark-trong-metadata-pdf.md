# ADR-038 — Watermark kiểm được bằng máy: chuỗi ghi vào `/Subject` của PDF qua thuộc tính `.docx`, kiểm bằng `pdfinfo` ở CI và ở phép kiểm sau UAT; runtime không đọc lại PDF

**Trạng thái:** Accepted · **Duyệt:** PO, 2026-10-13 (trả lời kế hoạch B9a: Q1–Q4) · **Ngày:** 2026-10-13 · **Quyết định tại:** BUILD MODE, B9a, đầu lát · **Liên quan:** ADR-015 (LibreOffice headless), ADR-036 (font), ADR-037 (client S3), D-009 và NFR-03 (watermark không gỡ được), M5 của `01-prd.md`, AC-1.3, A-096 · **Nguồn:** `docs/reference/pdf-document-information-dictionary.md` (ISO 32000-1, mục 14.3.3, Table 317)

---

## Context

Từ B8c, watermark là một shape VML chéo trải thân trang. Trong `.docx` kiểm được bằng XML. Trong PDF nó là **đường vẽ**: `pdftotext` không đọc ra chữ, nên "bản render này mang watermark" ở PDF chỉ kiểm được bằng pixel — không phải thứ chạy được trên dữ liệu thật sau UAT (M5). PO (2026-10-13): cần kiểm bằng máy, có chuỗi nguyên văn trong metadata PDF, có ghi nhận ở DB, có thủ tục kiểm sau UAT.

Hai thứ kéo theo:

1. **Khoá object theo input không gồm chuỗi watermark** (mục 5.6 của `03-agents.md`). Đổi chuỗi sau này thì cùng input cho `reused = True` và trả bản cũ mang chuỗi cũ — DB không cho biết bản nào mang chuỗi nào.
2. **Thuộc tính tài liệu của mẫu đi thẳng vào PDF.** Spike (LibreOffice 25.2.3.2): `author` của `.docx` ra `Author` của PDF. Mẫu thật có thể mang tên người soạn.

Đo bằng spike (2026-10-13), không phải quy tắc của nguồn: `subject` của `.docx` → `/Subject` của từ điển `Info` đúng nguyên văn (UTF-16BE) và `dc:description` của XMP; `keywords` bị tách từ; `comments`, `category` không ra PDF. Image `runtime` không có poppler (CI kiểm điều đó).

## Options

- **A — Ghi `subject` của `.docx`, để LibreOffice chuyển sang `/Subject`; kiểm bằng `pdfinfo` ở CI (image `test`) và ở phép kiểm sau UAT; runtime không đọc lại PDF.**
- **B — Bộ đọc PDF tự viết trong runtime**, kiểm `/Subject` sau mỗi lần chuyển đổi.
- **C — `pypdf` trong runtime** (hoặc `pikepdf`): đọc, hoặc ghi lại metadata sau khi chuyển đổi.
- **D — Hậu xử lý PDF** để ghi metadata (viết lại byte sau `soffice`).
- **E — Trường XMP tự định nghĩa** thay vì `Info`.

## Decision

**Chọn A**, với bốn điểm cụ thể.

1. **Ghi:** `docx_fill` đặt `subject` của `.docx` = chuỗi watermark khi `operating_mode = NON_PRODUCTION`, cùng chỗ và cùng luật "không có tham số tắt" với shape. `PRODUCTION`: `subject` bị **xoá** (PDF không bao giờ mang chuỗi watermark do thuộc tính của mẫu). Cùng lúc, `author` và `lastModifiedBy` của `.docx` bị **ghi đè** bằng tên hệ thống ở **cả hai chế độ**; `title` giữ nguyên, thuộc mốc M1.1 (PO).
2. **Kiểm:** `pdfinfo` đọc `/Subject` và `/Author` — ở CI (test chạy trong image `test` với `soffice` thật, một PDF thật) và ở phép kiểm sau UAT (`tools/render-audit/`, chạy trong image `test`). **Runtime không đọc lại PDF** — không bộ đọc tự viết, không `pypdf`.
3. **DB:** `document_render.watermark_text` (nullable; `CHECK`: `NON_PRODUCTION` thì có và không rỗng). `pdf_export` ghi chuỗi **đã đưa vào input của lần render** (đi theo `DocxRender`), trong cùng `INSERT`; bảng không `UPDATE`. Nó là **lời khai của tool về lệnh đã ra**, không phải kết quả đọc lại từ file — bằng chứng về file là chân `pdfinfo` của phép kiểm sau UAT, và chân checksum nối byte đã kiểm với byte đã commit.
4. **Khoá:** chuỗi watermark **vào input của khoá object** (`input_hash`): đổi chuỗi thì khoá khác, bản cũ còn nguyên, không còn `reused` nhầm.

## Consequences

**Tích cực**

- Không phụ thuộc mới, không parser nào để duy trì trong tiến trình sản xuất; bề mặt tấn công và RAM của image runtime không tăng.
- Phép kiểm dùng công cụ chuẩn, độc lập với mã của dự án: một lỗi của chính ta không che được lỗi của ta.
- DB trả lời được "bản này mang chuỗi nào"; đổi chuỗi không để lại bản render mơ hồ.
- Tên người soạn mẫu không lọt vào PDF phát hành qua `Author`.

**Tiêu cực / phải chấp nhận**

- **Runtime không tự phát hiện** nếu một bản LibreOffice khác ngừng ánh xạ `subject` → `/Subject`. Việc giữ cho đúng nằm ở CI (cùng `Dockerfile`, cùng stage `base` cho `test` và `runtime`) và ở phép kiểm sau UAT. Cột `watermark_text` là lời khai, không phải bằng chứng — nêu thẳng ở `11-ops.md`.
- Ánh xạ `subject` → `/Subject` của LibreOffice là **số đo, chưa có tài liệu gốc** (A-096). Địa vị của `Info` ở PDF 2.0 là `[CẦN XÁC MINH]` (ISO 32000-2 không lấy được: `403`).
- Metadata sửa được bằng công cụ PDF: đây là bằng chứng kiểm sau UAT, không chống giả mạo (cùng nghĩa "không gỡ được" của B8c).
- `title` của mẫu thật vẫn chảy vào PDF cho tới khi M1.1 xử lý; `Company`, `Manager` trong `docProps/app.xml` không bị chạm (chưa thấy chúng ra PDF; kiểm lại ở M1.1 khi có mẫu thật).
- Bản render ghi trước B9a không có metadata và không có cột — chưa có bản nào (không có đường ghi `document_render` ngoài test).

## Rejected alternatives

- **B — bộ đọc tự viết.** Một parser PDF tối thiểu trong tiến trình sản xuất là mã phải duy trì cho một việc mà công cụ chuẩn làm được ngoài tiến trình; PO loại.
- **C — `pypdf`/`pikepdf`.** Thêm phụ thuộc (lock có hash, ADR) và bề mặt tấn công vào image runtime để đọc lại một thứ mà ta vừa ghi; nếu để **ghi** thì là hậu xử lý (D). PO loại.
- **D — Hậu xử lý PDF.** Viết lại byte sau `soffice` — thêm một bước biến đổi nội dung văn bản chính thức, phải chứng minh nó không đổi gì ngoài metadata; không cần khi LibreOffice đã ghi đúng.
- **E — XMP tự định nghĩa.** Cần ghi XMP bằng tay (D) và đọc bằng công cụ ít phổ biến hơn; `Info` đọc được bằng mọi công cụ. XMP `dc:description` vẫn có mặt nhờ LibreOffice — không dựa vào nó.
- **Không thêm cột (chỉ dựa `operating_mode`).** Loại ở kế hoạch B9a: DB không nói được chuỗi nào đã đóng; đổi `WATERMARK_TEXT` không để dấu vết.
