# Đề xuất sửa contract — giới hạn độ dài và kích thước body của `POST /auth/session`

**Trạng thái:** ✅ **PO duyệt 2026-10-09** (`maxLength` 64/128 đã vào `openapi.yaml` do PO; B5 thêm `413` và làm code). · **Ngày:** 2026-10-05 · **Người đề xuất:** người triển khai · **Hạn làm:** trước cổng 2.8 (PO, 2026-10-05) · **Nợ từ:** B3 (`CHANGELOG.md`, mục B3 xong)

## 1. Vấn đề

`LoginBody` không có `maxLength`, và không có trần cho kích thước body. Uvicorn phân tích toàn bộ body **trước** khi request tới rate limit, nên một client chưa xác thực gửi body rất lớn tốn bộ nhớ và CPU mà bộ đếm không chặn được (lỗi 403 và 422 cũng không tăng bộ đếm — chúng không chạm DB). Đây là bề mặt của người chưa đăng nhập — endpoint công khai duy nhất (mục Rate limit của `05-api.md`).

## 2. Đề xuất

1. `LoginBody.employee_code`: `maxLength: 64`. `LoginBody.password`: `maxLength: 128`. Vượt thì `VALIDATION_FAILED` 422 với `fields[].code = TOO_LONG` — mã con đã có trong danh mục.
2. Body của `POST /auth/session` vượt **4096 byte** thì `PAYLOAD_TOO_LARGE` 413, kiểm **trước** khi phân tích JSON (đọc `Content-Length` và đếm byte khi đọc luồng, vì header có thể thiếu hoặc nói dối). Không tăng bộ đếm rate limit — như 403 và 422.
3. `PAYLOAD_TOO_LARGE` hiện chỉ nói về file; mở rộng mô tả để gồm body đăng nhập.

## 3. Các con số là đề xuất, **chưa có căn cứ nguồn**

64, 128 và 4096 là giá trị tôi chọn: mật khẩu seed của `tools/seed-dev/` dài 24 ký tự; mã nhân viên do CSV quyết định (D-002) và chưa có định dạng chốt; 4096 byte gấp nhiều lần body hợp lệ lớn nhất có thể (64 + 128 ký tự cộng khung JSON). Tài liệu OWASP đã có ở `docs/reference/owasp-password-storage-argon2id.md` **không** nêu độ dài mật khẩu tối đa, nên tôi không trích số nào từ nguồn; nếu PO muốn căn cứ nguồn thì cần tải thêm tài liệu về độ dài mật khẩu. Nếu tổ chức đã có chính sách mật khẩu hay định dạng mã nhân viên, thay số ở đây — đổi số không đổi cấu trúc đề xuất. Ghi `TBD` kèm mục ở `ASSUMPTIONS.md` nếu PO coi là giá trị làm việc "chưa hiệu chỉnh".

## 4. Diff đề xuất

```diff
--- a/docs/design/contracts/openapi.yaml
+++ b/docs/design/contracts/openapi.yaml
@@ -70,4 +70,5 @@
         '401': { $ref: '#/components/responses/Unauthenticated' }
         '403': { $ref: '#/components/responses/Forbidden' }
+        '413': { $ref: '#/components/responses/PayloadTooLarge' }
         '422': { $ref: '#/components/responses/Unprocessable' }
         '429': { $ref: '#/components/responses/RateLimited' }
@@ -1714,5 +1715,5 @@
           schema: { $ref: '#/components/schemas/ErrorEnvelope' }
     PayloadTooLarge:
-      description: PAYLOAD_TOO_LARGE — trần TBD (A-031)
+      description: PAYLOAD_TOO_LARGE — file vượt trần (trần TBD, A-031); và body của POST /auth/session vượt 4096 byte
       content:
         application/json:
@@ -2050,6 +2051,6 @@
       required: [employee_code, password]
       properties:
-        employee_code: { type: string, minLength: 1 }
-        password: { type: string, minLength: 1, format: password, writeOnly: true }
+        employee_code: { type: string, minLength: 1, maxLength: 64 }
+        password: { type: string, minLength: 1, maxLength: 128, format: password, writeOnly: true }
 
     # ------------------------------------------------------------------ chat
```

```diff
--- a/docs/design/05-api.md
+++ b/docs/design/05-api.md
@@ Danh mục error_code @@
-| `PAYLOAD_TOO_LARGE` | 413 | File vượt trần — trần `TBD` (A-031) | Chọn file nhỏ hơn | — |
+| `PAYLOAD_TOO_LARGE` | 413 | File vượt trần — trần `TBD` (A-031); hoặc body của `POST /auth/session` vượt 4096 byte | Chọn file nhỏ hơn; ở đăng nhập: gửi lại đúng mã và mật khẩu | — |
```

## 5. Nếu duyệt, việc làm theo thứ tự

1. Sửa `openapi.yaml` và `05-api.md` như trên, kèm `CHANGELOG.md`.
2. `api/schemas/auth.py`: `max_length` cho hai trường; test `TOO_LONG` trong `test_auth_endpoints.py`.
3. Middleware ASGI giới hạn body cho đường `POST /api/v1/auth/session`: từ chối bằng `PAYLOAD_TOO_LARGE` trước khi phân tích; test với `Content-Length` lớn, thiếu `Content-Length` (chunked) và `Content-Length` nói dối; test không tăng bộ đếm.
4. Thêm `PAYLOAD_TOO_LARGE` vào `CATALOG` của `api/errors.py` (test đối chiếu với bảng ở `05-api.md` đã có).

## Open Questions

- Số 64, 128, 4096 — PO chọn hay giữ đề xuất? Có chính sách mật khẩu hay định dạng mã nhân viên nào của tổ chức không?
