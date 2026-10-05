# Security & Guardrails — Admin Service Desk Agent (BO-19)

**Phiên bản:** 0.14 · **Trạng thái:** Draft chờ duyệt · **v0.3:** đợt sửa 3b sau Phase 13 — thêm mục 13, quyền của chủ thể dữ liệu ở mức nghĩa vụ (AUD-24 của `13-audit.md`); không sửa mục nào khác · **v0.4:** căn cứ bảo vệ dữ liệu cá nhân đổi sang Luật 2025 và Nghị định 356/2025/NĐ-CP (AUD-26); thời hạn thực hiện quyền của chủ thể · **v0.5:** đợt sửa 4 — dòng A-082 ở mục Mô hình mối đe doạ; `audit.read_all` ở mục Row-level theo phòng ban (AUD-24); nội dung cũ (AUD-11, AUD-22) · **v0.6:** đợt sửa 5 sau Phase 13 — tham chiếu theo tên mục (AUD-17); tính chất `argon2id` `[CẦN XÁC MINH]` (AUD-21) · **v0.7:** dòng A-082 ở mục Mô hình mối đe doạ trỏ tài liệu tham chiếu `langsmith` (2026-09-27) · **v0.8:** A-055 `Đã chốt` — hướng 1, danh sách miễn `audit_event` (2026-09-27) · **v0.9:** tham số `argon2id` làm việc và trần verify đồng thời — WV-16, WV-16b (PO, 2026-10-02) · **v0.10:** bảng secret: `bo19_admin` — chỉ PO giữ (2026-10-04) · **v0.11:** bảng secret: `bo19_app` qua `BO19_DATABASE_URL` (2026-10-04) · **v0.12:** bảng secret: `bo19_migrator` qua `BO19_MIGRATOR_DATABASE_URL` (2026-10-04) · **v0.13:** bảng secret: `bo19_admin` ở `~/.bo19/admin.env`, ngoài repo (2026-10-04) · **v0.14:** B3 — bốn yêu cầu an ninh của đăng nhập (verify giả, ghim thuật toán, IP một hàm, đọc lại DB mỗi request); thao tác `rate_limit_window_increment` và vì sao không cần `kernel`; WV-12 thay `TBD` ở mục Ngưỡng (2026-10-05)

> File này chốt AuthN/AuthZ, rate limit, PII masking và hiển thị theo `slot_sensitivity`, phòng thủ prompt injection, output validation trước khi render, bảo vệ template gốc, và secret management trên Render. File này **không** thiết kế màn hình (Phase 8 đã đóng phần của nó), **không** định cỡ tham số vận hành bằng số liệu tải thật (Phase 11), và **không** lặp lại lập luận đã có ở ADR-001, ADR-007, ADR-008, ADR-013.

Tên entity, trạng thái, permission, agent, tool dùng đúng `GLOSSARY.md`. Quyết định `D-xxx`/`A-xxx` tham chiếu `00-domain.md` và `ASSUMPTIONS.md`.

**Đã đối chiếu:** `CLAUDE.md`, `_PLAN.md`, `GLOSSARY.md`, `ASSUMPTIONS.md`, `CHANGELOG.md`, `00-domain.md`, `01-prd.md`, `02-architecture.md`, `03-agents.md`, `04-data.md`, `05-api.md`, `06-structure.md`, `07-prompts.md`, `08-hitl.md`, `contracts/schema.sql`, ADR-001 → ADR-019.

**ADR mới:** ADR-020 (`operating_mode_change` qua endpoint có permission, không qua thao tác vận hành); ADR-021 (`argon2id` cho hash mật khẩu).

---

## 1. Mô hình mối đe doạ — tóm gọn

Sản phẩm giao có tên do ADR-013 trỏ tới (điều kiện đảo ngược của vế phiên stateless: "đo ở mô hình mối đe doạ của Phase 9"). Không lặp lại kiến trúc — chỉ nêu tài sản, bề mặt, và cái đang được chấp nhận có chủ.

**Tài sản cần bảo vệ**

| Tài sản | Vì sao |
|---|---|
| Giá trị slot `PER`/`RES` | Dữ liệu cá nhân, nghĩa vụ theo Luật Bảo vệ dữ liệu cá nhân năm 2025 và Nghị định 356/2025/NĐ-CP (A-080) (`[CẦN XÁC MINH]`, A-036) |
| `employee_credential` | Mất là mất toàn bộ AuthN |
| Bản gốc `template` | Sai thể thức = văn bản vô hiệu (RISK-01); rò khung thể thức ra ngoài là rò mẫu con dấu, mẫu chữ ký |
| `document_register` / `document_number` | Nguồn sự thật pháp lý (ADR-011) |
| Session secret, `bo19_migrator` credential, provider API key | Chiếm được là chiếm quyền của toàn hệ thống hoặc của DB |

**Bề mặt tấn công chính** — ai đứng ở đâu: nhân viên đã đăng nhập (chat, upload `external_file` ở `SEAL_REQUEST` `[Could]`), người ngoài chưa đăng nhập (`POST /auth/session`, stream tín hiệu công khai không có), nội dung do bên thứ ba tạo mà hệ thống hiển thị lại (`procedure_document`, `external_document`).

**Đường rời hệ thống ngoài `ai_gateway` qua phụ thuộc bắc cầu:** `langsmith` vào cây phụ thuộc qua `langchain-core`. Hành vi mặc định đã xác minh cho bản 0.14.1 — không đặt biến bật tracing thì không gửi gì (`docs/reference/langsmith-tracing-env.md`); đối chiếu lại khi lockfile chốt bản (A-081). Lớp chặn là bước kiểm khởi động từ chối chạy khi biến bật tracing được đặt — A-082, trước cổng Sprint 1.

**Cái đang được chấp nhận có chủ, không phải khoảng trống**

| Rủi ro | Vì sao chấp nhận | Ghi ở đâu |
|---|---|---|
| Không thu hồi được một phiên đơn lẻ trước khi hết hạn | Đổi lại là một bảng phiên trong `postgresql`, mỗi lần đăng nhập/đăng xuất thành lệnh ghi — đụng A-055 | ADR-013, A-048 |
| Không có `ACCOUNT_LOCKED` | Mã đó lộ tài khoản nào tồn tại; khoá theo `employee_code` mở đường DoS nhắm vào một người (mục 6) | A-048, mục 6 của file này |
| Mật khẩu seed cũng là mật khẩu dùng lâu dài tới khi có đường đổi | Ngoài Sprint đầu (A-048) | A-048 |
| Role sở hữu (`bo19_migrator`) sửa được mọi thứ | Bất biến bằng `GRANT`/`REVOKE` chặn ứng dụng, không chặn người vận hành DB | Mục Hai role và bất biến bằng quyền của `04-data.md` |

---

## 2. AuthN

