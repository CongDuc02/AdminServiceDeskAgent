# Đề xuất — dữ liệu cần lấy từ tổ chức cho A-058, A-009, A-013, A-071, và cổng nào dời được vào giữa Sprint 1

**Trạng thái:** ✅ Đã áp — 2026-09-27, PO đồng ý · **Sửa khi áp:** bộ font đi cùng giấy phép ở cổng 1.6 trước Sprint 1, không đi theo mẫu ở mốc giữa Sprint 1 — không xét giấy phép được khi chưa biết font nào. Mục 2 dưới đây giữ nguyên bản đề xuất; bản đã áp ở mục Mốc giữa Sprint 1 của `12-roadmap.md` · **Ngày:** 2026-09-27 · **Người đề xuất:** người triển khai · **Nguồn:** cổng 1.6–1.8 của `12-roadmap.md`, mục Rủi ro chính của Sprint 1 (R1-4), A-058, A-009, A-013, A-071, mục Slot schema và mục Cấp số văn bản của `00-domain.md`, `contracts/schema.sql` (`employee`, `document_register_format`, `template_version`), ADR-015

---

## 1. Checklist — PO lấy từ tổ chức

Mỗi mục ghi **dạng** cần nhận. File chứa dữ liệu thật của nhân viên thì **che hết dữ liệu cá nhân trước khi đưa** — thiết kế chỉ cần cấu trúc và câu chữ.

### 1.1 A-058 — mẫu `.docx` và font (cổng 1.6)

- [ ] **File `.docx` gốc** của mẫu giấy xác nhận công tác tổ chức đang dùng. Phải là file Word soạn được — không nhận PDF, ảnh chụp hay bản scan, vì template được điền bằng biến trong chính file này (ADR-001).
- [ ] **Ít nhất một bản đã phát hành thật** của cùng loại giấy, đã che dữ liệu cá nhân. Dùng để đối chiếu mẫu với văn bản tổ chức thật sự phát hành — cách xác minh thay thế của A-018.
- [ ] **Các biến thể câu chữ** mà mẫu phải có, mỗi biến thể một đoạn văn nguyên văn:
  - theo `contract_type` — ví dụ câu chữ cho người thử việc (EC-WC-01);
  - cho người **đã nghỉ việc** — thể thức "đã từng công tác" (EC-WC-02).
- [ ] **Khối ký**, nguyên văn: chức danh người ký, và cách ghi khi ký thay hay thừa lệnh nếu tổ chức dùng.
- [ ] **Danh sách font** mà mẫu dùng, do tổ chức xác nhận. Người triển khai sẽ tự trích font khai trong file để đối chiếu — cách liệt kê đầy đủ theo OOXML vẫn `[CẦN XÁC MINH]` (ADR-015). Tổ chức xác nhận để bắt font mà file khai thiếu.
- [ ] **Giấy phép của từng font**: văn bản giấy phép gốc — file license hay điều khoản — kèm nguồn tải chính thức. Câu hỏi cần trả lời: **có được đóng font vào container image của dự án và chạy trên Render không**. Không đoán, không ghi tên giấy phép từ trí nhớ.
- [ ] Nếu có font không được phân phối: **quyết định có tên của PO** về họ font thay thế tương thích số đo (A-058). Thay thế tương thích số đo không phải là giống nhau.
- [ ] Bản gốc **Nghị định 30/2020/NĐ-CP** đặt vào `docs/reference/`. Không bắt buộc cho cổng, nhưng thiếu nó thì mọi chỗ nói về thể thức vẫn `[CẦN XÁC MINH]`.

### 1.2 A-009 — số và ký hiệu văn bản (cổng 1.7)

Cột đích: `document_register` và `document_register_format` trong `contracts/schema.sql`. Mẫu định dạng dùng ba chỗ giữ `{seq}`, `{year}`, `{symbol}` (mục Sổ số văn bản của `04-data.md`).

