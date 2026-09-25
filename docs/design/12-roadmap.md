# Roadmap — Admin Service Desk Agent (BO-19)

**Phiên bản:** 0.1 · **Trạng thái:** Draft chờ duyệt

> File này xếp phạm vi Must của PRD thành các sprint có thứ tự, mỗi sprint có Objective, Deliverable, Dependency, Acceptance Criteria và rủi ro chính, kèm các cổng phải qua trước từng sprint. File này **không** khai lại mức MoSCoW (nguồn duy nhất: mục Scope & priority của `01-prd.md`), **không** đặt ngày hay ước lượng khối lượng (A-071), **không** thiết kế lại bất cứ thứ gì đã chốt, và **không** giải hộ các giả định của phase khác — chỉ đặt chúng vào đúng cổng.

Tên entity, trạng thái, permission, agent, node, tool, component dùng đúng `GLOSSARY.md`. Quyết định `D-xxx`/`A-xxx` tham chiếu `00-domain.md` và `ASSUMPTIONS.md`.

**Đã đối chiếu:** `CLAUDE.md`, `_PLAN.md`, `GLOSSARY.md`, `ASSUMPTIONS.md`, `CHANGELOG.md`, `00-domain.md`, `01-prd.md`, `02-architecture.md`, `03-agents.md`, `04-data.md`, `05-api.md`, `06-structure.md`, `07-prompts.md` (mục lục và Open Questions), `08-hitl.md`, `09-security.md` (mục lục và Open Questions), `10-eval.md`, `11-ops.md`, `decisions/ADR-001` → `ADR-024` (theo tên và các đoạn được trích ở file phase), `.claude/commands/spike.md`, `tools/contract-checks/README.md` và danh sách nhóm quyền trong `check_grants.py`.

---

## 1. Nguyên tắc xếp sprint

Quyết định của PO trong phiên này (2026-09-25) — hai câu trả lời trực tiếp, ba câu theo phương án mặc định vì không có trả lời khác:

- **Sprint 1 làm `WORK_CONFIRMATION`** (mặc định). Lý do:
  - Người thụ hưởng mặc định là người tạo — lát cắt không phải đi qua đường nhập hộ, đường đang hỏng ở cả hai loại (A-052).
  - Chỉ hai slot `USER_INPUT` bắt buộc (`purpose`, `recipient_org`) và không phụ thuộc trần hiệu lực chưa có (A-011) như `valid_from`/`valid_to` của `INTRODUCTION_LETTER`.
  - Vẫn đi qua đủ **hai cổng HITL**, vì `requires_seal` luôn đúng với loại này (mục Request Type Catalog của `00-domain.md`) — lát cắt chạm đúng thứ khó nhất của hệ thống, không phải một đường tắt.
- **Sprint 1 chạy end-to-end ở môi trường local** (PO chọn). Render đến ở Sprint 2. Local cần một object storage nói giao thức S3 — A-072.
- **Spike 1 gộp vào Sprint 1** (PO chọn), thành một track riêng chạy song song với track build. Luật của VERIFY MODE ở `.claude/commands/spike.md` vẫn áp cho mọi thứ track đó viết ra.
- **Nợ Phase 8 thành cổng theo sprint, không mở lại Phase 8** (mặc định) — mục 9. Mâu thuẫn giữa trạng thái ☑ của Phase 8 và hạn cứng của A-052 được **báo cáo**, không tự sửa (Open Questions).
- **Không gắn ngày, không ước lượng khối lượng** (mặc định) — A-071. Thứ tự sprint là thứ tự phụ thuộc; độ dài sprint do PO chốt.

Nguyên tắc xếp:

- **Mỗi sprint kết thúc bằng một thứ chạy được**, không bằng một tầng hạ tầng dựng xong. Sprint 1 là một lát cắt dọc (mục Thuật ngữ nghiệp vụ của `GLOSSARY.md`); các sprint sau mở rộng lát cắt đó.
- **"Sprint đầu" của PRD ≠ Sprint 1 của file này.** "Sprint đầu" là phạm vi phát hành đầu tiên, nghiệm thu bằng mục Definition of Done của `01-prd.md` qua buổi UAT; nó trải trên Sprint 1 → Sprint 4. Đã thêm định nghĩa vào `GLOSSARY.md` để hai tên không bị đọc lẫn.
- **Cổng là điều kiện, không phải việc.** Một cổng liệt kê giả định phải đóng hoặc quyết định phải có trước khi sprint bắt đầu (**chặn khởi động**) hoặc trước khi AC của sprint đạt được (**chặn AC**). Việc đóng giả định thuộc owner ghi ở `ASSUMPTIONS.md`, không thuộc sprint.
- **Không ADR mới.** Thứ tự sprint là quyết định sản phẩm, không phải lựa chọn công nghệ (mục Tech stack của `CLAUDE.md`). Lựa chọn công nghệ duy nhất roadmap làm phát sinh — sản phẩm object storage cho local — được giao ADR ở A-072, không chọn ở đây.

---

## 2. Tổng quan