- **Đăng nhập:** `employee_code` + mật khẩu (đã chốt, ADR-013). Sai mã hay sai mật khẩu trả cùng `INVALID_CREDENTIALS` — không phân biệt để không lộ tài khoản nào tồn tại.
- **`employee_credential`** — bảng riêng, khác `employee`, thêm bằng migration của Phase 9 (A-048). DDL ở mục DDL bổ sung của Phase 9 bên dưới. `bo19_app` chỉ `SELECT` (H1) — ghi (seed, đổi, đặt lại) là thao tác vận hành bằng `bo19_migrator`, cùng loại với nạp `employee_role`.
- **Hash mật khẩu — `argon2id` (ADR-021).** Lý do bằng tính chất hàm, không trích số liệu benchmark từ trí nhớ (luật trích dẫn của `CLAUDE.md`): `argon2id` là một trong hai họ hash có tham số bộ nhớ **độc lập** với số vòng lặp (họ còn lại là `scrypt`) `[CẦN XÁC MINH]` — bản gốc chưa có trong `docs/reference/` (AUD-21), nên một cuộc dò mật khẩu ngoại tuyến song song hoá bằng phần cứng chuyên dụng — chiều tấn công có lợi thế nhất — tốn tài nguyên hơn hẳn so với `bcrypt`/`PBKDF2`, hai hàm không có tham số bộ nhớ độc lập. Chi tiết Options/Rejected alternatives ở ADR-021. Phiên bản thư viện và bộ tham số khuyến nghị `[CẦN XÁC MINH]` — chưa có bản gốc trong `docs/reference/`. **Tham số cụ thể — TBD, xem A-048:** bộ nhớ, số vòng lặp, độ song song. Cột `hash_algorithm` lưu định danh thuật toán cùng dòng hash, để đổi thuật toán sau này không phải migrate hồi tố toàn bộ bảng trong một bước.
- **Bốn yêu cầu an ninh của đăng nhập — PO, 2026-10-05, kế hoạch B3; mỗi yêu cầu có test:** (1) **Mã nhân viên không tồn tại vẫn chạy một lần verify `argon2id`** với một hash giả cùng tham số, dựng lúc khởi động — nên thời gian phản hồi không phân biệt được sai mã với sai mật khẩu; nhân viên `is_active = false` và nhân viên thiếu dòng credential đi cùng nhánh đó. (2) **Kiểm token ghim thuật toán:** danh sách thuật toán cố định trong code, không đọc `alg` từ header token; token `alg=none` và token ký bằng thuật toán khác bị từ chối (ADR-028, mục Cập nhật B3). (3) **IP của rate limit đọc ở đúng một hàm, mặc định không tin `X-Forwarded-For`** — A-062, cổng 2.7. (4) **`GET /me` và mọi endpoint đã đăng nhập đọc lại `is_active` và permission từ DB ở mỗi request** (ADR-013): tắt `is_active` thì request kế tiếp trả `UNAUTHENTICATED`. Thời hạn token là WV-17, 8 giờ tuyệt đối; thuật toán `HS256`, secret tối thiểu 32 byte (A-088 `Đã chốt`).
- **Ràng buộc RAM của instance Render — nói thẳng, không đo được ở phase này.** `argon2id` cấu hình bộ nhớ càng cao thì chống dò càng tốt, nhưng mỗi lần đăng nhập hợp lệ cũng tốn đúng bằng đó RAM trên instance chạy `api`. Trên instance nhỏ, cấu hình bộ nhớ cao cho nhiều lượt đăng nhập đồng thời có thể cạnh tranh RAM với phần còn lại của tiến trình. Đây là đánh đổi thật, không phải chi tiết cấu hình — tham số cuối cùng phải chọn có đối chiếu với hạng instance đã thuê (A-002, A-031), không chọn theo khuyến nghị chung chung rồi mặc định là an toàn.
- **Tham số làm việc — PO duyệt 2026-10-02, nhãn "chưa hiệu chỉnh" (WV-16, WV-16b ở `proposals/sprint1-working-values-a031-a048.md`):**
  - `argon2id` với `time_cost=2`, `memory_cost=19456` KiB, `parallelism=1` — cấu hình thứ hai trong năm cấu hình của OWASP (`docs/reference/owasp-password-storage-argon2id.md`). Chọn sau khi đo: bộ nhớ đỉnh tăng xấp xỉ `memory_cost` cho mỗi lần verify đang chạy (mục Bộ nhớ đỉnh và thời lượng khi verify đồng thời của `docs/reference/argon2-cffi-parameters.md`), và instance của giai đoạn build là `free`, 512 MB RAM (A-085).
  - **Trần số lần verify đồng thời trong một tiến trình `api`: 4.** Lần thứ năm chờ tới khi có chỗ. Rate limit giới hạn số lần thử theo IP trong một cửa sổ, không giới hạn số lần chạy cùng lúc; trần này cho bộ nhớ dành cho verify một cận trên cố định, khoảng 4 × 19 MiB, bất kể tải. Thời gian chờ ở trần này cộng vào thời lượng đăng nhập; chưa có số đo trên Render.
- **Session token — đã chốt ở ADR-013.** Ký bằng secret phía server, mang định danh nhân viên + thời điểm hết hạn, không mang permission. **Thời hạn token — `TBD`, giao đích danh cho Phase 9 ở A-048, chưa từng có giá trị:** thêm **A-048** dòng mới — không đặt token sống quá dài (mỗi ngày dùng thêm là một ngày rủi ro của rủi ro có chủ "không thu hồi được phiên đơn lẻ"), không quá ngắn (NFR-04: người dùng thưa, đăng nhập lại nhiều là ma sát). Giá trị số: `TBD`, đo cùng đợt với hành vi dùng thật (A-002).
- **Xoay vòng secret — không phải quyết định thuần vận hành.** ADR-013 đã ghi: đổi secret vô hiệu hoá **mọi** phiên đang mở, không phải một cơ chế "làm mới an toàn" âm thầm. Vì vậy chu kỳ xoay vòng là một đánh đổi với người đang dùng hệ thống, không phải một con số vệ sinh bảo mật đặt tuỳ ý: xoay càng dày thì càng nhiều lần toàn bộ nhân viên bị đăng xuất giữa chừng. **Quyết định của Phase 9:** xoay vòng theo lịch **không tự động, do người vận hành thực hiện**, không đặt cron tự xoay — vì hệ quả (đăng xuất hàng loạt) cần một người biết trước để không trùng giờ cao điểm (tần suất dùng thưa của NFR-04 nghĩa là "giờ cao điểm" khó đoán, càng phải để người quyết). Tần suất cụ thể: `TBD`, thêm vào A-048.
- **Vòng đời credential ngoài Sprint đầu (đã chốt ở A-048):** buộc đổi lần đầu, đổi, quên, khoá sau nhiều lần sai — không endpoint. Giữ nguyên, xem mục 6 về rủi ro của việc giữ nguyên.

---

## 3. AuthZ — hoàn tất danh mục permission

`tool_layer` là lớp kiểm permission cuối cùng và fail-closed (ADR-008 cùng họ): permission không được cấp thì không tool nào chạy, kể cả khi endpoint gọi đúng. `api` kiểm permission tĩnh theo endpoint (mục Nguyên tắc chung của `05-api.md`) là điều kiện cần, không phải điều kiện đủ — chi tiết vì sao ở mục 4.

### 3.1 Ba permission mới

| Permission | Cho phép làm gì | Cấp cho ai |
|---|---|---|
| `request_type.manage` | Thêm/sửa `request_type`, `slot_definition` (trừ đổi độ nhạy — vẫn qua `slot_sensitivity_change`) | Cấp lẻ (A-042) |
| `procedure.read_all` | Xem mọi `procedure_document` qua `procedure_retrieval`, bất kể `department_scope` | Cấp lẻ (A-043) |
| `operating_mode.change` | Đổi `operating_mode` giữa `NON_PRODUCTION` và `PRODUCTION` | Cấp lẻ (mục 12) |

Cả ba **cấp lẻ, không thuộc gói vai trò nào** — cùng khuôn với `document.sign`, `document.revoke_confirm` (D-006) và `procedure.manage` (A-033) đã có ở mục Gói permission theo vai trò của `00-domain.md`: hành động hiếm, rủi ro cao hoặc đòi một nghĩa vụ riêng, cấp trực tiếp cho một hoặc vài người cụ thể thay vì đi kèm mặc định một vai trò.

**`procedure.manage` không kéo theo `procedure.read_all`.** Nạp/thay/gỡ tài liệu (`procedure.manage`) và xem tài liệu ngoài phòng ban của mình trong đường retrieval (`procedure.read_all`) là hai nghĩa vụ khác nhau — cùng lý do đã tách `procedure.manage` khỏi `template.manage` ở A-033: người quản lý nội dung không tự động có quyền tiêu thụ nội dung ngoài phạm vi vai trò tác nghiệp của mình.

Danh mục permission: **22 → 25.** Sửa mục Danh mục permission của `00-domain.md` (thêm ba dòng vào bảng 7.1, thêm câu về `procedure.manage`/`procedure.read_all` sau bảng) và mục Permission của `GLOSSARY.md`. Câu về `request.read_all`/phòng ban ở mục Gói permission theo vai trò **đã viết lại tại chỗ** — xem mục 5.2, không còn là vá bằng chú thích.

### 3.2 Đường nạp thật — không chỉ đổi trên giấy

Ba permission mới, và toàn bộ danh mục 25 permission, vào DB qua **data migration** (`backend/migrations/data/0001_permission_catalog.sql`, mục Dữ liệu danh mục nạp ở đâu của `04-data.md`): `INSERT` vào `permission`, `role`, `role_permission`, chạy bằng `bo19_migrator`, sau schema migration, trước data migration của `request_type`/`employee`. File này seed **toàn bộ** danh mục — không chỉ ba dòng mới — vì `backend/migrations/data/` trước Phase 9 chỉ có `.gitkeep`: đường nạp cho 22 permission gốc cũng chưa từng được viết, dù đã "chốt" trên giấy từ Phase 4. Không đóng phase này mà im lặng bỏ qua chỗ hở đó.

