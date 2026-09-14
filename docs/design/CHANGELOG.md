# CHANGELOG — BO-19 Admin Service Desk Agent

> Ghi mọi thay đổi có ảnh hưởng liên phase: đổi tên entity hoặc trạng thái, đảo quyết định đã chốt, sửa `_PLAN.md`, bác bỏ giả định. Thay đổi chỉ nằm trong một file và không ai tham chiếu tới thì không cần ghi.

---

## 2026-09-11 — Phase 0: Domain Discovery

**Tạo mới**

- `docs/design/00-domain.md` — Request Type Catalog, slot schema, ba vòng đời, ma trận vai trò × hành động, edge case nghiệp vụ.
- `docs/design/GLOSSARY.md` — tên chuẩn của entity, vai trò, loại yêu cầu, trạng thái và enum.
- `docs/design/ASSUMPTIONS.md` — 15 giả định A-001 đến A-015.
- `docs/design/CHANGELOG.md` — file này.

**Quyết định có ảnh hưởng tới các phase sau**

1. `request` và `document` là hai entity riêng, hai vòng đời riêng. Lý do ở `00-domain.md` mục 1.
2. Thêm máy trạng thái thứ ba cho `room_booking`. `_PLAN.md` Phase 2 hiện chỉ yêu cầu hai máy trạng thái — **cần anh quyết** có cập nhật `_PLAN.md` hay không (Open Question Q3).
3. `document_number` chỉ được cấp tại thời điểm chuyển sang `ISSUED`. Ràng buộc này quyết định thiết kế `document_register` ở Phase 4.
4. Quá hạn SLA là điều kiện dẫn xuất, không phải trạng thái. Phase 2 và Phase 8 phải theo quy ước này.

**Mâu thuẫn giữa tài liệu gốc — đã báo cáo, xem mục ngày 2026-09-11 lần 2 bên dưới.**

**Chưa thay đổi**

`_PLAN.md` vẫn để trạng thái Phase 0 là `☐`. Tôi không tự đánh dấu hoàn thành — chờ anh duyệt.

---

## 2026-09-11 (lần 2) — Phase 0 v0.2: nạp quyết định D-001 → D-005

Anh trả lời Q1–Q5 và chốt quy ước ưu tiên. Toàn bộ được nạp vào tài liệu; `00-domain.md` lên `0.2`, `GLOSSARY.md` lên `0.2`, `ASSUMPTIONS.md` lên `0.2`.

### D-001 — Quy ước ưu tiên thống nhất MoSCoW

Ưu tiên MoSCoW khai báo **đúng một lần** ở PRD mục 5 (Phase 1). Phase khác chỉ tham chiếu tên feature; cần đánh dấu hạng mục có thể cắt thì dùng `[Should]`/`[Could]`.

