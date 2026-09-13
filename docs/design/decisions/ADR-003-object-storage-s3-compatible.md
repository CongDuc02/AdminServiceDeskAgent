# ADR-003 — `object_storage` là dịch vụ S3-compatible ngoài Render, bất biến đảm bảo ở tầng ứng dụng

**Trạng thái:** Accepted · **Ngày:** 2026-09-12 · **Quyết định tại:** Phase 2 — System Architecture · **Liên quan:** mục Tech stack của `CLAUDE.md`, AC F3 của `01-prd.md`, A-021, A-024

---

## Context

`CLAUDE.md` yêu cầu ràng buộc Render — trong đó "filesystem không bền vững" — phải được nêu trong thiết kế. `object_storage` không nằm trong danh sách công nghệ bắt buộc của `CLAUDE.md`, nên cần một ADR có phương án bị loại.

Ràng buộc sản phẩm đã chốt ở AC của F3 (`01-prd.md`), không thương lượng: **bản render gắn với `document` ở `SEALED` và `ISSUED` không bao giờ được mất hay bị đè.** Đây không phải một mong muốn vận hành mà là một yêu cầu lên chính interface lưu trữ — bất kỳ lựa chọn công nghệ nào cũng phải thoả được nó, không phụ thuộc vào việc chọn nhà cung cấp nào.

## Options

**A — Render persistent disk.**

**B — Dịch vụ S3-compatible bên ngoài, bất biến dựa vào tính năng riêng của nhà cung cấp** (Object Lock / Versioning).

**C — Dịch vụ S3-compatible bên ngoài, bất biến đảm bảo ở tầng ứng dụng** (khoá đối tượng content-addressed, `tool_layer` không bao giờ phát lệnh ghi đè lên khoá đã tồn tại cho bản render ở `SEALED`/`ISSUED`).

## Decision

**Chọn C.**

- `object_storage` là một dịch vụ S3-compatible bên ngoài Render. **Nhà cung cấp cụ thể và chi phí: `TBD`** (A-024) — không chốt ở phase này, không phải vì thiếu quyết đoán mà vì chọn vendor là quyết định vận hành/chi phí, không phải quyết định kiến trúc, và `CLAUDE.md` cấm bịa số liệu giá chưa xác minh.
- Ràng buộc lên **interface**, chốt được ngay bất kể vendor: khoá đối tượng (object key) của bản render gắn với `document` ở `SEALED` hoặc `ISSUED` bắt buộc là **content-addressed** — gồm `document_id`, phiên bản/hash nội dung. `tool_layer` không bao giờ phát lệnh ghi (PUT/overwrite) lên một khoá đã tồn tại thuộc hai trạng thái này; mọi lần render tạo ra khoá mới.
- Checksum của mỗi bản lưu ở PostgreSQL (bảng liên quan tới `document`, chi tiết ở Phase 4) để đối chiếu khi đọc — phát hiện được nếu object storage trả về nội dung sai khoá do lỗi phía nhà cung cấp.

## Consequences

**Tích cực**

- Bất biến của bản render ở `SEALED`/`ISSUED` không phụ thuộc vào việc nhà cung cấp có hỗ trợ Object Lock/Versioning hay không — portable giữa các nhà cung cấp S3-compatible khác nhau. **Sửa ở Phase 4:** câu này đúng với mọi ca **trừ một** — một lệnh ghi đã gửi mà treo lâu hơn lease vẫn đè được byte của object đã commit (mục Lưu trữ file và bất biến bản render của `04-data.md`). Tầng ứng dụng thu hẹp được ca đó nhưng không đóng được; vì vậy một cơ chế ở tầng lưu trữ thành **yêu cầu bắt buộc khi chọn nhà cung cấp** (A-024).
- Chọn vendor sau này (khi có số liệu chi phí thật, A-024) không đòi hỏi thiết kế lại cơ chế bất biến.
- Tương thích ràng buộc Render "filesystem không bền vững" — file không bao giờ chỉ tồn tại trên đĩa cục bộ của một instance.

**Tiêu cực và cái phải chấp nhận**

- Không tận dụng được tính năng Object Lock của nhà cung cấp như một lớp phòng thủ kép — nếu `tool_layer` có lỗi logic phát lệnh ghi đè, không có lớp chặn thứ hai ở phía hạ tầng. Đây là đánh đổi có ý thức để giữ tính portable.
- Thêm một dịch vụ bên ngoài Render phải quản lý credential và giám sát riêng.

**Điều kiện đảo ngược quyết định này (không phải hình dạng tín hiệu tải, mà là bối cảnh chọn vendor):** nếu vendor cuối cùng được chọn (A-024) hỗ trợ Object Lock/Versioning ổn định, nên **bật thêm nó như lớp phòng thủ thứ hai**, không bao giờ thay thế cơ chế app-level — vì cơ chế app-level là thứ duy nhất không phụ thuộc vendor. **Sửa ở Phase 4:** "nên" thành "phải" — vendor được chọn **bắt buộc** có ghi có điều kiện, khoá đối tượng hoặc versioning, và cơ chế đó **phải** được bật. Cơ chế app-level vẫn giữ nguyên. Không vendor nào đáp ứng thì rủi ro ghi đè thành rủi ro chấp nhận có người ký (A-024).

## Rejected alternatives

**Option A — Render persistent disk.** Bị loại vì mâu thuẫn trực tiếp với ràng buộc nền tảng mà chính `CLAUDE.md` yêu cầu phải nêu: disk không đảm bảo bền vững và không chia sẻ được giữa nhiều instance của cùng một Web Service hay giữa Web Service và Worker. Chọn phương án này là thiết kế ngược lại đúng ràng buộc đã biết trước.

**Option B — Bất biến dựa vào tính năng của nhà cung cấp.** Bị loại vì lý do khác Option A: không phải sai ràng buộc nền tảng, mà là **đặt cược vào một thứ chưa biết** — vendor cụ thể còn `TBD` (A-024), và các dịch vụ S3-compatible không đồng nhất về việc có hỗ trợ Object Lock/Versioning hay không, hỗ trợ tới mức nào. Chốt kiến trúc phụ thuộc một tính năng chưa xác minh là lặp lại đúng lỗi mà `CLAUDE.md` cấm ở các mục khác (bịa số liệu/tính năng chưa xác minh), chỉ khác là ở tầng hạ tầng thay vì tầng pháp lý.
