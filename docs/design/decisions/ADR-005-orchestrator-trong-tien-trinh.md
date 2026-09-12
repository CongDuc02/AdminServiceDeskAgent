# ADR-005 — `orchestrator` là thư viện dùng chung trong `api`/`queue_worker`, không phải service riêng

**Trạng thái:** Accepted · **Ngày:** 2026-09-12 · **Quyết định tại:** Phase 2 — System Architecture · **Liên quan:** mục Ràng buộc domain bắt buộc phải xử lý và mục Tech stack của `CLAUDE.md`, A-025

---

## Context

`CLAUDE.md` yêu cầu LangGraph phải có `interrupt` để dừng chờ người duyệt và checkpointer trên PostgreSQL để resume **sau nhiều giờ hoặc nhiều ngày**. Câu hỏi kiến trúc: `orchestrator` có nên là một service riêng biệt — một "agent server" độc lập nhận request, giữ vòng đời chạy graph, trả kết quả — hay là một thư viện được gọi từ bên trong các thành phần khác?

Đây là quyết định dễ bị chọn theo quán tính (mọi hệ thống agent khác đều có một "orchestrator service"), nên cần viết đầy đủ chuỗi suy luận thay vì chỉ ghi kết luận.

## Chuỗi suy luận

1. **HITL bắt buộc dừng dài hạn.** Hai cổng `PENDING_APPROVAL` và `PENDING_SEAL` có thể dừng hàng giờ hoặc hàng ngày chờ người duyệt — không có nhánh auto-approve nào rút ngắn việc này (mục Bối cảnh đề tài của `CLAUDE.md`). Không tiến trình nào có thể giữ một luồng thực thi sống trong suốt khoảng thời gian đó.
2. **Checkpointer PostgreSQL đã giải quyết đúng vấn đề đó.** Theo yêu cầu domain, mọi bước của graph phải được tuần tự hoá và lưu vào checkpointer sau mỗi lần chạy tới `interrupt` hoặc hoàn tất. Nghĩa là **toàn bộ trạng thái cần để tiếp tục một cuộc hội thoại hay một luồng duyệt đã nằm ở PostgreSQL**, không nằm ở bộ nhớ của bất kỳ tiến trình nào.
3. **Vì vậy, việc "chạy graph" tự nó là không trạng thái giữa hai lần gọi.** Một lần gọi orchestrator chỉ là: nạp checkpoint ứng với `request`/`document` đó, chạy tới node kế tiếp hoặc tới `interrupt` tiếp theo, lưu lại checkpoint, rồi kết thúc lệnh gọi. Đây là đúng những gì một request handler trong `api` (cho một lượt chat) hoặc một job trong `queue_worker` (cho job render sau `SUBMITTED`) đã làm — không có việc gì còn lại đòi hỏi một tiến trình sống lâu riêng.
4. **Tách `orchestrator` thành service riêng chỉ có lý do nếu (a) cần giữ tài nguyên trong bộ nhớ giữa các lượt, hoặc (b) cần scale lưu lượng hội thoại độc lập với lưu lượng REST thường.** Cả hai đều không đúng ở đây: (a) bị loại bởi bước 2 — checkpointer đã đảm nhiệm; (b) chưa có căn cứ — A-002 chưa có số liệu tải để biết lưu lượng hội thoại có tách rời lưu lượng REST hay không.
5. **Vì (a) và (b) đều không đúng, tách riêng chỉ cộng thêm chi phí:** một Render service nữa phải deploy và giám sát, một network hop nữa cho mỗi lượt chat, mà không đổi lại được lợi ích nào ở quy mô hiện biết.

## Decision

**`orchestrator` là một thư viện Python dùng chung**, không phải một service triển khai riêng trên Render.

- Được gọi trực tiếp từ tiến trình xử lý request của `api` cho lượt chat đồng bộ (miễn là không chạm giới hạn thời gian request của Render — xem điều kiện đảo ngược).
- Được gọi từ `queue_worker` cho các job nền cần chạy graph (ví dụ bước sinh nội dung tự do sau khi `request` chuyển `SUBMITTED`, xem sequence diagram (b) của `02-architecture.md`).
- Cả hai lời gọi dùng chung một checkpointer PostgreSQL — một cuộc hội thoại có thể bắt đầu ở `api` và được resume từ `queue_worker`, hoặc ngược lại, mà không mất trạng thái.

## Consequences

**Tích cực**

- Không có network hop thêm cho mỗi lượt chat — độ trễ thấp hơn so với gọi qua một service riêng.
- Một Render service ít hơn phải deploy, version, giám sát.
- Logic graph, `tool_layer` và checkpointer nằm trong cùng một codebase — dễ giữ nhất quán khi state schema đổi (yêu cầu domain: "xử lý khi schema state thay đổi giữa chừng" — chi tiết ở Phase 3).

**Tiêu cực và cái phải chấp nhận**

- `api` và `queue_worker` cùng phụ thuộc trực tiếp vào thư viện `orchestrator` — thay đổi state schema graph ảnh hưởng cả hai nơi gọi, phải deploy đồng bộ.
- Nếu một lượt chạy graph (đặc biệt bước gọi model mạnh + RAG) kéo dài, nó chiếm một luồng xử lý request của `api` trong suốt thời gian đó — xem điều kiện đảo ngược.

**Điều kiện đảo ngược** — không phải "tách `orchestrator` thành service riêng", mà là "đổi *nơi gọi*":

Tín hiệu đảo ngược là khi một lượt thực thi graph (gọi model mạnh + retrieval) đủ lâu để tiệm cận giới hạn thời gian một request HTTP của Render. Giá trị cụ thể của giới hạn này **chưa xác minh, cấm ghi từ trí nhớ** (A-025). Khi tín hiệu này xuất hiện: lượt chat đó cần chuyển từ "chạy đồng bộ trong luồng xử lý request của `api`" sang "enqueue job, trả lời ngay, `queue_worker` chạy graph, cập nhật cho client qua SSE" — đúng mẫu đã dùng cho bước sinh nội dung tự do ở sequence diagram (b).

**Điểm mấu chốt cần giữ khi tín hiệu này xảy ra:** phần cần đổi là *tiến trình nào gọi thư viện `orchestrator`* (từ luồng request của `api` sang `queue_worker`), **không phải** tách `orchestrator` thành một service triển khai riêng — vì lý do kỹ thuật duy nhất từng có thể biện minh cho việc tách riêng (giữ trạng thái trong bộ nhớ) đã bị loại bỏ ngay từ bước 2 của chuỗi suy luận, và không đổi dù giới hạn thời gian request là bao nhiêu.

## Rejected alternatives

**`orchestrator` như một service riêng (kiểu "agent server" tách khỏi `api`).** Bị loại vì một lý do khác với ADR-002 và ADR-004: đây không phải vấn đề "thêm một hệ thống phải vận hành mà không đổi lại được gì" (dù điều đó cũng đúng) — mà là **toàn bộ lý do kỹ thuật thường dùng để biện minh cho việc tách một orchestrator ra khỏi API (giữ trạng thái hội thoại trong bộ nhớ, cô lập tài nguyên thực thi dài hạn) đã bị chính yêu cầu checkpointer PostgreSQL của domain vô hiệu hoá từ trước khi cân nhắc tới chi phí.** Nói cách khác: câu hỏi "có nên tách" không cần đi tới bước so sánh chi phí/lợi ích, vì tiền đề của việc tách (cần trạng thái sống trong bộ nhớ) đã sai ngay từ bước 2 của chuỗi suy luận.
