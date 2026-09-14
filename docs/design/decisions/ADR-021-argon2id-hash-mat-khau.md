# ADR-021 — `argon2id` cho hash mật khẩu `employee_credential`

**Trạng thái:** Accepted · **Ngày:** 2026-09-14 · **Quyết định tại:** Phase 9 — Security & Guardrails · **Liên quan:** A-048, mục AuthN của `09-security.md`

---

## Context

`employee_credential.password_hash` (A-048) cần một hàm hash một chiều cho mật khẩu. Đây có điều kiện đảo ngược thật — không phải chi tiết cấu hình: tham số hàm càng "tốn tài nguyên" thì chống dò mật khẩu ngoại tuyến càng tốt nếu `password_hash` bị lộ, nhưng cùng tham số đó tốn đúng bằng đó tài nguyên ở **mỗi lần đăng nhập hợp lệ**, trên instance Render đang chạy `api`. Chọn sai họ hàm, hoặc chọn tham số mà không biết đánh đổi, khoá luôn khả năng điều chỉnh sau này mà không phá mọi hash đã có (đổi họ hàm bắt buộc đổi định dạng `hash_algorithm` và không xác minh lại được hash cũ theo tham số mới).

Không trích số liệu benchmark hay khuyến nghị của bất kỳ tổ chức nào từ trí nhớ (luật trích dẫn của `CLAUDE.md`) — quyết định dưới đây dựa trên **tính chất hàm đã công bố công khai qua tên thuật toán**, không dựa trên một con số hay một khuyến nghị chưa có bản gốc trong `docs/reference/`.

## Options

- **A — `argon2id`.** Hàm memory-hard: tham số cấu hình gồm chi phí bộ nhớ, số vòng lặp, độ song song. Biến thể `id` trộn đường tấn công side-channel (`i`) và đường tấn công GPU/ASIC thuần (`d`).
- **B — `bcrypt`.** Hàm dựa trên Blowfish, chi phí cấu hình bằng một tham số "work factor" (số vòng), **không** có tham số bộ nhớ độc lập — chi phí bộ nhớ của nó cố định ở mức nhỏ, không tăng theo work factor.
- **C — `PBKDF2`.** Hàm lặp dựa trên HMAC, chi phí cấu hình bằng số vòng lặp, không có tham số bộ nhớ.
- **D — `scrypt`.** Hàm memory-hard, có tham số bộ nhớ (`N`) như `argon2`, thiết kế trước `argon2`.

## Decision

**Chọn A — `argon2id`.**

Lý do bằng tính chất hàm, không bằng số liệu: A và D là hai họ duy nhất có tham số bộ nhớ **độc lập** với số vòng lặp — một cuộc dò mật khẩu ngoại tuyến chạy song song (GPU/ASIC) bị giới hạn bởi tổng RAM khả dụng, không chỉ bởi tổng phép tính, nên hai họ này đắt hơn B và C theo đúng chiều mà kẻ tấn công có lợi thế nhất (song song hoá phần cứng chuyên dụng). Chọn A thay D vì biến thể `id` của `argon2` là biến thể duy nhất trong bốn phương án trộn được cả hai mô hình đe doạ (kênh bên và tấn công thuần phần cứng) trong một hàm; `scrypt` chỉ có một biến thể.

**Tham số cụ thể — không quyết ở đây, TBD (A-048).** Cột `employee_credential.hash_algorithm` lưu định danh thuật toán cùng dòng hash, để một lần đổi tham số — hoặc đổi hẳn sang một họ khác — không đòi hồi tố toàn bộ bảng trong một bước; hash cũ vẫn xác minh được theo đúng tham số đã lưu, hash mới dùng tham số mới.

## Consequences

**Tích cực**

- Chống dò mật khẩu ngoại tuyến tốt hơn B/C nếu `password_hash` bị lộ, theo đúng chiều tấn công có lợi thế nhất (song song hoá phần cứng).
- `hash_algorithm` tách khỏi `password_hash` nên đổi tham số không phải một migration phá huỷ.

**Tiêu cực và cái phải chấp nhận**

- **RAM của instance Render là chi phí thật, không phải chi tiết cấu hình.** Tham số bộ nhớ càng cao thì mỗi lần đăng nhập hợp lệ tốn càng nhiều RAM trên instance chạy `api`; nhiều lượt đăng nhập đồng thời trên một instance nhỏ có thể cạnh tranh RAM với phần còn lại của tiến trình. Tham số cuối cùng phải chọn có đối chiếu với hạng instance đã thuê (A-002, A-031), không chọn theo một con số khuyến nghị chung rồi coi là an toàn.
- Thư viện `argon2` cho Python cần biên dịch phần mở rộng gốc (native extension) ở hầu hết bản phân phối — ràng buộc build, không phải ràng buộc thiết kế; ảnh hưởng cụ thể tới thời gian build/cold start `[CẦN XÁC MINH]`.

**Điều kiện đảo ngược** — tín hiệu vận hành: thời gian hash một lần đăng nhập (p95/p99) đặt cạnh RAM còn trống của instance, đo sau khi có môi trường Render đầu tiên. Thời gian hash vượt ngưỡng chấp nhận được cho một request đồng bộ, hoặc RAM cạnh tranh với tải nghiệp vụ, thì hạ tham số bộ nhớ trước khi đổi họ hàm — đổi tham số không đòi ADR mới, đổi họ hàm thì có.

## Rejected alternatives

**B — `bcrypt`.** Không có tham số bộ nhớ độc lập — work factor chỉ tăng số vòng lặp, không tăng RAM cần thiết cho một lần tính. Loại vì đúng chiều tấn công có lợi thế nhất (song song hoá phần cứng) không bị cản.

**C — `PBKDF2`.** Cùng lý do B, và không có tham số bộ nhớ dưới bất kỳ hình thức nào.

**D — `scrypt`.** Không loại vì kém A — cùng họ memory-hard, cùng đáp ứng tiêu chí trên. Loại vì chỉ có một biến thể, không tách được mô hình đe doạ kênh bên và mô hình đe doạ phần cứng thuần như `argon2id` làm được. Là phương án dự phòng hợp lý nếu thư viện `argon2` gặp trở ngại build thật sự trên Render.