**Sáu permission cấp lẻ — không seed vào `employee_permission_grant`.** `document.sign`, `document.revoke_confirm` (đã có từ D-006), cộng `procedure.manage` (A-033), `request_type.manage`, `procedure.read_all`, `operating_mode.change` (Phase 9) đều cấp cho **một nhân viên cụ thể**, không cấp theo mẫu. Không có nhân viên thật ở thời điểm thiết kế nên không seed được — khác `permission`/`role`/`role_permission` vốn là dữ liệu danh mục thuần, không phụ thuộc ai đã import. Cấp permission cấp lẻ là một dòng `employee_permission_grant` (`id`, `employee_id`, `permission_code`, `granted_at`), ghi bằng **thao tác vận hành**, chạy bằng `bo19_migrator` — cùng khuôn với seed `employee_role` và `employee_credential` (H1, A-048), không qua `tool_layer` vì không có endpoint cấp permission ở Sprint đầu (vai trò quản trị hệ thống không được mô hình hoá, mục Permission và vai trò của `00-domain.md`). **Ai được cấp — chưa có ai được chỉ định** ở Sprint đầu; đây là thông tin thật, không phải ô trống chờ điền, cùng khuôn A-018 ("không có ai" nghiệm thu thể thức).

### 3.3 A-039, A-042, A-043 — đóng

- **A-042 → Đã chốt.** Hạn cứng đã đáp ứng ở cả hai lớp: `request_type.manage` vào danh mục ở `00-domain.md`/`GLOSSARY.md` **và** vào DB qua `backend/migrations/data/0001_permission_catalog.sql` (mục 3.2). Endpoint cấu hình `request_type` không còn từ chối mọi người **sau khi migration này chạy** — điều kiện đó nói rõ trong `ASSUMPTIONS.md`, không giả định nó đã chạy.
- **A-039 → Đã chốt.** `procedure.manage` giữ cấp lẻ, không gộp vào `ADMIN_OFFICER` hay bất kỳ gói nào — cùng lý do đã có ở A-033 (nghĩa vụ cam kết nội dung không PII khác hẳn nghĩa vụ tác nghiệp hàng ngày).
- **A-043 → Đã chốt.** Vế permission của bộ lọc kho quy trình được giải bằng `procedure.read_all`; bộ lọc SQL ở mục Lọc quyền và so khớp phòng ban của `04-data.md` (mục 6.3) thêm một nhánh `OR`: `procedure_visibility = 'ORG_WIDE'` **hoặc** mã phòng ban của người đang chat nằm trong `department_scope` **hoặc** người đang chat có `procedure.read_all`. Không đổi vị trí lọc — vẫn lọc trước khi xếp hạng, trong cùng một câu truy vấn (lớp 1 của mục Retrieval trong `03-agents.md`).

---

## 4. Tool permission theo vai trò người yêu cầu

Ranh giới thật **không phải** "`api` kiểm tĩnh, `tool_layer` kiểm theo instance" — `05-api.md` đã có lớp instance ở tầng HTTP rồi: tài nguyên tồn tại mà người gọi không được xem thì trả `NOT_FOUND`, không trả `PERMISSION_DENIED` (mục Nguyên tắc chung của `05-api.md`). Ranh giới thật là: **tool của graph không có endpoint** (`INV-02`), nên câu hỏi đúng là *mỗi tool chạy dưới danh nghĩa ai*, và hai graph trả lời khác nhau.

### 4.1 `intake_graph` — chạy dưới danh nghĩa nhân viên đang chat

Mọi tool của `intake_agent` (mục Ai được gọi tool nào của `03-agents.md`) nhận `request_id`/`chat_session_id` đã bị buộc vào đúng phiên đang xử lý — thread key `intake:{chat_session_id}` (mục Agent, graph, node, tool của `GLOSSARY.md`), và phiên thuộc về đúng một nhân viên (`chat_session.employee_id`). Permission cần cho tool ghi ghi "Tác nhân hệ thống" ở mục Tool Registry của `03-agents.md` không có nghĩa là **không kiểm ai** — nó có nghĩa là quyền được kiểm **một lần, ở lối vào**: `POST /chat-sessions/{id}/turns` xác nhận người gọi là chủ phiên (`request.create` hoặc `request.create_on_behalf`, mục Hội thoại của `05-api.md`) trước khi lượt được nhận; mọi tool bên trong lượt đó kế thừa đúng phạm vi của phiên, không tự hỏi lại permission theo tên. Đây là lớp chống truy cập chéo instance (đọc/ghi `request` của người khác qua một `request_id` đoán được): tool không nhận `request_id` tuỳ ý từ input LLM, nó chỉ thao tác trên `request` đang mở của **chính đồ thị đang chạy**, và đồ thị đó bị khoá vào một `chat_session` từ lúc `load_turn`.

### 4.2 `document_graph` chạy trong job — không có người yêu cầu nào tại thời điểm chạy

Đây là ca thật sự cần trả lời, không phải ca đã có sẵn câu trả lời ở tầng HTTP. `render_document`, `resume_document_graph`, `finalize_issue` chạy trong `queue_worker` (ADR-004, ADR-010), được `job` đánh thức — không có ai đang "gọi API" tại thời điểm đó.

- **Căn cứ cấp quyền:** không phải permission của một người đang online, mà là **việc job đã được enqueue hợp lệ trong một giao dịch đã qua kiểm permission** (mục Thao tác của `tool_layer` theo nhóm được gọi của `GLOSSARY.md` — thao tác cổng kiểm permission, chuyển trạng thái và enqueue job **trong cùng một giao dịch**, mục Thao tác cổng trên văn bản của `08-hitl.md`). Permission được kiểm **một lần, ở lúc enqueue**, không kiểm lại lúc job chạy — vì lúc đó không còn "người gọi" nào để hỏi.
- **Ai chịu trách nhiệm:** `audit_event` của job mang `actor_kind = SYSTEM`, không có `actor_employee_id` — đúng bản chất, không phải khoảng trống. Trách nhiệm không nằm ở audit_event của job, mà ở **audit_event của thao tác cổng đã enqueue nó**: mỗi job mang được dấu vết đúng một thao tác cổng khởi phát nó (`decision_record`/`audit_event` của thao tác đó), nên truy vết ngược từ một hành vi hệ thống về đúng người ra lệnh không đi qua bảng `job`, mà qua liên kết `job` → thao tác cổng đã enqueue nó.
- **Vì sao đây không phải đường đi vòng qua permission của người khởi phát.** Job không tự chọn làm gì — nó chỉ tiếp tục đúng một `document_graph` đã dừng ở đúng một `interrupt`, với dữ liệu đã được ghi (và kiểm permission) từ trước lúc enqueue. Một job không có cách nào đổi phạm vi hành động của nó sang một `document_id` khác hay một permission khác với thao tác cổng đã tạo ra nó — đó là bất biến của việc `job` mang đúng một `subject_document_id` (mục Bảng chi tiết của `04-data.md`), không phải một tham số job có thể bị đổi giữa chừng.

### 4.3 Vì sao vẫn cần hai lớp dù đã trả lời "chạy dưới danh nghĩa ai"

`api` khai permission tĩnh theo **loại** hành động (đúng một permission cho mỗi endpoint), còn `tool_layer` kiểm lại theo **trạng thái thật của đối tượng tại thời điểm ghi** — `NOT_DRAFT`, `ILLEGAL_TRANSITION`, `NOT_READY` (mục Tool Registry của `03-agents.md`). Hai lớp không trùng nhau: `api` có thể đúng (người gọi có `document.approve_content`) nhưng hành động vẫn sai (document đã bị người khác duyệt giữa lúc `api` kiểm permission và lúc `tool_layer` thực thi — chính ca "hai người thao tác cùng lúc" ở mục Hai người thao tác cùng lúc của `05-api.md`). Bỏ lớp thứ hai thì một điều kiện đua (race) giữa kiểm quyền và ghi dữ liệu biến thành một lần ghi sai trạng thái không ai bắt được.

---

## 5. Row-level theo phòng ban

Hai trục khác nhau, không gộp một tiêu đề.

### 5.1 Kho quy trình — đã giải ở mục 3.3

Vế permission của A-043 xong; vế phòng ban (`department_scope`) đã có từ Phase 4.

### 5.2 `request.read_all` — trục thứ hai, org-wide đã áp

*`audit.read_all` theo cùng quyết định (đợt sửa 4 sau Phase 13, AUD-24): org-wide ở Sprint đầu, cùng điều kiện kích hoạt lọc (A-061) và cùng chỗ bám kỹ thuật — lọc `audit_event` theo phòng ban của người thụ hưởng của `request` mà sự kiện gắn vào. Sự kiện không gắn `request` nào — cấu hình, đổi chế độ — không lọc theo phòng ban.*

