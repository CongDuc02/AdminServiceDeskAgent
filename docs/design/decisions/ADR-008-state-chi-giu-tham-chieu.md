# ADR-008 — State LangGraph chỉ giữ tham chiếu; allowlist input là danh sách nạp, fail-closed

**Trạng thái:** Accepted · **Ngày:** 2026-09-12 · **Quyết định tại:** Phase 3 — Agent & Tool Architecture · **Liên quan:** NFR-05 của `01-prd.md`, A-014, A-010, mục Data flow diagram của `02-architecture.md`, ADR-006, ADR-007

---

## Context

Hai nghĩa vụ trong `_PLAN.md` Phase 3 cùng rơi vào state của LangGraph:

1. **Allowlist input.** Mỗi prompt module khai đích danh slot nó cần; `ai_gateway` chỉ đưa đúng danh sách đó vào prompt (NFR-05). Nhưng LangGraph mặc định truyền **toàn bộ state** vào mọi node. Nếu state chứa giá trị mọi slot, allowlist chỉ có thể là một **bộ lọc** đặt giữa state và prompt.
2. **Checkpoint là kho PII.** State được checkpointer ghi lại theo từng bước, kể cả lịch sử. Khi `request` `EXPIRED`, slot `RES` phải bị xoá khỏi **mọi** checkpoint (A-014), không chỉ khỏi bảng `request`.

## Options

**A — State giữ giá trị** theo thói quen của LangGraph: slot, tin nhắn, output LLM đều nằm trong state. Allowlist là bộ lọc trong `ai_gateway`. Khi `EXPIRED` thì xoá toàn bộ checkpoint của thread.

**B — State chỉ giữ tham chiếu và dữ liệu điều khiển luồng** (id, mã enum, tên slot, bộ đếm). Giá trị slot, tin nhắn thô và mọi văn bản do LLM sinh ra nằm ở bảng nghiệp vụ trong `postgresql`. Node nạp giá trị qua `tool_layer` **theo đúng danh sách input mà prompt module tự khai**.

## Decision

**Chọn B.**

- **Allowlist là danh sách nạp, không phải bộ lọc.** Danh sách input khai trong prompt module là nguồn duy nhất để node nạp dữ liệu (`request_slots_read` với đúng danh sách tên đó) và để `ai_gateway` lắp prompt. `ai_gateway` kiểm tra tập khoá được đưa vào **bằng đúng** tập đã khai: thừa một khoá thì từ chối, thiếu một khoá thì từ chối.
- **Fail-closed.** Quên khai một slot thì slot đó không bao giờ được nạp, nên prompt thiếu dữ liệu và bước đó **mất chức năng** — chứ không **rò dữ liệu**. Sai kiểu này tự bộc lộ khi test, vì output sai hoặc rỗng. Ngược lại, với bộ lọc (Option A), quên loại một slot thì dữ liệu lọt ra mà mọi test chức năng vẫn xanh.
- **Output LLM có giá trị được ghi xuống DB ngay trong node đã gọi LLM**, qua `tool_layer`. State chỉ nhận lại tên và mã kết quả. Giá trị không đi từ node này sang node khác qua state.
- **Dữ liệu dẫn xuất từ tin nhắn thô** (ví dụ `retrieval_query`) lưu cùng dòng `chat_message` sinh ra nó, cùng độ nhạy và cùng số phận khi xoá.
- **Checkpoint không chứa giá trị slot hay văn bản tự do theo cấu tạo.** Việc xoá slot `RES` khỏi mọi checkpoint khi `EXPIRED` vì vậy không cần thao tác nào trên checkpoint: không có gì để xoá. Việc xoá thật xảy ra trên bảng nghiệp vụ, nơi thao tác theo từng slot là một câu SQL bình thường.
- **Phòng thủ lớp hai:** checkpoint của một thread bị purge khi thread kết thúc (chi tiết ở mục Checkpointer và PII của `03-agents.md`).

## Consequences

**Tích cực**

- Allowlist và state nhất quán theo cấu tạo: node không có "toàn bộ state có giá trị" để lỡ tay truyền đi.
- Nghĩa vụ xoá của A-014 chỉ còn một nơi thực thi (bảng nghiệp vụ), key theo `slot_sensitivity`, không phải một thao tác riêng trên blob checkpoint đã tuần tự hoá.
- Resume sau nhiều ngày luôn đọc dữ liệu mới nhất từ DB, không phải bản sao cũ trong state.
- Đổi schema state giữa chừng ít rủi ro hơn, vì state nhỏ và không chứa dữ liệu nghiệp vụ.

**Tiêu cực và cái phải chấp nhận**

- Mỗi node gọi LLM đọc DB nhiều hơn. Chấp nhận ở quy mô hiện biết (A-002).
- Không dùng các tiện ích LangGraph dựa trên message trong state. Graph viết dài hơn.
- Checkpoint không còn hữu ích để debug nội dung. Debug phải dựa vào log kỹ thuật đã mask của `observability`.
- **Cái ADR này không tự bảo đảm:** một kỹ sư thêm một trường chuỗi tự do vào state là phá được nó. Chốt chặn: state khai bằng `TypedDict` không có trường văn bản tự do; bộ tuần tự hoá checkpoint từ chối khoá không có trong schema; và một **test canary** ở Phase 10 — chạy hội thoại chứa giá trị `RES` đánh dấu rồi quét bảng checkpoint — phải cho kết quả rỗng.

**Điều kiện đảo ngược** — tín hiệu vận hành, đo ở `observability`: số truy vấn và latency đọc DB do node gọi LLM gây ra, đặt cạnh latency lượt chat (cùng trục thời gian với tín hiệu của ADR-005). Nếu tải đọc này thành nguyên nhân chính khiến lượt chat tiến sát giới hạn thời gian request (A-025), phải xét lại cách nạp — nhưng không được xét lại bằng cách quay về allowlist dạng bộ lọc.

## Rejected alternatives

**A — State giữ giá trị, allowlist là bộ lọc.** Bị loại vì hai lý do độc lập:

1. **Bộ lọc hỏng theo hướng rò.** Thêm một slot mới vào state mà quên cập nhật bộ lọc, hoặc một node truyền nhầm đối tượng state, thì dữ liệu đi ra ngoài mà không test chức năng nào phát hiện. Đây đúng là họ lỗi "cơ chế có trên giấy nhưng không kích hoạt" đã ghi ở `CHANGELOG.md`.
2. **Xoá theo từng slot trên checkpoint là không khả thi.** Checkpoint lưu state đã tuần tự hoá theo từng bước; chỉ xoá được nguyên thread. A-014 lại yêu cầu xoá `RES` mà **giữ** `INT`/`PER`. Muốn xoá nguyên thread mà không mất dữ liệu cần giữ thì thread phải trùng đúng một `request` — điều này mâu thuẫn với EC-CV-01 và EC-CV-02, nơi một cuộc hội thoại sinh ra nhiều `request` nối tiếp.
