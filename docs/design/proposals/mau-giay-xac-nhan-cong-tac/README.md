# Đề xuất — mẫu `tpl_work_confirmation.docx` mới (M1.1) và cơ chế biến thể `contract_type` / "đã nghỉ việc"

**Trạng thái:** bản NHÁP để PO duyệt · **Ngày:** 2026-10-21 · **Căn cứ:** quyết định của PO 2026-10-21 (phiếu `.doc` là sai loại — dựng mẫu mới theo thể thức Phụ lục I Nghị định 30/2020/NĐ-CP); mốc M1.1 của `12-roadmap.md`; `proposals/ac-1-1-dau-vao-cua-po.md` mục E.

**Không đổi gì trong mã.** Mục 4 là **đề xuất** thay đổi ngữ nghĩa dựng bảng giá trị (`render_values`) — theo luật "hỏi trước" chờ PO duyệt, chưa làm. Mẫu này **chưa tải được** vào hệ thống thật cho tới khi mục 4 được duyệt (biến `contract_type` kiểu `ENUM` hiện ra `VARIABLE_MISSING`).

## 1. Các file

| File | Là gì |
|---|---|
| `tpl_work_confirmation.docx` | Mẫu nháp. Họ font khai trong file: **chỉ Times New Roman** (kiểm bằng `declared_families` của chính `tool_layer/rendering/fonts.py`) — nằm trong bộ cổng 1.6, không Webdings/Arial. Tên công ty và địa danh là **giữ chỗ trong ngoặc vuông** — PO điền |
| `xem-truoc-du-lieu-gia.pdf` | Ba trang xem trước, **dữ liệu giả có nhãn "(GIẢ)"**, đi đúng đường của `docx_render` (`fill_docx` kiểm biến + watermark `NON_PRODUCTION`, rồi LibreOffice): (1) `INDEFINITE`, đang làm; (2) `PROBATION`, đang làm; (3) `FIXED_TERM`, đã nghỉ việc |
| `tools/template-build/build_work_confirmation.py` | Công cụ dựng cả hai file trên. Chạy trong image `test`; PO điền `--company-name`, `--place` rồi dựng lại |

## 2. Đối chiếu thể thức — Phụ lục I, Nghị định 30/2020/NĐ-CP

Nguồn: bản Công báo số 283 + 284 đã lưu ở `docs/reference/nghi-dinh-30-2020-phong-chu-va-pham-vi.md` (sha256 `698e45e0…`). Tôi tải lại ngày 2026-10-21, sha256 khớp, và đọc lớp chữ của Phụ lục I Phần I mục I–II và bảng Phần V. Không trích từ trí nhớ.

