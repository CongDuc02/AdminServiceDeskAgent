# GLOSSARY — BO-19 Admin Service Desk Agent

**Phiên bản:** 0.11 · **Chốt tại:** Phase 0, bổ sung ở Phase 2, Phase 3 và các vòng sửa Phase 3

> Đây là danh sách tên chuẩn. Từ Phase 1 trở đi, mọi tài liệu, diagram, DDL, endpoint và prompt phải dùng **đúng** các định danh trong file này. Muốn đổi tên thì sửa file này trước, rồi ghi vào [`CHANGELOG.md`](./CHANGELOG.md).

**Quy ước:** định danh kỹ thuật viết `snake_case` cho entity/trường, `UPPER_SNAKE_CASE` cho giá trị enum và trạng thái, `entity.action` cho permission. Diễn giải bằng tiếng Việt, thuật ngữ kỹ thuật giữ nguyên tiếng Anh.

**Ưu tiên:** file này không ghi mức MoSCoW — mức ưu tiên chốt một lần ở mục Scope & priority của PRD. Nhãn `[Should]`/`[Could]` chỉ đánh dấu hạng mục sẽ bị cắt khỏi Sprint đầu.

---

## 1. Entity

| Định danh | Tên tiếng Việt | Định nghĩa |
|---|---|---|
| `employee` | Nhân viên | Người dùng của hệ thống. Bảng trên PostgreSQL, import thủ công CSV, có cột `source` và `synced_at` |
| `request` | Yêu cầu | Một lần nhân viên đề nghị phòng hành chính làm gì đó. Là đơn vị theo dõi trạng thái mà nhân viên nhìn thấy |
| `request_type` | Loại yêu cầu | Phân loại yêu cầu, quyết định slot schema, người duyệt và có cần dấu hay không |
| `document` | Văn bản | Văn bản hành chính do hệ thống sinh từ `template`. Có vòng đời riêng, độc lập với `request` |
| `external_document` | Văn bản ngoài | `[Could]` File do nhân viên tải lên, không do hệ thống soạn. Chỉ dùng làm đích của `seal_action` |
| `template` | Mẫu văn bản | File `.docx` do người soạn, **chứa sẵn toàn bộ khung thể thức** và các biến thay thế. Được quản lý phiên bản. Agent chỉ điền biến, không sửa khung (ADR-001) |
| `document_register` | Sổ văn bản | Sổ cấp số văn bản, nguồn sự thật duy nhất về `document_number`. Định dạng số là **cấu hình**, không hardcode |
| `seal_register` | Sổ theo dõi con dấu | Sổ ghi mọi lần sử dụng con dấu, tách biệt với `document_register` |
| `seal_action` | Lần sử dụng con dấu | Một lần đóng một loại dấu lên một văn bản đích |
| `room` | Phòng họp | Tài nguyên đặt được, có sức chứa và thiết bị |
| `room_booking` | Lượt đặt phòng | `[Should]` Artifact của một `request` loại `ROOM_BOOKING`, có máy trạng thái riêng |
| `approval_step` | Bước duyệt | Một lần một người được yêu cầu duyệt, ký hoặc duyệt dấu. Mang cờ `self_approved` và `self_approval_reason` khi rơi vào đường thoát ở mục Tách biệt trách nhiệm của `00-domain.md` |
| `permission` | Quyền | Đơn vị phân quyền nhỏ nhất, dạng `entity.action`. Vai trò chỉ là gói permission |
| `audit_event` | Sự kiện kiểm toán | Bản ghi bất biến về một hành động có ảnh hưởng nghiệp vụ. Có mức `severity` |
| `delegation` | Uỷ quyền | Cho phép một người hành động thay người khác trong một khoảng thời gian |
| `chat_session` | Phiên hội thoại | Một cuộc chat của nhân viên với `intake_agent`. Sinh được 0..n `request` nối tiếp (EC-CV-01, EC-CV-02). Thêm ở Phase 3 |
| `chat_message` | Tin nhắn | Một lượt trong `chat_session`. Văn bản tin nhắn xếp `RES` vì mang được mọi thứ; bị xoá khi `request` gắn với nó `EXPIRED` (A-014). Thêm ở Phase 3 |
| `procedure_document` | Tài liệu quy trình | Tài liệu quy trình hành chính nội bộ, nạp vào `vector_store` để trả hướng xử lý thủ công có trích nguồn. Có phiên bản; không chứa PII. Kho có thể rỗng (A-027). Thêm ở Phase 3 |

