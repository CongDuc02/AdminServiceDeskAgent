# Kế hoạch thiết kế — BO-19 Admin Service Desk Agent

Chạy **tuần tự, mỗi phase một phiên Claude Code mới** (tránh context rot). Sau mỗi phase tôi đọc và duyệt trước khi sang phase kế.

| #   | Phase                       | File đích                             | Phụ thuộc | Trạng thái |
| --- | --------------------------- | ------------------------------------- | --------- | ---------- |
| 0   | Domain Discovery            | `00-domain.md`, `GLOSSARY.md`         | —         | ☑          |
| 1   | PRD                         | `01-prd.md`                           | 0         | ☑          |
| 2   | System Architecture         | `02-architecture.md`                  | 1         | ☑          |
| 3   | Agent & Tool Architecture   | `03-agents.md`                        | 2         | ☐          |
| 4   | Data Architecture           | `04-data.md`, `contracts/schema.sql`  | 1, 3      | ☐          |
| 5   | API Spec                    | `05-api.md`, `contracts/openapi.yaml` | 4         | ☐          |
| 6   | Project Structure (BE + FE) | `06-structure.md`                     | 2, 5      | ☐          |
| 7   | Prompt Architecture         | `07-prompts.md`                       | 3         | ☐          |
| 8   | HITL & Approval Workflow    | `08-hitl.md`                          | 3, 4      | ☐          |
| 9   | Security & Guardrails       | `09-security.md`                      | 5, 8      | ☐          |
| 10  | Evaluation Framework        | `10-eval.md`                          | 3, 7      | ☐          |
| 11  | Ops, Cost & Deployment      | `11-ops.md`                           | tất cả    | ☐          |
| 12  | Roadmap                     | `12-roadmap.md`                       | tất cả    | ☐          |
| 13  | Consistency Audit           | `13-audit.md`                         | tất cả    | ☐          |

---

## Quy ước ưu tiên — áp dụng cho mọi phase

Ưu tiên MoSCoW được **khai báo đúng một lần** ở mục Scope & priority của PRD (Phase 1). Các phase khác **chỉ tham chiếu tên feature**, không lặp lại mức ưu tiên. Khi cần đánh dấu một hạng mục có thể cắt khỏi Sprint đầu thì dùng `[Should]` hoặc `[Could]` — không dùng `[MVP]`, `[ADVANCED]`, `P0`/`P1`/`P2`.

---

## Phase 0 — Domain Discovery

**Mục tiêu:** chốt từ vựng nghiệp vụ trước khi thiết kế bất cứ thứ gì. Đây là phase quan trọng nhất và hay bị bỏ qua nhất.

**Nội dung:**

- **Request Type Catalog** — bảng cho từng loại yêu cầu: mã, tên, mô tả, template văn bản tương ứng, trường bắt buộc, trường tuỳ chọn, rule hợp lệ, ai được duyệt, có cần con dấu không, SLA mục tiêu. Tối thiểu 4 loại theo đề bài; nếu đề xuất thêm thì đánh dấu `[ĐỀ XUẤT]`.
- **Slot schema** cho từng loại: tên trường, kiểu, nguồn dữ liệu (người dùng nhập / tra từ hồ sơ nhân viên / hệ thống sinh), rule kiểm tra.
- **Vòng đời văn bản** đầy đủ, có cả nhánh từ chối, yêu cầu sửa, quá hạn, thu hồi.
- **Ma trận permission × vai trò** (Nhân viên, Cán bộ hành chính, `[Should]` Người ký cấp trên). Mô hình hoá theo **permission**, vai trò chỉ là gói permission.
- **GLOSSARY.md**: tên chuẩn của mọi entity và trạng thái. Từ phase này trở đi mọi file phải dùng đúng tên ở đây.

**DoD riêng:** mỗi loại yêu cầu có ít nhất 2 edge case nghiệp vụ (ví dụ: nhân viên thử việc xin giấy xác nhận công tác; đặt phòng trùng lịch).

---

## Phase 1 — PRD

