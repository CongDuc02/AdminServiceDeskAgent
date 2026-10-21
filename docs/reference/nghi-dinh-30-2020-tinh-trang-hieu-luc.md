# Nghị định 30/2020/NĐ-CP — đã bị sửa đổi, thay thế sau 2020 chưa? (kiểm 2026-10-21)

- **Câu hỏi của PO (2026-10-21):** Nghị định 30/2020/NĐ-CP đã bị sửa đổi hoặc thay thế sau 2020 chưa, kiểm từ nguồn chính thức (`vanban.chinhphu.vn` hoặc `congbao.chinhphu.vn`). **Ghi nhận dữ kiện, không kết luận pháp lý** (A-036, A-080).
- **Lấy bằng `curl` ngày 2026-10-21**, không qua công cụ tóm tắt web. Tìm kiếm web chỉ dùng để tìm URL; mọi điều dưới đây đọc từ trang tải về, trừ mục 3 (nói rõ).
- **Kết luận ở mức dữ kiện:** hai trang chính thức **không nêu** văn bản nào sửa đổi hay thay thế Nghị định 30/2020/NĐ-CP; điều này **chưa đủ** để nói "chưa bị sửa đổi" (mục 2). Mục `[CẦN XÁC MINH]` ở A-036, A-009, A-018 và `00-domain.md` **giữ nguyên** cho tới khi có kiểm ở nguồn có thẩm quyền về hiệu lực (mục 4).

## 1. Nguồn đã tải

| Nguồn | URL | sha256 của bản tải |
|---|---|---|
| Trang văn bản, cổng `vanban.chinhphu.vn` | `https://vanban.chinhphu.vn/default.aspx?pageid=27160&docid=199378` | `8b03e6bb556982428d5b11ffd264ba7fddb545652cb08a3b7547bf2f488e45c6` |
| Trang văn bản, Công báo | `https://congbao.chinhphu.vn/noi-dung-van-ban-so-30-2020-nd-cp-30858` (cùng nội dung tại `https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-30-2020-nd-cp-30858.htm`) | `7360bbc68a38b9e41830e6eabdbeefc82c98b72d14fec753c8e15ed6563f29b4` |

Bản gốc nội dung Nghị định (PDF Công báo, 82 trang, có lớp chữ) đã ở `docs/reference/nghi-dinh-30-2020-phong-chu-va-pham-vi.md` (sha256 `698e45e0…c7bb`); không tải lại.

## 2. Điều hai trang nêu — nguyên văn các dòng liên quan

**`congbao.chinhphu.vn`** (bản chữ của trang):

- `Nghị định số 30/2020/NĐ-CP về công tác văn thư.` · `Ban hành: 05/03/2020` · `- Hiệu lực: 05/03/2020` · `Nằm trong các Công báo: 283 + 284`.
- Thuộc tính: `Loại văn bản: Nghị định` · `Số, ký hiệu: 30/2020/NĐ-CP` · `Cơ quan ban hành: CHÍNH PHỦ` · `Ngày ban hành: 05/03/2020` · `Ngày hiệu lực: 05/03/2020`.
- Mục "Lược đồ" liệt kê các loại quan hệ, **mỗi loại kèm `[0]`**: `Văn bản sửa đổi bổ sung/đính chính [0]` · `Văn bản thay thế/bãi bỏ/hủy bỏ/đình chỉ một phần [0]` · `Văn bản bị thay thế/bãi bỏ/hủy bỏ/đình chỉ [0]` · `Văn bản thay thế/bãi bỏ/hủy bỏ/đình chỉ [0]` · `Văn bản bị sửa đổi bổ xung/được đính chính [0]` · `Văn bản bị thay thế/bãi bỏ/hủy bỏ/đình chỉ một phần [0]` (và các loại khác). Khối "Văn bản liên quan" trong HTML mang `class="box-vb-cb hidden"` và danh sách rỗng.
- **Giới hạn:** các số `[0]` và khối ẩn do trang dựng; dữ liệu quan hệ đầy đủ của "Lược đồ" được trang nạp bằng JavaScript từ máy chủ khác (khoá `siteid1548:loaiquanhe:all`, `eth.cnnd.vn`), **không có trong bản HTML tải bằng `curl`**. Công báo chỉ phản ánh văn bản **đăng Công báo** và không tự nhận là nguồn tra hiệu lực. Vì vậy `[0]` là "trang không nêu", không phải "đã kiểm không có".

**`vanban.chinhphu.vn`:** chỉ có siêu dữ liệu (`Số ký hiệu 30/2020/NĐ-CP`, `Ngày ban hành 05-03-2020`, `Loại văn bản Nghị định`, `Cơ quan ban hành Chính phủ`, `Người ký Nguyễn Xuân Phúc`, `Trích yếu Về công tác văn thư`, tài liệu đính kèm `30.signed.pdf`). **Không có trường tình trạng hiệu lực hay văn bản sửa đổi/thay thế.**

## 3. Tìm kiếm web (chỉ để tìm URL; không phải nguồn chính thức)

Hai lượt tìm bằng cụm từ "sửa đổi / thay thế / hết hiệu lực / dự thảo" kèm số hiệu, một lượt giới hạn trong `chinhphu.vn`, **không trả về văn bản nào sửa đổi hay thay thế Nghị định 30/2020/NĐ-CP**; các trang trả về đều mô tả chính Nghị định (các trang đó nêu Nghị định thay thế Nghị định 110/2004/NĐ-CP và Nghị định 09/2010/NĐ-CP — điều này không đọc từ chính văn ở đây, và không phải điều PO hỏi). Đây là **vắng bằng chứng**, không phải bằng chứng vắng mặt: công cụ tìm kiếm không đọc được dữ liệu quan hệ nạp bằng JavaScript và không đảm bảo bao phủ.

Thông cáo báo chí hằng tháng của Bộ Tư pháp về văn bản quy phạm pháp luật do Chính phủ, Thủ tướng ban hành (ví dụ `https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/10/6378-tcbc.pdf`, tháng 9/2025; sha256 `3cb788cebdd85b2de9e745431644cd0edece52c5f8ccb9d9f0146233caaf9df7`) là cách duyệt từng tháng; **chưa duyệt** — bản PDF này không trích chữ được bằng `pdftotext` (font không ánh xạ), nên không dùng làm căn cứ.

## 4. Còn thiếu để kết luận được

1. **Cơ sở dữ liệu quốc gia về văn bản pháp luật** (nguồn có trường "tình trạng hiệu lực" và "văn bản sửa đổi/thay thế" của Bộ Tư pháp) — hai nguồn PO nêu không có trường này ở bản tải được. Chưa tải vì không nằm trong hai nguồn PO nêu; nếu PO đồng ý, tôi thử tải và ghi tiếp vào file này.
2. **Hỏi người phụ trách pháp chế / văn thư của tổ chức** (A-036 đã yêu cầu): ngoài việc Nghị định còn hiệu lực, còn là **phạm vi áp dụng** với tổ chức của dự án (bắt buộc hay tham chiếu).
3. **Văn bản liên quan lĩnh vực văn thư/lưu trữ ban hành sau 2020** có thể làm đổi cách đọc Nghị định mà không "sửa đổi" nó theo nghĩa pháp lý; nằm ngoài câu hỏi này, chưa kiểm.
