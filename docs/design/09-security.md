# Security & Guardrails — Admin Service Desk Agent (BO-19)

**Phiên bản:** 0.2 · **Trạng thái:** Draft chờ duyệt

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
| Giá trị slot `PER`/`RES` | Dữ liệu cá nhân, nghĩa vụ theo Nghị định 13/2023/NĐ-CP (`[CẦN XÁC MINH]`, A-036) |
| `employee_credential` | Mất là mất toàn bộ AuthN |
| Bản gốc `template` | Sai thể thức = văn bản vô hiệu (RISK-01); rò khung thể thức ra ngoài là rò mẫu con dấu, mẫu chữ ký |
| `document_register` / `document_number` | Nguồn sự thật pháp lý (ADR-011) |
| Session secret, `bo19_migrator` credential, provider API key | Chiếm được là chiếm quyền của toàn hệ thống hoặc của DB |

**Bề mặt tấn công chính** — ai đứng ở đâu: nhân viên đã đăng nhập (chat, upload `external_file` ở `SEAL_REQUEST` `[Could]`), người ngoài chưa đăng nhập (`POST /auth/session`, stream tín hiệu công khai không có), nội dung do bên thứ ba tạo mà hệ thống hiển thị lại (`procedure_document`, `external_document`).

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
- **Hash mật khẩu — `argon2id` (ADR-021).** Lý do bằng tính chất hàm, không trích số liệu benchmark từ trí nhớ (luật trích dẫn của `CLAUDE.md`): `argon2id` là một trong hai họ hash có tham số bộ nhớ **độc lập** với số vòng lặp (họ còn lại là `scrypt`), nên một cuộc dò mật khẩu ngoại tuyến song song hoá bằng phần cứng chuyên dụng — chiều tấn công có lợi thế nhất — tốn tài nguyên hơn hẳn so với `bcrypt`/`PBKDF2`, hai hàm không có tham số bộ nhớ độc lập. Chi tiết Options/Rejected alternatives ở ADR-021. Phiên bản thư viện và bộ tham số khuyến nghị `[CẦN XÁC MINH]` — chưa có bản gốc trong `docs/reference/`. **Tham số cụ thể — TBD, xem A-048:** bộ nhớ, số vòng lặp, độ song song. Cột `hash_algorithm` lưu định danh thuật toán cùng dòng hash, để đổi thuật toán sau này không phải migrate hồi tố toàn bộ bảng trong một bước.
- **Ràng buộc RAM của instance Render — nói thẳng, không đo được ở phase này.** `argon2id` cấu hình bộ nhớ càng cao thì chống dò càng tốt, nhưng mỗi lần đăng nhập hợp lệ cũng tốn đúng bằng đó RAM trên instance chạy `api`. Trên instance nhỏ, cấu hình bộ nhớ cao cho nhiều lượt đăng nhập đồng thời có thể cạnh tranh RAM với phần còn lại của tiến trình. Đây là đánh đổi thật, không phải chi tiết cấu hình — tham số cuối cùng phải chọn có đối chiếu với hạng instance đã thuê (A-002, A-031), không chọn theo khuyến nghị chung chung rồi mặc định là an toàn.
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

Mọi tool của `intake_agent` (mục Ai được gọi tool nào của `03-agents.md`) nhận `request_id`/`chat_session_id` đã bị buộc vào đúng phiên đang xử lý — thread key `intake:{chat_session_id}` (mục 12 của `GLOSSARY.md`), và phiên thuộc về đúng một nhân viên (`chat_session.employee_id`). Permission cần cho tool ghi ghi "Tác nhân hệ thống" ở mục Tool Registry của `03-agents.md` không có nghĩa là **không kiểm ai** — nó có nghĩa là quyền được kiểm **một lần, ở lối vào**: `POST /chat-sessions/{id}/turns` xác nhận người gọi là chủ phiên (`request.create` hoặc `request.create_on_behalf`, mục 2.3 của `05-api.md`) trước khi lượt được nhận; mọi tool bên trong lượt đó kế thừa đúng phạm vi của phiên, không tự hỏi lại permission theo tên. Đây là lớp chống truy cập chéo instance (đọc/ghi `request` của người khác qua một `request_id` đoán được): tool không nhận `request_id` tuỳ ý từ input LLM, nó chỉ thao tác trên `request` đang mở của **chính đồ thị đang chạy**, và đồ thị đó bị khoá vào một `chat_session` từ lúc `load_turn`.

