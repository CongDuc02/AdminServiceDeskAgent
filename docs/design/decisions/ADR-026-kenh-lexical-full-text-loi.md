# ADR-026 — Kênh lexical của hybrid search: full-text lõi của PostgreSQL, chưa phải BM25

**Trạng thái:** Accepted · **Ngày:** 2026-09-26 · **Duyệt:** PO, 2026-09-26 — `Proposed` → `Accepted`; PO tự sửa `CLAUDE.md` trỏ về ADR này · **Quyết định tại:** đợt sửa 1 sau Phase 13 (AUD-09 của `13-audit.md`) · **Liên quan:** ADR-002 (hybrid search trong một câu SQL), ADR-012 (vector collection), A-028 (embedding model), A-030 (năng lực text search tiếng Việt trên Render), mục Vector collection của `04-data.md`, mục Retrieval của `03-agents.md`, mục Ràng buộc domain bắt buộc phải xử lý của `CLAUDE.md`

> **ADR này lệch khỏi `CLAUDE.md`.** Mục Ràng buộc domain bắt buộc phải xử lý của `CLAUDE.md` ghi "hybrid search (BM25 + vector)". Quyết định dưới đây **không** dùng BM25 cho kênh lexical ở Sprint đầu. Theo luật 11, `CLAUDE.md` không được sửa ở đây — PO sửa file đó để trỏ về ADR này.

---

## Context

Hybrid search có hai kênh: kênh vector trên `pgvector` và kênh lexical trên văn bản. Nó phục vụ đúng một việc — hướng xử lý thủ công có trích nguồn cho yêu cầu ngoài phạm vi (mục Retrieval của `03-agents.md`) — trên một kho quy trình có thể rỗng (A-027).

Ba nơi đang nói ba điều khác nhau về kênh lexical:

- `CLAUDE.md` bắt buộc BM25.
- ADR-002, phần Decision, khẳng định "hybrid search (BM25 + vector) chạy được trong một câu truy vấn SQL".
- `04-data.md`, mục Hybrid search, đã chọn — không qua ADR — "hàm xếp hạng full-text lõi của PostgreSQL, **không phải BM25**, cho tới khi A-030 xác minh".

Chọn một kênh lexical khác thứ `CLAUDE.md` liệt kê là một quyết định công nghệ, nên luật 4 đòi ADR. `13-audit.md` ghi lỗi này là AUD-09.

**Điều đã biết và điều chưa biết.** PostgreSQL có sẵn full-text search lõi: kiểu `tsvector`, cấu hình `simple`, index GIN, và hàm xếp hạng sẵn có. `04-data.md` đã dựng cột `lexical_tsv` trên văn bản do ứng dụng chuẩn hoá và bản không dấu. **Chưa xác minh:** PostgreSQL managed trên Render có extension nào cung cấp xếp hạng BM25 không, và công cụ tách từ tiếng Việt nào chạy được ở đó (A-030, `[CẦN XÁC MINH]`). ADR này không nêu tên extension nào — không có bản gốc trong `docs/reference/`.

**Việc của kênh lexical ở dự án này** (mục Kênh lexical có việc gì của `03-agents.md`): khớp chính xác thuật ngữ hành chính và tên gọi riêng của thủ tục trong kho quy trình. Lý do `CLAUDE.md` nêu — mã nhân viên và tên riêng — không có đối tượng ở đây: tra nhân viên đi bằng SQL chính xác, và dữ liệu nhân viên bị cấm có mặt trong kho vector. PO đã quyết giữ nguyên `CLAUDE.md` ở Phase 3; ADR này không mở lại quyết định đó.

## Options

- **A — Full-text lõi của PostgreSQL.** `tsvector` cấu hình `simple`, index GIN, hàm xếp hạng sẵn có, trên văn bản do ứng dụng chuẩn hoá cộng bản không dấu. Gộp với kênh vector theo thứ hạng (reciprocal rank fusion). Đây là thứ `04-data.md` đang có.
- **B — BM25 qua một extension của PostgreSQL.** Tên extension và việc Render có hỗ trợ nó hay không: `[CẦN XÁC MINH]` (A-030).
- **C — Kênh lexical lấy từ biểu diễn thưa do chính model embedding sinh ra** — lối thoát đã ghi ở A-030, với điều kiện model được chọn (A-028) có năng lực đó (`[CẦN XÁC MINH]` theo model card).
- **D — Tính BM25 ở tầng ứng dụng**, trên tập ứng viên do SQL trả về.

