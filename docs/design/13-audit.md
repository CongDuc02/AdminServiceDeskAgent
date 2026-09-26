# Consistency Audit — Admin Service Desk Agent (BO-19)

**Phiên bản:** 0.1 · **Trạng thái:** Draft chờ duyệt · **Ngày chạy:** 2026-09-26

> File này đối chiếu toàn bộ `docs/design/` với nhau và với phần repo mà tài liệu dựa vào (`backend/migrations/`, cây thư mục backend, `tools/contract-checks/`). Kết quả là bảng lỗi `AUD-xx` kèm thứ tự sửa đề xuất. File này **chỉ báo cáo**: không sửa file nào khác, ngoài một mục mới trong `CHANGELOG.md`. Nó **không** quyết thay PO những chỗ cần quyết định, **không** thêm giả định, ADR hay tên mới, và **không** mở lại quyết định đã chốt.

**Đã đối chiếu:** `CLAUDE.md`, `_PLAN.md`, `GLOSSARY.md` (0.21), `ASSUMPTIONS.md` (0.29), `CHANGELOG.md`, `00-domain.md` → `12-roadmap.md`, `contracts/openapi.yaml` (0.2.2), `contracts/schema.sql`, ADR-001 → ADR-025, năm file của `proposals/`, `backend/migrations/schema/0001`–`0005`, `backend/migrations/data/0001_permission_catalog.sql`, `backend/migrations/library/checkpointer_grants.sql`, cây `backend/src/bo19/`, `tools/contract-checks/`. Nội dung của `frontend/` không đối chiếu (đã chốt ở kế hoạch phase).

---

## 1. Phạm vi và phương pháp

### 1.1 Kiểm bằng máy và đọc tay

| Phép kiểm | Cách | Kết quả tóm tắt |
|---|---|---|
| `05-api.md` mục Endpoint ↔ `openapi.yaml` | Script, phụ lục A.2 | 50 operation; khớp 50/50 method–path; bốn dòng `[NGOÀI-OPENAPI]` vắng đúng |
| Danh mục `error_code` ↔ enum `ErrorCode` | Script, phụ lục A.2 | 35 mã ở `05-api.md`, 33 mã trong enum — AUD-04 |
| Enum của `schema.sql` ↔ `GLOSSARY.md` ↔ `openapi.yaml` | `grep` các `CHECK … IN`, script phụ lục A.1 | Khớp mọi enum đã nâng lên `GLOSSARY.md` |
| Danh mục permission | Đọc `00-domain.md`, `GLOSSARY.md`, `0001_permission_catalog.sql` | 25 = 25 = 25; gói vai trò khớp |
| Máy trạng thái giữa các file | Trích cạnh Mermaid, so tập cạnh — phụ lục A.4 | `00-domain.md` = `02-architecture.md`; `08-hitl.md` thiếu hai cạnh — AUD-06 |
| Mọi cạnh của máy trạng thái có thao tác nào đi qua không | Đọc tay `03-agents.md` mục Tool Registry, `04-data.md`, `08-hitl.md` | AUD-01, AUD-07 |
| Mọi ID `A-`, `D-`, `ADR-`, `RISK-`, `EC-` được trỏ tới đều tồn tại | Script, phụ lục A.3 | Không có ID treo (chỉ một `EC-WC-04` lịch sử trong `CHANGELOG.md`) |
| Định danh `snake_case` trong backtick mà `GLOSSARY.md` và contract không biết | Script, phụ lục A.3 | Đọc tay danh sách; đa số là tên trường state và slot — AUD-08, AUD-20 |
| Mermaid | `@mermaid-js/mermaid-cli` 12.0.0 qua `npx`, chạy trong scratchpad — phụ lục A.4 | 31/31 sơ đồ render được; không sơ đồ nào quá 20 node |
| `openapi.yaml` hợp lệ | `openapi-spec-validator` 0.9.0 trong venv của scratchpad | Hợp lệ |
| Quyền DB | `tools/contract-checks/check_grants.py` `--local` và `--local-migrated` | 169 / 63 / Lệch 0 và 176 / 68 / Lệch 0 — trùng khít số đã ghi ở `CHANGELOG.md` |
| Tham chiếu chéo theo số mục, số dòng (luật 12) | `grep` — phụ lục A.5 | AUD-17 |
| Nội dung còn lại: câu "chưa có / chờ Phase N / TBD" đã được phase sau giải, mâu thuẫn ngữ nghĩa, nợ thiết kế | Đọc tay từng file | Phần lớn các AUD |

### 1.2 Không kiểm được — nói thẳng

- **Ngữ nghĩa của sơ đồ sequence** chỉ kiểm bằng đọc tay; không có công cụ nào so sequence diagram với bảng thao tác.
- **`12-roadmap.md` mục Endpoint → sprint** được đối chiếu bằng tay với 50 operation (đủ 50). Bộ tách tự động ở phụ lục A.2 không đọc được định dạng gộp nhiều endpoint trên một dòng của bảng đó.
- **Số liệu và trích dẫn ngoài `docs/reference/`** không kiểm được đúng sai. Theo quy tắc của phase này, chúng được ghi là **chưa xác minh được**, không bị kết luận là bịa (AUD-21).
- **Không có trạng thái nào có trong sơ đồ mà thiếu ở DB.** Ba máy trạng thái ở sơ đồ khớp đúng `CHECK` của `schema.sql` và enum của `openapi.yaml`. Lệch thật nằm ở chỗ khác: **cạnh** không có thao tác nào đi qua (AUD-01, AUD-07).

---

## 2. Thang mức độ và thứ bậc nguồn sự thật

| Mức | Nghĩa |
|---|---|
| **Chặn** | Build đúng theo tài liệu sẽ ra hành vi sai, phá một bất biến, hoặc không có đường làm một việc mà AC hay DoD đòi — và review thông thường khó thấy vì từng file riêng lẻ trông vẫn đúng |
| **Cao** | Gây hiểu sai khi build, nhưng review hoặc test phát hiện được |
| **Thấp** | Thẩm mỹ, trình bày; không ảnh hưởng hành vi |

**Khi hai nơi lệch nhau, nơi đúng xác định theo thứ tự này:**

1. Quyết định `D-xxx` và ADR `Accepted`. ADR `Superseded` thua ADR thay thế nó. Hai ADR `Accepted` mâu thuẫn nhau thì ghi lỗi, và tạm lấy ADR mới hơn. **Hiện cả 25 ADR đều `Accepted`, không có ADR nào bị thay thế.**
2. `GLOSSARY.md`, với câu hỏi về **tên**.
3. Phase gốc của khái niệm. `contracts/openapi.yaml` ngang hàng `05-api.md`. **`schema.sql` lệch migration thì migration đúng.**
4. Phase hạ nguồn.

**Riêng owner và hạn:** `ASSUMPTIONS.md` là nơi duy nhất, theo chính câu đầu của file đó và mục Open Questions của `01-prd.md`.

---

## 3. Kết quả theo bảy loại lỗi của `_PLAN.md`

| Loại | Kết quả | AUD |
|---|---|---|
| Tên entity lệch | Có — nhỏ, đã có ánh xạ ghi ở một nơi | AUD-20 |
| Trạng thái có trong diagram nhưng thiếu ở DB | **Không có.** Lệch thật nằm ở cạnh không có thao tác nào đi qua | AUD-01, AUD-07 |
| Endpoint không có FR tương ứng | Có 8 operation không mang `x-bo19-feature`. PRD không có feature nào cho đăng nhập | AUD-19 |
| FR không có endpoint | **Không có.** F1–F6 đều có endpoint. F2 chỉ có `GET /documents/{document_id}`: phần còn lại của F2 chạy bằng job, và điều đó đúng thiết kế | — |
| Tool không xuất hiện trong agent nào | `render_integrity_check`, `signing_route`, `document_number_assign`, `notification_send`, `document_halt_record` không thuộc agent nào — **có chủ đích**: chúng thuộc node tất định sau cổng hoặc node dùng chung (mục Ai được gọi tool nào của `03-agents.md`). `room_availability_check` `[Should]` thuộc `intake_agent` nhưng chưa node nào gọi — chấp nhận vì là `[Should]`. **Lỗi thật:** các thao tác chưa có tên, hoặc có tên mà vắng khỏi bản kê | AUD-08 |
| Giả định chưa được giải quyết | 76 dòng: 55 `Mở`, 17 `Đã chốt`, 3 `Thu hẹp`, 1 `Bác bỏ`. Không liệt kê cả 55 dòng `Mở`; chỉ báo những dòng có vấn đề | AUD-13 |
| ADR bị mâu thuẫn | Không có hai ADR mâu thuẫn nhau. ADR mâu thuẫn với tài liệu sau nó thì có | AUD-09, AUD-11, AUD-12 |

---

## 4. Bảng lỗi

### 4.1 Tổng hợp

