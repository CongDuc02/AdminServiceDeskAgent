# ADR-013 — Hai luồng SSE, luồng dài chỉ mang tín hiệu; xác thực bằng session cookie HttpOnly

**Trạng thái:** Accepted · **Ngày:** 2026-09-13 · **Quyết định tại:** Phase 5 — API Spec · **Liên quan:** ADR-004, ADR-005, ADR-007, NFR-04, NFR-05, NFR-08 của `01-prd.md`, mục Ánh xạ sang đơn vị triển khai trên Render của `02-architecture.md`, A-025, A-031, A-048, A-049, A-050, A-051

---

## Context

Có hai nhu cầu đẩy dữ liệu từ server xuống client:

1. **Lượt chat.** `intake_graph` chạy đồng bộ trong luồng request của `api` (ADR-005). NFR-08 đòi phản hồi tăng dần để người dùng biết hệ thống đang làm việc. Nhưng lượt chat **không có token nào để stream**: `intake_agent` không sinh văn bản hiển thị, câu trả lời được lắp từ khuôn (ADR-007). Thứ cần đẩy là tiến độ và câu trả lời cuối.
2. **Trạng thái.** `request` và `document` đổi trạng thái do `queue_worker` hoặc do người khác bấm (F4, hàng đợi duyệt). Nhân viên dùng hệ thống vài lần mỗi năm (NFR-04), nên thứ họ cần là thấy đúng trạng thái khi mở màn hình, không phải một luồng sự kiện đầy đủ.

Mọi chiều client → server đã là REST. Ràng buộc Render: giới hạn thời gian request chưa xác minh (A-025), có thể nhiều instance, không giữ trạng thái trong RAM giữa hai request. Không có SSO; đăng nhập hai vai trò; cơ chế credential chưa có (A-048).

Bảng `notification` không có cột đơn điệu: `id` là uuid do ứng dụng sinh, chỉ có thêm `created_at`. Phase 4 đã đóng; không thêm cột.

## Options

**Vận chuyển:** A — WebSocket · B — SSE · C — chỉ polling từ client.

**Mang credential:** (i) — session cookie HttpOnly · (ii) — bearer token giữ trong JS, gửi bằng header qua `fetch` · (iii) — token trong query string.

**Ngữ nghĩa của luồng trạng thái:** (α) — sự kiện có id, nối lại bằng `Last-Event-ID` · (β) — chỉ mang tín hiệu "có thay đổi", client GET lại để lấy sự thật.

## Decision

**Chọn B + (i) + (β).**

- **Hai stream, tách riêng** (mục SSE của `05-api.md`):
  - *Stream lượt chat* — chính là response của `POST` lượt chat, đọc bằng `fetch`. Ngắn, sống đúng một lượt. Mang tiến độ và câu trả lời cuối. **Bản có thẩm quyền là dòng `chat_message`**; stream đứt giữa lượt thì client dựng lại lượt đó bằng GET.
  - *Stream tín hiệu* — một `GET` dài, đọc bằng `EventSource`. Chỉ mang "chủ đề X có thay đổi"; client GET lại danh sách để lấy sự thật. Không id sự kiện, không `Last-Event-ID`, không bảo đảm giao đúng một lần.
- **Phát hiện thay đổi bằng poll DB trong tiến trình `api`**, theo từng kết nối, **không theo timestamp**:
  - `NOTIFICATIONS` — số dòng `notification` của người nhận. Đúng vì `bo19_app` không có quyền `DELETE` trên bảng đó, nên số dòng chỉ tăng. `COUNT` theo người nhận đi bằng index đã có: `uq_notification_dedupe` có cột đầu là `recipient_employee_id`.
  - `MY_REQUESTS`, `REVIEW_QUEUE` — dấu vân tay của tập (`id`, `row_version`) trên index đã có. Một dòng vào tập, ra khỏi tập hay đổi phiên bản đều làm dấu vân tay đổi, kể cả khi hai việc xảy ra trong cùng một nhịp poll.
- **Server tự đóng stream tín hiệu** sau một thời lượng có chặn trên, thấp hơn giới hạn thời gian request của Render (A-025); client nối lại và GET lại. Vì stream không mang sự thật, nối lại không mất gì.
- **Credential:** cookie `HttpOnly`, `Secure`, `SameSite=Strict`, cộng header bắt buộc `X-BO19-CSRF` trên mọi lệnh không phải GET. Ba lý do, theo đúng thứ tự:
  1. **Credential nằm ngoài vùng JS đọc được.** Mã độc chạy trong trang không lấy trộm được nó.
  2. **Một cơ chế xác thực dùng chung** cho REST, stream lượt chat và stream tín hiệu.
  3. *(Lý do phụ)* `EventSource` tự nối lại khi mất kết nối — hành vi của nền tảng web, `[CẦN XÁC MINH]`, A-051. Không được tính là lý do chính: stream lượt chat đã đọc bằng `fetch`, nên bearer token cũng làm được.

## Consequences

**Tích cực**

- Không có hạ tầng WebSocket. `api` không giữ trạng thái giữa hai request; mọi instance như nhau.
- Tín hiệu mất hay trùng không làm sai gì — client luôn GET lại sự thật. Render cắt một kết nối dài chỉ tốn một lần nối lại.
- Không bảng mới, không cột mới, không index mới.

