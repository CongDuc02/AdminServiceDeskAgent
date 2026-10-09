# Đề xuất — từ vựng `slot_definition.validation_rules` v1 và hàm "đủ điều kiện xử lý" (A-093, O1-14)

**Trạng thái:** ✅ **PO duyệt 2026-10-09, kèm chỉnh V1–V2** (`min_tokens` → `min_tokens`; khuôn hỏi lại `purpose` nêu ví dụ; đếm số lần `min_tokens` từ chối `purpose` ở cổng UAT) — B6a làm theo bản này. · **Ngày:** 2026-10-09 · **Người đề xuất:** người triển khai (Claude) · **Hạn:** trước `check_completeness` của `intake_graph` (B6) · **Nguồn của vấn đề:** B5 hoãn F1 vì chỗ này (mục B5 của `CHANGELOG.md`)

## 1. Vấn đề

Điều kiện 3 của định nghĩa "Yêu cầu đủ điều kiện xử lý" (F1, `01-prd.md`) đòi *"mọi rule kiểm tra ở bảng slot tương ứng đều pass"*, và F1 cấm *"slot có giá trị nhưng rỗng về nội dung — `purpose` là 'cần gấp', `work_content` là 'làm việc'"*. Cột `slot_definition.validation_rules` (jsonb, mặc định `{}`) được mô tả là "rule khai báo, do `tool_layer` diễn giải" (F6) — nhưng **không tài liệu nào định nghĩa từ vựng**. Cột "Rule kiểm tra" ở mục Slot schema của `00-domain.md` là văn xuôi ("Không rỗng", "Chỉ đọc", "Có giá trị và đã ở quá khứ → chuyển thể thức"). Không có từ vựng thì hàm F1 và `request_slots_write` (lỗi `RULE_FAILED`) không cài được.

## 2. Phân loại các "rule" trong văn xuôi — chỉ một phần là rule kiểm tra giá trị

| Văn xuôi ở `00-domain.md` | Thực chất | Nằm ở đâu |
|---|---|---|
| "Lấy từ phiên đăng nhập, không cho sửa" · "Chỉ đọc" | Ngữ nghĩa của **nguồn** (`SYSTEM`, `HR_PROFILE`): agent không ghi được | Cột `source`; `request_slots_write` trả `SLOT_NOT_ALLOWED` — không phải rule |
| "Lệch so với lời nhân viên khai thì chặn và báo phòng HC" · mâu thuẫn với `HR_PROFILE` | Đối chiếu ngữ nghĩa hai nguồn — việc của người xác minh | Không phải rule máy (F1: "chuyển phòng hành chính xác minh, không phải ca agent chọn bên nào đúng") |
| `employment_end_date` có giá trị và đã ở quá khứ → "đã từng công tác" | **Biến thể câu chữ** của template | Template (M1.1), không phải kiểm tra giá trị |
| "Không rỗng" (`purpose`, `recipient_org`) · "cần gấp", "làm việc" | **Rule máy** | Từ vựng dưới đây |
| `copies_count` "Mặc định 1. Trần TBD (A-011)" | **Rule máy** (khoảng) | Từ vựng dưới đây; trần chờ A-011 |
| `contract_type` thuộc ba giá trị | **Rule máy** (danh sách) | Từ vựng dưới đây |
| `valid_from >= ngày cấp`, `valid_to >= valid_from`, mã nhân viên của `accompanying_persons` | Rule so sánh **nhiều slot / tra DB** | **Sprint 3** (`INTRODUCTION_LETTER`) — ngoài B6; thêm kiểu rule lúc đó |

## 3. Đề xuất — từ vựng v1, đóng, bốn kiểu rule

`validation_rules` là **một đối tượng JSON, khoá = kiểu rule**, giá trị = tham số. Kiểu lạ, tham số sai kiểu, hay kiểu rule không hợp với `data_type` của slot → **cấu hình không hợp lệ** (fail-closed: test cấu hình đã nạp, và kiểm lúc tải cấu hình ở F6 — T5 của `12-roadmap.md`). Rule chạy theo thứ tự cố định dưới đây; rule đầu tiên hỏng quyết mã trả về.