- [ ] **Ít nhất ba số văn bản thật** đã cấp cho giấy xác nhận công tác, nguyên văn cả phần số lẫn ký hiệu. Nếu được, lấy số của hai năm khác nhau, để thấy cách reset.
- [ ] **Ký hiệu văn bản** (`symbol`) — nguyên văn, gồm phần viết tắt tên cơ quan hay đơn vị.
- [ ] **Số có đệm số 0 ở đầu không**, đệm tới mấy chữ số (`seq_min_digits`).
- [ ] **Chu kỳ đánh số**: reset đầu năm, hay không bao giờ reset (`reset_policy`: `YEARLY` · `NEVER`). A-009 đang giả định theo năm.
- [ ] **Một sổ hay nhiều sổ**: giấy xác nhận công tác và giấy giới thiệu dùng chung một dãy số, hay mỗi loại một dãy? Thiết kế giả định một dãy duy nhất (A-001).
- [ ] **Dạng số cho dải `TRIAL`**: PO chọn một cách đánh dấu để số thử nghiệm không bao giờ trùng dạng số thật — ví dụ một hậu tố riêng. Đây là quyết định của PO, không phải dữ liệu của tổ chức.
- [ ] **Số cuối cùng đã cấp trong năm hiện hành.** Không cần cho Sprint 1. Cần trước khi chuyển `PRODUCTION`, để dải `OFFICIAL` nối tiếp đúng.

### 1.3 A-013 — hồ sơ nhân viên (cổng 1.8)

Cột đích: bảng `employee` trong `contracts/schema.sql`.

- [ ] **Danh sách giá trị** của trường loại hợp đồng hay tình trạng công tác trong hồ sơ nhân sự hiện có, nguyên văn. Và **ánh xạ** từng giá trị sang `PROBATION` · `FIXED_TERM` · `INDEFINITE`. Nếu có loại không ánh xạ được — ví dụ cộng tác viên, thời vụ — ghi rõ, vì `ck_employee_contract_type` sẽ phải đổi bằng migration.
- [ ] **Hồ sơ có số căn cước không** (`national_id`), và dạng của nó.
- [ ] **File CSV mẫu** đúng cấu trúc tổ chức xuất ra được: dòng tiêu đề nguyên văn, **5 dòng dữ liệu giả** cùng cấu trúc.
  - Kèm: bảng mã ký tự (encoding), ký tự phân cách, định dạng ngày, cách ghi ô rỗng.
  - Kèm ánh xạ từng cột sang cột của `employee`: `employee_code`, `full_name`, `department_code`, `department_name`, `job_title`, `contract_type`, `employment_start_date`, `employment_end_date`, `date_of_birth`, `national_id`, `is_active`.
- [ ] **Ai xuất file, bao lâu một lần** — thành nhãn `source` của mỗi đợt import (D-002).

### 1.4 A-071 — nhịp sprint

- [ ] **Độ dài sprint**, tính bằng tuần.
- [ ] **Ngày bắt đầu Sprint 1.**
- [ ] **Năng lực:** số người triển khai, và số giờ mỗi tuần mỗi người dành cho dự án. Cộng ngày nghỉ đã biết trong Sprint 1–2.
- [ ] **Mốc cứng bên ngoài**, nếu có: ngày demo, ngày nghiệm thu, ngày UAT.
- [ ] **Ai dự grooming và review sprint** về phía tổ chức — người trả lời câu hỏi nghiệp vụ trong sprint.

## 2. Đánh giá — cổng nào dời được vào giữa Sprint 1

**Điểm xuất phát.** Trong bảng cổng trước Sprint 1 của `12-roadmap.md`, 1.6, 1.7 và 1.8 đã có cột Chặn là **"AC"**, không phải "Khởi động". Nghĩa là **chúng vốn không chặn 1.1**, cũng không chặn việc bắt đầu Sprint 1 — chỉ chặn nghiệm thu. Chỗ hở là bảng không nói **muộn nhất lúc nào trong Sprint 1**, cũng không nói **được dùng dữ liệu giả tới đâu**. R1-4 đã ghi rằng AC-1.1 không đạt được bằng mẫu `.docx` hay định dạng số giả. Đề xuất dưới đây giữ nguyên R1-4, và chỉ đặt mốc.