### 4.2 `document_graph` chạy trong job — không có người yêu cầu nào tại thời điểm chạy

Đây là ca thật sự cần trả lời, không phải ca đã có sẵn câu trả lời ở tầng HTTP. `render_document`, `resume_document_graph`, `finalize_issue` chạy trong `queue_worker` (ADR-004, ADR-010), được `job` đánh thức — không có ai đang "gọi API" tại thời điểm đó.

- **Căn cứ cấp quyền:** không phải permission của một người đang online, mà là **việc job đã được enqueue hợp lệ trong một giao dịch đã qua kiểm permission** (mục Thao tác của `tool_layer` theo nhóm được gọi của `GLOSSARY.md` — thao tác cổng kiểm permission, chuyển trạng thái và enqueue job **trong cùng một giao dịch**, mục 3.1 của `08-hitl.md`). Permission được kiểm **một lần, ở lúc enqueue**, không kiểm lại lúc job chạy — vì lúc đó không còn "người gọi" nào để hỏi.
- **Ai chịu trách nhiệm:** `audit_event` của job mang `actor_kind = SYSTEM`, không có `actor_employee_id` — đúng bản chất, không phải khoảng trống. Trách nhiệm không nằm ở audit_event của job, mà ở **audit_event của thao tác cổng đã enqueue nó**: mỗi job mang được dấu vết đúng một thao tác cổng khởi phát nó (`decision_record`/`audit_event` của thao tác đó), nên truy vết ngược từ một hành vi hệ thống về đúng người ra lệnh không đi qua bảng `job`, mà qua liên kết `job` → thao tác cổng đã enqueue nó.
- **Vì sao đây không phải đường đi vòng qua permission của người khởi phát.** Job không tự chọn làm gì — nó chỉ tiếp tục đúng một `document_graph` đã dừng ở đúng một `interrupt`, với dữ liệu đã được ghi (và kiểm permission) từ trước lúc enqueue. Một job không có cách nào đổi phạm vi hành động của nó sang một `document_id` khác hay một permission khác với thao tác cổng đã tạo ra nó — đó là bất biến của việc `job` mang đúng một `subject_document_id` (mục Bảng chi tiết của `04-data.md`), không phải một tham số job có thể bị đổi giữa chừng.

### 4.3 Vì sao vẫn cần hai lớp dù đã trả lời "chạy dưới danh nghĩa ai"

`api` khai permission tĩnh theo **loại** hành động (đúng một permission cho mỗi endpoint), còn `tool_layer` kiểm lại theo **trạng thái thật của đối tượng tại thời điểm ghi** — `NOT_DRAFT`, `ILLEGAL_TRANSITION`, `NOT_READY` (mục Tool Registry của `03-agents.md`). Hai lớp không trùng nhau: `api` có thể đúng (người gọi có `document.approve_content`) nhưng hành động vẫn sai (document đã bị người khác duyệt giữa lúc `api` kiểm permission và lúc `tool_layer` thực thi — chính ca "hai người thao tác cùng lúc" ở mục 1.9 của `05-api.md`). Bỏ lớp thứ hai thì một điều kiện đua (race) giữa kiểm quyền và ghi dữ liệu biến thành một lần ghi sai trạng thái không ai bắt được.

---

## 5. Row-level theo phòng ban

Hai trục khác nhau, không gộp một tiêu đề.

### 5.1 Kho quy trình — đã giải ở mục 3.3

Vế permission của A-043 xong; vế phòng ban (`department_scope`) đã có từ Phase 4.

### 5.2 `request.read_all` — trục thứ hai, org-wide đã áp

**Quyết định: giữ org-wide ở Sprint đầu — đã sửa trực tiếp** vào mục Gói permission theo vai trò của `00-domain.md`, không còn là câu cũ kèm chú thích. Lý do: A-001 giả định một pháp nhân đơn nhất; đề bài mô tả **một** Phòng Hành chính xử lý tập trung mọi yêu cầu của tổ chức (mục Bối cảnh đề tài của `CLAUDE.md`), nên `ADMIN_OFFICER` — vai trò duy nhất mang `request.read_all` ở Sprint đầu — về đúng nghĩa vụ cần thấy toàn bộ để xử lý.

**A-061 viết lại theo đúng nghĩa của nó: không phải "có sửa câu hay không" (đã sửa) mà là điều kiện kích hoạt lọc.** Org-wide đứng được chừng nào A-001 còn đúng. Điều kiện kích hoạt lọc theo phòng ban: A-001 bị bác bỏ — tổ chức thật ra có **từ hai Phòng Hành chính xử lý độc lập trở lên**. Khi đó "xem mọi yêu cầu" không còn là một nghĩa vụ duy nhất mà là nhiều nghĩa vụ tách biệt theo đơn vị.