| File | Thay đổi |
|---|---|
| `_PLAN.md` | Thêm mục "Quy ước ưu tiên — áp dụng cho mọi phase" ngay sau bảng phase. Phase 0: `[ADVANCED]` → `[Should]`, đổi "Ma trận vai trò × hành động" thành "Ma trận permission × vai trò". Phase 2: `[ADVANCED]` → `[Should]` ở sequence (f); viết lại yêu cầu state machine theo D-004 và bổ sung DoD "không sinh thêm máy trạng thái thứ hai cho Request". Phase 3: `[ADVANCED]` → `[Should]` |
| `.claude/commands/design.md` | Bước 3: bỏ "Đánh dấu `[MVP]`/`[ADVANCED]`", thay bằng quy ước mới |
| `00-domain.md`, `GLOSSARY.md` | Bỏ mọi nhãn **Must**/**Should**/**Could**/**Won't** nội dòng. Catalog dùng cột "Phạm vi" chỉ đánh dấu hạng mục bị cắt |

**Còn sót — cần anh quyết:** `CLAUDE.md` §2 dòng tiêu đề "Nâng cao" vẫn ghi *đánh dấu `[ADVANCED]`*, mâu thuẫn với khối quy ước ngay dưới nó và với D-001. Tôi không tự sửa `CLAUDE.md`. Ghi thành Q7.

### D-002 — Hồ sơ nhân viên (trả lời Q1)

Bảng `employee` trên PostgreSQL, import thủ công CSV, có cột `source` và `synced_at`. HRM thật vẫn ngoài phạm vi. Ba ràng buộc provenance mới ở `00-domain.md` mục 3.1 và phải đi vào định nghĩa "Yêu cầu đủ điều kiện xử lý" ở Phase 1. A-005 và A-007 chuyển sang `Đã chốt`. Thêm EC-WC-04 cho trường hợp `synced_at` quá cũ.

### D-003 — Tách đôi bài toán con dấu (trả lời Q2)

`requires_seal` là thuộc tính của `document`, cổng HITL `PENDING_SEAL` tách rời `PENDING_APPROVAL`, nằm trong Sprint đầu. `SEAL_REQUEST` thu hẹp thành loại yêu cầu cho **văn bản ngoài**, chuyển xuống `[Could]` vì phụ thuộc upload file ngoài. Slot schema `SEAL_REQUEST` bỏ `target_source` và `target_document_id`; enum `target_source` bị xoá khỏi `GLOSSARY.md`. Thêm bất biến số 2 ở mục 5.2 và EC-SR-05: duyệt nội dung và duyệt dấu không bao giờ gộp thành một thao tác. A-006 chuyển sang `Đã chốt`.

### D-004 — Một máy trạng thái Request (trả lời Q3)

Chấp nhận máy trạng thái cho `room_booking`, với điều kiện `request` có **đúng một** máy trạng thái dùng chung mọi loại yêu cầu. Khái niệm **artifact** được đưa vào `GLOSSARY.md`. `00-domain.md` mục 1 viết lại theo hướng "một Request, nhiều loại artifact"; mục 5.1 bổ sung quan hệ Request ↔ artifact và ví dụ EC-RB-04 nơi artifact sống tiếp sau khi request đã `FULFILLED`. `room_booking` chuyển xuống `[Should]`.

### D-005 — Permission thay cho role cứng (trả lời Q5)

Ma trận vai trò × hành động được thay bằng **danh mục 20 permission** dạng `entity.action`, cộng bảng gói permission theo vai trò. `document.issue` và `document.apply_seal` tách rời. Thêm ràng buộc **tách biệt trách nhiệm** ở mục 7.3: người tạo yêu cầu không được thực thi permission duyệt nào trên chính yêu cầu đó; `document.revoke_initiate` và `document.revoke_confirm` phải do hai người khác nhau. Ràng buộc này phải trở thành NFR ở Phase 1 và rule kiểm tra ở Phase 9. Hệ quả mới phát sinh: cần ít nhất hai người duyệt — thành A-016 và Q6.

### Q4 → A-014

Giữ `TBD` nhưng bổ sung giá trị mặc định đề xuất: **7 ngày làm việc** kể từ lần agent hỏi gần nhất, nhắc lại ở ngày thứ 3.

### Thay đổi tên gọi cần lưu ý cho phase sau

| Cũ (v0.1) | Mới (v0.2) |
|---|---|
| "Ma trận vai trò × hành động" | "Danh mục permission" + "Gói permission theo vai trò" |
| `SEAL_REQUEST` là loại yêu cầu nằm trong Sprint đầu, dùng cho cả văn bản nội bộ | `requires_seal` thuộc tính `document` (Sprint đầu) + `SEAL_REQUEST` chỉ cho văn bản ngoài `[Could]` |
| enum `target_source` | Đã xoá |
| "ba dạng kết quả" | "artifact" — thuật ngữ chuẩn trong `GLOSSARY.md` |


---

## 2026-09-11 (lần 3) — Phase 0 v0.3: D-006 và luật sửa `CLAUDE.md`

### Sửa `CLAUDE.md` — có phép của anh cho riêng lần này

Ba thay đổi, diff đầy đủ đã báo cáo trong phiên:

1. §2 dòng tiêu đề "Nâng cao": bỏ cụm *đánh dấu `[ADVANCED]`*.
2. §2 khối "Quy ước ưu tiên": bỏ cụm *và không dùng nhãn `[MVP]`/`[ADVANCED]`* khỏi câu đầu, thêm một đoạn mô tả lại theo `[Should]`/`[Could]` và nguyên tắc khai báo một lần ở PRD mục 5.
3. §4 thêm **luật 11**: model không tự ý sửa `CLAUDE.md`; chỉ sửa khi được cho phép từng lần và phải báo cáo diff. `docs/design/` vẫn được ghi tự do.

Kèm một lỗi tôi gây ra và đã sửa: lần ghi đầu làm `CLAUDE.md` đổi line ending từ LF sang CRLF, khiến diff thành toàn file. Đã chuẩn hoá lại LF cho `CLAUDE.md` và toàn bộ file trong `docs/design/` cùng `.claude/commands/design.md`, khớp quy ước của `docs/reference/sample_prd.md`. Diff cuối còn đúng 3 hunk.

### D-006 — Tách biệt trách nhiệm: đổi căn cứ chặn và thêm đường thoát

| | Trước (v0.2) | Sau (v0.3) |
|---|---|---|
| Căn cứ chặn | `actor == request.created_by` | `beneficiary_employee_id == approver_employee_id` |
| Nhập hộ rồi duyệt | Bị chặn nhầm | **Hợp lệ** — người thụ hưởng không phải người duyệt |
| Khi chỉ có một người duyệt | Điểm chết, chờ A-016 | Cho tự duyệt kèm 4 điều kiện bắt buộc |

Bốn điều kiện của đường thoát: `self_approval_reason` không rỗng · cờ `approval_step.self_approved` · `audit_event` mức `WARNING` · hiện riêng trên dashboard. Cấm mọi phương án tự động bỏ qua kiểm tra. Thiết kế chi tiết ở **Phase 8**.

**Tên mới cần dùng từ phase sau:** `request.beneficiary_employee_id` · `approval_step.self_approved` · `approval_step.self_approval_reason` · enum `audit_severity` (`INFO`/`WARNING`) · permission `request.create_on_behalf`.

**Đổi tên:** slot `subject_employee_code` của `WORK_CONFIRMATION` → `beneficiary_employee_id`, dùng chung cho mọi `request_type`. Số permission: 20 → 21.

### A-016 chuyển sang `Bác bỏ`

Không còn giả định nào về số người duyệt trong tổ chức. Thiết kế chạy được với một người lẫn nhiều người.

### A-005 tách đôi, EC-WC-04 bị gỡ

Anh hỏi con số 90 ngày lấy từ đâu — **tôi tự đề xuất, không có nguồn**. Xử lý:

- A-005 (cơ chế bảng `employee` + 3 ràng buộc provenance) → `Đã chốt`, không còn phần treo.
- Ngưỡng `synced_at` quá cũ tách thành **A-017**, giữ `TBD`, ghi rõ giá trị mặc định là do tôi đề xuất và không có căn cứ.
- **EC-WC-04 bị xoá khỏi bảng edge case**, vì bảng đó là nguồn của acceptance criteria và bộ eval Phase 10. Không đưa ngưỡng chưa có căn cứ vào tiêu chí nghiệm thu.
- Ràng buộc 3 ở mục 3.1 vẫn giữ nguyên: `source` và `synced_at` luôn hiển thị cho người duyệt. Đây là ràng buộc không cần ngưỡng nào.

Số edge case còn lại: WC 3 · IL 3 · RB 4 · SR 5.


---

## 2026-09-11 (lần 4) — Phase 0 v0.4: Q8, ADR-001, phân trách nhiệm về thể thức

Anh đổi cách phân trách nhiệm cho bài toán thể thức văn bản. Đây là thay đổi phạm vi thật, không phải làm rõ.

### ADR-001 — Khung thể thức nằm trong template, agent chỉ điền biến

File mới: `docs/design/decisions/ADR-001-template-giu-khung-the-thuc.md`. Là ADR đầu tiên của dự án.

Nội dung: khung thể thức (quốc hiệu, tiêu ngữ, tên cơ quan, số và ký hiệu, nơi nhận, phần chữ ký) nằm trong file `.docx` do người soạn. Agent chỉ điền biến, không tạo biến mới, không sửa ngoài vùng biến. Prompt LLM chỉ sinh nội dung tự do. Loại Option A (LLM sinh toàn bộ) và Option C (lai, cho LLM chỉnh khung).

**Hệ quả lên phạm vi phase: thể thức văn bản không còn thuộc Phase 7.** Phase 7 không viết prompt mô tả thể thức, không kiểm tra thể thức trong output validation, không nhận trách nhiệm về thể thức.

### D-008 — Định dạng số, owner, quy tắc trích dẫn, xử lý rủi ro

| Hạng mục | Trước | Sau |
|---|---|---|
| Định dạng số văn bản | `TBD`, chờ xác minh rồi mới thiết kế | **Cấu hình được ngay từ đầu**, không chờ ai. Ký hiệu chứa viết tắt tên cơ quan nên hardcode sai trong mọi trường hợp — là yêu cầu gốc, không phải chi phí phát sinh |
| Owner định dạng số | Chưa có | Product Owner, trước Phase 4 |
| Owner mẫu `.docx` | Chưa có | Product Owner, trước Phase 7 |
| Owner nghiệm thu thể thức | Chưa có | **Vẫn chưa có** — ghi rõ, ô Sign-off để chờ ký với người ký bỏ trống, cấm bịa owner |
| Trích dẫn ND 30/2020 | "không trích nếu chưa xác minh" | Cấm viết số điều/khoản/điểm/phụ lục **từ trí nhớ**; chỉ trích khi văn bản gốc đã có trong `docs/reference/` |
| A-009 | Giả định về cơ chế lẫn giá trị | Chỉ còn giả định về **giá trị**. Mức rủi ro giữ cao, mitigation là HITL, **residual risk ghi rõ** |

**Residual risk được ghi thành lời ở `00-domain.md` mục 6.1:** hệ thống không bao giờ tự khẳng định văn bản đúng thể thức. Nếu template sai thể thức *và* cán bộ hành chính không phát hiện khi duyệt, văn bản sai vẫn phát hành. Không có lớp kiểm soát tự động nào phía sau.

### File đã sửa

| File | Thay đổi |
|---|---|
| `decisions/ADR-001-...md` | Tạo mới |
| `00-domain.md` → v0.4 | Mục 6 viết lại phần định dạng số; thêm **mục 6.1** (owner, quy tắc trích dẫn, xử lý rủi ro); thêm D-007, D-008; Q8 → Q9 |
| `GLOSSARY.md` → v0.4 | `template` và `document_register` mô tả lại; thêm thuật ngữ **Khung thể thức** và **Nội dung tự do** |
| `ASSUMPTIONS.md` → v0.4 | A-009 viết lại có owner, mốc, mitigation, residual; thêm **A-018** (chưa có người nghiệm thu thể thức) |
| `_PLAN.md` | Phase 1 mục 10 và 11 ghi rõ ô Sign-off chờ và yêu cầu residual risk; Phase 1 siết quy tắc trích dẫn pháp lý; Phase 4 thêm yêu cầu định dạng số cấu hình được; Phase 7 thêm khối **Phạm vi** loại thể thức ra khỏi phase |

### Kiểm tra

Đã quét toàn bộ `docs/design/`: **không có** trích dẫn điều, khoản, điểm hay phụ lục nào của bất kỳ văn bản pháp luật nào. Mọi chỗ nhắc Nghị định 30/2020/NĐ-CP đều ở mức tên văn bản kèm `[CẦN XÁC MINH]`. `docs/reference/` hiện chỉ có `sample_prd.md`.


---

## 2026-09-11 (lần 5) — Phase 0 v0.5: chế độ phi sản xuất, đóng Open Questions

### Sửa `CLAUDE.md` §5 — có phép của anh cho riêng lần này, chỉ gạch đầu dòng đầu tiên

Một hunk duy nhất. Gạch đầu dòng "Thể thức văn bản hành chính" tách làm hai dòng: dòng đầu giữ nguyên tham chiếu Nghị định 30/2020/NĐ-CP; dòng thứ hai là **quy tắc trích dẫn tổng quát**, áp cho mọi nguồn bên ngoài chứ không riêng mục này — cấm viết từ trí nhớ số điều/khoản/điểm/phụ lục của văn bản pháp luật, số hiệu và nội dung tiêu chuẩn, phiên bản và con số trong tài liệu sản phẩm, số liệu benchmark; chỉ trích khi bản gốc đã có trong `docs/reference/`; chưa có thì ghi `[CẦN XÁC MINH]` kèm tên văn bản.

Đây là lần thứ hai sửa `CLAUDE.md`. Theo luật 11 của chính file đó, phép lần này không có giá trị cho lần sau.

### D-009 — Chế độ phi sản xuất

Q9 có câu trả lời cuối: **không có ai** nghiệm thu thể thức. Đây không phải khoảng trống chờ lấp, và phase sau không được hỏi lại.

Hệ quả không phải dừng thiết kế mà là một chế độ vận hành ràng buộc, ghi ở `00-domain.md` **mục 6.2**. Ba ràng buộc bắt buộc đồng thời chừng nào A-018 còn `Mở`:

| # | Ràng buộc |
|---|---|
| 1 | Watermark **không gỡ được** trong bản render: `BẢN THỬ NGHIỆM — KHÔNG CÓ GIÁ TRỊ PHÁP LÝ` |
| 2 | `document_register` cấp số từ dải `TRIAL`, tách hẳn khỏi dải `OFFICIAL` — sổ số thật không bị tiêu tốn số nào |
| 3 | Không đóng dấu thật. Cổng `PENDING_SEAL` vẫn chạy đủ quy trình duyệt để luồng được kiểm thử, chỉ chặn hành vi vật lý |

**Tháo chế độ là quyết định có người ký, không phải cờ cấu hình.** Thiết kế phải làm cho việc chuyển sang `PRODUCTION` đòi hỏi hành động được ghi nhận và quy trách nhiệm được, không phải sửa biến môi trường rồi deploy lại. Cơ chế cụ thể thuộc Phase 9 và Phase 11.

Ba ràng buộc này vào **NFR ở Phase 1**, đã ghi vào `_PLAN.md` mục 7 của Phase 1 — không để chúng chỉ nằm trong `ASSUMPTIONS.md`.

### A-018 — thêm cách xác minh thay thế

Trạng thái giữ `Mở` và đóng ở đó cho tới khi tổ chức có người nghiệm thu. Bổ sung cách xác minh khả thi: **xin một văn bản mẫu thật mà tổ chức đã phát hành, đối chiếu ngược template với nó.** Không phải nghiệm thu pháp lý, nhưng là căn cứ thực nghiệm và là thứ khả thi nhất hiện có.

### Open Questions của Phase 0 đã đóng

`00-domain.md` mục 11 giờ ghi rõ **"Không có"**, kèm bảng ba giả định mà Phase 1 sẽ chạm tới sớm nhất (A-002, A-009, A-018) cùng người gỡ. Mọi mục còn `Mở` trong `ASSUMPTIONS.md` là giả định có cách xác minh và có người làm, không phải câu hỏi chặn thiết kế.

### Tên mới cần dùng từ phase sau

`operating_mode` (`NON_PRODUCTION` / `PRODUCTION`) · `register_series` (`TRIAL` / `OFFICIAL`) · thuật ngữ **Chế độ phi sản xuất**.


---

## 2026-09-11 — Phase 1: PRD

`docs/design/01-prd.md` v0.1. `_PLAN.md` đánh dấu Phase 0 `☑`. `ASSUMPTIONS.md` lên v0.6, thêm A-019 và A-020.

### Bốn quyết định cấp Phase 1

| # | Quyết định | Lý do |
|---|---|---|
| 1 | **Không có pilot.** Metric neo vào UAT có kịch bản + bộ eval offline. Pilot thật là milestone riêng, mở sau khi A-018 đóng | D-009 buộc `NON_PRODUCTION` nên không phát hành văn bản thật; mọi số đo từ một "pilot" trong trạng thái đó là số giả. Đây là nhiễm format từ `sample_prd.md`, đã gỡ. Thành A-020 |
| 2 | **F5 thu hồi xuống Should** | Trạng thái `REVOKED` bắt buộc tồn tại trong mô hình dữ liệu, nhưng UI thu hồi thì không. Ở `NON_PRODUCTION` mọi văn bản đều mang watermark *không có giá trị pháp lý*, nên không có văn bản nào đang có hiệu lực để thu hồi. Việc giữ ở Sprint đầu: mô hình dữ liệu hỗ trợ `REVOKED`/`SUPERSEDED` và không có đường xoá cứng `document` đã `ISSUED` |
| 3 | **Hai định nghĩa vận hành nằm trong AC**, không ở mục riêng | "Yêu cầu đủ điều kiện xử lý" → AC của F1; "Văn bản đủ điều kiện trình duyệt" → AC của F2. Định nghĩa nổi ngoài AC là đồ trang trí không ai test |
| 4 | **Bộ eval 22 ca, dẫn xuất chứ không chọn số tròn** | Mỗi edge case Phase 0 sinh ≥1 ca, cộng happy path, thiếu thông tin, không đủ điều kiện, ngoài phạm vi. Công thức dẫn xuất ở NFR-07; thêm `request_type` hay edge case thì bộ eval mở rộng theo công thức, không thêm ca tuỳ ý |

### Metric neo phía nhân viên

M3 (hoàn tất không cần trợ giúp ngoài, đo ở UAT) và M7 (tỷ lệ yêu cầu vào qua hệ thống trên tổng, chỉ đo được sau khi mở sản xuất). Lý do phải có: M1–M6 chỉ nhìn thấy những gì đã vào hệ thống, nên chế độ hỏng *nhân viên bỏ hệ thống quay lại email* là **điểm mù đã biết** trước milestone sản xuất — PRD ghi thẳng điều đó ở RISK-03 thay vì để trống.

Tần suất dùng của nhân viên (vài lần/năm) thành **NFR-04**: người dùng thưa không có thói quen, không chịu được ma sát.

### Risk register — 7 rủi ro, mỗi cái có residual risk

RISK-02 (phân loại sai `request_type`) là rủi ro mới, không có trong outline ban đầu: văn bản sai loại **trông hoàn toàn đúng** nên người duyệt quen tay dễ bỏ qua. RISK-03 (nhân viên quay lại email) cũng mới. RISK-05 (prompt injection) viết lại đúng phạm vi — ADR-001 đã bịt phần lớn bề mặt, văn bản ngoài còn ở `[Could]`, còn lại chủ yếu là text nhân viên nhập; ghi rõ rủi ro sẽ tăng khi `SEAL_REQUEST` được kích hoạt.

### Sign-off

Bốn dòng, mọi ô "Người" để trống vì chưa có người thật. Dòng nghiệm thu thể thức ghi **"Không có"** ở cột Người và **"Không ký được"** ở cột Trạng thái — không phải ô chờ lấp. Kèm một dòng: nếu PO và Tech Lead là cùng một người thì ghi thẳng, và ghi luôn hạn chế một người giữ hai ô ký làm yếu kiểm tra chéo.


---

## 2026-09-11 (lần 2) — Phase 1: PRD v0.2 sau rà soát

Năm lỗi trong v0.1, anh chỉ ra bốn, tôi tìm thêm hệ quả của cái thứ năm.

### 1. Lỗi cấu trúc: ngưỡng vô căn cứ làm cổng nghiệm thu

Mục 2 khai M1–M3 là ngưỡng do chọn (A-019), rồi mục 8 lấy chính chúng làm điều kiện Definition of Done. Đúng cái bẫy EC-WC-04 đã bị gỡ ở Phase 0, quay lại ở quy mô lớn hơn.

Sửa bằng cách tách hai loại metric, khai ngay trong mục 2:

| Loại | Gồm | Vai trò |
|---|---|---|
| **Bất biến** | M8, M4, M5, M6 | Ngưỡng tuyệt đối. **Là** cổng nghiệm thu ở mục 8 |
| **Cảnh báo** | M1, M2, M3 | Ngưỡng do chọn. Không đạt thì mở rà soát, **không** trượt nghiệm thu. Không nằm trong mục 8 |

### 2. Bỏ phần trăm ở M1 và M3, thêm M8

Mẫu số quá nhỏ — 28 ca eval, vài người UAT — nên "≥ 95%" chỉ có nghĩa là *sai không quá một ca*, và "≥ 80%" đổi nghĩa tuỳ số người tham gia. Phần trăm làm ngưỡng trông như đã hiệu chỉnh trong khi chưa từng được đo. M1 và M3 giờ viết bằng **số ca tuyệt đối**.

Thêm **M8 = 0 ca sinh sai loại văn bản ở nhóm G**, tách khỏi M1 và đưa vào loại Bất biến. Lý do viết thẳng vào mục 2: hai loại yêu cầu đang hỗ trợ khác nhau rõ rệt nên M1 gần như chắc chắn đạt và **không canh giữ gì**; thứ thật sự canh RISK-02 là M8.

### 3. Bất biến rò qua một feature Should

Nghĩa vụ "không có đường xoá cứng `document` đã `ISSUED`" và "mô hình dữ liệu hỗ trợ `REVOKED`/`SUPERSEDED`" đang nằm trong văn xuôi của F5 (Should) — cắt F5 là mất luôn bất biến. **Chuyển cả hai thành AC của F3 (Must)**, cộng thêm "số đã cấp không bao giờ trả lại dải số để tái sử dụng". F5 giữ phần lý do và trỏ về F3.

### 4. Bộ eval: 22 → 28 ca, thêm nguồn dẫn xuất thứ hai

**Lỗ chính:** định nghĩa "Văn bản đủ điều kiện trình duyệt" ở F2 có **độ phủ eval bằng không**. Công thức cũ chỉ dẫn xuất từ `00-domain.md` mục 8, vốn thiên về khâu tiếp nhận và hầu như không chạm khâu sinh văn bản.

Sửa: khai **hai nguồn dẫn xuất**, mỗi ca phải chỉ được về một trong hai — (1) bảng edge case Phase 0, (2) các ca "bị coi là KHÔNG đạt" của hai định nghĩa vận hành ở F1 và F2. Bảng eval thêm cột **Nguồn**.

| Nhóm | v0.1 | v0.2 | Thay đổi |
|---|---|---|---|
| D | 1 | 3 | Thêm: slot có ký tự nhưng rỗng nội dung · lời khai mâu thuẫn `HR_PROFILE`. Đổi tên nhóm cho đúng nội dung |
| E | 4 | 2 | **Bỏ EC-SR-01 và EC-SR-05** — xem mục 5 dưới |
| G | 2 | 4 | Thêm: nhập nhằng `WORK_CONFIRMATION` với `INCOME_CONFIRMATION` chưa hỗ trợ · đổi loại giữa chừng · một tin nhắn hai yêu cầu |
| **H** | — | **4** | **Nhóm mới**, phủ định nghĩa ở F2: thêm câu chữ vào khung · render từ phiên bản template hết hiệu lực · tự đặt giá trị cho biến chưa xác nhận · thiếu biến "không quan trọng" |
| | **22** | **28** | |

### 5. EC-SR-01 và EC-SR-05 bị loại khỏi bộ eval — hai lý do khác nhau

Anh nghi ngờ đúng, nhưng hai ca sai chỗ vì hai lý do không giống nhau:

- **EC-SR-01** — phần thuộc Sprint đầu là **bất biến của máy trạng thái** (`PENDING_SEAL` chỉ nhận `SIGNED`), không phải hành vi agent. Theo D-003, trong Sprint đầu nhân viên **không tự xin dấu** vì đóng dấu là một bước trong vòng đời văn bản, nên không có input hội thoại nào kích hoạt được ca này. Nửa còn lại thuộc `SEAL_REQUEST`, đang `[Could]`.
- **EC-SR-05** — là ca kiểm thử **permission và giao diện người duyệt**, agent không tham gia.

Cả hai chuyển sang kiểm bằng **M4** và test permission. PRD ghi rõ hai ca này bị loại và tại sao, để lần rà soát sau không tưởng là bỏ sót.

### 6. Phát sinh ngoài eval — AC mới ở F1

Ca "một tin nhắn chứa hai yêu cầu" bộc lộ một tình huống **Phase 0 và Phase 1 đều chưa xử lý**. Thêm AC ở F1: một `request` mang đúng một `request_type` nên hai nhu cầu phải thành hai `request`; agent phải nhận ra và nêu rõ cả hai, xử lý **tuần tự**, **không bao giờ** im lặng bỏ qua nhu cầu thứ hai và không gộp hai nhu cầu vào một văn bản.

Đây là lỗ hổng trong bảng edge case của `00-domain.md` mục 8 — **chưa sửa Phase 0**, xem báo cáo cuối phiên.


---

## 2026-09-11 (lần 3) — Phase 0 v0.6 + Phase 1 v0.3: bổ sung chiều `EC-CV-xx`

### Tiền lệ về quy trình

**Đây là lần đầu một phase sau tìm ra thiếu sót ở phase trước.** Phase 1 phát hiện bảng edge case ở `00-domain.md` mục 8 không chứa được ca "một tin nhắn chứa hai yêu cầu".

Cách xử lý đã dùng, và là tiền lệ cho các lần sau:

1. **Chẩn đoán đến gốc, không dừng ở triệu chứng.** Bảng cũ tổ chức thuần theo `request_type`, nên **về cấu trúc** không chứa được bất kỳ ca nào xảy ra *trước* khi biết `request_type`. Thiếu một **chiều phân loại**, không phải thiếu hai ca. Thêm hai ca rồi đóng lại thì lần sau vẫn sót.
2. **Sửa ở phase gốc.** Nhóm `EC-CV-xx` được thêm vào `00-domain.md`, nơi bảng edge case thuộc về.
3. **Dẫn xuất lại ở phase sau.** Bộ eval ở PRD được tính lại từ bảng đã sửa, theo đúng công thức dẫn xuất có sẵn.
4. **Không vá ở phase sau.** Phiên bản trước có một ghi chú ngoại lệ trong `01-prd.md` kiểu *"ca này không có trong Phase 0"*. Ghi chú đó đã bị gỡ. Một ngoại lệ được ghi chú vẫn là một ngoại lệ, và nó làm hỏng chiều phụ thuộc Phase 0 → Phase 1.

### `00-domain.md` v0.6 — mục 8 có hai chiều

| Chiều | Nhóm | Xảy ra khi nào |
|---|---|---|
| Tầng hội thoại và phân loại | `EC-CV-xx` | **Trước** khi biết `request_type` |
| Tầng nghiệp vụ theo loại | `EC-WC`, `EC-IL`, `EC-RB`, `EC-SR` | **Sau** khi đã biết `request_type` |

Bốn ca mới: **EC-CV-01** nhiều nhu cầu trong một lượt · **EC-CV-02** đổi loại giữa chừng, slot cũ không được mang sang · **EC-CV-03** từ ngữ trỏ một loại nhưng ý định thuộc loại khác, hai chiều · **EC-CV-04** bỏ giữa chừng rồi quay lại, phân biệt trong hạn và sau `EXPIRED`.

Đặt tên theo **bản chất của tầng**, không gọi là "nhóm chung" — một nhóm mang tên "chung" sẽ hút mọi thứ không biết xếp đâu và thành sọt rác.

### Kiểm chéo trùng lặp

EC-CV-03 có hai chiều. Chiều *từ ngữ của loại đang hỗ trợ, ý định thuộc loại chưa hỗ trợ* **chính là EC-WC-03** đã có sẵn. Không tạo ca mới cho chiều đó và không đếm hai lần; PRD ghi rõ điều này ngay dưới bảng eval.

### `01-prd.md` v0.3 — dẫn xuất lại

| Thay đổi | Trước | Sau |
|---|---|---|
| Nhóm G | "Nhập nhằng phân loại", 4 ca, nguồn *"1 và 2 — F1"* | "Tầng hội thoại và phân loại", **7 ca**, nguồn **1** thuần Phase 0 |
| Tổng bộ eval | 28 | **31** |
| Ghi chú ngoại lệ ở F1 | Có | Đã gỡ |

Nhóm G dẫn xuất: EC-CV-01 → 2 ca · EC-CV-02 → 1 ca · EC-CV-03 → 2 ca · EC-CV-04 → 2 ca.

**Một ca nằm lạc đã chuyển về đúng chỗ.** Dòng *"yêu cầu thuộc loại chưa hỗ trợ nhưng được mô tả bằng từ ngữ của loại đang hỗ trợ"* đang nằm trong danh sách "KHÔNG đủ điều kiện xử lý" ở F1 — nhưng đó là ca **phân loại**, không phải ca **điều kiện**: nó xảy ra trước khi biết loại, nên không thể là điều kiện của một loại. Đã gỡ khỏi F1 và chuyển thành EC-CV-03. Danh sách ở F1 thêm một câu nói rõ nó chỉ bàn về điều kiện của yêu cầu **đã biết loại**.

F1 thêm ba AC tương ứng EC-CV-01, EC-CV-02, EC-CV-04.

### A-014 cần bổ sung — đã nêu, chưa tự quyết

EC-CV-04 làm lộ ra A-014 mới trả lời được một nửa. *"Bao lâu thì `EXPIRED`"* và *"rồi dữ liệu đã thu ra sao"* là **hai quyết định khác nhau**; A-014 chỉ có cái thứ nhất. Hệ quả: ca "quay lại sau `EXPIRED`" có hành vi đúng khác nhau tuỳ dữ liệu còn hay mất, nên chưa kiểm thử được hết.

Đã ghi chiều thiếu vào A-014, **không đổi giá trị mặc định 7 ngày làm việc**. Chiều thứ hai không cần đo — là quyết định về quyền riêng tư và trải nghiệm.

### Sửa lỗi đánh số phiên bản

Các vòng trước tôi ghi trong CHANGELOG rằng `00-domain.md` lên v0.3, v0.4, v0.5 nhưng **quên sửa dòng header trong chính file** — nó vẫn ở `0.2`. `GLOSSARY.md` cũng vậy. Đã đồng bộ cả hai lên **0.6**. Các mục CHANGELOG cũ giữ nguyên, không viết lại lịch sử; số phiên bản trong đó nên đọc là *thứ tự lần sửa*, và từ mốc này header file mới là nguồn sự thật.

`GLOSSARY.md` không có tên entity, trạng thái, enum hay permission nào mới — `EC-CV-xx` là quy ước mã edge case, không phải tên miền nghiệp vụ. Chỉ bump phiên bản cho đồng bộ.


---

## 2026-09-11 (lần 4) — Phase 0 v0.7 + Phase 1 v0.4: `slot_sensitivity`, D-010, tách nhóm eval

### Tiền lệ thứ hai: gom nhóm theo **nguồn dẫn xuất** thay vì theo **tiêu chí chấm**

Lần 3 tôi đổi tên nhóm eval G thành "Tầng hội thoại và phân loại" để nó chứa được cả bốn ca `EC-CV-xx`. Sai: bốn ca đó **cùng nguồn dẫn xuất nhưng khác tiêu chí chấm**.

| | Nhóm G | Nhóm I |
|---|---|---|
| Đáp án chuẩn khẳng định | Agent có nhận đúng ý định không | Agent có khôi phục hoặc bỏ đúng trạng thái không |
| Ca | EC-CV-01, EC-CV-02, EC-CV-03 | EC-CV-04 |

**Dấu hiệu phát hiện:** chính sách giữ hay xoá dữ liệu khi `EXPIRED` đổi đáp án của ca EC-CV-04 nhưng không đổi đáp án của bất kỳ ca nào còn lại. Một biến đổi chỉ ảnh hưởng một phần của nhóm là dấu hiệu nhóm đó phải tách.

**Quy tắc ghi lại cho Phase 10:** trục chia nhóm eval là *đáp án chuẩn khẳng định cái gì*, **không** phải *ca dẫn xuất từ đâu*. Hai trục này trùng nhau trong đa số trường hợp, nên rất dễ gom nhầm mà không ai nhận ra.

**EC-CV-02 chấm hai tiêu chí TÁCH RỜI:** phân loại đúng, và không mang slot cũ sang. Phân loại đúng mà mang slot cũ sang **vẫn là trượt**. Gộp một điểm thì chế độ hỏng nguy hiểm hơn bị điểm phân loại che mất.

Nhóm: G 7 ca → G 5 ca + I 2 ca. Tổng vẫn **31**.

### `slot_sensitivity` — trả một món nợ có sẵn, không phải chi phí mới

NFR-05 vốn đã yêu cầu mask PII trong log và trong prompt gửi LLM. Muốn mask thì phải biết trường nào nhạy cảm — và danh sách đó đang **hardcode "`national_id`, `date_of_birth`" trong văn xuôi NFR-05**. Cùng một lỗi với A-014: gắn độ nhạy vào **tên trường** thay vì làm nó thành **thuộc tính của dữ liệu**.

Thêm cột `Nhạy cảm` vào toàn bộ bảng slot schema ở `00-domain.md` mục 3, ba mức: `INT` · `PER` · `RES`. NFR-05 viết lại để key theo thuộc tính này. Hệ quả thực tế: thêm một slot mới là **gán độ nhạy cho nó**, không phải nhớ bổ sung tên nó vào một danh sách viết tay ở chỗ khác.

Độ nhạy **không trùng nguồn**: `purpose` và `work_content` là `USER_INPUT` nhưng ở mức `RES`; `date_of_birth` là `HR_PROFILE` nhưng chỉ `PER`.

Ánh xạ ba mức sang phân loại của Nghị định 13/2023/NĐ-CP ghi `[CẦN XÁC MINH]` — chưa có văn bản gốc trong `docs/reference/`.

### A-014 — chiều thứ hai đã chốt, key theo `slot_sensitivity`

| Nhóm | Khi `EXPIRED` |
|---|---|
| Slot `INT`, `PER` | **Giữ** giá trị |
| Slot `RES` | **Xoá** giá trị |
| Mọi slot nguồn `HR_PROFILE` | **Bỏ xác nhận**, lấy lại từ `employee` ở lần thử sau |
| Dòng `request` | **Giữ** làm bản ghi |

Nguyên tắc: `EXPIRED` là điểm cuối của một **lần thử**, không phải điểm cuối của **dữ liệu**. Thời hạn xoá thật vẫn thuộc A-010, **không** đặt thời hạn mới.

**Đánh đổi đã ghi thành lời, không viết như thể không có.** NFR-04 đẩy về phía giữ, NFR-05 và nghĩa vụ theo Nghị định 13/2023/NĐ-CP đẩy về phía xoá. Cái đang đánh đổi: slot `PER` được giữ, trong đó có `recipient_org` — tên nơi nhận có thể là bệnh viện hay toà án, tức vẫn suy ra được thông tin nhạy cảm dù trường đó không phải `RES`. Phương án **giảm** phơi nhiễm chứ không **loại bỏ**, và khối `PER` giữ lại **mở rộng phạm vi A-010 phải phủ**.

Định giá lại phần mất mát NFR-04 so với bản trước: `purpose` và `work_content` là thứ nhân viên **vẫn nhớ**, gõ lại rẻ. Cái đắt là **dữ liệu tra cứu** — mã số, ngày tháng, tên đầy đủ cơ quan nhận — và toàn bộ nhóm đó ở mức `INT`/`PER` nên **được giữ**.

### D-010 — `document` chỉ render sau `SUBMITTED`

Trước `SUBMITTED` yêu cầu chưa đủ điều kiện xử lý theo định nghĩa F1, nên render sẽ tạo ra đúng thứ ADR-001 muốn tránh: một artifact trông như văn bản thật nhưng không phải. Thêm nữa mỗi lần sửa slot phải render lại, tốn token cho thứ chưa chắc được gửi (NFR-06).

Hệ quả: ở `EXPIRED` **không tồn tại file nháp nào**. Xem trước cho nhân viên, nếu sau này cần, là một feature **riêng có tên và ở mức `[Could]`**, không phải hệ quả ngầm của việc render sớm.

### Rule về file — bỏ ở tầng slot, giữ lại câu hỏi

Rule "xoá `national_id`, `date_of_birth` khi `EXPIRED`" đã **bỏ** vì cả ba trường định danh đều là `HR_PROFILE`, và rule `RES` cộng rule bỏ xác nhận `HR_PROFILE` đã phủ hết ở tầng slot. Nhưng bỏ suông thì mất luôn câu hỏi, nên ghi lại: **nếu sau này có file nháp render tồn tại trước `SUBMITTED` thì cần một rule riêng cho FILE, không phải cho slot.** D-010 hiện làm tình huống đó không xảy ra; rule file chỉ cần khi D-010 bị đảo.


---

## 2026-09-11 (lần 5) — D-010 đủ hai biên, và ba câu hỏi kỹ thuật được neo thay vì chốt

### Ranh giới phase: cái gì thuộc PRD, cái gì không

Ba vấn đề nổi lên ở lần 4 được xử lý **ba cách khác nhau**, và sự khác nhau đó là điểm chính của mục này:

| Vấn đề | Xử lý | Vì sao |
|---|---|---|
| Mốc render | **Chốt** ở Phase 0 (D-010) | Là hành vi sản phẩm quan sát được: cán bộ mở hàng đợi có thấy bản nháp không |
| Lưu trữ bản render | **Neo** — ranh giới sản phẩm vào PRD, phần kỹ thuật thành A-021 owner Phase 4 | Đè hay tích luỹ là thiết kế lưu trữ; chốt ở Phase 1 vi phạm `CLAUDE.md` mục 0 |
| Số lần render | **Neo** — hành vi khi chạm trần vào NFR-06, con số thành A-022 owner Phase 11 | Hành vi là cam kết sản phẩm; con số là định cỡ kỹ thuật |

Bài học ghi lại: khi một vấn đề kỹ thuật nổi lên giữa Phase 1, câu hỏi đúng không phải *"chốt hay bỏ qua"* mà **"phần nào của nó là hành vi quan sát được"** — phần đó thuộc PRD, phần còn lại thành giả định có owner là phase sẽ giải nó. Bỏ qua thì mất; chốt hết thì lấn phase sau.

### D-010 — bổ sung biên thứ hai

Trước: chỉ có biên dưới, *không bao giờ trước `SUBMITTED`*. Thiếu biên trên nên vẫn mở đường hoãn tới `IN_REVIEW`.

Nay: render **tại thời điểm** `request` chuyển sang `SUBMITTED`. Lý do không hoãn tới `IN_REVIEW`: **`IN_REVIEW` không phải trạng thái do hệ thống điều khiển** — nó phụ thuộc việc có người mở hàng đợi hay không, nên yêu cầu gửi chiều thứ Sáu sẽ không có văn bản tới sáng thứ Hai mà không vì bất kỳ lý do kỹ thuật nào.

Hệ quả tôi từng nêu như một lo ngại — văn bản tồn tại khi chưa ai nhận xử lý — thực ra là **điều mong muốn**: cán bộ mở hàng đợi là thấy bản nháp sẵn, đúng user story 1 của F2. Render tại `IN_REVIEW` thì họ mở ra phải chờ.

Kèm theo: dòng `DRAFT` ở bảng trạng thái `document` sửa từ *"chỉ tồn tại sau khi"* thành *"được tạo tại thời điểm"* để không mâu thuẫn với D-010; và AC ở F2 sửa tương ứng.

**Ghi chú về phạm vi sửa:** chỉ thị *"bổ sung D-010"* buộc sửa `00-domain.md`, trong khi lệnh đứng của phiên là *"không đụng `00-domain.md`"*. Tôi đọc chỉ thị cụ thể là ghi đè lệnh đứng, và giới hạn thay đổi ở Phase 0 đúng trong hai chỗ trên, không động gì khác.

### A-021 — lưu trữ bản render, owner Phase 4

Ranh giới sản phẩm **đã có sẵn trong tài liệu nhưng chưa ai nối lại**: F6 yêu cầu văn bản đã render ghi lại phiên bản template đã dùng, và nội dung từ `APPROVED` trở đi là bất biến. Nối hai cái thành một câu ở AC của F3: **bản render gắn với `document` ở `SEALED` và `ISSUED` không bao giờ được mất hay bị đè**; bản trung gian trong vòng `CHANGES_REQUESTED → DRAFT` thì tự do.

Nhờ vậy Phase 4 có đủ đầu vào mà không cần ai quyết trước chuyện đè hay tích luỹ.

### A-022 — trần số lần render, owner Phase 11

Phần thuộc sản phẩm vào NFR-06: **hành vi khi chạm trần là cam kết, con số trần thì không.** Chạm trần thì dừng có kiểm soát và chuyển cho người thật, nêu rõ dừng ở đâu và vì sao — không bao giờ âm thầm dừng giữa chừng. Lý do viết thẳng: *một bản nháp thiếu nội dung nhưng trông hoàn chỉnh nguy hiểm hơn hẳn việc không có bản nháp nào.*

**Một giả định ngầm của tôi bị bắt và đã gỡ.** Tôi đang mặc định mỗi vòng `CHANGES_REQUESTED` là một lần render **đầy đủ**. Chưa chắc — sửa một chỗ trong nội dung tự do không nhất thiết phải gọi LLM lại từ đầu. Nếu render lại làm được từng phần thì con số trần mang ý nghĩa hoàn toàn khác, tức định cỡ trước khi biết điều đó là **định cỡ sai đơn vị**. Đã thành câu hỏi bắt buộc của Phase 3.

### `_PLAN.md` — bốn phase nhận thêm yêu cầu

| Phase | Thêm gì |
|---|---|
| 3 | **Đơn vị render lại** — render toàn bộ hay sửa từng phần? Cấm mặc định |
| 4 | **Lưu trữ bản render (A-021)** kèm ràng buộc bất biến ở `SEALED`/`ISSUED`; phải nêu cơ chế bảo đảm, không chỉ khẳng định |
| 8 | **Cơ chế dừng khi chạm trần (A-022)** — trạng thái và giao diện của tình huống dừng |
| 11 | **Định cỡ A-022**, chỉ sau khi Phase 3 chốt đơn vị và Phase 8 chốt cơ chế |


---

## 2026-09-12 — Bỏ mục Open questions và Sign-off khỏi PRD; luật tham chiếu theo tên

### Tiền đề ban đầu bị chính khảo sát bác bỏ

Yêu cầu xuất phát là *"bỏ mục 9 vì nó thừa"*. Khảo sát trước khi sửa cho kết quả **ngược lại**: mục 9 đang **gánh** thông tin không nơi nào khác giữ.

| | Mất nếu xoá thẳng |
|---|---|
| Hạn | **6/7 dòng** — chỉ A-009 có hạn ghi ở nơi khác |
| Owner | **3/7 dòng** |
| Cả nội dung câu hỏi | **1 dòng** — ba con số của buổi UAT: bao nhiêu người, bao nhiêu ca, ai chấm |

Cảm giác "thừa" đến từ việc `ASSUMPTIONS.md` **thiếu cột Owner và Hạn**, nên thông tin đó buộc phải trú ở PRD. **Trùng lặp là triệu chứng, không phải bệnh.**

Vì vậy thứ tự thi hành là bắt buộc: **sửa `ASSUMPTIONS.md` đủ cột trước**, rồi mục 9 mới thực sự thừa và xoá được. Làm ngược là mất thông tin. Ghi lại vì đây là lần đầu một bước khảo sát đảo ngược chính đề bài của nó — và lý do nó phát hiện được là vì khảo sát đi trước thao tác sửa.

### `ASSUMPTIONS.md` v0.9 — thêm Owner và Hạn

Bảng lên **7 cột**, 23 giả định, đã sắp xếp lại theo ID (trước đó lộn xộn do chèn dần).

- Giả định đã đóng — A-005, A-006, A-007 (`Đã chốt`) và A-016 (`Bác bỏ`) — ghi `—` ở cả hai cột. Để trống sẽ trông như còn treo.
- Ô **để trống** là thông tin thật: **chưa có ai nhận** hoặc **chưa có mốc**. Hiện 11/23 giả định không có owner — đó là hiện trạng, không phải chỗ chờ điền cho đẹp.
- Owner và Hạn từng nhúng trong văn xuôi cột *Cách xác minh* (A-009, A-018, A-020, A-021, A-022) đã được rút ra cột riêng, tránh hai nơi giữ cùng một thông tin.
- **A-023 mới** — đáp án chuẩn cho 31 ca eval, owner Trưởng phòng Hành chính, hạn trước UAT. Trước đây chỉ tồn tại ở mục 9 của PRD.
- **A-020** nạp thêm ba con số của buổi UAT, thứ không tồn tại ở bất kỳ đâu khác.

### PRD v0.6 — bỏ hai mục, đánh số lại

| Việc | Chi tiết |
|---|---|
| Mục Open questions | **Xoá hẳn, kể cả tiêu đề.** Mục `## Open Questions` cuối file gánh vai trò theo mục Definition of Done cho mọi phase của `CLAUDE.md`, trỏ thẳng sang `ASSUMPTIONS.md` và liệt kê 8 giả định PRD phụ thuộc |
| Mục Sign-off | **Xoá bảng.** Đoạn giải thích được nâng vào NFR-03 |
| Risk register | 11 → **9**, không phải 10 |

**Vì sao 9 chứ không phải 10:** chỉ thị ban đầu là "đổi 11 → 10" dựa trên phương án giữ tiêu đề mục 9. Phương án đó đã bị thay bằng xoá hẳn cả hai mục, nên đích đúng là 9. Đánh số 10 sẽ để lại lỗ ở vị trí 9.

**NFR-03 giờ tự giải thích được.** Trước đây nó mở bằng *"Chừng nào A-018 còn Mở…"* rồi liệt kê ba ràng buộc kỹ thuật — **trỏ mã giả định mà không bao giờ nói mã đó là gì**, nên người đọc PRD thấy ba ràng buộc treo lơ lửng không nguyên nhân. Nay mở bằng một đoạn nói thẳng: tổ chức không có ai nghiệm thu thể thức, nên residual risk của RISK-01 không có người gánh, nên hệ thống không được phép phát hành văn bản có giá trị pháp lý.

**Hai thứ bị bỏ cùng bảng Sign-off, báo cáo để anh quyết có cần giữ:** (a) câu *"PRD chỉ chuyển Draft → Approved khi đủ các xác nhận"* — PRD nay không còn cổng duyệt nào được phát biểu; (b) ghi chú *"một người giữ hai ô ký làm yếu kiểm tra chéo"* — mất chỗ bám khi không còn bảng ký.

### Luật mới: tham chiếu chéo theo TÊN MỤC

Thêm **luật 12** vào mục Luật viết tài liệu của `CLAUDE.md`. Đây là lớp lỗi thứ tư cùng họ được ghi thành luật:

| Lần | Khoá tham chiếu vào thứ có thể đổi |
|---|---|
| 1 | `[ADVANCED]` hardcode trong `_PLAN.md` và `CLAUDE.md` |
| 2 | Danh sách tên trường nhạy cảm viết tay trong NFR-05 |
| 3 | Nhóm eval gom theo nguồn dẫn xuất thay vì theo tiêu chí chấm |
| 4 | **Số mục trong tham chiếu chéo file** |

Quét **50 tham chiếu chéo file theo số** trong 8 file, chuyển hết sang tên mục. Tham chiếu trong cùng một file giữ nguyên số — luật chỉ áp cho tham chiếu chéo.

Không giữ ngoại lệ cho `PRD mục 5`. **Lệch với cách diễn đạt anh nêu:** anh đề xuất *"quy ước MoSCoW ở PRD"*, tôi dùng *"mục Scope & priority của PRD"* vì cả 7 ngữ cảnh đều đã có chữ MoSCoW ngay trước đó — dùng cụm kia sẽ thành *"khai báo một lần ở quy ước MoSCoW ở PRD"*. Ý định bỏ ngoại lệ được giữ nguyên.

### `_PLAN.md`

Bảng cấu trúc PRD bỏ hai hàng, Risk register về 9. DoD riêng Phase 1 **thay chứ không bỏ** vế cũ: *"mọi câu hỏi mở có Owner và Hạn trong `ASSUMPTIONS.md`"* cộng *"việc nghiệm thu thể thức được ghi nhận là không có người đảm nhận"* — vế thứ hai bắt buộc, không có nó thì việc "không ai ký" tuột khỏi mọi điều kiện nghiệm thu.

Kèm một mâu thuẫn cũ phát hiện khi sửa bảng: hàng `| 2 | Goals & metrics |` vẫn ghi *"Gắn với một pilot cụ thể"*, trái với A-020. Đã sửa cho khớp.


---

## 2026-09-12 (lần 2) — Phase 2: System Architecture

**Tạo mới:** `docs/design/02-architecture.md`; `decisions/ADR-002-pgvector-trong-postgresql.md`; `decisions/ADR-003-object-storage-s3-compatible.md`; `decisions/ADR-004-queue-worker-bang-job-postgresql.md`; `decisions/ADR-005-orchestrator-trong-tien-trinh.md`.

**Sửa:** `01-prd.md` → v0.7 (NFR-05); `GLOSSARY.md` → v0.8 (mục 11 mới); `ASSUMPTIONS.md` → v0.10 (A-024, A-025).

### Mâu thuẫn thật tìm thấy giữa Phase 1 và Phase 2 — sửa ở file gốc, không vá ở đây

**Hệ quả ngoài dự kiến của vòng thêm `slot_sensitivity` (v0.7 của `00-domain.md`/`GLOSSARY.md`).** Khi đó NFR-05 được viết lại để key theo `slot_sensitivity`, và câu "slot mức `RES` bị mask... trong log **và trong prompt gửi LLM**" được viết như một hệ quả tự nhiên của việc thêm cột độ nhạy. Không ai kiểm lại câu đó với F2: bước sinh nội dung tự do **phải đọc** đúng hai slot `RES` là `purpose` và `work_content` để soạn văn bản. Che chúng khỏi prompt thì bước đó không thực hiện được — đây không phải cách diễn đạt mơ hồ, mà là hai yêu cầu chốt ở hai phase khác nhau **phủ định lẫn nhau theo nghĩa đen**.

**Xử lý theo đúng tiền lệ đã lập (lần đầu ở mục `2026-09-11 (lần 3) — bổ sung chiều EC-CV-xx`):** chẩn đoán tới gốc, sửa ở file gốc (`01-prd.md`, nơi NFR-05 thuộc về), không vá bằng một ghi chú ngoại lệ ở `02-architecture.md`.

**Nguyên tắc đúng, thay cho nguyên tắc sai:** không phải "che theo độ nhạy" mà là **tối thiểu hoá theo nhu cầu từng bước** — mỗi prompt module (Phase 7) tự khai danh sách slot nó cần, tầng gọi LLM (`ai_gateway`) chỉ gửi đúng danh sách đó, bất kể độ nhạy cao hay thấp của từng slot. Quy tắc mask trong **log kỹ thuật** (khác `audit_event`) theo `slot_sensitivity` giữ nguyên, không bị ảnh hưởng — chỉ phần "trong prompt gửi LLM" bị viết lại.

**Vì sao đây là lỗi thật, không phải cách đọc khác nhau của cùng một ý:** nếu giữ nguyên câu cũ, Phase 7 và Phase 9 sẽ thiết kế output validation và guardrail theo đúng một quy tắc mà chính sản phẩm không thể vận hành được — phát hiện muộn hơn (ví dụ khi viết prompt thật ở Phase 7) sẽ tốn công sửa ngược nhiều phase.

### Bốn ADR mới — mỗi cái có điều kiện đảo ngược và lý do loại riêng, không dùng chung khuôn

| ADR | Quyết định | Vì sao không chỉ là "gộp vào Postgres cho đơn giản" |
|---|---|---|
| ADR-002 | `vector_store` = `pgvector` trong `postgresql`, không phải vector DB riêng | Lý do loại chính không phải chi phí mà là **hai nguồn sự thật cho cùng một khái niệm phiên bản `template`** nếu tách metadata và embedding ra hai hệ thống |
| ADR-003 | `object_storage` = S3-compatible ngoài Render, **bất biến đảm bảo ở tầng ứng dụng** (khoá đối tượng content-addressed), không dựa vào Object Lock của vendor | Vendor cụ thể còn `TBD` (A-024) — chốt kiến trúc phụ thuộc một tính năng chưa xác minh sẽ lặp lại đúng lỗi "bịa số liệu/tính năng chưa xác minh" mà `CLAUDE.md` cấm, chỉ khác tầng |
| ADR-004 | `queue_worker` = bảng job trong `postgresql`, không thêm Redis/Celery | Lý do chính là **tính nguyên tử của D-010** (enqueue job render phải cùng giao dịch với transition `SUBMITTED`) — Redis phá vỡ tính nguyên tử đó trừ khi thêm outbox pattern, tức thêm phức tạp để giải quyết đúng vấn đề Postgres đã giải quyết sẵn |
| ADR-005 | `orchestrator` là thư viện dùng chung trong `api`/`queue_worker`, không phải service riêng | Lý do không phải "tiết kiệm một service" mà là: checkpointer PostgreSQL (đã bắt buộc theo domain) đã xoá bỏ **tiền đề duy nhất** từng biện minh cho việc tách riêng (giữ trạng thái trong bộ nhớ) — quyết định không cần đi tới bước so sánh chi phí/lợi ích |

Cả bốn ADR đều bị soi lại theo đúng yêu cầu: "khi mọi quyết định cùng một hướng thì cần kiểm là lập luận hay quán tính." Mỗi ADR nêu **hình dạng tín hiệu đảo ngược** (không phải ngưỡng số, vì A-002 chưa có số liệu tải) và một đoạn Rejected alternatives viết theo lý do riêng của chính nó.

**Phát hiện đáng chú ý ở ADR-005:** điều kiện đảo ngược không dẫn tới "tách `orchestrator` thành service riêng" — nó dẫn tới "đổi tiến trình nào gọi `orchestrator`" (từ luồng request của `api` sang `queue_worker`). Lý do kỹ thuật để tách riêng (giữ trạng thái trong bộ nhớ) không tồn tại ở bất kỳ kịch bản nào trong phạm vi đã biết, kể cả khi giới hạn thời gian request của Render hoá ra thấp.

### `GLOSSARY.md` — mục 11 mới

Chốt tên chuẩn 10 thành phần kiến trúc (`client`, `api`, `ai_gateway`, `orchestrator`, `tool_layer`, `vector_store`, `postgresql`, `object_storage`, `queue_worker`, `observability`) để Phase 3 trở đi dùng đúng tên khi gán agent/tool/node vào từng thành phần.

### `ASSUMPTIONS.md` — A-024, A-025

Hai giả định mới, cùng mẫu owner/hạn đã có từ v0.9: A-024 (nhà cung cấp `object_storage`, owner Product Owner, hạn trước Phase 11); A-025 (giới hạn thời gian request của Render, owner Phase 11/người triển khai, hạn trước khi lên `PRODUCTION`).


---

## 2026-09-12 (lần 3) — Phase 2 v0.2: duyệt ADR, bổ sung NFR-05, neo nghĩa vụ vào Phase 3 và Phase 11

### Duyệt

Anh duyệt **ADR-002, ADR-003, ADR-004, ADR-005** và cách sửa **NFR-05 tại gốc**. Bản ghi đầy đủ của bốn ADR — quyết định, lý do loại riêng của từng cái, điều kiện đảo ngược — và của việc sửa NFR-05 như một hệ quả ngoài dự kiến của vòng A-014 đã nằm ở mục **lần 2** ngay trên. Mục này không chép lại, chỉ ghi phần phát sinh sau khi duyệt.

### 1. NFR-05 — `slot_sensitivity` chuyển chỗ, không mất vai trò (`01-prd.md` v0.8)

Bản sửa ở lần 2 để lại một cách hiểu nguy hiểm: allowlist đã **thay** `slot_sensitivity`. Không phải vậy. Thuộc tính này thôi quyết định cái gì vào prompt, nhưng vẫn là căn cứ duy nhất của ba quyết định khác: mask log kỹ thuật · xoá khi `EXPIRED` · hiển thị trên màn hình duyệt. Như vậy có **hai cơ chế riêng trên cùng một thuộc tính**. Viết rõ để Phase 9 không thiết kế như thể độ nhạy đã bị allowlist thay thế.

Ví dụ chốt được đưa vào NFR-05: `purpose` vừa được allowlist cho vào prompt, vừa bị mask trong log của chính lời gọi đó. Bỏ mask log cho một slot vì nó đã được phép vào prompt là sai.

**Một chỗ mới lộ ra, chưa giải:** quyết định thứ ba — hiển thị trên màn hình duyệt theo độ nhạy — **chưa được đặc tả ở đâu cả**. NFR-05 nêu nó như một việc thuộc Phase 8 và Phase 9, không tự đặt quy tắc.

### 2. Sơ đồ data flow sai cùng kiểu lỗi — phát hiện khi viết mục 1 (`02-architecture.md` v0.2)

Viết xong câu *"allowlist không làm slot bớt nhạy cảm"* thì chính sơ đồ data flow của tôi ở lần 2 vi phạm nó: luồng `ai_gateway` → LLM provider **không bị tô PII**, với lý do *"nó chỉ mang đúng những gì bước đó cần"* — tức là coi allowlist như thứ thay cho độ nhạy. Đã sửa:

- Tô hai mức: **đỏ** cho PII không bị giới hạn theo bước, **cam** cho PII đã được allowlist giới hạn. LLM provider được gọi đúng tên là bên thứ ba.
- **Thêm checkpoint của `orchestrator`** — sơ đồ cũ bỏ sót nó. State LangGraph lưu mọi slot đã thu, nên checkpoint là một kho PII chứ không phải dữ liệu kỹ thuật.
- Thêm `observability` để thấy chỗ hai cơ chế gặp nhau.

**Hệ quả mới phát sinh từ việc thêm checkpoint:** rule xoá slot `RES` khi `EXPIRED` (A-014) phải xoá cả trong checkpoint, **kể cả lịch sử checkpoint các bước trước**. Nếu không, giá trị đã xoá khỏi `request` vẫn còn nguyên trong lịch sử state. Chưa giải ở Phase 2, đã neo vào mục LangGraph design của Phase 3 trong `_PLAN.md`.

### 3. `_PLAN.md` Phase 3 — nghĩa vụ allowlist, neo trước khi chạy

Mọi agent/node gọi LLM phải khai input **đích danh từng slot**. **Cấm khai gộp** ("context của request", "thông tin yêu cầu", `request: Request`), vì khai gộp làm allowlist mất tác dụng mà vẫn trông như tuân thủ. Kèm hai điểm kỹ thuật khiến nghĩa vụ này dễ bị vô hiệu hoá mà không ai để ý:

- LangGraph mặc định truyền **toàn bộ state** vào mọi node, nên allowlist phải thực thi tại điểm lắp prompt trong `ai_gateway`, không đặt ở chữ ký hàm của node được.
- Input **không phải slot** — tin nhắn thô, lịch sử hội thoại, đoạn retrieval — là lỗ lớn nhất của allowlist theo slot. Node phân loại bắt buộc đọc text thô, mà text thô mang được mọi thứ. Phải khai đích danh loại input, phạm vi và loại dữ liệu nó có thể mang theo.

DoD riêng Phase 3 thêm vế tương ứng. Mục LangGraph design của Phase 3 thêm việc xoá slot `RES` trong mọi checkpoint. Phase 7 thêm một dòng trỏ về nghĩa vụ này, vì prompt module thuộc về Phase 7.

### 4. `_PLAN.md` Phase 11 — chỗ quan sát cho điều kiện đảo ngược

Điều kiện đảo ngược không có ngưỡng số là chấp nhận được — bịa ngưỡng còn tệ hơn, cùng lý do đã gỡ EC-WC-04 và ngưỡng 90 ngày. Nhưng một tín hiệu **không có chỗ đo thì không bao giờ phát ra**, và khi đó điều kiện đảo ngược chỉ còn là trang trí. Phase 11 giờ phải có chỗ quan sát cho **sáu tín hiệu vận hành** của ADR-002, ADR-004, ADR-005. Chưa cần ngưỡng — chỉ cần metric **tồn tại**.

**Hai điều kiện đảo ngược không phải tín hiệu vận hành**, nên được tách riêng: ADR-002 xét lại khi A-001 bị bác bỏ; ADR-003 kích hoạt khi A-024 đóng. Hai điều kiện này phát ra khi một giả định đổi trạng thái, không phải khi metric vượt ngưỡng. Chỗ đo của chúng là `ASSUMPTIONS.md`, không phải observability.

**Quy tắc ghi lại cho mọi ADR về sau:** điều kiện đảo ngược phải chỉ ra được chỗ đo nó. Tín hiệu vận hành đo ở observability; tín hiệu nghiệp vụ đo bằng một giả định trong `ASSUMPTIONS.md`.

### Một họ lỗi mới

Mục 3 và mục 4 cùng một họ lỗi: **cơ chế có trên giấy nhưng không bao giờ kích hoạt**. Allowlist khai gộp thì lọc được gì? Không gì cả. Điều kiện đảo ngược không có chỗ đo thì bao giờ phát ra? Không bao giờ. Cả hai đều trông như đã tuân thủ. Họ lỗi này khác với họ *"khoá tham chiếu vào thứ có thể đổi"* ghi ở mục ngày 2026-09-12 phía trên, nên ghi riêng.


---

## 2026-09-12 (lần 4) — Phase 3: Agent & Tool Architecture

**Tạo mới:** `docs/design/03-agents.md` v0.1; `decisions/ADR-006-hai-agent-intake-va-drafting.md`; `decisions/ADR-007-llm-khong-goi-tool.md`; `decisions/ADR-008-state-chi-giu-tham-chieu.md`; `decisions/ADR-009-don-vi-render-lai-la-bien-noi-dung-tu-do.md`; `decisions/ADR-010-resume-graph-qua-job.md`.

**Sửa:** `01-prd.md` → v0.9 · `02-architecture.md` → v0.3 · `00-domain.md` → v0.9 · `GLOSSARY.md` → v0.9 · `ASSUMPTIONS.md` → v0.11 · ADR-002 (sửa lập luận, giữ quyết định).

### Quyết định của phase

| ADR / ID | Quyết định |
|---|---|
| ADR-006 | Hai agent: `intake_agent` (model rẻ, đọc tin nhắn thô) và `drafting_agent` (model mạnh, **cấm** thấy tin nhắn thô). Sau cổng nội dung không có agent |
| ADR-007 | **LLM không tự gọi tool.** Output là JSON có schema đóng; node tất định gọi `tool_layer`. `intake_agent` không sinh văn bản hiển thị cho nhân viên. Prompt injection chỉ còn làm bẩn được một chuỗi JSON |
| ADR-008 | State LangGraph chỉ giữ tham chiếu. Allowlist là **danh sách nạp, fail-closed**: quên khai thì mất chức năng, không rò dữ liệu. Checkpoint không chứa `RES` theo cấu tạo |
| ADR-009 | Đơn vị render lại là **một biến nội dung tự do**; điền template và xuất file luôn chạy lại toàn bộ, 0 token |
| ADR-010 | Resume graph qua job ghi cùng giao dịch với quyết định của người — không để `tool_layer` gọi ngược `orchestrator` |
| INV-01 → INV-03 | Ba bất biến có tên: không LLM sau cổng nội dung · LLM không tự gọi tool · prompt chỉ chứa input được nạp theo khai báo |

### Chuỗi retrieval — kiểm trước khi viết

Kiểm lại theo yêu cầu cho thấy: theo thiết kế Phase 2, `vector_store` là thành phần **đề bài bắt buộc nhưng không có việc**. Chọn template là tra cứu chính xác (F2), kiểm tra điều kiện là rule tất định, và đưa retrieval vào bước soạn thảo làm mất tác dụng trigger của RISK-05. Lập luận chính của ADR-002 — "một nguồn sự thật cho phiên bản template" — sập theo, vì template không bao giờ đi qua vector search.

Xử lý: **retrieval có đúng một việc** — hướng xử lý thủ công có trích nguồn cho yêu cầu ngoài phạm vi, trong `intake_agent` — **kèm cơ chế rơi về tường minh khi kho rỗng**:

- F1 thêm định nghĩa "Hướng xử lý thủ công đủ căn cứ" theo khuôn "không đủ căn cứ thì nói không biết", và AC ngoài phạm vi đúng **trong cả hai trạng thái** của kho.
- Bộ eval thêm nhóm J phủ cả hai nhánh.
- A-027: kho quy trình chưa tồn tại, owner PO, hạn trước Phase 4.

Phương án "retrieval hỗ trợ soạn thảo" bị bác. ADR-002 giữ quyết định `pgvector`, sửa Context, Decision, Consequences, và thêm vào Rejected alternatives một đoạn ghi rõ lập luận cũ **đã sập và từng được viện dẫn nhầm**, để không ai dựng lại.

### Embedding là lời gọi ra ngoài — lỗ của allowlist ngay khi nó ra đời

Luật allowlist lập ở Phase 2 chỉ nói về prompt LLM. Embedding cũng mang văn bản ra ngoài, nên chịu **cùng luật khai input**. Đã sửa `02-architecture.md`: mục `ai_gateway` nêu mọi lời gọi embedding đi qua nó; data flow diagram thêm embedding model (bên thứ ba thứ hai nếu do nhà cung cấp chạy), `chat_message` và `vector_store`; component diagram thêm cạnh `queue_worker → ai_gateway` cho việc nạp kho. Bài học: một luật mới phải được áp ngay vào **mọi lời gọi cùng loại**, không chỉ loại người viết luật đang nghĩ tới.

### Sửa tại gốc theo phép của anh

| File | Sửa gì | Vì sao |
|---|---|---|
| `GLOSSARY.md`, `00-domain.md` | Bỏ "mask prompt gửi LLM theo `slot_sensitivity`" ở mục Enum khác, đoạn độ nhạy và dòng `national_id` | Hệ quả của việc sửa NFR-05 ở Phase 2 chưa được lan tới hai file này |
| `02-architecture.md` sequence (b) | Bỏ `orchestrator → vector_store` và bỏ retrieval khỏi bước soạn thảo; thay bằng `template_fetch` tra cứu chính xác | Trái component diagram, và retrieval không còn thuộc bước soạn thảo |
| `02-architecture.md` sequence (c) | Thêm nhánh `FREE_CONTENT` (`request` ở nguyên `IN_REVIEW`) và `SLOT_DATA` | Q4: tách hai ca theo `change_scope`. Bảng trạng thái ở `00-domain.md` **không** sửa — vẫn đúng |
| `01-prd.md` F1 | Điều kiện 1 cho phép giá trị đề xuất lại từ `request` `EXPIRED` và được xác nhận tường minh; thêm một ca KHÔNG đạt tương ứng | Q2: A-014 giữ dữ liệu với mục đích đỡ gõ lại; giữ mà không dùng là giữ dữ liệu không còn mục đích |

### Bộ eval 31 → 37 ca

| Nhóm | Trước | Sau | Nguồn |
|---|---|---|---|
| D | 3 | 4 | Ca KHÔNG đạt mới của điều kiện 1 ở F1 |
| J — Hướng xử lý thủ công | — | 5 | Bốn ca KHÔNG đạt của định nghĩa mới, cộng một happy path nhánh có kho. Nhánh kho rỗng được phủ bởi ca KHÔNG đạt thứ tư. Chạy trên kho quy trình giả lập, đánh dấu là dữ liệu giả |

Nhóm F chấm việc nhận ra ngoài phạm vi; nhóm J chấm phần hướng xử lý. Tách theo đúng trục "đáp án chuẩn khẳng định cái gì".

### `ASSUMPTIONS.md`

- A-014 mở rộng: `chat_message` xếp `RES` và bị xoá khi `EXPIRED`; khối `INT`/`PER` giữ lại có mục đích; câu hỏi mở về bản giữ sau khi đã đề xuất lại.
- A-022: Phase 3 đã trả lời đơn vị; tách thành hai trần — vòng và token.
- A-023: 37 ca.
- Mới: A-026 (provider LLM) · A-027 (kho quy trình) · A-028 (embedding) · A-029 (`CHANGES_REQUESTED` không có đường sang `EXPIRED`) · A-030 (text search tiếng Việt trên Render) · A-031 (tham số vận hành chưa định cỡ) · A-032 (công cụ chuyển PDF) · A-033 (quyền nạp kho) · A-034 (máy trạng thái `document` thiếu lối ra).

### Chưa sửa — chờ anh

- **Sequence (c) vẽ `tool_layer` gọi `orchestrator`**, ngược chiều component diagram và tạo vòng phụ thuộc. ADR-010 là cách làm không tạo vòng. Nhánh mới thêm vào (c) giữ kiểu mũi tên cũ; vẽ lại cần phép riêng.
- **Lý do hybrid search trong `CLAUDE.md`** ("mã nhân viên và tên riêng") không có đối tượng; kênh lexical có việc khác. Không tự sửa `CLAUDE.md`.
- **A-033** — quyền nạp kho quy trình.


---

## 2026-09-12 (lần 5) — Vòng sửa Phase 3 theo review

Không sang Phase 4. Năm ADR (ADR-006 → ADR-010) được duyệt, quyết định giữ nguyên. `_PLAN.md` giữ Phase 3 ở ☐ cho tới khi anh duyệt diff của vòng này.

### Tiền lệ: "Việc đã làm không xin phép"

Báo cáo Phase 3 xếp ba thay đổi vào mục *"anh chưa cho phép tường minh — cần anh chấp nhận"*, trong khi cả ba **đã được ghi vào file**: cạnh `queue_worker → ai_gateway` trong component diagram, nhãn cạnh checkpoint trong data flow diagram, và mục 1.3 của `02-architecture.md`. Nội dung ba thay đổi được chấp nhận; cách báo cáo thì không.

**Quy tắc từ nay — báo cáo có hai loại mục, không bao giờ trộn:**

| Loại | Điều kiện | Cách viết |
|---|---|---|
| **Đã sửa — xin duyệt sau** | Thay đổi đã nằm trong file | "Đã sửa, đây là diff, xin duyệt" |
| **Cần cho phép trước** | Chưa đụng tới file | "Chưa làm, xin phép" |

Trộn hai loại vào một mục làm người đọc không suy ra được trạng thái thật của repo từ báo cáo. Đây cùng họ lỗi với *"cơ chế có trên giấy nhưng không bao giờ kích hoạt"* ghi ở mục lần 3 phía trên: báo cáo trông như đang xin phép trong khi việc đã làm xong.

#### Bản nới — 2026-09-12 (lần 6)

Những thứ sau tính là **một phần** của sửa đổi đã được duyệt, không phải vượt phạm vi, nên **không** cần xin duyệt riêng:

- nâng số phiên bản ở header của file bị sửa;
- thêm participant, node hay nhãn mà sơ đồ bắt buộc phải có để vẽ được sửa đổi đã duyệt;
- sửa một câu ở file khác đã trở thành **sai** vì chính sửa đổi đã duyệt — ví dụ câu hệ quả của ADR-010 sau khi sequence diagram (c) được vẽ lại.

Chúng **vẫn phải được liệt kê trong diff**, chỉ không xếp vào mục "xin duyệt sau".

Lý do nới: nếu không, mọi báo cáo về sau sẽ ngập mục "xin duyệt sau" bằng những dòng không ai cần đọc, và mục đó mất tác dụng cảnh báo đúng lúc nó cần có tác dụng.

### Tám việc sửa theo review

| # | Việc | File |
|---|---|---|
| B1 | Mục `orchestrator` còn ghi "interrupt tại hai cổng HITL" → sáu điểm `interrupt`, trong đó hai là cổng HITL. Rà cả file: không còn số đếm cũ nào khác | `02-architecture.md` |
| B2 | Chốt **một** nơi cấp số: `finalize_issue`, trong `queue_worker`. `document_issue` chỉ ghi lệnh phát hành. Nhánh `VOIDED` treo ở `finalize_issue`. Việc này đổi hành vi so với sequence diagram (d) — báo cáo, chưa sửa (d) | `03-agents.md` |
| B3 | Thêm cạnh sinh lại sau `validate_free_content` và bảng cạnh điều kiện cho `document_graph`; state thêm `regenerated_variables` | `03-agents.md` |
| B4 | Bỏ `notification_send` khỏi `intake_agent` | `03-agents.md` |
| B5 | Tool Registry thêm mục "Ai được gọi tool nào" với nhóm node tất định sau cổng; rút các tool sau cổng khỏi `drafting_agent`; `document_number_assign` có dòng riêng | `03-agents.md`, `GLOSSARY.md` |
| B6 | Viết lại đúng chiều rủi ro của khoá content-addressed; ràng buộc ghi-một-lần neo vào A-021 | `03-agents.md`, `ASSUMPTIONS.md` |
| B7 | Ràng buộc thứ tự giữa thời hạn đóng phiên và thời hạn `EXPIRED`, không đặt số | `03-agents.md`, `ASSUMPTIONS.md` (A-010, A-014) |
| B8 | Thread kẹt tách khỏi A-034 thành A-035, owner Phase 4; bộ phát hiện thread kẹt thêm dạng (2) | `03-agents.md`, `ASSUMPTIONS.md` |

### Quyết định của anh được nạp

- **C1** — Vẽ lại mũi tên resume ở sequence diagram (c) theo ADR-010: `tool_layer` enqueue job, `queue_worker` resume. Không đụng phần còn lại của (c). Dòng hệ quả tương ứng của ADR-010 cập nhật theo.
- **C2** — Thêm `procedure.manage` vào danh mục permission ở `00-domain.md`, đúng một dòng; tên giữ nguyên vì hợp quy ước `entity.action` với entity viết tắt, như `booking.confirm`, `audit.read_all`. A-033 → `Đã chốt`, kèm lý do.
- **C4** — A-027 không chặn Phase 4, vector collection phải đúng cả khi kho rỗng. A-028: trần chiều `vector(n)`, n ≤ 1024, không `halfvec`; `model_id` và `dimension` là dữ liệu cấu hình; danh sách ứng viên và hai benchmark ghi lại, không chọn. A-030 thêm lối thoát biểu diễn thưa của BGE-M3.
- **D1** — A-036: phạm vi áp dụng của Nghị định 30/2020/NĐ-CP, chỉ ghi tên văn bản.
- **D2** — A-010: tên bốn văn bản cần lấy bản gốc, giữ `[CẦN XÁC MINH]`, không suy ra thời hạn nào.

### Nguồn đã đặt vào `docs/reference/`

`pgvector-dimension-limits.md` — trích nguyên văn README và CHANGELOG của pgvector, ghim theo commit. Một chi tiết lệch với cách diễn đạt trong review: trần 2,000 chiều cho index `vector` có từ bản **0.4.0**, không phải 0.7.0; bản 0.7.0 thêm `halfvec` và việc index `bit`. Con số thì khớp.

Thông số năm model ứng viên và hai benchmark do anh cung cấp **chưa có bản gốc** trong `docs/reference/`, nên được ghi kèm `[CẦN XÁC MINH]` theo cùng quy tắc trích dẫn.

### Hai nhận định sai của tôi được sửa

1. **Rủi ro của `docx_render` (B6).** Báo cáo Phase 3 nói timestamp nhúng trong file làm khoá lệch. Sai chiều: khoá là hash trên input. Rủi ro thật là cùng khoá, khác byte, tức ghi đè. Cùng lỗi đó nằm ở bước 3 của cơ chế INV-01 trong `03-agents.md`, câu "render tất định là điều kiện của bước 2" — đã sửa; bước 2 so giá trị biến, không so file.
2. **Sequence diagram (d).** Open Questions của Phase 3 nói tách phát hành thành lệnh cộng job "không mâu thuẫn về hành vi". Sai: thời điểm và kênh báo lỗi đã khác. Đã ghi lại đúng trong Open Questions.

### Mâu thuẫn mới phát hiện khi sửa — ghi Open Questions, không sửa

- `halt_for_human` ghi lý do dừng vào DB nhưng không tool nào trong registry làm việc đó.
- Nhân viên quay lại trong hạn ở một `chat_session` **mới**: `load_turn` chỉ đọc `request` gắn với phiên hiện tại, nên EC-CV-04 chưa được phủ trong ca này — độc lập với B7, nhưng B7 làm nó lộ ra.
- A-028: "không sửa DDL" chỉ đứng được nếu hiểu là không sửa **định nghĩa cột**; mỗi model vẫn cần một lệnh tạo index.
- `procedure.manage` chưa nằm trong gói vai trò nào.
- Bảng chủ sở hữu chuyển đổi của `document` ở `02-architecture.md` vẫn ghi `ISSUED` do `api`/`tool_layer`; theo B2 thì do `finalize_issue` trong `queue_worker`. Cùng cụm với (d), chưa sửa.

Một mâu thuẫn **đã sửa** ngay trong phạm vi B3: thêm cạnh sinh lại làm sai câu "mọi chu trình trong `document_graph` đều đi qua một `interrupt`" ở Agent Registry. Câu đó giờ nêu ngoại lệ và giới hạn của nó.


---

## 2026-09-12 (lần 6) — Vòng sửa Phase 3, lần 2

Diff lần 5 được duyệt có điều kiện: làm xong sáu việc G dưới đây. `_PLAN.md` giữ Phase 3 ở ☐ cho tới lượt duyệt cuối. Không sang Phase 4.

### Tiền lệ được nới

Bản nới của tiền lệ "Việc đã làm không xin phép" được ghi **ngay dưới tiền lệ cũ**, trong mục lần 5 phía trên, để hai bản đọc liền nhau. Tóm tắt: nâng số phiên bản, thêm participant/node/nhãn mà sơ đồ bắt buộc phải có, và sửa câu ở file khác đã thành sai vì chính sửa đổi đã duyệt — tính là một phần của sửa đổi đã duyệt. Vẫn liệt kê trong diff, nhưng không xếp vào mục "xin duyệt sau".

### Sáu việc G

| # | Việc | File |
|---|---|---|
| G1 | Đặt tên khoảng giữa lệnh phát hành và `ISSUED`: **khoảng hoàn tất phát hành**, cờ dẫn xuất `issue_in_progress` — không phải trạng thái mới; document đứng yên ở `SIGNED`/`SEALED`. Khoảng có hai đoạn: chưa có số, rồi đã có số mà chưa phát hành. Hiển thị giao Phase 8 | `03-agents.md`, `GLOSSARY.md` |
| G2 | Nguyên tử chi phí đổi thành **một lời gọi LLM sinh một biến**. Cận trên (1 + R) × V × 2 × 2 | `03-agents.md`, `ASSUMPTIONS.md` (A-022), ADR-009 |
| G3 | Kiểm lại nguồn trước khi sửa — kết quả **bác lại** nhận định của review (xem dưới). A-028 giữ cách hiểu cũ, ghi rõ chỗ nhận định kia không khớp nguồn; file tham chiếu thêm câu truy vấn mẫu cùng mục FAQ | `ASSUMPTIONS.md`, `docs/reference/pgvector-dimension-limits.md` |
| G4 | A-037: phiên bản pgvector trên Render, owner người triển khai, hạn trước Phase 4 | `ASSUMPTIONS.md`; A-030 và file tham chiếu trỏ sang |
| G5 | Tool `document_halt_record`, đủ chín cột. `halt_for_human` không còn ghi DB ngoài `tool_layer` | `03-agents.md`, `GLOSSARY.md` |
| G6 | Sequence diagram (d): phần phát hành vẽ theo B2 — ghi lệnh, enqueue `finalize_issue`, cấp số trong `queue_worker`. **Nhánh `VOIDED` giữ nguyên.** Phần đóng dấu không đổi. Bảng chủ sở hữu chuyển đổi: dòng `ISSUED` | `02-architecture.md` |

### G3 — nguồn bác lại một nhận định của review

Review cho rằng cột `vector` không khai chiều thì không đánh index được. Mục 4 của `docs/reference/pgvector-dimension-limits.md`, trích nguyên văn README đã ghim, nói khác: cột đó **đánh index được** bằng index biểu thức ép về `vector(n)` cộng điều kiện giới hạn các dòng cùng số chiều, và nguồn có sẵn lệnh mẫu. Nhận định kia đúng ở chỗ không index trực tiếp được cột thô, nhưng bỏ qua đường index biểu thức. Vì vậy A-028 đi theo nhánh (c) của review: giữ cách hiểu "không alter định nghĩa cột", nêu rõ chỗ lệch. Phương án "một collection = một model = một cột `vector(n)`" cũng đứng được; nguồn không bắt buộc cách nào, việc chọn thuộc Phase 4.

### G4 — hai mốc phiên bản, không gộp

Review nói bản pgvector cũ hơn 0.7.0 thì trần 1024 thành ràng buộc cứng. Theo nguồn đã ghim, bản cũ hơn 0.7.0 chỉ mất `halfvec` và việc index `bit`; trần index của `vector` vẫn là 2,000 kể từ 0.4.0. Trần 1024 chỉ thành ràng buộc cứng đúng nghĩa với bản **cũ hơn 0.4.0**. A-037 ghi tách hai mốc.

### G2 — thêm một hệ số ngoài hệ số review nêu

Review nêu hệ số 2 từ lần sinh lại sau khi trượt kiểm. Cùng lập luận áp cho **lần sửa lỗi parse đúng một lần**, đã có trong failure handling của `drafting_agent` từ bản 0.1: mỗi lần sinh — kể cả lần sinh lại — có thể tốn thêm một lời gọi sửa parse. Cận trên vì vậy có hai hệ số 2, không phải một. Cũng ghi rõ số 1 cộng thêm của vòng soạn đầu, và rằng retry do lỗi gọi model nằm ngoài cận. Phần này vượt đúng chữ của G2, nên xếp vào mục "xin duyệt sau" của báo cáo.

### H — không sửa, đã có owner

- **A-038** — hai ràng buộc kéo ngược nhau quanh `chat_session`: ràng buộc thứ tự thời hạn (A-010, A-014) và việc `load_turn` chỉ đọc `request` của phiên hiện tại. Owner Phase 8, cùng cụm A-029.
- **A-039** — `procedure.manage` chưa nằm trong gói vai trò nào. Owner Phase 9.

Hai mục này được ghi thành giả định có owner vì `ASSUMPTIONS.md` là nơi duy nhất giữ owner và hạn của câu hỏi mở; Open Questions của `03-agents.md` trỏ về đó.


---

## 2026-09-13 — Phase 4: Data Architecture

**Tạo mới:** `docs/design/04-data.md` v0.1 · `docs/design/contracts/schema.sql` · `decisions/ADR-011-so-so-bang-dem-giao-dich-ngan.md` · `decisions/ADR-012-mot-collection-mot-cot-vector-co-dinh.md`.

**Sửa:** `00-domain.md` → v0.11 · `02-architecture.md` → v0.6 · `03-agents.md` → v0.4 · `GLOSSARY.md` → v0.12 · `ASSUMPTIONS.md` → v0.14. `_PLAN.md` không đổi — Phase 3 đã ở ☑ từ trước, Phase 4 giữ ☐.

### Tiền lệ: kiểm nguồn trước khi sửa — giữ cho mọi vòng sau

Đã có hai lần một bước kiểm `docs/reference/` **trước khi** sửa theo chỉ thị trả lại kết quả có ích: G3 ở vòng sửa Phase 3 lần 2, và J1(a) ở Phase 4. **Cả hai lần đều bắt được lỗi của chính người ra lệnh.** Lần này, câu "index chỉ tạo được trên cột có số chiều cố định" là suy luận chứ không phải trích dẫn: nguồn nói các dòng cùng số chiều index được bằng index biểu thức cộng index partial. Người ra lệnh sai về cơ chế; kết luận vẫn đứng vì hai lý do khác — phạm vi, và nghĩa vụ phía truy vấn (ADR-012).

**Quy tắc:** chỉ thị nào dựa vào một nguồn thì kiểm nguồn trước, báo kết quả, rồi mới sửa. Bắt được lỗi của người ra lệnh là một kết quả hợp lệ, không phải lệch lệnh.

### Quyết định của phase

| ID | Quyết định |
|---|---|
| ADR-011 | Sổ số: bảng đếm khoá dòng trong một giao dịch cấp số **ngắn, riêng**; không giữ khoá xuyên qua render và upload; định dạng số theo (sổ, dải), chỉ thêm; chuỗi số lưu nguyên; không dùng sequence |
| ADR-012 | Một collection = một model = một cột `vector(1024)` cố định; đổi model là tạo phiên bản collection mới; `dimension` là bản khai, kiểm lúc khởi động; phiên bản đầu không có index ANN |
| J4 | Bất biến bằng `GRANT`/`REVOKE`, role runtime không sở hữu bảng, role migration tách riêng. Không trigger, không row-level security |
| A-021 | Bản render tích luỹ, không đè; ghim bản đã duyệt nội dung và bản phát hành; ghi một lần bằng `stored_object` cộng `stored_object_commit` |
| A-035 | `request_cancel` cộng cạnh `CHANGES_REQUESTED → ARCHIVED`, `archive_reason` bắt buộc |
| J3 | Luật xoá đọc độ nhạy hiện hành; không có cột chụp độ nhạy; nâng lên `RES` xoá hồi tố trên `request` `EXPIRED`, mang nhãn phá huỷ; hạ mức vẫn ghi `audit_event` |
| K3 | Mỗi người thụ hưởng, mỗi loại yêu cầu giữ tối đa một lần thử — thành ràng buộc DB |
| K4 | `expire_request` đóng phiên và enqueue purge trong cùng giao dịch |

### Sửa file phase trước — trong phạm vi anh cho phép

| File | Sửa gì | Phép |
|---|---|---|
| `00-domain.md` | Sơ đồ vòng đời `document`: cạnh `CHANGES_REQUESTED → ARCHIVED`. Định nghĩa `ARCHIVED` viết lại để bao hai đường vào khác loại | K1 |
| `02-architecture.md` | Cùng cạnh trong sơ đồ `document`; dòng `ARCHIVED` của bảng chủ sở hữu chuyển đổi | K1 |
| `03-agents.md` | Thêm dòng `request_cancel` vào bảng thao tác cổng; `ReviewSignal.kind` thêm `REQUEST_CANCELLED`; sơ đồ phần 1 của `document_graph` thêm node kết thúc và cạnh từ `await_resubmission`; bảng cạnh điều kiện và bảng `interrupt` cập nhật tương ứng; điều kiện kết thúc của `document_graph`; ghi chú bộ phát hiện thread kẹt dạng (2); Open Questions mục 7 | K1, J2 |
| `03-agents.md` | Ba câu đã thành **sai** vì K3 và K4 đã duyệt — mục Checkpointer và PII, câu hỏi mở ở mục Dùng lại giá trị từ lần thử `EXPIRED`, bước 7 của mục Khi `request` `EXPIRED` — cùng Open Questions mục 6 | Bản nới F3 |
| `GLOSSARY.md` | Mục 1: sáu entity mới. Mục 5: ghi chú `ARCHIVED`. Mục 8: enum `decision_kind`, mã `archive_reason`. Mục 10: trỏ tới bảng ánh xạ. Mục 12: `request_cancel`, `object_claim_reconcile`, `slot_sensitivity_change`, ba loại job, bảng thực thể tầng kỹ thuật | J2, P1, K1 |
| `ASSUMPTIONS.md` | A-021 và A-035 → `Đã chốt`; A-010, A-014, A-028, A-030, A-037, A-038 cập nhật; thêm A-040 → A-045 | O2–O4, J1(e), K3, K4 |

### Đã sửa — xin duyệt sau (vượt đúng chữ của chỉ thị)

1. **`document_free_content.template_version_id`** — lỗ tìm thấy khi kiểm P5: `document.template_version_id` đổi được giữa các vòng, nên thiếu cột này thì không dựng lại được danh sách input của một lần sinh.
2. **`request.opened_by_message_id`**, `UNIQUE` — idempotency của `request_open` chốt ở Phase 3 cần một chỗ bám trong DB.
3. **`decision_record` loại `SUBMITTED`** cho lần gửi đầu, để mỗi thao tác cổng ghi đúng một `decision_record`.
4. **Tách hai cặp bảng:** `decision_record_text` khỏi `decision_record`, và `stored_object_commit` khỏi `stored_object`. Mỗi cặp giải một xung đột: bất biến đối với xoá được, và ghi một lần đối với việc cần một lần commit.
5. **Kiểm lại checksum lúc ghim** — lớp thu hẹp rủi ro còn lại của ca cùng khoá khác byte.
6. **Phiên bản collection đầu không có index ANN** (ADR-012).
7. **`room_booking` chống trùng lịch bằng khoá dòng `room`**, không bằng exclusion constraint.

### Phát hiện mới — ghi Open Questions, không tự sửa

- **A-038:** bất đẳng thức thời hạn ở A-010 không còn cần cho bảo đảm thứ tự, vì bảo đảm đã đứng bằng sự kiện. Phase 8 quyết.
- **A-044:** khoá idempotency của `document_halt_record` gộp nhầm hai lần dừng sau tiếp quản.
- **A-042:** luồng cấu hình `request_type` của F6 chưa có permission.
- **`_PLAN.md`:** bảng chỗ quan sát của Phase 11 thiếu tín hiệu đảo ngược của ADR-011 và ADR-012.
- **A-009 và A-036** có hạn "trước Phase 4" và vẫn `Mở`. Thiết kế Phase 4 không phụ thuộc giá trị của chúng; hạn đã qua.

### Chưa chạy thử

`schema.sql` **chưa được chạy trên một PostgreSQL thật**: Docker có trên máy nhưng daemon không chạy. Đã parse bằng parser của PostgreSQL (thư viện `libpg-query`, cài tạm trong scratchpad): 113 câu lệnh, không lỗi cú pháp. Parse **không** kiểm ngữ nghĩa — đích của khoá ngoại, quy tắc của cột generated, quyền — nên những thứ đó chỉ được bảo đảm khi chạy trên một instance thật (cùng lượt với A-040).


---

## 2026-09-13 (lần 2) — Vòng duyệt Phase 4: S–V

Phase 4 được duyệt có điều kiện. Làm xong S–V, `_PLAN.md` chuyển Phase 4 sang ☑. Anh duyệt cả bảy mục "đã sửa — xin duyệt sau" của mục lần 1 (S1), và duyệt hướng bất biến bằng quyền DB, hai cặp bảng tách, quy tắc domain đứng bằng khoá ngoại ghép (S2).

### Sửa theo từng file

| File | Sửa gì | Mục |
|---|---|---|
| `_PLAN.md` | Bảng chỗ quan sát của Phase 11 thêm hai dòng: chờ khoá trên bộ đếm sổ số (ADR-011), latency truy hồi đặt cạnh số chunk (ADR-012). Phase 4 → ☑. Không đụng phần nào khác | S3, W |
| ADR-012 | Viết lại lý do, quyết định giữ nguyên. Cột cố định là ràng buộc **đề phòng**: việc chính của nó chưa có hiệu lực vì chưa có index ANN. Có tín hiệu kích hoạt index. A-037 chỉ cứng kể từ lúc có index. Có câu chống việc gỡ ràng buộc. Nói thẳng rằng lý do loại Option A cũng nhìn về lúc có index | T1 |
| ADR-003 | Hai câu đã thành sai vì T2: câu hệ quả "không phụ thuộc vendor", và chữ "nên" thành "phải" ở điều kiện đảo ngược | T2, bản nới F3 |
| `ASSUMPTIONS.md` → v0.15 | A-024 viết lại thành ràng buộc mua sắm. A-037 sửa lý do. A-038 ghi phương án có giá, đủ hai vế. A-009 và A-036 có hạn cứng "Trước Phase 7", kèm ghi nhận hạn cũ đã trượt. Thêm A-046 (exclusion constraint cho `room_booking`) và A-047 (`schema.sql` chưa từng chạy — điều kiện chặn) | T1–T4, U4, U5 |
| `04-data.md` → v0.2 | Mục 1.1 có lý do tách cho mọi dòng nhiều bảng, cộng câu độ phủ 45 bảng. Mục 1.5 mới: phép thử enum xuyên phase. Mục 3.8: ràng buộc bù cho `graph_thread`. Mục 3.9: thiết kế đích và thiết kế tạm. Mục 4.4 mới: khoảng hoàn tất phát hành. Mục 5.4: ca đồng bộ duy nhất, và A-024. Mục 6: A-037 và tín hiệu ANN. Mục 8.5 trỏ về A-038. Open Questions cập nhật | T1–T4, U1–U5, V1, V3 |
| `schema.sql` | Thêm index `ix_register_entry_issue_decision`; chú thích `room_booking` ghi thiết kế tạm | V1, T3 |
| `03-agents.md` → v0.5 | Danh sách ngoại lệ đóng, ghi ngay tại chỗ phát biểu luật ở mục Tool Registry | U1 |
| `02-architecture.md` → v0.7 | Câu "`orchestrator` không tự ghi PostgreSQL" đã sai với bảng checkpoint và `graph_thread` — nay trỏ tới danh sách ngoại lệ | U1, bản nới F3 |
| `GLOSSARY.md` → v0.13 | Định nghĩa `graph_thread` thêm ràng buộc bù | U1 |

### Ba xác nhận (V)

- **V1 — chưa có trước vòng này.** Bản 0.1 chỉ nói `issue_in_progress` là cờ dẫn xuất, không nói dẫn xuất từ đâu. Mục 4.4 nay ghi cách dẫn xuất từ `decision_record`, `document_register_entry` và `document_halt`. Không thêm cột; thêm một index.
- **V2 — có từ bản 0.1.** `ck_document_archive_reason_abandoned_draft` buộc `archive_reason` không rỗng khi `archived_from_status = 'CHANGES_REQUESTED'`. Đó là một `CHECK` có điều kiện, không phải `NOT NULL` trên cột, vì đường vào `ARCHIVED` thứ nhất không bắt buộc lý do.
- **V3 — đủ 45 bảng.** Không bảng nào đứng ngoài ánh xạ. Năm dòng nhiều bảng trước đây thiếu lý do tách; nay đã có.

### Một chỗ lệch nhẹ với chỉ thị T1

T1 nói cột cố định "hôm nay không gánh gì". Kiểm lại thì nó gánh **một việc nhỏ**: cho bước kiểm lúc khởi động một con số thật trong DDL để so với bản khai `dimension`. Việc chính của nó — index được mà không phải migrate cột — đúng là chưa có hiệu lực. ADR-012 ghi cả hai. Cột cố định có từ chối vector sai chiều lúc ghi hay không là hành vi thư viện nằm ngoài nguồn đã ghim — `[CẦN XÁC MINH]`, không được tính là lý do.

### Cần anh cho phép trước — chưa làm

- **Thêm việc kiểm lại checksum của bản đã ghim `APPROVED_CONTENT` vào hợp đồng của `signing_route`** ở mục Tool Registry của `03-agents.md` (U3). Có phép này thì không lần kiểm checksum nào nằm trong luồng request đồng bộ. Chưa có phép thì lần kiểm của lần ghim thứ nhất vẫn là thứ duy nhất có thể chạm A-025.

### Phát hiện mới

- **Câu dẫn của khối chỗ quan sát trong `_PLAN.md` vẫn ghi "ADR ở Phase 2"**, dù bảng nay có dòng của ADR-011 và ADR-012. Không sửa: phép S3 chỉ phủ cái bảng.
- **Ba tham chiếu nội bộ trong `04-data.md` trỏ nhầm "mục 6.4"** cho phần lọc quyền theo phòng ban, vốn nằm ở mục 6.3. Lỗi của tôi ở bản 0.1, đã sửa.


---

## 2026-09-13 (lần 3) — Tool `render_integrity_check`

Anh cho phép chuyển việc đọc lại object để kiểm checksum của bản đã ghim `APPROVED_CONTENT` ra khỏi luồng request đồng bộ, sang phía sau cổng 1, kèm mã lỗi dẫn tới `halt_for_human`.

**Cách viết lý do — theo chỉ thị, không phải một cách lách A-025.** Người duyệt nội dung duyệt **giá trị biến** (INV-01); người ký đặt chữ ký lên **byte**. Toàn vẹn byte vì vậy được kiểm ngay trước người đầu tiên dựa vào byte. Việc nó rời luồng đồng bộ là hệ quả của vị trí đúng.

**Chọn (a) — tool riêng, không gộp vào `signing_route`.** Bốn lý do, ghi ở mục Tool Registry của `03-agents.md`:
1. `signing_route` có đúng một việc.
2. Cùng phép kiểm cần ở hai chỗ, `route_signing` và `finalize_issue`.
3. Hai lớp timeout khác nhau.
4. Hai loại lỗi đòi hai cách tiếp quản khác nhau.

| File | Sửa gì |
|---|---|
| `03-agents.md` → v0.6 | Mục 5.1: dòng `render_integrity_check` đủ chín cột, cộng đoạn "nằm ở đâu, và vì sao là tool riêng". Mục 5.4: dòng mới trong bảng ai gọi tool nào. Bước 3 của `finalize_issue` và nhánh `VOIDED` nhắc tới phép kiểm. Sơ đồ phần 2 của `document_graph`: nhãn `route_signing` và cạnh tới `halt_for_human`. Bảng cạnh điều kiện. Danh sách tool cấm của `drafting_agent` |
| `GLOSSARY.md` → v0.14 | Mục 12: `render_integrity_check` trong nhóm node tất định sau cổng |
| `04-data.md` → v0.3 | Mục 5.4: lý do vị trí, hệ quả cho luồng đồng bộ, số phận của `document` sau khi trượt kiểm. Open Questions mục 10 đóng |
| `ASSUMPTIONS.md` | A-025: lo ngại cho biện pháp này đã hết, và vì sao |

Sơ đồ, bảng cạnh điều kiện, bước của `finalize_issue` và danh sách tool cấm của `drafting_agent` được sửa theo bản nới F3: không sửa thì chúng thành thiếu hoặc sai so với tool mới.

Không đổi máy trạng thái: trượt kiểm thì `document` đứng yên ở trạng thái lúc kiểm. Cách tiếp quản sau khi trượt kiểm thuộc Phase 8, cùng bảng mã lý do dừng.


---

## 2026-09-13 (lần 4) — Phase 5: API Spec

**Tạo mới:** `docs/design/05-api.md` v0.1 · `docs/design/contracts/openapi.yaml` · `decisions/ADR-013-sse-tin-hieu-va-session-cookie.md` · `decisions/ADR-014-tai-file-qua-api.md`.

**Sửa:** `03-agents.md` → v0.7 · `GLOSSARY.md` → v0.15 · `ASSUMPTIONS.md` → v0.16. `_PLAN.md` và `02-architecture.md` không đổi; Phase 5 giữ ☐.

### Ràng buộc cho Phase 6 — đọc trước khi thiết kế cấu trúc dự án

**`client` phải được phục vụ cùng origin với `api`.** Cookie `SameSite=Strict` cộng header `X-BO19-CSRF` của ADR-013 chỉ đứng khi hai bên cùng origin. Điều này thu hẹp lựa chọn "phục vụ tĩnh hoặc build riêng" ở mục Ánh xạ sang đơn vị triển khai trên Render của `02-architecture.md`: build riêng thì vẫn phải được phục vụ dưới cùng origin với `api`. Theo chỉ thị, `02-architecture.md` không sửa ở phase này; ràng buộc sống ở Consequences của ADR-013 và ở dòng này. Hai subdomain mặc định của Render có cùng site hay không: A-049.

### Tiền lệ: lỗi tiền đề của một ADR bị bắt trước khi viết

Bước lập kế hoạch viết "`EventSource` không gửi được header, nên phải dùng cookie", và chỉ thị ADR-013 được dựng trên câu đó. Rà lại trước khi viết cho thấy câu đó **không ép được quyết định** — stream lượt chat đã là `POST` đọc bằng `fetch`, nên bearer token vẫn làm được — và bản thân nó là kiến thức nền tảng web viết từ trí nhớ. ADR-013 giữ quyết định cookie nhưng thay lý do, theo thứ tự: credential ngoài vùng JS đọc được; một cơ chế xác thực cho REST và hai stream; tự nối lại của `EventSource` chỉ là lý do phụ, gắn A-051.

Cùng họ với tiền lệ "kiểm nguồn trước khi sửa" ở mục Phase 4. Khác ở chỗ lần này lỗi nằm ở chính người đề xuất, và nó đã đi vào chỉ thị trước khi bị bắt.

### Quyết định của phase

| ID | Quyết định |
|---|---|
| ADR-013 | Hai stream SSE tách riêng: stream lượt chat — response của `POST`, sống một lượt, bản có thẩm quyền là `chat_message`; và stream tín hiệu — `GET` dài, chỉ mang "chủ đề X có thay đổi", không id sự kiện, không `Last-Event-ID`. Phát hiện thay đổi bằng **số đếm** (`notification`) và **dấu vân tay** (`id`, `row_version`), không bằng timestamp. Session cookie `HttpOnly`, `SameSite=Strict`, header `X-BO19-CSRF` |
| ADR-014 | Tải file đi qua `api`: kiểm quyền tại lúc tải, so checksum trước byte đầu tiên, ghi `audit_event`. Không dùng URL ký sẵn |
| Idempotency | `Idempotency-Key` bằng uuid của dòng chính mà lệnh ghi tạo ra. Khi trùng, kiểm đúng ba điều — cùng tác nhân, cùng đối tượng, cùng loại thao tác. Lệch thì 409 và **không** trả nội dung dòng. Không so payload: lần ghi đầu thắng |
| Thời gian chờ của F4 | Định nghĩa bằng `status_changed_at`, không bằng `due_at` đang để trống; hàng đợi duyệt dùng cột của `document` |
| `request_type.manage` | Tên cho endpoint cấu hình loại yêu cầu; từ chối mọi người; **không** vào danh mục permission cho tới Phase 9 |
| Mã lỗi nội bộ | Không bao giờ ra khỏi `api`. Bảng lộ/không lộ ở mục Mã lỗi của `05-api.md` |

### Sửa file phase trước — trong phạm vi anh cho phép

| File | Sửa gì | Phép |
|---|---|---|
| `03-agents.md` | Mục 5.4 mới: thao tác `request_slot_confirm`, nhóm thứ ba cạnh thao tác cổng và thao tác vận hành | B2 (c) |
| `03-agents.md` | Mục 5.4 và 5.5 cũ đánh số lại thành 5.5 và 5.6; bảy tham chiếu nội bộ trỏ theo | Bản nới F3 — hệ quả trực tiếp của việc chèn mục |
| `03-agents.md` | `request_slots_write`: bỏ nhánh `(tên slot, hành động xác nhận)` khỏi input; cột Mục đích bỏ "ghi xác nhận" | B2 (a); cột Mục đích theo bản nới F3 |
| `03-agents.md` | Mục 7.3 bước 3 trỏ sang `request_slot_confirm` | B2 (b) |
| `03-agents.md` | Failure handling của `intake_agent`: "không đổi dữ liệu nghiệp vụ", đúng một `chat_message` của agent mang mã khuôn lỗi, ba cái cấm | Mục 5 của phản hồi |
| `03-agents.md` | Câu liệt kê các nhóm thao tác ở cuối mục "Ai được gọi tool nào", và bảng ánh xạ sang thành phần kiến trúc: thêm nhóm mới | Bản nới F3 |
| `GLOSSARY.md` | Mục 8: mười sáu enum nâng từ `04-data.md`, cộng một dòng chờ Phase 8. Mục 12: hai nhóm thao tác mới. Mục 13 mới: tên của API | D |
| `ASSUMPTIONS.md` | A-025, A-031, A-038 bổ sung. **A-042 nâng lên mức chặn nghiệm thu.** Thêm A-048 → A-054 | B1, B3, C, và các phát hiện dưới đây |

**Hai chỗ phải kiểm theo chỉ thị B2:**

- *Mã lỗi nào của `request_slots_write` chỉ phục vụ nhánh xác nhận:* **không có**. Cả bốn mã — `EVIDENCE_MISMATCH`, `RULE_FAILED`, `NOT_EDITABLE`, `SLOT_NOT_ALLOWED` — đều phục vụ việc ghi giá trị.
- *`PendingQuestion.kind = CONFIRM_PROPOSALS` có còn đúng không:* **còn đúng**. Agent vẫn là bên hỏi, không còn là bên ghi. State có thể cũ sau thao tác xác nhận; node đầu của lượt sau đọc lại DB, nên không cần sửa mục State schema. Một câu nói điều này nằm trong mục 5.4 mới.

### Đã sửa — xin duyệt sau (vượt đúng chữ của chỉ thị)

1. **Failure handling thêm một câu về những gì đã ghi trước lỗi.** Ba cái cấm đúng với nhánh lỗi, nhưng `open_request` chạy trước `extract_slots`: lượt lỗi ở `extract_slots` đã có một `request` vừa tạo. Câu thêm nói những ghi đó đứng nguyên, không hoàn tác, và idempotent theo tin nhắn. Không có câu này thì câu mới bị đọc thành lời hứa hoàn tác.
2. **`request_slot_confirm` đưa `NEEDS_INFO → DRAFT` khi hàm kiểm đạt.** Không có bước này thì nhân viên xác nhận xong vẫn kẹt ở `NEEDS_INFO`, vì `request_submit` chỉ nhận `DRAFT`, và phải gõ thêm một lượt chat chỉ để graph chuyển trạng thái.
3. **Mười ba thao tác của `tool_layer` được đặt tên** ở mục Endpoint của `05-api.md` và mục Agent, graph, node, tool của `GLOSSARY.md`. Luật "mọi ghi đi qua `tool_layer`" cộng danh sách ngoại lệ đóng buộc mỗi lệnh ghi do endpoint gây ra phải có tên; không có tên thì Phase 13 không truy vết được.
4. **Khi trùng khoá idempotency, tác nhân được đọc từ `audit_event` của lần tạo** nếu bảng không có cột người thực hiện — ví dụ `template`.

### Phát hiện mới — ghi `ASSUMPTIONS.md`, không tự sửa

- **A-052** — nhập hộ chưa đi được hết đường: không thao tác nào đặt người thụ hưởng khác người tạo cho `WORK_CONFIRMATION`; và người thụ hưởng không phải người tạo thì không xem được yêu cầu của chính mình.
- **A-053** — bảng nghĩa `CANCELLED` ở `00-domain.md` rộng hơn sơ đồ.
- **A-054** — không thao tác nào đưa `document` sang `SUPERSEDED`.
- **A-048 → A-051** — credential; cùng site trên domain Render; stream qua proxy của Render; hành vi nền tảng web và framework mà contract dựa vào.
- Không có ràng buộc một phiên `OPEN` cho mỗi nhân viên — ghi thêm vào A-038.
- Hai thứ tự không có index: `GET /requests?scope=ALL` — AC Must của F4 — và `GET /issue-queue`. Đề xuất `ix_request_waiting` và `ix_document_awaiting_issue` ở Open Questions của `05-api.md`; **không** thêm vào `schema.sql`.

### Cần anh cho phép trước — chưa làm

- Thêm hai dòng vào bảng chỗ quan sát của Phase 11 trong `_PLAN.md`: tải poll tín hiệu (ADR-013), và phân phối thời lượng tải file (ADR-014).
- Thêm mười ba thao tác đặt tên ở Phase 5 vào mục Tool Registry của `03-agents.md`, nếu anh muốn đó là bản kê đầy đủ.
- Bảng chủ sở hữu chuyển đổi của `request` ở `02-architecture.md` ghi `DRAFT` do `orchestrator` sở hữu; nay `request_slot_confirm` cũng đưa `NEEDS_INFO → DRAFT`.

### Đã kiểm

- `openapi.yaml` qua `openapi-spec-validator` 0.9.0 (OpenAPI 3.1.0): đạt.
- Đối chiếu tự động `05-api.md` ↔ `openapi.yaml`: 48 endpoint có contract khớp đúng 48 operation; bốn endpoint `[NGOÀI-OPENAPI]` không lọt vào `openapi.yaml`; 31 mã lỗi khớp; mọi lệnh ghi có header CSRF, khai `x-bo19-execution` và `x-bo19-idempotency-key`; operation khai khoá thì có header `Idempotency-Key`, và ngược lại.
- Sơ đồ Mermaid duy nhất của `05-api.md` render được bằng mermaid-cli 10.9.1.
- Tham chiếu chéo file theo số mục trong các file mới và file đã sửa: không có.
- **Chưa kiểm:** contract chưa chạy trên server nào — chưa có code (DESIGN MODE). Mọi hành vi nền tảng mà contract dựa vào nằm ở A-049 → A-051.


---

## 2026-09-13 (lần 5) — Vòng duyệt Phase 5: A, B, C

Anh duyệt Phase 5 có điều kiện. **Phase 5 giữ ☐**: hai mục dừng lại đúng theo điều kiện dừng anh đặt — nửa credential của B2, và B3. `_PLAN.md` chỉ thêm hai dòng chỗ quan sát.

**Sửa:** `05-api.md` → v0.2 · ADR-013 · ADR-014 · `03-agents.md` → v0.8 · `02-architecture.md` → v0.8 · `GLOSSARY.md` → v0.16 · `ASSUMPTIONS.md` → v0.17 · `_PLAN.md` (hai dòng). `openapi.yaml`, `schema.sql`, `00-domain.md`, `01-prd.md`, `04-data.md` không đổi.

### Ràng buộc cho Phase 6 — thay dòng cùng tên ở mục lần 4

**`client` được `api` (FastAPI) phục vụ tĩnh, dưới chính origin của `api`** (B1). Không còn là "build riêng thì vẫn phải cùng origin": đã chọn hẳn phục vụ tĩnh. Ba hệ quả, ghi ở Consequences của ADR-013: bản build được đóng gói cùng Web Service của `api`; đường dẫn của SPA không chồng lên tiền tố `/api`; cold start của `api` giờ cũng là cold start của trang. A-049 → `Đã chốt`, bằng quyết định chứ không bằng xác minh.

### A — duyệt

- **A1.** Bốn mục "đã sửa — xin duyệt sau" của mục lần 4 được duyệt.
- **A2.** Làm đủ ba việc: hai dòng ADR-013, ADR-014 vào bảng chỗ quan sát của Phase 11 trong `_PLAN.md`; mục Thao tác do endpoint gọi của `03-agents.md` liệt mười ba thao tác, đặt ở cuối mục Tool Registry để không phải đánh số lại lần thứ hai; dòng `DRAFT` ở bảng chủ sở hữu chuyển đổi `request` của `02-architecture.md`.
- **A3.** Dòng "openapi khớp 100%" ở bảng tự kiểm DoD là **✔ có điều kiện**, không phải ✔. Chữ của `_PLAN.md` là "khớp 100% với tài liệu"; phạm vi khớp đã được **định nghĩa lại** thành 48 endpoint có contract (mục Nguyên tắc chung của `05-api.md`). Việc loại bốn endpoint `ROOM_BOOKING` là một quyết định, được anh duyệt ở mục 4 của phản hồi trước — không phải một phép kiểm đạt.

### B — quyết định của anh

| Mục | Kết quả |
|---|---|
| B1 | Áp đủ. ADR-013, `05-api.md`, A-049 |
| B2 | **Áp nửa phiên:** phiên không lưu DB; cookie mang token ký bằng secret phía server, stateless; mỗi request đọc lại `employee.is_active` và permission; không thu hồi được phiên đơn lẻ, ghi thẳng ở `05-api.md` và ADR-013. Phiên lưu ở `postgresql` vào Rejected alternatives của ADR-013. **Nửa credential DỪNG, không vá:** "cột hash trong CSV import, buộc đổi ở lần đăng nhập đầu" đụng năm chỗ, ghi ở A-048 — cần cột mới trong `employee` (`schema.sql` đã đóng, A-047); cờ buộc đổi là một cột nữa; đổi mật khẩu là lệnh ghi cần tên và `audit_event` (A-055); import CSV ghi đè sẽ ghi đè mật khẩu đã đổi; khoá sau nhiều lần sai cần nơi lưu |
| B3 | **DỪNG, không cắt.** Theo quy ước ở đầu `00-domain.md`, hạng mục không mang nhãn là Sprint đầu; `request.create_on_behalf`, slot `beneficiary_employee_id` khi đặt khác người tạo, và EC-IL-01 đều không mang nhãn. Ở PRD, điều kiện 4 của định nghĩa "Yêu cầu đủ điều kiện xử lý" nằm trong AC của F1 (Must), và EC-IL-01 là một ca của nhóm E trong bộ eval — nhóm do M6, metric loại Bất biến, chấm. Cắt nhập hộ là đổi đáp án chuẩn của một ca trong cổng nghiệm thu. Không sửa file nào cho B3 |
| B4 | Chọn **đường (i)**: thêm `request_type.manage` vào danh mục permission; owner Phase 9; hạn cứng — Phase 9 không được duyệt khi chưa thêm. Đường (ii) — sửa điều 4 của Definition of Done — bị loại, kèm lý do ở A-042 |

### C — phải sửa

- **C1.** A-055 mới: luật "mọi thao tác ghi sinh `audit_event`" kéo ngược định nghĩa `audit_event` với tin nhắn chat và lượt tải file; kèm hệ quả thứ hai — dòng ứng dụng không xoá được, chạm A-010 và dung lượng. Owner Phase 8. Không giải.
- **C2.** Đề xuất `ix_audit_event_entity ON audit_event (entity_type, entity_id)` ở Open Questions của `05-api.md`; **không** thêm vào `schema.sql`. Kiểm thêm thấy **hai** bảng rơi vào ca này, không phải một: `template`, và `delegation` `[Should]` — người lập uỷ quyền có thể không phải người trao quyền. Nêu một cách rẻ hơn, không cần index: lấy `Idempotency-Key` bằng id của `audit_event` của lần tạo, như `POST /employee-imports`. **Chưa áp** — đổi contract.
- **C3.** Kết luận: không vi phạm **chữ** của NFR-06 — chữ nói về trần token, trần render và `document` dở dang — nhưng là cùng loại hỏng. A-056 mới, owner Phase 8. Câu "mọi lượt kết thúc bằng đúng một tin nhắn của agent" ở `05-api.md` sửa thành có điều kiện, và nêu đích danh ca phá nó.
- **C4.** Chưa có ở đâu. Thêm vào Consequences của ADR-013: quy tắc mượn rồi trả ngay, pool cạn thì bỏ lượt; bảng công thức bậc độ lớn N × q ÷ T, N × S ÷ T, (N × q ÷ T) × d — không có số. Dòng ADR-013 ở `_PLAN.md` quan sát cả số connection bị vòng poll chiếm. A-057 mới cho trần pool của Render.

### Lỗi trong phép kiểm của chính tôi — sửa ở vòng này

- Câu "tham chiếu chéo file theo số mục: không có" ở mục lần 4 **chưa được kiểm thật**: mẫu glob sai, không khớp file nào, nên phép quét trả rỗng. Quét lại đúng trên toàn bộ `docs/design`: còn một chỗ do tôi viết trong mục lần 4 — một tham chiếu tới `GLOSSARY.md` bằng số mục thay vì tên mục — đã sửa sang tên mục. Hai chỗ khác nằm ở các mục cũ hơn của file này, giữ nguyên vì không viết lại lịch sử.

### Đã kiểm

- `openapi.yaml` qua `openapi-spec-validator`: đạt. Đối chiếu tự động với `05-api.md`: 48/48 endpoint, 31/31 mã lỗi, không endpoint `[NGOÀI-OPENAPI]` nào lọt vào — sau vòng sửa này.
- Tham chiếu chéo file theo số mục: như trên.
- Diff của riêng vòng này lấy bằng cách so với bản chụp `docs/design/` trước khi sửa, vì cả Phase 5 chưa commit.


---

## 2026-09-13 (lần 6) — Vòng duyệt Phase 5, lần 2: D, E, F

**Phase 5 giữ ☐ — đúng một mục hở: E2(b).** Mọi mục khác của D, E, F đã xong.

**Sửa:** `05-api.md` → v0.3 · `contracts/openapi.yaml` · ADR-013 · `GLOSSARY.md` → v0.17 · `ASSUMPTIONS.md` → v0.18 · hai câu ở mục lần 5 của file này. **Không đổi:** `_PLAN.md`, `00-domain.md`, `01-prd.md`, `02-architecture.md`, `03-agents.md`, `04-data.md`, `schema.sql`, ADR-014.

### D — duyệt

D1 → D5 được duyệt: nửa phiên của B2 giữ nguyên; cách đọc hạn ở B4 giữ làm cổng, không đổi owner; A-056 giữ; phát hiện `delegation` ở C2 được nhận; các mục sửa theo bản nới F3 được duyệt.

### Đã làm theo chỉ thị

| Mục | Kết quả |
|---|---|
| E1 (a) | Credential ở **bảng riêng**, tên dự kiến `employee_credential`, do Phase 9 thêm bằng migration. Không cột nào vào `employee`, không DDL, không sửa `schema.sql`. Hình dạng và ràng buộc ghi ở A-048 |
| E1 (b) | A-048 ghi: bảng riêng thì import CSV không bao giờ chạm credential — và đó là **lý do chính** chọn bảng riêng |
| E1 (c) | Khoá sau nhiều lần sai không thuộc Sprint đầu. `INVALID_CREDENTIALS` đồng nhất; không có `ACCOUNT_LOCKED`. Ghi ở A-048 và mục Nguyên tắc chung của `05-api.md` |
| E1 (d) | Buộc đổi mật khẩu lần đầu không thuộc Sprint đầu. Mật khẩu ban đầu do thao tác vận hành seed, giao ngoài hệ thống. Giới hạn và rủi ro ghi ở A-048 |
| E1 (e) | Mục Nguyên tắc chung và bảng phiên đăng nhập ở mục Endpoint của `05-api.md` đã nói đúng: `DELETE /auth/session` chỉ xoá cookie phía client. **Nhưng `openapi.yaml` nói sai:** response 204 ghi "Đã huỷ phiên" — đã sửa. A-048 ghi "không thu hồi được phiên đã cấp trước khi hết hạn" là rủi ro có chủ, owner Phase 9 |
| E1 — kết | A-048: owner Phase 9, hạn trong Phase 9, **gỡ nhãn chặn Phase 6** |
| E2 (a) | Nhập hộ **giữ** trong Sprint đầu. Không file nào phải đổi — chưa file nào từng cắt nó. Quyết định ghi ở A-052 |
| E2 (c) | Phương án định nghĩa lại `request.read_own` ghi ở A-052, **chưa áp**. Hệ quả với quy tắc tách biệt trách nhiệm: không đổi quy tắc chặn. Ba chỗ phải đi theo nếu áp. Owner: Product Owner quyết, Phase 9 thực thi. Hạn: trước Phase 6 |
| F1 | Chạy lại toàn bộ phép kiểm tự động, mỗi phép in số đối tượng đã quét — mục Đã kiểm dưới đây |
| F2 | Đề xuất câu chữ cho luật mới của `CLAUDE.md` — dưới đây. **Không** sửa `CLAUDE.md` |
| F3 | Ngoại lệ idempotency tường minh cho `POST /employee-imports`, `POST /templates`, `POST /delegations` — mục Nguyên tắc chung của `05-api.md`, dòng `Idempotency-Key` của `GLOSSARY.md`, `openapi.yaml`. Đề xuất `ix_audit_event_entity` chuyển thành phương án bị loại, kèm hai lý do |

### Mục hở — E2(b), dừng đúng theo điều kiện anh đặt

Kiểm hai câu của chỉ thị với `00-domain.md` trước khi ghi. **Cả hai vướng:**

1. Cắt nhập hộ cho `WORK_CONFIRMATION` thì câu "người có `request.create_on_behalf` được đặt khác" ở bảng slot của loại đó thành sai. Theo quy ước ở đầu `00-domain.md`, câu không mang nhãn là Sprint đầu. Không tự chỉnh `00-domain.md`.
2. Câu "`INTRODUCTION_LETTER` không bị ảnh hưởng, đường đã có" chỉ đúng một nửa. Slot `bearer_employee_code` trích được, nhưng **không tool nào ghi `request.beneficiary_employee_id`** từ nó — vế (2) của A-052. Hệ quả nặng hơn bản trước ghi: cột người thụ hưởng vẫn bằng người tạo, nên phép kiểm tách biệt trách nhiệm (D-006) chặn nhầm người tạo, và để lọt người mang giấy nếu chính người đó duyệt.

Đề xuất cắt hẹp được ghi ở A-052 **như một đề xuất đang dừng**, không phải một quyết định.

### Đã sửa — xin duyệt sau

1. **A-048 — ai ghi bảng credential:** thao tác seed chạy bằng role sở hữu, cùng loại với việc nạp `employee_role`; `bo19_app` chỉ đọc. E1 chỉ nói "thao tác vận hành seed"; phần role là tôi chọn, để ứng dụng không có lệnh ghi credential nào và không chạm A-055.
2. **ADR-013 — một lý do loại phương án đã thành sai sau E1(a).** Phương án "phiên lưu ở `postgresql`" từng bị loại một phần vì "`schema.sql` đã đóng", nhưng E1(a) nay cho Phase 9 thêm bảng credential. Viết lại: lý do loại là mỗi lần đăng nhập, đăng xuất thành một lệnh ghi của ứng dụng — chạm A-055 — không phải việc thêm bảng. Theo bản nới F3.
3. **A-052 vế (2) — thêm hệ quả với D-006** (chặn nhầm, để lọt), tìm thấy khi kiểm E2(b).
4. **Hai câu ở mục lần 5 của file này sửa theo luật 12.** Một câu trỏ `03-agents.md` bằng số mục. Câu kia trích lại chính chỗ phạm luật, nên phép quét cũng bắt.
5. **Mục lần 5 ghi "hai chỗ khác nằm ở các mục cũ" — sai về số lượng.** Đó là kết quả của mẫu quét hẹp; mẫu mở rộng thấy **14** dòng cũ. Không sửa câu cũ, ghi đính chính ở đây.
6. **Chính mục này phạm luật 12 lúc mới viết**, ở hai ô E1 (c) và E1 (e) — cả hai trỏ `05-api.md` bằng số mục. Bắt được nhờ chạy lại phép quét **sau** khi ghi. Ô E1 (e) còn lộ một điểm yếu của phép quét cũ: nó bỏ sót chữ "Mục" viết hoa và câu có chữ chen giữa số mục và tên file. Đã sửa cả hai ô, và đổi phép quét sang mẫu rộng. Con số ở mục Đã kiểm dưới đây là của mẫu rộng.

### Cần cho phép trước — chưa làm

- **E2(b):** hoặc cho phép gắn nhãn câu ở bảng slot `WORK_CONFIRMATION` của `00-domain.md` rồi mới cắt; hoặc bỏ đề xuất cắt.
- **A-052 vế (1) và (2):** một thao tác có tên ghi `request.beneficiary_employee_id` — cần phép sửa `03-agents.md`. Việc này **cần dù có cắt hay không**, vì E2(a) giữ nhập hộ cho `INTRODUCTION_LETTER`.
- **A-052 vế (3):** định nghĩa lại `request.read_own` — cần phép sửa danh mục permission ở `00-domain.md`.
- **Luật mới cho `CLAUDE.md`** — anh tự dán. Đề xuất, đặt sau luật 12 ở mục Luật viết tài liệu:

> 13. **Phép kiểm tự động phải in số đối tượng đã quét.** Mọi khẳng định "đã kiểm" dựa trên một phép kiểm tự động — validator, script đối chiếu, grep, render sơ đồ — phải kèm số đối tượng mà phép đó đã quét: số file, số dòng, số endpoint, số mã, số sơ đồ. **Phép kiểm quét 0 đối tượng là ✘, không phải ✔**, kể cả khi nó không báo lỗi nào. Phép kiểm không in ra được con số đó thì coi như chưa chạy, và không được ghi vào báo cáo như đã đạt.

### Đã kiểm — F1, kèm số đối tượng

| Phép kiểm | Số đã quét | Kết quả |
|---|---|---|
| `openapi-spec-validator` 0.9.0 trên `openapi.yaml` (OpenAPI 3.1.0) | 44 path · 48 operation · 122 schema · 17 parameter · 12 response | Đạt |
| Endpoint có contract của `05-api.md` ↔ operation của `openapi.yaml` | 48 ↔ 48 | Đạt — không thiếu, không thừa |
| Endpoint `[NGOÀI-OPENAPI]` không lọt vào `openapi.yaml` | 4 | Đạt |
| Mã lỗi của `05-api.md` ↔ enum `ErrorCode` | 31 ↔ 31 | Đạt |
| Từng operation: header CSRF, `x-bo19-execution`, khoá idempotency khớp header, lỗi qua response chuẩn | 48 | Đạt |
| Response lỗi dùng `ErrorEnvelope` có đủ `error_code`, `message`, `trace_id` | 11 | Đạt |
| Ngoại lệ idempotency đúng ba endpoint đã liệt kê | 3 | Đạt |
| Tham chiếu chéo file theo số mục, trên toàn bộ `docs/design` — mẫu rộng, không phân biệt hoa thường, cho phép chữ chen giữa | 24 file · 6.581 dòng | 17 dòng trúng, **không dòng nào trong nội dung Phase 5.** 14 ở các mục cũ của file này, giữ nguyên. 2 trúng nhầm: `00-domain.md` và `05-api.md` trỏ số mục nội bộ đứng trước tên file của một cụm khác. 1 có từ trước Phase 5: dòng A-018 của `ASSUMPTIONS.md` trỏ tới `00-domain.md` bằng số mục — để Phase 13 |
| Mermaid trên toàn bộ `docs/design`, render bằng mermaid-cli 10.9.1 | 23 sơ đồ trong 5 file | 23 render, 0 lỗi, 23 SVG trên đĩa |

Lần chạy đầu của phép kiểm tổng **không in được bảng kết quả** — console dùng mã cp1252, không in được chữ tiếng Việt. Theo F1, lần đó coi như chưa chạy; bảng trên là của lần chạy lại với đầu ra UTF-8.


---

## 2026-09-13 (lần 7) — Đóng Phase 5: H, I, J

**Phase 5 → ☑ trong `_PLAN.md`.** Không sang Phase 6; Phase 6 mở bằng một phiên mới.

**Sửa:** `ASSUMPTIONS.md` (A-048, A-052) · `05-api.md` → v0.4 · `_PLAN.md` (Phase 5 ☑) · file này. Toàn bộ mục I chỉ chạm `ASSUMPTIONS.md`, `05-api.md` và file này (I6). **Không đổi:** `00-domain.md`, `03-agents.md`, danh mục permission, `openapi.yaml`, `schema.sql`, mọi ADR.

### H — duyệt năm mục "xin duyệt sau" của mục lần 6

- **H1** — seed credential bằng role sở hữu, `bo19_app` chỉ đọc: duyệt. A-048 ghi thêm hệ quả: ở Sprint đầu, đổi mật khẩu — kể cả đặt lại cho người quên — là **thao tác vận hành**, không phải tính năng của ứng dụng, vì `bo19_app` không có quyền ghi bảng credential. Cùng khuôn với việc xoá theo hạn lưu trữ ở mục Audit log bất biến của `04-data.md`.
- **H2, H3, H4** — duyệt.
- **H5** — duyệt. Mẫu quét đang dùng ghi ở dưới.
- **H6** — duyệt. **Nói thẳng: chưa có phép kiểm tự động nào bắt được loại lệch "contract máy đọc nói khác tài liệu".** `check_all.py` so tập endpoint, tập mã lỗi, các extension `x-bo19-*` và cấu trúc response lỗi. Nó không so nghĩa của `description` hay `summary` trong `openapi.yaml` với văn xuôi của `05-api.md`. Lỗi "Đã huỷ phiên" được bắt bằng đọc tay khi làm E1(e). Không thêm phép kiểm ở phase này.

### Mẫu quét luật 12 đang dùng — H5

Ghi mẫu, không chỉ kết quả, để lần sau kiểm lại được chính phép kiểm. Phép quét này đã sai hai lần: lần một do glob có ngoặc nhọn không khớp file nào, nên trả rỗng; lần hai do mẫu chỉ bắt chữ "mục" viết thường đứng liền trước "của".

- **Phạm vi:** mọi file `*.md` dưới `docs/design`, đệ quy — `glob(ROOT + '**/*.md', recursive=True)`. Phép quét phải in số file và số dòng đã quét; 0 file là hỏng, không phải đạt.
- **Mẫu** — Python `re`, cờ `re.IGNORECASE`:

```
mục [0-9]+(\.[0-9]+)*[^|;]{0,60}(của|ở) `?(0[0-9]-|PRD|GLOSSARY|ASSUMPTIONS|CLAUDE|_PLAN)|(PRD|0[0-9]-[a-z-]+\.md`?) mục [0-9]
```

- **Mọi dòng trúng được phân loại bằng tay**, ba nhóm: vi phạm thật; trúng nhầm — số mục nội bộ của chính file đứng trước tên file thuộc một cụm khác trong cùng câu; lịch sử — mục cũ của file này, không viết lại.
- **Giới hạn đã biết:** không bắt tham chiếu theo số mục tới ADR, `openapi.yaml` hay `schema.sql`; không bắt câu có dấu `|` hoặc `;` chen giữa số mục và tên file.

### I — E2(b): bỏ đề xuất cắt

| Mục | Kết quả |
|---|---|
| I1 | Bỏ đề xuất cắt nhập hộ cho `WORK_CONFIRMATION`. Không gắn nhãn, không sửa `00-domain.md`, `03-agents.md` hay danh mục permission. Ba phép từng xin không được cấp, và không xin lại |
| I2 | A-052 viết lại đủ ba vế, `Mở`, owner Phase 8 |
| I3 | A-052 nâng lên mức **chạm cổng nghiệm thu**, cùng cách A-042 đã được nâng; lý do EC-IL-01 → nhóm E → M6 → metric loại Bất biến. Ghi cả ở Open Questions của `05-api.md` |
| I4 | Câu riêng: phép tách biệt trách nhiệm đang **sai theo hai chiều**, không phải đang thiếu — chặn nhầm người tạo, để lọt người mang giấy nếu chính người đó duyệt. Có ở A-052 và ở `05-api.md` |
| I5 | Hai phương án cho Phase 8, là đề xuất, mỗi phương án một câu lý do và một câu cái giá. Phương án (b) kèm dòng: index theo `beneficiary_employee_id` kiểm ở Phase 8, không đề xuất ở Phase 5 |

### Đã sửa — xin duyệt sau

1. **I3 — chữ "không đạt được đúng căn cứ" thay cho "không thể đạt".** Đối chiếu cơ chế thì câu "không thể đạt" mạnh hơn điều chứng minh được. Điều kiện 4 của F1 không bao giờ nhận ra nhập hộ, vì cột người thụ hưởng luôn bằng người tạo. Nhưng ca vẫn có thể được chấm đạt qua một đường khác — `employee_lookup` chặn trước — và chính phép chặn đó cũng mơ hồ. Mức nâng không đổi.
2. **I2 — hạn viết thành cổng**, cùng cách A-042: "Phase 8 không được duyệt khi A-052 chưa giải". Chỉ thị ghi "owner Phase 8, hạn trước Phase 8" — cùng kiểu tự mâu thuẫn mà D2 đã giải cho A-042.
3. **I5(a) — ghi rằng phương án (a) không giải vế (1).** Chỉ thị không nêu; không ghi thì (a) trông như giải cả hai vế.
4. **Dòng nhập hộ ở mục Không có endpoint vì chưa có thao tác của `05-api.md`** — câu cũ chỉ nói `WORK_CONFIRMATION`, thành thiếu sau I2. Sửa theo bản nới F3, trong phạm vi file I6 cho phép.
5. **Bản đầu của mục 4 ngay trên phạm luật 12** — nó trỏ `05-api.md` bằng số mục. Đây là lần thứ ba tôi phạm luật này trong chính đoạn ghi về việc sửa nó. Bắt được ở lần quét chạy sau lần ghi, như J yêu cầu; đã sửa sang tên mục.

### Cần cho phép trước — chưa làm

**Không có.** Dòng A-018 trỏ theo số mục để Phase 13, theo chỉ thị.

### Đã kiểm

Theo J, các phép kiểm chạy **sau** lần ghi cuối — tức sau chính mục này — nên số liệu nằm ở báo cáo đóng phase, không ở đây.


---

## 2026-09-13 (lần 8) — Phase 6: Project Structure

**Tạo mới:** `docs/design/06-structure.md` v0.1 · ADR-015 → ADR-019 · năm file nguồn trong `docs/reference/`: `langgraph-checkpoint-postgres.md`, `starlette-streaming-disconnect.md`, `web-platform-sse-cors-samesite.md`, `render-deploys-docker.md`, `libreoffice-headless-convert.md`.

**Sửa:** `02-architecture.md` → v0.9 · `03-agents.md` → v0.9 · `04-data.md` → v0.4 · `05-api.md` → v0.5 · `GLOSSARY.md` → v0.18 · `ASSUMPTIONS.md` → v0.19 · `_PLAN.md` (một dòng) · `contracts/schema.sql` · `contracts/openapi.yaml`. **Không đổi:** `00-domain.md`, `01-prd.md`, ADR-001 → ADR-014, `CLAUDE.md`. Phase 6 giữ ☐.

### Thứ tự làm — theo chỉ thị

1. **Câu 4 trước:** tải tài liệu gốc, áp `schema.sql`, kiểm phủ định.
2. ADR-019 và phần sửa 02, 03, 04, GLOSSARY.
3. `06-structure.md`.
4. ADR-015 → ADR-018.
5. `ASSUMPTIONS.md`, file này, `_PLAN.md`.

### Câu 4 — xác minh

- **Tài liệu gốc lấy bằng `curl`, không bằng bản tóm tắt.** Công cụ tải web trả về bản tóm tắt do một model nhỏ viết, và một bản tóm tắt của Fetch Standard đã lẫn hai khái niệm khác nhau. Mọi trích dẫn ghim vào `docs/reference/` là nguyên văn từ file gốc, đầu file ghi URL, ngày lấy và phiên bản.
- **`schema.sql` áp trên PostgreSQL 16.2 cùng pgvector 0.6.2 — không qua Docker.** Docker Desktop trên máy không khởi động được: engine WSL không đọc được đĩa dữ liệu của nó. Sửa đĩa đó là thao tác phá huỷ trên dữ liệu Docker của anh, nên không làm. Dùng gói Python `pgserver` 0.1.4 trong một venv của scratchpad; không cài gì vào hệ thống. Bản build là Windows; Render chạy Linux.
- **Kết quả:** 45 bảng; **169** phép kiểm phủ định bị từ chối đúng, **63** phép khẳng định đúng, **0** lệch so với nhóm quyền của `04-data.md`; giao dịch `READ ONLY` chặn cả lệnh mà role có quyền. Chi tiết và bảng giới hạn ở mục Xác minh contract của `06-structure.md`.
- **Ba phát hiện thật:** `bo19_migrator` không tạo được extension `vector` → A-040 vế (3). `setup()` của checkpointer không chạy được trong giao dịch → trình tự ở ADR-017. `bo19_app` không tự chạy `setup()` được → runtime không bao giờ gọi nó.
- **Phát hiện từ mã nguồn LangGraph 1.2.11:** exception của node được lưu vào checkpoint. Lớp 2 ở mục Checkpointer và PII của `03-agents.md` từng đoán đúng rủi ro này nhưng chỉ chặn lỗi của `tool_layer`. `06-structure.md` thêm biên node. Ghi vào `03-agents.md` cần phép — Open Questions của `06-structure.md`.

### Phép của anh và phần đã làm

| Phép | File | Sửa gì |
|---|---|---|
| Câu 1 | ADR-019 | Tạo mới, **Accepted**. Ngoại lệ hẹp: `ai_gateway` ghi đúng một bảng, `llm_usage`. Ràng buộc bù; không `audit_event`; phương án "`ai_gateway` gọi `tool_layer`" loại tường minh; ba ca fail-closed viết đủ |
| Câu 1 | `03-agents.md` | Danh sách ngoại lệ đóng: hai → ba mục; "thêm mục thứ ba phải có ADR" → "thêm mục thứ tư phải có ADR" |
| Câu 1 | `02-architecture.md` | Cạnh `AIGateway -->|chi llm_usage| PostgreSQL`; câu ngoại lệ có tên ở dòng "Không thuộc" của `ai_gateway`, chữ cũ giữ nguyên |
| Câu 1 | `04-data.md` | Câu "Ai ghi `llm_usage`" theo đúng khuôn của `graph_thread` |
| Câu 1 | `GLOSSARY.md` | Dòng `llm_usage`: một trong ba ngoại lệ |
| Câu 2 | ADR-015, `04-data.md`, `schema.sql` | Manifest font đi kèm `template_version`; bước kiểm khởi động của `queue_worker` chặn khi thiếu font; mục PDF không tất định |
| Câu 2 | `ASSUMPTIONS.md` | A-058, owner Product Owner — cùng owner với mẫu `.docx` |
| Câu 3 | `06-structure.md` | Chỉ tài liệu; `.importlinter` và `Dockerfile` là khối đặc tả; công cụ ranh giới frontend là ESLint |
| Câu 4 | `docs/reference/`, `06-structure.md`, `ASSUMPTIONS.md` | Mục Câu 4 ở trên |
| Câu 5 | ADR-015, `_PLAN.md` | Một image; lý do đổi sang "đơn giản, ít đường lệch phiên bản" — không dùng ADR-005; cái giá cold start ghi rõ; một dòng chỗ quan sát của Phase 11 |
| Sửa bắt buộc (1)–(8) | `06-structure.md`, ADR-016, ADR-017, ADR-018 | Bảng "thứ gì chặn vi phạm"; bước kiểm khởi động mười lăm mục; thứ tự migration so với checkpointer; tên role đúng `schema.sql`, không role thứ ba; ba hệ quả của ADR-016; `try_acquire`; bốn điểm của ADR-018; chỗ của `observability` và hàm mask |

### Đã sửa — xin duyệt sau (vượt đúng chữ của chỉ thị)

1. **Mã `BUDGET_UNAVAILABLE`** thêm vào `ck_llm_usage_outcome` của `schema.sql` và câu "Ai ghi" ở `04-data.md`. Chỉ thị viết "nếu cần mã mới thì đó là migration cộng sửa `04-data.md`, phải nói rõ". Cần: `BUDGET_EXCEEDED` sai nghĩa cho ca DB hỏng, và sẽ trộn tỷ lệ DB hỏng vào tỷ lệ chạm trần mà Phase 11 dùng để định cỡ A-022. Vì `schema.sql` chưa từng áp lên môi trường nào ngoài phép thử local, "migration" ở đây là sửa chính file DDL ban đầu.
2. **Manifest font kéo theo contract API.** Không có đường nào đưa `required_fonts` vào thì cột luôn rỗng. Đã thêm `manifest.required_fonts` và response `TemplateVersion.required_fonts` ở `openapi.yaml`; mã lỗi mới `TEMPLATE_FONTS_INVALID` với mã con `NOT_IN_MANIFEST` · `NOT_INSTALLED`; response 422 cho endpoint kích hoạt; dòng ở mục Endpoint và mục Mã lỗi của `05-api.md`. Danh mục `error_code`: 31 → 32. Có thêm `CHECK (cardinality(required_fonts) >= 1)`.
3. **Chốt font rộng hơn chữ của chỉ thị.** Chỉ thị viết "các phiên bản template đang hiệu lực". Bước kiểm khởi động phủ thêm mọi phiên bản mà một `document` chưa tới trạng thái kết thúc đang dùng, vì `finalize_issue` render bằng đúng phiên bản đã duyệt, mà phiên bản đó có thể đã `RETIRED`. Thêm hai chốt: lúc tải lên và lúc kích hoạt. Chốt lúc kích hoạt đóng lỗ "kích hoạt phiên bản mới khi worker đang chạy" — bước kiểm khởi động không thấy lỗ đó.
4. **ADR-015 chọn (b), kèm một thứ tự mà chỉ thị không nêu:** chuyển đổi xong **rồi mới** giành khoá. Lease vì vậy phải phủ **thời lượng upload**, không phải "thời lượng chuyển đổi" như chỉ thị viết — cửa sổ ghi đè chỉ mở khi một lệnh upload đang bay. A-059 mang số đo của cả hai.
5. **ADR-019 đính chính hai câu của chỉ thị.** (a) Ràng buộc bù "đã được `CHECK` bảo chứng" đúng với tập cột, nhưng `prompt_module_version` và `trace_id` là hai cột `text` không có `CHECK` hình dạng — ghi thẳng là chỗ hở. (b) Phương án "`ai_gateway` gọi `tool_layer`" hôm nay phá contract **độc lập** giữa hai module, chưa phải vòng phụ thuộc theo nghĩa đen; nó thành vòng ngay khi một phần của `tool_layer` cần `ai_gateway`. Kết luận loại không đổi.
6. **Hệ quả trực tiếp của ADR-019 ở hai chỗ ngoài danh sách phép:** câu `graph_thread` của `04-data.md` và dòng `graph_thread` của `GLOSSARY.md` đang ghi "hai ngoại lệ". Để nguyên thì mâu thuẫn với chính phần sửa được phép.
7. **Kết quả xác minh A-045 thay chữ `[CẦN XÁC MINH]`** ở câu `graph_thread` và mục Vòng đời checkpoint của `04-data.md`, kèm trích dẫn nguồn. Không đổi thiết kế.
8. **Đoạn điều kiện chặn A-047 trong Open Questions của `04-data.md`** ghi trạng thái mới.
9. **A-050 trượt hạn** "Trước Phase 6" mà không đóng — ghi nhận, hạn mới chờ anh chốt.
10. **`persistence.probe`** — phép thử quyền khởi động cần giao dịch thường; trong giao dịch `READ ONLY`, PostgreSQL báo lỗi chỉ đọc trước khi kiểm quyền. Contract `write-path` cấm `startup` dùng lối ghi, nên thêm một lối thử riêng, luôn rollback, và một contract chặn mọi module khác import nó. Bắt được khi đọc lại chính `06-structure.md`.

### Phát hiện mới — ghi `ASSUMPTIONS.md` hoặc Open Questions, không tự sửa

- A-055, trường hợp thứ ba: giành, gia hạn lease và kết thúc job là ghi `postgresql` không phải nghiệp vụ. Tạm không sinh `audit_event` — lệch có tên.
- Chưa có thao tác nào có tên đóng `chat_session` vì nhàn rỗi.
- Bảng sổ migration `schema_migration` nằm ngoài `schema.sql`, chưa có dòng ở mục Nguyên tắc dữ liệu của `04-data.md`.
- A-059 (thời lượng upload, cho lease), A-060 (ngữ cảnh chạy `migrate`).

### Cần anh cho phép trước — chưa làm

Bốn mục đầu ở Open Questions của `06-structure.md`: dòng `schema_migration` ở `04-data.md`; biên node vào `03-agents.md` cộng ca canary; mã `FONT_MISSING` cho `pdf_export`; dòng chỗ quan sát thứ hai của ADR-015.

### Đã kiểm

Theo quy ước của mục lần 7: phép kiểm chạy **sau** lần ghi cuối, số liệu nằm ở báo cáo đóng phase.


---

## 2026-09-13 (lần 9) — Vòng duyệt Phase 6: A → F. Đóng Phase 6

Hoàn tất ngày 2026-09-14. **Phase 6 → ☑ trong `_PLAN.md`.** Phase 7 mở bằng một phiên mới.

**Sửa:** `05-api.md` → v0.6 · `03-agents.md` → v0.10 · `04-data.md` → v0.5 · `06-structure.md` → v0.2 · ADR-015 · `ASSUMPTIONS.md` · `_PLAN.md` (hai dòng chỗ quan sát, Phase 6 ☑). **Tạo mới:** `tools/contract-checks/` — `check_grants.py`, `requirements.txt`, `README.md`. **Không đổi:** `openapi.yaml`, `schema.sql`, `GLOSSARY.md`, ADR-016 → ADR-019, `CLAUDE.md`.

### A — mục SSE của `05-api.md` theo ADR-016

Chưa sửa ở Phase 6: đọc lại, cả hai câu còn nguyên chữ của Phase 5. Đã sửa trong phạm vi phép:

- Câu "Framework có huỷ xử lý khi client ngắt… Phase 6 phải bảo đảm điều này" → trỏ ADR-016.
- Câu hạn chót của lượt: bỏ mệnh đề "lượt chạy bên trong request", **bỏ cận dưới** "không ngắn hơn A-025", giữ một cận trên duy nhất của ADR-016. Ghi vai trò mới của A-025: chỉ cắt stream, không cắt lượt.
- **Hai câu cùng giả định, cùng file, tìm thấy khi quét:** ca phá bất biến "framework huỷ xử lý khi client ngắt kết nối" ở cùng mục SSE; và dòng `SYNC_GRAPH` ở bảng đồng bộ hay enqueue của mục Nguyên tắc chung. Cả hai đã sửa.
- **Cùng cận dưới ở `ASSUMPTIONS.md`:** A-025 — câu Phase 5 và ô "Ảnh hưởng nếu sai" — và A-031. Đã sửa, vì để nguyên thì mâu thuẫn vẫn sống ở sổ giả định.

**Câu còn giả định lượt chạy trong request, ngoài phạm vi phép — chưa sửa:** dòng "Chạy ở" của `intake_agent` và dòng độ trễ ở bảng năng lực model, mục Agent Registry của `03-agents.md` · ADR-005 (Decision, Consequences, điều kiện đảo ngược) · ADR-006 (câu về nơi chạy) · ADR-008 (điều kiện đảo ngược) · ADR-013 (Context, phương án C) · dòng ADR-005 ở bảng chỗ quan sát của Phase 11 trong `_PLAN.md`. Ghi ở Open Questions của `06-structure.md`.

### B — bốn phép, làm theo thứ tự B2 → B1, B3, B4

| # | Kết quả |
|---|---|
| B2 | Lớp 2 ở mục Checkpointer và PII của `03-agents.md` đổi thành "exception rời node chỉ mang mã", kèm lý do và nguồn; lớp 3 thêm ca canary bắt buộc thứ hai — node ném exception mang giá trị `RES` |
| B1 | Dòng `schema_migration` ở mục Nguyên tắc dữ liệu của `04-data.md` |
| B3 | `FONT_MISSING` ở dòng `pdf_export`: **mã nội bộ của tool**, dẫn tới `halt_for_human`. Danh mục `error_code` giữ **32**; `openapi.yaml` **không đổi**. Cùng ô: "Công cụ chuyển đổi chưa chọn (A-032)" đã cũ, thay bằng trỏ ADR-015 |
| B4 | Dòng chỗ quan sát thứ hai của ADR-015 — phần đuôi thời lượng upload đặt cạnh lease |

### C — chốt font số 2 phụ thuộc quyết định một image

Viết vào chính điều kiện đảo ngược "Đóng gói" của ADR-015: tách image thì chốt 2 mất; `FONT_MISSING` theo từng job chuyển thành **bắt buộc**; tách image mà không bật nó là hạ một lớp phòng thủ mà không ai quyết. Quyết định của ADR-015 không đổi.

### D — ba việc

- **D1:** A-050 — hạn "ngay khi có môi trường Render đầu tiên", owner người triển khai. Dòng ADR-013 · A-050 ở bảng chỗ quan sát của Phase 11: một phép thử tổng hợp từ ngoài Render đo thời gian tới sự kiện `signal` đầu tiên.
- **D2:** chấp nhận kết quả pgserver. Không sửa Docker. A-047 giữ "thu hẹp — đã áp trên PostgreSQL 16.2, chưa áp trên Render".
- **D3:** bộ kiểm ở `tools/contract-checks/` — ngoài `backend/` nên không vào image, ngoài `docs/` để contract giữ dạng khai báo. Hai chế độ `--local` và `--app-dsn`; thêm kiểm độ phủ nhóm quyền. **Căng thẳng với mục Chế độ làm việc hiện tại của `CLAUDE.md`**, vốn cấm "test chạy được" ở DESIGN MODE: đặt script vào repo theo chỉ thị D3, rằng script kiểm contract không phải mã ứng dụng. Ghi ra để không ai coi đây là tiền lệ cho test ứng dụng.

### E — danh sách "chặn Phase 7" dựng lại theo phạm vi Phase 7 ở ADR-001

| Mã | Trước | Sau |
|---|---|---|
| A-018 | Hạn "Trước Phase 7" | **Không có hạn, không chặn phase nào** — `Mở` vĩnh viễn theo thiết kế |
| A-009 | "Trước Phase 7 — Phase 7 dựng template" | Trước khi hệ thống sinh văn bản thật — cụ thể trước lần cấp số đầu tiên, kể cả dải `TRIAL` ở UAT. Lý do cũ trái ADR-001 |
| A-036 | Như A-009 | Trước khi hệ thống sinh văn bản thật, và trước mọi đề xuất tháo chế độ phi sản xuất |
| A-058 | "Trước Phase 7, cùng hạn với mẫu `.docx`" | Trước lần render đầu tiên, kể cả bản thử nghiệm ở UAT |
| A-026 | "Trước Phase 7" | Không chặn Phase 7 — đường vòng: khai theo năng lực bắt buộc, JSON Schema đóng độc lập provider, ép JSON viết cho hai nhánh năng lực |

**Kết luận: Phase 7 không bị chặn.**

### F — luật 13

Anh tự dán vào `CLAUDE.md`. Không sửa `CLAUDE.md`.

### Đã kiểm

Chạy sau lần ghi cuối của mục này; số liệu ở báo cáo đóng phase.


---

## 2026-09-14 — Sau vòng duyệt Phase 6: phép bổ sung

Phase 6 giữ ☑. Anh cho phép hai việc còn treo ở báo cáo đóng phase.

**Sửa:** `05-api.md` → v0.7 · `03-agents.md` → v0.11 · `02-architecture.md` → v0.10 · `06-structure.md` → v0.3 · ADR-005, ADR-006, ADR-008, ADR-013 (dòng **Cập nhật** ở đầu mỗi file, quyết định giữ nguyên) · `_PLAN.md` (dòng ADR-005 ở bảng chỗ quan sát). **Không đổi:** `openapi.yaml`, `schema.sql`, `GLOSSARY.md`, `ASSUMPTIONS.md`, `CLAUDE.md`.

### 1. `FONT_MISSING` ở bảng "mã lỗi của tool" của `05-api.md`

Thêm vào dòng có `pdf_export`, cột "Không qua `error_code`". Danh mục `error_code` giữ 32 mã; `openapi.yaml` không đổi.

### 2. Mười một dòng còn giả định lượt chạy trong request, cộng một dòng mơ hồ

| File | Chỗ | Sửa thành |
|---|---|---|
| `03-agents.md` | Dòng "Chạy ở" của `intake_agent` | Gọi từ tiến trình `api`, ở task tách khỏi vòng đời request |
| `03-agents.md` | Dòng độ trễ ở bảng năng lực model | Mốc là hạn chót của lượt, không phải A-025 |
| ADR-005 | Decision, Consequences, điều kiện đảo ngược (bốn câu) | Nơi gọi là tiến trình `api`; tín hiệu đảo ngược đo bằng shutdown delay, không bằng A-025; câu cũ giữ trong ngoặc nghiêng làm dấu vết |
| ADR-006 | Câu về nơi chạy | Task trong tiến trình `api` |
| ADR-008 | Điều kiện đảo ngược | Mốc là hạn chót của lượt |
| ADR-013 | Context, lý do loại phương án C | Lượt chạy trong tiến trình giữ response; lý do loại không đổi |
| `_PLAN.md` | Dòng ADR-005 ở bảng chỗ quan sát | Thành dòng ADR-005 · ADR-016, đặt cạnh hạn chót và shutdown delay |
| `02-architecture.md` | Mục `orchestrator`, dòng "Công nghệ" | **Quyết định thêm vào danh sách:** "lượt chat đồng bộ" không sai hẳn, nhưng là câu duy nhất ở mục đó nói lượt chạy ở đâu, dễ đọc thành "trong request". Sửa tốn một cụm từ |

Không đổi quyết định nào của các ADR. Dòng **Cập nhật** ở đầu file theo tiền lệ "Sửa lập luận" của ADR-002 và ADR-012.

### Đã kiểm

Chạy sau lần ghi cuối của mục này; số liệu ở báo cáo.

---

## 2026-09-14 — Phase 7: Prompt Architecture

**Tạo mới:** `docs/design/07-prompts.md` v0.1. **Không đổi:** `00-domain.md`, `01-prd.md`, `02-architecture.md`, `03-agents.md`, `04-data.md`, `05-api.md`, `06-structure.md`, `GLOSSARY.md`, `ASSUMPTIONS.md`, `contracts/schema.sql`, `contracts/openapi.yaml`, ADR-001 → ADR-019, `CLAUDE.md`. `_PLAN.md` Phase 7 → ☑.

### Quyết định của phase

Không có ADR mới. Thiết kế dựa trên ADR-007 (LLM không gọi tool), ADR-008 (allowlist là danh sách nạp, fail-closed), ADR-009 (đơn vị render lại là biến), ADR-016 (lượt chat tách khỏi kết nối).

| Prompt | Quyết định |
|---|---|
| P1 `classify_intent` / P2 `extract_slots` / P3 `select_procedure_passages` (intake, tier rẻ) | Input đích danh theo `03-agents.md:102`, output JSON đóng `additionalProperties: false`, không sinh văn bản hiển thị — `render_reply` lắp khuôn |
| P4 `draft_free_content` / P5 `revise_free_content` (drafting, tier mạnh) | Một biến một lời gọi, input `template_variable_input` của `template_version`, `change_reason` là dữ liệu RES chỉ tới biến trong `change_targets` |
| Ép JSON | Hai nhánh theo năng lực provider (A-026): provider hỗ trợ JSON Schema thì ép native, không thì `ai_gateway.json_contract` validate + sửa parse đúng 1 lần |

### Phạm vi đã chốt

Prompt chỉ sinh nội dung tự do (`purpose_statement`, `work_content_statement` — `GLOSSARY.md:325`); khung thể thức trong `template .docx` do PO chuẩn bị (ADR-001, D-007) **không** thuộc Phase 7. Mọi few-shot đánh dấu **dữ liệu giả**.

### Đã kiểm

Theo quy ước của mục lần 7: phép kiểm chạy **sau** lần ghi cuối, số liệu nằm ở báo cáo đóng phase.

---

## 2026-09-14 — Phase 8: HITL & Approval Workflow

**Tạo mới:** `docs/design/08-hitl.md` v0.1. **Không đổi:** `00-domain.md`, `01-prd.md`, `02-architecture.md`, `03-agents.md`, `04-data.md`, `05-api.md`, `06-structure.md`, `07-prompts.md`, `GLOSSARY.md`, `ASSUMPTIONS.md`, `contracts/schema.sql`, `contracts/openapi.yaml`, ADR-001 → ADR-019, `CLAUDE.md`. `_PLAN.md` Phase 8 → ☑.

### Quyết định của phase

Không có ADR mới. Thiết kế dựa trên D-006, D-009, ADR-009, ADR-010, ADR-011 đã chốt.

| Mục | Quyết định |
|---|---|
| Hàng đợi | 3 queue theo trạng thái + `issue-queue`, sắp `status_changed_at` (chờ lâu nhất trước), keyset, tín hiệu `REVIEW_QUEUE` |
| Duyệt | 6 thao tác cổng `05-api.md:250`, chặn `beneficiary==approver` + đường thoát 4 điều kiện `WARNING` + `GET /self-approvals` |
| Yêu cầu sửa | `FREE_CONTENT` (request ở nguyên) vs `SLOT_DATA` (request về `CHANGES_REQUESTED`), `change_targets` do người chọn |
| Ký/uỷ quyền | `SIGNER [Should]` 1 cấp Sprint đầu, `delegation` `[Should]` |
| Thu hồi | `F5 [Should]` nhưng trạng thái `REVOKED` bắt buộc, 2 người `initiate`/`confirm` |
| Dừng khi chạm trần | Mọi lỗi/trần về `halt_for_human` (`await_human_takeover`), không để `document` dở dang — `NFR-06` |

### Đã kiểm

Theo quy ước: phép kiểm chạy **sau** lần ghi cuối, số liệu nằm ở báo cáo đóng phase.

### Đã kiểm

Chạy sau lần ghi cuối của mục này; số liệu ở báo cáo.

---

## 2026-09-14 (lần 2) — Phase 7/8: phép kiểm chéo đã chạy, sửa 08-hitl.md v0.1 → v0.2

Placeholder "phép kiểm chạy sau lần ghi cuối" ở hai mục trên chưa từng có số liệu thật. Chạy lại phép kiểm chéo chỉ cho `07-prompts.md` và `08-hitl.md` (đối chiếu tham chiếu số dòng, tên entity với `GLOSSARY.md`, ADR, assumption, cú pháp Mermaid, nhất quán nội bộ hai file). Kết quả: không có lỗi tên entity/trạng thái/permission cốt lõi, ADR/assumption viện dẫn đúng, không mâu thuẫn logic giữa hai file. 6 lỗi nhẹ/vừa tìm thấy, toàn bộ ở `08-hitl.md`, đã sửa:

| Vị trí | Trước | Sau | Lý do |
|---|---|---|---|
| Mục 2.2 | `06-structure.md:549` | `06-structure.md:700` | Dòng 549 là dòng đóng code block sau khi `06-structure.md` bị sửa ở phase sau; nội dung "khoá gốc `['review-queue']`" thật ở dòng 700 |
| Mục 5 | `signer_employee_id` | `signer_user_id` | Tên biến/tool output chuẩn theo `GLOSSARY.md` và `03-agents.md:175` là `signer_user_id`; `signer_employee_id` chỉ là tên cột DB ở `04-data.md:421`, không phải tên dùng ở tầng tool/prompt |
| Mục 5 | `00-domain.md:403` | `00-domain.md:396` | Dòng 403 là tiêu đề mục khác; `delegation.manage` thật ở dòng 396 |
| Mục 6 | `04-data.md:565` | `04-data.md:705` | Dòng 565 là dòng index không liên quan; "Giao thức ghi một lần" thật ở dòng 705 |
| Mục 6, `stateDiagram-v2` | Thiếu `CHANGES_REQUESTED → DRAFT`, `CHANGES_REQUESTED → ARCHIVED`, `REVOKED → ARCHIVED`, `SUPERSEDED → ARCHIVED` | Đã thêm | Máy trạng thái `document` thật (`00-domain.md` mục 5.1) có các cạnh này; thiếu làm sơ đồ trông đầy đủ trong khi không phải, dù chính mục 4 và mục 7 của `08-hitl.md` mô tả các nhánh đó bằng lời |
| Mục 9.3 | `05-api.md:247` | `05-api.md:161` | Dòng 247 là tiêu đề mục khác; `document.halted`/`latest_halt.reason_code` thật ở dòng 161 |

`08-hitl.md` lên **v0.2**. Không đổi quyết định, không đổi phạm vi, không đổi entity/trạng thái nào khác ngoài bảng trên. `07-prompts.md` không có lỗi, giữ nguyên v0.1. `_PLAN.md`, `GLOSSARY.md`, `ASSUMPTIONS.md`, `contracts/`, ADR không đổi.

**Bài học ghi lại:** tham chiếu chéo bằng số dòng sang file khác vẫn có rủi ro lệch tương tự khi file đích bị sửa ở phase sau — 4/6 lỗi trên đều do `05-api.md`, `04-data.md`, `06-structure.md` đã bị sửa nhiều lần kể từ khi các dòng đó được trích. Phase 13 (Consistency Audit) nên quét lại toàn bộ tham chiếu số dòng liên file, không chỉ tên entity.

---

## 2026-09-14 (lần 2) — Phase 9: Security & Guardrails

**Tạo mới:** `docs/design/09-security.md` v0.1, `docs/design/decisions/ADR-020-operating-mode-change-qua-endpoint.md`.

**Sửa file gốc của phase trước — trong phạm vi được duyệt tại vòng lập kế hoạch của phase này (mục D, E, F, G của phiên):**

| File | Thay đổi |
|---|---|
| `00-domain.md` | Mục Danh mục permission: thêm `request_type.manage`, `procedure.read_all`, `operating_mode.change` (22 → 25), cộng câu ghi rõ `procedure.manage` không kéo theo `procedure.read_all`. Mục Gói permission theo vai trò: thêm câu ba permission mới cấp lẻ; thêm câu ghi nhận đề xuất sửa (chưa tự áp) câu về `request.read_all`/phòng ban — diff ở `09-security.md`, chờ duyệt. **Không đụng** câu gốc về `request.read_all` |
| `GLOSSARY.md` → 0.19 | Mục Permission: thêm ba permission (22 → 25). Mục 12: thêm thao tác `operating_mode_transition` (thêm ở Phase 9) và hai entity tầng kỹ thuật `employee_credential`, `rate_limit_window` |
| `04-data.md` → v0.6 | Mục Ánh xạ entity → bảng: thêm `employee_credential`, `rate_limit_window`; "45 bảng" → "47 bảng". Mục Hai role và bất biến bằng quyền: thêm hai nhóm quyền mới |
| `05-api.md` → v0.8 | Mục 1.10: đánh dấu loại trừ thứ ba (`operating_mode_change`) đã giải, trỏ sang endpoint mới. Mục 1.11: đánh dấu quy tắc hiển thị theo độ nhạy đã giải, trỏ `09-security.md`. Mục 2.1: thêm thao tác `operating_mode_transition`. Mục 2.2: thêm ghi chú rate limit đăng nhập. Mục **2.2b mới**: endpoint `POST`/`GET /operating-mode/transitions`. Mục 2.14: sửa dòng rate limit trỏ `09-security.md`. Bảng mã lỗi: thêm `OPERATING_MODE_UNCHANGED`, `RATE_LIMITED`. Endpoint có contract: 48 → 49 |
| `contracts/openapi.yaml` → 0.2.0 | Thêm path `/operating-mode/transitions` (GET, POST); thêm schema `OperatingModeTransitionBody`, `OperatingModeChange`, `OperatingModeChangePage`; thêm response `RateLimited`; thêm `OPERATING_MODE_UNCHANGED` vào `Unprocessable` |
| `contracts/schema.sql` | Thêm bảng `employee_credential`, `rate_limit_window`, index `ix_rate_limit_window_start`, `GRANT` J.7 |
| `ASSUMPTIONS.md` → 0.20 | A-039, A-042, A-043 → **Đã chốt**. A-048 → thêm rủi ro (d), chốt `argon2id` và giữ H1, còn `TBD` tham số hash/thời hạn token/chu kỳ xoay vòng. A-055 → thêm trường hợp thứ tư (`rate_limit_window`, vẫn Mở). A-031 → thêm tham số rate limit (Thêm ở Phase 9). A-060 → thêm ràng buộc vị trí `bo19_migrator`. **A-061 mới** — `request.read_all` org-wide, đề xuất diff chờ duyệt |
| `_PLAN.md` | Phase 9 → ☑ |

### Quyết định của phase

**ADR-020** — `operating_mode_change` qua endpoint có permission (`operating_mode.change`), không qua thao tác vận hành. Lý do đứng trên hai dữ kiện đã có: `bo19_app` đã được cấp `INSERT` trên bảng này từ Phase 4 (ngược hướng `employee_credential`); thao tác vận hành không đi qua `tool_layer` nên không sinh `audit_event` cho hành động hệ trọng nhất hệ thống.

| Mục | Quyết định |
|---|---|
| Tool permission theo vai trò người yêu cầu | Ranh giới thật không phải "api tĩnh, tool_layer instance" (đã có ở `05-api.md`) mà là "tool chạy dưới danh nghĩa ai" — nhân viên đang chat (`intake_graph`) hay không ai tại thời điểm chạy job (`document_graph`), trách nhiệm truy vết qua thao tác cổng đã enqueue job, không qua `audit_event` của job |
| Row-level theo phòng ban | Hai trục tách riêng: kho quy trình (A-043, giải bằng `procedure.read_all`) và `request.read_all` (A-061, giữ org-wide, đề xuất sửa câu ở `00-domain.md` chưa tự áp) |
| Rate limit | Bảng `rate_limit_window`, khoá theo IP (không thuần theo `employee_code` — tránh DoS nhắm một người), không sinh `audit_event` (A-055 trường hợp thứ tư), chỉ áp cho `POST /auth/session` ở Sprint đầu |
| PII masking và hiển thị | Ba việc tách biệt trên cùng `slot_sensitivity`: mask log (đã có), giữ/xoá khi `EXPIRED` (A-014, không đổi), hiển thị (mới — `RES` ẩn mặc định kiểu ô mật khẩu, `PER` hiển thẳng kèm huy hiệu) |
| AuthN | `argon2id`, giữ H1 (`bo19_app` chỉ đọc `employee_credential`, không đảo); xoay vòng session secret không tự động, do người vận hành quyết |

### Tự kiểm

- **A-042 (hạn cứng) — đã đóng.** `request_type.manage` đã vào danh mục permission, cấp lẻ.
- Mọi tên entity/trạng thái/permission/tool dùng đúng `GLOSSARY.md`; ba permission mới đã thêm vào đúng nguồn trước khi dùng ở nơi khác.
- Không bịa số liệu: tham số hash, thời hạn token, chu kỳ xoay vòng, ngưỡng rate limit đều `TBD` kèm dòng `ASSUMPTIONS.md` có owner/hạn.
- Không ADR cho lựa chọn `argon2id` hay bảng `rate_limit_window` — lý do nêu ở mục Quyết định kiến trúc của `09-security.md` (áp lại nguyên tắc GRANT/REVOKE đã có, không phải mẫu hình mới).
- Đã đối chiếu `03-agents.md`, `04-data.md`, `05-api.md`, `07-prompts.md`, `08-hitl.md`, mọi ADR đã chốt — không tìm thêm mâu thuẫn ngoài các mục đã sửa ở trên.

### Chưa áp — chờ duyệt

Diff câu "`request.read_all` còn bị giới hạn thêm theo phòng ban ở Phase 9" ở mục Gói permission theo vai trò của `00-domain.md` — đề xuất ở mục Row-level theo phòng ban của `09-security.md`, ghi thành A-061. Không tự áp vì nó sửa một câu đã chốt ở Phase 0.

---

## 2026-09-14 (lần 3) — Phase 9 v0.2: bốn lỗ hở bị bắt trước khi duyệt, chưa đóng phase

Vòng lần 2 báo cáo đóng phase quá sớm. Bốn lỗ hở bị bắt, cộng ba câu hỏi được trả lời — sửa hết trước khi xin duyệt lại.

### I1 — A-042 quay lại `Mở` rồi đóng lại đúng căn cứ: đường nạp DB không tồn tại

Thêm ba dòng vào `00-domain.md`/`GLOSSARY.md` chỉ là sửa danh mục **trên giấy**. `backend/migrations/data/` trước phiên này chỉ có `.gitkeep` — đường nạp `permission`/`role`/`role_permission` mà `04-data.md` mô tả từ Phase 4 **chưa từng được viết**, kể cả cho 22 permission gốc. Không đóng A-042 mà bỏ qua chỗ hở đó.

**Đã viết:** `backend/migrations/data/0001_permission_catalog.sql` — `INSERT` toàn bộ 25 permission, 3 role, gói `role_permission` theo mục Gói permission theo vai trò của `00-domain.md`. **Không** seed `employee_role`/`employee_permission_grant` — cần `employee_id` thật, chưa tồn tại ở thời điểm thiết kế; cấp lẻ (`document.sign`, `document.revoke_confirm`, `procedure.manage`, `request_type.manage`, `procedure.read_all`, `operating_mode.change`) là thao tác vận hành bằng `bo19_migrator`, chưa có ai được chỉ định — nói rõ trong data migration và trong `09-security.md` mục 3.2, không phải ô trống.

A-042 giữ **Đã chốt**, nhưng lý do viết lại: danh mục **và** đường nạp cùng tồn tại, không chỉ danh mục.

### I2 — `03-agents.md` bị bỏ sót: `operating_mode_transition` thuộc đúng nhóm đã có sẵn

Mục 5.7 của `03-agents.md` ("Thao tác do endpoint gọi — đặt tên ở Phase 5") lập ra chính vì lý do "không có tên thì Phase 13 không truy vết được endpoint về thao tác". `operating_mode_transition` là đúng loại thao tác đó — lệnh ghi do endpoint gây ra, qua `tool_layer`, sinh `audit_event` — và đã bị bỏ ngoài bảng. Thêm dòng thứ mười bốn; nhân tiện sửa dòng `request_type_upsert`/`slot_definition_upsert` đang ghi "A-042 chưa có trong danh mục" — stale sau khi A-042 đóng.

### I3 — `contracts/schema.sql` bị sửa thẳng, sai với quyết định đã có từ Phase 6

`06-structure.md` mục 3 đã viết sẵn: *"`0001_initial.sql` = `contracts/schema.sql` ở trạng thái đóng Phase 6; về sau mỗi thay đổi một file"*. Vòng lần 2 sửa thẳng `contracts/schema.sql` — sai. **Đã sửa:**

- `contracts/schema.sql` — trả về nguyên trạng đóng Phase 6, gỡ hai bảng, index, GRANT J.7 vừa thêm.
- **Tạo mới** `backend/migrations/schema/0002_phase9_security.sql` — hai bảng `employee_credential`, `rate_limit_window`, index, GRANT, đúng trình tự schema migration của ADR-017.
- `04-data.md` — câu "45 bảng" giữ nguyên (mô tả đúng một file `schema.sql`, không đổi); thêm câu riêng cho "47 bảng của toàn bộ schema sau migration 0002". Hai dòng GRANT mới ghi rõ thuộc `0002_phase9_security.sql`, không thuộc `contracts/schema.sql`.
- `09-security.md` mục DDL — viết lại thành "Migration bổ sung của Phase 9", trỏ đúng hai file thay vì nói "schema.sql đã đóng — được phép".

### I4 — `CHANGELOG.md` thiếu trong bảng file đã sửa của mục trước

Đúng — quên liệt kê chính file đang ghi. Bảng ở mục trước (2026-09-14 lần 2) không có dòng `CHANGELOG.md`; coi mục ngày đó **là** bằng chứng đã ghi, không sửa lại lịch sử. Từ mục này trở đi, `CHANGELOG.md` tự liệt kê chính nó khi đáng kể.

### J1 — Câu về `request.read_all` ở `00-domain.md`: sửa tại chỗ, không vá bằng chú thích

Vòng lần 2 giữ nguyên câu cũ ("còn bị giới hạn thêm theo phòng ban ở Phase 9") kèm một chú thích trỏ sang đề xuất diff — đúng kiểu vá đã bị bác ở tiền lệ Phase 2 (chẩn đoán tới gốc, sửa ở file gốc). **Đã sửa trực tiếp** mục Gói permission theo vai trò của `00-domain.md`: câu mới nói org-wide, kèm lý do (A-001, một Phòng Hành chính tập trung) và điều kiện kích hoạt lọc (A-001 bị bác bỏ — từ hai Phòng Hành chính độc lập trở lên). **A-061 viết lại theo đúng nghĩa của nó** — không còn "có sửa câu hay không" (đã sửa) mà là điều kiện kích hoạt, giữ `Mở`.

### J2 — `GET /operating-mode/transitions`: bỏ vế `operating_mode.change`

Quyền ghi không tự kéo theo quyền đọc — đúng nguyên tắc chính phiên này vừa viết cho `document.issue`/`audit.read_all` và `procedure.manage`/`procedure.read_all`. Sửa permission còn lại đúng một: `audit.read_all`. Không mở mẫu hình "permission theo quan hệ HOẶC" mới cho riêng một endpoint. Sửa `05-api.md` mục 2.2b, `contracts/openapi.yaml`, `09-security.md` mục 12.

### J3 — ADR cho `argon2id`; giữ không-ADR cho `rate_limit_window`

Phép thử đúng là "có điều kiện đảo ngược không", không phải "có phải mẫu hình kiến trúc mới không". `argon2id` có — RAM của instance Render, đã tự viết ra ở vòng trước nhưng không nhận ra đó là điều kiện đảo ngược. **Tạo mới** `docs/design/decisions/ADR-021-argon2id-hash-mat-khau.md`: Context/Options (A `argon2id` · B `bcrypt` · C `PBKDF2` · D `scrypt`)/Decision/Consequences (điều kiện đảo ngược: thời gian hash cạnh RAM còn trống, đo khi có Render đầu tiên)/Rejected alternatives — lý do bằng tính chất hàm (tham số bộ nhớ độc lập hay không), không trích khuyến nghị từ trí nhớ. `rate_limit_window` giữ không cần ADR — không có điều kiện đảo ngược riêng ngoài tham số TBD đã ở A-031.

### K1 — IP thật phía sau proxy Render: `[CẦN XÁC MINH]`

Rate limit khoá theo IP giả định `api` đọc đúng IP client từ header chuyển tiếp của Render — chưa xác minh header nào, và có tự đặt được không khi có nhiều proxy chồng nhau. **A-062 mới**, cùng họ A-051, owner Người triển khai, hạn trước `PRODUCTION`. Nhắc trong `09-security.md` mục Rate limit và mục Open Questions.

### K3 — `_PLAN.md` Phase 9 trả về `☐`

Tiền lệ Phase 5: giữ `☐` khi còn đúng một mục hở. Ba câu hỏi (J1–J3) và bốn lỗ hở (I1–I4) đã xử lý; đánh `☑` ở mục báo cáo tiếp theo sau khi anh xác nhận.

### File đã sửa thêm trong vòng này

| File | Thay đổi |
|---|---|
| `09-security.md` → v0.2 | Mục 3: thêm 3.2 (đường nạp DB), đánh số lại 3.2→3.3; mục 5.2: bỏ đoạn diff-chờ-duyệt, viết org-wide đã áp; mục 6.1: thêm cảnh báo A-062; mục 12.2: `GET` chỉ `audit.read_all`; mục DDL viết lại thành "Migration bổ sung của Phase 9"; `ADR mới` +ADR-021; `Không viết ADR cho` bỏ `argon2id`, chỉ còn `rate_limit_window` |
| `decisions/ADR-021-argon2id-hash-mat-khau.md` | Tạo mới |
| `backend/migrations/data/0001_permission_catalog.sql` | Tạo mới |
| `backend/migrations/schema/0002_phase9_security.sql` | Tạo mới |
| `contracts/schema.sql` | Trả về nguyên trạng đóng Phase 6 |
| `03-agents.md` | Mục 5.7: +`operating_mode_transition` (14 thao tác); sửa dòng `request_type_upsert` stale |
| `00-domain.md` | Mục 7.2: câu `request.read_all` viết lại tại chỗ, không còn chú thích riêng |
| `05-api.md` → v0.9 | Mục 2.2b: `GET` chỉ `audit.read_all`, thêm câu giải thích |
| `contracts/openapi.yaml` → 0.2.1 | `x-bo19-permission` của `GET /operating-mode/transitions` chỉ còn `audit.read_all` |
| `04-data.md` → v0.7 | Câu "45 bảng"/"47 bảng" viết lại phân biệt file; hai dòng GRANT và hai dòng ánh xạ entity ghi rõ thuộc `0002_phase9_security.sql`; mục 1.4 sửa hai dòng stale (A-042) |
| `ASSUMPTIONS.md` → 0.21 | A-061 viết lại theo điều kiện kích hoạt; **A-062 mới**; A-042 giữ Đã chốt, lý do bổ sung đường nạp |
| `_PLAN.md` | Phase 9 → `☐` |

### Tự kiểm lại

- **A-042** — Đã chốt, đúng căn cứ: danh mục **và** đường nạp DB cùng tồn tại.
- **`contracts/schema.sql`** — nguyên trạng đóng Phase 6, không một ký tự đổi.
- Không ADR nào thiếu Rejected alternatives; ADR-021 có bốn phương án, ba lý do loại riêng biệt.
- Ba câu hỏi J1–J3 đều đã áp trực tiếp vào file, không còn ở dạng đề xuất treo.