| Thành phần (ô theo Mục IV) | Quy định (nguyên văn, đã gộp khoảng trắng thừa) | Mẫu làm gì |
|---|---|---|
| Khổ giấy, lề | "Khổ A4 (210 mm x 297 mm)"; "Cách mép trên và mép dưới 20 - 25 mm, cách mép trái 30 - 35 mm, cách mép phải 15 - 20 mm" | A4; trên 20, dưới 20, trái 30, phải 15 mm |
| Phông | "Times New Roman, bộ mã ký tự Unicode … màu đen" | Times New Roman, màu đen; PDF nhúng Liberation Serif (ADR-036) |
| Quốc hiệu (ô 1) | in hoa, cỡ 12–13, đứng, đậm, "ở phía trên cùng, bên phải trang đầu" | in hoa đậm cỡ 13, bên phải |
| Tiêu ngữ (ô 1) | in thường, 13–14, đứng, đậm, canh giữa dưới Quốc hiệu; chữ đầu mỗi cụm viết hoa, "có gạch nối (-), có cách chữ"; "phía dưới có đường kẻ ngang, nét liền, có độ dài bằng độ dài của dòng chữ" | cỡ 14 đậm, gạch chân đúng độ dài dòng chữ |
| Tên tổ chức (ô 2) | in hoa, 12–13, đứng, đậm; đường kẻ dài "từ 1/3 đến 1/2 độ dài của dòng chữ" | in hoa đậm cỡ 13; đường kẻ ≈ 0,42 độ dài dòng chữ (ước theo số ký tự — PO duyệt bằng mắt) |
| Số, ký hiệu (ô 3) | "Số" in thường cỡ 13, đứng, sau có dấu hai chấm; số < 10 thêm số 0; `/` giữa số và ký hiệu, `-` giữa các nhóm chữ viết tắt | `Số: {{ document_number }}`, cỡ 13; chuỗi số do sổ cấp (`01/GXN-ABC`) |
| Địa danh, ngày (ô 4) | in thường, 13–14, **nghiêng**; sau địa danh có dấu phẩy; ngày nhỏ hơn 10 và tháng 1, 2 thêm số 0 | nghiêng cỡ 14: `[Địa danh], ngày 21 tháng 10 năm 2026` |
| Tên loại (ô 5a) | in hoa, 13–14, đứng, đậm, canh giữa | `GIẤY XÁC NHẬN CÔNG TÁC` cỡ 14 |
| Nội dung (ô 6) | in thường, canh đều hai lề, 13–14; lùi đầu dòng 1 cm hoặc 1,27 cm; giữa đoạn ≥ 6 pt; dòng từ đơn tới 1,5 | cỡ 14; lùi 1,27 cm; dãn dòng 1,3; giữa đoạn 6 pt |
| Kính gửi (ô 9a) | in thường 13–14, đứng, sau "Kính gửi" có dấu hai chấm | `Kính gửi: {{ recipient_org }}` |
| Nơi nhận (ô 9b) | "Nơi nhận" cỡ 12 nghiêng đậm, sát lề trái; danh sách cỡ 11, gạch đầu dòng, cuối dòng `;`; dòng cuối "Lưu: VT, …" kết thúc bằng `.` | đúng cỡ và kiểu; `- Như trên;` rồi `- Lưu: VT.` (với công văn "Như trên" là phần thứ hai của nơi nhận) |
| Số trang | "không hiển thị số trang thứ nhất" | một trang, không số trang |
| Cỡ chữ nhất quán | chú thích 1 của Phần V: "Quốc hiệu cỡ chữ 13, Tiêu ngữ cỡ chữ 14, địa danh … cỡ chữ 14" (hoặc 12/13/13) | dùng bộ 13/14/14 |

**Chưa đối chiếu và nói thẳng:** (a) chữ ký và dấu — Phụ lục I mục 7–8 nói về quyền hạn, chức vụ, họ tên và vị trí con dấu; mẫu chừa chỗ ký/đóng dấu và in một dòng `họ tên, chức danh` (xem câu hỏi 3). (b) Tôi không kiểm hình học tuyệt đối trên bản in (vị trí ô theo hình ở Phần I mục IV) — xem PDF bằng mắt. (c) Nghị định áp dụng thế nào với công ty tư nhân là A-036 (PO: chuẩn tham chiếu, không chặn).

## 3. Biến của mẫu

| Biến | Loại (`template_variable.kind`) | Nguồn | Ghi chú |
|---|---|---|---|
| `full_name`, `department_name`, `job_title`, `recipient_org` | `DIRECT_SLOT` | slot cùng tên | như mẫu giả đang chạy |
| `employment_start_date`, `employment_end_date` | `DIRECT_SLOT` | slot cùng tên; `DATE` → `dd/mm/yyyy` | `employment_end_date` **không bắt buộc** (`○`): vắng thì cần giá trị rỗng, hiện ra `VARIABLE_MISSING` (mục 4) |
| `contract_type` | `DIRECT_SLOT`, slot kiểu **`ENUM`** | slot `contract_type` | **chưa hỗ trợ trong mã** (mục 4) |
| `purpose_statement` | `FREE_CONTENT` | P4, từ slot `purpose` | như mẫu giả |
| `document_number`, `issued_date`, `signer_user_id` | `SYSTEM`, điền sau duyệt | `finalize_issue` | đúng ba tên mã đã khoá (`domain/final_values.py`) |

