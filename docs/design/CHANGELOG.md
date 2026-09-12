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
