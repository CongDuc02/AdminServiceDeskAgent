# ADR-007 — LLM không tự gọi tool: output của model là dữ liệu có schema, không phải hành động

**Trạng thái:** Accepted · **Ngày:** 2026-09-12 · **Quyết định tại:** Phase 3 — Agent & Tool Architecture · **Liên quan:** NFR-01, NFR-05 và RISK-05 của `01-prd.md`, ADR-001, ADR-006, ADR-008

---

## Context

Đây là quyết định bảo mật lớn nhất của dự án.

Mẫu phổ biến của hệ thống agent là trao cho model một danh sách tool và để model tự quyết gọi tool nào, với tham số nào. Ở BO-19, mọi thứ model đọc đều có thể mang chỉ dẫn độc hại: tin nhắn nhân viên gõ hoặc dán vào, đoạn trong kho quy trình, và cả lý do sửa do người duyệt viết. Câu hỏi là: khi một chỉ dẫn độc hại lọt vào input, tầm ảnh hưởng tối đa của nó là gì?

## Options

**A — Model gọi tool tự do**, mọi tool (kể cả tool ghi) đi qua permission check ở `tool_layer`.

**B — Model chỉ được gọi tool đọc**; tool ghi do node tất định gọi.

**C — Model không gọi tool nào.** Mỗi lời gọi LLM trả về JSON theo một schema cố định. Node tất định trong `orchestrator` validate JSON đó rồi mới quyết định gọi tool nào, với tham số lấy từ state và từ output đã validate.

## Decision

**Chọn C.**

- Không lời gọi LLM nào được trao danh sách tool. Mọi lời gọi `tool_layer` xuất phát từ code của node, không từ quyết định của model.
- Output của mỗi prompt module có JSON Schema đóng (không cho khoá lạ). Output không qua schema bị loại, được sửa lỗi parse **đúng một lần**, sau đó dừng có kiểm soát. Không bao giờ "đoán" ý của một output hỏng.
- Giá trị trong output bị ràng buộc thêm bằng kiểm tra tất định của từng node — ví dụ `select_procedure_passages` chỉ được trả id nằm trong tập đoạn đã đưa vào; `extract_slots` chỉ được trả slot nguồn `USER_INPUT` của đúng `request_type`, kèm đoạn trích nguyên văn làm bằng chứng.
- **Ở `intake_agent`, output không chứa văn bản hiển thị cho nhân viên.** Mọi câu trả lời trong chat được lắp từ khuôn câu trả lời trong cấu hình (`render_reply`), tham số là tên slot, mã `request_type`, id đoạn trích. Đoạn quy trình hiển thị là văn bản nguyên văn đọc từ DB theo id, không phải văn bản model viết lại.
- `drafting_agent` là nơi duy nhất model sinh văn bản tự do, và văn bản đó chỉ đi vào đúng biến nội dung tự do của template, rồi vào cổng `PENDING_APPROVAL`.

## Consequences

**Tích cực**

- Prompt injection đổi bản chất: từ **"có thể kích hoạt hành vi"** thành **"chỉ làm bẩn một chuỗi JSON rồi bị schema chặn"**. Chỉ dẫn độc hại trong input không thể gọi tool, không thể chuyển trạng thái, không thể đọc thêm dữ liệu. Tệ nhất nó làm ra một giá trị sai nhưng hợp schema — và giá trị đó còn phải qua xác nhận của nhân viên (slot) hoặc qua cổng HITL (nội dung tự do).
- Ở `intake_agent`, injection không làm được chatbot nói điều gì với nhân viên, vì chatbot không có văn bản tự sinh.
- Luồng xử lý là graph tường minh, đọc được và kiểm thử được theo từng nhánh (Phase 10).

**Tiêu cực và cái phải chấp nhận**

- Mất tính linh hoạt: hành vi mới đòi sửa graph và schema, không chỉ sửa prompt.
- Hội thoại cứng hơn một chatbot sinh văn bản tự do. Rủi ro này đè lên NFR-04 (người dùng thưa). Mitigation: khuôn câu trả lời viết bằng ngôn ngữ thường, không thuật ngữ nội bộ; M3 ở UAT là nơi phát hiện.
- Một giá trị sai nhưng hợp schema vẫn lọt được tới bước xác nhận. ADR này thu hẹp tầm ảnh hưởng, không bảo đảm giá trị đúng.

**Điều kiện đảo ngược** — tín hiệu nghiệp vụ, không đo ở observability. ADR này chỉ được xét lại khi có một feature **bắt buộc** model tự chọn tool qua nhiều bước mà không biểu diễn được thành graph. Feature đó phải có ADR riêng thay thế ADR này, không được bật ngầm qua cấu hình.

## Rejected alternatives

**A — Model gọi tool tự do, dựa vào permission check.** Bị loại vì permission check chặn sai đối tượng. `tool_layer` kiểm tra *người đang dùng hệ thống* có permission không — và trong phiên chat của một `ADMIN_OFFICER`, người đó **có** `document.approve_content`. Một đoạn văn bản độc hại được dán vào chat có thể khiến model gọi thao tác duyệt nhân danh chính cán bộ đó, và permission check sẽ cho qua. Đây là bài toán *confused deputy*: người có quyền, còn ý định là của kẻ tấn công. Permission không phân biệt được hai thứ đó; chỉ việc không trao tool cho model mới phân biệt được.

**B — Chỉ trao tool đọc.** Bị loại vì tool đọc chính là kênh rò. Chỉ dẫn độc hại có thể khiến model gọi `employee_lookup` cho một nhân viên khác, rồi chèn kết quả vào output của nó. Không ghi gì cả, nhưng dữ liệu `PER`/`RES` của người thứ ba đã đi vào một chuỗi mà model kiểm soát. Tool đọc an toàn về toàn vẹn dữ liệu, không an toàn về bảo mật dữ liệu.
