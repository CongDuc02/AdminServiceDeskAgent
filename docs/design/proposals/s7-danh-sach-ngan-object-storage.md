# Cổng 2.5 / S7 — danh sách ngắn nhà cung cấp object storage (đề xuất, PO chọn)

**Trạng thái:** đề xuất, chờ PO chọn · **Ngày:** 2026-10-20 · **Chỉ tài liệu** — chưa tạo tài khoản, chưa chạy phép thử nào, chưa đổi mã · **Căn cứ:** A-024 (nhà cung cấp phải có ít nhất một cơ chế ghi một lần ở tầng lưu trữ), ADR-037 (mọi `PUT` mang `If-None-Match: *`; điều kiện 3: phép thử `412` trên nhà cung cấp thật trước cổng 2.5), A-080 (vùng lưu trữ dữ liệu), A-085 (gói free/rẻ ở giai đoạn build), bước S7 của `.claude/commands/spike.md` (PO duyệt danh sách ngắn; spike không tự chọn) · **Bằng chứng:** `docs/reference/s7-object-storage-ung-vien.md` (URL, ngày, sha256, dòng trích nguyên văn)

## Tiêu chí (theo PO) và cách kiểm

1. **Ghi có điều kiện `If-None-Match: *` trả `412`** (ADR-037): tài liệu gốc phải nêu cho `PutObject`; rồi **phép thử thật ở S7** (T2: ghi lại lên khoá đã có → `412`, byte cũ còn nguyên; T6: tám luồng cùng khoá, một thắng — bộ phép thử đã có ở `docs/reference/object-storage-local-s3.md`, chạy bằng `boto3` của ADR-037).
2. **Vùng lưu trữ dữ liệu (A-080):** nhà cung cấp cho **chọn** nơi đặt dữ liệu không, và mức đảm bảo (điều khoản hay chỉ gợi ý). Đây là dữ kiện của nhà cung cấp, **không** phải kết luận pháp lý — văn bản luật chưa có ở `docs/reference/` (A-080).
3. **Hạn mức miễn phí / giá** (giai đoạn build chỉ dữ liệu giả, A-085).
4. **API tương thích S3:** đủ `PutObject` (có `IfNoneMatch`), `GetObject`, `HeadObject`, `DeleteObject`, `ListObjectsV2`, chữ ký SigV4, địa chỉ kiểu path (cách adapter của ADR-037 gọi); kiểm bằng chính adapter ở S7.

## Danh sách ngắn đề xuất — bốn nhà cung cấp

| | **Cloudflare R2** | **Tigris** | **OVHcloud Object Storage** | **Scaleway Object Storage** |
|---|---|---|---|---|
| **`If-None-Match: *` → 412** (tài liệu gốc) | **Có, nêu rõ**: đồng thời nhiều ghi cùng khoá chưa có, "at most one write succeeds and the others fail with 412 PreconditionFailed" | **Có, nêu rõ**: "412 Precondition Failed on a matching PUT" | **Có, nêu rõ**: "all others receive 412 Precondition Failed" | Header được hỗ trợ; **trang không nêu mã `412`** → chỉ biết bằng phép thử ở S7 |
| **Vùng (A-080)** | Chỉ **gợi ý** (`apac`, best effort); đảm bảo bằng điều khoản chỉ có **EU** và FedRAMP — **không có châu Á** | Mặc định **toàn cầu**; chọn được **một vùng** (`sin` — Singapore, `nrt` — Tokyo) | **Singapore, Sydney, Mumbai** (1-AZ) và nhiều vùng châu Âu — chọn vùng khi tạo bucket | Paris, Amsterdam, Warsaw, Milan — **chỉ châu Âu** |
| **Miễn phí / giá** | **10 GB-tháng**, 1 triệu thao tác ghi (Class A), 10 triệu đọc (Class B), egress miễn phí; ngoài gói $0,015/GB-tháng | Dòng tiêu đề "FREE 5GB STORAGE"; **hạn mức thao tác chưa nêu** `[CẦN XÁC MINH]`; ngoài gói $0,02/GB-tháng, egress miễn phí | **Không có gói lưu trữ miễn phí**; vùng 1-AZ Standard ≈ **$0,0081/GiB-tháng**, request và lưu lượng miễn phí; **$200 tín dụng dùng thử** cho dự án Public Cloud đầu tiên | **Không có gói lưu trữ miễn phí**; One Zone €0,00803/GB-tháng; egress miễn phí 75 GB/tháng |
| **Versioning / khoá đối tượng** | Không có cả hai (`❌`) — chỉ còn ghi có điều kiện làm lớp bảo vệ (A-024 chỉ đòi **một**) | Chưa xác minh được từ bảng tương thích `[CẦN XÁC MINH]` | Có hướng dẫn cho cả hai (nội dung chưa đọc) | Có hướng dẫn cho cả hai (chưa đọc) |
| **Rủi ro đã thấy** | Vùng châu Á không bảo đảm → nếu dữ liệu thật phải ở một vùng cụ thể thì **không đủ** | Mặc định toàn cầu: phải đặt vùng khi tạo bucket và kiểm lại; hạn mức miễn phí mơ hồ | Phải có tài khoản Public Cloud; chưa thấy gói miễn phí vô thời hạn | `412` chưa xác nhận; không có châu Á |