**Quyết định: giữ org-wide ở Sprint đầu — đã sửa trực tiếp** vào mục Gói permission theo vai trò của `00-domain.md`, không còn là câu cũ kèm chú thích. Lý do: A-001 giả định một pháp nhân đơn nhất; đề bài mô tả **một** Phòng Hành chính xử lý tập trung mọi yêu cầu của tổ chức (mục Bối cảnh đề tài của `CLAUDE.md`), nên `ADMIN_OFFICER` — vai trò duy nhất mang `request.read_all` ở Sprint đầu — về đúng nghĩa vụ cần thấy toàn bộ để xử lý.

**A-061 viết lại theo đúng nghĩa của nó: không phải "có sửa câu hay không" (đã sửa) mà là điều kiện kích hoạt lọc.** Org-wide đứng được chừng nào A-001 còn đúng. Điều kiện kích hoạt lọc theo phòng ban: A-001 bị bác bỏ — tổ chức thật ra có **từ hai Phòng Hành chính xử lý độc lập trở lên**. Khi đó "xem mọi yêu cầu" không còn là một nghĩa vụ duy nhất mà là nhiều nghĩa vụ tách biệt theo đơn vị.

**Chỗ bám kỹ thuật nếu sau này kích hoạt** (neo sẵn, không cài đặt): lọc qua `employee.department_code` của người thụ hưởng, tức join `request.beneficiary_employee_id → employee.department_code`, **không phải** phòng ban của người tạo (D-006: người thụ hưởng mới là chủ của yêu cầu). Không có bảng `department` (mục Nguyên tắc dữ liệu của `04-data.md`) — mã phòng ban là chuỗi do CSV quyết định, nên cùng hệ quả đã ghi ở mục Lọc quyền và so khớp phòng ban của `04-data.md`: CSV đổi mã một phòng ban mà chưa kịp cập nhật nơi dùng nó thì lọc theo phòng ban mất chức năng theo hướng **ẩn nhầm** một số yêu cầu khỏi người vốn cần thấy (fail-closed, cùng họ với ADR-008) — không theo hướng rò thêm.

---

## 6. Rate limit

**Cơ chế: bảng PostgreSQL, cửa sổ cố định** (B3, đồng ý bảng thay vì in-memory — đúng vì Render có thể chạy nhiều instance `api`, và in-memory mỗi instance đếm riêng thì trần thực tế nhân lên theo số instance).

### 6.1 DDL — xem mục DDL bổ sung của Phase 9

`rate_limit_window (scope, window_start, attempt_count)`, khoá chính `(scope, window_start)`. `scope` là chuỗi ghép — ví dụ `login_ip:{ip}` — **không bao giờ khoá thuần theo `employee_code`**. **IP đọc từ đâu, phía sau proxy của Render, là `[CẦN XÁC MINH]` — A-062, chưa ghi từ trí nhớ.** Header giả được hoặc đọc sai vị trí thì lớp này chỉ còn là gờ giảm tốc, không phải chặn thật — nói thẳng ở A-062, không để ẩn trong quyết định nghe chắc chắn dưới đây: `employee_code` không bí mật (dùng để đăng nhập, không phải bí danh), nên rate limit thuần theo nó là một đường DoS có chủ đích nhắm vào một nhân viên cụ thể — đúng lý do `05-api.md` đã không có mã `ACCOUNT_LOCKED` (mục Xác thực và chống CSRF của `05-api.md`, A-048). Khoá theo IP là chính; ghép thêm `employee_code` vào `scope` cho một ngưỡng chặt hơn ở cùng cặp (IP, mã) là được, miễn ngưỡng theo **IP đơn** vẫn tồn tại độc lập và không thể bị vô hiệu hoá bằng cách đổi mã liên tục từ cùng một IP.

### 6.2 Rủi ro của việc ghi trước khi xác thực

`POST /auth/session` ghi (tăng bộ đếm) **trước khi** biết người gọi là ai — đây là lệnh ghi do request chưa xác thực gây ra, tức chính bề mặt mà kẻ tấn công kiểm soát được tần suất. Hai thứ có thể bị mở:

- **Bơm dòng.** Bị chặn bằng chính khoá chính `(scope, window_start)`: một `scope` trong một cửa sổ chỉ có đúng một dòng, `UPSERT` (`INSERT … ON CONFLICT (scope, window_start) DO UPDATE SET attempt_count = attempt_count + 1`) tăng tại chỗ chứ không thêm dòng mới. Số dòng bị chặn trên bởi (số `scope` khác nhau) × (số cửa sổ còn chưa dọn), không bởi số lần thử.
- **Chiếm connection của pool.** Cùng họ rủi ro với vòng poll tín hiệu ở ADR-013 (mục C4): mỗi lần đăng nhập vốn đã cần một connection để kiểm `employee_credential`, nên tăng bộ đếm trong **cùng giao dịch, cùng connection đó** không mở thêm kết nối nào — không phải một request phụ. Rủi ro thật là **tổng số lần đăng nhập** cạnh tranh pool với request nghiệp vụ khi bị dội, không phải bản thân việc có bảng đếm. Đây là lý do rate limit phải chặn **trước** khi chạm `employee_credential` khi một `scope` đã vượt ngưỡng của cửa sổ hiện tại — kiểm bộ đếm rẻ hơn kiểm hash mật khẩu, nên kiểm nó trước.

**Thao tác ghi — B3, 2026-10-05.** Bộ đếm tăng qua thao tác `rate_limit_window_increment` của `tool_layer/endpoint_ops/`: một câu `INSERT … ON CONFLICT (scope, window_start) DO UPDATE SET attempt_count = attempt_count + 1 RETURNING attempt_count`, commit ngay để lần thử sai vẫn được đếm. Không cần `tool_layer.kernel` — không có tác nhân, không `audit_event` (A-055), không đổi `status`, không enqueue. `api` không import `persistence.write`; nó gọi thao tác này. Cửa sổ cố định tính theo đồng hồ của DB (không theo đồng hồ từng instance `api`): `window_start` là mốc làm tròn xuống bội của độ dài cửa sổ. Đếm sau khi tăng **lớn hơn** ngưỡng thì trả `RATE_LIMITED` kèm `retry_after_seconds` tới hết cửa sổ, chưa chạm `employee_credential`. Bộ đếm tăng ở mọi lần thử, kể cả lần đúng (WV-12).

### 6.3 Dọn cửa sổ hết hạn

`queue_worker` cron xoá dòng có `window_start` cũ hơn N cửa sổ (giá trị TBD, A-031) — cùng khuôn với `expire_request`, `checkpoint_purge`.

### 6.4 Không sinh `audit_event` — thuộc danh sách miễn của A-055

Tăng bộ đếm và dọn cửa sổ **không** sinh `audit_event`. Đây là **sổ sách kỹ thuật**, cùng họ với `llm_usage` và với việc "giành, gia hạn lease, kết thúc job" của `queue_worker` mà A-055 đã xếp là ngoại lệ ở vòng duyệt Phase 6 ("trường hợp thứ ba"): sinh `audit_event` cho mỗi lần tăng bộ đếm làm loãng nhật ký nghiệp vụ đúng như hệ quả thứ nhất mà A-055 đã nêu, và một lần thử đăng nhập sai — kể cả của kẻ tấn công — không phải "hành động có ảnh hưởng nghiệp vụ" theo định nghĩa `audit_event` ở `GLOSSARY.md`. Phase 9 không tự giải A-055 mà thêm **A-055 trường hợp thứ tư** trong `ASSUMPTIONS.md`. **Cập nhật 2026-09-27:** A-055 `Đã chốt` theo hướng 1 — tăng bộ đếm và `rate_limit_window_sweep` nằm trong danh sách miễn ở mục Tool Registry của `03-agents.md`; không còn là lệch khỏi luật.

### 6.5 Ngưỡng — chưa định cỡ

Số lần thử mỗi cửa sổ, độ dài cửa sổ: **WV-12 — 15 phút, 20 lần thử mỗi `scope`**, nhãn "chưa hiệu chỉnh" (PO duyệt 2026-09-27; chạy từ B3). Thêm vào **A-031** (cùng họ tham số vận hành, owner Product Owner theo câu 7 — trước đó "Phase 11"; cơ chế chốt ở Phase 9).

---