| ID | Mức | Loại | Tóm tắt | Cần PO quyết? |
|---|---|---|---|---|
| AUD-01 | **Chặn** | Máy trạng thái ↔ thao tác | Không thao tác nào đưa `request` sang `APPROVED`, nên `FULFILLED` không tới được. Gắn việc đó vào lúc duyệt nội dung thì lại gãy ở nhánh người ký trả lại | Có |
| AUD-02 | **Chặn** | Nợ thiết kế chưa giao | Phần `_PLAN.md` và các phase trước giao cho Phase 8 mà `08-hitl.md` chưa làm, và `12-roadmap.md` mục Nợ thiết kế Phase 8 chưa ghi: bảng mã, thao tác tiếp quản, chi tiết đường thoát tự duyệt | Có |
| AUD-03 | Cao | DDL ↔ migration | `contracts/schema.sql` không còn là schema thật; không chỗ nào trong file nói vậy | Có — cách biểu diễn |
| AUD-04 | Cao | Contract | Enum `ErrorCode` thiếu `RATE_LIMITED`, `OPERATING_MODE_UNCHANGED` | Không |
| AUD-05 | Cao | Contract, tên | `request_type.manage` vẫn bị ghi là "chưa có trong danh mục, từ chối mọi người" ở 8 nơi, gồm `openapi.yaml` và `GLOSSARY.md` | Không |
| AUD-06 | Cao | Nội dung sai | `08-hitl.md` mô tả sai luồng yêu cầu sửa và vẽ thiếu cạnh của máy trạng thái `document` — trong khi Sprint 2 dựng đúng theo mục đó | Không |
| AUD-07 | Cao | Máy trạng thái ↔ thao tác | Cạnh không có thao tác nào đi qua (ngoài AUD-01), và thao tác đòi một cạnh không có (EC-CV-02 ở `NEEDS_INFO`) | Có |
| AUD-08 | Cao | Tool / thao tác | Thao tác được mô tả mà chưa có tên; có tên mà vắng khỏi `GLOSSARY.md` hoặc khỏi bản kê của Tool Registry | Không |
| AUD-09 | Cao | ADR ↔ tài liệu, tech stack | BM25: `CLAUDE.md` bắt buộc, ADR-002 và `02-architecture.md` khẳng định có, `04-data.md` chốt là không phải BM25 — mà không có ADR | Có |
| AUD-10 | Cao | Tên | Lượt sửa `GLOSSARY.md`/contract ở mục Phát hiện, không tự sửa của `11-ops.md` chưa chạy | Không |
| AUD-11 | Cao | Nội dung cũ | Câu "chưa có / TBD / chờ Phase N / chưa áp" đã được phase sau giải nhưng không sửa ngược — 25 dòng vị trí, gom theo file | Không |
| AUD-12 | Cao | ADR ↔ observability | Điều kiện đảo ngược của ADR-008 và một vế của ADR-015 không có chỗ quan sát | Không |
| AUD-13 | Cao | Giả định | Hạn trỏ vào phase đã qua; owner là một phase đã đóng; giả định chặn cổng sprint mà không có owner/hạn; trạng thái lệch nội dung | Có — owner |
| AUD-14 | Cao | Contract prompt | `ExtractSlotsResult` không biểu diễn được slot kiểu `LIST` — `accompanying_persons` không bao giờ trích được | Không |
| AUD-15 | Cao | Tên, phạm vi | `delegation` mang hai nghĩa; điều kiện 4 của F1 và EC-IL-01 (Must, chấm bằng M6) dựa vào uỷ quyền `[Should]` không có đường tạo trong Sprint đầu | Có |
| AUD-16 | Cao | Cấu trúc | Skeleton backend lệch `06-structure.md`: `api/app.py` trùng tên package `api/app/`; router `health` ngoài contract | Có — `/health` |
| AUD-17 | Thấp | Luật 12 | Tham chiếu chéo theo số dòng (47 chỗ trong tài liệu, 30 trong skeleton) và theo số mục (36 chỗ); có tham chiếu trỏ vào mục không tồn tại | Không |
| AUD-18 | Thấp | Trình bày | Số phiên bản đầu file lệch ghi chú phiên bản ở ba file | Không |
| AUD-19 | Thấp | Truy vết | 8 operation không có `x-bo19-feature`; PRD không có feature đăng nhập; không có ID `FR-xx`/`US-xx` (luật 8) | Có — ID |
| AUD-20 | Thấp | Tên | `signer_user_id` ↔ `signer_employee_id`; `beneficiary_employee_id` trộn mã và id; `VALIDATION_FAILED` trùng giữa `error_code` và `reason_code` | Không |
| AUD-21 | Thấp | Trích dẫn | Tiêu chuẩn và thông số không có bản gốc trong `docs/reference/` — chưa xác minh được | Không |
| AUD-22 | Thấp | Lỗi nội bộ | Tham chiếu sai đích, đếm sai, bỏ sót một bước trong DoD | Không |

### 4.2 Chi tiết

#### AUD-01 — `request` không bao giờ tới `APPROVED` · **Chặn**

**Bằng chứng**

| Vị trí | Nói gì |
|---|---|
| `00-domain.md`, mục Vòng đời `request` | Cạnh `IN_REVIEW → APPROVED` và `APPROVED → FULFILLED`; bảng nghĩa ghi `APPROVED` do "người có `document.approve_content`" đẩy sang |
| `02-architecture.md`, mục State machine — bảng chủ sở hữu của `request` | `APPROVED` — `api`/`tool_layer`, permission `document.approve_content` |
| `03-agents.md`, mục Tool Registry — Thao tác cổng | `document_approve_content`: `PENDING_APPROVAL → APPROVED` cho **`document`**, ghi `approved_content_hash`. **Không** nhắc `request` |
| `08-hitl.md`, mục Ma trận duyệt và tách biệt trách nhiệm | Cột `request` của `document_approve_content`: "—" |
| `03-agents.md`, mục Tool Registry — Chi tiết từng tool, dòng `document_transition` | Vào `ISSUED` thì cùng giao dịch đưa `request` sang `FULFILLED` |

Tìm khắp `03-agents.md`, `04-data.md`, `05-api.md`, `08-hitl.md`: không thao tác nào ghi `request → APPROVED`.

**Hệ quả.** Build đúng theo `03-agents.md` và `08-hitl.md` thì `request` đứng ở `IN_REVIEW` tới lúc phát hành. Khi đó `finalize_issue` phải chuyển `IN_REVIEW → FULFILLED` — cạnh không tồn tại. Điểm ghi trạng thái duy nhất (`tool_layer.kernel.transition`, mục Cây backend của `06-structure.md`) kiểm trạng thái mong đợi, nên sẽ từ chối. Hành trình ở điều 1 của mục Definition of Done của `01-prd.md` — "nhân viên thấy trạng thái `FULFILLED`" — không chạy được, tức AC-1.1 của Sprint 1 trượt.

**Chữa theo bảng của `02-architecture.md` cũng không xong.** Đặt `request → APPROVED` trong `document_approve_content` thì nhánh người ký trả lại (`PENDING_SIGNATURE → CHANGES_REQUESTED`, ca `SLOT_DATA`) phải chuyển `request APPROVED → CHANGES_REQUESTED`. Ca `FREE_CONTENT` thì `request` phải quay về `IN_REVIEW`. Máy trạng thái `request` không có cạnh nào ra khỏi `APPROVED` ngoài `FULFILLED`.

**Nguồn đúng.** Máy trạng thái `request` (D-004) là gốc, nhưng nó mâu thuẫn với thao tác cổng đã chốt. Không nơi nào đúng trọn — cần PO quyết.

**Hai hướng — nghiêng về (a):**

- **(a)** `request → APPROVED` xảy ra trong `document_sign` (tức khi `document` rời `PENDING_SIGNATURE`), không trong `document_approve_content`. Sau `SIGNED` máy trạng thái `document` không có đường quay lại (A-034 còn mở cho `PENDING_SEAL`), nên `request` không cần cạnh mới. Bảng nghĩa ở `00-domain.md` và bảng chủ sở hữu ở `02-architecture.md` phải sửa thành "người có `document.sign`". Nếu A-034 được quyết theo hướng thêm lối trả lại ở `PENDING_SEAL`, hướng này phải xét lại cùng lúc.
- **(b)** Giữ `APPROVED` ở lúc duyệt nội dung, thêm vào máy trạng thái `request` hai cạnh `APPROVED → CHANGES_REQUESTED` và `APPROVED → IN_REVIEW`. Đổi D-004; sửa `00-domain.md`, `02-architecture.md`, `03-agents.md`, `08-hitl.md`.

---

#### AUD-02 — Nợ thiết kế giao cho Phase 8 chưa được giao, và chưa vào sổ nợ · **Chặn**

**Nguyên nhân gốc.** `08-hitl.md` đóng khi còn thiếu nhiều phần được giao. PO giữ Phase 8 ☑, và `12-roadmap.md` mục Nợ thiết kế Phase 8 chuyển nợ thành cổng sprint — nhưng chỉ gom những việc **đã có dòng `A-xxx`**. Các việc dưới đây không có dòng giả định nào, nên không nằm ở cổng nào.