**Format chuẩn: `docs/reference/sample_prd.md`.** Đọc kỹ file này trước khi viết. Giữ nguyên thứ tự mục, giọng văn và các quy ước của mẫu. Chỉ thêm mục khi thực sự cần cho AI Agent và phải ghi lý do thêm ở cuối file.

### Cấu trúc bắt buộc

| #   | Mục                         | Ghi chú riêng cho BO-19                                                                                                                                                                                                                                                                                                                        |
| --- | --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| —   | Header                      | Phiên bản · Trạng thái · Primary persona · blockquote một câu: sản phẩm làm gì và **không** làm gì                                                                                                                                                                                                                                             |
| 1   | Problem statement           | Bảng pain point 4 cột: pain point / quy trình hiện tại gãy ở đâu / tác động / root cause. Kèm **giả thuyết baseline cần kiểm chứng** và cách kiểm chứng                                                                                                                                                                                        |
| 2   | Goals & metrics             | **Không có pilot** (A-020) — neo vào một buổi UAT có kịch bản và bộ eval offline. Tách hai loại: **Bất biến** là cổng nghiệm thu, **Cảnh báo** thì không. Mỗi metric có nguồn đo                                                                                                                                                               |
| 3   | Persona                     | Primary persona viết dạng văn xuôi; vai trò liên quan nêu riêng, không nhận là primary                                                                                                                                                                                                                                                         |
| 4   | Input                       | Bảng chiều input × phạm vi MVP                                                                                                                                                                                                                                                                                                                 |
| 5   | Scope & priority            | **MoSCoW**: Must / Should / Could / Won't                                                                                                                                                                                                                                                                                                      |
| 6   | Features & AC               | Mỗi feature ghi rõ _pain point nào được giải quyết_; AC cấp feature                                                                                                                                                                                                                                                                            |
| 7   | Non-functional requirements | Gồm HITL là mục con riêng. **Bắt buộc có thêm hai mục con:** (a) tách biệt trách nhiệm theo `beneficiary_employee_id` cùng đường thoát tự duyệt (D-006); (b) **chế độ phi sản xuất** — watermark không gỡ được, dải số `TRIAL`, không đóng dấu thật, tháo chế độ là quyết định có người ký (D-009, mục Chế độ phi sản xuất của `00-domain.md`) |
| 8   | Definition of Done          | Hành trình end-to-end + Must features đạt AC + đạt metric mục 2                                                                                                                                                                                                                                                                                |
| 9   | Risk register               | _(bổ sung so với mẫu)_ `RISK-xx`: likelihood, impact, mitigation, trigger phát hiện, **residual risk còn lại sau mitigation**. A-009 vào đây ở mức cao với mitigation là HITL — nguyên liệu ở mục Thể thức văn bản của `00-domain.md`                                                                                                          |

### Quy ước kế thừa từ mẫu — bắt buộc tuân thủ

- **MoSCoW thay cho `[MVP]`/`[ADVANCED]`.** Ánh xạ đề bài: mục "Cơ bản" → **Must**; "Nâng cao" → **Should** hoặc **Could**; phần ngoài phạm vi ở mục Phạm vi của `CLAUDE.md` → **Won't**, và Won't phải ghi _lý do_ chứ không chỉ liệt kê.
- **AC cấp feature là cam kết. User story chỉ là gợi ý phân rã, chưa chốt.** Chép nguyên tinh thần khối "Quy ước" ở mục 6 của mẫu. Không gán P0/P1/P2 cho story.
- **Yêu cầu xuyên suốt khai báo một lần ở NFR, cấm lặp ở AC từng feature** (ví dụ: mọi văn bản đều phải qua HITL trước khi phát hành — nói một lần ở mục 7).
- **Thành thật về evidence.** Mọi con số chưa đo được phải gọi đúng tên là giả thuyết và kèm cách kiểm chứng. Cấm bịa số nhân viên, số yêu cầu/tháng, thời gian xử lý hiện tại.
- **Trích dẫn pháp lý phải có nguồn thật hoặc không trích.** Cấm viết số điều, khoản, điểm, phụ lục **từ trí nhớ**; chỉ trích dẫn khi văn bản gốc đã có trong `docs/reference/`. Chưa có thì ghi `[CẦN XÁC MINH]` và chỉ mô tả ở mức nguyên tắc. Áp dụng cho mọi phase (D-008).

