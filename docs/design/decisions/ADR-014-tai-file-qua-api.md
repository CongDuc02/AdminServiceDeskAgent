# ADR-014 — Tải file đi qua `api`, không dùng URL ký sẵn

**Trạng thái:** Accepted · **Ngày:** 2026-09-13 · **Quyết định tại:** Phase 5 — API Spec · **Liên quan:** ADR-003, A-002, A-021, A-024, A-025, AC của F3 và F4 trong `01-prd.md`, mục Lưu trữ file và bất biến bản render của `04-data.md`

---

## Context

Bản render `.docx`/`.pdf`, bản gốc template và bản gốc tài liệu quy trình nằm ở `object_storage` S3-compatible; nhà cung cấp chưa chọn (ADR-003, A-024). Có ba nhóm người tải:

- nhân viên — bản phát hành của yêu cầu của mình (hành trình end-to-end ở mục Definition of Done của `01-prd.md`: "tải được văn bản có watermark");
- cán bộ hành chính — bản nháp, bản đã duyệt nội dung và bản cuối, khi duyệt, ký, đóng dấu, phát hành;
- người quản template — bản gốc template.

File chứa dữ liệu `PER`/`RES` và là văn bản chính thức, hoặc bản thử nghiệm mang watermark. Bản đã ghim được bảo đảm bất biến bằng chuỗi mắt xích ở `04-data.md`, nhưng còn một cửa sổ ghi đè ở tầng lưu trữ mà tầng ứng dụng chỉ thu hẹp được (A-024).

## Options

**A — `api` đọc object rồi stream về client**, sau khi kiểm quyền.

**B — `api` kiểm quyền rồi trả một URL ký sẵn có hạn**; client tải thẳng từ `object_storage`.

## Decision

**Chọn A.** Mỗi lần tải:

1. Kiểm permission **tại lúc tải**, không tại lúc cấp đường dẫn.
2. Đọc object qua module lưu trữ của `tool_layer` — module duy nhất chạm `stored_object` (mục Lưu trữ file và bất biến bản render của `04-data.md`).
3. **So checksum với `stored_object_commit` trước khi gửi byte đầu tiên** — cùng phép so với tool `render_integrity_check`. Lệch hoặc mất object thì không gửi gì, trả `FILE_UNAVAILABLE`.
4. Ghi `audit_event`: ai tải bản nào, lúc nào. Chỉ mã và id.
5. Response mang `Content-Disposition: attachment` và `Cache-Control: no-store`.

Chạy **đồng bộ trong luồng request, có chạm `object_storage`**.

## Consequences

**Tích cực**

- Quyền bị thu — ví dụ nhân viên nghỉ việc, `is_active = false` — có hiệu lực ngay ở lần tải kế tiếp. Không có đường dẫn nào còn hạn sống sót sau khi quyền đã mất.
- Mọi lần tải có một `audit_event`, nên câu hỏi "văn bản này đã rời hệ thống bao nhiêu lần, về tay ai" trả lời được.
- Người tải là người dựa vào byte của file. Phép so checksum đặt ngay trước họ, cùng nguyên tắc đã dùng cho người ký (`render_integrity_check`). Nó thu hẹp thêm, ở phía đọc, cửa sổ ghi đè còn lại của A-024 — không đóng được cửa sổ đó.
- Không phụ thuộc tính năng ký URL của một nhà cung cấp chưa chọn.

**Tiêu cực và cái phải chấp nhận**

- Byte đi qua `api`: tốn bộ nhớ và thời gian của luồng request, và chịu giới hạn thời gian request (A-025). Phép so checksum trước khi gửi buộc đọc trọn object trước. Chấp nhận vì văn bản của hai loại yêu cầu Sprint đầu là giấy tờ ngắn theo template; kích thước thật `TBD` (A-002).
- Thêm một thao tác chạm `object_storage` trong luồng request đồng bộ, bên cạnh tải lên template và tài liệu quy trình (mục Nguyên tắc chung của `05-api.md`).

**Điều kiện đảo ngược**

- *Tín hiệu vận hành, đo ở `observability`:* phân phối thời lượng một lần tải — nhìn phần đuôi, không nhìn trung bình — đặt cạnh kích thước file và giới hạn thời gian request (A-025). Khi phần đuôi tiến sát giới hạn: xét phương án B cho đúng loại file đó. Chỗ quan sát này **chưa có** trong bảng chỗ quan sát của Phase 11 ở `_PLAN.md`.
- *Tín hiệu kiến trúc:* việc kiểm quyền làm được ở chỗ khác — ví dụ `object_storage` tự xác thực được danh tính người tải. Khi đó lý do 1 mất; phương án B cần một ADR thay thế, ghi rõ audit chuyển về lúc cấp đường dẫn và phép so checksum trước khi gửi bị mất.

## Rejected alternatives

**B — URL ký sẵn có hạn.** Bị loại vì bốn lý do:

1. URL ký sẵn là credential cầm tay: ai có URL thì tải được tới lúc hết hạn, bất kể là ai. Quyền được kiểm một lần lúc cấp, không phải lúc dùng.
2. Audit ghi được việc cấp đường dẫn, không ghi được việc tải.
3. Byte đi thẳng từ `object_storage` tới người dùng, nên không có chỗ nào so checksum trước khi họ nhận file.
4. Cơ chế ký và hạn của URL phụ thuộc nhà cung cấp chưa chọn — `[CẦN XÁC MINH]` (A-024) — đúng loại phụ thuộc mà ADR-003 đã tránh.

Lợi ích của B — giảm tải cho `api` — chưa có số liệu nào cho thấy cần (A-002).
