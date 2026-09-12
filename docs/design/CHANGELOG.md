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
