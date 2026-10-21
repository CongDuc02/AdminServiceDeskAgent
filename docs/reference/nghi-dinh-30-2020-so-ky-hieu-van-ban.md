# Nghị định 30/2020/NĐ-CP — số, ký hiệu, đánh lại số mỗi năm, số nhỏ hơn 10, chữ viết tắt tên loại (cho M1.2)

- **Câu hỏi của PO (2026-10-21):** định dạng số của giấy xác nhận công tác `Số: {seq}/GXN-{VIẾT_TẮT}` — kiểm từ văn bản gốc, Phụ lục I: dãy số có đánh lại mỗi năm không; số < 10 có thêm số 0 không; và ghi rõ "GXN" không có trong Phụ lục III.
- **Nguồn:** PDF Công báo số 283 + 284, ngày 17-3-2020, 82 trang, có lớp chữ — `https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2020/3/30858/30246-1-2020283-28430-2020-nd-cp.pdf`, **lấy bằng `curl` ngày 2026-10-21**, sha256 `698e45e0aae921a20c0e31ffa87c50fd0324f640e70a6eca8d49e4f51045c7bb` (trùng bản đã ghi ở `nghi-dinh-30-2020-phong-chu-va-pham-vi.md`). File PDF không vào repo.
- **Cách trích:** `pypdf` 4.3.1 đọc lớp chữ (`pdftotext` làm rơi dấu tiếng Việt nên không dùng). Lớp chữ có khoảng trắng thừa giữa các chữ ("v ăn bản"); các trích dẫn dưới đây **gộp khoảng trắng thừa, không đổi chữ nào**. Số trang là số in trên trang Công báo.
- **Không phải kết luận pháp lý.** Phạm vi áp dụng với tổ chức của dự án (Điều 2: cơ quan, tổ chức nhà nước và doanh nghiệp nhà nước) xem `nghi-dinh-30-2020-phong-chu-va-pham-vi.md`; quyết định của PO 2026-10-21: tổ chức là doanh nghiệp tư nhân nên Nghị định là **chuẩn tham chiếu**, không phải ràng buộc bắt buộc (A-036).

## 1. Đánh lại số mỗi năm — Điều 15 khoản 1 (Công báo trang 9)

> **Điều 15. Cấp số, thời gian ban hành văn bản**
> 1. Số và thời gian ban hành văn bản được lấy theo thứ tự và trình tự thời gian ban hành văn bản của cơ quan, tổ chức trong năm (bắt đầu liên tiếp từ số 01 vào ngày 01 tháng 01 và kết thúc vào ngày 31 tháng 12 hàng năm). Số và ký hiệu văn bản của cơ quan, tổ chức là duy nhất trong một năm, thống nhất giữa văn bản giấy và văn bản điện tử.

→ Dãy số **bắt đầu lại từ 01 mỗi năm**. Tính duy nhất được nêu **theo năm** ("duy nhất trong một năm"), không phải duy nhất mãi mãi.

## 2. Số, ký hiệu — Phụ lục I, Phần I, khoản 3 "Số, ký hiệu của văn bản" (Công báo trang 23–24)

> 3. Số, ký hiệu của văn bản
> a) Số của văn bản là số thứ tự văn bản do cơ quan, tổ chức ban hành trong một năm được đăng ký tại Văn thư cơ quan theo quy định. Số của văn bản được ghi bằng chữ số Ả Rập.
> […]
> b) Ký hiệu của văn bản
> Ký hiệu của văn bản bao gồm chữ viết tắt tên loại văn bản và chữ viết tắt tên cơ quan, tổ chức hoặc chức danh nhà nước có thẩm quyền ban hành văn bản. Đối với công văn, ký hiệu bao gồm chữ viết tắt tên cơ quan, tổ chức hoặc chức danh nhà nước ban hành công văn và chữ viết tắt tên đơn vị soạn thảo hoặc lĩnh vực được giải quyết.
> Chữ viết tắt tên cơ quan, tổ chức và các đơn vị trong mỗi cơ quan, tổ chức hoặc lĩnh vực do người đứng đầu cơ quan, tổ chức quy định cụ thể, bảo đảm ngắn gọn, dễ hiểu.
> c) Số, ký hiệu của văn bản được đặt canh giữa dưới tên cơ quan, tổ chức ban hành văn bản. Từ "Số" được trình bày bằng chữ in thường, cỡ chữ 13, kiểu chữ đứng; sau từ "Số" có dấu hai chấm (:); **với những số nhỏ hơn 10 phải ghi thêm số 0 phía trước.** Ký hiệu của văn bản được trình bày bằng chữ in hoa, cỡ chữ 13, kiểu chữ đứng. **Giữa số và ký hiệu văn bản có dấu gạch chéo (/), giữa các nhóm chữ viết tắt trong ký hiệu văn bản có dấu gạch nối (-), không cách chữ.**

