# ADR-001 — Khung thể thức nằm trong template `.docx`, agent chỉ điền biến

**Trạng thái:** Accepted · **Ngày:** 2026-09-11 · **Quyết định bởi:** Product Owner · **Liên quan:** mục Cấp số văn bản của `00-domain.md`, A-009, A-018

---

## Context

Văn bản hành chính có hai phần bản chất khác nhau:

| Phần | Ví dụ | Tính chất |
|---|---|---|
| **Khung thể thức** | Quốc hiệu, tiêu ngữ, tên cơ quan, số và ký hiệu văn bản, địa danh và ngày tháng, nơi nhận, quyền hạn và chức vụ người ký | Do pháp luật quy định. Sai là văn bản vô hiệu. Gần như không đổi giữa các văn bản cùng loại |
| **Nội dung tự do** | Lý do, mục đích, nội dung công việc cụ thể, phạm vi giới thiệu | Thay đổi theo từng yêu cầu. Không có chuẩn pháp lý về câu chữ |

Thể thức văn bản hành chính do Nghị định 30/2020/NĐ-CP quy định. Tại thời điểm viết ADR này, **văn bản gốc chưa có trong `docs/reference/`**, nên tài liệu thiết kế không được phép ghi cấu trúc cụ thể của bất kỳ thành phần thể thức nào — xem mục "Quy tắc trích dẫn" bên dưới.

Câu hỏi cần quyết: ai chịu trách nhiệm sinh ra phần khung thể thức — LLM, hay template?

Đây là quyết định có rủi ro bất đối xứng. Nội dung tự do sai thì người duyệt đọc và sửa được. Khung thể thức sai — thiếu tiêu ngữ, sai vị trí số và ký hiệu, sai cách ghi nơi nhận — thì văn bản mất giá trị pháp lý, và lỗi loại này khó phát hiện bằng mắt vì trông vẫn "giống văn bản thật".

## Options

**Option A — LLM sinh toàn bộ văn bản, kể cả khung thể thức.**
Prompt mô tả đầy đủ thể thức, model sinh ra văn bản hoàn chỉnh.

**Option B — Template `.docx` giữ khung thể thức, agent chỉ điền biến.**
Người soạn template dựng sẵn toàn bộ khung đúng thể thức. Agent điền giá trị vào các biến đã khai báo. Prompt LLM chỉ sinh phần nội dung tự do, và phần đó cũng đi vào một biến.

**Option C — Lai: template giữ khung, nhưng LLM được phép chỉnh khung khi "thấy cần".**
Ví dụ tự thêm dòng nơi nhận, tự đổi cách ghi ngày tháng cho hợp ngữ cảnh.

## Decision

**Chọn Option B.**

- Khung thể thức — quốc hiệu, tiêu ngữ, tên cơ quan, số và ký hiệu, nơi nhận, phần chữ ký — **nằm trong file template `.docx` do người soạn**, không do model sinh.
- Agent **chỉ điền biến** đã được khai báo trong template. Agent không tạo biến mới, không sửa văn bản ngoài vùng biến, không đổi bố cục.
- Prompt soạn thảo ở Phase 7 **chỉ sinh phần nội dung tự do**: lý do, mục đích, nội dung công việc cụ thể. Phần này cũng được đưa vào template qua một biến.
- Vì vậy **thể thức văn bản không thuộc phạm vi Phase 7.** Phase 7 không viết prompt mô tả thể thức, không kiểm tra thể thức trong output validation, và không nhận trách nhiệm về thể thức.
- Mẫu `.docx` đúng thể thức do **Product Owner chuẩn bị trước Phase 7**.

### Quy tắc trích dẫn kèm theo quyết định này

Cấm viết số điều, khoản, điểm hay phụ lục của Nghị định 30/2020/NĐ-CP **từ trí nhớ**. Chỉ được trích dẫn khi văn bản gốc đã được đặt vào `docs/reference/`. Chưa có thì ghi `[CẦN XÁC MINH]` và mô tả ở mức nguyên tắc, không ở mức điều khoản. Quy tắc này áp dụng cho mọi phase, không riêng Phase 7.

