# ADR-019 — `ai_gateway` ghi đúng một bảng: `llm_usage`

**Trạng thái:** Accepted · **Ngày:** 2026-09-13 · **Quyết định tại:** Phase 6 — Project Structure · **Liên quan:** NFR-06 của `01-prd.md`, ADR-007, ADR-008, A-022, A-031, mục Component diagram của `02-architecture.md`, mục Tool Registry của `03-agents.md`, mục Bảng chi tiết của `04-data.md`, mục Luật import của `06-structure.md`

---

## Context

Luật ở mục Tool Registry của `03-agents.md`: mọi ghi `postgresql` đi qua `tool_layer`, trừ một **danh sách ngoại lệ đóng** — tới Phase 5 có hai mục, bảng checkpoint và `graph_thread`.

`04-data.md` giao việc kế toán token cho `ai_gateway`: index `ix_llm_usage_request` tồn tại vì "`ai_gateway` cộng token đã tiêu của chủ budget trước mỗi lời gọi — nằm trên đường nóng"; bước nạp kho ghi "token ghi vào `llm_usage`". Nhưng component diagram của `02-architecture.md` không có cạnh nào từ `ai_gateway` tới `postgresql`, và `llm_usage` không nằm trong danh sách ngoại lệ. Ba tài liệu nói ba điều không khớp. Lỗi phát hiện ở bước lập kế hoạch Phase 6.

Trần budget (NFR-06, A-022) chỉ có nghĩa nếu nó được thi hành ở chỗ **mọi** lời gọi ra model đều phải đi qua. Chỗ đó là `ai_gateway`.

## Options

**A — `ai_gateway` đọc và ghi thẳng `llm_usage`**, là mục thứ ba có tên của danh sách ngoại lệ.

**B — `ai_gateway` gọi `tool_layer` để ghi** — một thao tác có tên kiểu `llm_usage_record`.

**C — Node gọi `ai_gateway` tự lo budget:** đọc số đã tiêu qua `tool_layer`, truyền vào `ai_gateway`, rồi ghi usage qua `tool_layer` sau lời gọi.

**D — Không ghi bảng; chỉ ghi log `observability` rồi tổng hợp sau.**

## Decision

**Chọn A, với phạm vi hẹp:**

- Ngoại lệ **không phải** "`ai_gateway` được ghi `postgresql`". Nó là: **`ai_gateway` ghi đúng một bảng, `llm_usage`, và không bảng nào khác.** Phép đọc duy nhất của nó cũng là trên `llm_usage` — tổng token đã tiêu của một chủ budget.
- **Ràng buộc bù**, cùng hình dạng với ràng buộc bù của `graph_thread`: `llm_usage` không chứa văn bản prompt, văn bản output hay giá trị slot. Điều này đứng ở tầng DB bằng **tập cột**, không phải bằng lời hứa: bảng không có cột nào dành cho văn bản; `call_name`, `model_tier`, `outcome` bị `CHECK` khoá vào danh sách đóng; bảng là chỉ thêm với `bo19_app`. **Chỗ hở còn lại, nói thẳng:** hai cột kiểu `text` không có `CHECK` hình dạng — `prompt_module_version` và `trace_id`. Chúng được chặn ở tầng ứng dụng bằng kiểu: module sổ của `ai_gateway` chỉ nhận định danh phiên bản và `trace_id` từ ngữ cảnh trace, không nhận chuỗi tự do. Thêm `CHECK` hình dạng cần định dạng của `trace_id`, mà chưa phase nào chốt — không bịa ở đây.
- **Không sinh `audit_event`.** Đây là sổ sách kỹ thuật, không phải hành động nghiệp vụ — cùng lý do với checkpoint và `graph_thread`.
- Trong cây mã, việc ghi và đọc `llm_usage` nằm ở **đúng một module** của `ai_gateway` — module sổ budget ở mục Cây backend của `06-structure.md` — và `.importlinter` chặn mọi phần khác của `ai_gateway` import quyền ghi của lớp truy cập DB.

### Trần budget fail-closed — ba ca, viết cho hết

1. **Không đọc được số token đã tiêu** — lỗi DB, timeout. `ai_gateway` **từ chối** lời gọi, không gọi provider, và cố ghi một dòng `outcome = BUDGET_UNAVAILABLE`. **Đây là mã mới**: `ck_llm_usage_outcome` là danh sách đóng, và `BUDGET_EXCEEDED` sai nghĩa cho ca này — trần chưa chạm, chỉ là không biết. Dùng nhầm thì tỷ lệ chạm trần mà Phase 11 dùng để định cỡ A-022 bị trộn với tỷ lệ DB hỏng. Mã mới đã vào `ck_llm_usage_outcome` của `schema.sql` và mục Bảng chi tiết của `04-data.md` ở Phase 6. **Giới hạn:** DB không đọc được thì rất có thể cũng không ghi được. Khi đó dòng sổ không tồn tại, chỉ còn một sự kiện log có `trace_id` ở `observability`. Lời gọi vẫn bị từ chối — fail-closed không phụ thuộc việc ghi sổ thành công.
2. **Chưa cấu hình trần.** Giá trị trần còn `TBD` (A-022, A-031), nhưng cấu hình thiếu **không bao giờ** được hiểu là "không có trần". Kiểu cấu hình không có giá trị rỗng cho trần. Thiếu một trần nào thì **bước kiểm khởi động từ chối khởi động** `api` và `queue_worker` (mục Bước kiểm khởi động của `06-structure.md`) — không đợi tới lời gọi đầu tiên lúc hai giờ sáng. Giá trị khởi đầu được phép mang nhãn "chưa hiệu chỉnh" theo A-031; nó chỉ không được vắng mặt.
3. **Dòng của hai ca từ chối — `BUDGET_EXCEEDED` và `ALLOWLIST_REJECTED` — do chính `ai_gateway` ghi, trong một giao dịch riêng, commit xong mới trả lỗi cho node.** Node chết ngay sau đó thì dòng vẫn còn. Đây là lý do mạnh nhất cho ADR này: với B hay C, việc ghi xảy ra sau khi quyền điều khiển đã về tay node, nên node chết là lần từ chối biến mất khỏi sổ — đúng loại dừng không để lại dấu mà NFR-06 cấm.