### Định nghĩa vận hành bắt buộc

Mẫu PRD định nghĩa chính xác "đủ căn cứ" và nêu rõ trường hợp nào _không_ đạt. BO-19 phải có hai định nghĩa tương đương, ở mức chi tiết ngang vậy:

1. **"Yêu cầu đủ điều kiện xử lý"** — slot nào bắt buộc, thiếu thì agent phải hỏi lại; tuyệt đối cấm suy diễn giá trị từ ngữ cảnh hay từ hồ sơ nhân viên khi người dùng chưa xác nhận.
2. **"Văn bản đủ điều kiện trình duyệt"** — biến template nào bắt buộc có giá trị thật, biến nào agent không bao giờ được tự điền, điều kiện nào khiến bản nháp bị chặn không cho vào hàng đợi duyệt.

Cả hai định nghĩa phải nêu rõ **trường hợp bị coi là KHÔNG đạt**, giống cách mẫu xử lý "ghép nhiều đoạn mà không đoạn nào nêu trực tiếp kết luận = thiếu căn cứ".

### Bộ eval chuẩn

Đặc tả ngay trong NFR như mẫu: số lượng yêu cầu mẫu và **phân bố cố định** theo request type × (đủ điều kiện / thiếu thông tin / không đủ điều kiện theo quy chế / ngoài phạm vi). Nêu ai duyệt đáp án chuẩn. Phân bố phải chốt trước khi đo.

**DoD riêng:** mọi feature truy vết được tới ít nhất một pain point ở mục 1 **và** ít nhất một request type ở Phase 0; mọi metric ở mục 2 có cách đo; **mọi câu hỏi mở có Owner và Hạn trong `ASSUMPTIONS.md`** — PRD không giữ bản sao; **việc nghiệm thu thể thức văn bản được ghi nhận là không có người đảm nhận**, không để nó tuột khỏi mọi điều kiện nghiệm thu.

---

## Phase 2 — System Architecture

High-level component (Client, API, AI Gateway, Orchestrator, Tool Layer, Vector Store, PostgreSQL, Object Storage, Queue/Worker, Observability) — mỗi thành phần: trách nhiệm, công nghệ, lý do, cái gì **không** thuộc nó.

Sequence diagram cho: (a) tạo yêu cầu qua chat → phân loại → thiếu slot → hỏi lại; (b) sinh văn bản từ template + RAG; (c) HITL duyệt/từ chối/yêu cầu sửa với `interrupt` + resume; (d) phát hành + cấp số + đóng dấu; (e) thu hồi văn bản đã phát hành; (f) `[Should]` đặt phòng họp có xung đột lịch.

Component diagram (dependency, chỉ rõ chiều phụ thuộc, không cho phép vòng) · Data flow diagram có đánh dấu **điểm chứa PII** · State machine của **Request** — đúng **một** máy trạng thái dùng chung cho mọi loại yêu cầu — và của từng **artifact**: Document, cùng Booking `[Should]`. Nêu rõ quan hệ giữa Request và artifact.

**DoD riêng:** mọi trạng thái trong state machine xuất hiện ở đúng tên trong `GLOSSARY.md`; mọi sequence diagram có ít nhất một nhánh lỗi; không sinh thêm máy trạng thái thứ hai cho Request.

---

## Phase 3 — Agent & Tool Architecture

**Trước tiên:** biện minh số lượng agent. Bắt đầu từ giả thuyết "một agent + nhiều tool" và chỉ tách agent khi chứng minh được lý do (khác biệt về prompt, về quyền truy cập tool, về mô hình, hoặc về ranh giới HITL). Mỗi lần tách = một dòng lập luận.

Agent Registry — mỗi agent: Goal · Input/Output schema · tool được phép gọi · model tier (rẻ/mạnh) và lý do · failure handling · retry policy · điều kiện thoát vòng lặp · token budget.

Tool Registry — mỗi tool: mục đích, input schema, output schema, side effect (đọc/ghi), quyền cần có, error case, idempotency, timeout, có cần HITL trước khi chạy không. Tối thiểu: employee lookup, policy/template retrieval, docx render, document numbering, PDF export, notification, `[Should]` calendar/room booking.