| # | Việc | Ai giao, ở đâu | Hiện trạng | Sprint đầu tiên cần |
|---|---|---|---|---|
| a | Bảng mã `document_halt.reason_code` đầy đủ | `04-data.md` mục Nguyên tắc dữ liệu (dữ liệu danh mục); `GLOSSARY.md` mục Enum khác; `05-api.md` mục Mã lỗi (bảng mã quyết mã nào lộ cho người tiếp quản) | `08-hitl.md` mục Cơ chế dừng khi chạm trần chỉ có 6 mã. Không có mã cho `NO_ELIGIBLE_SIGNER`, `RENDER_OBJECT_MISSING`, `TEMPLATE_NOT_ACTIVE`, `CONVERSION_FAILED`, `approved_content_hash` lệch (nhánh `VOIDED`), lỗi provider hết retry, `SLOT_NOT_DECLARED` — dù chính mục đó liệt các đường vào này. `document_halt_record` trả `UNKNOWN_REASON_CODE` cho mã ngoài bảng | 2 — `halt_for_human` |
| b | Bảng mã `archive_reason` | `00-domain.md` mục Vòng đời `document`; `GLOSSARY.md` mục Enum khác; `05-api.md` mục Endpoint (`cancel` — "server gán từ bảng mã của Phase 8") | Không có ở đâu. `ck_document_archive_reason_abandoned_draft` bắt buộc giá trị | 2 — `request_cancel` |
| c | Bảng mã `notification.event_code` | `04-data.md`, `GLOSSARY.md` mục Enum khác | Không có ở đâu (xác nhận lại mục Phát hiện, không tự sửa của `11-ops.md`) | 2 — `halt_for_human` gửi thông báo |
| d | Thao tác tiếp quản ghi `decision_record` loại `TAKEOVER_RESOLVED` | `05-api.md` mục Nhãn phạm vi và loại trừ có chủ đích (loại trừ, "Phase 8"); `03-agents.md` bảng node `interrupt` — `await_human_takeover` "Thiết kế ở Phase 8" | Không có tên thao tác, permission hay endpoint. `08-hitl.md` mục Tiếp quản chỉ có bảng hành động. Trong đó hai hành động trái thiết kế đã chốt: "sửa `variable_guidance`/`template_variable` rồi resume" — phiên bản template bất biến, `template_variable` chỉ thêm (mục Bảng chi tiết của `04-data.md`); "người thật soạn tay phần còn lại" — không thao tác nào cho người ghi biến nội dung tự do (`document_draft_save` chỉ dành cho tác nhân hệ thống). NFR-06 hứa "chuyển cho người thật xử lý"; thiếu mục này thì lời hứa không có đường vào | 2 — AC-2.3 dừng được; tiếp quản không sprint nào dựng |
| e | Cách xác định "chỉ còn một người đủ quyền" cho đường thoát tự duyệt | `00-domain.md` mục Tách biệt trách nhiệm ("Việc còn lại cho phase sau") | `08-hitl.md` nhắc lại bốn điều kiện nhưng không định nghĩa phép xác định | 3 — AC-3.6 |
| f | Đường thoát tự duyệt cho thu hồi | D-006: "Cùng cơ chế này áp dụng cho ràng buộc hai người ở bước thu hồi" | `05-api.md` mục Endpoint — Thu hồi và `08-hitl.md` mục Thu hồi văn bản: trùng người thì `SEPARATION_OF_DUTIES_VIOLATION`, **không** có đường thoát. `approval_step` không có loại bước cho thu hồi để mang cờ `self_approved`. **Mâu thuẫn trực tiếp với D-006** | Sau UAT (F5 `[Should]`) — nhưng mâu thuẫn với một quyết định thì phải ghi ngay |
| g | Hiển thị khoảng hoàn tất phát hành (`issue_in_progress`, nhất là đoạn đã có số) | `03-agents.md` mục Tool Registry và Open Questions | `08-hitl.md` mục Duyệt dấu và khoảng hoàn tất phát hành: "hiển thị do Phase 8 quyết" — tự trỏ về chính nó | 1 — `/issue` |
| h | Thao tác đóng `chat_session` vì nhàn rỗi (`IDLE_TIMEOUT`) | `06-structure.md` mục Open Questions — đoạn "Chưa có thao tác nào có tên đóng `chat_session` vì nhàn rỗi" ("owner Phase 8") | Không có ở `08-hitl.md` hay `12-roadmap.md`. Xem thêm AUD-08 | 2 — lớp phòng thủ hai của ADR-008 cho thread `intake` |

**Nguồn đúng.** Việc (f): D-006 đúng, contract lệch. Các việc còn lại: chưa có nguồn.

**Sửa đề xuất.** PO quyết từng việc (a)–(h) — làm trong một lượt sửa `08-hitl.md` có phép, hay mở dòng `A-xxx` rồi đặt vào cổng sprint như các nợ khác. (a), (b), (c), (d) phải xong trước cổng Sprint 2. (f): hoặc thiết kế đường thoát cho thu hồi, hoặc sửa D-006 cho khớp contract. Sửa D-006 là đổi một quyết định đã chốt, phải có PO.

---

#### AUD-03 — `contracts/schema.sql` không còn là schema thật · **Cao**

| Vị trí | Nói gì |
|---|---|
| `contracts/schema.sql`, khối chú thích đầu file | "contract DDL", "Chỉ có đúng các quyền cấp ở cuối file". Không câu nào nói file dừng ở trạng thái đóng Phase 6 |
| `backend/migrations/schema/0002`–`0005` | Hai bảng (`employee_credential`, `rate_limit_window`), một index (`ix_job_latest_by_document`), một `CHECK` (`llm_usage.trace_id`), một lần thu hẹp quyền theo cột — **không** có trong `schema.sql` |
| `06-structure.md` mục Cây backend; ADR-017 | Đã chốt: `0001_initial.sql` = `schema.sql` ở trạng thái đóng Phase 6; về sau mỗi thay đổi một file. Đã kiểm: trùng sha256 `0ce8dd…` |
| `CLAUDE.md` mục Cấu trúc output; `_PLAN.md` Phase 4 | Coi `contracts/schema.sql` là contract DDL |

**Hệ quả.** Người đọc `contracts/` — người viết `bo19.persistence`, người viết test — thấy một schema thiếu hai bảng, thiếu một index và một `CHECK`. `check_grants.py --app-dsn` bắt được lệch quyền, nhưng không bắt được việc người viết code không biết một bảng tồn tại.

**Nguồn đúng:** migration (quy tắc ở mục 2).

**Sửa đề xuất — PO chọn một:**

- **(i)** Thêm vào đầu `schema.sql` khối chú thích "đóng ở Phase 6, bằng `0001`; mọi thay đổi sau nằm ở `backend/migrations/schema/`: …". Cái giá: sửa dù chỉ một dòng chú thích cũng đổi sha256, nên `schema.sql` không còn trùng byte với `0001_initial.sql` — mất căn cứ mà `--local-migrated` dựa vào khi áp `0001` thay cho `schema.sql`.
- **(ii)** Giữ `schema.sql` nguyên byte, thêm `contracts/README.md` nói điều trên, kèm danh sách migration sau Phase 6.
- **(iii)** Sinh một bản chụp gộp — schema sau `0005` — làm contract để đọc, và giữ `schema.sql` là `0001`.

Nghiêng về (ii): rẻ nhất, và không đụng tới sự trùng byte. `CLAUDE.md` mục Cấu trúc output chưa nhắc `backend/migrations/` — báo cáo, không sửa (luật 11).

---

#### AUD-04 — Enum `ErrorCode` thiếu hai mã · **Cao**

| Vị trí | Nói gì |
|---|---|
| `05-api.md` mục Mã lỗi | 35 mã, gồm `OPERATING_MODE_UNCHANGED` (422, `details.current_mode`) và `RATE_LIMITED` (429, `details.retry_after`). Câu dẫn: "`openapi.yaml` khai đúng tập này dưới dạng enum" |
| `contracts/openapi.yaml`, `components.schemas.ErrorCode` | 33 mã; thiếu hai mã trên. Hai mã có mặt trong `description` của response `Unprocessable`/`RateLimited` |
| `11-ops.md` mục Phát hiện, không tự sửa — đoạn về enum `ErrorCode` | Đã phát hiện ở Phase 11, chưa sửa |
| `12-roadmap.md` AC-1.10 | Đòi `RATE_LIMITED` ở Sprint 1 |

Kèm một lệch nhỏ cùng gốc: `details.retry_after` của `RATE_LIMITED` so với `retry_after_seconds` của `TURN_IN_PROGRESS` — hai tên cho cùng một khái niệm.

**Nguồn đúng:** `05-api.md` (nguồn duy nhất của danh mục). **Sửa:** thêm hai mã vào enum; thống nhất tên `details` thành `retry_after_seconds`. Type của `client` sinh từ `openapi.yaml` và CI kiểm lệch (mục Đặc tả `Dockerfile` của `06-structure.md`), nên thiếu mã trong enum thì type sinh ra thiếu theo.

---

#### AUD-05 — `request_type.manage` vẫn bị ghi là chưa có · **Cao**

Phase 9 đã thêm permission này vào danh mục và vào data migration (A-042 `Đã chốt`), nhưng không sửa ngược các nơi sau:

| Vị trí | Nói gì |
|---|---|
| `contracts/openapi.yaml` — 6 operation `/config/request-types…` | `x-bo19-permission-status: NOT_IN_CATALOG_A042`; phần mô tả extension ở đầu file vẫn định nghĩa trạng thái này |
| `05-api.md` mục Nguyên tắc chung — Phân quyền ở tầng API | "chưa có trong danh mục… các endpoint đó từ chối mọi người cho tới khi Phase 9 quyết" |
| `05-api.md` mục Endpoint — Cấu hình, khối Loại yêu cầu và slot schema | Cùng câu |
| `05-api.md` mục Open Questions | Đoạn A-042 "chặn nghiệm thu" |
| `06-structure.md` mục Cây frontend — Tuyến | `/config/request-types` "hôm nay từ chối mọi người (A-042)" |
| `08-hitl.md` mục Ma trận duyệt và tách biệt trách nhiệm | "luồng cấu hình từ chối mọi người cho tới Phase 9" |
| `GLOSSARY.md` mục API — chốt ở Phase 5 | "**Cố ý vắng mặt:** `request_type.manage` … **không** có trong mục 7" — **mâu thuẫn ngay trong `GLOSSARY.md`**: mục Permission liệt nó và ghi "22 → 25" |
| `04-data.md` mục Lưu trữ và xoá dữ liệu cá nhân; mục Open Questions — dòng A-042 | "Permission của thao tác này chưa tồn tại (A-042)" |

**Nguồn đúng:** `GLOSSARY.md` mục Permission, `00-domain.md` mục Permission và vai trò, `09-security.md` mục AuthZ, `0001_permission_catalog.sql`. **Sửa:** bỏ `x-bo19-permission-status` và định nghĩa của nó khỏi `openapi.yaml`; gỡ đoạn "Cố ý vắng mặt" khỏi `GLOSSARY.md`; sửa các câu còn lại. Một câu cần **giữ**: cấu hình sổ văn bản vẫn chưa có permission — `05-api.md` mục Không có endpoint vì chưa có thao tác. Câu đó còn đúng, chỉ phải đổi căn cứ từ A-042 (đã chốt) sang một căn cứ khác (AUD-13).

---

#### AUD-06 — `08-hitl.md` mô tả sai luồng yêu cầu sửa và máy trạng thái · **Cao**