**Ngày dạng "ngày 21 tháng 10 năm 2026".** Mã cấp `issued_date` dạng `dd/mm/yyyy` (A-098), còn Nghị định đòi viết đủ ngày, tháng, năm. Mẫu **tách bằng cú pháp cắt chuỗi của Jinja** (`issued_date[0:2]`, `[3:5]`, `[6:10]`) khi giá trị đúng dạng `dd/mm/yyyy`; bản nháp mang dấu giữ chỗ `[Ngày … — cấp khi phát hành]` thì hiện nguyên dấu giữ chỗ. Không đổi mã, nhưng là chỗ dựa vào dạng chuỗi — nếu PO muốn bỏ, hướng thay là thêm ba biến `SYSTEM` riêng (đổi `final_values`, hỏi trước).

## 4. ĐỀ XUẤT (chưa làm) — cơ chế biến thể câu chữ

**Vấn đề (đã nêu từ B9a, O1-20):** `render_values.build_values` chỉ hỗ trợ `DIRECT_SLOT` kiểu `STRING`/`TEXT`/`INT`/`DATE`; `ENUM` và slot không bắt buộc vắng giá trị ra `VARIABLE_MISSING`. Hai biến thể của mẫu — theo `contract_type`, và "đã từng công tác" — không có cơ chế trong mã.

**Đề xuất (mặc định):** giữ câu chữ trong **mẫu** (PO duyệt như đang duyệt văn bản), mã chỉ cung cấp giá trị tất định:

1. **`ENUM` ở `DIRECT_SLOT` → bảng giá trị chứa đúng MÃ** (`PROBATION` / `FIXED_TERM` / `INDEFINITE`), đã kiểm thuộc tập giá trị của slot. Mẫu chọn câu chữ bằng điều kiện Jinja (`{% if contract_type == 'PROBATION' %}…`) — như bản nháp. Chữ tiếng Việt cho từng mã không nằm trong mã hay DB. Mã lạ → `VARIABLE_MISSING`.
2. **Slot không bắt buộc (`is_required = false`, cột `○`) mà vắng giá trị ở biến `DIRECT_SLOT` → chuỗi rỗng**, không phải `VARIABLE_MISSING`. Dùng cột sẵn có `slot_definition.is_required`: **không migration**.
3. **"Đã từng công tác" = `employment_end_date` có giá trị.** Chỉ dựa vào slot nên **ổn định theo thời gian** — bản `FINAL` và bản đã duyệt (`approved_content_hash`, INV-01) cho cùng bảng giá trị; không dùng "hôm nay" (một biến dẫn xuất theo ngày làm hash đổi giữa lúc duyệt và lúc phát hành). Ngày nghỉ **ở tương lai** thì thể thức này sai: cần luật kiểm lúc xác nhận slot ("ngày kết thúc không ở tương lai", hoặc đẩy `NEEDS_INFO` theo EC-WC-02) — **hỏi PO**, mặc định thêm luật vào bộ luật kiểm sẵn có nếu bộ từ vựng cho phép.
4. **Kiểm độ phủ của mẫu bằng test, không bằng parser Jinja:** test render mẫu với từng mã `ENUM` và kiểm có đúng một mệnh đề loại hợp đồng, không rỗng — để mã thứ tư thêm vào sau không lọt thành văn bản thiếu câu.

**Chạm vào:** `render_values.py` (hai nhánh trên), `03-agents.md` (mục `render_values`/Tool Registry), `00-domain.md` mục 3.2 (một dòng), `A-098`/`O1-20`; test `test_render_values`. **Không** chạm `openapi.yaml`, schema, `docx_fill`, `final_values`. Đây là thay đổi ngữ nghĩa dựng bảng giá trị → **chờ PO duyệt**.

**Phương án khác đã cân:** (B) bảng "mã → chữ" trong `template_variable` (thêm cột/bảng, migration, và chữ pháp lý nằm trong DB khó duyệt hơn trong mẫu); (C) ba mẫu riêng cho ba loại hợp đồng (nhân đôi phần khung, lệch thể thức giữa các mẫu). Chọn mặc định ở trên vì không migration và giữ văn bản ở một chỗ duyệt được.

## 5. Loại hợp đồng — kiểm lại từ văn bản gốc

Bản gốc: `docs/reference/bo-luat-lao-dong-2019-loai-hop-dong-thu-viec.md` (Bộ luật số 45/2019/QH14, Công báo 993 + 994, sha256 `3c865f3d…`).