## 7. PII masking và hiển thị theo `slot_sensitivity`

`05-api.md` (mục Dữ liệu trong response) để lại nguyên câu: "Quy tắc hiển thị theo độ nhạy trên màn hình duyệt chưa được đặc tả ở đâu cả — thuộc Phase 8 và Phase 9." Phase 8 đóng mà không đặc tả (không có mục nào trong `08-hitl.md` nói tới), nên Phase 9 là chủ cuối cùng của quyết định này.

### 7.1 Phân vai — hai cơ chế trên cùng một thuộc tính, không được lẫn

`slot_sensitivity` (`GLOSSARY.md` mục Enum khác) quyết **ba** việc: mask trong log kỹ thuật, giữ/xoá khi `EXPIRED` (A-014, đã chốt — không đổi ở đây), và hiển thị (quyết định thứ ba, đóng ở đây). Việc slot nào **ra khỏi hệ thống tới một model** do allowlist tự khai của prompt module quyết (ADR-008), **độc lập hoàn toàn** với `slot_sensitivity`. Một slot `RES` vẫn được vào prompt nếu prompt module khai đích danh nó — allowlist không thay đổi độ nhạy, nó chỉ mở một đường đi có kiểm soát. Ví dụ chốt ở NFR-05 và nhắc lại ở mục Guardrail chung của `07-prompts.md`: `purpose` (độ nhạy `RES`) vừa được `draft_free_content` đưa vào prompt, **vừa** bị mask trong log kỹ thuật của chính lời gọi đó — hai việc không mâu thuẫn, vì log kỹ thuật và lời gọi tới model là hai đích khác nhau.

### 7.2 Mask trong log kỹ thuật (`observability`) — đã có, làm rõ cơ chế

| `slot_sensitivity` | Mask trong log kỹ thuật |
|---|---|
| `INT` | Không mask — không tự nó định danh cá nhân |
| `PER` | Thay giá trị bằng `[PER]` trong log; không log cả độ dài hay ký tự đầu/cuối (một mảnh giá trị vẫn là một mảnh dữ liệu cá nhân) |
| `RES` | Thay giá trị bằng `[RES]`, giữ nguyên nghiêm ngặt hơn `PER`: không log tên slot nếu bản thân tên slot đã gợi ý nội dung nhạy cảm (ví dụ log tên slot `bearer_national_id` là chấp nhận được — nó là metadata cấu trúc; log một đoạn trích của giá trị thì không) |

Áp dụng cho **mọi** đích ghi thuộc `observability` — log, trace, span attribute — không riêng log lời gọi model. `chat_message`, `purpose`, `work_content`, `change_reason` mang `RES` nên không bao giờ xuất hiện nguyên văn trong log kỹ thuật, kể cả log lỗi (một exception không được phép serialize giá trị `RES` vào message của nó — ràng buộc này đã có ở dòng Exception rời node chỉ mang mã, mục Nghĩa vụ kế thừa của `06-structure.md` cho exception nói chung; ở đây áp riêng cho giá trị `RES`).

### 7.3 Hiển thị trên màn hình duyệt — quyết định mới của Phase 9

`05-api.md` đã chốt: **contract không che giá trị với người được xem** — API luôn trả đủ, kèm `sensitivity` của từng giá trị (mục Dữ liệu trong response). Người duyệt cần thấy giá trị thật để làm việc (ví dụ đối chiếu `bearer_national_id` khi cấp giấy giới thiệu tới cơ quan nhà nước — EC-IL-03). Vì vậy quy tắc hiển thị **không phải ẩn dữ liệu** — đó là việc client làm gì với `sensitivity` đã nhận:

| `slot_sensitivity` | Hiển thị trên `DocumentReviewPage`/`RequestDetail` |
|---|---|
| `INT` | Hiển thị thẳng, không huy hiệu |
| `PER` | Hiển thị thẳng, kèm huy hiệu nhẹ "Dữ liệu cá nhân" cạnh tên trường |
| `RES` | **Ẩn theo mặc định, hiện khi bấm** — cùng kiểu ô mật khẩu (`••••`, nút "hiện"). Kèm huy hiệu "Hạn chế". Không tự động hiện khi tải trang |

**Lý do ẩn-theo-mặc-định chỉ áp cho `RES`, không áp cho `PER`:** rủi ro chặn ở đây là lộ **vô ý** — màn hình chia sẻ trong cuộc họp, ảnh chụp màn hình, người đứng sau nhìn — không phải lộ cho chính người duyệt (người đó vốn được xem). `RES` là định danh pháp lý hoặc suy ra được tình trạng sức khoẻ/pháp lý/tài chính — mức thiệt hại của một lần lộ vô ý cao hơn hẳn `PER`; `PER` (tên, ngày sinh) không đủ để bù lại chi phí thao tác "bấm để hiện" trên **mọi** trường ở một màn hình mà người dùng chỉ mở vài lần một năm (NFR-04).

**Xuất/tải xuống — không mở đường vòng.** Bất kỳ chức năng xuất danh sách hay CSV nào (nếu có ở phase sau) phải áp đúng quy tắc trên; không có "chế độ xuất" bỏ qua ẩn mặc định của `RES`. Ngoài phạm vi Sprint đầu vì chưa có chức năng xuất nào được thiết kế — ghi để chặn trước, không phải để mô tả cái chưa tồn tại.

---

## 8. Prompt injection — chỉ nội dung mới

ADR-007 (LLM không tự gọi tool) và ADR-008 (allowlist là danh sách nạp, fail-closed) đã đóng phần lớn bề mặt. Hai chỗ còn hở, chưa được đặt tên đầy đủ ở phase nào trước:

### 8.1 EC-SR-02 — điểm phòng thủ chính, hiện tại chỉ có [Could]

`00-domain.md` tự gọi EC-SR-02 là "điểm phòng thủ prompt injection chính", nhưng nó nằm trong `SEAL_REQUEST` — `[Could]`, chưa vào Sprint đầu. **Nội dung mới:** khi `SEAL_REQUEST` kích hoạt, `external_file` (độ nhạy `RES`, nguồn `UPLOAD`) không bao giờ được đọc bởi bất kỳ prompt nào — kể cả một prompt "chỉ trích metadata". Lý do đây không phải một quy tắc guardrail thường mà là một quyết định **kiến trúc dữ liệu**: hệ thống trích metadata (tên file, số trang, kiểu MIME) bằng công cụ đọc cấu trúc file (không phải LLM), **không bao giờ** đưa byte nội dung vào bất kỳ lời gọi model nào. Nếu một phase sau (khi `SEAL_REQUEST` được kích hoạt) thiết kế một tool "tóm tắt văn bản ngoài giúp người duyệt", tool đó phải là một tính năng riêng có tên, có guardrail riêng, không phải một nhánh mở rộng của `draft_free_content` — mở rộng phạm vi input của prompt soạn thảo sang một file người dùng tải lên là đúng thứ ADR-008 được dựng lên để chặn.

### 8.2 Đường trích nguyên văn từ kho quy trình — nội dung do người nạp cam kết, hệ thống không kiểm được

`procedure_retrieval` trả **văn bản nguyên văn** của `procedure_chunk` cho nhân viên xem (nhánh ngoài phạm vi của `intake_agent`, mục Retrieval của `03-agents.md`), và mục Prompt module chi tiết của `07-prompts.md` đã cố ý loại đưa đoạn quy trình vào prompt soạn thảo (RISK-05: "nội dung văn bản chứa câu chữ không đến từ slot nào" là trigger phát hiện, đưa retrieval vào đó làm trigger mất tác dụng). Cái chưa từng được nói ra: **hệ thống không xác minh được nội dung của `procedure_chunk` không mang chỉ dẫn injection**, vì nó tin vào cam kết của người có `procedure.manage` (A-033) — cùng khuôn tin cậy với A-018 ("không ai nghiệm thu thể thức", chấp nhận rủi ro còn lại bằng chế độ vận hành, không bằng kiểm tự động). Hệ quả thực thi: nội dung trích cho nhân viên xem đi qua đúng một đường — hiển thị nguyên văn có trích nguồn (tên tài liệu, phiên bản, đường dẫn mục) — **không bao giờ** được diễn giải lại bởi một lời gọi model trước khi hiển thị (đã đúng, vì P3 `select_procedure_passages` chỉ chọn id, không tóm tắt — mục P3 `select_procedure_passages` của `07-prompts.md`). Không thêm guardrail kỹ thuật mới ở đây vì không có: đường phòng thủ là **quy trình nạp có người chịu trách nhiệm** (A-033), không phải kiểm tra tự động nội dung.

