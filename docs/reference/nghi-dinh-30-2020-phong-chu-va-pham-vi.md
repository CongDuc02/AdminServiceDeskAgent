# Nghị định 30/2020/NĐ-CP về công tác văn thư — phạm vi áp dụng và quy định về phông chữ (cổng 1.6, A-058)

- **Lấy bằng `curl` ngày 2026-10-13** (03:03 UTC), không qua công cụ tóm tắt web. Tìm URL bằng tìm kiếm web; nội dung đọc từ file đã tải.
- **Văn bản:** Nghị định số 30/2020/NĐ-CP ngày 05 tháng 3 năm 2020 của Chính phủ về công tác văn thư; đăng Công báo số 283 + 284, ngày 17-3-2020. Điều 37: "có hiệu lực thi hành kể từ ngày ký".

| Nguồn | URL | sha256 |
|---|---|---|
| Trang văn bản, vanban.chinhphu.vn | `https://vanban.chinhphu.vn/default.aspx?pageid=27160&docid=199378` | (trang HTML, không lưu file) |
| **PDF ký, vanban.chinhphu.vn** — 76 trang, **bản quét, không có lớp chữ** (trích văn bản được 1.206 ký tự) | `https://datafiles.chinhphu.vn/cpp/files/vbpq/2020/03/30.signed.pdf` | `be2514460c953141923579e4a0ddd0249c611643a59514976790dc1d90589178` |
| **PDF Công báo** — 82 trang, **có lớp chữ**; nguồn của các trích dẫn dưới đây | `https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2020/3/30858/30246-1-2020283-28430-2020-nd-cp.pdf` | `698e45e0aae921a20c0e31ffa87c50fd0324f640e70a6eca8d49e4f51045c7bb` |
| DOC Công báo | `https://congbao.chinhphu.vn/noi-dung-van-ban-so-30-2020-nd-cp-30858` (liên kết tải trên trang) | `22f381fd3ba74599ef4d3a5756dbb4c210e6a76411a39865c05cfe0adb48830f` |

**Cách trích:** `pypdf` 4.3.1 đọc lớp chữ của PDF Công báo. Lớp chữ có khoảng trắng thừa giữa các chữ ("v ăn bản", "ph ạm vi"); các trích dẫn dưới đây **gộp khoảng trắng thừa, không đổi chữ nào**. Đối chiếu với PDF ký (bản quét) chưa làm — bản quét không có chữ để so; số trang ghi theo Công báo.

## 1. Phạm vi áp dụng — Điều 1 và Điều 2

> **Điều 1. Phạm vi điều chỉnh** — Nghị định này quy định về công tác văn thư và quản lý nhà nước về công tác văn thư. Công tác văn thư được quy định tại Nghị định này bao gồm: Soạn thảo, ký ban hành văn bản; quản lý văn bản; lập hồ sơ và nộp lưu hồ sơ, tài liệu vào Lưu trữ cơ quan; quản lý và sử dụng con dấu, thiết bị lưu khóa bí mật trong công tác văn thư.
>
> **Điều 2. Đối tượng áp dụng**
> 1. Nghị định này áp dụng đối với cơ quan, tổ chức nhà nước và doanh nghiệp nhà nước (sau đây gọi chung là cơ quan, tổ chức).
> 2. Tổ chức chính trị, tổ chức chính trị - xã hội, tổ chức xã hội, tổ chức xã hội - nghề nghiệp căn cứ quy định của Nghị định này và các quy định của Đảng, của pháp luật có liên quan để áp dụng cho phù hợp.

**Đọc ở mức nguyên văn, không phải phán quyết pháp lý:**

- Khoản 1 Điều 2 nêu **cơ quan, tổ chức nhà nước và doanh nghiệp nhà nước** là đối tượng áp dụng. **Văn bản không nêu doanh nghiệp tư nhân** ở khoản nào của Điều 2, và không có điều nào khác trong 38 điều của Nghị định mở rộng đối tượng.
- Khoản 2 áp dụng "cho phù hợp" với tổ chức chính trị, chính trị - xã hội, xã hội, xã hội - nghề nghiệp — không gọi tên doanh nghiệp tư nhân.
- Phạm vi điều chỉnh (Điều 1) là **công tác văn thư của cơ quan, tổ chức** — soạn thảo, ký ban hành, quản lý văn bản, con dấu — chứ không phải mọi văn bản mà một doanh nghiệp phát hành cho người ngoài.
- **`[CẦN XÁC MINH]`:** bản này là bản gốc ban hành 2020. Chưa kiểm xem có văn bản sửa đổi, bổ sung hay thay thế sau đó không, và cơ quan nào hướng dẫn áp dụng cho tổ chức ngoài Điều 2. Nơi tra: Công báo, Cơ sở dữ liệu quốc gia về văn bản pháp luật.

## 2. Phông chữ — Điều 9 và Phụ lục I

> **Điều 9. Kỹ thuật trình bày văn bản** — Kỹ thuật trình bày văn bản bao gồm: Khổ giấy, kiểu trình bày, định lề trang, phông chữ, cỡ chữ, kiểu chữ, vị trí trình bày các thành phần thể thức, số trang văn bản. Kỹ thuật trình bày văn bản hành chính được thực hiện theo quy định tại Phụ lục I Nghị định này. […]

> **Phụ lục I — THỂ THỨC, KỸ THUẬT TRÌNH BÀY VĂN BẢN HÀNH CHÍNH VÀ BẢN SAO VĂN BẢN, Phần I, mục I. QUY ĐỊNH CHUNG** (Công báo, trang 22)
> 1. Khổ giấy: Khổ A4 (210 mm x 297 mm).
> […]
> 3. Định lề trang: Cách mép trên và mép dưới 20 - 25 mm, cách mép trái 30 - 35 mm, cách mép phải 15 - 20 mm.
> **4. Phông chữ: Phông chữ tiếng Việt Times New Roman, bộ mã ký tự Unicode theo Tiêu chuẩn Việt Nam TCVN 6909:2001, màu đen.**
> 5. Cỡ chữ và kiểu chữ: Theo quy định cụ thể cho từng yếu tố thể thức.

Bảng "Mẫu chữ và chi tiết trình bày thể thức văn bản hành chính" (Phụ lục I, mục V) lặp lại cột "Phông chữ Times New Roman" cho từng thành phần thể thức, và nhiều thành phần (ví dụ dòng thời gian ký số) ghi "phông chữ Times New Roman".

**Đọc ở mức nguyên văn:** quy định **đích danh tên phông "Times New Roman"** cho văn bản hành chính theo Nghị định này; không nêu phông thay thế hay tương đương.