## Decision

**Chọn A** — PO duyệt 2026-09-26.

- Kênh lexical ở Sprint đầu là full-text lõi của PostgreSQL, đúng như `04-data.md` mục Vector collection đã dựng. Không thêm cột, index hay extension nào.
- Tài liệu gọi đúng tên nó: **"xếp hạng full-text lõi"**, không gọi là BM25. Câu Decision của ADR-002 và mục Thành phần — `vector_store` của `02-architecture.md` được sửa theo.
- Giữ nguyên hai tính chất mà ADR-002 dựa vào: hai kênh chạy trong **một câu SQL**, và lọc quyền chạy **trước** khi xếp hạng (mục Lọc quyền và so khớp phòng ban của `04-data.md`).
- Gộp theo thứ hạng, không cộng điểm thô. Tham số và `top_k` theo A-031.

## Consequences

**Tích cực**

- Không phụ thuộc một extension chưa xác minh trên Render. `schema.sql` và mọi migration chạy được trên PostgreSQL managed như hôm nay — cùng lý do ADR-012 không thêm index ANN trước khi cần.
- Kho rỗng vẫn đúng (A-027): không index nào cần dữ liệu mẫu.
- Không có hệ thống hay tiến trình thứ hai phải đồng bộ với `procedure_chunk`.

**Tiêu cực và cái phải chấp nhận**

- **Lệch khỏi `CLAUDE.md`** — ghi ở đầu file, PO xử lý.
- Hàm xếp hạng full-text lõi không phải BM25. Chênh lệch chất lượng giữa hai cách trên tiếng Việt hành chính **chưa đo** — không có số liệu, không ghi số nào.
- Cấu hình `simple` không tách từ tiếng Việt: thuật ngữ nhiều âm tiết khớp theo từng âm tiết. Bản không dấu làm tín hiệu phụ bù cho câu gõ không dấu, không bù được việc thiếu tách từ.

**Điều kiện đảo ngược**

- *Tín hiệu kiến trúc:* A-030 xác minh được một extension BM25 khả dụng trên PostgreSQL managed của Render — xét B.
- *Tín hiệu đo:* phương pháp `recall@k` ở mục Bộ đo retrieval của `10-eval.md`, chạy trên kho thật, cho thấy kênh lexical không đưa được đoạn đúng vào top-k ở các câu hỏi dựa vào thuật ngữ chính xác — xét B hoặc C.
- *Tín hiệu chọn model:* model embedding được chọn ở A-028 sinh được biểu diễn thưa — xét C. C đổi luôn câu "hai kênh trong một câu SQL" của ADR-002, nên đảo sang C cần sửa cả ADR-002.

## Rejected alternatives

**B — BM25 qua extension.** Không bị loại vì kém. Bị hoãn vì **chưa xác minh được trên nền tảng triển khai**: chọn nó hôm nay là đặt cược kiến trúc vào một tính năng chưa có nguồn — cùng lý do ADR-003 loại phương án dựa vào tính năng riêng của nhà cung cấp. Giữ làm hướng đảo ngược thứ nhất.

**C — Biểu diễn thưa từ model embedding.** Phụ thuộc hai việc chưa đóng: chọn model (A-028) và năng lực của model đó (`[CẦN XÁC MINH]`). Nó còn kéo thêm một bên thứ ba vào kênh lexical nếu model do nhà cung cấp chạy — cùng câu hỏi PII đã ghi ở A-028. Giữ làm hướng đảo ngược.

**D — BM25 ở tầng ứng dụng.** Mất tính chất "hai kênh trong một câu SQL" của ADR-002 mà không được gì chắc hơn A. Tính BM25 cần thống kê trên toàn kho — tần suất tài liệu, độ dài trung bình — nên hoặc phải giữ một chỉ mục trong bộ nhớ tiến trình (trái nguyên tắc không giữ trạng thái giữa hai lượt của ADR-005, và chịu cold start), hoặc chỉ tính trên tập ứng viên SQL đã trả, khi đó thứ hạng không còn là BM25 đúng nghĩa.