---

## 9. Output validation trước khi render

`validate_free_content` (mục P4/P5 `draft_free_content` / `revise_free_content` của `07-prompts.md`) đã kiểm chất lượng nội dung — không rỗng, không placeholder, không câu khung. Bổ sung kiểm **an ninh**, cùng node, trước `render_draft`:

| Kiểm | Vì sao |
|---|---|
| Không chứa thẻ HTML/XML hay cú pháp trường hợp lệ của template (`{{`, `}}` hay ký hiệu placeholder mà template dùng) | `.docx` chứa XML bên trong; nội dung tự do chèn được cú pháp trường có thể đổi cách LibreOffice hoặc trình đọc `.docx` diễn giải file, hoặc vô tình tạo một biến trùng tên |
| Độ dài đã có `max_length` theo `template_variable.max_length` (đã có ở mục P4/P5 `draft_free_content` / `revise_free_content` của `07-prompts.md`) | Chặn tràn bố cục — không phải kiểm an ninh mới, nhắc lại để thấy nó đứng cùng nhóm |
| Không chứa toàn bộ giá trị nguyên văn của một slot `RES` khác biến đang sinh (ví dụ `body` của `purpose_statement` không được chứa chuỗi `bearer_national_id`) | `drafting_agent` không được cấp `bearer_national_id` trong input đã khai (mục Guardrail chung của `07-prompts.md`) nên về lý thuyết không tự chèn được — kiểm này là lớp phòng thủ thứ hai, bắt trường hợp allowlist bị khai sai ở một phiên bản prompt sau |

Trượt bất kỳ dòng nào ở trên đi theo đúng con đường đã có: `halt_for_human` sau lần sinh lại thứ hai (mục P4 `draft_free_content` của `07-prompts.md`), không phải một nhánh lỗi mới.

---

## 10. Chống lộ template mật

- **Không có endpoint tải bản gốc `template` cho ai ngoài người có `template.manage`.** Nhân viên và người duyệt chỉ thấy `document_render` — bản đã điền biến — không bao giờ thấy file `.docx`/`.pdf` gốc rỗng biến.
- **`object_storage` không có URL công khai trực tiếp.** Mọi lần tải đi qua `stored_file_fetch` (ADR-014) — kiểm permission trên **đối tượng nghiệp vụ** trỏ tới object (`document`, `template_version`), không cấp quyền thẳng trên chính object storage. Không có tính năng "link chia sẻ" ở Sprint đầu.
- **Bản render `DRAFT` cũng qua đúng đường đó** — không có ngoại lệ "bản nháp thì lỏng hơn". Quyền xem một `document_render` đi theo quyền xem `document` mà nó thuộc về (`request.read_own`/`read_all`/`read_assigned`), không có permission riêng cho riêng file render.

---

## 11. Secret management trên Render

| Secret | Ai giữ | Xoay vòng |
|---|---|---|
| Session secret (ADR-013) | Biến môi trường của `api` | Không tự động — người vận hành quyết, xem mục 2 |
| Credential `bo19_admin` — user mặc định của Postgres trên Render, chủ database và schema `public` *(thêm 2026-10-04)* | **Chỉ PO** — file **ngoài repo** `~/.bo19/admin.env`, biến `BO19_RENDER_ADMIN_DSN`, trên máy của PO (PO, 2026-10-04). **Không** nằm trong `.env` của repo; người triển khai không đọc, không ghi file đó — chỉ `tools/db-bootstrap/step0.sh` đọc, lúc PO chạy. PO là người triển khai duy nhất (A-071). **Không** ở CI, **không** ở biến môi trường của service runtime nào. Chỉ dùng cho bước 0 của mục Migration và checkpointer của `06-structure.md`, và cho thao tác tạo role | Khi dựng lại DB free theo runbook ở `11-ops.md` — mỗi DB mới có credential mới; xoay giữa chu kỳ: PO quyết |
| Credential `bo19_migrator` | Ngữ cảnh chạy bước `migrate` — **đã chọn:** CI pipeline (ADR-022; A-060 `Đã chốt`). Biến `BO19_MIGRATOR_DATABASE_URL`, chỉ `migrate_main` đọc; không bao giờ là biến của Web Service (mục Biến môi trường theo môi trường của `11-ops.md`, 2026-10-04) | Cùng owner với A-060. Dựng lại DB thì đổi cùng lượt — `tools/db-bootstrap/` |
| Credential `bo19_app` | Biến môi trường `BO19_DATABASE_URL` của `api`/`queue_worker`/cron — host nội bộ Render, user `bo19_app`, `sslmode=require`; **không** phải URL nội bộ Render hiển thị, vì URL đó mang credential `bo19_admin` (mục Biến môi trường theo môi trường của `11-ops.md`, 2026-10-04) | Theo chính sách chung của DB managed, `[CẦN XÁC MINH]`; đổi bằng SCRAM verifier như S1 |
| Provider API key (LLM, embedding — A-026) | Biến môi trường của `ai_gateway` | `[CẦN XÁC MINH]` theo nhà cung cấp được chọn |
| S3-compatible credential (A-024) | Biến môi trường của `tool_layer` | `[CẦN XÁC MINH]` theo nhà cung cấp được chọn |

**Nguyên tắc chung — không hardcode, không log.** Không secret nào xuất hiện trong `schema.sql`, trong response API, hay trong log kỹ thuật (cùng luật mask ở mục 7 — một secret log ra dù chỉ một lần là secret đã lộ, không "mask được sau"). Giá trị cụ thể của mọi secret không được ghi ở đây hay ở bất kỳ file nào trong `docs/design/` — chỉ tên biến môi trường.

**A-060 — chưa đóng, ghi nhận vị trí Phase 9 trong đó.** Ngữ cảnh chạy `migrate` quyết định `bo19_migrator` sống ở đâu. Phase 9 không tự chọn (cần đọc tài liệu Render về phạm vi biến môi trường theo dịch vụ, `[CẦN XÁC MINH]`), nhưng thêm một ràng buộc: bất kể ngữ cảnh nào được chọn, `bo19_migrator` **không được** nằm trong biến môi trường của `api` hay `queue_worker` — đúng điều A-060 đã cảnh báo sẽ làm mọi bất biến bằng `GRANT`/`REVOKE` (mục Nguyên tắc dữ liệu của `04-data.md`) chỉ còn là chữ.

---

## 12. `operating_mode_change`

### 12.1 Quyết định — endpoint có permission (ADR-020)

`05-api.md` từng liệt `operating_mode_change` vào ba loại trừ có chủ đích của Phase 5, chỉ mở `GET /me` đọc chế độ hiện hành (mục Nhãn phạm vi và loại trừ có chủ đích của `05-api.md`). Phase 9 đóng nó bằng **endpoint**, không bằng thao tác vận hành, vì hai lý do đứng trên dữ kiện đã có, không trên sở thích:

1. `contracts/schema.sql` đã cấp `bo19_app` quyền `INSERT` trên `operating_mode_change` (nhóm "Chỉ thêm", mục Hai role và bất biến bằng quyền của `04-data.md`) từ Phase 4 — ngược hẳn với `employee_credential`, nơi `bo19_app` cố tình chỉ đọc. Chọn thao tác vận hành nghĩa là phải thu hồi quyền đã cấp bằng một migration khác, hoặc để lại một quyền ghi không code nào dùng — cả hai đều vi phạm nguyên tắc "`bo19_app` chỉ có đúng các quyền cấp".
2. Thao tác chạy bằng `bo19_migrator` không đi qua `tool_layer`, nên **không sinh `audit_event`**. Hành động hệ trọng nhất hệ thống — bật/tắt mọi ràng buộc của chế độ phi sản xuất (D-009) — sẽ nằm ngoài nhật ký mà `audit.read_all` đọc. Một endpoint có permission và `audit_event` đáp ứng "hành động được ghi nhận và quy trách nhiệm được" (D-009) tốt hơn một dòng SQL thủ công, không kém hơn.

Chi tiết Context/Options/Decision/Consequences/Rejected alternatives ở **ADR-020**.

### 12.2 Endpoint

| Method | Path | Mô tả | Permission | Chạy | Khoá = id của | Body → Response |
|---|---|---|---|---|---|---|
| POST | `/operating-mode/transitions` | Đổi `operating_mode`. `from_mode` server tự gán bằng chế độ hiệu lực hiện tại — client không truyền | `operating_mode.change` | `SYNC` | `operating_mode_change` | `OperatingModeTransitionBody` → `OperatingModeChange` |
| GET | `/operating-mode/transitions` | Lịch sử đổi chế độ, mới nhất trước | `audit.read_all` | — | — | → `OperatingModeChangePage` |

