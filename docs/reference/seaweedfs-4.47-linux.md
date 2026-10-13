# SeaweedFS 4.47 — bản Linux amd64 cho test object storage (B8a, ADR-031, ADR-037)

- **Lấy bằng `curl` ngày 2026-10-13** (03:29 UTC), không qua công cụ tóm tắt web.
- **Nguồn:** bản phát hành `4.47` của `seaweedfs/seaweedfs` (đăng 2026-09-14 theo GitHub API).

| File | URL | sha256 | md5 |
|---|---|---|---|
| `linux_amd64.tar.gz` (45.801.355 byte; chứa đúng một file `weed`) | `https://github.com/seaweedfs/seaweedfs/releases/download/4.47/linux_amd64.tar.gz` | `31fb804858885f9e7f18b6d3b1da09e824baac3e6a55b5a62c3c4c77e6ed6d7d` | `d327aa9fc73bfa7861fe3be4a4e9ebb7` — **khớp** file `linux_amd64.tar.gz.md5` đi kèm bản phát hành |

- **Ghim:** `tools/object-storage-local/start.sh` kiểm sha256 trên trước khi giải nén; sai thì không chạy. Bản Windows đã đo ở `object-storage-local-s3.md` (cùng bản 4.47, sha256 của `windows_amd64.zip` ở đó).
- **Dùng cho:** test của `bo19.object_storage` và `tool_layer.storage` ở CI và local. **Không vào image, không lên Render** (ADR-031).
- **Cờ chạy:** như ADR-031 (`weed server`, `-filer -s3 -s3.config`, telemetry tắt, `-master.volumeSizeLimitMB=64 -volume.max=200`). Khác một chỗ — trong container phải `-ip=<tên container> -ip.bind=0.0.0.0` để container khác trên network `ci` nối được; cổng không publish ra máy chủ.
- **Kết quả đo trên bản Linux này (2026-10-13):** `PutObject` kèm `If-None-Match: *` lên khoá đã có trả HTTP **412**, mã lỗi `PreconditionFailed`; byte cũ nguyên vẹn (`backend/tests/test_object_storage.py`, `test_dieu_kien_q1_*`) — điều kiện duyệt Q1 của ADR-037. Không có `If-None-Match` thì `PUT` đè được (đối chứng).