**Chỗ bám kỹ thuật nếu sau này kích hoạt** (neo sẵn, không cài đặt): lọc qua `employee.department_code` của người thụ hưởng, tức join `request.beneficiary_employee_id → employee.department_code`, **không phải** phòng ban của người tạo (D-006: người thụ hưởng mới là chủ của yêu cầu). Không có bảng `department` (mục Nguyên tắc dữ liệu của `04-data.md`) — mã phòng ban là chuỗi do CSV quyết định, nên cùng hệ quả đã ghi ở mục Lọc quyền và so khớp phòng ban của `04-data.md`: CSV đổi mã một phòng ban mà chưa kịp cập nhật nơi dùng nó thì lọc theo phòng ban mất chức năng theo hướng **ẩn nhầm** một số yêu cầu khỏi người vốn cần thấy (fail-closed, cùng họ với ADR-008) — không theo hướng rò thêm.

---

## 6. Rate limit

**Cơ chế: bảng PostgreSQL, cửa sổ cố định** (B3, đồng ý bảng thay vì in-memory — đúng vì Render có thể chạy nhiều instance `api`, và in-memory mỗi instance đếm riêng thì trần thực tế nhân lên theo số instance).

### 6.1 DDL — xem mục DDL bổ sung của Phase 9

`rate_limit_window (scope, window_start, attempt_count)`, khoá chính `(scope, window_start)`. `scope` là chuỗi ghép — ví dụ `login_ip:{ip}` — **không bao giờ khoá thuần theo `employee_code`**. **IP đọc từ đâu, phía sau proxy của Render, là `[CẦN XÁC MINH]` — A-062, chưa ghi từ trí nhớ.** Header giả được hoặc đọc sai vị trí thì lớp này chỉ còn là gờ giảm tốc, không phải chặn thật — nói thẳng ở A-062, không để ẩn trong quyết định nghe chắc chắn dưới đây: `employee_code` không bí mật (dùng để đăng nhập, không phải bí danh), nên rate limit thuần theo nó là một đường DoS có chủ đích nhắm vào một nhân viên cụ thể — đúng lý do `05-api.md` đã không có mã `ACCOUNT_LOCKED` (mục 1.3 của `05-api.md`, A-048). Khoá theo IP là chính; ghép thêm `employee_code` vào `scope` cho một ngưỡng chặt hơn ở cùng cặp (IP, mã) là được, miễn ngưỡng theo **IP đơn** vẫn tồn tại độc lập và không thể bị vô hiệu hoá bằng cách đổi mã liên tục từ cùng một IP.

### 6.2 Rủi ro của việc ghi trước khi xác thực

`POST /auth/session` ghi (tăng bộ đếm) **trước khi** biết người gọi là ai — đây là lệnh ghi do request chưa xác thực gây ra, tức chính bề mặt mà kẻ tấn công kiểm soát được tần suất. Hai thứ có thể bị mở:

- **Bơm dòng.** Bị chặn bằng chính khoá chính `(scope, window_start)`: một `scope` trong một cửa sổ chỉ có đúng một dòng, `UPSERT` (`INSERT … ON CONFLICT (scope, window_start) DO UPDATE SET attempt_count = attempt_count + 1`) tăng tại chỗ chứ không thêm dòng mới. Số dòng bị chặn trên bởi (số `scope` khác nhau) × (số cửa sổ còn chưa dọn), không bởi số lần thử.
- **Chiếm connection của pool.** Cùng họ rủi ro với vòng poll tín hiệu ở ADR-013 (mục C4): mỗi lần đăng nhập vốn đã cần một connection để kiểm `employee_credential`, nên tăng bộ đếm trong **cùng giao dịch, cùng connection đó** không mở thêm kết nối nào — không phải một request phụ. Rủi ro thật là **tổng số lần đăng nhập** cạnh tranh pool với request nghiệp vụ khi bị dội, không phải bản thân việc có bảng đếm. Đây là lý do rate limit phải chặn **trước** khi chạm `employee_credential` khi một `scope` đã vượt ngưỡng của cửa sổ hiện tại — kiểm bộ đếm rẻ hơn kiểm hash mật khẩu, nên kiểm nó trước.

### 6.3 Dọn cửa sổ hết hạn

