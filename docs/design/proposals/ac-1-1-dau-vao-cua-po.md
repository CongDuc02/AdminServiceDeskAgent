# Đầu vào PO phải giao trước lần chạy AC-1.1

**Trạng thái:** danh sách để PO giao · **Ngày:** 2026-10-21 · **Căn cứ:** mốc M1.1, M1.2 và AC-1.1 của `12-roadmap.md`; `proposals/sprint1-org-data-checklist.md` (đã áp 2026-09-27) · **Cập nhật theo mã hiện có** (B9b2): các điều "mẫu phải có" dưới đây đối chiếu với `render_values`, `final_values`, `docx_render`, `issue_prepare` đang chạy, không chép lại từ thiết kế cũ.

**AC-1.1 là gì:** hành trình ở điều 1 của mục Definition of Done của `01-prd.md` chạy trọn cho `WORK_CONFIRMATION` trên local, **provider LLM thật (Groq)**, dữ liệu `employee` giả có nhãn. Sau B10a và B10b.

## A. Việc anh giao — không có thì AC-1.1 không đóng được bằng dữ liệu thật

### A1. M1.1 — mẫu `tpl_work_confirmation.docx` thật

Hiện chỉ có **mẫu giữ chỗ** do tôi dựng (`MẪU GIẢ — chỉ để thử`). Qua B9b2 nó đã chạy trọn đường phát hành, nhưng AC-1.1 đòi mẫu đúng thể thức của tổ chức. Anh giao:

1. **File `.docx` Word soạn được** của giấy xác nhận công tác tổ chức đang dùng — không PDF, ảnh hay bản quét (template được điền bằng biến ngay trong file, ADR-001).
2. **Ít nhất một bản đã phát hành thật**, che dữ liệu cá nhân — để đối chiếu mẫu với văn bản thật (A-018).
3. **Khối ký nguyên văn**: chức danh người ký, cách ghi ký thay / thừa lệnh nếu có.
4. **Các biến thể câu chữ**, mỗi biến thể một đoạn nguyên văn:
   - theo `contract_type` (thử việc — EC-WC-01; hợp đồng có thời hạn; không thời hạn);
   - người **đã nghỉ việc** — thể thức "đã từng công tác" (EC-WC-02, có mốc bắt đầu và kết thúc).
5. **Danh sách font** mẫu dùng, và xác nhận của anh rằng bộ này nằm trong bộ đã qua cổng 1.6 (Liberation Serif thay Times New Roman, ADR-036). Font ngoài bộ thì quay lại cổng 1.6 cho font đó.
6. **Giá trị `contract_type` thật của tổ chức** và ánh xạ sang `PROBATION` · `FIXED_TERM` · `INDEFINITE` (A-013 (a)). Có loại không ánh xạ được (cộng tác viên, thời vụ…) thì ghi rõ — `ck_employee_contract_type` sẽ phải đổi bằng migration.

**Mẫu phải có gì** (đối chiếu với mã đang chạy):

| Phần của mẫu | Yêu cầu | Ghi chú |
|---|---|---|
| Biến `DIRECT_SLOT` | `full_name`, `department_name`, `job_title`, `recipient_org` (và các slot anh muốn in) — mỗi biến trỏ một slot đã khai ở `WORK_CONFIRMATION` | Giá trị `HR_PROFILE` phải `CONFIRMED`, `USER_INPUT` phải `PROVIDED`/`CONFIRMED`; định dạng `STRING`/`TEXT`/`INT`/`DATE` (`dd/mm/yyyy`) |
| Biến `FREE_CONTENT` | `purpose_statement` (một câu hành chính ngắn, giọng bên phát hành), có `variable_guidance`, `max_length`, danh sách input tự khai | Chỉ biến này do LLM sinh; kiểm cấm cú pháp trường/lời thoại khung |
| Biến `SYSTEM` điền sau duyệt | đúng ba tên: `document_number`, `issued_date`, `signer_user_id` (in **họ tên, chức danh** người đã ký) | Tên khác → `finalize_issue` dừng (`RENDER_INPUT_INVALID`); đổi tên cần sửa `domain/final_values.py` |
| Khung cố định | Không được còn chuỗi dạng `[… — cấp khi phát hành]` trong khung | Bản `FINAL` thất bại (`PLACEHOLDER_REMAINS`) |
| Font | Mọi font file khai nằm trong `required_fonts` của manifest và có trong image | `TEMPLATE_FONTS_INVALID` lúc tải lên / kích hoạt |

**Một việc của tôi, cần anh biết trước:** mã hiện **chưa hỗ trợ biến kiểu `ENUM`** ở biến `DIRECT_SLOT` (`contract_type` là `ENUM`; A-098, O1-20 — "câu chữ theo loại hợp đồng là việc của đoạn điều kiện của mẫu thật"). Tức các biến thể theo `contract_type` và "đã nghỉ việc" **chưa có cơ chế trong mã**. Khi anh giao mẫu, tôi sẽ **đề xuất cách** (ví dụ biến dẫn xuất tất định do hệ thống tính từ slot và chọn đoạn câu chữ, hoặc điều kiện trong mẫu) và **báo trước để anh duyệt** — đây là thay đổi ngữ nghĩa dựng bảng giá trị và có thể chạm contract, nên theo luật "hỏi trước" (2026-10-21).

### A2. M1.2 — định dạng số và ký hiệu (`document_register_format`, dải `TRIAL`)

Hiện dùng định dạng giả `TRIAL-{seq}/{year}/{symbol}`, ký hiệu `THU-NGHIEM` (A-100). Anh giao:

1. **Ít nhất ba số văn bản thật** đã cấp cho giấy xác nhận công tác, nguyên văn (số và ký hiệu); nếu được, hai năm khác nhau để thấy cách reset.
2. **Ký hiệu** (`symbol`) nguyên văn, gồm phần viết tắt tên cơ quan/đơn vị.
3. **Đệm số 0**: có không, tới mấy chữ số (`seq_min_digits`).
4. **Chu kỳ**: reset đầu năm hay không bao giờ (`YEARLY` · `NEVER`; hiện giả định `YEARLY`).
5. **Một sổ hay nhiều**: giấy xác nhận công tác và giấy giới thiệu chung một dãy hay riêng (thiết kế giả định một dãy duy nhất, A-001).
6. **Cách đánh dấu số `TRIAL`** để số thử nghiệm không bao giờ trùng dạng số thật (quyết định của anh, không phải dữ liệu của tổ chức).

Mã chỉ hỗ trợ ba chỗ giữ `{seq}`, `{year}`, `{symbol}` (token lạ → `BAD_FORMAT`). Thể thức số có thành phần khác (ví dụ mã đơn vị soạn thảo) thì cần mở rộng — tôi sẽ báo trước.

### A3. Hai quyết định nhỏ gắn với mẫu

- **A-099 (người ký):** chấp nhận quy tắc làm việc "người mang `document.sign` có `employee_code` nhỏ nhất, không phải người thụ hưởng", hay anh có danh sách người ký thật / quy tắc khác. Seed giả đang có hai người ký.
- **A-100 (dòng người ký):** `"<họ tên>, <chức danh>"` — anh chỉnh dấu phân cách / thứ tự / xuống dòng theo mẫu thật.

### A4. Khoá và hạn mức Groq cho lần chạy

- **`BO19_LLM_API_KEY`** do anh export trong cửa sổ chạy (không `.env`, không dòng lệnh; như `llm-probe`).
- **Hạn mức:** gói Free của Groq giới hạn token mỗi phút/ngày theo model (`docs/reference/llm-groq.md`). Một lượt đầy đủ gọi `classify_intent` (P1), `extract_slots` (P2), và `draft_free_content` (P4); mỗi vòng sửa nội dung thêm một lần P4. Anh cho **số lời gọi tối đa** của lần chạy AC-1.1 (lần trước anh còn 3/10 lời gọi cho phép của đợt khác).
- **Dữ liệu giả có nhãn:** nhân viên giả của seed; anh không dùng dữ liệu người thật (mốc 1 của ADR-032).

## B. Việc của tôi trước lần chạy (để anh biết thứ tự)

1. **B10a, B10b** (client). 2. Cơ chế biến thể `contract_type`/đã nghỉ việc (sau khi có mẫu, **sau khi anh duyệt cách làm**). 3. Tải mẫu thật lên bằng chính luồng `template` (kiểm font, manifest) và kích hoạt. 4. Thêm dòng `document_register_format` thật vào `tools/seed-dev/`. 5. Chạy AC-1.1 cùng anh trên local.

## C. `[CẦN XÁC MINH]` còn treo, theo mức ảnh hưởng tới AC-1.1

| Mục | Ảnh hưởng tới AC-1.1 | Trạng thái |
|---|---|---|
| **A-058 (a)(b)** mẫu và font thật | Chặn: không có mẫu thật thì AC-1.1 chỉ đạt trên mẫu giữ chỗ | Chờ A1 |
| **A-013 (a)** `contract_type` thật | Chặn nếu giá trị thật ngoài ba giá trị (cần migration) | Chờ A1.6 |
| **A-009** định dạng số | Chặn: như A2 | Chờ A2 |
| **A-099**, **A-100** | Chặn nhẹ: cần anh xác nhận | Chờ A3 |
| **A-098** ba mặc định bản nháp, **O1-20** | Kiểm lại với mẫu thật (dấu giữ chỗ, `dd/mm/yyyy`, kiểu slot chưa hỗ trợ) | Làm khi có mẫu |
| **A-090** trần output | Đã có số đo B4b; còn "chưa hiệu chỉnh" | Không chặn |
| **O1-17** P1 treo 8 s một lần | Quan sát khi chạy; không chặn | Mở |
| **A-092** tỷ lệ token `estimated` | Đo ở lần chạy này | Đo trong lần chạy |
| **A-036** phạm vi áp dụng Nghị định 30/2020 với tổ chức; **tình trạng hiệu lực** | **Không chặn AC-1.1 (dữ liệu giả)**; chặn trước khi sinh văn bản **thật** và trước khi tháo chế độ phi sản xuất. Kết quả kiểm hiệu lực: `docs/reference/nghi-dinh-30-2020-tinh-trang-hieu-luc.md` — hai nguồn chính thức không nêu văn bản sửa đổi/thay thế, **chưa đủ để kết luận** | Cần pháp chế |
| **A-080** Luật BVDLCN 2025 / Nghị định 356/2025 | Không chặn AC-1.1 (dữ liệu giả); chặn trước dữ liệu cá nhân thật | Chưa có bản gốc trong `docs/reference/` |
| **A-024** object storage | **Đã đóng phần S7 trên R2 (2026-10-21)**; chờ anh xác nhận cổng 2.5 — chỉ liên quan Render, không liên quan lần chạy local | Chờ anh |

**Không cần cho AC-1.1:** dải `OFFICIAL`, số cuối cùng đã cấp trong năm (chỉ cần trước `PRODUCTION`), cột CSV hồ sơ (cổng 3.8), A-071 (nhịp sprint).

## Open Questions

Ba mục anh quyết thêm: cách xử lý biến thể `contract_type` (sau khi có mẫu), số lời gọi Groq tối đa cho lần chạy, và có tải bản vbpl (Cơ sở dữ liệu quốc gia) cho câu hỏi hiệu lực Nghị định 30/2020 không.