| # | Kiểu rule | Tham số | `data_type` | Nghĩa |
|---|---|---|---|---|
| 1 | `non_blank` | `true` | `STRING`, `TEXT` | Sau chuẩn hoá Unicode **NFC** và cắt khoảng trắng hai đầu, còn ít nhất một ký tự thuộc nhóm chữ hoặc chữ số (`L*`, `N*`). `"..."`, `"—"`, `"  "` hỏng |
| 2 | `min_tokens` | số nguyên ≥ 1 | `STRING`, `TEXT` | Số **đơn vị cách nhau bởi khoảng trắng** (sau chuẩn hoá NFC, tách theo khoảng trắng Unicode, bỏ đơn vị rỗng) ≥ N. **Với tiếng Việt đây là đếm tiếng (âm tiết), không phải đếm từ:** "xin visa" = 2 nên với N = 3 bị hỏi lại, dù là một yêu cầu rõ ràng. Cơ học: **không** đánh giá nghĩa |
| 3 | `int_range` | `{"min": n, "max": m}` (mỗi khoá tuỳ chọn, có ít nhất một) | `INT` | `min ≤ giá trị ≤ max`. `bool` không phải số nguyên |
| 4 | `one_of` | danh sách chuỗi không rỗng | `ENUM` | Giá trị bằng đúng một phần tử (phân biệt hoa thường) |

Kiểm `data_type` có sẵn trước các rule (kiểu sai thì `RULE_FAILED` với mã `TYPE`): `INT` là số nguyên không phải `bool`; `DATE` là `YYYY-MM-DD` hợp lệ; `STRING`/`TEXT` là chuỗi; `ENUM` là chuỗi.

**Mã kết quả:** `RULE_NON_BLANK`, `RULE_MIN_TOKENS`, `RULE_INT_RANGE`, `RULE_ONE_OF`, `RULE_TYPE` — chỉ mã và **tên slot**, **không bao giờ** giá trị (`purpose` là `RES`). Trong lượt chat, mã đi vào state/log; `request_slots_write` trả `RULE_FAILED` kèm danh sách (tên slot, mã).

**Nơi cài:** hàm thuần `bo19.domain.slot_rules` (không IO) — dùng ở ba chỗ: `request_slots_write` (từng giá trị lúc ghi), F1 `eligible_for_processing` (điều kiện 3, mọi slot đang có giá trị), `request_submit` (chạy lại với cấu hình **hiện hành** — đúng cái giá đã ghi ở mục Cấu hình loại yêu cầu của `04-data.md`: rule không version).

## 4. Giá trị nạp cho `WORK_CONFIRMATION` (Sprint 1)

| Slot (nguồn) | `validation_rules` | Ghi chú |
|---|---|---|
| `purpose` (`USER_INPUT`, `RES`) | `{"non_blank": true, "min_tokens": 3}` | **N = 3 là giá trị làm việc, nhãn "chưa hiệu chỉnh"** (PO, 2026-10-09). Hai ví dụ F1 ("cần gấp", "làm việc") đều 2 tiếng nên hỏng; "bổ sung hồ sơ vay vốn" (6 tiếng) qua; "xin visa" (2 tiếng) **cũng bị hỏi lại** — chấp nhận, vì khuôn hỏi lại nêu một ví dụ cụ thể (`ASK_PURPOSE_RETRY`, `reply-templates.md`) để nhân viên viết rõ hơn. Không có số liệu nào nói 3 là đúng: **cổng UAT đếm số lần `min_tokens` từ chối `purpose`** (cổng 4.x của `12-roadmap.md`) để hiệu chỉnh N |
| `recipient_org` (`USER_INPUT`, `PER`) | `{"non_blank": true}` | Tên cơ quan có thể một từ ("Vietcombank"), nên không `min_tokens` |
| `copies_count` (`USER_INPUT`, `INT`) | `{"int_range": {"min": 1}}` | **Không `max`** cho tới khi A-011 có trần — nói thẳng: chưa có chặn trên |
| `contract_type` (`HR_PROFILE`, `PER`) | `{"one_of": ["INDEFINITE", "FIXED_TERM", "PROBATION"]}` | Ba giá trị của `ck_employee_contract_type` (DDL); giá trị thật của tổ chức ánh xạ sang ba giá trị này ở mốc M1.1 |
| Các slot còn lại (`HR_PROFILE`, `SYSTEM`) | `{}` | Giá trị do hệ thống/hồ sơ nhân sự cấp, không do người gõ |