**Tiêu cực và cái phải chấp nhận**

- Mỗi kết nối tín hiệu poll DB theo chu kỳ (`TBD`, A-031). Tải tỷ lệ với số kết nối đang mở. Dấu vân tay tính trên toàn tập đang theo dõi, nên chi phí một nhịp tăng theo kích thước tập — với `REVIEW_QUEUE` là kích thước hàng đợi.
- Mỗi tín hiệu tốn thêm một round-trip GET.
- Độ trễ phát hiện bằng một chu kỳ poll.

**Ràng buộc cùng origin — ADR này thu hẹp một lựa chọn đang để ngỏ.** Cookie `SameSite=Strict` không được gửi kèm request khác site, nên `client` khác site với `api` thì không đăng nhập được. Cùng site mà khác origin thì request mang credential phải đi qua CORS, tức phải mở CORS cho `api`. ADR này chọn **cùng origin**: `client` được phục vụ dưới cùng origin với `api`. Ràng buộc này rơi vào mục Ánh xạ sang đơn vị triển khai trên Render của `02-architecture.md`, nơi `client` đang ghi "phục vụ tĩnh hoặc build riêng": từ ADR này, build riêng vẫn phải được phục vụ dưới cùng origin với `api`. `02-architecture.md` không sửa ở Phase 5; ràng buộc được ghi ở đây và ở `CHANGELOG.md` để Phase 6 không thiết kế ngược lại. Hai subdomain trên domain mặc định của Render có tính là cùng site hay không: A-049.

**Chống CSRF dựa trên hành vi nền tảng chưa có bản gốc trong `docs/reference/`:** cookie `SameSite=Strict` không đi kèm request khác site; header tuỳ biến trên request khác origin buộc trình duyệt hỏi trước (preflight), và lần hỏi đó thất bại khi `api` không cho phép origin kia. Cả hai ở A-051.

**Điều kiện đảo ngược**

- *Tín hiệu vận hành, đo ở `observability`:* tỷ trọng truy vấn do vòng poll tín hiệu gây ra trên tổng tải của `postgresql`, đặt cạnh số kết nối tín hiệu đang mở — cùng hình dạng với tín hiệu thứ ba của ADR-004. Khi tín hiệu phát ra: kéo dài chu kỳ poll, gom poll về một vòng cho mỗi instance, hoặc thêm LISTEN/NOTIFY như một tối ưu — **không** đổi ngữ nghĩa (β). Chỗ quan sát này **chưa có** trong bảng chỗ quan sát của Phase 11 ở `_PLAN.md` (Open Questions của `05-api.md`).
- *Tín hiệu nghiệp vụ, đo ở `ASSUMPTIONS.md`:* A-049 trả lời "không" và tổ chức không có domain riêng — `client` và `api` không thể cùng origin. Khi đó xét lại vế credential: bearer token trong JS qua `fetch` cho cả hai stream, chấp nhận mất lý do 1.

## Rejected alternatives

**A — WebSocket.** Chiều client → server đã là REST; một kênh hai chiều không có việc gì để làm. WebSocket cần một bước xác thực riêng lúc bắt tay và một giao thức riêng đi qua proxy; SSE là một response HTTP thường, đi qua cùng middleware xác thực và cùng log như mọi endpoint khác. Render có hỗ trợ WebSocket hay không **không** phải lý do loại — không ghi từ trí nhớ.

**C — Chỉ polling từ client.** Lượt chat chạy **bên trong** một request (ADR-005): muốn báo tiến độ mà không lưu trạng thái tiến độ xuống DB thì chỉ có cách stream chính response đó. Với trạng thái, polling từ client vẫn phải làm đúng phép phát hiện ở trên, chỉ khác là nhân số request lên theo số màn hình đang mở.

**(ii) — Bearer token trong JS, qua `fetch`.** Chạy được — stream lượt chat đã là `fetch`. Loại vì token nằm trong vùng JS đọc được, và vì mất vế tự nối lại của `EventSource` cho stream dài. Giữ làm phương án dự phòng ở điều kiện đảo ngược.

**(iii) — Token trong query string.** Loại vì query string đi vào log kỹ thuật — log truy cập, trace — tức một credential nằm dạng thật trong `observability`, đụng NFR-05.

**(α) — Sự kiện có id, nối lại bằng `Last-Event-ID` trên bảng `notification`.** Không có cột đơn điệu để làm id. Con trỏ theo `created_at` bỏ sót dòng commit muộn hơn một dòng có `created_at` lớn hơn nó. Thêm cột `bigserial` là sửa Phase 4 đã đóng — và (β) không cần cột đó.

**LISTEN/NOTIFY của PostgreSQL thay cho poll.** Không loại vì sai, mà vì thừa ở Sprint đầu: lúc kết nối và nối lại, client vẫn phải GET sự thật từ DB, nên đường poll phải tồn tại bất kể có NOTIFY hay không; NOTIFY chỉ là một tối ưu độ trễ đặt trên đường đó. Hành vi của nó trên PostgreSQL managed của Render `[CẦN XÁC MINH]`. Giữ ở điều kiện đảo ngược.
