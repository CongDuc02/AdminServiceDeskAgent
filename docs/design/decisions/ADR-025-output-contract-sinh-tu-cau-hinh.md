# ADR-025 — Enum của output contract sinh từ cấu hình lúc gọi, không viết cứng trong prompt module

**Trạng thái:** Accepted · **Ngày:** 2026-09-25 · **Quyết định tại:** đợt sửa A-068, A-073, A-075 sau Phase 12 · **Liên quan:** A-075, A-076, ADR-007 (output là JSON Schema đóng), ADR-008 (allowlist là danh sách nạp), ADR-009 (một biến một lời gọi), ADR-019 (`llm_usage`), F6 của `01-prd.md`, mục Output contract của `07-prompts.md`

---

## Context

F6 có một AC cứng, cũng là điều 4 ở mục Definition of Done của `01-prd.md`: thêm một `request_type` thứ ba **chỉ bằng cấu hình và một file template — không sửa code, không deploy lại**. `request_type_catalog`, input của P1 `classify_intent`, đã là cấu hình. Nhưng output contract của P1 liệt kê cứng các mã `request_type` trong enum của `intent`, và prompt module sống trong mã (`bo19.ai_gateway.prompt_modules`, mục Cây backend của `06-structure.md`). Thêm một dòng vào catalog không thêm được mã đó vào enum, nên `classify_intent` không bao giờ trả được loại mới, và loại mới không bao giờ được mở qua chat (A-075). Enum `variable_name` của `DraftContentResult` (P4, P5) có cùng vấn đề với biến nội dung tự do của template mới.

Đây là quyết định kiến trúc, không chỉ là sửa một schema: nó đổi **nơi output contract được định nghĩa** — từ hằng trong mã sang dữ liệu cấu hình đọc lúc gọi — và kéo theo câu hỏi phiên bản của prompt module nghĩa là gì.

## Options

- **A — Enum tĩnh, thêm loại là sửa mã và deploy lại.**
- **B — Bỏ enum, để `intent` là string tự do; chỉ node kiểm mã có trong catalog.**
- **C — Enum sinh lúc gọi, từ chính giá trị `request_type_catalog` đã nạp làm input của lời gọi đó.** Node vẫn kiểm lại.
- **D — Enum sinh một lần lúc khởi động tiến trình, từ catalog đọc lúc đó.**

## Decision

**Chọn C** — quyết định của PO, 2026-09-25.

- `intent`: mã có `support_status` ∈ {`SUPPORTED`, `KNOWN_UNSUPPORTED`} trong catalog của lời gọi, cộng `OUT_OF_SCOPE`, `NEED_CLARIFICATION`. `secondary_intent`: cùng lần dựng, bỏ `NEED_CLARIFICATION`, cộng `null`.
- `variable_name` của P4/P5: đúng một giá trị — biến `FREE_CONTENT` mà lời gọi sinh, lấy từ `template_variable` của phiên bản template đã ghim.
- **Một nguồn cho mỗi lời gọi.** Enum và phần context của prompt lấy từ cùng một giá trị input, nên không thể lệch nhau giữa hai lần đọc. `ai_gateway.json_contract` dựng schema; allowlist không đổi, vì không có input nào mới.
- **Node vẫn kiểm lại** mã nhận về theo đúng catalog đó — lớp thứ hai cho nhánh provider không ép được schema (mục Chiến lược ép JSON và xử lý lỗi parse của `07-prompts.md`).
- **Phiên bản:** catalog hay template đổi thì `prompt_module_version` **không** đổi; đổi luật sinh mới là đổi `major`. Truy vết bằng `catalog_fingerprint` — sha256 của bản tuần tự hoá chuẩn của catalog — ghi vào log kỹ thuật và bản ghi eval, không vào `llm_usage`.

## Consequences

**Tích cực**

- AC cứng của F6 đạt được ở tầng thiết kế: loại mới vào catalog là vào enum ngay ở lời gọi kế tiếp.
- Giữ được cả hai nhánh ép JSON của ADR-007 — schema vẫn đóng ở mỗi lời gọi, chỉ không cố định giữa các lời gọi.
- Tiêu chí T6 của mục Loại yêu cầu thứ ba trong `12-roadmap.md` — "không có biến nội dung tự do" — không còn cần.

**Tiêu cực và cái phải chấp nhận**

- **Hành vi của `classify_intent` đổi mà không có commit nào.** Thêm loại, hay chỉ sửa `example_phrases`, là đổi input của mọi lời gọi P1 sau đó. Regression gate của `10-eval.md` chạy ở CI, nên **không chặn** được thay đổi này. Ghi thành A-076, với biện pháp bù tối thiểu: loại mới phải có `example_phrases` và qua một lần diễn tập thủ công trước khi sang `SUPPORTED`.
- `prompt_module_version` một mình không còn đủ để tái tạo một lời gọi P1; phải có thêm `catalog_fingerprint`. Chưa có chỗ trong `llm_usage` — đó là lựa chọn, vì ADR-019 giữ bảng đó hẹp.
- Schema khác nhau giữa các lời gọi, nên nếu provider được chọn (A-026) cache schema theo định danh thì phải dùng định danh theo `catalog_fingerprint`. `[CẦN XÁC MINH]` theo tài liệu của provider khi chọn.

**Điều kiện đảo ngược:** provider được chọn ở A-026 không nhận schema khác nhau theo từng lời gọi, **và** nhánh tự validate phía `ai_gateway` không đủ độ tin cậy trên chính bộ eval. Khi đó xét lại A hoặc D.

## Rejected alternatives

**A — enum tĩnh, sửa mã khi thêm loại.** Trái thẳng AC cứng của F6 và điều 4 của Definition of Done. Hạ AC để hợp mã là sửa ngược chiều — cùng lý do đã loại phương án (ii) của A-042.

**B — string tự do, chỉ node kiểm.** Mất khả năng ép schema phía provider ở nhánh A của `07-prompts.md`: model được phép trả bất cứ chuỗi nào, và mọi mã bịa ra thành một vòng sửa lỗi parse thay vì bị chặn ngay khi sinh. Node kiểm lại vẫn cần — nhưng làm lớp duy nhất thì yếu hơn C.

**D — sinh một lần lúc khởi động.** Catalog đổi lúc chạy qua `request_type_upsert`; enum dựng lúc khởi động sẽ cũ tới lần deploy sau, tức vẫn đòi deploy lại để loại mới có hiệu lực — đúng thứ F6 cấm, chỉ là muộn hơn một bước. Còn tạo khoảng lệch giữa enum (cũ) và context của prompt (mới) trong cùng một lời gọi.
