# Ứng viên object storage cho cổng 2.5 / S7 — trích từ tài liệu gốc

- **Nguồn — lấy bằng `curl`, ngày 2026-10-20.** Bản HTML gốc không vào repo (lớn; một số trang là bản dựng bằng JavaScript); đây là các dòng **nguyên văn** trích từ bản chữ của chúng, cùng sha256 của bản HTML đã tải. Tài liệu sống — có thể đổi sau ngày lấy. Tìm kiếm web chỉ dùng để tìm URL; mọi điều dưới đây lấy từ trang gốc, trừ chỗ ghi "nguồn thứ ba".
- **Dùng cho:** `docs/design/proposals/s7-danh-sach-ngan-object-storage.md`; cổng 2.5 và bước S7 của `12-roadmap.md`; A-024, ADR-037 (điều kiện 3), A-080.
- **Không có gì ở đây là kết luận về pháp lý** (A-080 chưa có bản gốc của luật trong `docs/reference/`): cột "vùng" chỉ nêu nhà cung cấp cho đặt dữ liệu ở đâu.

| Tên | URL | sha256 của bản tải |
|---|---|---|
| r2-s3-api | `https://developers.cloudflare.com/r2/api/s3/api/` | `73277c0d7fc7a8009a77083e5234394e3f9c51041459801dbb000e59a9067c36` |
| r2-pricing | `https://developers.cloudflare.com/r2/pricing/` | `977bd2fec2f153b04c5f0a244ec92fcffb697bc59cddc230b75c5835b46838e0` |
| r2-data-location | `https://developers.cloudflare.com/r2/reference/data-location/` | `32bed76cb74de103e63ac74ff5b2fdebc3e86490fbadad35345f65e4c3831e30` |
| tigris-conditionals | `https://www.tigrisdata.com/docs/objects/conditionals/` | `4885f553bfb00f90b8efd4522ae7e548893259b543a1ccc7c1d6bad376b1ab94` |
| tigris-pricing | `https://www.tigrisdata.com/docs/pricing/` | `e2ea3d3ad84c5c79208fa81841041aef545e94818220669b7e505790eecd2a17` |
| tigris-regions | `https://www.tigrisdata.com/docs/concepts/regions/` | `562a47bca6adb97f2128ef49881d8d9949b8d6b535bd182ef24a18bfb62af02a` |
| tigris-locations | `https://www.tigrisdata.com/docs/buckets/locations/` | `f2e0332c87a289b430b14c1c9c273209f015e35f525aeb97ba7c70205d5ae5f6` |
| tigris-s3api | `https://www.tigrisdata.com/docs/api/s3/` | `20d416e74d78c7f2b1c6b7320153b914d1b30f22d9c32591b6fd3151d6c0cf3e` |
| ovh-conditional | `https://docs.ovhcloud.com/en/guides/storage-and-backup/object-storage/s3-conditional-writes` | `4e348b58633dca0c310931a8b329eae0d6c78100814a82c2dc6497c3f45aee06` |
| ovh-locations | `https://docs.ovhcloud.com/en/guides/storage-and-backup/object-storage/s3-location` | `0f35f64e9f44d4584e50a0c7321dda05c1e25f9fc40243d38c97bc82e0d8bc34` |
| ovh-prices | `https://www.ovhcloud.com/en/public-cloud/prices/` | `66112cc3dce6e1efb6481ad13d12e16e4bb9894850773a471821940921c7c2fc` |
| ovh-pricing (trang sản phẩm) | `https://www.ovhcloud.com/en/public-cloud/object-storage/` | `d5c6b29825df0c115ab5a49a9e335501d9dde1b2c6f38de718dbd85bf5e6af68` |
| scw-conditional | `https://www.scaleway.com/en/docs/object-storage/api-cli/using-conditional-writes/` | `08758b75b1cadd2155bafdd4d2b8861bbb6f477371637f0d77ac3fa0be129c20` |
| scw-pricing | `https://www.scaleway.com/en/pricing/storage/` | `4528d09d384462cd6dac875cc5b18e8d7ebd089b8de9480c4eac22340fe83cec` |
| scw-availability | `https://www.scaleway.com/en/docs/account/reference-content/products-availability/` | `ae663b63c9cc9761f702e185642d3669e9302dd8f5f905d1c98e30c7cdd7fe09` |
| aws-conditional-writes | `https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html` | `8333d943dbbd7455a65791449d7e83816e62a3c4a9d006292ca59aa7602f394e` |
| aws-s3-pricing | `https://aws.amazon.com/s3/pricing/` | `7e8022ca70fa98b122b0adfa27223be3f186aef37157bca4527a2ea78687b8fd` |
| b2-s3-compat | `https://www.backblaze.com/docs/cloud-storage-s3-compatible-api` | `fa69a3e4abb5df4e217e7d35cf9a2b19a5ed2cb484987316ffb481241ffb62ee` |