---

## 2. Vai trò

| Định danh | Tên tiếng Việt | Phạm vi |
|---|---|---|
| `EMPLOYEE` | Nhân viên | Tạo và theo dõi yêu cầu của chính mình |
| `ADMIN_OFFICER` | Cán bộ hành chính | Duyệt, duyệt dấu, cấp số, phát hành, quản lý mẫu văn bản |
| `SIGNER` | Người ký cấp trên | `[Should]` Ký và duyệt ở cấp cao hơn. Chưa có trong Sprint đầu |

Vai trò là **gói permission**, không phải đơn vị phân quyền. Mọi kiểm tra quyền phải hỏi permission, không hỏi tên vai trò. Danh mục permission và gói theo vai trò ở mục Permission và vai trò của `00-domain.md`.

---

## 3. Mã loại yêu cầu — `request_type`

| Định danh | Tên tiếng Việt | Artifact | Phạm vi |
|---|---|---|---|
| `WORK_CONFIRMATION` | Giấy xác nhận công tác | `document` | — |
| `INTRODUCTION_LETTER` | Giấy giới thiệu | `document` | — |
| `ROOM_BOOKING` | Đặt phòng họp | `room_booking` | `[Should]` |
| `SEAL_REQUEST` | Yêu cầu đóng dấu cho văn bản ngoài | `seal_action` | `[Could]` |
| `INCOME_CONFIRMATION` | Giấy xác nhận thu nhập | `document` | `[Could]` `[ĐỀ XUẤT]` |
| `BUSINESS_TRIP_ORDER` | Quyết định cử đi công tác | `document` | `[Could]` `[ĐỀ XUẤT]` |

---

## 4. Trạng thái `request`

Một máy trạng thái duy nhất, dùng chung cho mọi `request_type`.

| Định danh | Tên tiếng Việt | Kết thúc? |
|---|---|---|
| `DRAFT` | Đang soạn | Không |
| `NEEDS_INFO` | Chờ bổ sung thông tin | Không |
| `SUBMITTED` | Đã gửi | Không |
| `IN_REVIEW` | Đang chờ duyệt | Không |
| `CHANGES_REQUESTED` | Bị yêu cầu sửa | Không |
| `APPROVED` | Đã duyệt | Không |
| `FULFILLED` | Đã hoàn tất — mọi artifact đã tới trạng thái cuối | Có |
| `REJECTED` | Bị từ chối | Có |
| `CANCELLED` | Đã huỷ | Có |
| `EXPIRED` | Hết hạn chờ bổ sung | Có |

Quá hạn SLA **không** phải trạng thái. Đó là điều kiện dẫn xuất từ `due_at`, biểu diễn bằng cờ `sla_breached`.

---

## 5. Trạng thái `document`

| Định danh | Tên tiếng Việt | Ghi chú |
|---|---|---|
| `DRAFT` | Bản nháp | Nội dung còn sửa được |
| `PENDING_APPROVAL` | Chờ duyệt nội dung | Cổng HITL số 1 · `document.approve_content` |
| `CHANGES_REQUESTED` | Bị yêu cầu sửa | |
| `REJECTED` | Bị từ chối | |
| `APPROVED` | Đã duyệt nội dung | Từ đây nội dung bất biến |
| `PENDING_SIGNATURE` | Chờ ký | |
| `SIGNED` | Đã ký | |
| `PENDING_SEAL` | Chờ đóng dấu | Cổng HITL số 2 · `document.apply_seal` |
| `SEALED` | Đã đóng dấu | |
| `ISSUED` | Đã phát hành | `document.issue` · thời điểm duy nhất cấp `document_number` |
| `REVOKED` | Đã thu hồi | Mất hiệu lực, vẫn truy xuất được |
| `SUPERSEDED` | Bị thay thế | Trỏ tới văn bản thay thế |
| `ARCHIVED` | Đã lưu trữ | |