## Consequences

**Tích cực**

- Rủi ro pháp lý cao nhất của dự án rời khỏi vùng LLM. Không có prompt nào, không có model nào, không có nhiệt độ sinh nào ảnh hưởng được tới khung thể thức.
- Thể thức trở thành thứ **kiểm tra được bằng mắt một lần** khi duyệt template, thay vì phải kiểm tra lại trên từng văn bản sinh ra.
- Phase 7 thu hẹp đáng kể: chỉ còn lo phần nội dung tự do, nơi mà sai sót có thể sửa được.
- Chi phí LLM giảm — không sinh lại phần khung lặp đi lặp lại ở mọi văn bản.
- Template versioning (đã có trong mục Ràng buộc domain bắt buộc phải xử lý của `CLAUDE.md`) trở thành cơ chế quản lý thể thức: đổi thể thức là ra phiên bản template mới, có vết.

**Tiêu cực và cái phải chấp nhận**

- **Hệ thống phụ thuộc vào chất lượng template.** Template sai thể thức thì mọi văn bản sinh ra từ nó đều sai, và agent không có cách nào phát hiện. Đây là điểm lỗi tập trung, đã ghi thành A-018.
- Thêm một loại yêu cầu mới lệ thuộc vào việc có người soạn được template đúng thể thức, không phải việc viết thêm prompt.
- Biến mới trong nghiệp vụ đòi hỏi sửa template, không sửa được bằng prompt. Chậm hơn nhưng có chủ đích.
- Phase 4 phải thiết kế `document_register` với **định dạng số cấu hình được ngay từ đầu**, vì ký hiệu văn bản chứa phần viết tắt tên cơ quan — khác nhau theo từng tổ chức nên hardcode là sai trong mọi trường hợp. Đây **không** phải chi phí phát sinh mà là yêu cầu gốc.

**Rủi ro còn lại sau khi đã giảm thiểu**

Hệ thống **không bao giờ tự khẳng định một văn bản đúng thể thức**. Chốt kiểm soát là HITL: cán bộ hành chính duyệt tại cổng `PENDING_APPROVAL` trước khi phát hành. Residual risk sau chốt này: nếu bản thân template sai thể thức **và** cán bộ hành chính không phát hiện khi duyệt, văn bản sai vẫn được phát hành. Không có lớp kiểm soát tự động nào phía sau — hệ thống không có khả năng thẩm định thể thức. Rủi ro này được chấp nhận có ý thức, và sẽ vào mục Risk register của PRD.

## Rejected alternatives

**Option A — LLM sinh toàn bộ văn bản.** Bị loại vì đặt rủi ro pháp lý không hồi phục được vào tay một thành phần bất định. Thể thức không có lý do gì phải sinh động: nó cố định theo loại văn bản. Dùng model để tái tạo một thứ cố định là đổi tính đúng đắn lấy sự tiện lợi, sai hướng với ràng buộc "sai thể thức = văn bản vô hiệu" ở mục Bối cảnh đề tài của `CLAUDE.md`. Thêm nữa, muốn viết được prompt này thì phải mô tả thể thức bằng chữ trong prompt, mà tại thời điểm này chưa ai xác minh được thể thức — nghĩa là prompt sẽ được viết từ trí nhớ của model.

**Option C — Lai, cho LLM chỉnh khung khi thấy cần.** Bị loại vì nó xoá sạch lợi ích của Option B mà vẫn giữ nguyên chi phí. Một khi model được phép chạm vào khung, không còn kiểm tra được thể thức ở mức template nữa, và người duyệt lại phải soi lại từng văn bản. "Khi thấy cần" cũng không phải một điều kiện định nghĩa được, nên không kiểm thử được ở Phase 10.
