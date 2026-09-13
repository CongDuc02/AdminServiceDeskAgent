# System Architecture — Admin Service Desk Agent (BO-19)

**Phiên bản:** 0.7 · **Trạng thái:** Draft để xác thực với người dùng · **v0.3–0.5:** sửa ở Phase 3 và các vòng sửa Phase 3 theo phép — xem các mục ngày 2026-09-12 (lần 4, lần 5, lần 6) của `CHANGELOG.md` · **v0.6:** sửa ở Phase 4 theo phép K1 — mục ngày 2026-09-13 của `CHANGELOG.md` · **v0.7:** trỏ tới danh sách ngoại lệ đóng của luật ghi qua `tool_layer` (U1)

> File này chốt kiến trúc mức component: thành phần nào tồn tại, chạy ở đâu trên Render, phụ thuộc gì, và luồng dữ liệu đi qua chúng thế nào. File này **không** đổi state machine hay entity đã chốt ở `00-domain.md`, không chọn agent/tool cụ thể (Phase 3), không thiết kế bảng/cột (Phase 4).

Tên component dùng đúng mục Thành phần kiến trúc hệ thống của `GLOSSARY.md`. Tên entity, trạng thái, permission dùng đúng `GLOSSARY.md` các mục còn lại. Quyết định `D-xxx`/`A-xxx` tham chiếu `00-domain.md` và `ASSUMPTIONS.md`.

**Đã đối chiếu:** `CLAUDE.md`, `_PLAN.md`, `GLOSSARY.md`, `ASSUMPTIONS.md`, `00-domain.md`, `01-prd.md`, `decisions/ADR-001-template-giu-khung-the-thuc.md`. Một mâu thuẫn được tìm thấy và sửa ở phase gốc (`01-prd.md` NFR-05, xem `CHANGELOG.md`), không vá ở file này.

---

## 1. Thành phần

Mười thành phần theo yêu cầu của `_PLAN.md`. Bốn trong số đó (`ai_gateway`, `orchestrator`, `vector_store`, `queue_worker` một phần) **không phải đơn vị triển khai riêng trên Render** — chúng là module/thư viện hoặc extension chạy bên trong các đơn vị triển khai khác. Bảng ánh xạ ở mục 1.11 làm rõ điều này trước khi mô tả từng thành phần, để tránh đọc nhầm "10 thành phần" thành "10 service".

### 1.1 `client`

- **Trách nhiệm:** giao diện chat streaming cho nhân viên; giao diện hàng đợi duyệt, form duyệt nội dung/từ chối/yêu cầu sửa/ký/đóng dấu/cấp số/thu hồi cho cán bộ hành chính; hiển thị trạng thái `request`/artifact đúng tên `GLOSSARY.md` kèm diễn giải tiếng Việt (NFR-04 của `01-prd.md`).
- **Công nghệ:** React SPA, tiêu thụ REST và SSE của `api`.
- **Lý do:** React là bắt buộc theo `CLAUDE.md`; SSE phù hợp luồng chat tăng dần và cập nhật trạng thái duyệt mà không cần hạ tầng WebSocket (quyết định đầy đủ ở Phase 5).
- **Không thuộc:** không tự validate business rule (slot bắt buộc, permission, điều kiện trình duyệt) — chỉ hiển thị kết quả `api` trả về; không giữ trạng thái nghiệp vụ lâu dài ngoài phiên đăng nhập; không render `.docx`/`.pdf`.

### 1.2 `api`

- **Trách nhiệm:** FastAPI; AuthN/AuthZ (RBAC + row-level theo phòng ban, chi tiết Phase 9); validate HTTP; là điểm vào duy nhất gọi `orchestrator` (lượt chat) hoặc gọi thẳng `tool_layer` (hành động duyệt/ký/đóng dấu/cấp số/thu hồi/booking — không cần LLM); publish sự kiện SSE.
- **Công nghệ:** FastAPI, chạy như Render Web Service.
- **Lý do:** bắt buộc theo `CLAUDE.md`.
- **Không thuộc:** không gọi LLM provider trực tiếp (qua `ai_gateway`); không render `.docx`/PDF (qua `tool_layer`); không chứa logic quyết định chuyển trạng thái của state machine (`orchestrator`/`tool_layer` sở hữu, `api` chỉ là nơi lời gọi HTTP đi vào).

### 1.3 `ai_gateway`