Ca thường — `OK`, `PARSE_REPAIRED`, `PARSE_FAILED`, `PROVIDER_ERROR`: dòng được ghi sau khi provider trả về, trong giao dịch riêng, commit trước khi output về tới node.

**Không có chủ budget thì không có lời gọi.** `ck_llm_usage_has_budget_owner` buộc mỗi dòng có ít nhất một trong `request_id`, `chat_session_id`, `procedure_document_version_id`. `ai_gateway` từ chối lời gọi thiếu chủ budget **trước** khi gọi provider; không ghi được dòng nào cho ca này vì chính `CHECK` đó, nên nó chỉ để lại log. Đây là lỗi lập trình, không phải ca vận hành.

## Consequences

**Tích cực**

- Trần budget thi hành ở một chỗ mà mọi lời gọi LLM và embedding đều qua. Không node nào quên được việc kiểm, vì node không làm việc đó.
- Sổ chi phí đầy đủ cả ở những ca node chết.
- Không cạnh mới giữa `ai_gateway` và `tool_layer`: hai module giữ quan hệ độc lập mà `.importlinter` khai.

**Tiêu cực và cái phải chấp nhận**

- `ai_gateway` phụ thuộc lớp truy cập DB. Test của nó cần một cơ sở dữ liệu, hoặc một bản giả của module sổ.
- **Tiến trình chết giữa lúc gọi provider:** token đã tiêu mà chưa có dòng. `llm_usage` là chỉ thêm, không có dòng "đang gọi" để sửa sau, nên sổ **đếm thiếu** tối đa một lời gọi cho mỗi lần chết. Chấp nhận; retry của lời gọi đó được đếm như một lời gọi mới.
- **Đọc rồi mới gọi, không khoá:** hai lời gọi đồng thời cùng một chủ budget có thể cùng thấy "chưa chạm trần" và cùng đi qua. Vượt trần tối đa bằng chi phí các lời gọi đồng thời đó. Đồng thời trên cùng chủ budget vốn đã bị chặn ở tầng khác: lượt chat của một phiên chạy tuần tự (`TURN_IN_PROGRESS`), thread `document:{id}` chạy tuần tự. Không thêm khoá.

**Điều kiện đảo ngược** — tín hiệu kiến trúc: xuất hiện một bảng thứ hai mà `ai_gateway` "cần" ghi. Khi đó **không** mở rộng ngoại lệ này; phải có ADR mới, và câu hỏi đầu tiên của ADR đó là vì sao việc ghi kia không thuộc `tool_layer`.

## Rejected alternatives

**B — `ai_gateway` gọi `tool_layer`.** Loại vì lý do kỹ thuật:

1. Node gọi cả `tool_layer` lẫn `ai_gateway`; hai module là **ngang hàng**, và `.importlinter` của `06-structure.md` khai chúng độc lập với nhau. Cho `ai_gateway` import `tool_layer` là phá đúng contract Phase 6 đang dựng để cấm, và phép kiểm tĩnh báo đỏ. Nó thành **vòng phụ thuộc theo nghĩa đen** ngay khi có một phần của `tool_layer` cần tới `ai_gateway` — hôm nay chưa có, vì embedding của `procedure_ingest` được `queue_worker` gọi chứ không phải `tool_layer`. Nhưng một luật chỉ đúng vì chưa ai viết đoạn mã thứ hai là luật dễ gãy.
2. Phương án này chỉ lành mạnh nếu việc ghi nằm ở một tầng **thấp hơn cả hai** module. Mà một tầng thấp hơn cả hai, được gọi thẳng từ `ai_gateway` để ghi `llm_usage`, chính là quyết định của ADR này dưới tên khác.
3. Thao tác của `tool_layer` sinh `audit_event` theo luật hiện hành. Ghi qua đó là thêm một dòng nhật ký nghiệp vụ bất biến cho **mỗi** lời gọi LLM — cùng loại mâu thuẫn A-055 đang treo.

**C — Node tự lo budget.** Loại vì **fail-open**: node nào quên đọc hoặc quên truyền budget thì lời gọi đi qua không có trần, và không phép kiểm nào nhận ra, vì mọi test chức năng vẫn xanh. Thêm vào đó, logic budget bị chép vào mọi nơi gọi model — năm lời gọi LLM và hai lời gọi embedding — và dòng sổ phụ thuộc việc node còn sống (ca 3 ở trên).

**D — Chỉ ghi log.** Loại vì phép kiểm trần nằm trên đường nóng và phải đọc được tổng đã tiêu **trước** mỗi lời gọi. Log của `observability` không phải nguồn truy vấn được trên đường đó, và có thể xoay vòng theo chính sách giữ log kỹ thuật.
