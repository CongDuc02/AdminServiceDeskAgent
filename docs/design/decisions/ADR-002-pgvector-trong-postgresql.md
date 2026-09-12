# ADR-002 — `vector_store` là `pgvector` trong cùng PostgreSQL, không phải vector DB riêng

**Trạng thái:** Accepted · **Ngày:** 2026-09-12 · **Quyết định tại:** Phase 2 — System Architecture · **Liên quan:** mục Tech stack của `CLAUDE.md`, `02-architecture.md`

---

## Context

`CLAUDE.md` liệt Vector DB vào danh sách công nghệ bắt buộc cho RAG, nhưng yêu cầu rõ: "Cân nhắc rõ `pgvector` vs vector DB ngoài, có so sánh chi phí." Đây không phải lựa chọn có sẵn đáp án — cần một quyết định có so sánh thật.

`vector_store` phục vụ đúng một việc trong phạm vi Sprint đầu: embedding kho mẫu văn bản và quy định hành chính, phục vụ hybrid search (BM25 + vector) cho bước sinh nội dung tự do ở F2. Kho dữ liệu này thuộc một tổ chức, một kho mẫu nội bộ (giả định A-001: một pháp nhân đơn nhất) — không phải một kho tri thức đa khách hàng.

## Options

**A — Vector DB ngoài** (dịch vụ vector database chuyên dụng, triển khai như một managed service riêng cạnh PostgreSQL).

**B — `pgvector`** (extension chạy trong cùng PostgreSQL managed đã có sẵn cho toàn bộ entity nghiệp vụ).

## Decision

**Chọn B.**

- `vector_store` không phải một thành phần triển khai riêng — nó là extension `pgvector` trong cùng instance PostgreSQL managed trên Render.
- Hybrid search (BM25 + vector) chạy được trong **một câu truy vấn SQL** kết hợp `tsvector` và `pgvector`, không cần join chéo hệ thống.
- `template` đã có versioning trong PostgreSQL (mục Vòng đời của `00-domain.md`); embedding của nó nằm cùng chỗ với bản ghi metadata, nên không có nguy cơ hai nguồn sự thật lệch nhau về việc "phiên bản nào đang hiệu lực".

## Consequences

**Tích cực**

- Một nguồn sự thật duy nhất cho cả metadata và vector — không có bài toán đồng bộ hai hệ thống khi `template` đổi phiên bản.
- Không thêm một managed service phải vận hành (backup, patch, giám sát riêng) trong lúc chưa có số liệu tải để biện minh cho nó (A-002).
- Chi phí thêm bằng 0 ngoài chi phí PostgreSQL đã trả — không có hoá đơn dịch vụ vector DB riêng.

**Tiêu cực và cái phải chấp nhận**

- Tải truy vấn vector và tải giao dịch nghiệp vụ (đọc/ghi `request`, `document`, ...) dùng chung tài nguyên CPU/IO của một instance.
- Reindex embedding (khi đổi embedding model, xem Phase 4) chạy trên cùng instance đang phục vụ giao dịch, không cô lập được.

**Điều kiện đảo ngược quyết định này** — không đặt được ngưỡng số vì chưa có số liệu tải thật (A-002); mô tả **hình dạng tín hiệu** thay vì con số:

- Truy vấn nghiệp vụ (không phải truy vấn retrieval) bắt đầu chậm đi rõ rệt đúng vào lúc retrieval được gọi nhiều — dấu hiệu hai loại tải đang tranh CPU/IO trên cùng instance.
- Reindex embedding cần đủ lâu tới mức ảnh hưởng thấy được lên độ trễ ghi giao dịch đang chạy song song.
- Phạm vi kho mẫu mở rộng vượt giả định A-001 (nhiều pháp nhân, nhiều kho tài liệu lớn độc lập) — khi đó bài toán không còn là "một kho mẫu nội bộ nhỏ" mà ADR này giả định.

Khi một trong ba tín hiệu trên xuất hiện, quyết định cần xét lại — không phải trước đó.

## Rejected alternatives

**Option A — Vector DB ngoài.** Bị loại không chỉ vì chi phí vận hành một hệ thống nữa (dù đúng), mà vì nó tạo ra **hai nguồn sự thật cho cùng một khái niệm phiên bản**: `template.manage` (F6) yêu cầu văn bản đã render ghi lại đúng phiên bản template đã dùng, và phiên bản đó phải khớp giữa nơi lưu metadata (PostgreSQL) và nơi lưu embedding (vector DB ngoài). Giữ đồng bộ hai hệ thống cho đúng một sự kiện "đổi phiên bản template" là rủi ro không cần thiết khi bài toán đủ nhỏ để một PostgreSQL managed xử lý được cả hai vai trò.