- **Trách nhiệm:** model routing rẻ/mạnh theo bước (NFR-06 của `01-prd.md`); lắp ráp prompt **chỉ với slot mà prompt module đang gọi tự khai là input** (nguyên tắc tối thiểu hoá theo nhu cầu từng bước — xem NFR-05 đã sửa của `01-prd.md`); token budget accounting mỗi request; ép output theo JSON Schema và retry khi parse lỗi; timeout/retry gọi model. **Mọi lời gọi embedding cũng đi qua đây** và chịu cùng luật khai input: embedding là lời gọi ra ngoài mang văn bản, không phải bước kỹ thuật được miễn (mục Allowlist input của `03-agents.md`).
- **Công nghệ:** module Python, chạy trong cùng tiến trình với nơi gọi nó (`api` hoặc `queue_worker`) — không phải service riêng. Gọi LLM provider qua HTTP; nhà cung cấp cụ thể chưa chốt ở phase này (không ảnh hưởng kiến trúc, chỉ ảnh hưởng cấu hình — chi tiết chọn model thuộc Agent Registry của Phase 3).
- **Lý do:** tách "gọi model" khỏi "quyết định luồng nghiệp vụ" để đổi model/provider không đụng logic LangGraph của `orchestrator`.
- **Không thuộc:** không quyết định node kế tiếp trong graph; không thực hiện side effect ghi dữ liệu nghiệp vụ; không tự ý gửi slot ngoài allowlist của prompt module đang gọi nó — đây là ranh giới cứng, vi phạm nó chính là vi phạm NFR-05.

### 1.4 `orchestrator`

- **Trách nhiệm:** graph LangGraph — node/edge cho phân loại, thu slot, retrieval, sinh nội dung tự do; `interrupt` tại **sáu** điểm chờ người thật, trong đó chỉ **hai** là cổng HITL (`PENDING_APPROVAL`, `PENDING_SEAL`) — danh sách ở mục LangGraph design của `03-agents.md`; resume qua checkpointer, bằng job ghi cùng giao dịch với quyết định của người (ADR-010).
- **Công nghệ:** LangGraph, checkpointer trên PostgreSQL. Chạy như thư viện dùng chung, gọi từ `api` (lượt chat đồng bộ) và từ `queue_worker` (job nền). Xem ADR-005 cho lý do đầy đủ.
- **Lý do:** bắt buộc theo `CLAUDE.md`; ADR-005 giải thích vì sao không cần service riêng.
- **Không thuộc:** không tự gọi LLM provider (qua `ai_gateway`); không tự ghi PostgreSQL/Object Storage (qua `tool_layer`) — trừ danh sách ngoại lệ đóng ở mục Tool Registry của `03-agents.md`: bảng checkpoint và `graph_thread`; không giữ trạng thái trong bộ nhớ tiến trình giữa hai lượt gọi — mọi trạng thái sống ở checkpointer.

### 1.5 `tool_layer`

- **Trách nhiệm:** mọi thao tác có side effect qua permission check — employee lookup, policy/template retrieval, docx render, document numbering (nguyên tử), PDF export, notification, `[Should]` calendar/room booking. Danh mục tool cụ thể thuộc Phase 3.
- **Công nghệ:** thư viện Python dùng chung bởi `api`, `orchestrator`, `queue_worker`.
- **Lý do:** một nơi duy nhất enforce permission và sinh `audit_event` cho mọi ghi dữ liệu — tránh `api` hay `orchestrator` tự ý ghi tắt qua đường khác.
- **Không thuộc:** không quyết định *khi nào* được gọi (`api`/`orchestrator` quyết định); không soạn prompt; không quyết định model nào được dùng.

### 1.6 `vector_store`

- **Trách nhiệm:** embedding và hybrid search (BM25 + vector) trên kho quy trình hành chính (`procedure_document`), phục vụ **một** việc: `intake_agent` trả hướng xử lý thủ công có trích nguồn cho yêu cầu ngoài phạm vi (AC của F1). **Không** phục vụ việc chọn template — đó là tra cứu chính xác — và **không** phục vụ bước sinh nội dung tự do (mục Retrieval của `03-agents.md`). Kho có thể rỗng (A-027).
- **Công nghệ:** `pgvector` trong cùng `postgresql` — không phải service riêng. Xem ADR-002.
- **Lý do:** ADR-002.
- **Không thuộc:** không phải nguồn sự thật cho entity nghiệp vụ (các bảng thường của `postgresql` đảm nhiệm); không lưu file gốc (`object_storage` đảm nhiệm).

### 1.7 `postgresql`

- **Trách nhiệm:** toàn bộ entity nghiệp vụ (`request`, `document`, `employee`, ...), `document_register`, `seal_register`, `audit_event`, checkpoint của `orchestrator`, bảng job của `queue_worker`, extension `pgvector`.
- **Công nghệ:** PostgreSQL managed trên Render.
- **Lý do:** bắt buộc theo `CLAUDE.md`; managed để tránh tự vận hành backup/HA.
- **Không thuộc:** không lưu file `.docx`/`.pdf` (`object_storage` đảm nhiệm); không tự chạy job định kỳ (`queue_worker` đọc/ghi nó, không phải ngược lại).