**Đã xem, không đưa vào danh sách:**
- **Backblaze B2** — tài liệu chính thức đã tải không nêu ghi có điều kiện; chỉ có nguồn thứ ba nói B2 từ chối header. Không xác minh được từ tài liệu gốc nên loại khỏi S7 (ghi rõ lý do thay vì suy đoán).
- **AWS S3** — có ghi có điều kiện, nhưng không có gói miễn phí vô thời hạn ("up to $200 in AWS Free Tier credits… free plan available for 6 months"); là phương án đối chứng nếu PO muốn trả phí.
- **Chưa xem:** Supabase Storage, Hetzner Object Storage, và nhà cung cấp trong nước (VNG Cloud vStorage, Viettel IDC, FPT Cloud) — cần thêm tài liệu gốc nếu PO muốn xét theo A-080.

## Gợi ý (PO quyết)

- **Giai đoạn build (dữ liệu giả, A-085):** **Cloudflare R2** — gói miễn phí lớn nhất trong bốn, `412` nêu rõ trong tài liệu, egress miễn phí, ít việc nhất để dựng. Hạn chế vùng của R2 không cản dữ liệu giả.
- **Trước mốc dùng dữ liệu thật (mốc 2, ADR-032):** đánh giá lại theo A-080: nếu cần đặt dữ liệu ở một vùng châu Á cụ thể thì **OVHcloud (Singapore)** hoặc **Tigris (một vùng `sin`)** là hai ứng viên có vùng chọn được; đổi nhà cung cấp chỉ là đổi biến môi trường (`BO19_OBJECT_STORAGE_*`, ADR-037) nếu phép thử qua.
- **S7 chạy trên 2–3 nhà cung cấp** (đúng `spike.md`): đề xuất **R2, Tigris, OVHcloud**; Scaleway chỉ khi PO muốn có ứng viên thứ tư ở châu Âu.

## Việc của S7 sau khi PO chọn (chưa làm)

1. PO tạo tài khoản, bucket (đặt vùng theo mục Vùng ở trên), và **API token chỉ đọc/ghi bucket đó**; ghi vào file env ngoài repo với các biến `BO19_OBJECT_STORAGE_ENDPOINT_URL`, `_BUCKET`, `_REGION`, `_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY` — không dán vào chat, không vào repo (luật credential của `CLAUDE.md`).
2. Người triển khai viết `tools/object-storage-contract/` (script dùng chung cho nhà cung cấp thật — ADR-037 điều kiện 3): T2 (`412`, byte cũ nguyên), T6 (8 luồng một khoá, một thắng), `HEAD`/`GET`/`DELETE`/`ListObjectsV2` qua adapter của dự án, path-style, vùng; ghi kết quả vào `ASSUMPTIONS.md` và `CHANGELOG.md` theo luật `spike.md` (số đo nguyên văn, hoặc ghi rõ không chạy được và vì sao).
3. Kết quả đạt thì cổng 2.5 đạt; cấu hình trên Render (`BO19_OBJECT_STORAGE_*`) rồi chuyển sang `combined_main` theo mục Runbook — chuyển Render sang `combined_main` của `11-ops.md`.

## Câu cần PO quyết

1. Chọn 2–3 nhà cung cấp cho S7 (đề xuất: R2, Tigris, OVHcloud).
2. Có muốn xét thêm nhà cung cấp trong nước theo A-080 không (cần tài liệu gốc — tôi sẽ tải bằng `curl` nếu PO cho tên)?
3. Có cần gói **trả phí rẻ** thay vì miễn phí không (A-085 nói gói free; OVH/Scaleway ≈ $0,008/GB-tháng)?
