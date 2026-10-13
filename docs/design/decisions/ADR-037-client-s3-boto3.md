# ADR-037 — Client S3 của `bo19.object_storage`: `boto3`, một adapter, mọi `PUT` ghi có điều kiện

**Trạng thái:** Accepted · **Duyệt:** PO, 2026-10-13 — kèm điều kiện ở mục Điều kiện duyệt · **Ngày:** 2026-10-13 · **Quyết định tại:** BUILD MODE, B8a, trước adapter `object_storage` · **Liên quan:** ADR-003 (interface S3-compatible), ADR-030 (khoá phiên bản), ADR-031 (SeaweedFS local, ghi có điều kiện), A-024, A-072, A-084 · **Nguồn:** `docs/reference/object-storage-local-s3.md`

---

## Context

`bo19.object_storage` là adapter duy nhất tới dịch vụ S3-compatible (ADR-003, ADR-031): **một** adapter cho mọi môi trường, và mọi `PUT` mang `If-None-Match: *` — bảo vệ nằm ở header adapter gửi, không ở sản phẩm (ADR-031, T8). Cần chọn client. Contract `object-storage` của `.importlinter` còn chỗ giữ `<sdk-s3>` chờ quyết định này.

Đã có sẵn: `boto3` 1.37.3 và `botocore` 1.37.3 nằm trong `requirements-linux.lock` (ADR-030), và là client của bộ phép thử ở `docs/reference/object-storage-local-s3.md` — T2 (ghi lại lên khoá đã có: `412 PreconditionFailed`), T6 (tám luồng cùng khoá: một thắng), T10 (đối soát trên bucket có versioning). Đã kiểm trên chính bản này (2026-10-13): `PutObject` có tham số `IfNoneMatch`; tài liệu của tham số ghi "Otherwise, Amazon S3 returns a `412 Precondition Failed` error".

Tool của `tool_layer` là đồng bộ (`psycopg` sync), nên không cần client async.

## Options

- **A — `boto3`** (đồng bộ).
- **B — `httpx` + tự ký SigV4.** `httpx` có sẵn trong lock (ADR-035).
- **C — `aioboto3` / `aiobotocore`.**
- **D — Client khác** (ví dụ SDK riêng của một nhà cung cấp).

## Decision

**Chọn A.** `boto3` 1.37.3 ở bản đã khoá — không thêm phụ thuộc.

- `addressing_style = path`, `retries.max_attempts = 1` (như bộ phép thử): retry là việc của tầng trên (giao thức ghi một lần và `jobs`), không chồng hai lớp retry; timeout kết nối và đọc theo WV-08 (30 s).
- `PUT` luôn gọi `put_object(…, IfNoneMatch="*")`. Adapter **không có đường ghi nào khác**; không có tham số tắt điều kiện.
- Credential, endpoint, bucket và vùng đọc từ biến môi trường (mục Biến môi trường của `11-ops.md`); không log, không `repr`.
- **Luật import:** `boto3`, `botocore` chỉ được import trong `bo19.object_storage`. Contract `object-storage` của `.importlinter` thêm hai module đó vào `forbidden_modules` cho mọi nguồn khác.

## Điều kiện duyệt — PO, 2026-10-13

1. **CI chứng minh** SeaweedFS 4.47 trả `412` thật khi `PutObject` kèm `If-None-Match: *` lên khoá đã có — một test chạy ở mỗi lần CI trên đúng adapter, kèm khẳng định byte cũ còn nguyên.
2. **Nếu SeaweedFS bỏ qua header** (trả 200 và đè), người triển khai **dừng và báo PO**: giao thức ghi một lần phải thiết kế lại — không tự sửa vòng qua.
3. Script kiểm contract dùng chung cho nhà cung cấp thật (ADR-031) **hoãn tới trước cổng 2.5**, nhưng khi viết **phải có phép thử 412** của điều kiện 1.

## Consequences

**Tích cực**

- Không thêm phụ thuộc, không đổi lock; bộ phép thử của ADR-031 chạy trên cùng client.
- Ký chữ ký và xử lý lỗi S3 là mã đã được dùng rộng; không có mã mật mã tự viết trong repo.

**Tiêu cực và cái phải chấp nhận**

- `boto3` kéo theo `botocore` và `s3transfer` — phụ thuộc lớn, nằm sẵn trong lock và image. Chỉ dùng `put_object`, `get_object`, `head_object`, `delete_object`, `list_objects_v2`; không dùng `s3transfer` (không upload nhiều phần — bản render là một vài trang).
- Hành vi của header `If-None-Match` do **phía server** quyết định: client gửi đúng chưa đủ. Vì vậy điều kiện duyệt 1 là test trên server thật, và nhà cung cấp thật (A-024) phải qua cùng phép thử trước cổng 2.5.
- `boto3` đồng bộ chặn thread: lời gọi nằm trong job của `worker` (một job một lúc) hoặc trong `stored_file_fetch` của `api` chạy ở thread của FastAPI — không chạy trên event loop.

**Điều kiện đảo ngược**

- Nhà cung cấp của A-024 không tương thích với `boto3` mặc định (ví dụ cần chữ ký hay endpoint riêng) → xét cấu hình client trước, thay client sau.
- Bản `boto3` được khoá đổi (ADR-030) → chạy lại bộ phép thử trước khi dùng — như ADR-031 đòi với SeaweedFS.

## Rejected alternatives

**B — `httpx` + tự ký SigV4.** `httpx` đã có, nhưng tự cài chữ ký AWS là tự viết mã mật mã và quy tắc chuẩn hoá yêu cầu của một giao thức không có trong `docs/reference/`; một lỗi nhỏ thành lỗi xác thực khó đoán trên nhà cung cấp lạ. Tiết kiệm không đáng kể vì `boto3` đã nằm trong lock.

**C — `aioboto3`/`aiobotocore`.** Thêm phụ thuộc ngoài lock; toàn bộ tool chạy đồng bộ nên không có chỗ dùng event loop.

**D — SDK riêng của nhà cung cấp.** Giành trước A-024 (chưa chọn nhà cung cấp) và phá "một adapter cho mọi môi trường" (A-072). Không kiểm chúng; không liệt kê tên.