### 1.8 `object_storage`

- **Trách nhiệm:** lưu bản gốc `template` (bất biến, có phiên bản) và bản render `.docx`/`.pdf`; bản gắn với `document` ở `SEALED`/`ISSUED` phải bất biến tuyệt đối (AC F3 của `01-prd.md`).
- **Công nghệ:** dịch vụ S3-compatible ngoài Render; vendor cụ thể `TBD` (A-024). Xem ADR-003.
- **Lý do:** ADR-003 — ràng buộc Render "filesystem không bền vững".
- **Không thuộc:** không phải nơi truy vấn metadata (`postgresql` giữ path + checksum); không tự enforce business rule ngoài bất biến đã khai ở ADR-003.

### 1.9 `queue_worker`

- **Trách nhiệm:** render `document` (gọi `orchestrator` + `tool_layer`) sau khi enqueue tại thời điểm `request` chuyển `SUBMITTED`; quét `NEEDS_INFO → EXPIRED`; quét SLA/escalation; giải phóng `room_booking` `HELD` quá hạn; gửi notification; tổng hợp chi phí LLM.
- **Công nghệ:** Render Background Worker (poll bảng job trong `postgresql`) + Render Cron Job (job thuần định kỳ). Xem ADR-004.
- **Lý do:** ADR-004.
- **Không thuộc:** không phục vụ request đồng bộ của `client`; không giữ session người dùng.

### 1.10 `observability`

- **Trách nhiệm:** log kỹ thuật có `trace_id` xuyên suốt `api` → `orchestrator` → `tool_layer` → `queue_worker`; metric (latency, token usage, độ dài hàng đợi job).
- **Công nghệ:** log JSON có cấu trúc ra stdout, thu bởi log viewer của Render. Lựa chọn công cụ APM/metric cụ thể để Phase 11 quyết khi có số liệu tải (A-002).
- **Lý do:** tối thiểu hoá phụ thuộc ngoài trước khi có số liệu tải thật để biện minh cho một công cụ trả phí.
- **Không thuộc:** **không phải** `audit_event`. `audit_event` là nhật ký nghiệp vụ bất biến, cho người dùng và kiểm toán, sống trong `postgresql`, không bao giờ bị xoá/sửa. `observability` là log vận hành cho kỹ sư, có thể xoay vòng/hết hạn theo chính sách retention kỹ thuật. Nhầm hai khái niệm này là lỗi cần tránh — chúng phục vụ hai đối tượng đọc khác nhau với hai yêu cầu bất biến khác nhau.

### 1.11 Ánh xạ sang đơn vị triển khai trên Render

| Đơn vị triển khai Render | Gồm những thành phần logic nào |
|---|---|
| Web Service (`api`) | `client` phục vụ tĩnh hoặc build riêng; `api`; `ai_gateway`; `orchestrator`; `tool_layer` (thư viện dùng chung) |
| Background Worker (`queue_worker`) | `queue_worker`; cùng thư viện `orchestrator`, `tool_layer`, `ai_gateway` |
| Cron Job | các job thuần định kỳ của `queue_worker` (quét `EXPIRED`, quét SLA, giải phóng `HELD`) |
| PostgreSQL managed | `postgresql`, `vector_store` (`pgvector`) |
| Dịch vụ ngoài Render | `object_storage` (S3-compatible, vendor `TBD`) |

`vector_store` và `postgresql` là **cùng một instance vật lý** — tách thành hai dòng trong bảng thành phần chỉ để nói rõ hai trách nhiệm logic khác nhau (ADR-002).

---

## 2. Ràng buộc nền tảng Render