```mermaid
flowchart LR
    G1{Cong truoc Sprint 1}
    SP1[Sprint 1 - lat cat doc WORK_CONFIRMATION local, cong Spike 1]
    S0FAIL[Buoc S0 truot - dung build tang du lieu, xet lai 04-data]
    G2{Cong truoc Sprint 2}
    SP2[Sprint 2 - du AC F1 F2 F3 cho WORK_CONFIRMATION, len Render dev]
    G3{Cong truoc Sprint 3}
    SP3[Sprint 3 - INTRODUCTION_LETTER, F6, nhap ho, F4 day du]
    G4{Cong truoc Sprint 4}
    SP4[Sprint 4 - san sang UAT tren staging]
    UAT([Buoi UAT - nghiem thu Sprint dau])
    POST[Sau UAT - hang muc Should va Could]
    PROD([Milestone san xuat - chan boi A-018])

    G1 --> SP1
    SP1 -->|buoc S0 truot| S0FAIL
    SP1 --> G2 --> SP2 --> G3 --> SP3 --> G4 --> SP4 --> UAT
    UAT --> POST
    UAT -.->|chi khi A-018 dong| PROD
```

| Sprint | Objective — một câu | Feature chạm tới |
|---|---|---|
| Sprint 1 | Một nhân viên đi trọn hành trình của `WORK_CONFIRMATION` trên máy local; Render được đo, chưa được dùng | F1, F2, F3, F4 — đường chính |
| Sprint 2 | Mọi nhánh lệch khỏi đường chính của `WORK_CONFIRMATION` đều có đích; lát cắt chạy trên Render `dev` | F1, F2, F3 — nhánh lỗi, sửa, hết hạn; NFR-06 |
| Sprint 3 | Loại thứ hai, nhập hộ, và thêm loại thứ ba không cần sửa code | F1, F2 cho `INTRODUCTION_LETTER`; F6; F4 đầy đủ; NFR-02 |
| Sprint 4 | Bằng chứng nghiệm thu: bộ eval có đáp án, gate hồi quy, `staging`, buổi UAT | NFR-07; mục Definition of Done của `01-prd.md` |

---

## 3. Cổng trước Sprint 1

