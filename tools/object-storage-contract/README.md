# `tools/object-storage-contract/` — phép thử object storage thật (S7, cổng 2.5)

Không phải mã ứng dụng, không vào image. Đóng **A-024** (nhà cung cấp phải giữ được giao thức ghi một lần) và **điều kiện 3 của ADR-037** (phép thử `412` trên nhà cung cấp thật trước cổng 2.5). Nhà cung cấp: **Cloudflare R2, gói miễn phí** (PO, 2026-10-20). Quyết định về tool này: PO, 2026-10-21.

## Luật

- **Cấu hình chỉ từ năm biến môi trường** do người chạy export tường minh trong terminal: `BO19_OBJECT_STORAGE_ENDPOINT_URL`, `_BUCKET`, `_REGION`, `_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY`. Tool **không đọc `.env`** hay file nào; credential không bao giờ trên dòng lệnh, không in, không ghi.
- **Gọi mạng thật chỉ khi có `--confirm-real`.** Không có cờ này tool chỉ in kế hoạch và thoát mã `3`.
- **Chỉ đụng khoá dưới `s7-probe/<mã lần chạy>/`.** Xong thì xoá từng khoá của lần chạy và kiểm lại: dưới tiền tố đó không còn khoá nào. Tool không liệt kê hay xoá khoá ngoài tiền tố.
- **Chỉ ghi số, mã, kết quả đạt/không.** Không ghi endpoint (có mã tài khoản), tên bucket hay khoá; `self_check` quét kết quả, không đạt thì **không ghi file** (mã `1`).
- Quy mô: dưới 100 request (khoảng 20 thao tác ghi hoặc liệt kê — "Class A" của R2 — còn lại đọc và xoá) — rất nhỏ so với gói miễn phí (1 triệu Class A mỗi tháng, `s7-object-storage-ung-vien.md` mục 1).

## Phép thử

| # | Làm gì | Đóng |
|---|---|---|
| C0 | `HeadBucket` với credential này — **thông tin**, không tính đạt/không | bước kiểm khởi động #14 |
| C1 | `PUT` khoá mới kèm `If-None-Match: *`, `GET` | ghi một lần |
| C2 | `PUT` lại khoá đã có, byte khác → từ chối (`412`); đọc lại: byte cũ nguyên | A-024, ADR-037 điều kiện 3 (T2) |
| C3 | Metadata `bo19-*` và `Content-Length` trong cùng lệnh `PUT` | metadata bản ghim `ISSUED` (T3) |
| C4 | Tám luồng cùng `PUT` một khoá mới → đúng một thắng; mã của bảy lệnh bị từ chối (nếu khác `ALREADY_EXISTS` thì thêm mã gốc của sản phẩm) | ghi đồng thời (T6) |
| C5 | `ListObjectsV2` theo tiền tố trả đúng tập khoá | `object_claim_reconcile` (T7) |
| C6 | `GET` theo khối 64 KiB, byte khớp | tải file theo khối (O1-18) |
| C7 | Khoá không có: `HEAD`→`None`, `GET`→`OBJECT_MISSING`, `DELETE` không lỗi | ánh xạ lỗi |
| C8 | `DELETE` rồi `PUT` lại có điều kiện | dọn object mồ côi |
| C9 | Sai secret → `ACCESS_DENIED` | ánh xạ lỗi |

**Không chạy** (ghi trong kết quả kèm lý do): versioning và object lock — token Object Read & Write không có quyền cấu hình bucket, và R2 ghi chưa hỗ trợ (`docs/reference/r2-s3-endpoint-va-region.md` mục 3). A-024 chỉ đòi **một** trong ba lớp; lớp đã chọn là ghi có điều kiện.

## Chạy

Từ thư mục gốc repo, với image `bo19-test` (đủ `boto3`) hoặc môi trường Python có `backend/requirements-linux.lock`. PowerShell, từng dòng — biến chỉ sống trong cửa sổ terminal đó:

```powershell
$env:BO19_OBJECT_STORAGE_ENDPOINT_URL = "https://<ACCOUNT_ID>.r2.cloudflarestorage.com"
$env:BO19_OBJECT_STORAGE_BUCKET = "<tên bucket>"
$env:BO19_OBJECT_STORAGE_REGION = "auto"
$env:BO19_OBJECT_STORAGE_ACCESS_KEY_ID = Read-Host "Access Key ID"
$env:BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY = Read-Host "Secret Access Key"
python tools/object-storage-contract/object_storage_contract.py            # in kế hoạch, KHÔNG gọi mạng (mã 3)
python tools/object-storage-contract/object_storage_contract.py --confirm-real --label r2
```

Mã thoát: `0` đạt · `1` có phép thử bắt buộc hỏng hoặc `self_check` không đạt · `2` thiếu biến / nhãn sai · `3` chưa xác nhận · `4` đạt nhưng dưới tiền tố còn khoá chưa dọn được. Kết quả: `tools/object-storage-contract/out/s7-<label>.md` (gitignored) và, nếu không có `--no-publish`, `docs/reference/object-storage-s7-<label>.md`.

`backend/tests/test_object_storage_contract_tool.py` chạy toàn bộ tool với SeaweedFS trong container ở mỗi lần CI (không mạng ngoài, không credential thật).