| Ràng buộc | Hệ quả thiết kế |
|---|---|
| **Cold start** (Web Service có thể sleep ở gói thấp) | Không ảnh hưởng tính đúng đắn: trạng thái hội thoại và trạng thái duyệt sống ở checkpointer/`postgresql`, không sống trong RAM của tiến trình `api`. Cold start chỉ cộng thêm độ trễ cho lần gọi đầu sau khi sleep, không làm mất tiến trình đang dừng ở `interrupt`. |
| **Filesystem không bền vững** | Không file nghiệp vụ nào (template gốc, bản render) được coi là tồn tại nếu chỉ nằm trên đĩa cục bộ của một instance — mọi file đi qua `object_storage` (ADR-003). File tạm trong một request/job không phải nguồn sự thật. |
| **Background worker** | `queue_worker` là một Render Background Worker riêng, tách khỏi Web Service phục vụ `api`. |
| **Cron job** | Các job thuần định kỳ (không cần vòng lặp poll liên tục) chạy qua Render Cron Job thay vì giữ Background Worker chạy trần cho việc đó. |
| **Giới hạn thời gian request** | Giá trị cụ thể **`[CẦN XÁC MINH]`** — cấm ghi từ trí nhớ theo quy tắc trích dẫn tài liệu sản phẩm của `CLAUDE.md` (A-025). Hệ quả thiết kế không phụ thuộc con số: bước "render + RAG + LLM soạn nội dung tự do" (thời gian không cố định, phụ thuộc model mạnh) **không chạy đồng bộ trong request chuyển `SUBMITTED`** — được enqueue nguyên tử trong cùng giao dịch DB (D-010, ADR-004), trả response ngay, `queue_worker` xử lý sau. Xem sequence diagram (b) và điều kiện đảo ngược của ADR-005. |

---

## 3. Component diagram

```mermaid
graph TD
    Client[client - React SPA]
    API[api - FastAPI]
    AIGateway[ai_gateway]
    Orchestrator[orchestrator - LangGraph]
    ToolLayer[tool_layer]
    VectorStore[vector_store - pgvector]
    PostgreSQL[(postgresql)]
    ObjectStorage[(object_storage)]
    Worker[queue_worker]
    Observability[observability]
    LLMProvider[LLM provider - ngoai he thong]

    Client --> API
    API --> Orchestrator
    API --> ToolLayer
    API --> PostgreSQL
    Orchestrator --> AIGateway
    Orchestrator --> ToolLayer
    Worker --> Orchestrator
    Worker --> AIGateway
    Worker --> ToolLayer
    Worker --> PostgreSQL
    ToolLayer --> PostgreSQL
    ToolLayer --> ObjectStorage
    ToolLayer --> VectorStore
    VectorStore --> PostgreSQL
    AIGateway --> LLMProvider
    API --> Observability
    Orchestrator --> Observability
    ToolLayer --> Observability
    Worker --> Observability
```

Mọi cạnh có một chiều duy nhất; không có cạnh nào đi ngược lại `Client`, `API`, `Worker`, `Orchestrator`, `ToolLayer`, `AIGateway` hay `VectorStore` — không tồn tại vòng phụ thuộc. Cạnh `Worker --> AIGateway` thêm ở Phase 3: `procedure_ingest` gọi embedding khi nạp kho quy trình, và mọi lời gọi embedding phải đi qua `ai_gateway` (mục Allowlist input của `03-agents.md`). Cạnh này không tạo vòng.

---

## 4. Data flow diagram — điểm chứa PII

```mermaid
flowchart LR
    NV[Nhan vien nhap chat]
    MSG[(postgresql - chat_message, xep RES)]
    ORC[orchestrator]
    CKPT[(postgresql - checkpoint)]
    GW[ai_gateway]
    LLM[LLM provider - ben thu ba]
    EMB[embedding model - neu nha cung cap chay thi la ben thu ba thu hai]
    TL[tool_layer]
    EMP[(postgresql - employee, HR_PROFILE)]
    VS[(vector_store - procedure_document, khong PII)]
    OS[(object_storage - ban render)]
    AUD[(postgresql - audit_event)]
    LOG[observability - log ky thuat]
    CB[Nhan vien tai xuong sau ISSUED]

    NV -->|tin nhan tho va slot USER_INPUT, co the PER hoac RES| MSG
    MSG -->|chi luot hien tai, nap theo khai bao| ORC
    ORC -->|state, chi tham chieu theo ADR-008| CKPT
    ORC -->|chi input duoc prompt module khai| GW
    GW -->|chi slot duoc khai la input, van co the la RES| LLM
    GW -->|retrieval_query, co the RES| EMB
    VS -->|doan quy trinh da loc quyen| TL
    LLM -->|noi dung tu do sinh ra| TL
    EMP -->|gia tri PER hoac RES tu HR_PROFILE| TL
    TL -->|ghep bien, render ban day du| OS
    OS -->|tai xuong, sau kiem tra permission| CB
    TL -->|ghi nhan hanh dong, khong chua noi dung RES tho| AUD
    GW -->|mask theo slot_sensitivity| LOG
    TL -->|mask theo slot_sensitivity| LOG

    classDef pii fill:#f4cccc,stroke:#a61c00,color:#000
    classDef scoped fill:#fce5cd,stroke:#b45f06,color:#000
    class NV,MSG,ORC,CKPT,TL,EMP,OS pii
    class GW,LLM,EMB scoped
```

Hai mức tô màu, ứng với hai cơ chế ở NFR-05 của `01-prd.md`:

- **Đỏ — PII không bị giới hạn theo bước:** điểm chứa hoặc xử lý dữ liệu `PER`/`RES` ở dạng chưa mask. Trong đó có **checkpoint của `orchestrator`** trong `postgresql`: state LangGraph lưu mọi slot đã thu, nên nó là một kho PII ngang hàng với bảng `employee`, không phải dữ liệu kỹ thuật. Hệ quả: việc xoá slot `RES` khi `request` `EXPIRED` (A-014) phải xoá cả trong checkpoint — kể cả checkpoint của những bước trước, vì LangGraph giữ lịch sử state theo từng bước. Nếu không, giá trị đã xoá khỏi `request` vẫn còn nguyên trong lịch sử state. Thời hạn giữ checkpoint cũng thuộc phạm vi A-010. **Cập nhật ở Phase 3:** ADR-008 bỏ mọi giá trị khỏi state, nên theo thiết kế checkpoint chỉ còn tham chiếu. Nó vẫn được tô đỏ cho tới khi test canary ở Phase 10 chứng minh không có giá trị `RES` nào lọt vào (mục Checkpointer và PII của `03-agents.md`). Sơ đồ thêm `chat_message` — nơi tin nhắn thô thực sự nằm — tô đỏ.
- **Cam — PII đã bị allowlist giới hạn:** `ai_gateway`, LLM provider và embedding model chỉ thấy những input mà bước đang chạy tự khai cần. Embedding model nếu do nhà cung cấp chạy là **bên thứ ba thứ hai**, nhận `retrieval_query` — cụm chủ đề trích từ tin nhắn thô, có thể mang dữ liệu `RES` (A-028). Luồng này thêm ở Phase 3. Allowlist thu hẹp **tập** slot đi ra ngoài hệ thống; nó **không** làm những slot đó bớt nhạy cảm. LLM provider là bên thứ ba, và `purpose` gửi tới đó vẫn là dữ liệu `RES`.

`observability` không tô màu vì mọi luồng vào nó đều mask theo `slot_sensitivity` — kể cả log của chính lời gọi LLM đã chở slot đó đi. Hai cơ chế gặp nhau đúng ở chỗ này: allowlist quyết định slot nào vào prompt, còn `slot_sensitivity` quyết định slot nào bị mask khi prompt đó được ghi log.

---

## 5. State machine — tái hiện từ `00-domain.md`, không đổi trạng thái nào

Ba máy trạng thái dưới đây **giống hệt** mục Vòng đời của `00-domain.md`. Cột "Thành phần sở hữu transition" là nội dung mới của Phase 2 — không đổi tên hay thêm/bớt trạng thái nào (DoD của Phase 2 cấm việc đó).

### 5.1 `request` — đúng một máy trạng thái cho mọi loại yêu cầu

```mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> NEEDS_INFO: thieu slot bat buoc
    NEEDS_INFO --> DRAFT: nhan vien bo sung
    NEEDS_INFO --> EXPIRED: qua han cho bo sung
    DRAFT --> SUBMITTED: nhan vien xac nhan gui
    DRAFT --> CANCELLED: nhan vien huy
    SUBMITTED --> REJECTED: khong du dieu kien theo quy che
    SUBMITTED --> IN_REVIEW: vao hang doi duyet
    IN_REVIEW --> CHANGES_REQUESTED: can bo yeu cau sua
    CHANGES_REQUESTED --> SUBMITTED: soan lai va gui lai
    CHANGES_REQUESTED --> CANCELLED: nhan vien huy
    IN_REVIEW --> REJECTED: tu choi kem ly do
    IN_REVIEW --> APPROVED: duyet
    APPROVED --> FULFILLED: artifact da den trang thai cuoi
    FULFILLED --> [*]
    REJECTED --> [*]
    CANCELLED --> [*]
    EXPIRED --> [*]
```

| Trạng thái | Thành phần sở hữu transition |
|---|---|
| `DRAFT` | `orchestrator` (thu slot qua chat) |
| `NEEDS_INFO` | `orchestrator` |
| `SUBMITTED` | `api` — giao dịch chuyển trạng thái và enqueue job render là **cùng một transaction** (D-010, ADR-004) |
| `IN_REVIEW` | `tool_layer`, kích hoạt khi `document` vào `PENDING_APPROVAL` |
| `CHANGES_REQUESTED` | `api`/`tool_layer`, permission `document.request_changes` |
| `APPROVED` | `api`/`tool_layer`, permission `document.approve_content` |
| `FULFILLED` | `tool_layer`, khi mọi artifact của `request` tới trạng thái cuối |
| `REJECTED` | `api`/`tool_layer`, permission `document.reject` |
| `CANCELLED` | `api` (nhân viên) |
| `EXPIRED` | `queue_worker` (Cron Job quét quá hạn — A-014) |