`language` `[Could]` **không nạp** ở Sprint 1: `[Could]`, bản tiếng Anh cần mẫu riêng, và một slot `USER_INPUT` còn trong `slot_specs` là một slot mà P2 có thể trích.

## 5. Giới hạn nói thẳng

- `min_tokens` **không** phân biệt "nhằm mục đích bổ sung hồ sơ" với "vì lý do cá nhân khác": nội dung rỗng nghĩa vẫn lọt nếu đủ tiếng; và nó từ chối nhầm câu ngắn nhưng đủ nghĩa ("xin visa"). Chốt chặn thật cho ca này là **người duyệt ở cổng 1** (HITL bắt buộc), không phải rule máy. Rule máy chỉ chặn ca trần trụi đã nêu ở F1.
- Từ vựng v1 chưa phủ `INTRODUCTION_LETTER`, `ROOM_BOOKING`, `SEAL_REQUEST`. Thêm một kiểu rule là: sửa tài liệu này, `04-data.md`, `CHANGELOG.md`, thêm code và test — **không cần ADR** (không phải quyết định kiến trúc), cần PO duyệt kiểu mới. Mục tiêu F6 ("thêm loại không sửa code") đúng khi kiểu rule cần đã có trong từ vựng; loại nào đòi kiểu mới thì sửa code — chấp nhận và nêu rõ ở Sprint 3.

## 6. Hàm F1 sau khi duyệt (mô tả, chưa viết)

`domain.eligibility.evaluate(request_header, definitions, slots, actor_can_create_on_behalf) -> list[reason_code]` — thuần, danh sách rỗng = đủ điều kiện. Bốn điều kiện của F1: (1) mọi slot `USER_INPUT` bắt buộc có giá trị `PROVIDED`, hoặc `PROPOSED` từ lần `EXPIRED` đã `CONFIRMED` từng giá trị; (2) mọi slot `HR_PROFILE` bắt buộc `CONFIRMED`; (3) mọi rule pass (từ vựng trên); (4) `beneficiary_employee_id` xác định, và nếu khác người tạo thì người tạo có `request.create_on_behalf`. Mã lý do: `SLOT_MISSING`, `SLOT_UNCONFIRMED`, `RULE_*`, `BENEFICIARY_UNKNOWN`, `ON_BEHALF_FORBIDDEN` — kèm tên slot. `tool_layer.checks` nạp dữ liệu một lần cho `check_completeness`, `request_slot_confirm`, `request_submit` (một lối nạp — `06-structure.md`).

Test: bảng chân trị bốn điều kiện × từng loại hỏng; đột biến cho từng điều kiện (bỏ điều kiện → đỏ); mọi kiểu rule với giá trị biên (NFC dựng sẵn và tổ hợp, `"..."`, `bool` vào `INT`); kết quả không bao giờ chứa giá trị.

## Quyết định cần PO

| # | Quyết định | Mặc định |
|---|---|---|
| V1 | Chấp nhận từ vựng v1 (bốn kiểu rule, đối tượng khoá theo kiểu, kiểu lạ → cấu hình hỏng) | Chấp nhận |
| V2 | `purpose`: `min_tokens` = 3 (giá trị làm việc, "chưa hiệu chỉnh") | 3 |
| V3 | `copies_count` không `max` tới khi A-011 có trần | Đồng ý |
| V4 | `language` không nạp ở Sprint 1 | Đồng ý |

## Open Questions

- Trần `copies_count` (A-011) và "khoảng hiệu lực tối đa" (A-011, Sprint 3) vẫn `TBD` — không bịa số.