Thao tác đặt tên **`operating_mode_transition`** — khác tên entity `operating_mode_change` có chủ đích, cùng lý do `open_request`/`request_open` đã nêu ở `GLOSSARY.md`: một tên là bước ghi của `tool_layer`, một tên là entity/bảng nó ghi vào. Thêm vào nhóm Thao tác do endpoint gọi ở mục Agent, graph, node, tool của `GLOSSARY.md` (mục 12), tag "thêm ở Phase 9" — cùng khuôn với các đợt bổ sung "thêm ở Phase 4/5" đã có ở đúng danh sách đó.

`OperatingModeTransitionBody`: `to_mode` (`NON_PRODUCTION` | `PRODUCTION`), `decision_reference` (string, không rỗng — CHECK đã có ở DB, `api` **không** thêm phép kiểm hình thức nào khác cho nó: một tham chiếu văn bản có người ký là thứ hệ thống không thẩm định được, cùng nguyên tắc đã dùng ở A-033 và A-018), `effective_at` (tuỳ chọn, mặc định `now()`).

**Idempotency-Key = id của dòng `operating_mode_change` được tạo** — theo đúng quy tắc chuẩn ở mục Idempotency của `05-api.md`, **không** thêm một ngoại lệ mới vào danh sách ba ngoại lệ đã đóng (`POST /employee-imports`, `POST /templates`, `POST /delegations`).

**`audit_event` mức `WARNING`** — đúng định nghĩa ở `GLOSSARY.md`: hành động đúng luật nhưng cần người khác nhìn thấy, cùng họ với đường thoát tự duyệt của D-006.

**Một permission, cả hai chiều — chỉ ở `POST`.** `operating_mode.change` gác cả `NON_PRODUCTION → PRODUCTION` lẫn chiều ngược lại — không gác chiều quay về chặt hơn: chặn đường lùi (về chế độ an toàn hơn) nguy hiểm hơn chặn đường tiến, vì nó có thể khoá hệ thống ở `PRODUCTION` đúng lúc cần lùi khẩn cấp (ví dụ phát hiện template sai thể thức sau khi đã tháo chế độ phi sản xuất).

**`GET` dùng `audit.read_all`, không dùng `operating_mode.change`.** Quyền ghi không tự kéo theo quyền đọc — cùng nguyên tắc `document.issue` không kéo theo `audit.read_all`, `procedure.manage` không kéo theo `procedure.read_all` (mục 3.1). Lịch sử đổi chế độ là nhật ký, đã có chủ trong danh mục permission; đặt nó đúng nhà thay vì mở một mẫu hình "permission theo quan hệ HOẶC" mới cho riêng một endpoint. Người có `operating_mode.change` vẫn thấy dòng vừa tạo ở response của `POST`, và thấy chế độ hiện hành qua `GET /me` — không mất khả năng nào.

**Lỗi mới:** `OPERATING_MODE_UNCHANGED` (422) — `to_mode` trùng chế độ hiệu lực hiện tại. Kiểm ở `api` trước khi chạm DB; `ck_operating_mode_change_differs` là lớp chặn thứ hai.

### 12.3 Phạm vi contract đổi

Endpoint có contract: 48 → **50** — bản trước ghi 49, thêm hai operation nên phải là 50 (AUD-22, sửa ở đợt 4) (con số 48 được xác nhận ở lần đối chiếu tự động Phase 5/6, mục ngày 2026-09-13 của `CHANGELOG.md`). Sửa `05-api.md` (thêm mục 2.2b, cập nhật mục Nhãn phạm vi và loại trừ có chủ đích để trỏ sang endpoint thật thay vì liệt kê như loại trừ) và `contracts/openapi.yaml` (thêm path, hai schema). Bộ kiểm đối chiếu tự động ở `tools/contract-checks/` (nhắc ở A-047) cần chạy lại sau thay đổi này — **không chạy ở đây**, vì đó là code, ngoài phạm vi DESIGN MODE (mục Chế độ làm việc hiện tại của `CLAUDE.md`); người triển khai chạy lại trước khi build.

---

## 13. Quyền của chủ thể dữ liệu — ở mức nghĩa vụ *(đợt sửa 3b sau Phase 13, AUD-24)*

`03-agents.md` mục Memory và `04-data.md` mục Lưu trữ và xoá dữ liệu cá nhân giao việc này cho Phase 9; bản 0.2 của file này không có mục nào làm. Mục đích thu thập và thời hạn lưu đã có chỗ (NFR-05, A-010). Mục này xử lý vế thứ ba mà mục Ràng buộc domain bắt buộc phải xử lý của `CLAUDE.md` đòi: **quyền của chủ thể**.

**Giới hạn — nói trước.** Căn cứ là Luật Bảo vệ dữ liệu cá nhân năm 2025 và Nghị định 356/2025/NĐ-CP — theo PO, có hiệu lực từ 01/01/2026 và thay Nghị định số 13/2023/NĐ-CP (A-080, AUD-26). Chưa văn bản nào có bản gốc trong `docs/reference/`. Danh mục các quyền, điều khoản, thời hạn phải đáp ứng yêu cầu và ngoại lệ: `[CẦN XÁC MINH]`. PO nêu Điều 5 của Nghị định 356/2025/NĐ-CP quy định thời hạn thực hiện quyền của chủ thể — số điều và thời hạn `[CẦN XÁC MINH]` bằng bản gốc. Mục này **không** phán quyết pháp lý. Nó trả lời một câu hỏi kỹ thuật: với dữ liệu hệ thống đang giữ, hệ thống **làm được** gì khi có một yêu cầu xem, sửa, hay xoá dữ liệu về một người — và chỗ nào chưa làm được. Ba nhóm việc này do chính dữ liệu của hệ thống đặt ra, không phải bản liệt kê quyền theo Nghị định.

### 13.1 Chủ thể là ai

- **Nhân viên có hồ sơ** trong `employee` — người tạo yêu cầu, người thụ hưởng, người duyệt. Cả dữ liệu hồ sơ lẫn dấu vết thao tác (`actor_employee_id` ở `decision_record`, `audit_event`) đều gắn với họ.
- **Người được nhắc tới trong giá trị slot** mà không phải người dùng hệ thống — ví dụ người đi cùng trong slot `accompanying_persons`. Họ không đăng nhập được, nên không tự gửi yêu cầu qua hệ thống được.

### 13.2 Làm được gì hôm nay, bằng gì

| Việc | Dữ liệu | Làm được bằng | Chỗ hở |
|---|---|---|---|
| **Xem** | `request` và slot do mình tạo; tin nhắn trong phiên của mình | `GET /requests?scope=OWN`, `GET /requests/{request_id}`, `GET /chat-sessions/{chat_session_id}/messages` — `request.read_own`; tin nhắn: chủ phiên | Không có đường tổng hợp **mọi** dữ liệu về một người: hồ sơ `employee` đầy đủ — `GET /me` chỉ trả một phần; slot về mình trên `request` người khác tạo (nhập hộ, người thụ hưởng, người đi cùng); dấu vết thao tác trong `audit_event` |
| **Sửa** | Hồ sơ `employee` | `employee_import` — người có `employee.import` (D-002) | — |
| | Giá trị slot trước `SUBMITTED` | Hội thoại, `request_slot_confirm` | — |
| | Giá trị slot sau `SUBMITTED` | Yêu cầu sửa `SLOT_DATA` của người duyệt | — |
| | Văn bản đã `ISSUED` | Thu hồi rồi phát hành văn bản mới — không sửa tại chỗ (bất biến thứ ba ở mục Vòng đời `document` của `00-domain.md`) | Thu hồi là F5 `[Should]`, sau UAT |
| **Xoá, ẩn danh** | Slot `RES`, văn bản tin nhắn, `retrieval_query` | Xoá theo sự kiện và theo thời hạn — `expire_request`, `slot_sensitivity_change` (mục Lưu trữ và xoá dữ liệu cá nhân của `04-data.md`) | Không có lệnh xoá **theo yêu cầu của một người**; chỉ có xoá theo luật chung. Thời hạn: A-010 |
| | Văn bản lý do (`decision_record_text`) | Xoá dòng được (`bo19_app` có `DELETE`); `decision_record` giữ nguyên | Không có thao tác có tên |
| | Hồ sơ `employee` | Nghỉ việc: `is_active = false`, không xoá dòng | **Ẩn danh chưa có thao tác.** Dòng không xoá được vì khoá ngoại từ `request`, `decision_record` và các bảng khác; `audit_event.actor_employee_id` không có khoá ngoại nhưng vẫn là một định danh cá nhân (cùng nhận xét ở A-070). Ẩn danh là ghi đè các cột `PER`/`RES` và giữ `id` — `bo19_app` có quyền `UPDATE` trên `employee` |
| | Checkpoint | Purge khi thread kết thúc (ADR-008) | — |
| | Bản render đã ghim, dòng sổ văn bản | **Ứng dụng không bao giờ xoá** (mục Chuỗi bảo đảm bất biến của bản đã ghim của `04-data.md`) | **Xung đột**: văn bản đã phát hành mang tên và dữ liệu của chủ thể; nghĩa vụ lưu trữ văn bản chính thức và quyền xoá kéo ngược nhau. Không phải thiết kế quyết — người phụ trách pháp chế quyết (A-079) |
| | Dữ liệu đã gửi tới provider LLM hay embedding | Allowlist chỉ gửi đúng input đã khai (INV-03); không gửi giá trị `HR_PROFILE` (mục `drafting_agent` của `03-agents.md`) | Thời gian provider giữ dữ liệu: phụ thuộc provider chưa chọn (A-026, A-028), `[CẦN XÁC MINH]` |