**Đơn vị render lại — phải trả lời, không được mặc định:** khi văn bản quay về `DRAFT` qua `CHANGES_REQUESTED`, một lần sửa có bắt buộc render lại **toàn bộ** không, hay sửa được **từng phần** nội dung tự do mà không gọi LLM lại từ đầu? Câu trả lời quyết định đơn vị đo của A-022 và cách Phase 11 định cỡ chi phí. Cấm mặc định mỗi vòng là một lần render đầy đủ.

**LangGraph design:** state schema (TypedDict đầy đủ field), sơ đồ node/edge, conditional edge, vị trí `interrupt`, chiến lược checkpointer trên PostgreSQL, cách resume sau nhiều ngày, xử lý khi schema state thay đổi giữa chừng. **Checkpoint là kho PII** (mục Data flow diagram của `02-architecture.md`): phải nêu cách xoá slot `RES` khi `request` `EXPIRED` (A-014) trong **mọi** checkpoint, kể cả lịch sử checkpoint của các bước trước — xoá khỏi `request` mà không xoá khỏi lịch sử state là chưa xoá.

Memory: working / session / long-term (hồ sơ & thói quen yêu cầu của nhân viên) / vector. Nêu rõ **khi nào đọc, khi nào ghi, thời hạn lưu, ai xoá được**. Không thiết kế graph memory.

Retrieval: nguồn dữ liệu, chunk strategy, embedding model tiếng Việt, hybrid search, metadata filter theo phòng ban/mức bảo mật, chống rò rỉ tài liệu ngoài quyền.

**Nghĩa vụ allowlist input — kế thừa từ NFR-05 đã sửa ở Phase 2, bắt buộc với mọi agent và node có gọi LLM:**

- Input phải khai **tường minh, liệt kê đích danh từng slot**, dùng đúng tên ở mục Slot schema của `00-domain.md`. Ví dụ khai đúng: `purpose`, `recipient_org`, `work_content`.
- **Cấm khai gộp**: "nhận context của request", "nhận thông tin yêu cầu", "toàn bộ state", hay một kiểu dữ liệu bao trùm như `request: Request`. Khai gộp làm allowlist mất tác dụng mà vẫn trông như đang tuân thủ.
- LangGraph mặc định truyền **toàn bộ state** vào mọi node, nên allowlist không đặt được ở chữ ký hàm của node — nó phải được thực thi tại điểm lắp prompt trong `ai_gateway`. Node nhìn thấy cả state thì chưa phải vi phạm; prompt chứa slot ngoài danh sách khai báo mới là vi phạm.
- Input **không phải slot** — tin nhắn thô của người dùng, lịch sử hội thoại, đoạn retrieval — cũng phải khai đích danh loại input, kèm hai thông tin: phạm vi (chỉ lượt hiện tại, hay bao nhiêu lượt trước) và loại dữ liệu nó có thể mang theo. Đây là lỗ lớn nhất của allowlist theo slot: node phân loại và node trích slot bắt buộc phải đọc text thô, mà text thô thì mang theo được mọi thứ, kể cả dữ liệu `RES` chưa kịp gán vào slot nào.

**DoD riêng:** mỗi tool có side effect ghi dữ liệu phải chỉ rõ nó nằm trước hay sau cổng HITL; mỗi agent/node gọi LLM có danh sách input đích danh, không dòng nào khai gộp.

---

## Phase 4 — Data Architecture

ERD (`erDiagram`) · bảng chi tiết: cột, kiểu, nullable, default, constraint, index, lý do index · quy tắc soft delete & audit column · bảng audit log bất biến · bảng sổ số văn bản kèm cơ chế chống trùng khi đồng thời và **định dạng số cấu hình được ngay từ đầu** (ADR-001, D-008) — ký hiệu chứa viết tắt tên cơ quan nên hardcode là sai trong mọi trường hợp · lưu trữ file (object storage, đường dẫn, checksum, immutability) · vector collection: tên, embedding model, dimension, metadata schema, chunk strategy, chiến lược re-index · chính sách lưu trữ và thời hạn xoá PII.