`queue_worker` cron xoá dòng có `window_start` cũ hơn N cửa sổ (giá trị TBD, A-031) — cùng khuôn với `expire_request`, `checkpoint_purge`.

### 6.4 Không sinh `audit_event` — xếp nhóm, không tự giải A-055

Tăng bộ đếm và dọn cửa sổ **không** sinh `audit_event`. Đây là **sổ sách kỹ thuật**, cùng họ với `llm_usage` và với việc "giành, gia hạn lease, kết thúc job" của `queue_worker` mà A-055 đã xếp là ngoại lệ ở vòng duyệt Phase 6 ("trường hợp thứ ba"): sinh `audit_event` cho mỗi lần tăng bộ đếm làm loãng nhật ký nghiệp vụ đúng như hệ quả thứ nhất mà A-055 đã nêu, và một lần thử đăng nhập sai — kể cả của kẻ tấn công — không phải "hành động có ảnh hưởng nghiệp vụ" theo định nghĩa `audit_event` ở `GLOSSARY.md`. Không tự giải A-055 ở đây; thêm **A-055 trường hợp thứ tư** trong `ASSUMPTIONS.md`, cùng cách trường hợp thứ ba đã được ghi.

### 6.5 Ngưỡng — chưa định cỡ

Số lần thử mỗi cửa sổ, độ dài cửa sổ: `TBD`. Thêm vào **A-031** (cùng họ tham số vận hành owner Phase 11, cơ chế chốt ở Phase 9).

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

Áp dụng cho **mọi** đích ghi thuộc `observability` — log, trace, span attribute — không riêng log lời gọi model. `chat_message`, `purpose`, `work_content`, `change_reason` mang `RES` nên không bao giờ xuất hiện nguyên văn trong log kỹ thuật, kể cả log lỗi (một exception không được phép serialize giá trị `RES` vào message của nó — ràng buộc này đã có ở mục Biên node của `06-structure.md` cho exception nói chung; ở đây áp riêng cho giá trị `RES`).

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

`procedure_retrieval` trả **văn bản nguyên văn** của `procedure_chunk` cho nhân viên xem (nhánh ngoài phạm vi của `intake_agent`, mục 8 của `03-agents.md`), và mục Prompt module chi tiết của `07-prompts.md` đã cố ý loại đưa đoạn quy trình vào prompt soạn thảo (RISK-05: "nội dung văn bản chứa câu chữ không đến từ slot nào" là trigger phát hiện, đưa retrieval vào đó làm trigger mất tác dụng). Cái chưa từng được nói ra: **hệ thống không xác minh được nội dung của `procedure_chunk` không mang chỉ dẫn injection**, vì nó tin vào cam kết của người có `procedure.manage` (A-033) — cùng khuôn tin cậy với A-018 ("không ai nghiệm thu thể thức", chấp nhận rủi ro còn lại bằng chế độ vận hành, không bằng kiểm tự động). Hệ quả thực thi: nội dung trích cho nhân viên xem đi qua đúng một đường — hiển thị nguyên văn có trích nguồn (tên tài liệu, phiên bản, đường dẫn mục) — **không bao giờ** được diễn giải lại bởi một lời gọi model trước khi hiển thị (đã đúng, vì P3 `select_procedure_passages` chỉ chọn id, không tóm tắt — mục 4.3 của `07-prompts.md`). Không thêm guardrail kỹ thuật mới ở đây vì không có: đường phòng thủ là **quy trình nạp có người chịu trách nhiệm** (A-033), không phải kiểm tra tự động nội dung.

---

## 9. Output validation trước khi render

`validate_free_content` (mục 3.4 của `07-prompts.md`) đã kiểm chất lượng nội dung — không rỗng, không placeholder, không câu khung. Bổ sung kiểm **an ninh**, cùng node, trước `render_draft`:

| Kiểm | Vì sao |
|---|---|
| Không chứa thẻ HTML/XML hay cú pháp trường hợp lệ của template (`{{`, `}}` hay ký hiệu placeholder mà template dùng) | `.docx` chứa XML bên trong; nội dung tự do chèn được cú pháp trường có thể đổi cách LibreOffice hoặc trình đọc `.docx` diễn giải file, hoặc vô tình tạo một biến trùng tên |
| Độ dài đã có `max_length` theo `template_variable.max_length` (đã có ở mục 3.4 của `07-prompts.md`) | Chặn tràn bố cục — không phải kiểm an ninh mới, nhắc lại để thấy nó đứng cùng nhóm |
| Không chứa toàn bộ giá trị nguyên văn của một slot `RES` khác biến đang sinh (ví dụ `body` của `purpose_statement` không được chứa chuỗi `bearer_national_id`) | `drafting_agent` không được cấp `bearer_national_id` trong input đã khai (mục Guardrail chung của `07-prompts.md`) nên về lý thuyết không tự chèn được — kiểm này là lớp phòng thủ thứ hai, bắt trường hợp allowlist bị khai sai ở một phiên bản prompt sau |

