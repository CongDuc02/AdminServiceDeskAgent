# ADR-012 — Một collection một cột cố định, đổi model là tạo phiên bản collection mới

**Trạng thái:** Accepted · **Ngày:** 2026-09-12 · **Quyết định tại:** Phase 4 — Data Architecture · **Sửa lập luận:** 2026-09-13, vòng duyệt Phase 4 (T1) — quyết định giữ nguyên · **Liên quan:** ADR-002, A-027, A-028, A-037, mục Retrieval của `03-agents.md`, `docs/reference/pgvector-dimension-limits.md`

---

## Context

`vector_store` có đúng một việc: hướng xử lý thủ công có trích nguồn cho yêu cầu ngoài phạm vi (ADR-002). Kho `procedure_document` **chưa tồn tại và có thể không bao giờ tồn tại** (A-027). Embedding model chưa chọn; trần số chiều đã chốt là n ≤ 1024, không dùng `halfvec` ở Sprint đầu (A-028).

Nguồn đã ghim ở `docs/reference/pgvector-dimension-limits.md` nói ba điều liên quan:

- Mục 4: cột kiểu `vector` **không khai chiều** lưu được vector khác chiều, và index được các dòng cùng số chiều **bằng index biểu thức và index partial**, kèm lệnh mẫu `CREATE INDEX ON embeddings USING hnsw ((embedding::vector(3)) vector_l2_ops) WHERE (model_id = 123);`. Ví dụ truy vấn đi kèm lặp lại **cả** biểu thức ép kiểu **lẫn** điều kiện partial.
- Mục 1: index HNSW nhận kiểu `vector` tới 2,000 chiều.
- Mục 6: từ bản 0.4.0 trần chiều của index tăng từ 1024 lên 2000.

## Options

**A — Cột `vector` không khai chiều**, nhiều model dùng chung một bảng, mỗi model một index biểu thức cộng partial.

**B — Một collection = một model = một cột `vector(n)` cố định.** Mỗi phiên bản collection là một bảng riêng. Đổi model là một migration **tạo bảng mới**, nạp lại, rồi đổi collection hiện hành trong một giao dịch. Không alter bảng cũ.

## Decision

**Chọn B.** Phiên bản đầu là bảng `procedure_chunk_embedding_v1` với cột `vector(1024)`.

- **Phiên bản đầu không có index ANN — tìm chính xác.** Hai lý do, cả hai đang có hiệu lực: kho rỗng hoặc nhỏ (A-027), nên quét toàn bộ có chi phí bị chặn bởi kích thước kho; và sai số xấp xỉ của index ANN sẽ trộn vào phép đo model ở Phase 10 — recall@k phải đo **model**, không đo **index**.
- **Vì vậy, hôm nay cột cố định là một ràng buộc ĐỀ PHÒNG.** Việc chính nó gánh — để khi cần index thì đánh được ngay trên cột đang có, **không phải migrate cột** — **chưa có hiệu lực**, vì chưa có index nào. Hôm nay nó chỉ gánh một việc nhỏ: cho bước kiểm lúc khởi động (dưới đây) một con số thật trong DDL để so với bản khai. Cột cố định có từ chối vector sai chiều lúc ghi hay không là hành vi thư viện **không có** trong nguồn đã ghim — `[CẦN XÁC MINH]`, không được tính là lý do.
- **Vì sao chọn n = 1024 vẫn an toàn kể cả khi chọn sai:** A-027. Chi phí của một phiên bản collection mới bị chặn trên bởi kích thước kho quy trình — rỗng hoặc gần rỗng. Chọn sai n thì cái giá là một migration tạo bảng và một lần nạp lại một kho nhỏ, không phải một cuộc di trú dữ liệu. **Lý do phụ:** theo thông số anh cung cấp, cả năm ứng viên ở A-028 đều ra được 1024 chiều — còn `[CẦN XÁC MINH]` theo model card, nên chỉ là lý do phụ.
- **`dimension` trong `embedding_collection` là một bản khai, không phải một tham số đổi được.** Nó phải khớp với n thật của cột trong DDL. `api` và `queue_worker` kiểm sự khớp này lúc khởi động; lệch thì **từ chối chạy**, không chạy tiếp kèm cảnh báo.
- **Không alter DDL đã có.** Đổi model là thêm một bảng qua migration; bảng cũ bị bỏ bằng một migration sau, khi collection mới đã hiện hành.
- **Khoảng cách:** L2 trên vector đã được chuẩn hoá về độ dài đơn vị trước khi ghi và trước khi truy vấn. Với vector độ dài đơn vị, thứ tự theo L2 trùng thứ tự theo cosine — tính chất toán học, không phụ thuộc thư viện. Toán tử và opclass L2 là thứ có nguyên văn trong nguồn đã ghim (mục 4: `vector_l2_ops`, `<->`). Model nào đòi thước đo khác thì đó là một phiên bản collection mới.