---

## 6. Trạng thái `room_booking` `[Should]`

| Định danh | Tên tiếng Việt |
|---|---|
| `HELD` | Đang giữ chỗ |
| `CONFIRMED` | Đã xác nhận |
| `RELEASED` | Đã nhả chỗ |
| `CANCELLED` | Đã huỷ |
| `COMPLETED` | Đã diễn ra |

---

## 7. Permission

Định danh dạng `entity.action`. Danh mục đầy đủ, gói theo vai trò và quy tắc tách biệt trách nhiệm ở mục Permission và vai trò của `00-domain.md`.

`request.create` · `request.create_on_behalf` · `request.read_own` · `request.read_assigned` · `request.read_all` · `request.supply_info` · `request.cancel_own` · `document.approve_content` · `document.request_changes` · `document.reject` · `document.sign` · `document.apply_seal` · `document.issue` · `document.revoke_initiate` · `document.revoke_confirm` · `template.manage` · `procedure.manage` · `employee.import` · `booking.confirm` `[Should]` · `delegation.manage` `[Should]` · `audit.read_own` · `audit.read_all`

`document.issue` và `document.apply_seal` là hai permission tách rời, không bao giờ gộp. **Không tồn tại** permission xoá hay sửa `audit_event`.

---

## 8. Enum khác

**`slot_source` — nguồn dữ liệu của slot**

`USER_INPUT` · `HR_PROFILE` · `RESOURCE_CATALOG` · `UPLOAD` · `SYSTEM`

**`slot_sensitivity` — độ nhạy của dữ liệu trong một slot**

| Mã | Tên | Nghĩa |
|---|---|---|
| `INT` | `INTERNAL` | Dữ liệu tổ chức hoặc tham chiếu, không tự nó nhận dạng cá nhân |
| `PER` | `PERSONAL` | Nhận dạng một cá nhân cụ thể |
| `RES` | `RESTRICTED` | Định danh pháp lý, hoặc nội dung suy ra được tình trạng sức khoẻ, pháp lý, tài chính |

Là thuộc tính của **dữ liệu**, không suy ra từ tên trường hay từ `slot_source`. Ba quyết định key theo đây: mask trong log kỹ thuật, giữ hay xoá khi `EXPIRED`, và cách hiển thị trên màn hình duyệt. **Slot nào được vào prompt gửi LLM không do thuộc tính này quyết định**, mà do danh sách input tự khai của từng prompt module (NFR-05 của `01-prd.md`, ADR-008). Bảng gán cụ thể ở mục Slot schema của `00-domain.md`.

**`seal_type` — loại dấu**

| Định danh | Tên tiếng Việt |
|---|---|
| `ORGANIZATION_ROUND` | Dấu tròn của đơn vị |
| `TITLE_STAMP` | Dấu chức danh |
| `OVERLAP_STAMP` | Dấu treo |
| `EDGE_STAMP` | Dấu giáp lai |

**`contract_type` — loại hợp đồng lao động** *(danh sách đầy đủ chờ xác nhận, xem A-013)*

`PROBATION` (thử việc) · `FIXED_TERM` (xác định thời hạn) · `INDEFINITE` (không xác định thời hạn)

**`operating_mode` — chế độ vận hành của hệ thống**

`NON_PRODUCTION` (chế độ phi sản xuất — bắt buộc chừng nào A-018 còn `Mở`) · `PRODUCTION`. Chuyển sang `PRODUCTION` là quyết định có người ký, không phải cờ cấu hình. Xem mục Chế độ phi sản xuất của `00-domain.md`

**`register_series` — dải số của `document_register`**

`TRIAL` (dải thử nghiệm, dùng ở `NON_PRODUCTION`) · `OFFICIAL` (dải thật). Hai dải hoàn toàn tách biệt, không dùng chung bộ đếm

**`audit_severity` — mức của `audit_event`**

`INFO` (hành động bình thường) · `WARNING` (hành động đúng luật nhưng cần người khác nhìn thấy, ví dụ tự duyệt theo đường thoát ở mục Tách biệt trách nhiệm của `00-domain.md`)

