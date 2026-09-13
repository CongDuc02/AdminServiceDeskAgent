# ADR-018 — Frontend: Vite, React Router, TanStack Query làm bộ đệm trạng thái server; không store toàn cục

**Trạng thái:** Accepted · **Ngày:** 2026-09-13 · **Quyết định tại:** Phase 6 — Project Structure · **Liên quan:** ADR-013, NFR-04, NFR-05 của `01-prd.md`, mục Nguyên tắc chung, mục SSE và mục Mã lỗi của `05-api.md`

---

## Context

- `client` được `api` phục vụ tĩnh, cùng origin (ADR-013, B1). Đường dẫn SPA không được chồng tiền tố `/api`.
- Ngữ nghĩa của stream tín hiệu là (β): tín hiệu chỉ nói "chủ đề X có thể đã đổi", client GET lại để lấy sự thật (ADR-013).
- Stream lượt chat là response của một `POST`, đọc bằng `fetch`, không bằng `EventSource`. Bản có thẩm quyền là `chat_message`.
- Lớp chống CSRF thứ hai là header `X-BO19-CSRF` trên mọi lệnh không phải GET.
- `client` không giữ bản sao thứ hai của tên trạng thái: nhãn tiếng Việt đến từ server (`status_label`).
- Contract máy đọc được là `contracts/openapi.yaml`.

## Options

**Trạng thái:** A — TanStack Query giữ trạng thái server, còn lại là state cục bộ của component · B — Redux Toolkit, cùng lớp truy vấn của nó · C — một store nhẹ cộng `fetch` viết tay.

**Build và render:** Vite, xuất file tĩnh · Next.js, render phía server.

**Công cụ kiểm ranh giới import:** ESLint với luật lõi · dependency-cruiser.

## Decision

**Chọn A, Vite, và ESLint.**

### Trạng thái — ba chủ đề, ba khoá gốc, một luật invalidate

| Chủ đề tín hiệu | Khoá gốc | Query nằm dưới khoá gốc |
|---|---|---|
| `NOTIFICATIONS` | `['notifications']` | Hộp thông báo |
| `MY_REQUESTS` | `['my-requests']` | Danh sách `GET /requests?scope=OWN`; chi tiết `GET /requests/{id}` của yêu cầu do mình tạo |
| `REVIEW_QUEUE` | `['review-queue']` | `GET /review-queue` theo từng `status`; `GET /issue-queue`; `GET /documents/{id}` đang mở |

- **Luật invalidate — đúng một:** gặp sự kiện `signal` thì invalidate **theo tiền tố** khoá gốc của từng chủ đề trong `topics`. Sự kiện đầu tiên sau mỗi lần kết nối mang mọi chủ đề mà người đó theo dõi, nên nối lại là làm mới toàn bộ — không cần con trỏ.
- Mỗi query **khai nó thuộc chủ đề nào** bằng cách nằm dưới khoá gốc đó. Query không thuộc chủ đề nào — template, nhật ký, cấu hình — được lấy lại khi màn hình mở hoặc cửa sổ lấy lại tiêu điểm, không theo tín hiệu.
- Không store toàn cục. Trạng thái của form, bộ lọc và bước xác nhận là state cục bộ.

### Stream lượt chat — ngoài TanStack Query

- Nằm ở module stream lượt của tính năng chat (mục Cây frontend của `06-structure.md`). Nó đọc response của `POST` qua lối `fetch` duy nhất và phân tích sự kiện SSE.
- **Luật dựng lại lượt khi stream đứt** — đứt trước `turn.reply` hoặc `turn.error`:
  1. GET `/chat-sessions/{id}/messages`;
  2. tin nhắn agent của lượt đã có thì hiển thị nó, xong;
  3. chưa có thì gửi lại **cùng** `Idempotency-Key`. Server trả `TURN_NOT_FINISHED`: nếu `turn_abandoned = false` thì chờ theo `Retry-After` rồi quay lại bước 1; nếu `true` thì hiển thị đúng `message` của server — tin nhắn đã được lưu, cần gửi lại nội dung.