### 5.2 `document`

```mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_APPROVAL: trinh duyet
    PENDING_APPROVAL --> CHANGES_REQUESTED: yeu cau sua noi dung
    CHANGES_REQUESTED --> DRAFT: agent soan lai
    PENDING_APPROVAL --> REJECTED: tu choi kem ly do
    PENDING_APPROVAL --> APPROVED: duyet noi dung
    APPROVED --> PENDING_SIGNATURE: dinh tuyen nguoi ky
    PENDING_SIGNATURE --> CHANGES_REQUESTED: nguoi ky tra lai
    PENDING_SIGNATURE --> SIGNED: da ky
    SIGNED --> PENDING_SEAL: requires_seal true
    PENDING_SEAL --> SEALED: da dong dau
    SIGNED --> ISSUED: requires_seal false
    SEALED --> ISSUED: cap so va phat hanh
    ISSUED --> REVOKED: thu hoi hoac huy hieu luc
    ISSUED --> SUPERSEDED: bi van ban moi thay the
    ISSUED --> ARCHIVED: het thoi han hieu luc
    REVOKED --> ARCHIVED
    SUPERSEDED --> ARCHIVED
    REJECTED --> ARCHIVED
    CHANGES_REQUESTED --> ARCHIVED: request bi huy
    ARCHIVED --> [*]
```

| Trạng thái | Thành phần sở hữu transition |
|---|---|
| `DRAFT` | `queue_worker` tạo ra (job render sau `SUBMITTED`, D-010); `queue_worker` cũng đưa `CHANGES_REQUESTED → DRAFT` về đây khi soạn lại |
| `PENDING_APPROVAL` | `queue_worker`, sau khi `tool_layer` xác nhận đủ điều kiện trình duyệt (F2) |
| `CHANGES_REQUESTED` | `api`/`tool_layer`, permission `document.request_changes` |
| `REJECTED` | `api`/`tool_layer`, permission `document.reject` |
| `APPROVED` | `api`/`tool_layer`, permission `document.approve_content` |
| `PENDING_SIGNATURE` | `tool_layer` (định tuyến ký) |
| `SIGNED` | `api`/`tool_layer`, permission `document.sign` |
| `PENDING_SEAL` | `tool_layer`, tự động khi `requires_seal = true` |
| `SEALED` | `api`/`tool_layer`, permission `document.apply_seal` |
| `ISSUED` | `queue_worker` qua `tool_layer`, trong node `finalize_issue` — hoàn tất lệnh phát hành do người mang permission `document.issue` ra ở `api`. Cấp số nguyên tử trên `document_register` diễn ra trong `finalize_issue`, không trong luồng request (mục Tool Registry của `03-agents.md`) |
| `REVOKED` | `api`/`tool_layer`, hai permission tách rời `document.revoke_initiate`/`document.revoke_confirm` |
| `SUPERSEDED` | `api`/`tool_layer` |
| `ARCHIVED` | `queue_worker` (Cron Job theo thời hạn lưu trữ, `TBD` — A-010); `api`/`tool_layer` qua thao tác cổng `request_cancel` khi `document` đang ở `CHANGES_REQUESTED`, bắt buộc `archive_reason` (A-035) |

### 5.3 `room_booking` `[Should]`

```mermaid
stateDiagram-v2
    [*] --> HELD
    HELD --> CONFIRMED: request duoc APPROVED
    HELD --> RELEASED: request bi REJECTED hoac CANCELLED
    CONFIRMED --> CANCELLED: huy sau khi da xac nhan
    CONFIRMED --> COMPLETED: het khung gio
    RELEASED --> [*]
    CANCELLED --> [*]
    COMPLETED --> [*]
```

| Trạng thái | Thành phần sở hữu transition |
|---|---|
| `HELD` | `tool_layer`, tạo ngay khi `request` chuyển `SUBMITTED` (kiểm tra xung đột lịch — sequence diagram (f)) |
| `CONFIRMED` | `api`/`tool_layer`, permission `booking.confirm` |
| `RELEASED` | `api`/`tool_layer`, khi `request` bị `REJECTED`/`CANCELLED` |
| `CANCELLED` | `api`/`tool_layer` |
| `COMPLETED` | `queue_worker` (Cron Job theo `end_at` đã qua) |

### 5.4 Quan hệ `request` ↔ artifact