**Lưu trữ bản render (A-021):** quyết bản render ở `document.DRAFT` lưu ở đâu, và các bản qua vòng `CHANGES_REQUESTED → DRAFT` đè nhau hay tích luỹ. Ràng buộc sản phẩm đã chốt ở PRD F3 và không thương lượng: **bản render gắn với `document` ở `SEALED` và `ISSUED` không bao giờ được mất hay bị đè**; bản trung gian thì tự do. Thiết kế phải nêu rõ cơ chế bảo đảm tính bất biến đó, không chỉ khẳng định nó.

Xuất `contracts/schema.sql` (DDL thuần, không seed data).

---

## Phase 5 — API Spec

REST endpoint: method, URL, mô tả, auth + role, request/response JSON, mã lỗi chuẩn hoá (`error_code`, `message`, `trace_id`), pagination, idempotency key cho endpoint ghi. Đề xuất SSE cho streaming phản hồi chat và cập nhật trạng thái duyệt, kèm lý do chọn SSE thay vì WebSocket trong bối cảnh Render.

Xuất `contracts/openapi.yaml` khớp 100% với tài liệu.

---

## Phase 6 — Project Structure

Cây thư mục backend FastAPI + frontend React, mỗi thư mục một dòng trách nhiệm và quy tắc "được import gì, cấm import gì". Frontend: page, component chính, hook, service, state management, auth flow, màn hình hàng đợi duyệt, màn hình theo dõi trạng thái.

---

## Phase 7 — Prompt Architecture

**Phạm vi:** prompt **chỉ sinh phần nội dung tự do** — lý do, mục đích, nội dung công việc cụ thể. Khung thể thức (quốc hiệu, tiêu ngữ, tên cơ quan, số và ký hiệu, nơi nhận, phần chữ ký) nằm trong template `.docx`, **không** thuộc Phase 7 và không được mô tả trong prompt (ADR-001, D-007). Mẫu `.docx` đúng thể thức do Product Owner chuẩn bị trước phase này.

Prompt dạng module (system / role / task / context / output contract / guardrail), có versioning và biến truyền vào. Mỗi prompt: mục tiêu, biến input (liệt kê đích danh theo nghĩa vụ allowlist ở Phase 3, cấm khai gộp), output format (JSON Schema), guardrail, failure mode, ví dụ few-shot **đánh dấu rõ là dữ liệu giả**. Nêu chiến lược ép JSON hợp lệ và xử lý khi parse lỗi.

---

## Phase 8 — HITL & Approval Workflow

Hàng đợi duyệt, tiêu chí sắp xếp, SLA & escalation, luồng từ chối kèm lý do, luồng yêu cầu sửa và agent làm lại, định tuyến ký nhiều cấp, ủy quyền khi vắng mặt, duyệt con dấu, thu hồi văn bản. **Cơ chế dừng khi chạm trần (A-022):** khi số lần render lại hoặc token budget chạm trần, hệ thống dừng thế nào. Ràng buộc sản phẩm ở NFR-06: không bao giờ âm thầm dừng giữa chừng để lại `document` dở dang — phải dừng có kiểm soát và chuyển cho người thật, nêu rõ dừng ở đâu và vì sao. Thiết kế trạng thái và giao diện của tình huống này.

Audit log: ghi gì, ai xem được, chứng minh tính bất biến. **Quy tắc cứng:** liệt kê rõ mọi hành động không bao giờ được tự động hoá.

---

## Phase 9 — Security & Guardrails

AuthN/AuthZ (RBAC + row-level theo phòng ban), rate limit, prompt injection (đặc biệt từ nội dung tài liệu và văn bản người dùng dán vào), tool permission theo vai trò người yêu cầu, PII masking trong log và trong prompt gửi lên LLM, output validation trước khi render văn bản, chống lộ template mật, secret management trên Render.

---

## Phase 10 — Evaluation Framework