- Kết thúc lượt thì cập nhật query tin nhắn của phiên, và invalidate `['my-requests']`, vì lượt có thể vừa mở hay đổi một `request`.

### Một lối `fetch` duy nhất

- **Chỉ một module được tham chiếu `fetch`**, và đó là chỗ duy nhất gắn `X-BO19-CSRF` cho mọi lệnh không phải GET, đặt `credentials: 'same-origin'` và phân tích `ErrorEnvelope`. **Chỉ một module khác được tham chiếu `EventSource`** — nguồn của stream tín hiệu. Hai luật này là luật ESLint, không phải quy ước: tham chiếu `fetch` hay `EventSource` ở bất kỳ file nào khác thì CI đỏ.
- Rẽ nhánh lỗi theo `error_code`, không theo `message`; hiển thị `message` của server nguyên văn (NFR-04).

### Định tuyến và phục vụ tĩnh

- Đường dẫn SPA không bắt đầu bằng `/api`.
- Phía `api`:
  - đường dẫn lạ **thuộc** `/api` trả `ErrorEnvelope` JSON với `NOT_FOUND`;
  - file tĩnh lạ dưới thư mục asset trả 404, không trả `index.html`;
  - mọi GET lạ còn lại trả `index.html`.

  Nuốt 404 của API thành một trang HTML là lỗi rất khó truy: client nhận mã 200 kèm HTML ở chỗ chờ JSON.

### Type sinh từ `openapi.yaml`

- Type TypeScript được sinh từ `docs/design/contracts/openapi.yaml` bằng `openapi-typescript`. **File sinh ra được commit.** CI sinh lại và **đỏ nếu có khác biệt**. Commit để thay đổi contract hiện ra trong diff mà người review đọc; kiểm lệch để không ai sửa tay file sinh.

## Consequences

**Tích cực**

- Ngữ nghĩa (β) của ADR-013 ánh xạ thẳng lên cơ chế invalidate. Tín hiệu mất hay trùng không làm sai gì.
- Lớp chống CSRF không phụ thuộc kỷ luật của người viết component.
- Không có bản sao trạng thái server nào để lệch với server.

**Tiêu cực và cái phải chấp nhận**

- Mỗi tín hiệu tốn thêm một vòng GET — đã chấp nhận ở ADR-013.
- Stream lượt chat là một đường dữ liệu thứ hai, viết tay, phải test riêng.
- Tên tuỳ chọn của hai luật ESLint và cú pháp cấu hình `[CẦN XÁC MINH]` theo tài liệu của phiên bản ESLint được chọn; contract ở mục Luật import của `06-structure.md` là hình dạng, không phải file cấu hình.

**Điều kiện đảo ngược** — tín hiệu kiến trúc: xuất hiện trạng thái client **dùng chung giữa nhiều màn hình mà không phải trạng thái server** — ví dụ một bản nháp nhiều bước sống qua điều hướng. Khi đó thêm một store nhỏ cho đúng phần đó; không chuyển trạng thái server sang store.

## Rejected alternatives

**B — Redux Toolkit.** Loại vì trạng thái của ứng dụng này gần như toàn bộ là trạng thái server, và server luôn là sự thật. Một store toàn cục mời gọi giữ bản sao của trạng thái `request` và `document` — đúng thứ ADR-013 và mục Nguyên tắc chung của `05-api.md` tránh.

**C — Store nhẹ cộng `fetch` viết tay.** Loại vì phải tự viết lại bộ đệm, khử trùng lặp request và invalidate theo tiền tố — thứ A có sẵn — và vì `fetch` rải trong mã tính năng chính là thứ luật "một lối `fetch`" cấm.

**Next.js, render phía server.** Loại vì cần một tiến trình Node phục vụ trang, tức một origin khác hoặc một proxy trước `api` — trái quyết định B1 của ADR-013 là `api` phục vụ tĩnh.

**dependency-cruiser.** Kiểm tốt đồ thị import, nhưng `fetch` và `EventSource` là **biến toàn cục**, không phải import, nên luật quan trọng nhất ở đây nằm ngoài tầm của nó. Dùng ESLint cho cả hai loại luật là một công cụ thay vì hai.
