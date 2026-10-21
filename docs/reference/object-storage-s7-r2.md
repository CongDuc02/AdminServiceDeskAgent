# Phép thử object storage thật — r2 (S7, cổng 2.5)

- **Sinh bằng** `tools/object-storage-contract/object_storage_contract.py --label r2`, lần chạy `d2c487b11234`, bắt đầu 2026-10-21 05:15:54 (UTC). Chỉ số, mã và kết quả; không có endpoint, tên bucket hay khoá (tool tự quét trước khi ghi).
- **Client:** `boto3` 1.37.3, `botocore` 1.37.3; qua adapter `bo19.object_storage.ObjectStorage` (SigV4, path-style, `retries.max_attempts = 1`). `region` = `auto`.
- **Tiền tố khoá:** chỉ `s7-probe/d2c487b11234/`. **Dọn:** xoá 6 khoá, lỗi 0, còn lại dưới tiền tố 0.

| # | Phép thử | Kết quả | ms | Dữ kiện |
|---|---|---|---|---|
| C0 | HeadBucket với credential này (thông tin, bước kiểm khởi động #14) | đạt (thông tin) | 1529 | `{"head_bucket": true}` |
| C1 | PUT khoá mới kèm If-None-Match: * rồi GET | đạt | 730 | `{}` |
| C2 | PUT lại khoá đã có → từ chối (412) và byte cũ nguyên (A-024, ADR-037 điều kiện 3; T2) | đạt | 1218 | `{"old_bytes_intact": true, "second_put": "ALREADY_EXISTS"}` |
| C3 | Metadata và Content-Length trong cùng lệnh PUT (T3) | đạt | 602 | `{"metadata_roundtrip": true, "size_bytes": 2048}` |
| C4 | 8 luồng cùng PUT một khoá mới → đúng một thắng (T6) | đạt | 1256 | `{"already_exists": 7, "final_object_is_one_writer": true, "other_codes": [], "succeeded": 1, "threads": 8}` |
| C5 | ListObjectsV2 theo tiền tố trả đúng tập khoá đã ghi (T7) | đạt | 308 | `{"listed": 4, "same_set": true, "written": 4}` |
| C6 | GET theo khối 64 KiB, byte khớp | đạt | 3146 | `{"bytes_equal": true, "chunks": 5}` |
| C7 | Khoá không có: HEAD → None, GET → OBJECT_MISSING, DELETE không lỗi | đạt | 947 | `{"delete_missing_ok": true, "get_missing": "OBJECT_MISSING", "head_missing_is_none": true}` |
| C8 | DELETE rồi PUT lại có điều kiện được | đạt | 1642 | `{"gone_after_delete": true, "reput_after_delete": true}` |
| C9 | Sai secret → ACCESS_DENIED (ánh xạ lỗi của adapter) | đạt | 392 | `{"bad_secret": "ACCESS_DENIED"}` |

## Không chạy

- **PutBucketVersioning / GetBucketVersioning** — không chạy: token Object Read & Write không có quyền cấu hình bucket; bảng tương thích của nhà cung cấp ghi chưa hỗ trợ — xem docs/reference/r2-s3-endpoint-va-region.md
- **PutObjectLockConfiguration / PutObjectRetention** — không chạy: như trên; A-024 chỉ đòi MỘT trong ba lớp bảo vệ, lớp đã chọn là ghi có điều kiện (ADR-037)