- **Điều 20 khoản 1 chỉ có hai loại hợp đồng lao động:** không xác định thời hạn, và xác định thời hạn "không quá 36 tháng". Hợp đồng 1, 2 hay 3 năm đều là **một loại** — nên `FIXED_TERM` không cần tách theo năm, và mẫu không in thời hạn (không có slot thời hạn).
- **Thử việc không phải "loại" của Điều 20 khoản 1**; Điều 24 khoản 1 cho hai cách (thỏa thuận ghi trong hợp đồng lao động, hoặc hợp đồng thử việc). Nhận định của PO ("hai loại HĐ + thử việc") **khớp**. `PROBATION` vẫn là giá trị hợp lệ của `contract_type` trong hồ sơ nhân sự; câu chữ của mẫu cho `PROBATION` là "trong thời gian thử việc", **không** gọi là loại hợp đồng, và không hàm ý nhân viên chính thức (EC-WC-01).
- `ck_employee_contract_type` (`PROBATION`, `FIXED_TERM`, `INDEFINITE`) **giữ nguyên — không migration.** Dòng "Khác (ghi rõ)" của phiếu cũ không có chỗ tương ứng trong văn bản.
- Tôi **chưa** kiểm hiệu lực hay sửa đổi của Bộ luật sau 2019 (ghi trong tài liệu tham chiếu).

## 6. Câu hỏi cho PO (mặc định kèm theo)

1. **Tên công ty và địa danh** (chữ cố định): giá trị thật? Mặc định: giữ chỗ trong ngoặc, PO điền rồi tôi dựng lại. `ABC` trong `Số: …/GXN-ABC` là ký hiệu thật hay giữ chỗ?
2. **Chủ ngữ "Công ty xác nhận:"** — dùng "Công ty" chung (mặc định) hay tên đầy đủ?
3. **Khối ký.** Mã hiện in **một dòng** `họ tên, chức danh` (A-100). Nghị định đặt "quyền hạn, chức vụ" (in hoa, đậm) **phía trên** chỗ ký và họ tên **phía dưới**. Mặc định: giữ một dòng dưới chỗ ký, thêm chú thích nghiêng "(Ký, ghi rõ họ tên, chức danh và đóng dấu)". Muốn đúng bố cục Nghị định thì tách hai biến `SYSTEM` (đổi `final_values` — hỏi trước, sẽ có đề xuất riêng).
4. **`Lưu: VT.`** — Nghị định: "Lưu: VT, chữ viết tắt tên đơn vị soạn thảo và số lượng bản lưu". Đơn vị soạn thảo (ví dụ phòng Hành chính) viết tắt là gì, và có ghi số bản lưu không?
5. **Không có trích yếu** dưới tên loại. Mặc định: bỏ (giấy xác nhận không cần "Về việc …"). Muốn có không?
6. **Không in** `date_of_birth`, `national_id`, `copies_count`, `language` (slot `○` hoặc `[Could]`). Có thể điều kiện hoá sau; cho biết cái nào nhất định phải in.
7. **Câu chữ ba mệnh đề** (duyệt từng chữ): đang làm — "Hiện đang làm việc tại Công ty từ ngày …"; đã nghỉ — "Đã làm việc tại Công ty từ ngày … đến ngày …"; kèm "theo hợp đồng lao động không xác định thời hạn" / "… xác định thời hạn" / "trong thời gian thử việc".
8. **Duyệt mục 4** (cơ chế `ENUM`, slot không bắt buộc rỗng, "đã nghỉ" = có `employment_end_date`) và luật cấm ngày nghỉ ở tương lai.
9. **Cách đánh dấu số dải `TRIAL`** — mặc định `{seq}/GXN-{symbol}-TN` (không bao giờ trùng dạng số thật, vẫn trong khuôn ký hiệu của Nghị định: chữ in hoa, nối bằng `-`).

## Open Questions

Chín câu ở mục 6. Hai điều **chưa đối chiếu** ở mục 2 (hình học tuyệt đối; chữ ký/dấu) và việc kiểm hiệu lực Bộ luật Lao động sau 2019 vẫn mở.
