# ADR-006 — Hai agent: `intake_agent` và `drafting_agent`

**Trạng thái:** Accepted · **Ngày:** 2026-09-12 · **Quyết định tại:** Phase 3 — Agent & Tool Architecture · **Liên quan:** NFR-05, NFR-06 của `01-prd.md`, D-010, ADR-005, ADR-007, ADR-008

---

## Context

`_PLAN.md` yêu cầu bắt đầu từ giả thuyết "một agent + nhiều tool" và chỉ tách agent khi chứng minh được khác biệt ở ít nhất một trong bốn trục: prompt, quyền truy cập tool, model, ranh giới HITL.

Hệ thống có ba chặng việc: tiếp nhận hội thoại trước `SUBMITTED`; soạn nội dung tự do sau `SUBMITTED` (D-010); và mọi bước từ duyệt nội dung tới phát hành.

## Options

**A — Một agent** giữ mọi prompt, mọi tool, chọn model theo từng lời gọi.

**B — Hai agent**: `intake_agent` cho chặng tiếp nhận, `drafting_agent` cho chặng soạn nội dung tự do. Chặng sau duyệt không có agent.

**C — Nhiều agent chuyên biệt hơn**: tách thêm agent phân loại, agent trích slot, agent retrieval, agent kiểm tra bản nháp (critic).

## Decision

**Chọn B.** Ranh giới tiếp nhận / soạn thảo khác nhau ở **cả bốn trục**:

| Trục | `intake_agent` | `drafting_agent` |
|---|---|---|
| Input | Bắt buộc đọc tin nhắn thô | **Cấm** thấy tin nhắn thô — chỉ nhận slot khai đích danh |
| Model | Rẻ (NFR-06) | Mạnh (NFR-06) |
| Tool | Ghi slot vào `request`, tra `employee` | Không tra `employee`, không ghi `request`; ghi bản nháp `document` |
| Ranh giới HITL | Output đi qua xác nhận của nhân viên trước `SUBMITTED` | Output là thứ đi vào cổng `PENDING_APPROVAL` |

Cộng thêm khác biệt về nơi chạy: `intake_agent` chạy trong luồng request của `api`, `drafting_agent` chạy trong `queue_worker` (D-010, ADR-005).

Chặng từ `PENDING_APPROVAL` trở đi **không có agent nào** — chỉ có node tất định và thao tác cổng do người thật thực hiện (bất biến INV-01 ở `03-agents.md`).

## Consequences

**Tích cực**

- Bất đối xứng input là lý do mạnh nhất: nếu một agent làm cả hai chặng, allowlist của bước soạn thảo phải được định nghĩa bằng cách *trừ* tin nhắn thô khỏi thứ agent đang mang — tức một bộ lọc, thứ ADR-008 đã loại. Tách agent làm cho "soạn thảo không thấy hội thoại" đúng theo cấu tạo.
- Tập tool của mỗi agent nhỏ và khai được, nên kiểm tra "tool nào nằm trước/sau cổng HITL" đọc được trực tiếp từ registry.

**Tiêu cực và cái phải chấp nhận**

- Hai bộ prompt module, hai cấu hình model, hai điểm theo dõi chi phí.
- Hai graph LangGraph (`intake_graph`, `document_graph`) với hai loại thread; `api` và `queue_worker` phải deploy đồng bộ (đã chấp nhận ở ADR-005).

**Điều kiện đảo ngược** — tín hiệu nghiệp vụ, đo tại cấu hình `request_type` (F6), không phải ở observability:

- Có một `request_type` mà biến nội dung tự do của nó **không khai được từ slot** — tức bước soạn thảo buộc phải đọc hội thoại. Khi đó bất đối xứng input, lý do chính của việc tách, không còn đúng cho loại đó.

## Rejected alternatives

**A — Một agent.** Bị loại vì bất đối xứng input: một agent mang cả tin nhắn thô lẫn nhiệm vụ soạn thảo thì allowlist của chặng soạn thảo chỉ có thể là bộ lọc trừ bớt, và bộ lọc hỏng theo hướng rò dữ liệu (ADR-008).

**C — Nhiều agent chuyên biệt.** Bị loại từng cái một, mỗi cái một lý do:

- *Tách phân loại khỏi trích slot:* cùng input (tin nhắn thô lượt hiện tại), cùng model rẻ, cùng phía cổng. Không trục nào khác nhau — chỉ là hai prompt module của cùng một agent.
- *Tách soạn lần đầu khỏi soạn lại:* cùng model, cùng slot input; soạn lại chỉ thêm hai input đích danh (bản cũ của biến và lý do sửa). Khác prompt, không khác gì khác.
- *Agent retrieval:* retrieval là một lời gọi tool với câu truy vấn đã xác định, không có quyết định nào để một agent đưa ra.
- *Agent critic kiểm tra bản nháp:* một LLM chấm LLM tạo ra cảm giác "đã kiểm tra" mà không kiểm chứng được, trùng vai với HITL, và đi ngược nguyên tắc hệ thống không bao giờ tự khẳng định văn bản đúng (ADR-001). Kiểm tra bản nháp là kiểm tra tất định (`review_readiness_check`).