→ **Số nhỏ hơn 10 có thêm số 0 phía trước** (tức `01`…`09`; trong cấu hình là `seq_min_digits = 2`). Ký hiệu = chữ viết tắt **tên loại văn bản** + chữ viết tắt **tên cơ quan, tổ chức**; chữ viết tắt tên cơ quan, tổ chức do **người đứng đầu cơ quan, tổ chức quy định** — đây là chỗ tổ chức tự đặt `{VIẾT_TẮT}`. Ký hiệu **in hoa**; `/` giữa số và ký hiệu, `-` giữa các nhóm chữ viết tắt, không cách chữ. Khuôn `Số: {seq}/GXN-{VIẾT_TẮT}` của PO khớp các quy tắc dấu này.

## 3. Bảng chữ viết tắt tên loại — Phụ lục III, mục I (Công báo trang 46–47)

> **Phụ lục III — BẢNG CHỮ VIẾT TẮT TÊN LOẠI, MẪU TRÌNH BÀY VĂN BẢN HÀNH CHÍNH VÀ BẢN SAO VĂN BẢN**
> I. BẢNG CHỮ VIẾT TẮT TÊN LOẠI VĂN BẢN HÀNH CHÍNH VÀ BẢN SAO VĂN BẢN
> STT · Tên loại văn bản hành chính · Chữ viết tắt
> […] 21. Giấy ủy quyền GUQ · 22. Giấy mời GM · **23. Giấy giới thiệu GGT** · 24. Giấy nghỉ phép GNP · 25. Phiếu gửi PG · 26. Phiếu chuyển PC · 27. Phiếu báo PB
> Bản sao văn bản: 1. Bản sao y SY · 2. Bản trích sao TrS · 3. Bản sao lục SL

Bảng có **27 loại văn bản hành chính** và 3 loại bản sao. Tìm trong toàn văn bản Công báo: **không có dòng "Giấy xác nhận" và không có chữ viết tắt "GXN"** (tìm chuỗi "GXN" và "Giấy xác nhận": không có kết quả).

→ **`GXN` không có trong Phụ lục III của Nghị định 30/2020/NĐ-CP — là ký hiệu loại văn bản do công ty tự đặt.** Ngược lại Giấy giới thiệu có `GGT` ở bảng này (dùng cho loại `INTRODUCTION_LETTER` về sau).

## 4. Điều dẫn tới thiết kế (không phải điều của Nghị định)

- Khuôn của PO **không có năm** (`{seq}/GXN-{VIẾT_TẮT}`), nhất quán với Nghị định (số đánh lại mỗi năm, "duy nhất trong một năm"). Nhưng ràng buộc hiện tại của schema `uq_register_entry_number` đòi chuỗi số **duy nhất trong (sổ, dải) qua mọi năm** (mục 4.3 của `04-data.md`): sang năm sau số `01/GXN-…` đầu tiên trùng chuỗi năm trước → giao dịch cấp số hỏng (`NUMBER_FORMAT_COLLISION`). Xem `proposals/ac-1-1-dau-vao-cua-po.md` mục A2 — cần PO quyết trước khi dùng khuôn này.
