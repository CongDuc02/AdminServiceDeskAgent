# ADR-002 — `vector_store` là `pgvector` trong cùng PostgreSQL, không phải vector DB riêng

**Trạng thái:** Accepted · **Ngày:** 2026-09-12 · **Quyết định tại:** Phase 2 — System Architecture · **Sửa lập luận:** 2026-09-12, Phase 3 — quyết định giữ nguyên · **Liên quan:** mục Tech stack của `CLAUDE.md`, `02-architecture.md`, `03-agents.md`, A-027

---

## Context

`CLAUDE.md` liệt Vector DB vào danh sách công nghệ bắt buộc cho RAG, nhưng yêu cầu rõ: "Cân nhắc rõ `pgvector` vs vector DB ngoài, có so sánh chi phí." Đây không phải lựa chọn có sẵn đáp án — cần một quyết định có so sánh thật.

`vector_store` phục vụ đúng một việc: truy hồi kho quy trình hành chính (`procedure_document`) để `intake_agent` trả **hướng xử lý thủ công có trích nguồn** cho yêu cầu ngoài phạm vi (AC của F1). Nó **không** phục vụ việc chọn template — việc đó là tra cứu chính xác theo `request_type` và phiên bản đang hiệu lực — và **không** phục vụ bước soạn nội dung tự do (mục Retrieval của `03-agents.md`). Kho có thể rỗng (A-027). Kho thuộc một tổ chức (giả định A-001: một pháp nhân đơn nhất) — không phải một kho tri thức đa khách hàng.

**Bản đầu của ADR này (Phase 2) mô tả sai việc của `vector_store`:** nó giả định retrieval phục vụ bước soạn thảo và cả việc truy hồi template. Lập luận được sửa ở Phase 3; quyết định giữ nguyên. Lập luận đã bị bác được ghi lại ở Rejected alternatives.

## Options

**A — Vector DB ngoài** (dịch vụ vector database chuyên dụng, triển khai như một managed service riêng cạnh PostgreSQL).

**B — `pgvector`** (extension chạy trong cùng PostgreSQL managed đã có sẵn cho toàn bộ entity nghiệp vụ).

## Decision

**Chọn B.**

- `vector_store` không phải một thành phần triển khai riêng — nó là extension `pgvector` trong cùng instance PostgreSQL managed trên Render.
- Hybrid search (BM25 + vector) chạy được trong **một câu truy vấn SQL** kết hợp `tsvector` và `pgvector`, không cần join chéo hệ thống.
- Phiên bản đang hiệu lực của `procedure_document` và embedding của nó nằm trong cùng một cơ sở dữ liệu: điều kiện "chỉ phiên bản đang hiệu lực" là một mệnh đề trong cùng câu truy vấn, và việc kích hoạt phiên bản mới cùng tắt phiên bản cũ nằm trong một giao dịch.

## Consequences

**Tích cực**

- Một nguồn sự thật duy nhất cho cả metadata và vector — không có bài toán đồng bộ hai hệ thống khi `procedure_document` đổi phiên bản.
- Không thêm một managed service phải vận hành (backup, patch, giám sát riêng) trong lúc chưa có số liệu tải để biện minh cho nó (A-002).
- Chi phí thêm bằng 0 ngoài chi phí PostgreSQL đã trả — không có hoá đơn dịch vụ vector DB riêng.

**Tiêu cực và cái phải chấp nhận**

- Tải truy vấn vector và tải giao dịch nghiệp vụ (đọc/ghi `request`, `document`, ...) dùng chung tài nguyên CPU/IO của một instance.
- Reindex embedding (khi đổi embedding model, xem Phase 4) chạy trên cùng instance đang phục vụ giao dịch, không cô lập được.

**Điều kiện đảo ngược quyết định này** — không đặt được ngưỡng số vì chưa có số liệu tải thật (A-002); mô tả **hình dạng tín hiệu** thay vì con số:

- Truy vấn nghiệp vụ (không phải truy vấn retrieval) bắt đầu chậm đi rõ rệt đúng vào lúc retrieval được gọi nhiều — dấu hiệu hai loại tải đang tranh CPU/IO trên cùng instance.
- Reindex embedding cần đủ lâu tới mức ảnh hưởng thấy được lên độ trễ ghi giao dịch đang chạy song song.
- Phạm vi kho quy trình mở rộng vượt giả định A-001 (nhiều pháp nhân, nhiều kho tài liệu lớn độc lập) — khi đó bài toán không còn là "một kho quy trình nội bộ nhỏ, có thể rỗng" mà ADR này giả định.

Khi một trong ba tín hiệu trên xuất hiện, quyết định cần xét lại — không phải trước đó.

## Rejected alternatives

**Option A — Vector DB ngoài.** Bị loại vì **quy mô công việc không tương xứng với một hệ thống riêng**. `vector_store` chỉ phục vụ một nhánh của `intake_agent` — hướng xử lý thủ công cho yêu cầu ngoài phạm vi — trên một kho quy trình nội bộ **có thể rỗng** (A-027). Dựng và vận hành một managed service riêng, với credential, backup và giám sát riêng, cho một kho có thể không có tài liệu nào là đầu tư ngược chiều với bằng chứng hiện có. Lý do phụ: phiên bản đang hiệu lực của `procedure_document` phải khớp giữa metadata và embedding; tách hai hệ thống thì việc kích hoạt phiên bản mới không còn nguyên tử.

**Lập luận đã bị bác — ghi lại để không ai dựng lại.** Bản Phase 2 của ADR này lấy lý do chính là *"một nguồn sự thật cho phiên bản `template`"*: tách vector DB ra thì phiên bản template phải được đồng bộ giữa hai hệ thống. **Lập luận đó đã sập.** F2 buộc template được chọn bằng tra cứu chính xác theo `request_type` và phiên bản đang hiệu lực; template **không bao giờ đi qua vector search**, nên không có phiên bản template nào phải đồng bộ với embedding. Nó từng được viện dẫn nhầm vì Phase 2 mặc định rằng retrieval phục vụ bước soạn thảo và truy hồi cả template — một giả định chưa ai kiểm lại. Quyết định chọn `pgvector` không đổi; chỉ căn cứ của nó đổi. Lý do phụ ở đoạn trên là dạng yếu hơn của cùng lập luận, áp cho `procedure_document` chứ không cho `template`, và chỉ đứng được khi kho quy trình có tài liệu.
