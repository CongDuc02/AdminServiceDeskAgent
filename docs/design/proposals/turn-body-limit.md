# Đề xuất sửa contract — trần body của `POST /chat-sessions/{chat_session_id}/turns` (nợ B6b, cùng khuôn O1-10)

**Trạng thái:** ⏳ **chờ PO duyệt diff** — chưa sửa `openapi.yaml`, `05-api.md`, chưa viết code. · **Ngày:** 2026-10-12 · **Người đề xuất:** người triển khai · **Nợ từ:** B6b (báo cáo B6b, mục "Chưa làm / nói thẳng") · **Khuôn:** `proposals/login-body-limits.md` (O1-10)

## 1. Vấn đề

`TurnBody.text` có `max_length` 2000 (WV-15, `CHAT_MESSAGE_MAX_CHARS`) ở pydantic, nhưng uvicorn và FastAPI đọc và phân tích **toàn bộ** body trước khi pydantic từ chối — một client đã đăng nhập gửi body hàng chục megabyte vẫn tốn bộ nhớ và CPU. Khác `POST /auth/session`, endpoint này cần phiên, nhưng phiên là của mọi nhân viên: bề mặt tấn công là tài khoản bất kỳ. `openapi.yaml` hiện cũng **không** có `maxLength` trên `TurnBody.text` ("Độ dài tối đa TBD (A-031)") và **không** có phản hồi `413` cho endpoint này.

## 2. Đề xuất

1. Body của `POST /chat-sessions/{chat_session_id}/turns` vượt **`TURN_BODY_MAX_BYTES`** thì `PAYLOAD_TOO_LARGE` 413, kiểm bằng đếm byte thực nhận **trước** khi phân tích JSON — cùng middleware `BodyLimitMiddleware` của O1-10 (không tin `Content-Length`; `Content-Length` lớn quá trần chỉ giúp từ chối sớm). Middleware chạy trước xác thực, nên 413 đến trước 401/403/404 — như đăng nhập; không đọc DB, không chạm khoá phiên.
2. **Mức trần theo `max_length` của `TurnBody`, không phải con số rời:** `TURN_BODY_MAX_BYTES = CHAT_MESSAGE_MAX_CHARS × 12 + 1024 = 25 024`. Lý do: body hợp lệ lớn nhất là 2000 ký tự mà client mã hoá **mọi** ký tự ngoài BMP thành cặp `\uXXXX\uXXXX` (12 byte mỗi ký tự, trường hợp xấu nhất của JSON), cộng khung `{"text":""}` và khoảng trắng; `1024` là dư cho khung và định dạng. Đổi WV-15 thì trần đi theo. (UTF-8 thô tối đa 4 byte mỗi ký tự = 8000, nằm trong trần; tin hợp lệ dù mã hoá kiểu nào cũng qua.)
3. `TurnBody.text` của `openapi.yaml`: thay "Độ dài tối đa TBD (A-031)" bằng `maxLength: 2000` — khớp WV-15 và pydantic hiện có (giá trị đã chạy từ B6b; chỉ tài liệu còn ghi TBD). Đây là sửa cho tài liệu khớp code, không đổi hành vi.
4. `PAYLOAD_TOO_LARGE` mở rộng mô tả để gồm body của `POST …/turns`.

Con số 12 là hệ quả của cách mã hoá JSON, không phải ước đoán; `1024` là đề xuất của người triển khai (nhãn "chưa hiệu chỉnh", như 4096 của O1-10). Không số nào lấy từ nguồn ngoài.

## 3. Diff đề xuất

```diff
--- a/docs/design/contracts/openapi.yaml
+++ b/docs/design/contracts/openapi.yaml
@@ /chat-sessions/{chat_session_id}/turns → post → responses @@
         "409": { $ref: "#/components/responses/Conflict" }
+        "413": { $ref: "#/components/responses/PayloadTooLarge" }
         "422": { $ref: "#/components/responses/Unprocessable" }
@@ components/responses/PayloadTooLarge @@
-      description: PAYLOAD_TOO_LARGE — file vượt trần (trần TBD, A-031); và body của POST /auth/session vượt 4096 byte
+      description: PAYLOAD_TOO_LARGE — file vượt trần (trần TBD, A-031); body của POST /auth/session vượt 4096 byte; body của POST /chat-sessions/{chat_session_id}/turns vượt 25 024 byte
@@ components/schemas/TurnBody @@
         text:
-          description: Độ dài tối đa TBD (A-031)
           type: string
           minLength: 1
+          maxLength: 2000
```

```diff
--- a/docs/design/05-api.md
+++ b/docs/design/05-api.md
@@ Danh mục error_code @@
-| `PAYLOAD_TOO_LARGE` | 413 | File vượt trần — trần `TBD` (A-031); hoặc body của `POST /auth/session` vượt 4096 byte | Chọn file nhỏ hơn; ở đăng nhập: gửi lại đúng mã và mật khẩu | — |
+| `PAYLOAD_TOO_LARGE` | 413 | File vượt trần — trần `TBD` (A-031); hoặc body của `POST /auth/session` vượt 4096 byte; hoặc body của `POST /chat-sessions/{id}/turns` vượt 25 024 byte | Chọn file nhỏ hơn; ở đăng nhập: gửi lại đúng mã và mật khẩu; ở chat: gửi tin ngắn hơn (tối đa 2000 ký tự) | — |
```

`06-structure.md`, mục "Triển khai ở B6b": thêm một gạch đầu dòng cùng khuôn gạch O1-10 — "`POST …/turns` (nợ B6b): trần `TURN_BODY_MAX_BYTES`, cùng `BodyLimitMiddleware`".

## 4. Nếu duyệt, việc làm theo thứ tự

1. Sửa `openapi.yaml`, `05-api.md`, `06-structure.md` như trên, kèm `CHANGELOG.md`.
2. `config/working_values.py`: `TURN_BODY_MAX_BYTES = CHAT_MESSAGE_MAX_CHARS * 12 + 1024`.
3. `BodyLimitMiddleware`: khoá giới hạn nhận **mẫu đường dẫn** (đường có `{chat_session_id}`); đường chính xác của đăng nhập giữ nguyên. Chỉ `POST`, chỉ đúng mẫu `/api/v1/chat-sessions/<uuid>/turns`.
4. Test: `Content-Length` lớn (không đọc byte nào); chunked vượt trần (dừng ngay); `Content-Length` nói dối (nhỏ hơn thực); đúng bằng trần thì qua; tin 2000 ký tự ngoài BMP mã hoá `\uXXXX` toàn bộ **vẫn qua** (< trần); 413 mang `trace_id`; 413 không tạo `chat_message`, không chạm DB; đối chiếu `openapi.yaml` (`413`, `maxLength`) và `05-api.md` với `working_values` như `test_login_limits.py`; các endpoint khác (`/messages`, `/chat-sessions`) **không** bị giới hạn bởi mẫu này.
5. Đột biến: bỏ kiểm byte thực nhận (chỉ tin `Content-Length`), mẫu đường khớp quá rộng/quá hẹp, trần lệch một byte, `maxLength` openapi lệch WV-15 — đều phải đỏ.

## Open Questions

- Công thức `× 12 + 1024` (= 25 024) — PO giữ hay muốn một con số tròn khác (ví dụ 32 768)? Công thức có lợi là đi theo WV-15.
- `maxLength: 2000` trong `openapi.yaml` có cần chờ A-031 chốt không? Nếu PO coi 2000 vẫn là "giữ theo O1-1" thì thêm ngay như trên.