Trượt bất kỳ dòng nào ở trên đi theo đúng con đường đã có: `halt_for_human` sau lần sinh lại thứ hai (mục 4.4 của `07-prompts.md`), không phải một nhánh lỗi mới.

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
| Credential `bo19_migrator` | Ngữ cảnh chạy bước `migrate` — **chưa chọn** (A-060, `[CẦN XÁC MINH]` theo tài liệu Render) | Cùng owner với A-060 |
| Credential `bo19_app` | Biến môi trường của `api`/`queue_worker` | Theo chính sách chung của DB managed, `[CẦN XÁC MINH]` |
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

Thao tác đặt tên **`operating_mode_transition`** — khác tên entity `operating_mode_change` có chủ đích, cùng lý do `open_request`/`request_open` đã nêu ở `GLOSSARY.md`: một tên là bước ghi của `tool_layer`, một tên là entity/bảng nó ghi vào. Thêm vào mục Thao tác do endpoint gọi của `GLOSSARY.md` (mục 12), tag "thêm ở Phase 9" — cùng khuôn với các đợt bổ sung "thêm ở Phase 4/5" đã có ở đúng danh sách đó.

`OperatingModeTransitionBody`: `to_mode` (`NON_PRODUCTION` | `PRODUCTION`), `decision_reference` (string, không rỗng — CHECK đã có ở DB, `api` **không** thêm phép kiểm hình thức nào khác cho nó: một tham chiếu văn bản có người ký là thứ hệ thống không thẩm định được, cùng nguyên tắc đã dùng ở A-033 và A-018), `effective_at` (tuỳ chọn, mặc định `now()`).

**Idempotency-Key = id của dòng `operating_mode_change` được tạo** — theo đúng quy tắc chuẩn ở mục Idempotency của `05-api.md`, **không** thêm một ngoại lệ mới vào danh sách ba ngoại lệ đã đóng (`POST /employee-imports`, `POST /templates`, `POST /delegations`).

**`audit_event` mức `WARNING`** — đúng định nghĩa ở `GLOSSARY.md`: hành động đúng luật nhưng cần người khác nhìn thấy, cùng họ với đường thoát tự duyệt của D-006.

**Một permission, cả hai chiều — chỉ ở `POST`.** `operating_mode.change` gác cả `NON_PRODUCTION → PRODUCTION` lẫn chiều ngược lại — không gác chiều quay về chặt hơn: chặn đường lùi (về chế độ an toàn hơn) nguy hiểm hơn chặn đường tiến, vì nó có thể khoá hệ thống ở `PRODUCTION` đúng lúc cần lùi khẩn cấp (ví dụ phát hiện template sai thể thức sau khi đã tháo chế độ phi sản xuất).

**`GET` dùng `audit.read_all`, không dùng `operating_mode.change`.** Quyền ghi không tự kéo theo quyền đọc — cùng nguyên tắc `document.issue` không kéo theo `audit.read_all`, `procedure.manage` không kéo theo `procedure.read_all` (mục 3.1). Lịch sử đổi chế độ là nhật ký, đã có chủ trong danh mục permission; đặt nó đúng nhà thay vì mở một mẫu hình "permission theo quan hệ HOẶC" mới cho riêng một endpoint. Người có `operating_mode.change` vẫn thấy dòng vừa tạo ở response của `POST`, và thấy chế độ hiện hành qua `GET /me` — không mất khả năng nào.

**Lỗi mới:** `OPERATING_MODE_UNCHANGED` (422) — `to_mode` trùng chế độ hiệu lực hiện tại. Kiểm ở `api` trước khi chạm DB; `ck_operating_mode_change_differs` là lớp chặn thứ hai.

### 12.3 Phạm vi contract đổi