`12-roadmap.md` mục Sprint 2 dựng vòng sửa "theo mục Luồng yêu cầu sửa và agent làm lại của `08-hitl.md`", nên các lỗi dưới đây nằm đúng trên đường build.

| Vị trí trong `08-hitl.md` | Sai gì | Nguồn đúng |
|---|---|---|
| Mục Luồng yêu cầu sửa, sơ đồ, nhánh `SLOT_DATA` | Vẽ `document_graph` chuyển `document CHANGES_REQUESTED → DRAFT` và `request IN_REVIEW → CHANGES_REQUESTED`. Thực tế: thao tác cổng `document_request_changes` chuyển `request` trong giao dịch của nó; `document` đứng ở `CHANGES_REQUESTED`, thread chờ ở `await_resubmission`, và chỉ về `DRAFT` qua `reopen_draft` **sau khi** nhân viên gửi lại | `03-agents.md` mục Tool Registry — Thao tác cổng; mục LangGraph design — `document_graph` |
| Cùng sơ đồ, nhánh `FREE_CONTENT` | Gọi `draft_free_content`; đúng là `revise_free_content` | `03-agents.md` mục `document_graph` |
| Cùng sơ đồ, nhánh `SLOT_DATA` | Ghi chú "bổ sung via `request_slot_confirm` + submit". Nhân viên còn bổ sung được qua chính hội thoại (`request_slots_write` cho phép `CHANGES_REQUESTED` ca `SLOT_DATA`) | `03-agents.md` mục `intake_graph` |
| Mục Duyệt dấu và khoảng hoàn tất phát hành, sơ đồ trạng thái | Thiếu cạnh `REJECTED → ARCHIVED` và `ARCHIVED → [*]` — đo bằng so tập cạnh (phụ lục A.4). Chú thích "`ISSUED` chỉ do `finalize_issue` sau `ISSUE_ORDERED` (A-010)" gán nhầm A-010 (A-010 là thời hạn lưu trữ) | `00-domain.md` mục Vòng đời `document` |
| Mục Cơ chế dừng khi chạm trần — Đường vào `halt_for_human` | "document giữ nguyên `PENDING_APPROVAL`/`PENDING_SIGNATURE`/… tại thời điểm dừng". Không có đường nào dừng ở `PENDING_APPROVAL` (dừng xảy ra trước `submit_for_review`, ở `APPROVED` hay ở `SIGNED`/`SEALED`) | `03-agents.md` mục `document_graph` |
| Mục Audit log — Ghi gì, dòng Hội thoại | "`chat_message` (RES, đã mask)" như một sự kiện `audit_event`. `audit_event` không bao giờ chứa văn bản tự do, và việc có ghi `audit_event` cho tin nhắn chat hay không còn đang là A-055 | `04-data.md` mục Audit log bất biến; A-055 |

**Sửa:** sửa `08-hitl.md` theo cột nguồn đúng, trong cùng lượt với AUD-02.

---

#### AUD-07 — Máy trạng thái và thao tác không khớp (ngoài AUD-01) · **Cao**

**Cạnh không có thao tác nào đi qua**

| Cạnh | Ghi chú | Đã có giả định? |
|---|---|---|
| `request`: `SUBMITTED → REJECTED` ("không đủ điều kiện theo quy chế") | `document_reject` chỉ nhận `PENDING_APPROVAL`, lúc đó `request` đã `IN_REVIEW`. Một `document` dừng trước cổng 1 thì `request` đứng ở `SUBMITTED` mà không có đường từ chối — nối với AUD-02 (d) | **Không** |
| `document`: `ISSUED`/`REVOKED`/`SUPERSEDED`/`REJECTED → ARCHIVED` theo thời hạn lưu | `02-architecture.md` ghi "Cron Job theo thời hạn lưu trữ"; không thao tác nào có tên | Một phần — A-010 (thời hạn), không phải thao tác |
| `document`: `ISSUED → SUPERSEDED` | — | A-054 |
| `room_booking` `[Should]`: `→ RELEASED`, `→ CANCELLED`, `→ COMPLETED` | `05-api.md` mục `ROOM_BOOKING` ghi rõ một phần | Chấp nhận — `[Should]` |

**Thao tác đòi một cạnh không có**

- EC-CV-02 (`00-domain.md` mục Edge case nghiệp vụ): "yêu cầu cũ chưa `SUBMITTED` thì chuyển `CANCELLED`" — tức cả ở `NEEDS_INFO`. Nhưng `request_open` và cạnh `route_intent → open_request` của `03-agents.md` chỉ huỷ `request` cũ khi còn `DRAFT`, và trả `REPLACED_NOT_DRAFT` với trạng thái khác. Máy trạng thái không có `NEEDS_INFO → CANCELLED`. **A-053 chỉ ghi vế "nhân viên tự huỷ"; vế đổi loại giữa chừng ở `NEEDS_INFO` chưa có ở đâu.** Nhóm G của bộ eval có ca EC-CV-02, chấm bằng M8 — metric Bất biến.

**Sửa đề xuất.** Thêm vế EC-CV-02 vào A-053 (cùng cổng Sprint 2). PO quyết `SUBMITTED → REJECTED`: xoá cạnh, hoặc gắn nó vào thao tác tiếp quản của AUD-02 (d). Đặt tên thao tác lưu trữ theo thời hạn cùng lúc với A-010.

---

#### AUD-08 — Thao tác chưa có tên, hoặc có tên mà vắng khỏi bản kê · **Cao**

Luật ở mục Tool Registry của `03-agents.md`: mọi ghi `postgresql` đi qua một thao tác có tên của `tool_layer`, trừ danh sách ngoại lệ đóng.

| Thao tác | Được mô tả ở | Vấn đề |
|---|---|---|
| Dọn `rate_limit_window` | `09-security.md` mục Rate limit; `11-ops.md` mục Background worker & Cron ("một thao tác `cron_main` mới") | Không có tên; vắng khỏi `GLOSSARY.md`, khỏi `06-structure.md` mục Entrypoint và deploy trên Render |
| Đóng `chat_session` nhàn rỗi (`IDLE_TIMEOUT`) | `04-data.md` (index `ix_chat_session_idle` — "Cron đóng phiên nhàn rỗi"); `06-structure.md` mục Open Questions — đoạn đóng `chat_session` vì nhàn rỗi | Không có tên, không cron |
| Nhắc hạn `NEEDS_INFO` | `03-agents.md` mục Agent Registry ("job của `queue_worker`"); `08-hitl.md` mục SLA, escalation và nhắc hạn gán cho `expire_request` | Không có tên. Gán cho `expire_request` trái danh sách việc của nó ở `04-data.md` mục Lưu trữ và xoá dữ liệu cá nhân |
| Lưu trữ `document` theo thời hạn | AUD-07 | Không có tên |
| `operating_mode_transition_reject` | ADR-023; `05-api.md` mục Mã lỗi; `11-ops.md` | Có tên; vắng khỏi `GLOSSARY.md` và khỏi `03-agents.md` mục Thao tác do endpoint gọi (`11-ops.md` mục Phát hiện, không tự sửa đã nêu) |
| `object_claim_reconcile` · `slot_sensitivity_change` | `GLOSSARY.md` mục Agent, graph, node, tool — "định nghĩa đầy đủ ở `03-agents.md`" | Cả hai **không xuất hiện lần nào** trong `03-agents.md`. Định nghĩa thật nằm ở `04-data.md` |
| `[Should]` quét SLA, nhả `HELD`, hoàn tất `room_booking` | `06-structure.md`, `11-ops.md` | Không có tên — chấp nhận tới khi kích hoạt `[Should]` |

**Không phải lỗi** — ghi lại theo yêu cầu của `06-structure.md` mục Open Questions — đoạn "Hàm kiểm đủ điều kiện xử lý": lối nạp dữ liệu chỉ đọc `tool_layer.checks` không có tên tool, cùng loại với `review_readiness_check`. Chấp nhận.

**Sửa:** đặt tên bốn thao tác đầu; thêm tên vào `GLOSSARY.md` mục Agent, graph, node, tool; thêm một dòng bản kê cho mỗi thao tác ở `03-agents.md` — gồm `object_claim_reconcile`, `slot_sensitivity_change` và `operating_mode_transition_reject`.

---

#### AUD-09 — BM25: bắt buộc, được khẳng định, nhưng không được chọn · **Cao**

| Vị trí | Nói gì |
|---|---|
| `CLAUDE.md` mục Ràng buộc domain | "hybrid search (BM25 + vector) cho mã nhân viên và tên riêng" |
| ADR-002, mục Decision | "Hybrid search (BM25 + vector) chạy được trong **một câu truy vấn SQL** kết hợp `tsvector` và `pgvector`" |
| `02-architecture.md` mục Thành phần — `vector_store` | "hybrid search (BM25 + vector)" |
| `03-agents.md` mục Retrieval — Hybrid search | "BM25 hoặc hàm xếp hạng full-text sẵn có… `[CẦN XÁC MINH]` (A-030)" |
| `04-data.md` mục Vector collection — Hybrid search | "hàm xếp hạng full-text lõi của PostgreSQL, **không phải BM25**, cho tới khi A-030 xác minh" |

**Hệ quả.** Chọn một kênh lexical không phải BM25, trong khi `CLAUDE.md` bắt buộc BM25, là một quyết định công nghệ. Luật 4 đòi ADR cho quyết định đó, nhưng hiện nó chỉ nằm trong một câu của `04-data.md` và một giả định. ADR-002 vẫn khẳng định điều ngược lại.

Ghi kèm, không mở lại: `03-agents.md` mục Kênh lexical có việc gì đã báo lý do của `CLAUDE.md` ("mã nhân viên và tên riêng") không có đối tượng, và PO đã quyết giữ nguyên `CLAUDE.md`.