**`document_register_entry_status` — trạng thái dòng sổ văn bản**

`ASSIGNED` (đã cấp cho một văn bản) · `VOIDED` (đã huỷ, không tái sử dụng)

---

## 9. Thuật ngữ nghiệp vụ

| Thuật ngữ | Nghĩa trong dự án này |
|---|---|
| **Slot** | Một trường dữ liệu mà agent phải thu thập đủ trước khi xử lý yêu cầu |
| **Cổng HITL** | Điểm trong vòng đời bắt buộc dừng chờ người thật quyết định. Có đúng hai cổng, **tách rời nhau**: `PENDING_APPROVAL` và `PENDING_SEAL` |
| **Artifact** | Vật do một `request` tạo ra và có máy trạng thái riêng: `document`, `room_booking` `[Should]`, `seal_action` |
| **Tách biệt trách nhiệm** | Người **thụ hưởng** một yêu cầu không được duyệt chính yêu cầu đó. Căn cứ là `beneficiary_employee_id == approver_employee_id`, không phải người tạo. Chi tiết ở mục Tách biệt trách nhiệm của `00-domain.md` |
| **Người thụ hưởng** | Cột `beneficiary_employee_id` của `request` — nhân viên mà kết quả yêu cầu phục vụ. Mặc định bằng người tạo, khác đi khi nhập hộ |
| **Tự duyệt** | `approval_step.self_approved = true` — trường hợp người thụ hưởng buộc phải tự duyệt vì không còn ai đủ quyền. Luôn kèm `self_approval_reason`, `audit_event` mức `WARNING` và hiển thị riêng trên dashboard |
| **Provenance hồ sơ** | Ràng buộc `source` + `synced_at` phải hiển thị cho người duyệt với mọi giá trị nguồn `HR_PROFILE` |
| **Khung thể thức** | Phần văn bản do pháp luật quy định: quốc hiệu, tiêu ngữ, tên cơ quan, số và ký hiệu, nơi nhận, phần chữ ký. Nằm trong `template`, agent không sinh và không sửa (ADR-001) |
| **Nội dung tự do** | Phần thay đổi theo từng yêu cầu: lý do, mục đích, nội dung công việc. Là phần duy nhất prompt LLM được sinh ra |
| **Chế độ phi sản xuất** | `operating_mode = NON_PRODUCTION` — watermark không gỡ được, dải số `TRIAL`, không đóng dấu thật. Bắt buộc chừng nào chưa có người nghiệm thu thể thức. Chi tiết ở mục Chế độ phi sản xuất của `00-domain.md` |
| **Cấp số** | Gán `document_number` từ `document_register`, chỉ xảy ra tại thời điểm chuyển sang `ISSUED` |
| **Lỗ hổng số** | Số đã cấp nhưng không gắn được với văn bản nào. Được đánh dấu `VOIDED`, không tái sử dụng |
| **Thu hồi** | Đánh dấu văn bản đã phát hành mất hiệu lực. Không phải xoá |
| **Văn bản ngoài** | File do bên thứ ba soạn, nhân viên tải lên. Nội dung là **dữ liệu không tin cậy** đối với agent |
| **Uỷ quyền** | `delegation` — cho phép hành động thay người khác trong khoảng thời gian có hiệu lực |

---

## 10. Tên chưa chốt

Trong sơ đồ `erDiagram` ở mục Quan hệ giữa các entity của `00-domain.md`, tên entity viết HOA theo thông lệ Mermaid: `REQUEST` là `request`, `SEAL_ACTION` là `seal_action`, và tương tự cho các entity còn lại. Chỉ là khác biệt hiển thị, không phải tên khác.

Tên **agent**, **node LangGraph** và **tool** chốt ở mục 12, từ Phase 3. Tên **bảng** và **cột** cụ thể thuộc Phase 4; các định danh entity ở mục 1 là tên logic, Phase 4 có thể ánh xạ sang tên bảng khác nhưng phải ghi rõ ánh xạ đó.

---

## 11. Thành phần kiến trúc hệ thống — chốt ở Phase 2