**Tín hiệu kích hoạt index ANN.** Latency của `procedure_retrieval` đặt cạnh số chunk đang hiệu lực, trên cùng một trục thời gian — dòng ADR-012 ở bảng chỗ quan sát của Phase 11 trong `_PLAN.md`. Chưa có ngưỡng (A-002, A-031); khi có số liệu thật thì ngưỡng được đặt lên **đúng metric đó**. Khi tín hiệu phát ra: một migration tạo index HNSW trên cột `embedding` của bảng collection hiện hành, opclass L2. **Kể từ lúc đó** cột cố định mới bắt đầu gánh việc chính của nó, giới hạn chiều của index ở mục 1 và mục 6 của nguồn bắt đầu có hiệu lực, và A-037 thành ràng buộc cứng. Với n = 1024, nguồn cho thấy index được trên mọi phiên bản nó mô tả, kể cả bản trước 0.4.0.

**Đừng gỡ ràng buộc này vì hôm nay nó không gánh gì.** Một ràng buộc không có lý do đang hoạt động rất dễ bị gỡ, nên câu này được viết ngay tại đây. Đổi cột về không khai chiều "cho linh hoạt, vì đằng nào cũng chưa có index" là dời chi phí migrate cột tới đúng lúc tín hiệu ANN phát ra — tức lúc kho đã lớn và việc migrate đắt nhất. Muốn gỡ thì phải có ADR thay thế ADR này.

## Consequences

**Tích cực**

- Khi có index, truy vấn viết thẳng trên cột, không có biểu thức nào phải lặp lại đúng từng ký tự để index được dùng.
- **A-037 hôm nay không chặn gì — vì chưa có index ANN, không vì giới hạn phiên bản.** Nó thành ràng buộc cứng kể từ lúc có index; khi đó `vector(1024)` nằm trong giới hạn của mọi phiên bản mà nguồn mô tả.
- Kho rỗng không làm hỏng migration, truy vấn hay bước nạp lại nào: bảng rỗng, không có index cần dữ liệu mẫu.

**Tiêu cực và cái phải chấp nhận**

- Đổi model cần một migration và một lần deploy, không chỉ sửa cấu hình.
- Số chiều không còn là cấu hình thuần như bản đầu của A-028 viết; cấu hình chỉ khai lại con số mà DDL đã quyết.
- Hai model chạy song song cần hai bảng; không trộn được trong một bảng.
- Dự án mang một ràng buộc mà lý do chính chưa có hiệu lực. Cái giá là phải bảo vệ nó bằng văn bản — đoạn "Đừng gỡ ràng buộc này" ở trên.

**Điều kiện đảo ngược** — tín hiệu nghiệp vụ, đo ở quyết định chọn model của Phase 10 (A-028): cần chạy **song song** hai model trên truy vấn thật, hoặc đổi model thường xuyên tới mức mỗi lần một migration thành gánh nặng. Khi đó xét lại Option A. Tín hiệu kích hoạt index ANN ở phần Decision **không** phải điều kiện đảo ngược: nó kích hoạt thứ mà ADR này được dựng ra để đón.

## Rejected alternatives

**A — Cột không khai chiều cộng index biểu thức.** Về mặt cơ chế, phương án này **đứng được**: nguồn xác nhận index biểu thức tạo được. Nó bị loại vì hai lý do khác, không vì bất khả thi:

1. **Phạm vi.** Sprint đầu có một collection, một model, và kho có thể không bao giờ tồn tại (A-027). Dựng hạ tầng nhiều collection trộn số chiều cho một tình huống chưa có là vi phạm luật "không nhồi" của `CLAUDE.md`.
2. **Nghĩa vụ phía truy vấn.** Ví dụ truy vấn của chính nguồn lặp lại cả biểu thức ép kiểu lẫn điều kiện partial. Mỗi câu truy vấn trong code phải khớp đúng biểu thức của index; quy tắc khớp của planner là `[CẦN XÁC MINH]` vì tài liệu PostgreSQL chưa có trong `docs/reference/`. Hỏng ở chỗ này không làm truy vấn trả sai — nó chỉ làm truy vấn không dùng index, nên không test chức năng nào bắt được. Đó đúng là họ lỗi "cơ chế có trên giấy nhưng không kích hoạt" đã ghi trong `CHANGELOG.md`.

**Nói thẳng:** lý do 2 cũng chỉ có hiệu lực **khi có index** — không có index thì cột không khai chiều cũng không đòi truy vấn lặp biểu thức nào. Lựa chọn giữa A và B hôm nay vì thế được quyết bằng những lý do nhìn về lúc có index, cùng tính chất đề phòng như chính quyết định. Đó là lý do đoạn "Đừng gỡ ràng buộc này" tồn tại.
