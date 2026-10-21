# Cloudflare R2 — dạng endpoint, giá trị `region` cho SigV4, quyền của token

- **Nguồn — lấy bằng `curl`, ngày 2026-10-21.** Bản HTML gốc không vào repo (lớn; bản dựng bằng JavaScript); đây là các dòng **nguyên văn** trích từ bản chữ (`<url>index.md` của chính trang, do Cloudflare phát hành) cùng sha256 của bản HTML đã tải. Tài liệu sống — có thể đổi sau ngày lấy. Không dùng công cụ tóm tắt web.
- **Dùng cho:** cổng 2.5 / S7 (`12-roadmap.md`), `tools/object-storage-contract/`, biến `BO19_OBJECT_STORAGE_*` (ADR-037). PO hỏi 2026-10-21: giá trị `REGION` cho SigV4 và dạng endpoint.

| Tên | URL | sha256 của bản HTML tải | `dateModified` trong trang |
|---|---|---|---|
| r2-s3-api | `https://developers.cloudflare.com/r2/api/s3/api/` | `73277c0d7fc7a8009a77083e5234394e3f9c51041459801dbb000e59a9067c36` | 2026-10-14 |
| r2-get-started-s3 | `https://developers.cloudflare.com/r2/get-started/s3/` | `6e6841f420918abfa8e52db7c9e5a0a1bf7b456d82ba8bb04e149dcead9af309` | 2026-04-21 |
| r2-api-tokens | `https://developers.cloudflare.com/r2/api/tokens/` | `d7ffd5cd0664b3f629abd027cd3c7b05e542ab01a8bf675b46ca0199273bcdff` | 2026-10-01 |

(Bản HTML của `r2-s3-api` có cùng sha256 với lần tải ngày 2026-10-20 ở `s7-object-storage-ung-vien.md`: trang không đổi giữa hai ngày.)

## 1. Giá trị `region` — `auto`

> "When using the S3 API, the region for an R2 bucket is `auto`. For compatibility with tools that do not allow you to specify a region, an empty value and `us-east-1` will alias to the `auto` region." *(r2-s3-api, mục Bucket region)*

Ví dụ `boto3` của Cloudflare: `region_name='auto',  # Required by boto3, not used by R2` *(r2-get-started-s3)*.

→ `BO19_OBJECT_STORAGE_REGION=auto`. `us-east-1` (mặc định của `ObjectStorageConfig`) cũng được tài liệu nêu là bí danh của `auto`; tool S7 dùng đúng giá trị PO đặt trong biến môi trường và ghi giá trị đó vào kết quả.

## 2. Dạng endpoint

> "The API is available via the `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` endpoint." *(r2-s3-api)*

> "You will also need to configure the `endpoint` in your S3 client to `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`." *(r2-api-tokens)*

> "You also need your S3 API endpoint URL which you can find at the bottom of the Create API Token confirmation page once you have created your token, or on the R2 Overview page" *(r2-get-started-s3, trích ý; câu đầy đủ ở trang gốc)*

→ `BO19_OBJECT_STORAGE_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com` — **không** kèm tên bucket hay đường dẫn. `<ACCOUNT_ID>` lấy ở dashboard (trang "Find account and zone IDs" do tài liệu trỏ tới).

**Bucket đặt jurisdiction** phải dùng endpoint riêng, và *"Jurisdictional buckets can only be accessed via the corresponding jurisdictional endpoint"* *(r2-api-tokens)*:

- European Union: `https://<ACCOUNT_ID>.eu.r2.cloudflarestorage.com`
- FedRAMP: `https://<ACCOUNT_ID>.fedramp.r2.cloudflarestorage.com`
- United States: `https://<ACCOUNT_ID>.us.r2.cloudflarestorage.com`

Bucket tạo **không** chọn jurisdiction (chỉ có gợi ý vùng — `r2-data-location` ở `s7-object-storage-ung-vien.md`) dùng endpoint chung ở trên.

## 3. Quyền của token

> "You must purchase R2 before you can generate an API token." *(r2-api-tokens)* — **`[CẦN XÁC MINH]`**: trang không nói "mua" ở đây có gồm việc kích hoạt R2 trong gói miễn phí hay không, và có đòi phương thức thanh toán không. Cổng 2.5 giữ ràng buộc "gói free" của PO: nếu bước kích hoạt R2 đòi thẻ hay phát sinh phí thì PO báo trước khi tiếp tục.

> "(Optional) If you select the **Object Read and Write** or **Object Read** permissions, you can scope your token to a set of buckets." — "Object Read & Write: Allows the ability to read, write, and list objects in specific buckets." *(r2-api-tokens)*

> "You will not be able to access your **Secret Access Key** again after this step." *(r2-api-tokens)*

→ Token loại **Object Read & Write**, giới hạn vào đúng một bucket. Quyền này **không** gồm tạo/xoá bucket hay sửa cấu hình bucket (đó là "Admin Read & Write") → phép thử versioning và object lock **không chạy được bằng token này** (và bảng tương thích của `r2-s3-api` ghi `❌` cho cả bốn thao tác đó — `s7-object-storage-ung-vien.md` mục 1); S7 ghi rõ "không chạy" kèm lý do, không ghi "đạt".

## 4. Chưa có trong tài liệu đã tải

- **Kiểu địa chỉ path-style hay virtual-hosted:** các trang trên không nêu. Adapter của dự án dùng path-style (`addressing_style = path`, ADR-037) → `[CẦN XÁC MINH]`, S7 đo bằng chính adapter.
- **Mã lỗi khi hai `PUT … If-None-Match: *` đồng thời:** trang nêu `412 PreconditionFailed` *(s7-object-storage-ung-vien.md mục 1)*; S7 ghi mã thực tế của từng lệnh bị từ chối; adapter chỉ ánh xạ `412`/`PreconditionFailed` thành `AlreadyExists`, mã khác thành `STORAGE_UNAVAILABLE` và sẽ hiện ra ở kết quả.