**Sửa đề xuất.** Một ADR mới cho kênh lexical: full-text lõi tạm thời, BM25 qua extension, hay biểu diễn thưa từ model embedding — mỗi phương án bị loại kèm lý do. Sửa câu Decision của ADR-002 cho khớp. `CLAUDE.md`: báo cáo, không sửa.

---

#### AUD-10 — Lượt sửa `GLOSSARY.md`/contract của Phase 11 chưa chạy · **Cao**

`11-ops.md` mục Phát hiện, không tự sửa liệt bảy việc cho "lượt sửa GLOSSARY/contract cho Phase 5 và Phase 8, một phiên riêng". Phiên đó chưa diễn ra. Đầu `11-ops.md` vẫn ghi "còn chờ lượt GLOSSARY/contract".

| Việc ở mục Phát hiện, không tự sửa của `11-ops.md` | Hiện trạng | Xử lý ở |
|---|---|---|
| `reason_code` "Chờ Phase 8" | `GLOSSARY.md` vẫn ghi vậy. Nhưng "`08-hitl.md` đã liệt đủ sáu giá trị" **không đúng** — sáu giá trị không đủ | AUD-02 (a) |
| `notification.event_code` | Chưa có | AUD-02 (c) |
| Thuật ngữ `job_failed` | Chưa vào `GLOSSARY.md`, dù đã vào `DocumentSummary` của `openapi.yaml` | Ở đây |
| `operating_mode_transition_reject` | Chưa vào | AUD-08 |
| Định nghĩa `WARNING` thành danh sách đóng | Chưa sửa; `GLOSSARY.md` mục Enum khác vẫn chỉ nêu ví dụ tự duyệt | Ở đây |
| `BO19_ENVIRONMENT` | Chưa vào `GLOSSARY.md` mục Cấu trúc dự án | Ở đây |
| Enum `ErrorCode` | Chưa sửa | AUD-04 |

**Sửa:** chạy đúng lượt đó, gộp với AUD-02, AUD-04, AUD-05, AUD-08.

---

#### AUD-11 — Nội dung cũ không được sửa ngược sau khi phase sau chốt · **Cao**

**Nguyên nhân gốc chung.** Khi một phase sau giải một câu hỏi, file của phase trước không được sửa lại. Người build đọc phase trước sẽ thấy "TBD" hay "chưa có" ở chỗ đã có giá trị. Các vị trí được gom theo file. Vị trí thuộc AUD khác không lặp lại ở đây.

| File và mục | Câu cũ | Đã giải ở |
|---|---|---|
| `00-domain.md` mục Cấp số văn bản; mục Thể thức văn bản; mục Open Questions; ADR-001 mục Decision | Hạn "trước Phase 4", "trước Phase 7" cho A-009 và mẫu `.docx` | A-009 đổi hạn ở vòng duyệt Phase 6; `12-roadmap.md` cổng 1.6, 1.7 |
| `01-prd.md` NFR-05, quyết định thứ ba của `slot_sensitivity` | Quy tắc hiển thị theo độ nhạy "chưa được đặc tả ở đâu cả" | `09-security.md` mục PII masking và hiển thị theo `slot_sensitivity` |
| `01-prd.md` NFR-06; RISK-07 | Token budget "`TBD`, định cỡ ở Phase 11"; "Không đo được cho tới Phase 11" | `11-ops.md` mục Định cỡ A-022 |
| `01-prd.md` RISK-08 | Tag metadata "đề xuất, chờ duyệt Phase 4" | Đã áp 2026-09-25 (`04-data.md` v0.8) |
| `03-agents.md` mục Agent Registry, hai dòng Token budget | "Giá trị: `TBD` (A-022)" | `11-ops.md` mục Định cỡ A-022 |
| `03-agents.md` mục Checkpointer và PII | Hành vi checkpointer `[CẦN XÁC MINH]`; "lớp một … còn `[CẦN XÁC MINH]`" | A-045 `Đã chốt` ở Phase 6 (trừ vế tuần tự hoá exception) |
| `03-agents.md` mục Open Questions | A-038, A-029, A-034 "owner Phase 8"; A-039 "owner Phase 9"; A-037 "hạn trước Phase 4" | Owner nay là PO (vòng duyệt Phase 12); A-039 `Đã chốt` |
| `04-data.md` mục Vector collection — Lọc quyền và so khớp phòng ban | Vế permission "Thuộc Phase 9" | A-043 `Đã chốt` — `procedure.read_all` |
| `04-data.md` mục Open Questions | A-043, A-045 còn mở; A-038 "owner Phase 8" | Như trên |
| `05-api.md` mục Endpoint — Thao tác của `tool_layer` được đặt tên ở Phase 5 | "danh sách ngoại lệ đóng gồm **hai** mục" | Ba mục từ ADR-019 |
| `05-api.md` mục Lỗi chuẩn hoá (ví dụ); `openapi.yaml` `ErrorEnvelope.trace_id` | Ví dụ `trace_id` 16 ký tự hex; schema không có `format: uuid` | ADR-024: UUID v4 |
| `06-structure.md` mục Cây backend | `endpoint_ops/` — "mười ba thao tác" | Mười bốn (Phase 9), mười lăm nếu tính `operating_mode_transition_reject` |
| `06-structure.md` mục Bước kiểm khởi động, đoạn cuối | "sau khi diff riêng cho file đó được duyệt" | Đã áp 2026-09-25 |
| `06-structure.md` mục Xác minh contract — Chạy lại | "Hai chế độ" | Ba — có `--local-migrated` |
| `06-structure.md` mục Open Questions — đoạn "`llm_usage` còn hai cột `text` không có `CHECK`" | `llm_usage.trace_id` chưa có `CHECK` hình dạng | ADR-024, `0004` |
| `06-structure.md` mục Cây frontend — Tuyến; mục Màn hình hàng đợi duyệt | "đổi `operating_mode` (Phase 9)" không có tuyến; quy tắc che theo độ nhạy "Phase 8, Phase 9 — hôm nay chỉ có chỗ nhận" | Phase 9 chốt endpoint (không chốt tuyến) và chốt quy tắc hiển thị. Tuyến cho `operating_mode`: có chủ đích không có, hay còn thiếu — **cần PO nói** |
| `backend/src/bo19/startup/__init__.py` | "15 bước kiểm khởi động" | 17 bước từ ADR-023 |
| `08-hitl.md` mục Cơ chế dừng khi chạm trần — Hai trần độc lập | Hai giá trị `TBD` | `11-ops.md` mục Định cỡ A-022 |
| `11-ops.md` mục Môi trường Render; mục Background worker & Cron | "chưa áp, xem mục 13"; "`job_failed` — chưa có chỗ đứng trong contract … chưa áp" | Chính mục Đề xuất diff của `11-ops.md`: cả bốn đã áp |
| `11-ops.md` mục Đề xuất diff, dòng `0004` | "Chưa kiểm bằng `tools/contract-checks`" | `--local-migrated` đã áp `0001`–`0005` (vòng duyệt Phase 12; chạy lại ở phase này) |
| `11-ops.md` mục Open Questions; dòng Trạng thái đầu file | A-068 "Mở"; "còn chờ đợt sửa `03-agents.md` riêng cho A-068" | A-068 `Đã chốt` 2026-09-25 |
| `12-roadmap.md` mục Sprint 1 — Deliverable, dòng Dữ liệu | "gồm `0001`–`0004`" | Có `0005` |
| `12-roadmap.md` mục Open Questions — dòng `rate_limit_window`; mục Nợ thiết kế Phase 8, dòng A-068 | "`0005` … **chưa áp**"; A-068 còn là nợ | Đã áp; A-068 `Đã chốt` |
| ADR-003 mục Decision | Khoá object "hash nội dung"; "mọi lần render tạo ra khoá mới" | `03-agents.md` mục Khoá object theo input: hash trên **input**, trùng input thì dùng lại khoá — ghi một lần |
| ADR-011 mục Điều kiện đảo ngược | "Chỗ quan sát này **chưa có** trong bảng … của `_PLAN.md`" | Đã có trong `_PLAN.md` và `11-ops.md` |

**Sửa:** một lượt quét theo từng file, không đổi nghĩa. Riêng dòng tuyến `operating_mode` cần PO trả lời trước.

---

#### AUD-12 — Điều kiện đảo ngược không có chỗ quan sát · **Cao**

`_PLAN.md` Phase 11: "một tín hiệu không có chỗ đo thì không bao giờ phát ra". `11-ops.md` mục Chỗ quan sát cho điều kiện đảo ngược đối chiếu từng dòng của bảng trong `_PLAN.md`. Nhưng chính bảng đó thiếu những tín hiệu mà ADR tự ghi là "đo ở `observability`":

| ADR | Tín hiệu | Có trong `_PLAN.md`/`11-ops.md`? |
|---|---|---|
| ADR-008 | "số truy vấn và latency đọc DB do node gọi LLM gây ra, đặt cạnh latency lượt chat" | **Không** |
| ADR-015, vế công cụ | "bộ nhớ hay thời lượng chuyển đổi của worker tiến sát giới hạn của gói Render đang dùng" | **Không.** Chỉ có vế đóng gói (cold start) và vế PDF (lease) |
| ADR-009 | Đo ở rubric human eval: "văn bản lệch ý giữa các biến sinh ở vòng khác nhau" | `10-eval.md` mục Human eval rubric không có tiêu chí này. Với `V = 1` ở Sprint đầu thì chưa gây hại |

**Sửa:** thêm hai dòng vào bảng chỗ quan sát của `_PLAN.md` (file do PO quản) và `11-ops.md`; thêm một tiêu chí vào rubric của `10-eval.md` khi có template nhiều biến.

---

#### AUD-13 — Giả định: hạn, owner, trạng thái · **Cao**

Không liệt kê 55 dòng `Mở`. Dưới đây chỉ là những dòng có vấn đề.

**(a) Hạn trỏ vào một phase đã qua**