Golden dataset (nguồn, kích thước, cách gán nhãn, ai gán), metric cho từng chặng: phân loại intent, trích slot, retrieval (recall@k), độ đúng thể thức văn bản, tỷ lệ bị người duyệt từ chối, tỷ lệ escalation, cost/request, latency p95. Offline eval, online eval, human eval rubric, taxonomy failure mode, regression gate trước khi đổi prompt/model.

---

## Phase 11 — Ops, Cost & Deployment

Môi trường dev/staging/prod trên Render, cold start, worker nền, cron, migration, backup & restore, observability (trace của một request xuyên agent, log schema, metric, alert), dashboard SLA & tồn đọng, mô hình chi phí LLM theo request type kèm giả định giá (ghi vào ASSUMPTIONS), ngưỡng cảnh báo và cơ chế cắt chi phí. **Định cỡ A-022:** trần số lần render lại và token budget mỗi request — chỉ định cỡ được **sau khi** Phase 3 chốt đơn vị render lại và Phase 8 chốt cơ chế dừng; định cỡ trước đó là định cỡ sai đơn vị.

**Chỗ quan sát cho điều kiện đảo ngược của ADR ở Phase 2.** ADR-002, ADR-004 và ADR-005 chỉ nêu _hình dạng_ tín hiệu, không có ngưỡng, vì A-002 chưa có số liệu tải. Nhưng một tín hiệu không có chỗ đo thì không bao giờ phát ra, và điều kiện đảo ngược khi đó chỉ còn là trang trí. Thiết kế observability phải có chỗ quan sát cho từng tín hiệu dưới đây. Chưa cần ngưỡng — chỉ cần metric **tồn tại**, để khi có số liệu thật thì đặt được ngưỡng lên nó.

| ADR     | Hình dạng tín hiệu                                 | Chỗ phải quan sát được                                                                                                                                                    |
| ------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ADR-002 | Truy vấn nghiệp vụ chậm đi đúng lúc retrieval tăng | Latency truy vấn nghiệp vụ và số truy vấn retrieval, đặt **trên cùng một trục thời gian**. Nhìn riêng từng metric thì không thấy được tương quan                          |
| ADR-002 | Reindex embedding làm chậm ghi giao dịch           | Thời lượng mỗi lần reindex, và latency ghi giao dịch trong cửa sổ reindex so với ngoài cửa sổ                                                                             |
| ADR-004 | Tranh khoá trên bảng job                           | Thời gian chờ khoá trên bảng job của `queue_worker`                                                                                                                       |
| ADR-004 | Độ trễ dispatch không chấp nhận được               | Khoảng thời gian từ lúc enqueue tới lúc bắt đầu xử lý, tách theo loại job                                                                                                 |
| ADR-004 | Vòng poll chiếm IO đáng kể                         | Tỷ trọng truy vấn và IO do vòng poll gây ra, trên tổng tải của `postgresql`                                                                                               |
| ADR-005 | Một lượt graph tiến sát giới hạn thời gian request | **Phân phối** thời lượng một lượt chạy `orchestrator` trong luồng request của `api` — nhìn phần đuôi, không nhìn trung bình — đặt cạnh giới hạn thời gian request (A-025) |

**Hai điều kiện đảo ngược không phải tín hiệu vận hành**, nên không đo ở observability mà ở `ASSUMPTIONS.md`: ADR-002 phải xét lại khi A-001 bị bác bỏ; ADR-003 kích hoạt khi A-024 đóng. Hai điều kiện này phát ra khi một giả định đổi trạng thái, không phải khi một metric vượt ngưỡng.

---

## Phase 12 — Roadmap

Sprint có Objective, Deliverable, Dependency, Acceptance Criteria, rủi ro chính. Sprint 1 phải kết thúc bằng một lát cắt dọc chạy được end-to-end cho **một** request type, không phải "dựng hạ tầng".

---

## Phase 13 — Consistency Audit

Đối chiếu toàn bộ `docs/design/`. Xuất bảng lỗi: tên entity lệch, trạng thái tồn tại ở diagram nhưng thiếu ở DB, endpoint không có FR tương ứng, FR không có endpoint, tool không xuất hiện trong agent nào, giả định chưa được giải quyết, ADR bị mâu thuẫn. Chỉ **báo cáo**, không tự sửa; đề xuất thứ tự sửa.