Không đổi so với mục Một Request, nhiều loại artifact của `00-domain.md`: một `request` sinh 0..n artifact (`document`, `room_booking` `[Should]`); `request` chuyển `FULFILLED` khi mọi artifact tới trạng thái cuối; sau đó artifact tiếp tục sống đời riêng (ví dụ `document` bị `REVOKED`) mà không kéo `request` ra khỏi `FULFILLED`. Về mặt component: `tool_layer` là nơi duy nhất kiểm tra điều kiện "mọi artifact đã tới trạng thái cuối" trước khi phát transition `FULFILLED`.

---

## 6. Sequence diagram

Mỗi luồng có ít nhất một nhánh lỗi/thay thế (đánh dấu `alt`/`else`).

### (a) Tạo yêu cầu qua chat → phân loại → thiếu slot → hỏi lại

```mermaid
sequenceDiagram
    actor NV as Nhan vien
    participant API as api
    participant ORC as orchestrator
    participant GW as ai_gateway

    NV->>API: Gui tin nhan chat
    API->>ORC: Chuyen luot hoi thoai
    ORC->>GW: Phan loai + trich slot (model re)
    GW-->>ORC: request_type de xuat + slot trich duoc
    alt Slot bat buoc con thieu
        ORC->>API: Cau hoi bo sung slot con thieu
        API-->>NV: Hien cau hoi, request chuyen NEEDS_INFO
    else Phan loai nhap nhang (nhom G, EC-CV-03)
        ORC->>API: Cau hoi lam ro y dinh, khong doan
        API-->>NV: Hien cau hoi lam ro
    else Du dieu kien xu ly (dinh nghia F1)
        ORC->>API: Xac nhan da du slot
        API-->>NV: Thong bao san sang gui yeu cau
    end
```

### (b) Sinh văn bản từ template + RAG

```mermaid
sequenceDiagram
    actor NV as Nhan vien
    participant API as api
    participant DB as postgresql
    participant Worker as queue_worker
    participant ORC as orchestrator
    participant GW as ai_gateway
    participant TL as tool_layer
    participant OS as object_storage

    NV->>API: Xac nhan gui yeu cau (du dieu kien xu ly)
    API->>DB: Chuyen request sang SUBMITTED + enqueue job render (cung mot giao dich)
    API-->>NV: Tra ve ket qua ngay, khong cho render xong
    Worker->>DB: Lay job render tiep theo (SKIP LOCKED)
    Worker->>ORC: Chay document_graph
    ORC->>TL: template_fetch - tra cuu chinh xac template dang hieu luc
    TL-->>ORC: Template, phien ban, danh muc bien
    ORC->>TL: request_slots_read - chi slot da khai cho bien noi dung tu do
    ORC->>GW: Sinh noi dung tu do (model manh, chi input da khai, khong co retrieval)
    GW-->>ORC: Noi dung tu do
    ORC->>TL: Ghi noi dung, dien bien vao template, render document
    TL->>OS: Luu ban render DRAFT
    alt Du dieu kien trinh duyet (dinh nghia F2)
        TL->>DB: Chuyen document sang PENDING_APPROVAL
    else Thieu bien bat buoc hoac render tu template het hieu luc
        TL->>DB: Giu document o DRAFT, ghi audit_event canh bao
        TL-->>ORC: Bao khong dat, graph vao halt_for_human (co che dung o Phase 8)
    end
```

### (c) HITL duyệt/từ chối/yêu cầu sửa — `interrupt` + resume

```mermaid
sequenceDiagram
    actor CB as Can bo hanh chinh
    participant API as api
    participant TL as tool_layer
    participant ORC as orchestrator
    participant DB as postgresql
    participant Worker as queue_worker

    CB->>API: Mo hang doi, xem document PENDING_APPROVAL
    CB->>API: Gui quyet dinh
    API->>TL: Kiem permission tuong ung
    alt Duyet noi dung
        TL->>DB: document -> APPROVED, audit_event
        TL->>DB: Enqueue job resume_document_graph (cung giao dich, ADR-010)
        Worker->>ORC: Resume graph tai node dinh tuyen ky
    else Yeu cau sua - noi dung soan sai (FREE_CONTENT)
        TL->>DB: document -> CHANGES_REQUESTED, request giu nguyen IN_REVIEW
        TL->>DB: Enqueue job resume_document_graph (cung giao dich, ADR-010)
        Worker->>ORC: Resume graph, sinh lai dung cac bien nguoi duyet chon (ADR-009)
    else Yeu cau sua - du lieu khai sai hoac thieu (SLOT_DATA)
        TL->>DB: document -> CHANGES_REQUESTED, request -> CHANGES_REQUESTED
        TL->>DB: Enqueue job resume_document_graph (cung giao dich, ADR-010)
        Worker->>ORC: Resume graph, cho nhan vien bo sung va gui lai (gioi han A-022, Phase 8)
    else Tu choi kem ly do
        TL->>DB: document -> REJECTED, request -> REJECTED
    end
```