| ID | Hạn đang ghi | Ghi chú |
|---|---|---|
| A-002 | "Trước khi chốt PRD" | PRD đã chốt từ Phase 1 |
| A-024 | "Trước Phase 11" | `12-roadmap.md` đặt ở cổng 2.5 |
| A-030 | "Trước Phase 10" | — |
| A-041 | "Trước Phase 11" | `12-roadmap.md` đặt ở cổng 1.9 — chặn AC Sprint 1 |
| A-022 | "Sau khi Phase 3 … Phase 8 …" | Đã qua; trạng thái vẫn "Thu hẹp" |

**(b) Owner là một phase đã đóng — không còn ai**

A-022 (Phase 11) · A-025 (Phase 11 hoặc người triển khai) · A-031 (Phase 11 — `12-roadmap.md` cổng 1.10 ghi Người triển khai) · A-045 (vế còn lại: Phase 10 — thực tế là canary C2 ở Sprint 2) · A-048 (Phase 9 / Phase 11) · A-057 (Phase 11 + người triển khai) · A-063, A-065 (Phase 11 / người triển khai) · A-061 ("Phase kế").

**(c) Chặn cổng sprint nhưng `ASSUMPTIONS.md` không có owner hoặc hạn**

| ID | Cổng | Owner/hạn ở `ASSUMPTIONS.md` |
|---|---|---|
| A-013 | 1.8 — chặn AC Sprint 1 (`12-roadmap.md` ghi PO) | Trống cả hai |
| A-014 | 2.4 — chặn AC-2.7 | Trống cả hai |
| A-010 | Không có cổng; nhưng lưu trữ theo thời hạn (AUD-07) và đóng phiên nhàn rỗi (AUD-08) đều chờ nó | Trống cả hai |

**(d) Trạng thái hoặc nội dung lệch**

- A-022: cột trạng thái ghi trần `chat_session` "`32.000` **đang hiệu lực** … `46.500` tự động áp khi A-068 đóng". A-068 đã đóng 2026-09-25; `11-ops.md` mục Định cỡ A-022 ghi `46.500` đang hiệu lực.
- A-062, A-024: hạn ở `ASSUMPTIONS.md` (trước `PRODUCTION`; trước Phase 11) khác cổng ở `12-roadmap.md` (2.7, 2.5). `ASSUMPTIONS.md` là nơi duy nhất giữ hạn, nên chỗ phải sửa là `ASSUMPTIONS.md`.

**Sửa:** PO gán owner là **người** cho các dòng ở (b), (c); đổi hạn ở (a), (d) sang cổng sprint của `12-roadmap.md`.

---

#### AUD-14 — `ExtractSlotsResult` không biểu diễn được slot `LIST` · **Cao**

| Vị trí | Nói gì |
|---|---|
| `07-prompts.md` mục Output contract — P2 | `value`: `string` · `number` · `boolean` · `null`. Không có mảng |
| `03-agents.md` mục Allowlist input — `extract_slots` | Output của `INTRODUCTION_LETTER` gồm `accompanying_persons` |
| `00-domain.md` mục Slot schema — `INTRODUCTION_LETTER` | `accompanying_persons`: kiểu `list` |
| `04-data.md` mục Bảng chi tiết — `slot_definition` | `data_type` gồm `LIST`; `12-roadmap.md` tiêu chí T5 cho loại thứ ba dùng mọi kiểu đã có |

**Hệ quả.** Slot tuỳ chọn `accompanying_persons` của loại Sprint 3 không trích được qua chat. `request_slots_write` không có đường nào khác.

Cùng mục của `07-prompts.md`, lệch nhỏ: schema của P4/P5 viết cứng `maxLength: 2000`, trong khi câu dưới nó nói `maxLength` lấy từ `template_variable.max_length`.

**Sửa:** cho `value` nhận mảng chuỗi; ghi rõ `maxLength` là chỗ `ai_gateway` điền lúc gọi, cùng khuôn `<…>` của ADR-025.

---

#### AUD-15 — `delegation` mang hai nghĩa; một điều kiện Must dựa vào nó · **Cao**

| Vị trí | Nghĩa |
|---|---|
| `GLOSSARY.md` mục Entity; `08-hitl.md` mục Định tuyến ký và uỷ quyền vắng mặt | Hành động thay người khác khi vắng mặt — phía người duyệt |
| `00-domain.md` EC-IL-01; `01-prd.md` F1, định nghĩa "Yêu cầu đủ điều kiện xử lý" điều 4; `04-data.md` mục Bảng chi tiết — `delegation` | Người mang giấy uỷ cho người lập quyền tạo yêu cầu nhân danh mình — phía nhân viên |

`delegation` là `[Should]`: `delegation.manage` không thuộc gói vai trò nào, và endpoint tạo uỷ quyền mang `x-bo19-scope: Should`. Vậy trong Sprint đầu không có cách tạo một `delegation`. Trong khi đó EC-IL-01 là một ca nhóm E của bộ eval, chấm bằng M6 — metric Bất biến. A-052 đã ghi phần nhập hộ, nhưng không ghi rằng một từ đang mang hai nghĩa.

**Sửa đề xuất.** PO quyết trong cùng lượt A-052 (cổng Sprint 3): tách hai khái niệm, hoặc định nghĩa lại `delegation` bao được cả hai, và nêu đường tạo trong Sprint đầu — hoặc bỏ vế `delegation` khỏi điều 4 của F1.

---

#### AUD-16 — Skeleton backend lệch `06-structure.md` · **Cao**

| Vị trí | Vấn đề |
|---|---|
| `backend/src/bo19/api/app.py` và `backend/src/bo19/api/app/__init__.py` | Một module và một package **cùng tên** trong cùng thư mục. Python nhập package, module `app.py` không bao giờ được nạp. `06-structure.md` mục Cây backend chỉ có `app.py` |
| `backend/src/bo19/api/routers/health.py` | Khai `GET /health`. Endpoint này không có trong `05-api.md` hay `openapi.yaml` — trái "khớp 100%". Không file nào của `docs/design/` bàn tới health check của Render |
| `backend/src/bo19/ai_gateway/gateway/` | `06-structure.md` ghi `gateway.py` là **lối vào duy nhất**; skeleton là một package |
| `backend/src/__init__.py` | Biến `src` thành package, trong khi `06-structure.md` đặt package gốc là `bo19` |

**Sửa đề xuất.** Bỏ một trong hai `app`. PO quyết `/health`: thêm vào contract (`05-api.md`, `openapi.yaml`) kèm lý do từ ràng buộc Render, hoặc xoá router. Đồng bộ `gateway` và `src/__init__.py` với `06-structure.md`.

---

#### AUD-17 — Tham chiếu chéo theo số dòng và số mục (luật 12) · **Thấp**

| File | Dạng | Số chỗ |
|---|---|---|
| `08-hitl.md` | `file.md:dòng` | 31 |
| `07-prompts.md` | `file.md:dòng`; một chỗ theo số mục | 16 + 1 |
| `09-security.md` | "mục N của `file`" | 12 |
| `10-eval.md` | "mục N của `file`" / "`file` mục N" | 10 |
| `04-data.md` | "mục N của `file`" | 5 |
| `ASSUMPTIONS.md` | "mục N của `file`" | 3 |
| `11-ops.md` | "mục 12 của `ASSUMPTIONS.md`" — **`ASSUMPTIONS.md` không có mục 12** (chỉ có mục 1, 2) | 2 |
| ADR-020, ADR-024 | "mục N của `file`" — ADR-024 cũng trỏ tới "mục 12 của `ASSUMPTIONS.md`" không tồn tại | 1 + 1 |
| `openapi.yaml` (phần mô tả extension) | "`GLOSSARY.md` mục 12, `05-api.md` mục 2.1" | 1 |
| Docstring của `backend/`, chú thích của `frontend/` | "`06-structure.md:3`", "`05-api.md:2`" | 30 |

Số dòng đã trôi, có bằng chứng. `08-hitl.md` trỏ "`03-agents.md:192`" cho sáu thao tác cổng; nay dòng đó rơi vào đoạn giải thích tool ở mục Chi tiết từng tool, còn mục Thao tác cổng bắt đầu sau đó. `07-prompts.md` trỏ "`GLOSSARY.md:325`" cho biến nội dung tự do; bảng đó nay nằm ở chỗ khác.

**Sửa:** thay bằng tên mục. Việc cơ học, không đổi nghĩa.

---

#### AUD-18 — Số phiên bản đầu file lệch ghi chú · **Thấp**

| File | Đầu file | Ghi chú phiên bản cao nhất | Hướng sửa |
|---|---|---|---|
| `02-architecture.md` | 0.8 | v0.10 | Nâng đầu file lên **0.10** |
| `04-data.md` | 0.3 | v0.10 | Nâng lên **0.10** |
| `06-structure.md` | 0.4 | v0.5 | Nâng lên **0.5** |

Cùng họ lỗi đã sửa ở `03-agents.md` (v0.12) và `05-api.md` (v0.10).

---

#### AUD-19 — Truy vết endpoint ↔ feature; ID requirement · **Thấp**

- **8 operation không có `x-bo19-feature`:** `POST`/`DELETE /auth/session`, `GET /me`; `POST`/`GET /operating-mode/transitions`; ba endpoint `/delegations`. Chúng truy được về NFR-03 (chế độ vận hành), về dòng Should "Định tuyến ký nhiều cấp, `SIGNER`, uỷ quyền" ở mục Scope & priority của `01-prd.md`, và về điều 1 của mục Definition of Done.
- **Đăng nhập không có feature hay NFR nào trong PRD**, dù MVP ở mục Phạm vi của `CLAUDE.md` là "đăng nhập 2 vai trò". AuthN được thiết kế đầy đủ ở `05-api.md` và `09-security.md`; chỉ thiếu mắt xích truy vết.
- **Luật 8 đòi ID ổn định `FR-xx`, `US-xx`.** PRD dùng F1–F6; user story đánh số trong từng feature; AC không có ID. `12-roadmap.md` tự đặt ID `AC-n.m` cho AC của sprint, không phải của PRD.