| # | Điều kiện | Nguồn | Owner | Chặn |
|---|---|---|---|---|
| 1.1 | Anh tuyên bố chuyển sang BUILD MODE | Mục Chế độ làm việc hiện tại của `CLAUDE.md` | Anh | Khởi động |
| 1.2 | Phase 13 (Consistency Audit) xong và các lỗi nó tìm thấy đã có quyết định sửa hay không. Code bám vào tên; sửa tên sau khi có code đắt hơn nhiều sửa trên giấy | `_PLAN.md` | Anh | Khởi động |
| 1.3 | A-055 có quyết định: `audit_event` ghi cho thao tác nào | Hạn gốc của A-055: "trước khi viết code của `tool_layer`" | Phase 8 — mục 9 | Khởi động |
| 1.4 | Có quyết định và ADR cho object storage chạy local | A-072 | Người triển khai | Khởi động |
| 1.5 | Chọn nhà cung cấp và model cho hai tier | A-026 — hạn gốc "trước khi viết adapter provider của `ai_gateway`" | Product Owner | AC — AC-1.1 cần lời gọi LLM thật |
| 1.6 | Mẫu `tpl_work_confirmation` `.docx` đúng thể thức, bộ font nó dùng, và quyền phân phối font trong image | A-058, mục Thể thức văn bản của `00-domain.md` | Product Owner | AC — không có mẫu thì không render; thiếu font thì `worker` không khởi động (bước kiểm khởi động #7) |
| 1.7 | Giá trị định dạng số và ký hiệu cho sổ, kể cả dải `TRIAL` | A-009 — hạn gốc "trước lần cấp số đầu tiên, kể cả số dải `TRIAL`" | Product Owner | AC — AC-1.2 cấp số |
| 1.8 | Giá trị `contract_type` và các cột CSV hồ sơ nhân viên | A-013 | Product Owner | AC — `contract_type` là slot bắt buộc của `WORK_CONFIRMATION` |
| 1.9 | Múi giờ của tổ chức | A-041 | Product Owner | AC — bước kiểm khởi động #13 chặn khi thiếu |
| 1.10 | Giá trị làm việc cho tham số vận hành chưa định cỡ (số lần retry, hạn chót lượt, các timeout), được phép mang nhãn "chưa hiệu chỉnh" nhưng không được vắng | A-031; bước kiểm khởi động #5, #11 | Người triển khai | AC |

Trần token và trần số vòng **không** nằm ở đây — đã có giá trị khởi tạo ở mục Định cỡ A-022 của `11-ops.md`.

---

## 4. Sprint 1 — lát cắt dọc `WORK_CONFIRMATION`, local, cộng Spike 1

**Objective.** Một nhân viên đăng nhập, mô tả nhu cầu bằng chat, xác nhận hồ sơ, gửi; một cán bộ hành chính duyệt nội dung, ký, duyệt dấu, phát hành; nhân viên thấy `FULFILLED` và tải được bản PDF có watermark — toàn bộ trên máy local, với LLM thật. Song song, Spike 1 đo Render để Sprint 2 không phải đoán.

### 4.1 Track build — Deliverable

| Tầng | Deliverable | Ghi chú phạm vi |
|---|---|---|
| Dữ liệu | `migrate_main` chạy đủ bốn bước của mục Migration và checkpointer của `06-structure.md` trên PostgreSQL local, gồm `0001`–`0004`; data migration nạp danh mục permission, hai vai trò, cấu hình `WORK_CONFIRMATION` và một phiên bản template `ACTIVE` | Cấu hình nạp bằng data migration — màn hình F6 chưa có |
| Kiểm contract | Bổ sung `employee_credential` và `rate_limit_window` (tạo ở `0002_phase9_security.sql`) vào danh sách nhóm quyền của `tools/contract-checks/check_grants.py`, rồi chạy `--app-dsn` trên DB local đã migrate | Hai bảng đó hiện **không** thuộc nhóm nào trong `check_grants.py`; chạy `--app-dsn` hôm nay sẽ báo lệch độ phủ. Nhóm của chúng lấy từ mục Migration bổ sung của Phase 9 ở `09-security.md` |
| Khởi động | `bo19.startup` với mọi bước ở mục Bước kiểm khởi động của `06-structure.md` áp cho `api` và `worker` | `BO19_ENVIRONMENT = dev` |
| Xác thực | `POST /auth/session`, `DELETE /auth/session`, `GET /me`; mật khẩu seed bằng thao tác vận hành (A-048) | Hai tài khoản: `EMPLOYEE`; `ADMIN_OFFICER` được cấp lẻ `document.sign` (mục Gói permission theo vai trò của `00-domain.md`) |
| `intake_graph` | Đường chính: `load_turn` → `classify_intent` → `route_intent` → `open_request` → `extract_slots` → `propose_values` → `check_completeness` → `ask_missing`/`offer_submit` → `render_reply`; stream lượt chat | Nhánh `ask_clarification` có mặt vì `route_intent` cần đích cho `AMBIGUOUS`; nhánh ngoài phạm vi chưa có (Sprint 2, A-073) |
| Thao tác của nhân viên | `request_slot_confirm`, `request_submit` | `request_cancel` ở Sprint 2 |
| `document_graph` | Job `render_document`: `draft_free_content` cho `purpose_statement` → `validate_free_content` → `render_draft` → `check_review_readiness` → `PENDING_APPROVAL`; resume qua `await_content_review`, `route_signing` (`render_integrity_check`, `signing_route` một cấp), `await_signature`, `await_seal`; job `finalize_issue` cấp số dải `TRIAL` | Nhánh `reopen_draft`, `halt_for_human` là Sprint 2 — lỗi ở Sprint 1 làm job `FAILED`, chấp nhận vì chưa có người dùng thật |
| Thao tác cổng | `document_approve_content`, `document_sign`, `document_apply_seal`, `document_issue` | `document_request_changes`, `document_reject` ở Sprint 2 |
| `client` | `/login`, `/chat`, `/my-requests/:requestId` (bảng xác nhận từng slot, nút gửi, tải bản `FINAL`), `/review/:status`, `/issue`, `/documents/:documentId` với provenance | Chưa có stream tín hiệu: người dùng tải lại trang để thấy trạng thái mới (Sprint 3) |
| `observability` | Handler mask duy nhất, `trace_id` theo ADR-024 | Bốn điểm đo của mục Log schema của `11-ops.md` ở Sprint 4 |

### 4.2 Track Spike 1 — Deliverable

Bảng bước, giả định cần đóng và luật riêng ở `.claude/commands/spike.md`; ở đây chỉ nêu thứ tự so với track build.

| Bước | Thứ tự so với track build |
|---|---|
| S0 — cổng | **Việc đầu tiên của Sprint 1**, trước mọi mã của `bo19.persistence` và `migrate_main`. Trượt thì chạy luật "S0 là cổng" của `spike.md` cho **cả** track build ở tầng dữ liệu — xem rủi ro R1-1 |
| S1, S2 | Sau S0. S2 dùng lại `bo19.startup` bước #1, #2 của track build — một mã, không viết hai lần |
| S3, S4 | Sau S2. Kết quả S4 là căn cứ cho hạn chót lượt (A-031) mà track build đang dùng giá trị tạm |
| S5 | Sau khi có mẫu và font (cổng 1.6) |
| S6 | Cần khoảng 50 đoạn văn bản hành chính tiếng Việt thật — nguồn do PO cấp |
| S7 | Cần danh sách ngắn nhà cung cấp do PO duyệt; spike không tự chọn nhà cung cấp |

### 4.3 Acceptance Criteria

| ID | Tiêu chí | Truy vết |
|---|---|---|
| AC-1.1 | Hành trình ở điều 1 của mục Definition of Done của `01-prd.md` chạy trọn cho `WORK_CONFIRMATION` trên local, với provider LLM thật và dữ liệu `employee` giả đánh dấu là giả | DoD điều 1 |
| AC-1.2 | Trên dữ liệu của lần chạy AC-1.1: có hai `decision_record` riêng loại `APPROVED` và `SEALED`, mỗi cái một `audit_event`; `document_number` lấy từ `document_register` thuộc dải `TRIAL` | M4, M5 — hình dạng; ngưỡng đo ở Sprint 4 |
| AC-1.3 | Bản `FINAL` mang watermark `BẢN THỬ NGHIỆM — KHÔNG CÓ GIÁ TRỊ PHÁP LÝ` **trong file**; nhân viên chỉ tải được `pdf` bản `FINAL` sau `ISSUED`; tải `docx` hay bản nháp trả lỗi quyền | NFR-03, mục Tải file của `05-api.md` |
| AC-1.4 | `request_submit` trả `REQUEST_NOT_READY` khi còn một giá trị `HR_PROFILE` chưa xác nhận, kể cả khi mọi giá trị khác đã xác nhận | F1 — định nghĩa "Yêu cầu đủ điều kiện xử lý" |
| AC-1.5 | Màn hình duyệt hiện `source` và `synced_at` cho mọi giá trị `HR_PROFILE` có trong văn bản | F2 |
| AC-1.6 | `check_grants.py --app-dsn` trên DB local đã migrate bằng `migrate_main`: `Lệch: 0`, mã thoát `0` | Mục Nguyên tắc dữ liệu của `04-data.md` |
| AC-1.7 | `api` khởi động bằng credential của `bo19_migrator` bị chặn ở bước kiểm khởi động #2; khởi động bằng `bo19_app` qua đủ các bước | Mục Bước kiểm khởi động của `06-structure.md` |
| AC-1.8 | Một giá trị `RES` đánh dấu nhập vào `purpose` trong lần chạy AC-1.1 không xuất hiện dạng thật trong log kỹ thuật của lần chạy đó | NFR-05 |
| AC-1.9 | CI đỏ khi vi phạm luật import (`import-linter`, ESLint) — chứng minh bằng một vi phạm cố ý | Mục Luật import của `06-structure.md` |
| AC-1.10 | Mỗi bước S0–S7 có kết quả ghi vào `ASSUMPTIONS.md` và `CHANGELOG.md` theo luật của `spike.md`: số đo nguyên văn, hoặc ghi rõ không chạy được và vì sao. Không bước nào ghi "đạt" khi không chạy | Spike 1 |

### 4.4 Rủi ro chính

- **R1-1 — S0 trượt giữa sprint.** Nếu Render không cho role runtime không sở hữu bảng hoặc không cho migrate bằng role khác, mô hình hai role của `04-data.md` phải xét lại. Đặt S0 làm việc đầu tiên giới hạn thiệt hại ở phần track build chưa bắt đầu; phần đã viết ngoài tầng dữ liệu (`intake_graph`, `client`) không phụ thuộc kết quả S0.
- **R1-2 — Sprint 1 gánh hai track với năng lực chưa biết** (A-071). Nếu phải cắt, cắt S5–S7 trước — đầu ra của chúng là đầu vào của Sprint 2, không phải của AC Sprint 1. S0–S2 không cắt.
- **R1-3 — Local khác image Linux.** Mục Xác minh contract của `06-structure.md` ghi máy triển khai chạy PostgreSQL bản Windows và Docker Desktop không khởi động được. Tên họ font, hành vi `soffice`, và object storage local có thể khác Render. AC-1.1 đạt ở local **không** chứng minh lát cắt đạt trên Render — đó là AC-2.1.
- **R1-4 — Đầu vào của PO về muộn** (cổng 1.5–1.9). Chúng chặn AC, không chặn khởi động, nên sprint vẫn chạy được tới lúc cần chúng; nhưng AC-1.1 không đạt được bằng dữ liệu giả thay cho mẫu `.docx` hay định dạng số thật.

---

## 5. Sprint 2 — đủ AC F1–F3 cho `WORK_CONFIRMATION`, lên Render `dev`

**Objective.** Mọi nhánh lệch khỏi đường chính của `WORK_CONFIRMATION` đều có một đích có tên — sửa, từ chối, dừng có kiểm soát, hết hạn, huỷ, ngoài phạm vi — và lát cắt của Sprint 1 chạy trên Render `dev`.

### 5.1 Cổng trước Sprint 2

| # | Điều kiện | Nguồn | Chặn |
|---|---|---|---|
| 2.1 | S0 của Spike 1 đạt, hoặc đã có quyết định thay kiến trúc dữ liệu | `spike.md`, AC-1.10 | Khởi động |
| 2.2 | A-029, A-034, A-038, A-044, A-053, A-068 có quyết định | Mục 9 | Khởi động |
| 2.3 | Có hướng cho nhánh ngoài phạm vi khi kho rỗng | A-073 | AC-2.6 |
| 2.4 | Thời hạn chờ ở `NEEDS_INFO` trước `EXPIRED` có giá trị làm việc | A-014 | AC-2.7 |
| 2.5 | Chọn nhà cung cấp object storage | A-024, kết quả S7 | AC-2.1 |
| 2.6 | Ba vế secret của CI | A-067 | AC-2.1 |

### 5.2 Deliverable

- **Vòng sửa và từ chối:** `document_request_changes` cả hai `change_scope`; `reopen_draft`, `compute_targets`, `revise_free_content`; gửi lại ở ca `SLOT_DATA` qua `request_submit`; `document_reject` — theo mục Luồng yêu cầu sửa và agent làm lại của `08-hitl.md`.
- **Dừng có kiểm soát:** mọi đường vào `halt_for_human` ở mục Cơ chế dừng khi chạm trần của `08-hitl.md`; `document_halt_record`; banner `halted` trên `/documents/:documentId`; nhánh `VOIDED` của `finalize_issue`.
- **Hết hạn và huỷ:** cron `expire_request` với số phận dữ liệu theo `slot_sensitivity` (A-014); `prior_attempt_lookup`; `checkpoint_purge`; `request_cancel`.
- **Hội thoại:** EC-CV-01 → EC-CV-04; `ask_clarification` theo quyết định A-068; nhánh ngoài phạm vi trên kho rỗng theo A-073.
- **Render `dev`:** CI pipeline chạy `migrate_main` rồi mới trigger deploy (ADR-022); Web Service, Background Worker, Cron Job từ **một** image (ADR-015); `check_grants.py --app-dsn` chạy sau migrate trong CI.
- **Harness eval:** schema `EvalCase` ở mục `EvalCase` của `10-eval.md`; các nhóm chạy được với `WORK_CONFIRMATION`; canary C1, C2. Kết quả **không kết luận được** trước khi A-023 đóng — ghi rõ trong mọi báo cáo chạy.

### 5.3 Acceptance Criteria

| ID | Tiêu chí | Truy vết |
|---|---|---|
| AC-2.1 | AC-1.1, AC-1.3, AC-1.7 đạt lại trên Render `dev` | DoD điều 1; R1-3 |
| AC-2.2 | Yêu cầu sửa `FREE_CONTENT` chỉ sinh lại biến trong `change_targets`; `request` ở nguyên `IN_REVIEW` | F3; ADR-009 |
| AC-2.3 | Chạm trần `R` vòng `CHANGES_REQUESTED`, và chạm trần token đặt thấp có chủ đích: `document` dừng ở `halt_for_human`, không vào `PENDING_APPROVAL` với biến rỗng, có dòng `document_halt` | NFR-06 |
| AC-2.4 | Hai lệnh phát hành đồng thời không nhận cùng số; lỗi sau khi có số chuyển số sang `VOIDED` kèm lý do và không tái sử dụng | F3 |
| AC-2.5 | Canary C1 và C2: không tìm thấy giá trị đánh dấu trong bảng checkpoint | Mục Canary suite của `10-eval.md` |
| AC-2.6 | Yêu cầu ngoài phạm vi trên kho rỗng được báo chưa hỗ trợ và **nói rõ kho không có căn cứ** | F1; M6 |
| AC-2.7 | EC-CV-04 cả hai nhánh: quay lại trong hạn khôi phục đúng slot đã thu; quay lại sau `EXPIRED` báo đã hết hạn, không dùng lại dữ liệu cũ, slot `RES` đã bị xoá | F1; A-014 |
| AC-2.8 | EC-CV-02: đổi loại giữa chừng không mang slot nào sang loại mới | F1; nhóm G |

### 5.4 Rủi ro chính

- **R2-1 — Nợ Phase 8 chưa quyết kịp** (cổng 2.2). Sáu giả định, mỗi cái chạm một nhánh của Sprint 2. Quyết từng phần thì Sprint 2 bắt đầu được với các nhánh đã có quyết định; không có cái nào thì Sprint 2 không có việc ngoài lên Render.
- **R2-2 — A-024 chưa chọn.** Không có nhà cung cấp thì không có Render `dev` đầy đủ; bất biến bản render ở tầng lưu trữ tiếp tục chỉ được chứng minh trên sản phẩm local (A-072 hệ quả 2).
- **R2-3 — Harness chạy mà không kết luận được** (A-023). Rủi ro là đội đọc kết quả "đạt" trên đáp án chưa duyệt như thể đã nghiệm thu.

---

## 6. Sprint 3 — `INTRODUCTION_LETTER`, F6, nhập hộ, F4 đầy đủ

**Objective.** Loại yêu cầu thứ hai chạy bằng cấu hình và mẫu, nhập hộ chạy đúng ở cả hai loại, và một loại thứ ba được thêm vào mà không sửa code — diễn tập điều 4 của mục Definition of Done của `01-prd.md` trước UAT.

### 6.1 Cổng trước Sprint 3

| # | Điều kiện | Nguồn | Chặn |
|---|---|---|---|
| 3.1 | A-052 có quyết định — hạn cứng của chính nó | Mục 9 | Khởi động |
| 3.2 | A-056 có quyết định | Mục 9 | AC-3.8 |
| 3.3 | Trần `copies_count` và trần hiệu lực giấy giới thiệu | A-011 | AC-3.1 |
| 3.4 | Mẫu `tpl_introduction_letter` `.docx` và font của nó | A-058 | AC-3.1 |
| 3.5 | Chọn loại yêu cầu thứ ba và có mẫu của nó | A-074 | AC-3.2 |
| 3.6 | Embedding model cho nhánh có kho của nhóm J | A-073 hướng (b), A-028 | AC-3.7 |

### 6.2 Deliverable

- **`INTRODUCTION_LETTER`:** `draft_free_content` cho `work_content_statement`; EC-IL-01 → EC-IL-03, gồm `requires_seal` và `bearer_national_id` theo `recipient_org`.
- **Nhập hộ và tách biệt trách nhiệm:** theo quyết định A-052 ở cả hai loại; đường thoát tự duyệt đủ bốn điều kiện; `GET /self-approvals`; `/audit`, `/audit/self-approvals`.
- **F6:** `template_create`, `template_version_upload` có kiểm biến, `template_version_activate`; `employee_import`; `request_type_upsert`, `slot_definition_upsert`, `slot_sensitivity_change`; `procedure_version_upload` và job `procedure_ingest`; các tuyến `/config/*` ở mục Tuyến của `06-structure.md`.
- **F4 đầy đủ:** stream tín hiệu `GET /signals` với ba chủ đề; `notification_send` và `GET /notifications`; `/requests` sắp chờ lâu nhất trước; `status_label` tiếng Việt.
- **Eval:** đủ 37 ca chạy được trên harness, nhóm J trên kho quy trình giả lập đánh dấu là dữ liệu giả.

### 6.3 Acceptance Criteria

| ID | Tiêu chí | Truy vết |
|---|---|---|
| AC-3.1 | AC-1.1 đạt cho `INTRODUCTION_LETTER` trên Render `dev`; ca EC-IL-03 không vào hàng đợi duyệt khi thiếu `bearer_national_id` | F1, F2; DoD điều 2 |
| AC-3.2 | Thêm loại yêu cầu thứ ba trên `dev` chỉ bằng `request_type_upsert`, `slot_definition_upsert` và một phiên bản template — không commit mã, không deploy lại — rồi đi trọn hành trình của nó | F6 — AC cứng; DoD điều 4 (diễn tập) |
| AC-3.3 | Tải lên template thiếu biến bắt buộc bị từ chối, nêu đúng tên biến thiếu; văn bản đã render ghi lại phiên bản template đã dùng | F6 |
| AC-3.4 | Import CSV ghi `source`, `synced_at` cho từng bản ghi và một `audit_event` cho đợt | F6 |
| AC-3.5 | Nhập hộ: người thụ hưởng khác người tạo được ghi đúng vào `request.beneficiary_employee_id`; người duyệt trùng **người thụ hưởng** bị chặn; cán bộ nhập hộ cho người khác rồi tự duyệt thì **không** bị chặn | NFR-02; D-006; A-052 |
| AC-3.6 | Tự duyệt chỉ đi qua khi đủ bốn điều kiện; thiếu một thì bị từ chối | NFR-02 |
| AC-3.7 | 37 ca của NFR-07 chạy hết trên harness, mỗi ca có bản ghi kết quả gắn phiên bản prompt module, template và commit | NFR-07; mục Offline eval của `10-eval.md` |
| AC-3.8 | Ở `NEEDS_INFO` và `CHANGES_REQUESTED`, trang chi tiết nêu thiếu gì hoặc cần sửa gì; trạng thái `request` và trạng thái `document` hiển thị riêng; không mã trạng thái trần nào lộ ra trang của nhân viên | F4; NFR-04 |

### 6.4 Rủi ro chính

- **R3-1 — Loại thứ ba đòi năng lực ngoài Sprint đầu.** Hai ứng viên sẵn có trong catalog đều vậy (A-074): `BUSINESS_TRIP_ORDER` cần `SIGNER` `[Should]`, `INCOME_CONFIRMATION` cần tầng phê duyệt dữ liệu lương. Chọn nhầm thì AC-3.2 trượt vì phạm vi, không vì F6 hỏng.
- **R3-2 — Quyết định A-052 chạm danh mục permission** (phương án (b) của A-052 sửa nghĩa `request.read_own`) — kéo theo quyền tải bản `FINAL` và chủ đề `MY_REQUESTS`, đều đã có mã từ Sprint 1 và Sprint 3.
- **R3-3 — F6 là sprint rộng nhất.** Nếu phải cắt trong F6, thứ tự giữ: đường thêm loại thứ ba (AC-3.2) trước, kho quy trình sau — kho rỗng là trạng thái được hỗ trợ (A-027), còn AC-3.2 là điều kiện nghiệm thu.

---

## 7. Sprint 4 — sẵn sàng UAT trên `staging`

**Objective.** Có bằng chứng cho từng điều của mục Definition of Done của `01-prd.md`, trên `staging`, và chạy buổi UAT.

### 7.1 Cổng trước Sprint 4

| # | Điều kiện | Nguồn | Chặn |
|---|---|---|---|
| 4.1 | Đáp án chuẩn 37 ca đã được Trưởng phòng Hành chính duyệt | A-023 | AC-4.1 |
| 4.2 | Ba con số của buổi UAT: số người, số ca kịch bản, ai chấm | A-020 | AC-4.3 |
| 4.3 | Ngưỡng metric Cảnh báo đã chốt **trước** khi đo | A-019 | AC-4.3 |

### 7.2 Deliverable

- Môi trường `staging` theo mục Môi trường Render của `11-ops.md`, ba lớp khoá `operating_mode` của ADR-023 ở mức áp dụng được khi chưa có endpoint đổi chế độ (lớp 1 và 2).
- Regression gate trong CI theo mục Regression gate của `10-eval.md`: nhóm tương đương Bất biến chặn merge, nhóm tương đương Cảnh báo chỉ ghi.
- Log schema và bốn điểm đo mới của mục Log schema của `11-ops.md`; alert cứng của mục Alert.
- Kịch bản UAT theo A-020; loại yêu cầu thứ ba và mẫu của nó sẵn sàng để thêm **trong** buổi UAT.

### 7.3 Acceptance Criteria

| ID | Tiêu chí | Truy vết |
|---|---|---|
| AC-4.1 | M8, M4, M5, M6 đạt ngưỡng tuyệt đối trên 37 ca có đáp án đã duyệt và trên dữ liệu buổi UAT | DoD điều 3 |
| AC-4.2 | Regression gate chặn merge khi một ca nhóm G, nhóm J hoặc canary lệch — chứng minh bằng một thay đổi cố ý làm lệch | Mục Regression gate của `10-eval.md` |
| AC-4.3 | M1, M2, M3 được ghi đủ tử số và mẫu số; không đạt ngưỡng thì mở rà soát, không trượt nghiệm thu | Mục Goals & metrics của `01-prd.md` |
| AC-4.4 | Trong buổi UAT, loại yêu cầu thứ ba được thêm bằng cấu hình và một file template, không sửa code | DoD điều 4 |
| AC-4.5 | Hành trình của AC-1.1 cho cả hai loại chạy trên `staging` với người thật thao tác | DoD điều 1, điều 2 |

AC-4.1 → AC-4.5 cùng đạt là **Sprint đầu done** theo mục Definition of Done của `01-prd.md`. M7 và milestone sản xuất không thuộc điều kiện này.

### 7.4 Rủi ro chính

- **R4-1 — A-023 là đường găng không thuộc đội kỹ thuật.** Ba trong bốn metric Bất biến không chấm được khi chưa có đáp án chuẩn; không có cách kỹ thuật nào rút ngắn việc duyệt 37 ca.
- **R4-2 — RISK-03 vẫn vô hình.** Buổi UAT đo được M3 nhưng không đo được việc nhân viên bỏ hệ thống quay lại email; đó là M7, chỉ đo được sau milestone sản xuất. Sprint đầu done không có nghĩa rủi ro đó đã được kiểm.

---

## 8. Sau UAT — thứ tự đề xuất, chưa xếp sprint

Chưa đánh số sprint: độ dài sprint chưa có (A-071), và thứ tự dưới đây nên được xét lại bằng kết quả UAT.

| # | Hạng mục | Phụ thuộc | Vì sao ở vị trí này |
|---|---|---|---|
| 1 | Endpoint đổi `operating_mode` (`POST /operating-mode/transitions`), cùng lớp 3 của ADR-023 | ADR-020, ADR-023 | Không cần cho UAT vì mọi môi trường giữ `NON_PRODUCTION`; cần trước milestone sản xuất (NFR-03) |
| 2 | F5 — màn hình thu hồi `[Should]`, cùng thao tác đưa `document` sang `SUPERSEDED` | A-054 | Dữ liệu và trạng thái đã có từ Sprint 1 (AC F3); chỉ cần khi có văn bản thật đang hiệu lực |
| 3 | Dashboard SLA và cảnh báo tồn đọng `[Should]` | A-002, hai gap ở mục Dashboard SLA & tồn đọng của `11-ops.md` | Ngưỡng cần số liệu vận hành thật |
| 4 | Định tuyến ký nhiều cấp, `SIGNER`, uỷ quyền `[Should]` | Ngữ nghĩa uỷ quyền cho người duyệt (mục Định tuyến ký và uỷ quyền vắng mặt của `08-hitl.md`) | Chỉ cần khi tổ chức có cấp ký trên phòng hành chính |
| 5 | `ROOM_BOOKING` `[Should]` | A-008, A-012, A-046 | Máy trạng thái `room_booking` riêng; contract đang `[NGOÀI-OPENAPI]` |
| 6 | Hạng mục `[Could]` | Mục Scope & priority của `01-prd.md` | — |

**Milestone sản xuất** nằm ngoài roadmap này: chỉ mở khi A-018 đóng (D-009), và trước đó phải đóng những giả định có hạn "trước khi lên `PRODUCTION`" hoặc "trước khi hệ thống sinh văn bản thật" — tối thiểu A-025, A-031, A-036, A-048, A-057, A-059, A-062, A-066, A-070 — cộng ký nhận RISK-08.

---

## 9. Nợ thiết kế Phase 8 — cổng theo sprint

`_PLAN.md` ghi Phase 8 ☑, nhưng các giả định dưới đây — owner Phase 8 — vẫn `Mở`, và `08-hitl.md` v0.2 không giải chúng. Theo phương án mặc định, roadmap đặt mỗi giả định vào cổng của sprint đầu tiên cần nó, thay vì mở lại Phase 8. Người quyết vẫn là owner ghi ở `ASSUMPTIONS.md`; roadmap chỉ đặt hạn.

| Mã | Chạm tới | Cổng | Vì sao ở cổng đó |
|---|---|---|---|
| A-055 | `audit_event` ghi cho thao tác nào | Trước Sprint 1 | Hạn gốc: trước khi viết code của `tool_layer` |
| A-029 | `CHANGES_REQUESTED` ca `SLOT_DATA` không có đường sang `EXPIRED` | Trước Sprint 2 | Sprint 2 dựng vòng `SLOT_DATA` |
| A-034 | `PENDING_SEAL` không có lối ra ngoài `SEALED` | Trước Sprint 2 | Sprint 2 dựng nhánh từ chối và sửa; cổng 2 là chỗ duy nhất không có |
| A-038 | Quay lại trong hạn ở một `chat_session` mới | Trước Sprint 2 | AC-2.7 |
| A-044 | Khoá idempotency của `document_halt_record` khi dừng hai lần cùng node | Trước Sprint 2 | Sprint 2 dựng `halt_for_human` và tiếp quản |
| A-053 | Huỷ ở `NEEDS_INFO`, `SUBMITTED`, `IN_REVIEW` | Trước Sprint 2 | Sprint 2 dựng `request_cancel` |
| A-068 | Reset `clarification_count` | Trước Sprint 2 | Hạn gốc "trước UAT"; kéo sớm lên vì Sprint 2 dựng EC-CV-01, ca nhiều yêu cầu trong một phiên làm lộ lỗi. Owner: đợt sửa `03-agents.md` riêng do PO khởi động |
| A-056 | Lượt chat chết giữa chừng không có điểm dừng có tên | Trước Sprint 3 | Phải có trước UAT; nếu quyết thêm một thao tác, cần một sprint để dựng |
| A-052 | Nhập hộ ở cả hai loại; D-006 đang sai theo hai chiều | Trước Sprint 3 | Sprint 3 dựng nhập hộ; hạn gốc là cổng duyệt của chính Phase 8 |
| A-054 | Không thao tác nào đưa `document` sang `SUPERSEDED` | Sau UAT, cùng F5 | Không chạm hạng mục nào của Sprint đầu |

---

## 10. Ma trận truy vết

Mỗi dòng là một AC hay NFR của `01-prd.md`, và sprint mà nó **đạt lần đầu**. Sprint sau chỉ giữ cho nó không vỡ.

| PRD | Nội dung, rút gọn | Sprint |
|---|---|---|
| F1 | Phân loại hoặc hỏi lại khi nhập nhằng | 1 (đường chính), 2 (EC-CV-03) |
| F1 | Ngoài phạm vi có hướng xử lý thủ công, đúng cả khi kho rỗng | 2 (kho rỗng), 3 (có kho) |
| F1 | Thu slot, chỉ `SUBMITTED` khi đủ điều kiện xử lý | 1 |
| F1 | Nhiều nhu cầu một lượt; đổi loại giữa chừng; quay lại sau gián đoạn | 2 |
| F2 | Render tại thời điểm `SUBMITTED` | 1 |
| F2 | Chỉ điền biến; LLM chỉ sinh nội dung tự do | 1 |
| F2 | Provenance `HR_PROFILE` trên màn hình duyệt | 1 |
| F2 | Chỉ vào `PENDING_APPROVAL` khi đủ điều kiện trình duyệt | 1 (kiểm), 2 (nhánh trượt → `halt_for_human`) |
| F3 | Hai cổng là hai quyết định | 1 |
| F3 | Từ chối, yêu cầu sửa có lý do | 2 |
| F3 | Cấp số đúng một lần, nguyên tử, không trùng khi đồng thời; `VOIDED` không tái sử dụng | 1 (cấp số), 2 (đồng thời, `VOIDED`) |
| F3 | Mỗi quyết định một `audit_event` | 1 |
| F3 | Bản render ở `SEALED`/`ISSUED` bất biến; không xoá cứng `ISSUED`; mô hình có `REVOKED`/`SUPERSEDED` | 1 (ứng dụng, local), 2 (tầng lưu trữ, Render) |
| F4 | Trạng thái có diễn giải tiếng Việt; thiếu gì, sửa gì; hàng đợi chờ lâu nhất trước; `request` và artifact hiển thị riêng | 1 (hàng đợi), 3 (đủ) |
| F6 | Thêm loại thứ ba không sửa code | 3 (diễn tập), 4 (UAT) |
| F6 | Template có phiên bản, bản gốc bất biến; kiểm biến khi tải lên; import CSV có provenance; không kiểm thể thức | 3 |
| NFR-01 | HITL hai cổng | 1 |
| NFR-02 | Tách biệt trách nhiệm theo người thụ hưởng, đường thoát tự duyệt | 1 (chặn), 3 (nhập hộ, đường thoát) |
| NFR-03 | Chế độ phi sản xuất: watermark, dải `TRIAL`, dấu thử nghiệm | 1 |
| NFR-04 | Người dùng thưa | 3 (đo ở M3, Sprint 4) |
| NFR-05 | Mask log theo `slot_sensitivity`; allowlist prompt | 1 |
| NFR-06 | Dừng có kiểm soát khi chạm trần | 2 |
| NFR-07 | Bộ eval 37 ca | 3 (chạy), 4 (có đáp án, là cổng) |
| NFR-08 | Phản hồi chat tăng dần; thao tác duyệt không chờ mù | 1 (stream lượt), 2 (đo gom đệm trên Render, S3 của Spike 1 cho số) |
| DoD 1–4 | Mục Definition of Done của `01-prd.md` | 4 |

Không có AC nào của F1, F2, F3, F4, F6 hay NFR-01 → NFR-08 không có sprint.

---

## Open Questions

Mọi mục có owner và hạn ở `ASSUMPTIONS.md`. Mục này gom những gì Phase 12 phát hiện.

1. **Phase 8 ☑ mâu thuẫn với hạn cứng của A-052.** A-052 ghi *"Phase 8 không được duyệt khi A-052 chưa giải"*; A-052 vẫn `Mở`, và mục ngày 2026-09-14 của `CHANGELOG.md` đánh ☑ ngay khi tạo `08-hitl.md` v0.1. Roadmap theo phương án (a) — đặt nợ vào cổng, mục 9 — nhưng **không** sửa `_PLAN.md`. Anh quyết giữ ☑ hay trả về ☐.
2. **A-073 — mới.** Nhánh ngoài phạm vi luôn gọi `embed_query`, kể cả khi kho rỗng, nên AC Must của F1 cần một embedding model mà A-028 chưa chọn. Hai hướng ghi ở A-073; hướng (a) là một đợt sửa `03-agents.md`, không thuộc Phase 12.
3. **`tools/contract-checks` chưa phủ bảng của Phase 9.** `employee_credential` và `rate_limit_window` không nằm trong nhóm nào của `check_grants.py`; migration `0002`–`0004` chưa từng được kiểm bằng bộ này (mục Đề xuất diff của `11-ops.md` đã ghi vế sau). Đưa vào deliverable của Sprint 1, không tự sửa ở phase này.
4. **A-072 — mới.** Object storage cho local cần ADR trước Sprint 1; Docker local trên máy triển khai đang hỏng (mục Xác minh contract của `06-structure.md`) có thể loại luôn các lựa chọn chạy bằng container.
5. **A-074 — mới.** Loại yêu cầu thứ ba cho AC cứng của F6 chưa chọn, và cả hai ứng viên sẵn có đều đòi năng lực ngoài Sprint đầu.
6. **A-071 — mới.** Độ dài sprint và năng lực đội chưa có; roadmap chỉ có thứ tự.
7. **Tên "Sprint đầu" dễ đọc lẫn với Sprint 1.** Đã thêm định nghĩa vào `GLOSSARY.md`; không đổi tên trong các phase đã đóng. Nếu anh muốn đổi hẳn tên — ví dụ thành một tên chỉ phạm vi phát hành — thì đó là việc của Phase 13 cùng `CHANGELOG.md`.