Endpoint có contract: 48 → **49** (con số 48 được xác nhận ở lần đối chiếu tự động Phase 5/6, mục ngày 2026-09-13 của `CHANGELOG.md`). Sửa `05-api.md` (thêm mục 2.2b, cập nhật mục Nhãn phạm vi và loại trừ có chủ đích để trỏ sang endpoint thật thay vì liệt kê như loại trừ) và `contracts/openapi.yaml` (thêm path, hai schema). Bộ kiểm đối chiếu tự động ở `tools/contract-checks/` (nhắc ở A-047) cần chạy lại sau thay đổi này — **không chạy ở đây**, vì đó là code, ngoài phạm vi DESIGN MODE (mục 0 của `CLAUDE.md`); người triển khai chạy lại trước khi build.

---

## Migration bổ sung của Phase 9

**`contracts/schema.sql` KHÔNG bị sửa.** Mục 3 của `06-structure.md` đã chốt từ Phase 6: *"`0001_initial.sql` = `contracts/schema.sql` ở trạng thái đóng Phase 6; về sau mỗi thay đổi một file"*. Đây không phải một cách diễn giải — là câu đã viết sẵn cho đúng tình huống này. Toàn bộ thay đổi của Phase 9 nằm ở hai file migration mới, đúng trình tự của ADR-017 (bước 1: schema migration; bước 4: data migration).

### Schema migration — `backend/migrations/schema/0002_phase9_security.sql`

Hai bảng mới, cả hai tầng kỹ thuật (`GLOSSARY.md` mục 12): `employee_credential` (A-048) và `rate_limit_window` (mục Rate limit). Nội dung đầy đủ trong chính file đó; tóm tắt:

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

### Data migration — `backend/migrations/data/0001_permission_catalog.sql`

`INSERT` cho `permission` (25 dòng), `role` (3 dòng), `role_permission` (gói theo mục Gói permission theo vai trò của `00-domain.md`). Chi tiết ở mục 3.2. **Không** ghi `employee_role` hay `employee_permission_grant` — cả hai cần `employee_id` thật, chưa tồn tại ở thời điểm thiết kế.

### Hệ quả lên `04-data.md`

`contracts/schema.sql` vẫn **45 bảng**, không đổi — con số đó mô tả đúng một file, và file đó không đổi. Mục Ánh xạ entity → bảng của `04-data.md` mô tả **toàn bộ hệ schema sau migration** (45 bảng của `schema.sql` + 2 bảng của `0002_phase9_security.sql` = 47), nên hai dòng mới cho `employee_credential`/`rate_limit_window` vẫn đúng chỗ — chỉ sửa lại câu diễn giải con số cho không còn ngụ ý cả 47 bảng nằm trong một file. Tương tự mục Hai role và bất biến bằng quyền: hai nhóm quyền mới áp dụng cho hai bảng của migration 0002, không phải của `schema.sql`.

---

## Open Questions

Không có câu hỏi mở chỉ tồn tại trong file này. Giả định liên quan: `A-002` (số liệu tải cho ngưỡng rate limit), `A-031` (ngưỡng rate limit, thêm ở Phase 9), `A-036` (phạm vi Nghị định 30/2020/NĐ-CP, chạm chế độ phi sản xuất mà `operating_mode.change` điều khiển), `A-042` (đã chốt — danh mục + data migration), `A-048` (credential — tham số hash, thời hạn token, chu kỳ xoay vòng secret, rủi ro thứ tư), `A-055` (audit_event — trường hợp thứ tư), `A-057` (trần connection pool, liên quan tới rủi ro pool ở mục 6.2), `A-060` (ngữ cảnh chạy `migrate`), `A-061` (điều kiện kích hoạt lọc `request.read_all` theo phòng ban — Mở, không phải đề xuất chờ duyệt) — xem `ASSUMPTIONS.md`. **Thêm một `[CẦN XÁC MINH]` mới, xem mục K1 của báo cáo đóng phase:** header IP thật của client phía sau proxy Render, dùng để khoá `rate_limit_window` theo IP — cùng họ A-051.

---

## Quyết định kiến trúc

**ADR mới:** ADR-020 (`operating_mode_change` qua endpoint, không qua thao tác vận hành); ADR-021 (`argon2id` cho hash mật khẩu — có điều kiện đảo ngược thật: RAM của instance Render, nên không cùng mức với "chọn một thư viện" thông thường).

**Không viết ADR cho:** bảng `rate_limit_window` (áp dụng lại đúng nguyên tắc "bất biến bằng `GRANT`/`REVOKE`" đã có từ J4 của `04-data.md`, không phải một mẫu hình mới, và không có điều kiện đảo ngược riêng ngoài các tham số TBD đã ghi ở A-031).
