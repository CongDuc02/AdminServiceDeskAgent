# Bộ luật Lao động 2019 — loại hợp đồng lao động và thử việc (Điều 20, Điều 24; mẫu giấy xác nhận công tác, A-013)

- **Lấy bằng `curl` ngày 2026-10-21** (09:32 UTC), không qua công cụ tóm tắt web. Tìm URL bằng tìm kiếm web; nội dung đọc từ file đã tải.
- **Văn bản:** Bộ luật số 45/2019/QH14 (Quốc hội), Công báo số 993 + 994, ngày 26-12-2019. PDF Công báo 94 trang, **có lớp chữ**.

| Nguồn | URL | sha256 |
|---|---|---|
| Trang văn bản, congbao.chinhphu.vn (tiêu đề trang ghi "Nghị quyết số 45/2019/QH14" — nhãn của trang, văn bản là Bộ luật) | `https://congbao.chinhphu.vn/van-ban/nghi-quyet-so-45-2019-qh14-30232.htm` | (trang HTML, không lưu file) |
| **PDF Công báo** — nguồn của các trích dẫn dưới đây | `https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2019/11/30232/29070-1-2019993-99445-2019-qh14.pdf` | `3c865f3d92ba23604e316360b902297ddbc0d1c394d3c08a466029a9d43b5b6c` |
| PDF ký, datafiles.chinhphu.vn — 83 trang, **bản quét, không có lớp chữ**; chưa dùng | `https://datafiles.chinhphu.vn/cpp/files/vbpq/2019/12/45.signed.pdf` | `a0c0fcc3b9e040bcdcab70191f0ab95952183be94a6f5bc6424e8d3e85697139` |

**Cách trích:** `pypdf` 4.3.1 đọc lớp chữ của PDF Công báo. Lớp chữ có khoảng trắng thừa giữa các chữ ("lo ại", "k ể"); các trích dẫn dưới đây **gộp khoảng trắng thừa, không đổi chữ nào**. Số trang ghi theo Công báo.

**Phạm vi của tài liệu này:** chỉ chữ của Điều 20 và Điều 24. **Không** kiểm tình trạng hiệu lực hay sửa đổi của Bộ luật sau 2019 (nguồn tìm kiếm có nói vbpl.vn ghi "hết hiệu lực một phần" — chưa mở, chưa kết luận), và không kết luận pháp lý.

## Điều 20. Loại hợp đồng lao động (Công báo, trang 11–12)

> 1. Hợp đồng lao động phải được giao kết theo một trong các loại sau đây:
> a) Hợp đồng lao động không xác định thời hạn là hợp đồng mà trong đó hai bên không xác định thời hạn, thời điểm chấm dứt hiệu lực của hợp đồng;
> b) Hợp đồng lao động xác định thời hạn là hợp đồng mà trong đó hai bên xác định thời hạn, thời điểm chấm dứt hiệu lực của hợp đồng trong thời gian không quá 36 tháng kể từ thời điểm có hiệu lực của hợp đồng.
> 2. Khi hợp đồng lao động quy định tại điểm b khoản 1 Điều này hết hạn mà người lao động vẫn tiếp tục làm việc thì thực hiện như sau: […] b) Nếu hết thời hạn 30 ngày kể từ ngày hợp đồng lao động hết hạn mà hai bên không ký kết hợp đồng lao động mới thì hợp đồng đã giao kết theo quy định tại điểm b khoản 1 Điều này trở thành hợp đồng lao động không xác định thời hạn; […]

## Điều 24. Thử việc (Công báo, trang 13)

> 1. Người sử dụng lao động và người lao động có thể thỏa thuận nội dung thử việc ghi trong hợp đồng lao động hoặc thỏa thuận về thử việc bằng việc giao kết hợp đồng thử việc.
> 2. Nội dung chủ yếu của hợp đồng thử việc gồm thời gian thử việc và nội dung quy định tại các điểm a, b, c, đ, g và h khoản 1 Điều 21 của Bộ luật này.

## Đọc ở mức nguyên văn (không phải kết luận pháp lý)

- **Điều 20 khoản 1 chỉ có hai loại hợp đồng lao động:** không xác định thời hạn, và xác định thời hạn (tối đa 36 tháng). Một hợp đồng xác định thời hạn 01, 02 hay 03 năm đều là **cùng một loại** (điểm b) — không có loại "1 năm / 2 năm / 3 năm" riêng.
- **Thử việc không nằm trong danh sách loại ở Điều 20 khoản 1.** Điều 24 khoản 1 cho hai cách: thỏa thuận thử việc **ghi trong** hợp đồng lao động, hoặc **hợp đồng thử việc** riêng. Với hệ thống: `PROBATION` trong `contract_type` là một giá trị trạng thái của hồ sơ nhân sự, không phải "loại hợp đồng lao động" theo nghĩa Điều 20 — khác với `FIXED_TERM` và `INDEFINITE`, ứng với điểm b và điểm a khoản 1 Điều 20.
- Văn bản này **không có** loại "khác" ngoài các loại trên; dòng "Khác (ghi rõ)" của phiếu khai cũ không có chỗ tương ứng.