**Sửa đề xuất.** Thêm `x-bo19-feature` (giá trị NFR hoặc Scope) cho 8 operation. PO quyết có đặt ID cho AC của PRD không — nếu có, dùng dạng `F1-AC-n` để không phải đổi F1–F6.

---

#### AUD-20 — Tên lệch · **Thấp**

| Tên | Chỗ lệch | Nguồn đúng |
|---|---|---|
| `signer_user_id` (slot và biến — `00-domain.md`, `01-prd.md`, `03-agents.md`, `GLOSSARY.md`) ↔ cột `document.signer_employee_id` (`04-data.md`) | Từ `user` không có trong từ vựng — entity là `employee`. Ánh xạ đã ghi ở `04-data.md` ("Biến `signer_user_id`") | `GLOSSARY.md`; nên đổi tên biến thành `signer_employee_id` |
| `beneficiary_employee_id` | `00-domain.md` mục Slot schema: kiểu `string`, "mặc định bằng `requester_employee_code`" — lẫn **mã** nhân viên với **id**; DDL là `uuid` FK | `04-data.md` |
| `VALIDATION_FAILED` | Vừa là `error_code` (422, lỗi body) ở `05-api.md`, vừa là `reason_code` của `document_halt` ở `08-hitl.md` và `10-eval.md` (trượt `validate_free_content`) | Đổi tên `reason_code`, ví dụ `FREE_CONTENT_INVALID` — cùng lượt AUD-02 (a) |

---

#### AUD-21 — Trích dẫn chưa xác minh được · **Thấp**

Không có bản gốc trong `docs/reference/`, nên theo quy tắc trích dẫn của `CLAUDE.md` chúng chưa được phép dùng làm căn cứ. **Không** kết luận chúng sai.

| Vị trí | Trích dẫn |
|---|---|
| `05-api.md` mục Quy ước chung | RFC 3339 |
| `openapi.yaml` | ISO 8601 |
| `07-prompts.md` mục Output contract; `10-eval.md` mục `EvalCase` | JSON Schema draft 2020-12 |
| ADR-024; `11-ops.md` mục Log schema | W3C Trace Context "16 byte, 32 ký tự hex" |
| `11-ops.md` mục Định cỡ A-022, dòng `embed_query` | "~100–150 token" cho 200 ký tự — nhãn "ước lượng có căn cứ", nhưng căn cứ quy đổi ký tự ra token không có nguồn |
| `09-security.md` mục AuthN; ADR-021 | Tính chất của `argon2id`, `scrypt`, `bcrypt`, `PBKDF2` — tự ghi là "tính chất công bố", không có bản gốc |

**Sửa:** thêm bản gốc vào `docs/reference/`, hoặc gắn `[CẦN XÁC MINH]`.

---

#### AUD-22 — Lỗi nội bộ nhỏ · **Thấp**

| Vị trí | Lỗi |
|---|---|
| `01-prd.md` mục Goals & metrics | "Số người, số ca và người chấm chốt ở mục 9" — mục 9 là Risk register; nơi đúng là A-020 |
| `01-prd.md` mục Definition of Done, điều 1 | Hành trình "duyệt nội dung → duyệt dấu → cấp số" bỏ bước ký, trong khi vòng đời bắt buộc `PENDING_SIGNATURE`. `12-roadmap.md` mục Sprint 1 có bước ký |
| `01-prd.md` M4 | "đi qua đủ hai cổng HITL" — không nói cổng 2 chỉ áp khi `requires_seal` (NFR-01 thì có nói) |
| `05-api.md` dòng phiên bản v0.8; `09-security.md` mục `operating_mode_change` | "Endpoint có contract: 48 → 49". Thêm hai operation nên phải là **48 → 50**; đếm thật: 50 |
| `10-eval.md` mục Phạm vi và nguyên tắc | "Ba việc PRD không phủ" rồi liệt bốn; câu kết "Cả ba việc trên" |
| `07-prompts.md` mục Catalog prompt module | ID `P1`–`P5` trùng dạng với nhãn ưu tiên `P0/P1/P2` bị cấm ở `_PLAN.md`. Không vi phạm vì là ID, không phải mức ưu tiên — ghi để người đọc không nhầm |

---

## 5. Việc được giao cho Phase 13

Ba nơi giao việc đích danh cho phase này. Theo quy tắc chỉ báo cáo, dưới đây là khuyến nghị, không phải quyết định.

| # | Việc | Giao ở | Khuyến nghị |
|---|---|---|---|
| 1 | Duyệt hai index đề xuất: `ix_request_waiting ON request (status_changed_at, id) WHERE status IN (…4 trạng thái mở…)` cho `GET /requests?scope=ALL` — AC Must của F4; `ix_document_awaiting_issue ON document (status_changed_at, id) WHERE status IN ('SIGNED','SEALED')` cho `GET /issue-queue` | `05-api.md` mục Open Questions ("Phase 13 duyệt các đề xuất này") | **Nhận cả hai**, thêm bằng một migration `0006` theo tiền lệ `0003`. Hình dạng đúng khuôn của `ix_document_review_queue`. Chưa có index thì sắp xếp vẫn đúng, chỉ chậm — không chặn Sprint 1. Chưa có migration nào chứa chúng |
| 2 | Có đổi tên "Sprint đầu" không | `12-roadmap.md` mục Open Questions — dòng "Tên 'Sprint đầu' dễ đọc lẫn với Sprint 1" | **Không đổi.** `GLOSSARY.md` mục Thuật ngữ nghiệp vụ đã định nghĩa tách "Sprint đầu" với "Sprint 1", và audit này không thấy chỗ nào dùng lẫn |
| 3 | Lối nạp `tool_layer.checks` không có tên tool | `06-structure.md` mục Open Questions — đoạn "Hàm kiểm đủ điều kiện xử lý" ("để Phase 13 không coi là thiếu") | Đã ghi nhận ở AUD-08 — không tính lỗi |

---

## 6. Đã kiểm, không có lỗi