## 1. Cloudflare R2

- **Ghi có điều kiện:** *"The conditional headers on PutObject (such as If-Match and If-None-Match) are evaluated atomically against the committed bucket state, as part of the same write that commits the object. For example, when multiple clients concurrently issue PutObject with If-None-Match: * for a previously absent key, at most one write succeeds and the others fail with **412 PreconditionFailed**."* Bảng tương thích: PutObject — `✅ Conditional Operations: ✅ If-Match ✅ If-Modified-Since ✅ If-None-Match ✅ If-Unmodified-Since`. *(r2-s3-api)*
- **Khoá đối tượng, versioning:** bảng liệt `❌ PutObjectLockConfiguration`, `❌ GetObjectLockConfiguration`, `❌ PutBucketVersioning`, `❌ GetBucketVersioning` *(r2-s3-api)* — chỉ còn ghi có điều kiện làm lớp bảo vệ (A-024 chỉ đòi **một** trong ba).
- **Gói miễn phí (hằng tháng):** Storage **10 GB-month**; Class A **1 million** requests; Class B **10 million** requests; Egress **Free**. Chỉ áp cho lớp Standard. Ngoài gói: `$0.015 / GB-month` Standard *(r2-pricing)*.
- **Vùng:** *Location Hints* — "optional parameters … to indicate the primary geographical location you expect data will be accessed from"; "best effort and not a guarantee" *(trích ý; câu đầy đủ ở r2-data-location)*; giá trị: `wnam`, `enam`, `weur`, `eeur`, `apac` (Asia-Pacific), `oc`. *Jurisdictional Restrictions* — "guarantee objects in a bucket are stored within a specific jurisdiction": chỉ có **`eu`** (European Union) và **`fedramp`** *(r2-data-location)*. **Không có** jurisdiction châu Á.

## 2. Tigris

- **Ghi có điều kiện:** *"If-None-Match: Request proceeds only if the object's ETag does not match. Use If-None-Match: "*" to write only if the object does not already exist. Returns 304 Not Modified on a matching GET, or **412 Precondition Failed** on a matching PUT."* Và: "guarantees that preconditions are always evaluated against the globally …" (câu bị cắt ở bản chữ — đọc đủ ở trang gốc) *(tigris-conditionals)*.
- **Gói miễn phí:** trang giá có dòng tiêu đề `FREE 5GB STORAGE COST EGRESS FEES` — **hạn mức miễn phí cụ thể (số request) không nêu trong bản tải** → `[CẦN XÁC MINH]`. Giá: Standard `$0.02/GB/month`, Infrequent Access `$0.01/GB/month`, ghi `$0.005/1000 requests`, đọc `$0.0005/1000 requests`, egress `Free`; "Tigris pricing is the same across all geographies" *(tigris-pricing)*.
- **Vùng:** mặc định bucket **toàn cầu** (*"Data distributed globally, follows access patterns"*, tigris-pricing); có thể đặt một vùng hay một vài vùng: `LocationConstraint` "names one Tigris region (iad), two regions separated by a comma (iad,sjc), or one geography (usa, eur)" *(tigris-s3api)*. Danh sách vùng có `sin` — Singapore (Asia-Pacific) và `nrt` *(tigris-regions)*.
- **Versioning, khoá đối tượng:** bảng tương thích của trang `tigris-s3api` có dòng `GetBucketVersioning`/`PutBucketVersioning` nhưng cột bị lệch khi trích — **không khẳng định** → `[CẦN XÁC MINH]` ở S7.