### (d) Phát hành + cấp số + đóng dấu

```mermaid
sequenceDiagram
    actor CB as Can bo hanh chinh
    participant API as api
    participant TL as tool_layer
    participant DB as postgresql
    participant Worker as queue_worker
    participant ORC as orchestrator

    CB->>API: Dong dau (PENDING_SEAL -> SEALED)
    API->>TL: Kiem permission document.apply_seal
    TL->>DB: Ghi seal_register, document -> SEALED
    CB->>API: Cap so va phat hanh
    API->>TL: Kiem permission document.issue
    TL->>DB: Ghi lenh phat hanh + enqueue job finalize_issue (cung giao dich, ADR-010)
    TL-->>CB: Xac nhan da ghi lenh, document van SEALED, chua co so
    Worker->>ORC: Chay finalize_issue
    ORC->>TL: document_number_assign - giao dich nguyen tu lay so tu document_register
    ORC->>TL: Render ban cuoi co so va ngay, kiem approved_content_hash
    alt Hoan tat thanh cong
        TL->>DB: document -> ISSUED, gan document_number
    else That bai sau khi da lay so
        TL->>DB: Danh dau so la VOIDED kem ly do, khong tai su dung
        TL->>DB: Document giu nguyen o SEALED, ghi ly do dung qua document_halt_record
        TL-->>CB: Bao loi qua thong bao, khong qua loi goi dong bo
    end
```

### (e) Thu hồi văn bản đã phát hành

```mermaid
sequenceDiagram
    actor A as Can bo A - revoke_initiate
    actor B as Can bo B - revoke_confirm
    participant API as api
    participant TL as tool_layer
    participant DB as postgresql

    A->>API: Khoi tao thu hoi kem revocation_reason
    API->>TL: Kiem permission document.revoke_initiate
    TL->>DB: Ghi audit_event khoi tao, cho xac nhan
    B->>API: Xac nhan thu hoi
    API->>TL: Kiem permission document.revoke_confirm
    alt A va B la hai nguoi khac nhau
        TL->>DB: document -> REVOKED
    else A va B la cung mot nguoi
        TL-->>API: Tu choi (duong thoat rieng cho truong hop mot nguoi thuoc Phase 8)
    end
```

### (f) `[Should]` Đặt phòng họp có xung đột lịch

```mermaid
sequenceDiagram
    actor NV as Nhan vien
    participant ORC as orchestrator
    participant TL as tool_layer
    participant DB as postgresql

    NV->>ORC: Yeu cau dat phong, du slot
    ORC->>TL: Kiem tra xung dot lich cho room_id, khung gio
    TL->>DB: Truy van room_booking dang HELD hoac CONFIRMED trung khung gio
    alt Khong trung lich
        TL->>DB: Tao room_booking o HELD
        TL-->>ORC: Xac nhan giu cho
    else Trung lich
        TL-->>ORC: Bao trung, de xuat phong hoac khung gio khac
        ORC-->>NV: Thong bao xung dot, khong tu doi lich nguoi khac
    end
```

---

## 7. ADR mới ở phase này

- **ADR-002** — `vector_store` là `pgvector` trong `postgresql`, không phải vector DB riêng.
- **ADR-003** — `object_storage` là dịch vụ S3-compatible, bất biến đảm bảo ở tầng ứng dụng, vendor `TBD` (A-024).
- **ADR-004** — `queue_worker` dùng bảng job trong `postgresql`, không thêm Redis/Celery.
- **ADR-005** — `orchestrator` là thư viện dùng chung trong `api`/`queue_worker`, không phải service riêng.

Cả bốn ADR đều nêu **điều kiện đảo ngược** (hình dạng tín hiệu, không phải con số — vì A-002 chưa có số liệu tải) và **lý do loại phương án khác nhau giữa bốn ADR**, không dùng chung một khuôn lập luận.

---

## Open Questions

Không có câu hỏi mở nào chỉ tồn tại trong file này.

Giả định mới do Phase 2 phát sinh nằm ở `ASSUMPTIONS.md`: **A-024** (nhà cung cấp `object_storage` cụ thể), **A-025** (giới hạn thời gian request của Render). File này cũng phụ thuộc **A-002** (chưa có số liệu tải thật) — đây là lý do cả bốn ADR chỉ mô tả được hình dạng tín hiệu đảo ngược, không đặt được ngưỡng số.

Một mâu thuẫn giữa phase trước đã được tìm thấy và xử lý ở phase gốc, không phải ở đây: NFR-05 của `01-prd.md` (đã sửa, xem `CHANGELOG.md`) — chi tiết ở mục Đã đối chiếu ở đầu file này.
