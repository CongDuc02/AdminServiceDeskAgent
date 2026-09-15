# ADR-024 — Định dạng `trace_id`: UUID v4, với điều kiện đảo ngược buộc chéo vào A-069

**Trạng thái:** Accepted · **Ngày:** 2026-09-16 · **Quyết định tại:** Phase 11 — Ops, Cost & Deployment · **Liên quan:** ADR-019 (câu bỏ ngỏ về định dạng `trace_id`), A-069 (chọn công cụ APM), mục Log schema của `11-ops.md`

---

## Context

ADR-019 để ngỏ một câu, nguyên văn: *"Thêm `CHECK` hình dạng cần định dạng của `trace_id`, mà chưa phase nào chốt — không bịa ở đây."* Phase 11 (Observability) là phase tự nhiên đóng câu này, vì `trace_id` chỉ có ý nghĩa trong bối cảnh log/trace mà Phase 11 thiết kế.

Cùng phase này mở **A-069** (chọn công cụ APM/metric cụ thể — chưa chọn, chưa cần chọn ngay). Nhiều hệ quan sát/APM ép một định dạng trace ID riêng của chúng — ví dụ W3C Trace Context (`traceparent`) dùng 16 byte (32 ký tự hex, không gạch nối), một số APM thương mại dùng số nguyên 64-bit. Nếu định dạng chốt hôm nay không tương thích với công cụ chọn sau ở A-069, phải sửa một `CHECK` trong DB — một migration nữa.

Áp phép thử J3 (CHANGELOG 2026-09-13 lần 3): **"có điều kiện đảo ngược không"**, không phải "có phải mẫu hình kiến trúc mới không". Có — điều kiện đảo ngược nêu được rõ ràng: công cụ APM chọn ở A-069 ép một định dạng khác UUID v4. Cùng dạng với điều kiện đảo ngược của `argon2id` (ADR-021: RAM instance đo được khi có Render đầu tiên). **Cần ADR**, không phải chỉ một dòng cấu hình trong `11-ops.md`.

## Options

- **A — UUID v4.** Chữ thường, có gạch nối (`8-4-4-4-12` hex).
- **B — ULID.** Sortable theo thời gian, cần thư viện mới.
- **C — W3C Trace Context (`traceparent` trace-id).** 32 ký tự hex, không gạch nối — chuẩn OpenTelemetry.
- **D — Hoãn định dạng, chờ A-069 chọn công cụ trước.** Không thêm `CHECK` nào ở Phase 11.

## Decision

**Chọn A — UUID v4**, với điều kiện đảo ngược ghi tường minh và buộc chéo vào A-069.

1. **Không thư viện mới, không quy ước mới.** Mọi khoá chính trong `schema.sql` đã là `uuid`. Sinh `trace_id` bằng đúng cơ chế đã dùng ở mọi nơi khác trong hệ thống.
2. **D bị loại vì để câu bỏ ngỏ của ADR-019 tiếp tục treo** — đúng lỗi đã bị bắt một lần ("sắp rơi giữa hai phase lần thứ hai"). Không thiết kế được `CHECK` nào nếu không chốt định dạng trước.
3. **C (W3C Trace Context) bị loại vì tiền-cam-kết một hệ sinh thái quan sát (OpenTelemetry) trước khi A-069 chọn công cụ** — đúng loại quyết định sớm mà dự án này tránh (ví dụ cách A-026 không chốt provider LLM trước khi cần).

**Điều kiện đảo ngược, ghi tường minh:** nếu công cụ APM chọn ở A-069 **bắt buộc** một định dạng `trace_id` khác UUID v4 (ví dụ để tích hợp trực tiếp, không qua tầng dịch), quyết định này phải mở lại — cần một `ALTER TABLE ... DROP CONSTRAINT` + `ADD CONSTRAINT` mới (migration tiếp theo), và một quyết định về các dòng `llm_usage`/`audit_event` đã ghi trước đó mang định dạng cũ (chấp nhận `CHECK` mới chỉ áp cho dòng ghi sau, hoặc chuyển đổi hồi tố — quyết định của lúc đó, không phải bây giờ).

**Buộc chéo vào A-069 (mục 12 của `ASSUMPTIONS.md`):** tiêu chí chọn công cụ APM ở A-069 phải bao gồm câu hỏi *"công cụ này có ép một định dạng trace ID không tương thích UUID v4 không"* — người chọn công cụ đọc A-069 phải thấy ràng buộc này, không được để nó chỉ nằm trong một ADR riêng mà không ai đọc lại lúc chọn.

## Consequences

**Tích cực**

- Đóng câu bỏ ngỏ của ADR-019, không để nó rơi giữa hai phase lần thứ hai.
- Không tốn thư viện, không tốn quy ước mới — nhất quán với mọi `uuid` khác trong hệ thống.
- Điều kiện đảo ngược được đặt tên và buộc chéo, không để người chọn APM sau này phát hiện xung đột một cách bất ngờ.

**Tiêu cực và cái phải chấp nhận**

- Không tương thích trực tiếp với W3C Trace Context — nếu tổ chức về sau muốn dùng công cụ chuẩn OpenTelemetry, cần một tầng dịch (map UUID v4 nội bộ sang `traceparent` ở biên xuất log ra ngoài) hoặc phải đảo ADR này.
- Migration tương lai (nếu điều kiện đảo ngược xảy ra) phải xử lý dữ liệu lịch sử — không giải quyết trước ở đây, vì chưa biết công cụ nào sẽ được chọn.

## Rejected alternatives

**B — ULID.** Có ưu điểm sắp xếp theo thời gian, nhưng không giải quyết vấn đề tương thích APM tốt hơn UUID v4 (ULID cũng không phải chuẩn của bất kỳ hệ APM lớn nào), trong khi lại cần một thư viện mới. Không đổi được rủi ro chính, chỉ đổi rủi ro phụ.

**C — W3C Trace Context.** Xem lý do loại ở mục Decision — tiền-cam-kết một hệ sinh thái trước khi cần.

**D — Hoãn định dạng.** Xem lý do loại ở mục Decision — để câu bỏ ngỏ của ADR-019 tiếp tục treo.