Tên chuẩn của các thành phần trong `02-architecture.md`. Từ Phase 3 trở đi, agent/tool/node phải nói rõ chúng thuộc thành phần nào trong danh sách này, dùng đúng tên.

| Định danh | Vai trò | Ghi chú |
|---|---|---|
| `client` | Giao diện React SPA | Không tự validate business rule |
| `api` | FastAPI, điểm vào REST + SSE, AuthN/AuthZ | — |
| `ai_gateway` | Gọi LLM, model routing rẻ/mạnh, ép input theo allowlist của prompt module | Không phải service riêng — module trong tiến trình `api`/`queue_worker` |
| `orchestrator` | LangGraph: node/edge, `interrupt`, resume qua checkpointer | Thư viện dùng chung `api` và `queue_worker`, không phải service riêng (ADR-005) |
| `tool_layer` | Mọi thao tác có side effect qua permission check | — |
| `vector_store` | Embedding + hybrid search trên kho quy trình hành chính (`procedure_document`) | `pgvector` trong cùng `postgresql`, không phải service riêng (ADR-002). Chỉ phục vụ hướng xử lý thủ công của `intake_agent`; không phục vụ chọn template hay soạn thảo — sửa ở Phase 3 |
| `postgresql` | Nguồn sự thật cho entity, `document_register`, `seal_register`, `audit_event`, checkpoint, bảng job | — |
| `object_storage` | Lưu bản gốc template và bản render `.docx`/`.pdf` | S3-compatible, vendor `TBD` (ADR-003, A-024) |
| `queue_worker` | Job nền: render sau `SUBMITTED`, quét hạn, thông báo | Bảng job trong `postgresql` (ADR-004) |
| `observability` | Log kỹ thuật, trace, metric | **Khác** `audit_event` — log cho kỹ sư vận hành, không phải nhật ký nghiệp vụ |

Tên **agent**, **node LangGraph** cụ thể bên trong `orchestrator`, và **tool** cụ thể bên trong `tool_layer`, vẫn thuộc Phase 3 — mục này chỉ chốt tên các thành phần hạ tầng bao quanh chúng.

---

## 12. Agent, graph, node, tool — chốt ở Phase 3

Định nghĩa đầy đủ ở `03-agents.md`. Từ Phase 4 trở đi mọi file dùng đúng các tên này.

**Bất biến**

| ID | Tên | Nội dung ngắn |
|---|---|---|
| `INV-01` | Không LLM sau cổng nội dung | Từ `PENDING_APPROVAL` trở đi, không lời gọi LLM nào sửa document trừ khi nó quay về `DRAFT`; bản phát hành chỉ khác bản đã duyệt ở tập biến `SYSTEM` mang cờ *điền sau duyệt* |
| `INV-02` | LLM không tự gọi tool | ADR-007 |
| `INV-03` | Prompt chỉ chứa input được nạp theo danh sách tự khai | ADR-008 — allowlist là danh sách nạp, fail-closed |

**Agent và graph**

| Định danh | Loại | Ghi chú |
|---|---|---|
| `intake_agent` | Agent | Model rẻ; chạy trong `intake_graph` |
| `drafting_agent` | Agent | Model mạnh; chạy trong `document_graph` |
| `intake_graph` | Graph | Thread `intake:{chat_session_id}` |
| `document_graph` | Graph | Thread `document:{document_id}` |

**Lời gọi ra model** — `classify_intent` · `extract_slots` · `select_procedure_passages` · `draft_free_content` · `revise_free_content` (LLM) · `embed_query` · `embed_corpus_chunk` (embedding)

**Node `interrupt`** — `await_content_review` (cổng HITL số 1) · `await_signature` · `await_seal` (cổng HITL số 2) · `await_issue` · `await_resubmission` · `await_human_takeover`

**Node tất định** — `intake_graph`: `load_turn` · `route_intent` · `resume_context` · `ask_clarification` · `open_request` · `propose_values` · `check_completeness` · `ask_missing` · `offer_submit` · `render_reply`. `document_graph`: `prepare_draft` · `validate_free_content` · `render_draft` · `check_review_readiness` · `submit_for_review` · `route_review` · `reopen_draft` · `compute_targets` · `halt_for_human` · `route_signing` · `route_after_signature` · `finalize_issue` · `notify_issued`