- Tên trạng thái của `request` (10), `document` (13), `room_booking` (5) khớp giữa `GLOSSARY.md`, mọi sơ đồ, `CHECK` của `schema.sql` và enum của `openapi.yaml`.
- Mọi enum đã nâng lên `GLOSSARY.md` khớp `CHECK` của DDL và enum của `openapi.yaml`. `job_type` (6), `call_name` (7), tên node `interrupt` (6), `decision_kind` (13) khớp giữa `GLOSSARY.md` và DDL; `ReviewSignal.kind` ở mục State schema của `03-agents.md` là tập con đúng của `decision_kind`.
- 20 tool ở mục Tool Registry của `03-agents.md` đều có ở `GLOSSARY.md`, đều có nhóm caller ở mục Ai được gọi tool nào.
- Danh mục permission 25 mục và gói ba vai trò khớp giữa `00-domain.md`, `GLOSSARY.md`, `0001_permission_catalog.sql`. Mọi permission ở `x-bo19-permission` đều thuộc danh mục.
- Không `A-`, `D-`, `ADR-`, `RISK-`, `EC-` nào bị trỏ tới mà không tồn tại.
- 31 sơ đồ Mermaid render được, không sơ đồ nào quá 20 node. `openapi.yaml` hợp lệ.
- `check_grants.py`: `--local` 169/63/**0**; `--local-migrated` 176/68/**0**. `0001_initial.sql` trùng sha256 với `contracts/schema.sql`.
- Năm đề xuất ở `proposals/` đều `✅ Đã áp`, và đích của chúng đã nhận thay đổi.
- Không có nhãn `[MVP]`/`[ADVANCED]`; mức MoSCoW chỉ khai ở mục Scope & priority của `01-prd.md` — nơi khác chỉ tham chiếu.
- Mọi endpoint của `openapi.yaml` có sprint ở `12-roadmap.md` mục Endpoint → sprint (đếm tay 50/50).

---

## 7. Thứ tự sửa đề xuất

Gom theo file, để mỗi lượt chạm ít file và mỗi file chỉ mở một lần. Cổng 1.2 của `12-roadmap.md` đòi mọi lỗi của audit này **có quyết định sửa hay không** trước khi khởi động Sprint 1 — không đòi sửa xong hết.

| Đợt | Việc | AUD | File chạm | Trước cổng |
|---|---|---|---|---|
| 0 — PO quyết | Hướng (a)/(b) của `request → APPROVED`; từng việc (a)–(h) của nợ Phase 8, gồm D-006 với thu hồi; cách biểu diễn schema sau migration; ADR kênh lexical; hai nghĩa của `delegation`; `/health`; tuyến `operating_mode`; owner là người cho các giả định ở AUD-13; ID cho AC của PRD; hai index | 01, 02, 03, 07, 09, 11, 13, 15, 16, 19, §5 | — | Sprint 1 (cổng 1.2) |
| 1 — Contract | Enum `ErrorCode` và `details`; bỏ `x-bo19-permission-status`; `x-bo19-feature` cho 8 operation; `trace_id` `format: uuid`; `contracts/README.md` hoặc chú thích cho `schema.sql`; migration `0006` nếu nhận index | 03, 04, 05, 11, 19, §5 | `openapi.yaml`, `05-api.md`, `contracts/`, `backend/migrations/schema/` | Sprint 1 |
| 2 — Tên và thao tác | Lượt `GLOSSARY.md` của `11-ops.md`; đặt tên bốn thao tác; bản kê ở `03-agents.md`; áp hướng đã chọn của AUD-01 vào `00-domain.md`, `02-architecture.md`, `03-agents.md`; cạnh của AUD-07; đổi tên ở AUD-20; skeleton | 01, 05, 07, 08, 10, 16, 20 | `GLOSSARY.md`, `00-domain.md`, `02-architecture.md`, `03-agents.md`, `backend/src/` | Sprint 1 |
| 3 — Phase 8 | Sửa phần sai và giao phần thiếu của `08-hitl.md`; thêm vế EC-CV-02 vào A-053 | 02, 06, 07 | `08-hitl.md`, `ASSUMPTIONS.md` | Sprint 2 (cổng 2.2) |
| 4 — Quét nội dung cũ | Từng file theo bảng AUD-11; hạn và owner ở `ASSUMPTIONS.md`; hai dòng chỗ quan sát; schema P2 | 11, 12, 13, 14, 22 | Mọi file phase, `_PLAN.md` (PO), `ASSUMPTIONS.md`, `07-prompts.md` | Sprint 1 — rẻ, và đợt 2 đã mở phần lớn các file này |
| 5 — Cơ học | Tham chiếu theo tên mục; số phiên bản; trích dẫn | 17, 18, 21 | Mọi file có trong bảng | Bất kỳ lúc nào; gộp được với đợt 4 |

**Việc chạm `CLAUDE.md` — chỉ báo cáo, chờ PO (luật 11):** mục Ràng buộc domain (BM25, AUD-09) và mục Cấu trúc output (`backend/migrations/` là nơi chứa DDL sau Phase 6, AUD-03).

---

## Open Questions

Không có giả định mới và không có ADR mới ở phase này. Mọi câu hỏi dưới đây là quyết định, liệt ở đợt 0 của mục 7:

1. **AUD-01** — `request → APPROVED` theo hướng (a) (ở `document_sign`) hay (b) (thêm cạnh vào máy trạng thái `request`)?
2. **AUD-02** — mỗi việc (a)–(h): sửa `08-hitl.md` có phép, hay mở dòng `A-xxx` đặt vào cổng sprint? Với (f): thiết kế đường thoát tự duyệt cho thu hồi, hay sửa D-006?
3. **AUD-03** — biểu diễn schema sau migration theo (i), (ii) hay (iii)?
4. **AUD-09** — có viết ADR cho kênh lexical ngay bây giờ, hay đợi A-030?
5. **AUD-15** — `delegation` tách thành hai khái niệm, hay giữ một khái niệm và định nghĩa lại?
6. **AUD-16, AUD-11** — `GET /health` có vào contract không; đổi `operating_mode` có tuyến trên `client` không?
7. **AUD-13** — ai là owner (người) cho các giả định đang có owner là một phase đã đóng?
8. **AUD-19** — đặt ID cho AC của PRD, hay giữ nguyên?

---

## Phụ lục A — Lệnh đã chạy và script

Mọi script nằm ở scratchpad của phiên, ngoài repo; nội dung ghi dưới đây đủ để chạy lại. Chạy từ gốc repo, trên Windows cần `PYTHONIOENCODING=utf-8`. Không lệnh kiểm nào ghi vào repo: `git status` sau khi chạy chỉ thấy hai file của chính phase này.

### A.1 `audit_openapi.py` — liệt kê operation và enum của `openapi.yaml`

```python
import yaml
spec = yaml.safe_load(open("docs/design/contracts/openapi.yaml", encoding="utf-8"))
for path, item in spec["paths"].items():
    for m, op in item.items():
        if m in ("get", "post", "put", "patch", "delete"):
            print(m.upper(), path, op.get("operationId"), op.get("x-bo19-scope"),
                  op.get("x-bo19-permission"), op.get("x-bo19-operation"))
def enums(n, trail):
    if isinstance(n, dict):
        if "enum" in n: print(".".join(trail), n["enum"])
        for k, v in n.items(): enums(v, trail + [str(k)])
    elif isinstance(n, list):
        for i, v in enumerate(n): enums(v, trail + [str(i)])
enums(spec["components"], [])
```

Và `grep -n "IN (" docs/design/contracts/schema.sql` cho các `CHECK` enum.

### A.2 `audit_api_trace.py` — `05-api.md` ↔ `openapi.yaml`, mã lỗi

```python
import re, yaml
D = "docs/design/"
spec = yaml.safe_load(open(D + "contracts/openapi.yaml", encoding="utf-8"))
oa = {(m.upper(), p): op for p, it in spec["paths"].items() for m, op in it.items()
      if m in ("get", "post", "put", "patch", "delete")}
api = open(D + "05-api.md", encoding="utf-8").read()
sec2 = api.split("## 2. Endpoint", 1)[1].split("## 3. SSE", 1)[0]
md, cur = {}, None
for line in sec2.splitlines():
    if line.startswith("### "): cur = line[4:]
    m = re.match(r"\|\s*(GET|POST|PUT|DELETE|PATCH)\s*\|\s*`([^`]+)`", line)
    if m: md[(m.group(1), m.group(2).split("?")[0])] = cur
ngoai = {k for k, s in md.items() if "NGOÀI-OPENAPI" in s}
print(len(md), len(oa), sorted(set(md) - set(oa) - ngoai), sorted(set(oa) - set(md)))
print([k for k, op in oa.items() if not op.get("x-bo19-feature")])
print([k for k, op in oa.items() if op.get("x-bo19-permission-status")])
cat = api.split("### 4.1", 1)[1].split("### 4.2", 1)[0]
md_codes = set(re.findall(r"^\|\s*`([A-Z_]+)`", cat, re.M))
oa_codes = set(spec["components"]["schemas"]["ErrorCode"]["enum"])
print(len(md_codes), len(oa_codes), md_codes - oa_codes, oa_codes - md_codes)
```

Kết quả: 54 dòng ở `05-api.md` (50 + 4 `[NGOÀI-OPENAPI]`), 50 operation, không lệch method–path; 8 operation không có `x-bo19-feature`; 6 operation mang `x-bo19-permission-status`; 35 so với 33 mã.

### A.3 ID treo và định danh lạ

```python
import re, glob, collections
fs = glob.glob("docs/design/*.md") + glob.glob("docs/design/decisions/*.md") \
   + glob.glob("docs/design/contracts/*") + glob.glob("docs/design/proposals/*.md")
t = {f: open(f, encoding="utf-8").read() for f in fs}
A = set(re.findall(r"^\| (A-\d{3}) \|", t["docs/design/ASSUMPTIONS.md"], re.M))
EC = set(re.findall(r"^\| (EC-[A-Z]{2}-\d{2}) \|", t["docs/design/00-domain.md"], re.M))
for f, s in t.items():
    for x in re.findall(r"\bA-\d{3}\b", s):
        if x not in A: print("A treo", x, f)
    for x in re.findall(r"\bEC-[A-Z]{2}-\d{2}\b", s):
        if x not in EC: print("EC treo", x, f)
# Tương tự cho D- (bảng Quyết định của 00-domain.md), ADR- (tên file), RISK- (01-prd.md).
known = set(re.findall(r"[a-z][a-z0-9_]*", t["docs/design/GLOSSARY.md"]
        + t["docs/design/contracts/schema.sql"] + t["docs/design/contracts/openapi.yaml"]
        + "".join(open(m, encoding="utf-8").read() for m in glob.glob("backend/migrations/*/*.sql"))))
bad = collections.defaultdict(set)
for f, s in t.items():
    if f.endswith("CHANGELOG.md"): continue
    for x in re.findall(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`", s):
        if x not in known: bad[x].add(f)
for k, v in sorted(bad.items()): print(k, sorted(v))
```

Thống kê `ASSUMPTIONS.md`: tách cột 5–7 của mỗi dòng `| A-xxx |`, đếm theo tiền tố của cột Trạng thái → 55 `Mở`, 17 `Đã chốt`, 3 `Thu hẹp`, 1 `Bác bỏ`.

### A.4 Mermaid

```bash
# Trích mọi khối ```mermaid ra <scratchpad>/mmd/<file>__L<dòng>.mmd (python, regex ```mermaid\n(.*?)```)
cd <scratchpad>
for f in mmd/*.mmd; do
  npx -y -p @mermaid-js/mermaid-cli mmdc -i "$f" -o "svg/$(basename "$f" .mmd).svg" || echo "FAIL $f"
done
```

`mmdc` 12.0.0, chạy trong scratchpad; không thêm `package.json` hay phụ thuộc nào vào repo. Đếm node: tách định danh node của `graph`/`flowchart`, trạng thái của `stateDiagram-v2`, entity của `erDiagram`, participant của `sequenceDiagram` — lớn nhất là 17. So cạnh: tách `A --> B` của ba sơ đồ `document` (`00-domain.md`, `02-architecture.md`, `08-hitl.md`) rồi lấy hiệu tập hợp.

### A.5 Luật 12

```bash
cd docs/design
grep -oE '[A-Za-z0-9_-]+\.md:[0-9]+' 07-prompts.md 08-hitl.md | cut -d: -f1 | uniq -c
grep -oE "mục [0-9]+(\.[0-9]+)*[a-z]? (của|trong|ở) \`[^\`]+\`|\`[0-9A-Za-z_-]+\.(md|yaml|sql)\` mục [0-9]+(\.[0-9]+)*" *.md decisions/*.md
grep -rhoE "\.md:[0-9]+(\.[0-9]+)?" ../../backend ../../frontend --include=*.py --include=*.ts --include=*.tsx --include=*.js | wc -l
```

### A.6 Contract và quyền

```bash
cd tools/contract-checks
PYTHONIOENCODING=utf-8 .venv/Scripts/python check_grants.py --local            # 169 / 63 / Lệch 0, thoát 0
PYTHONIOENCODING=utf-8 .venv/Scripts/python check_grants.py --local-migrated   # 176 / 68 / Lệch 0, thoát 0
sha256sum docs/design/contracts/schema.sql backend/migrations/schema/0001_initial.sql   # trùng 0ce8dd…
# openapi: venv riêng trong scratchpad, pip install openapi-spec-validator (0.9.0)
python -c "from openapi_spec_validator import validate; from openapi_spec_validator.readers import read_from_filename; validate(read_from_filename('docs/design/contracts/openapi.yaml')[0])"
```