## 3. OVHcloud Object Storage (S3)

- **Ghi có điều kiện:** *"This guide explains how to use the If-Match and If-None-Match HTTP conditional headers on PutObject, DeleteObject, and CompleteMultipartUpload requests on your OVHcloud Object Storage buckets."*; *"Distributed locking primitive: Implement a lightweight, storage-native lock using If-None-Match: * on PutObject - only the first writer succeeds; all others receive **412 Precondition Failed**."* Gửi cả hai header: `400 Bad Request` *(ovh-conditional)*.
- **Vùng:** bảng vị trí S3 có **Asia-Pacific: Singapore (`sgp`), Sydney (`ap-southeast-syd`), Mumbai (`ap-south-mum`)**, loại "1-AZ region", lớp `High Performance, Standard, Infrequent Access`; cũng có vùng châu Âu (Milan 3-AZ, Frankfurt …) *(ovh-locations)*.
- **Giá (chưa gồm VAT), "One Zone":** Standard `~$0.0081103 / GiB / month`; lưu lượng vào/ra ngoài `Free`, API requests `Free`; High Performance `~$0.0202794`; Infrequent Access `~$0.0043581` *(ovh-prices)*. **Không có gói lưu trữ miễn phí** — có "Public Cloud free trial: … US$ 200 free credit" cho dự án Public Cloud đầu tiên *(ovh-pricing)*.
- **Versioning, khoá đối tượng:** có hướng dẫn "Getting Started with Versioning" và "Managing object immutability with Object Lock (WORM)" *(tiêu đề ở ovh-s3-limits; nội dung chưa đọc)*.

## 4. Scaleway Object Storage

- **Ghi có điều kiện:** *"The If-None-Match header prevents overwrites of existing data by checking that no object with the same key name already exists in the bucket."* và "If an identical key name is found in the bucket, the operation fails." Ví dụ `put-object … --if-none-match "*"`. **Trang không nêu mã `412`** → cần phép thử ở S7 *(scw-conditional)*.
- **Giá:** Standard Multi-AZ `€0.01606/GB/month`; Standard One Zone `€0.00803/GB/month`; Ingress `Included`; Egress `75GB free every month then €0.01/GB/MONTH` *(scw-pricing)* — **không có lưu trữ miễn phí** (75 GB miễn phí là egress).
- **Vùng Object Storage:** Paris, Amsterdam, Warsaw, Milan *(scw-availability)* — **không có châu Á**.

## 5. Đối chứng và loại

- **AWS S3:** có ghi có điều kiện (`If-None-Match` prevents overwrites; `aws s3api put-object … --if-none-match "*"`) *(aws-conditional-writes)*. Giá/gói: *"As of July 15, 2025, new AWS customers will receive up to $200 in AWS Free Tier credits … The free plan will be available for 6 months after account creation"* *(aws-s3-pricing)* — **không phải gói miễn phí vô thời hạn**. Danh sách vùng không trích ở đây.
- **Backblaze B2:** trang tương thích S3 chính thức đã tải **không nêu** ghi có điều kiện (không có chuỗi `If-None-Match` hay `conditional` trong bản tải) → **chưa xác minh được từ tài liệu gốc**. **Nguồn thứ ba** (không phải tài liệu Backblaze): một bản vá của dự án Proxmox Backup Server, 2025-07, ghi B2 từ chối header `If-None-Match` trên PUT nên phải bỏ header khi dùng B2 (`https://lists.proxmox.com/pipermail/pbs-devel/2025-July/014234.html`) — **chỉ là dấu hiệu**, không đưa vào quyết định.
- **Chưa xem (nêu để PO biết, không phải đánh giá):** Supabase Storage (S3 endpoint), Hetzner Object Storage, nhà cung cấp trong nước (VNG Cloud vStorage, Viettel IDC, FPT Cloud) — liên quan A-080 nếu dữ liệu thật phải ở trong nước; chưa có tài liệu gốc bằng tiếng Anh/Việt được tải về.