**Tool của `tool_layer`, theo nhóm được gọi** — bảng đầy đủ, kèm vị trí so với cổng HITL, ở mục Tool Registry của `03-agents.md`:

- `intake_agent`: `employee_lookup` · `request_open` · `request_slots_write` · `request_slots_read` · `request_transition` · `prior_attempt_lookup` · `procedure_retrieval` · `room_availability_check` `[Should]`
- `drafting_agent`, toàn bộ trước cổng 1: `template_fetch` · `request_slots_read` · `document_draft_save` · `review_readiness_check` · `document_transition` (ba chuyển đổi trước cổng) · `docx_render` và `pdf_export` (bản nháp)
- Node tất định sau cổng, không thuộc agent nào: `signing_route` · `document_number_assign` · `document_transition` (sang `ISSUED`) · `docx_render` và `pdf_export` (bản cuối) · `notification_send`
- Node dùng chung của `document_graph`: `notification_send` và `document_halt_record` (cùng gọi từ `halt_for_human`)

Node `open_request` gọi tool `request_open`; hai tên khác nhau có chủ đích — một là bước của graph, một là thao tác của `tool_layer`.

**Thao tác cổng** — chỉ đi vào từ `api` với người thật làm tác nhân: `request_submit` · `document_approve_content` · `document_request_changes` · `document_reject` · `document_sign` · `document_apply_seal` · `document_issue` · `document_revoke_initiate` · `document_revoke_confirm` · `booking_confirm` `[Should]`

**Thao tác vận hành** — `expire_request` · `checkpoint_purge` · `procedure_ingest`

**Loại job** — `render_document` · `resume_document_graph` · `finalize_issue`

**Biến nội dung tự do**

| Định danh | `request_type` | Slot input đã khai |
|---|---|---|
| `purpose_statement` | `WORK_CONFIRMATION` | `purpose` |
| `work_content_statement` | `INTRODUCTION_LETTER` | `work_content` |

**Enum**

- `change_scope` — `FREE_CONTENT` (nội dung soạn sai; `request` ở nguyên `IN_REVIEW`) · `SLOT_DATA` (dữ liệu khai sai hoặc thiếu; `request` về `CHANGES_REQUESTED`). Bắt buộc ở `document_request_changes`
- `procedure_visibility` — `ORG_WIDE` · `DEPARTMENT_ONLY`

**Thuật ngữ**

| Thuật ngữ | Nghĩa |
|---|---|
| **Biến nội dung tự do** | Biến của template mà giá trị do `drafting_agent` sinh. Là đơn vị render lại (ADR-009) |
| **Cờ điền sau duyệt** | Đánh dấu trong danh mục biến của template cho biến `SYSTEM` được điền sau cổng nội dung (`document_number`, `issued_date`, `signer_user_id` và biến suy ra từ nó) |
| **`change_targets`** | Danh sách biến hoặc slot người duyệt chọn khi yêu cầu sửa. LLM không tự quyết danh sách này |
| **`change_reason`** | Lý do sửa, văn bản tự do, bắt buộc. Tới `revise_free_content` như dữ liệu, chỉ cho biến đã chọn |
| **`approved_content_hash`** | Hash ghi lúc duyệt nội dung, kiểm lại ở `finalize_issue` để thực thi INV-01 |
| **Danh sách nạp** | Danh sách input tự khai của prompt module, dùng để nạp dữ liệu và kiểm prompt. Quên khai thì mất chức năng, không rò dữ liệu |
| **Khoảng hoàn tất phát hành** · cờ `issue_in_progress` | Từ lúc `document_issue` ghi lệnh phát hành tới lúc `finalize_issue` commit `ISSUED` hoặc bỏ cuộc. Document đứng yên ở `SIGNED`/`SEALED`; phần đầu chưa có `document_number`. Là **cờ dẫn xuất** như `sla_breached`, **không** phải trạng thái. Hiển thị thuộc Phase 8 |
