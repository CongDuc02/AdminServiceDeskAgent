# ADR-043 — Chuỗi số văn bản duy nhất theo kỳ, không theo cả đời sổ (migration `0015`)

**Trạng thái:** Accepted · **Duyệt:** PO, 2026-10-21 (chọn hướng (a) cho xung đột khuôn số; `proposals/ac-1-1-dau-vao-cua-po.md` mục D2) · **Ngày:** 2026-10-21 · **Quyết định tại:** BUILD MODE, lát `build/m12-khuon-so` · **Sửa:** một ý của ADR-011 (mục Decision, gạch đầu dòng "Định dạng") và `uq_register_entry_number` ở `0001_initial.sql`; phần còn lại của ADR-011 giữ nguyên.

---

## Context

PO chọn khuôn số của giấy xác nhận công tác (mốc M1.2): `Số: {seq}/GXN-{VIẾT_TẮT}` — **không có năm** trong chuỗi số. Nghị định 30/2020/NĐ-CP đòi đánh lại từ 01 mỗi năm và coi số là duy nhất **trong một năm** (Điều 15 khoản 1; trích nguyên văn ở `docs/reference/nghi-dinh-30-2020-so-ky-hieu-van-ban.md`).

Schema hiện hành (`0001`) có `uq_register_entry_number UNIQUE (document_register_id, series, formatted_number)`: chuỗi số duy nhất trong (sổ, dải) **qua mọi năm**. ADR-011 dùng nó làm lưới an toàn cho mẫu cấu hình sai — sổ `YEARLY` mà mẫu thiếu `{year}`. Với khuôn của PO, ngày đầu năm sau `seq = 1` cho chuỗi `01/GXN-…` đã có ở năm trước: `UniqueViolation`, `finalize_issue` hỏng (`NUMBER_FORMAT_COLLISION`, vĩnh viễn) ngay lần phát hành đầu tiên của năm. Hai thứ không cùng đúng: khuôn của PO (và Nghị định) cho phép chuỗi số lặp ở năm khác, lưới an toàn thì cấm.

## Options

- **(a) Đổi ràng buộc thành duy nhất theo kỳ:** `UNIQUE (document_register_id, series, period_key, formatted_number)`. Khớp "duy nhất trong một năm".
- **(b) Đưa năm vào ký hiệu** (`{seq}/{year}/GXN-…`) — không migration, nhưng khác khuôn PO đã chọn.
- **(c) Bỏ hẳn ràng buộc chuỗi số**, chỉ giữ `uq_register_entry_seq` — loại: mất lưới an toàn cho mẫu cấu hình sai trong cùng kỳ.

## Decision

**(a).** Migration `backend/migrations/schema/0015_register_entry_number_per_period.sql`: bỏ `uq_register_entry_number`, thêm lại **cùng tên** với `period_key` trong khoá. Cùng tên để mã và test bắt `UniqueViolation` theo `constraint_name` không phải sửa.

Chuỗi số vẫn duy nhất trong (sổ, dải, **kỳ**): hai số khác `seq` trong cùng kỳ mà ra cùng chuỗi — ví dụ đổi mẫu giữa kỳ làm hai `seq` định dạng ra cùng chữ — vẫn làm giao dịch cấp số hỏng, `seq` không bị tiêu. Sổ `NEVER` có `period_key = 'ALL'` nên không đổi hành vi. Mã `document_number_assign` **không đổi**; chỉ đổi lời giải thích và test.

**Hệ quả với phần "mẫu thiếu `{year}`":** ở sổ `YEARLY` đây không còn là cấu hình sai — là khuôn hợp lệ (ND30). Test `test_mau_thieu_year_o_so_yearly_hong_thay_vi_phat_so_trung` đổi nghĩa: nay khẳng định số lặp ở năm khác **được**, còn trùng trong cùng kỳ vẫn **hỏng**.

## Consequences

**Tương thích ngược (quy trình migration cố định, mục Migration của `11-ops.md`):**
- Mọi dòng thoả ràng buộc cũ đều thoả ràng buộc mới (khoá rộng hơn nên tập thoả lớn hơn) — `ADD CONSTRAINT` không thể trượt trên dữ liệu cũ.
- Code đang live (B9b2, B10a) chạy nguyên trên schema mới: nó chỉ đọc `constraint_name = 'uq_register_entry_number'` và tên không đổi; hành vi khác duy nhất là chuỗi số lặp ở năm khác không còn bị chặn.
- Đây là **nới ràng buộc** bằng cách bỏ và thêm lại cùng tên trong một giao dịch, không phải xoá cột hay đổi tên (không có cột nào đổi). Quy trình nói "không xoá" nhằm cột/bảng mà code cũ dùng; ghi rõ ở đây để PO thấy chủ ý.
- **Quay lui** (`DROP` rồi `ADD` lại khoá cũ) chỉ làm được khi chưa có hai dòng cùng chuỗi số khác kỳ; sau ngày đầu năm đầu tiên dùng khuôn không có năm thì không quay lui được.

**Phải chấp nhận:**
- `document_number` có thể giống nhau giữa hai năm. Số vẫn phân biệt được bằng `issued_date` in cùng văn bản và bằng `period_key` ở sổ. Mọi chỗ tra số theo **chuỗi** mà không kèm kỳ có thể trả hai dòng; mã hiện tại tra theo `document_id` và `entry_id`, không theo chuỗi.
- **Đối soát sau khôi phục** (mục Khôi phục của `11-ops.md`, 5.2(b)/(c)) dùng `x-bo19-document-number` — chuỗi **không có năm** — để tìm "số lớn nhất dùng thật" rồi đẩy `next_seq`. Với khuôn không có năm, hai object của hai năm cùng mang `01/GXN-…`. Cần quyết (không làm trong lát này): thêm ngày phát hành vào metadata, hay đối soát theo `document_id` của khoá object (`renders/{document_id}/…`) — mục 4 của `proposals/ac-1-1-dau-vao-cua-po.md`, câu hỏi mở.

**Điều kiện đảo ngược:** nếu tổ chức sau này gộp nhiều năm vào một dãy (đổi sang `NEVER`) thì ràng buộc này vẫn đúng — không cần đảo.

## Rejected alternatives

- **(b) Năm trong ký hiệu:** khác khuôn PO đã chọn và khác ví dụ của Nghị định (số và ký hiệu viết `15/QĐ-BNV`, không năm). Giữ lại như phương án dự phòng nếu pháp chế đòi.
- **(c) Bỏ ràng buộc chuỗi số:** xem trên.
- **Giữ ràng buộc cũ và bắt người vận hành thêm `{year}`:** trái khuôn đã chọn; đẩy lỗi cấu hình sang ngày 01/01.