### 13.3 Quyết định ở đợt này

- **Không thêm endpoint, thao tác hay DDL.** Kênh tiếp nhận yêu cầu ở Sprint đầu nằm **ngoài hệ thống**: nhân viên gửi phòng hành chính. Phần làm được thì làm bằng đường ở bảng trên.
- **Ba chỗ hở thành A-079**, owner Product Owner, hạn theo quyết định PO về AUD-24: **trước cổng Sprint 4, hoặc trước khi nạp dữ liệu cá nhân thật đầu tiên — tuỳ cái nào sớm hơn.** (1) Tổng hợp mọi dữ liệu về một chủ thể. (2) Thao tác ẩn danh hồ sơ và giá trị slot về một chủ thể. (3) Xung đột giữa quyền xoá và nghĩa vụ lưu trữ văn bản đã phát hành.
- **Vì sao không thiết kế luôn (1), (2).** Cả hai tuỳ vào (3) và vào thời hạn ở A-010: ẩn danh giá trị slot trên một `request` đã `FULFILLED` là sửa bằng chứng đi kèm một văn bản đã phát hành. Thiết kế thao tác trước khi biết phạm vi được phép xoá là đoán luật.
- **Thời hạn thực hiện yêu cầu của chủ thể** có quy định riêng (A-080) mà thiết kế chưa có. Kênh tiếp nhận nằm ngoài hệ thống, nên giữ hạn là việc của quy trình tiếp nhận — vế thứ tư của A-079.
- **Không có dữ liệu cá nhân thật nào được nạp** khi A-079 còn `Mở` — cùng điều kiện với hạn ở trên. UAT dùng dữ liệu giả (quyết định PO về AUD-24).

---

## Migration bổ sung của Phase 9

**`contracts/schema.sql` KHÔNG bị sửa.** Mục 3 của `06-structure.md` đã chốt từ Phase 6: *"`0001_initial.sql` = `contracts/schema.sql` ở trạng thái đóng Phase 6; về sau mỗi thay đổi một file"*. Đây không phải một cách diễn giải — là câu đã viết sẵn cho đúng tình huống này. Toàn bộ thay đổi của Phase 9 nằm ở hai file migration mới, đúng trình tự của ADR-017 (bước 1: schema migration; bước 4: data migration).

### Schema migration — `backend/migrations/schema/0002_phase9_security.sql`

Hai bảng mới, cả hai tầng kỹ thuật (mục Agent, graph, node, tool của `GLOSSARY.md`): `employee_credential` (A-048) và `rate_limit_window` (mục Rate limit). Nội dung đầy đủ trong chính file đó; tóm tắt:

```sql
CREATE TABLE employee_credential (
    employee_id     uuid        PRIMARY KEY REFERENCES employee (id),
    password_hash   text        NOT NULL,
    hash_algorithm  text        NOT NULL DEFAULT 'argon2id',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_employee_credential_hash_not_blank CHECK (btrim(password_hash) <> '')
);

CREATE TABLE rate_limit_window (
    scope          text        NOT NULL,
    window_start   timestamptz NOT NULL,
    attempt_count  integer     NOT NULL DEFAULT 1,
    CONSTRAINT pk_rate_limit_window PRIMARY KEY (scope, window_start),
    CONSTRAINT ck_rate_limit_window_count_positive CHECK (attempt_count > 0)
);

CREATE INDEX ix_rate_limit_window_start ON rate_limit_window (window_start);

GRANT SELECT ON employee_credential TO bo19_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limit_window TO bo19_app;
```

**Thu hẹp sau Phase 12 — `backend/migrations/schema/0005_rate_limit_window_column_grant.sql`:** quyền `UPDATE` của `bo19_app` trên `rate_limit_window` còn đúng cột `attempt_count`, khớp nhóm "Đếm và dọn theo cửa sổ" ở mục Nguyên tắc dữ liệu của `04-data.md`. Khối SQL trên chép đúng `0002`, và `0002` không đổi. Lý do và số đo ở `proposals/migration-0005-rate-limit-window-column-grant.md`.

### Data migration — `backend/migrations/data/0001_permission_catalog.sql`

`INSERT` cho `permission` (25 dòng), `role` (3 dòng), `role_permission` (gói theo mục Gói permission theo vai trò của `00-domain.md`). Chi tiết ở mục 3.2. **Không** ghi `employee_role` hay `employee_permission_grant` — cả hai cần `employee_id` thật, chưa tồn tại ở thời điểm thiết kế.

### Hệ quả lên `04-data.md`

`contracts/schema.sql` vẫn **45 bảng**, không đổi — con số đó mô tả đúng một file, và file đó không đổi. Mục Ánh xạ entity → bảng của `04-data.md` mô tả **toàn bộ hệ schema sau migration** (45 bảng của `schema.sql` + 2 bảng của `0002_phase9_security.sql` = 47), nên hai dòng mới cho `employee_credential`/`rate_limit_window` vẫn đúng chỗ — chỉ sửa lại câu diễn giải con số cho không còn ngụ ý cả 47 bảng nằm trong một file. Tương tự mục Hai role và bất biến bằng quyền: hai nhóm quyền mới áp dụng cho hai bảng của migration 0002, không phải của `schema.sql`.

---

## Open Questions

Không có câu hỏi mở chỉ tồn tại trong file này. Giả định liên quan: `A-079` (quyền của chủ thể dữ liệu — ba chỗ hở, thêm ở đợt sửa 3b), `A-002` (số liệu tải cho ngưỡng rate limit), `A-031` (ngưỡng rate limit, thêm ở Phase 9), `A-036` (phạm vi Nghị định 30/2020/NĐ-CP, chạm chế độ phi sản xuất mà `operating_mode.change` điều khiển), `A-042` (đã chốt — danh mục + data migration), `A-048` (credential — tham số hash, thời hạn token, chu kỳ xoay vòng secret, rủi ro thứ tư), `A-055` (audit_event — trường hợp thứ tư), `A-057` (trần connection pool, liên quan tới rủi ro pool ở mục 6.2), `A-060` (ngữ cảnh chạy `migrate`), `A-061` (điều kiện kích hoạt lọc `request.read_all` theo phòng ban — Mở, không phải đề xuất chờ duyệt) — xem `ASSUMPTIONS.md`. **Thêm một `[CẦN XÁC MINH]` mới, xem mục K1 của báo cáo đóng phase:** header IP thật của client phía sau proxy Render, dùng để khoá `rate_limit_window` theo IP — cùng họ A-051.

---

## Quyết định kiến trúc

**ADR mới:** ADR-020 (`operating_mode_change` qua endpoint, không qua thao tác vận hành); ADR-021 (`argon2id` cho hash mật khẩu — có điều kiện đảo ngược thật: RAM của instance Render, nên không cùng mức với "chọn một thư viện" thông thường).

**Không viết ADR cho:** bảng `rate_limit_window` (áp dụng lại đúng nguyên tắc "bất biến bằng `GRANT`/`REVOKE`" đã có từ J4 của `04-data.md`, không phải một mẫu hình mới, và không có điều kiện đảo ngược riêng ngoài các tham số TBD đã ghi ở A-031).
