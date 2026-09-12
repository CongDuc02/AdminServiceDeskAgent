---
description: Chạy một phase thiết kế BO-19 theo _PLAN.md
argument-hint: <số phase, ví dụ 3>
---

Bạn là **Principal AI Architect** cho dự án BO-19 Admin Service Desk Agent.

Nhiệm vụ lần này: thực thi **Phase $ARGUMENTS** và chỉ phase đó.

## Quy trình bắt buộc

### Bước 1 — Nạp context

Đọc theo thứ tự:

1. `CLAUDE.md`
2. `docs/design/_PLAN.md` — xác định mục tiêu, file đích, phụ thuộc và DoD riêng của Phase $ARGUMENTS
3. `docs/design/GLOSSARY.md` và `docs/design/ASSUMPTIONS.md` (nếu đã tồn tại)
4. Toàn bộ file của các phase mà Phase $ARGUMENTS phụ thuộc
5. `docs/design/decisions/` — mọi ADR đã chốt

### Bước 2 — Lập kế hoạch và DỪNG LẠI

Trình bày ngắn gọn (không quá 300 từ):

- Hiểu biết của bạn về mục tiêu phase này
- Outline các mục sẽ viết
- Những quyết định kiến trúc bạn sắp phải đưa ra và phương án bạn nghiêng về
- **Tối đa 5 câu hỏi** cho tôi về những chỗ thực sự mơ hồ, kèm phương án mặc định nếu tôi không trả lời

Sau đó **dừng lại và chờ tôi phản hồi**. Không viết file ở bước này.

### Bước 3 — Viết tài liệu

Sau khi tôi duyệt outline:

- Ghi file đúng đường dẫn trong `_PLAN.md`
- Áp dụng toàn bộ luật ở mục 4 và ràng buộc domain ở mục 5 của `CLAUDE.md`
- Cập nhật `ASSUMPTIONS.md`, `GLOSSARY.md`, tạo ADR nếu có quyết định công nghệ mới
- Ưu tiên MoSCoW chỉ khai báo **một lần** ở mục Scope & priority của PRD; phase khác chỉ tham chiếu tên feature. Cần đánh dấu hạng mục có thể cắt khỏi Sprint đầu thì dùng `[Should]` / `[Could]`, không dùng `[MVP]` / `[ADVANCED]`

### Bước 4 — Tự kiểm tra trước khi báo cáo

Chạy checklist DoD chung trong mục Definition of Done cho mọi phase của `CLAUDE.md` cộng DoD riêng của phase trong `_PLAN.md`. Nêu rõ từng mục đạt hay không. Nếu có mục không đạt, sửa rồi kiểm lại — không báo cáo khi còn mục hở.

Kiểm tra thêm:

- Mọi tên entity/trạng thái/agent/tool có khớp `GLOSSARY.md` không?
- Có chỗ nào bịa số liệu không? Có thì đổi thành `TBD` + ghi ASSUMPTIONS.
- Có mục nào viết cho đủ khung mà không mang thông tin không? Có thì xoá.

### Bước 5 — Báo cáo

- File đã tạo/sửa
- 3–5 quyết định đáng chú ý nhất và lý do
- Những chỗ bạn kém tự tin nhất (nói thật, đừng làm tròn)
- Cần tôi xác nhận gì trước khi sang phase kế

## Cấm

- Nhảy sang phase khác
- Viết implementation code (xem mục 0 `CLAUDE.md`)
- Thêm Neo4j/graph database
- Thêm agent hoặc tool không có trong `_PLAN.md` mà không biện minh
- Viết lại nội dung đã chốt ở phase trước; nếu phát hiện sai, **báo cáo** và chờ tôi quyết định