| Mục | Dữ liệu | Dùng lần đầu ở đâu trong Sprint 1 | Dữ liệu giả tạm được không | Đề xuất |
|---|---|---|---|---|
| A-058 (a) | Mẫu `.docx` thật, cả các biến thể câu chữ | Data migration nạp một phiên bản template `ACTIVE` — tầng Dữ liệu, rất sớm | **Được.** Một mẫu giữ chỗ do người triển khai dựng, đủ biến theo danh mục biến của `WORK_CONFIRMATION`. Nó phải qua đúng phép kiểm lúc tải lên như mẫu thật. Đổi sang mẫu thật là tải một **phiên bản mới** rồi kích hoạt — template đã có versioning, không đổi migration schema | **Mốc giữa Sprint 1** — muộn nhất trước S5 của Spike 1 **và** trước lần chạy AC-1.1, cái nào tới trước. S5 đã ghi "sau khi có mẫu và font (cổng 1.6)" |
| A-058 (b) | Danh sách font | Manifest `required_fonts` của phiên bản template; bước kiểm khởi động #7 của `worker` | Được — đi theo mẫu giữ chỗ | Cùng mốc với (a) |
| A-058 (c) | **Giấy phép font** | S5 đóng font vào image — việc của Sprint 1 | **Không — theo chỉ đạo của PO** | **Giữ nguyên là cổng trước Sprint 1.** S5 là lần đầu font vào image, và S5 thuộc Sprint 1. Local chạy native không đóng font vào đâu, nên track build không bị chặn trong lúc chờ |
| A-009 | Định dạng số và ký hiệu, cả dải `TRIAL` | Job `finalize_issue` — bước cuối của đường chính | **Được** tới trước AC-1.1: một dòng `document_register_format` dải `TRIAL` có nhãn giả. Bảng chỉ thêm, có `effective_from`, nên đổi sang định dạng thật là **thêm một dòng**, không sửa gì | **Mốc giữa Sprint 1** — trước lần chạy AC-1.1. Giữ R1-4 |
| A-013 (a) | Giá trị `contract_type` và ánh xạ | Data migration nạp `employee` giả; enum của slot; câu chữ biến thể của mẫu | Được — `employee` giả dùng ba giá trị đang có trong `CHECK` | **Mốc giữa Sprint 1**, cùng mốc với A-058 (a), vì câu chữ biến thể nằm trong mẫu. **Rủi ro nếu muộn:** giá trị thật khác ba giá trị hiện có thì cần migration đổi `ck_employee_contract_type` và sửa dữ liệu giả — rẻ ở Sprint 1, đắt hơn sau |
| A-013 (b) | Cột CSV | `employee_import` — F6, **Sprint 3** (AC-3.4). Sprint 1 nạp `employee` bằng data migration, không qua CSV | Không cần dữ liệu giả — Sprint 1 không dùng | **Dời sang cổng trước Sprint 3.** Không có lý do để chặn Sprint 1 |
| A-071 | Độ dài sprint, năng lực, ngày bắt đầu | Grooming Sprint 1 | **Không** — không có "năng lực giả" | **Giữ trước Sprint 1.** Ghi chú: A-071 có hạn "trước grooming Sprint 1" và được mục Open Questions của `12-roadmap.md` gọi là cổng, nhưng **không có dòng nào** trong bảng cổng trước Sprint 1. Đề xuất thêm một dòng |

**Tóm lại:**

- **Giữ trước Sprint 1:** A-058 (c) giấy phép font; A-071 — thêm thành một dòng cổng.
- **Thành mốc giữa Sprint 1, dữ liệu giả tới lúc đó:** A-058 (a)(b), A-009, A-013 (a).
- **Dời sang cổng trước Sprint 3:** A-013 (b), cột CSV.

## 3. Nếu PO duyệt — việc áp

- **`12-roadmap.md`, mục Cổng trước Sprint 1:**
  - thêm dòng A-071;
  - tách 1.6 thành 1.6 — mẫu và font, mốc giữa Sprint 1 — và một dòng mới cho giấy phép font, giữ trước Sprint 1;
  - 1.7 và 1.8 ghi mốc "giữa Sprint 1 — trước lần chạy AC-1.1";
  - thêm một bảng ngắn "Mốc giữa Sprint 1" nói rõ dữ liệu giả nào được dùng tới đó;
  - thêm một dòng cổng trước Sprint 3 cho cột CSV của A-013.
- **Dữ liệu giả có nhãn:** mẫu giữ chỗ, dòng `document_register_format` giả và `employee` giả đều mang dấu hiệu nhận ra được là giả, cùng luật "dữ liệu giả đánh dấu là giả" của AC-1.1.
- **`ASSUMPTIONS.md`:** hạn của A-058, A-009, A-013 sửa theo mốc mới.
- **`CHANGELOG.md`:** một mục.

## Open Questions

- Tách A-013 thành hai vế (giá trị `contract_type` và cột CSV) — giữ một dòng A-013 với hai hạn, hay mở một giả định mới cho cột CSV? Đề xuất: giữ một dòng, hai hạn, để khỏi thêm ID.
