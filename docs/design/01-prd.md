# PRD — Admin Service Desk Agent (BO-19)

**Phiên bản:** 0.9 · **Trạng thái:** Draft để xác thực với người dùng · **Primary persona:** Cán bộ hành chính

> Sản phẩm tiếp nhận yêu cầu hành chính bằng hội thoại, soạn sẵn văn bản từ mẫu đã duyệt và đưa vào hàng đợi duyệt của phòng hành chính. Sản phẩm **không** tự phát hành, **không** tự đóng dấu, và **không** thẩm định thể thức văn bản.

Tên entity, trạng thái, permission và loại yêu cầu trong file này dùng đúng [`GLOSSARY.md`](./GLOSSARY.md). Quyết định `D-xxx` và giả định `A-xxx` tham chiếu mục Quyết định đã chốt trong Phase 0 của [`00-domain.md`](./00-domain.md) và [`ASSUMPTIONS.md`](./ASSUMPTIONS.md).

## 1. Problem statement

Nhân viên gửi yêu cầu hành chính — xác nhận công tác, giấy giới thiệu, đặt phòng họp, xin con dấu — qua nhiều kênh rời rạc. Phòng Hành chính nhận, tự phân loại, tự tra hồ sơ nhân sự, copy một văn bản cũ ra sửa, rồi trình duyệt và phát hành. Không kênh nào là nguồn sự thật, nên không ai trả lời được "yêu cầu của tôi đang ở đâu" ngoài cách đi hỏi.

**Giả thuyết baseline cần kiểm chứng:** chưa có bất kỳ số liệu vận hành nào — số nhân viên, số yêu cầu mỗi tháng theo loại, thời gian xử lý hiện tại, tỷ lệ phải làm lại (A-002). Trước khi chốt PRD, cần phỏng vấn phòng hành chính, đếm yêu cầu thực nhận trong một tháng gần nhất từ hộp thư và sổ tay hiện có, và thu ít nhất một văn bản mẫu thật đã phát hành cho mỗi loại (A-018). **Ngưỡng của metric loại Cảnh báo ở mục 2 là do chọn, không phải kết quả đo.**

### Pain points ưu tiên

| Pain point | Quy trình hiện tại → failure | Tác động | Root cause |
|---|---|---|---|
| Yêu cầu đến từ nhiều kênh rời rạc | Email, chat, giấy, gặp trực tiếp → cán bộ tự gom, dễ sót, không có thứ tự xử lý | Yêu cầu rơi; không ai biết tồn đọng bao nhiêu | Không có một điểm tiếp nhận duy nhất |
| Yêu cầu gửi lên thiếu thông tin | Cán bộ đọc xong mới phát hiện thiếu → nhắn hỏi lại → chờ → nhắn tiếp | Mỗi yêu cầu mất nhiều vòng qua lại trước khi bắt đầu làm được | Không có gì kiểm tra điều kiện tại thời điểm gửi |
| Soạn văn bản thủ công từ bản cũ | Mở một văn bản cũ cùng loại, sửa tên, sửa ngày, sửa nơi nhận → sót một chỗ là sai | Sai nội dung hoặc sai thông tin nhân sự; phải làm lại, mất uy tín với bên nhận | Mẫu nằm rải rác, không có cơ chế điền biến |
| Không theo dõi được trạng thái | Nhân viên hỏi "xong chưa", cán bộ phải tự nhớ hoặc lục lại | Cán bộ bị ngắt quãng liên tục; nhân viên không dự liệu được thời gian | Trạng thái chỉ nằm trong đầu người xử lý |
| Cấp số và theo dõi con dấu bằng sổ tay | Ghi tay vào sổ → trùng số, nhảy số, hoặc không đối chiếu được số bản đã đóng dấu | Rủi ro pháp lý và không giải trình được khi bị hỏi | Sổ không phải hệ thống, không có ràng buộc đồng thời |

Đây là các pain point suy ra từ mô tả hiện trạng trong đề bài, **chưa phải evidence nội bộ**. Chúng cần được xác nhận bằng phỏng vấn ở giả thuyết baseline trên.

## 2. Goals & metrics

**Không có pilot.** D-009 buộc hệ thống chạy ở `operating_mode = NON_PRODUCTION`: văn bản mang watermark không gỡ được, cấp số từ dải `TRIAL`, không đóng dấu thật. Vì vậy không có văn bản thật nào được phát hành, và mọi con số lấy từ một "pilot" trong trạng thái này sẽ là số giả. Metric được neo vào hai nguồn đo thật:

- **UAT có kịch bản** — một buổi làm việc với tập yêu cầu soạn sẵn, người thật thao tác trên hệ thống, có người chấm kết quả. Số người, số ca và người chấm chốt ở mục 9.
- **Bộ eval offline** — tập ca kiểm thử dẫn xuất từ bảng edge case Phase 0, đặc tả ở mục 7.

Metric chia **hai loại**, và chỉ loại thứ nhất là cổng nghiệm thu:

- **Bất biến** — hoặc đúng hoàn toàn, hoặc hệ thống sai. Ngưỡng là tuyệt đối, không phải con số hiệu chỉnh được. Đây là điều kiện trong Definition of Done ở mục 8.
- **Cảnh báo** — chỉ số quan sát, ngưỡng do chọn và **chưa hiệu chỉnh** (A-019). Không đạt thì **mở rà soát**, không phải trượt nghiệm thu. **Không** nằm trong Definition of Done.

| ID | Loại | Metric | Nguồn đo | Ngưỡng |
|---|---|---|---|---|
| M8 | **Bất biến** | Ca ở nhóm G của bộ eval bị sinh **sai loại văn bản** | Bộ eval | **0 ca** |
| M4 | **Bất biến** | Văn bản đi qua đủ hai cổng HITL trước khi `ISSUED`; văn bản `ISSUED` có số cấp từ `document_register` | Kiểm tra dữ liệu sau UAT | Toàn bộ, không ngoại lệ |
| M5 | **Bất biến** | Văn bản sinh ra ở `NON_PRODUCTION` mang watermark và số thuộc dải `TRIAL` | Kiểm tra dữ liệu sau UAT | Toàn bộ, không ngoại lệ |
| M6 | **Bất biến** | Ca "không đủ điều kiện" và "ngoài phạm vi" được agent báo rõ là chưa xử lý được, không tự suy diễn cho xong | Bộ eval | Toàn bộ, không ngoại lệ |
| M1 | Cảnh báo | Số ca phân loại sai `request_type` **ngoài** nhóm G | Bộ eval | Mong đợi 0. Từ 2 ca trở lên thì mở rà soát |
| M2 | Cảnh báo | Số văn bản phải quay lại `CHANGES_REQUESTED` trước khi được duyệt, trên tổng số văn bản sinh ra trong UAT | UAT | Ghi nhận cả tử số và mẫu số. Quá một phần ba thì mở rà soát |
| M3 | Cảnh báo | Số người tham gia UAT **không** hoàn tất được một yêu cầu đến `SUBMITTED` mà không cần trợ giúp ngoài hệ thống | UAT | Mong đợi 0. Mỗi người không hoàn tất là một phát hiện phải ghi lại |

**Vì sao M1 không phải cổng nghiệm thu.** Hai loại yêu cầu đang hỗ trợ khác nhau rõ rệt — một cái xác nhận người đang làm việc ở đâu, một cái giới thiệu người đi làm việc với bên ngoài. Phân loại giữa hai thứ đó gần như chắc chắn đúng, nên một ngưỡng đặt trên chúng **không canh giữ điều gì**. Thứ thật sự canh RISK-02 là **M8** — các ca nhập nhằng ở nhóm G, nơi mô tả cố tình mập mờ hoặc trỏ về một loại chưa hỗ trợ.

**Vì sao bỏ phần trăm ở M1 và M3.** Mẫu số quá nhỏ. Bộ eval có 37 ca, buổi UAT có vài người. Trên mẫu số đó "≥ 95%" chỉ có nghĩa là *sai không quá một ca*, và "≥ 80%" thay đổi ý nghĩa tuỳ theo có 4 hay 6 người tham gia. Viết bằng phần trăm làm ngưỡng **trông như đã hiệu chỉnh** trong khi nó chưa từng được đo. Số ca tuyệt đối nói đúng thứ thực sự được kiểm.

**M7 — chỉ đo được sau khi mở milestone sản xuất:** tỷ lệ yêu cầu hành chính vào qua hệ thống trên tổng số yêu cầu phòng hành chính thực nhận. Đây là metric phát hiện chế độ hỏng *nhân viên bỏ hệ thống, quay lại email* — chế độ hỏng này vô hình với M1–M6 và M8 vì chúng chỉ đo những gì đã vào hệ thống. Không đo được trước sản xuất vì trước đó nhân viên không có lý do thật để dùng.

**Điều kiện mở milestone sản xuất:** A-018 đóng — tổ chức có người nghiệm thu thể thức văn bản. Chừng nào chưa có, `operating_mode` giữ `NON_PRODUCTION` và việc chuyển sang `PRODUCTION` là một quyết định có người ký, không phải một cờ cấu hình (D-009). Pilot thật là milestone riêng nằm sau mốc đó, không thuộc phạm vi PRD này.

## 3. Persona

**Primary — Cán bộ hành chính:** làm việc trên máy tính văn phòng, mỗi ngày xử lý nhiều yêu cầu từ nhiều kênh. Là người soạn văn bản, giữ sổ văn bản, giữ con dấu, và là người chịu trách nhiệm khi văn bản sai. Hiểu rất rõ nghiệp vụ và thể thức, nhưng phần lớn thời gian mất vào thao tác lặp: gom yêu cầu, hỏi lại thông tin thiếu, copy văn bản cũ ra sửa. Là nút thắt của toàn bộ quy trình — mọi cải thiện về thời gian trả kết quả đều đi qua người này. Mục tiêu của họ là xử lý hết hàng đợi mà không phải nhớ gì trong đầu và không phải giải trình lại về sau.

**Vai trò liên quan — Nhân viên:** người gửi yêu cầu. **Dùng hệ thống vài lần mỗi năm.** Đây là ràng buộc thiết kế chứ không phải thông tin nền: người dùng thưa **không hình thành thói quen**, nên không nhớ hệ thống ở đâu, không nhớ cần chuẩn bị gì, và không chịu được ma sát. Mỗi bước thừa, mỗi thuật ngữ nội bộ, mỗi lần bắt tra cứu thông tin của chính mình đều đẩy họ quay về email — và khi đó sản phẩm thất bại dù mọi metric phía cán bộ vẫn đẹp. Ràng buộc này thành NFR-04.

**Vai trò liên quan — Người ký cấp trên (`SIGNER`):** ký văn bản ở cấp cao hơn. Chưa có trong Sprint đầu; thao tác ký do `ADMIN_OFFICER` được cấp lẻ permission `document.sign` thực hiện. Không phải primary persona.

## 4. Input

| Chiều input | Phạm vi Sprint đầu |
|---|---|
| Kênh | Chat trên web. Không email, không mobile app |
| Loại yêu cầu | `WORK_CONFIRMATION` và `INTRODUCTION_LETTER`. Các loại khác xem mục 5 |
| Ngôn ngữ | Tiếng Việt. Bản tiếng Anh của giấy xác nhận công tác là **Could** |
| Hồ sơ nhân viên | Bảng `employee` trên PostgreSQL, import thủ công từ CSV, mỗi bản ghi có `source` và `synced_at` (D-002). Không tích hợp HRM thật |
| Mẫu văn bản | File `.docx` do Product Owner chuẩn bị, chứa sẵn toàn bộ khung thể thức và các biến (ADR-001). Có phiên bản |
| Kho quy trình hành chính | Tài liệu quy trình nội bộ, dùng để trả hướng xử lý thủ công có trích nguồn cho yêu cầu ngoài phạm vi (F1). **Chưa tồn tại** (A-027); kho rỗng là trạng thái được hỗ trợ, không phải lỗi |
| File người dùng tải lên | Không có trong Sprint đầu. Upload văn bản ngoài gắn với `SEAL_REQUEST`, ở mức **Could** |
| Khối lượng | `TBD` — chưa có số liệu vận hành (A-002). Không đặt ngưỡng tải trong Sprint đầu |

## 5. Scope & priority

| Priority | Feature | Giá trị |
|---|---|---|
| **Must** | F1 — Tiếp nhận và phân loại yêu cầu qua chat | Một điểm tiếp nhận duy nhất; chặn yêu cầu thiếu thông tin ngay tại lúc gửi |
| **Must** | F2 — Sinh văn bản từ mẫu | Bỏ thao tác copy văn bản cũ ra sửa, nguồn sai sót lớn nhất hiện nay |
| **Must** | F3 — Duyệt, cấp số và phát hành | Hai cổng HITL, sổ số có ràng buộc đồng thời thay cho sổ tay |
| **Must** | F4 — Theo dõi trạng thái | Nhân viên tự biết yêu cầu đang ở đâu, cán bộ không bị ngắt quãng để trả lời |
| **Must** | F6 — Quản lý mẫu, danh mục loại yêu cầu và hồ sơ nhân viên | Thêm loại yêu cầu mới không cần lập trình viên |
| **Should** | F5 — Thu hồi văn bản đã phát hành | Xử lý văn bản phát hành nhầm; xem lý do xếp Should ở mục 6 |
| **Should** | `ROOM_BOOKING` — đặt phòng họp | Loại yêu cầu không sinh văn bản, cần máy trạng thái `room_booking` riêng |
| **Should** | Định tuyến ký nhiều cấp, vai trò `SIGNER`, uỷ quyền khi vắng mặt | Cần khi tổ chức có cấp ký trên phòng hành chính |
| **Should** | Dashboard SLA, cảnh báo tồn đọng | Cần dữ liệu vận hành thật mới định cỡ được ngưỡng (A-002) |
| **Could** | `SEAL_REQUEST` cho văn bản ngoài, kèm upload file | Phụ thuộc tính năng upload; là bề mặt prompt injection lớn nhất (RISK-02) |
| **Could** | `INCOME_CONFIRMATION`, `BUSINESS_TRIP_ORDER` | Hai loại `[ĐỀ XUẤT]` chưa xác nhận là có thật (A-015) |
| **Could** | Bản tiếng Anh của giấy xác nhận công tác; memory yêu cầu định kỳ | Tiện ích, không gỡ pain point nào ở mục 1 |
| **Won't** | Chữ ký số | Cần tích hợp CA và quản lý chứng thư; `SIGNED` trong Sprint đầu là ghi nhận sự kiện ký tay (A-003) |
| **Won't** | Điều khiển thiết bị đóng dấu, sinh ảnh dấu | Con dấu là dấu vật lý; hệ thống quản lý quy trình duyệt và nhật ký, không thay thao tác vật lý (A-004) |
| **Won't** | Tích hợp HRM/ERP thật, SSO doanh nghiệp, multi-tenant, mobile app, i18n | Ngoài phạm vi đề bài (mục Phạm vi của `CLAUDE.md`); mỗi cái kéo theo một trục phức tạp không phục vụ pain point nào ở mục 1 |
| **Won't** | Graph database | SQL cộng vector đủ cho mọi truy vấn trong phạm vi này; thêm vào là thêm một hệ thống phải vận hành mà không đổi lại được gì (mục Phạm vi của `CLAUDE.md`) |
| **Won't** | Agent tự thẩm định thể thức văn bản | Khung thể thức nằm trong template, không do model sinh và không do model kiểm (ADR-001). Đây là loại trừ có chủ đích, không phải thiếu sót |

## 6. Features & acceptance criteria

> **Quy ước:** Feature và AC ở cấp feature là phạm vi cam kết của PRD. Các user stories bên dưới chỉ là gợi ý phân rã, **không bắt buộc và chưa được chốt**; team sẽ refinement, bổ sung và chốt AC cấp story trong buổi grooming trước từng sprint.

Yêu cầu xuyên suốt — HITL, tách biệt trách nhiệm, chế độ phi sản xuất, bảo mật, chi phí — khai báo một lần ở mục 7 và **không lặp lại** trong AC từng feature.

### F1 — Tiếp nhận và phân loại yêu cầu qua chat (Must)

**Pain point giải quyết:** yêu cầu đến từ nhiều kênh rời rạc; yêu cầu gửi lên thiếu thông tin.
**Request type:** `WORK_CONFIRMATION`, `INTRODUCTION_LETTER`.

**User stories**

1. Là nhân viên, tôi muốn mô tả nhu cầu bằng lời để không phải biết mình cần loại giấy nào.
2. Là nhân viên, tôi muốn được hỏi đúng những gì còn thiếu để không bị trả lại sau.
3. Là cán bộ hành chính, tôi muốn yêu cầu vào hàng đợi đã đủ thông tin để bắt tay vào làm ngay.

**AC**

- Agent phân loại yêu cầu về đúng `request_type` hoặc hỏi lại khi mô tả nhập nhằng. Khi không chắc, agent **hỏi**, không đoán.
- Yêu cầu ngoài hai loại đang hỗ trợ được báo rõ là chưa hỗ trợ, kèm **hướng xử lý thủ công đủ căn cứ** theo định nghĩa ở cuối feature này. Agent không cố ép vào một loại gần giống. AC này phải đúng **trong cả hai trạng thái** của kho quy trình hành chính: có đoạn nguồn thì trả hướng xử lý có trích nguồn; kho rỗng hoặc không đoạn nào đủ căn cứ thì trả hướng dẫn chung và **nói rõ là không có căn cứ trong kho**. Kho hiện chưa tồn tại (A-027) — kho rỗng không làm AC này trượt.
- Agent thu thập slot theo schema ở mục Slot schema của `00-domain.md`, và chỉ chuyển yêu cầu sang `SUBMITTED` khi **đủ điều kiện xử lý** theo định nghĩa dưới đây.
- **Nhiều nhu cầu trong một lượt** (EC-CV-01): một `request` mang đúng một `request_type`, nên hai nhu cầu phải thành hai `request`. Agent nhận ra và nêu rõ cả hai, xử lý **tuần tự**, không bao giờ im lặng bỏ qua nhu cầu thứ hai và không gộp hai nhu cầu vào một văn bản.
- **Đổi loại giữa chừng** (EC-CV-02): slot đã thu của loại cũ **không được mang sang** loại mới, kể cả khi trùng tên. Agent xác nhận việc đổi loại và nêu rõ thông tin nào phải hỏi lại.
- **Quay lại sau gián đoạn** (EC-CV-04): trong hạn thì khôi phục đúng trạng thái đã thu và nhắc lại còn thiếu gì; sau khi `EXPIRED` thì nói rõ yêu cầu đã hết hạn trước khi bắt đầu lại, **không** âm thầm dùng tiếp dữ liệu cũ. Đây là ca mà persona nhân viên ở mục 3 gần như chắc chắn rơi vào.

**Định nghĩa "Yêu cầu đủ điều kiện xử lý"**

Một `request` chỉ được rời `DRAFT` sang `SUBMITTED` khi đồng thời:

1. Mọi slot nguồn `USER_INPUT` được đánh dấu bắt buộc của `request_type` đó đều có giá trị **do người dùng cung cấp trong hội thoại**, **hoặc** do agent **đề xuất lại** từ `request` `EXPIRED` gần nhất có cùng `beneficiary_employee_id` và cùng `request_type`, rồi được nhân viên **xác nhận tường minh từng giá trị** — không giá trị nào được hiển thị ở dạng đã xác nhận sẵn. Đề xuất rồi để nhân viên xác nhận là cơ chế đã chấp nhận cho `HR_PROFILE` (D-002), không phải suy diễn. Dùng lại giá trị từ `request` đã `FULFILLED` là memory yêu cầu định kỳ, ở mức **Could**, không thuộc điều kiện này.
2. Mọi slot nguồn `HR_PROFILE` đã được agent **đề xuất** và **nhân viên xác nhận từng giá trị** (D-002 ràng buộc 1 và 2).
3. Mọi rule kiểm tra ở bảng slot tương ứng đều pass.
4. `beneficiary_employee_id` đã xác định, và nếu khác người tạo thì có `delegation` còn hiệu lực hoặc người tạo có permission `request.create_on_behalf`.

**Bị coi là KHÔNG đủ điều kiện** — mỗi ca dưới đây chặn `SUBMITTED`, agent phải hỏi lại hoặc từ chối, tuyệt đối không tự lấp. Danh sách này chỉ nói về **điều kiện của một yêu cầu đã biết loại**; ca phân loại sai hay nhập nhằng thuộc `EC-CV-xx` và đã xử lý ở phần AC trên, không lặp lại ở đây:

- Agent suy ra giá trị slot `USER_INPUT` từ ngữ cảnh hội thoại, từ yêu cầu cũ của cùng nhân viên, hoặc từ hồ sơ nhân sự. Suy diễn hợp lý vẫn là suy diễn.
- Nhân viên chưa xác nhận một giá trị `HR_PROFILE` nào đó, kể cả khi giá trị đó hiển nhiên đúng.
- Một giá trị đề xuất lại từ `request` `EXPIRED` được tính là đã có trong khi nhân viên chưa xác nhận tường minh — kể cả khi nó được hiển thị ở dạng đã tick sẵn.
- Nhân viên khai một giá trị mâu thuẫn với `HR_PROFILE` — ví dụ khai đã nghỉ việc nhưng `employment_end_date` rỗng. Đây là ca chuyển phòng hành chính xác minh, không phải ca agent chọn bên nào đúng.
- Một slot có giá trị nhưng rỗng về nội dung: `purpose` là "cần gấp", `work_content` là "làm việc". Có ký tự không phải là có thông tin.

**Định nghĩa "Hướng xử lý thủ công đủ căn cứ"**

Hướng xử lý cho một yêu cầu ngoài phạm vi là **đủ căn cứ** khi mỗi bước, đầu mối, giấy tờ hay thời hạn được nêu ra đều nằm **nguyên văn** trong ít nhất một đoạn của `procedure_document` **đang hiệu lực** mà nhân viên có quyền xem, và đoạn đó được hiển thị kèm tên tài liệu, phiên bản và mục. Không có đoạn nào như vậy thì câu trả lời đúng là: báo chưa hỗ trợ, hướng dẫn chung liên hệ phòng hành chính, và **nói rõ là kho quy trình không có căn cứ cho việc này**.

**Bị coi là KHÔNG đủ căn cứ:**

- Nêu một bước, đầu mối, giấy tờ hay thời hạn không có trong đoạn nguồn nào — kể cả khi nghe hợp lý.
- Trích một đoạn thuộc phiên bản tài liệu không còn hiệu lực.
- Dựng hướng xử lý bằng cách ghép các đoạn mà không đoạn nào nói trực tiếp về việc nhân viên cần. Có đoạn được truy hồi không có nghĩa là có căn cứ.
- Kho rỗng hoặc không có đoạn liên quan, nhưng câu trả lời không nói rõ là không có căn cứ — trình bày hướng dẫn chung như thể đó là quy trình.

### F2 — Sinh văn bản từ mẫu (Must)

**Pain point giải quyết:** soạn văn bản thủ công từ bản cũ.
**Request type:** `WORK_CONFIRMATION`, `INTRODUCTION_LETTER`.

**User stories**

1. Là cán bộ hành chính, tôi muốn nhận bản nháp đã điền sẵn để chỉ còn việc kiểm tra.
2. Là cán bộ hành chính, tôi muốn thấy giá trị nào lấy từ đâu để kiểm tra nhanh.
3. Là cán bộ hành chính, tôi muốn bản nháp thiếu biến bị chặn lại thay vì đến tay tôi với chỗ trống.

**AC**

- `document` được render **tại thời điểm `request` chuyển sang `SUBMITTED`** (D-010) — không sớm hơn, và không hoãn tới khi có người mở hàng đợi. Cán bộ hành chính mở hàng đợi là thấy bản nháp sẵn, đúng user story 1 ở trên. Không có bản nháp nào tồn tại trước mốc đó, nên yêu cầu `EXPIRED` không để lại file nào. Cho nhân viên xem trước văn bản, nếu sau này cần, là một feature riêng ở mức `[Could]`, không phải hệ quả của việc render sớm.
- Agent render `document` từ `template` bằng cách **điền biến**. Agent không tạo biến mới, không sửa nội dung ngoài vùng biến, không đổi bố cục (ADR-001).
- Prompt LLM chỉ sinh phần **nội dung tự do** — lý do, mục đích, nội dung công việc. Khung thể thức đến từ file `.docx`.
- Màn hình duyệt hiển thị `source` và `synced_at` cho mọi giá trị nguồn `HR_PROFILE` có trong văn bản (D-002 ràng buộc 3).
- `document` chỉ vào `PENDING_APPROVAL` khi **đủ điều kiện trình duyệt** theo định nghĩa dưới đây.

**Định nghĩa "Văn bản đủ điều kiện trình duyệt"**

Một `document` chỉ được rời `DRAFT` sang `PENDING_APPROVAL` khi đồng thời:

1. **Mọi biến khai báo trong template đều có giá trị thật.** Không biến nào còn ở dạng placeholder, chuỗi rỗng, hay giá trị giữ chỗ kiểu `N/A`, `...`, `[điền sau]`.
2. Giá trị của mỗi biến đến từ đúng nguồn đã khai báo ở slot schema. Biến gắn nguồn `SYSTEM` chỉ do hệ thống sinh.
3. Phần nội dung tự do do LLM sinh đã được ghi vào đúng biến của nó, không tràn ra phần khung.
4. `requires_seal` và `seal_type` đã được xác định theo `request_type` và `recipient_org`.

**Biến agent không bao giờ được tự điền:** `document_number` và `issued_date` — chỉ sinh tại thời điểm `ISSUED` (mục Cấp số văn bản của `00-domain.md`); `signer_user_id` — do định tuyến duyệt quyết định; và mọi giá trị thuộc khung thể thức, vốn nằm trong template chứ không phải biến.

**Bị coi là KHÔNG đủ điều kiện trình duyệt:**

- Thiếu bất kỳ biến nào, kể cả biến "không quan trọng". Không có khái niệm biến tuỳ chọn trong bản render cuối: biến tuỳ chọn phải được template xử lý bằng đoạn điều kiện, không bằng cách để trống.
- Agent tự đặt một giá trị hợp lý cho biến mà nhân viên chưa xác nhận.
- Agent sinh thêm câu chữ vào phần khung — thêm dòng nơi nhận, đổi cách ghi ngày tháng, thêm câu kết — dù nội dung nghe hợp lý.
- Văn bản render từ một phiên bản template khác với phiên bản đang hiệu lực tại thời điểm render.

### F3 — Duyệt, cấp số và phát hành (Must)

**Pain point giải quyết:** cấp số và theo dõi con dấu bằng sổ tay; không có vết của việc duyệt.
**Request type:** `WORK_CONFIRMATION`, `INTRODUCTION_LETTER`.

**User stories**

1. Là cán bộ hành chính, tôi muốn một hàng đợi duyệt thay vì đi lục email.
2. Là cán bộ hành chính, tôi muốn trả lại kèm lý do để agent soạn lại đúng chỗ sai.
3. Là cán bộ hành chính, tôi muốn số văn bản do hệ thống cấp để không trùng và không nhảy số.

**AC**

- Hai cổng duyệt là **hai quyết định riêng biệt**: duyệt nội dung tại `PENDING_APPROVAL` và duyệt dấu tại `PENDING_SEAL`. Không có thao tác nào gộp hai cổng, kể cả khi cùng một người thực hiện.
- Từ chối và yêu cầu sửa đều bắt buộc có lý do dạng văn bản tự do, không rỗng. Yêu cầu sửa đưa `document` về `DRAFT` để agent soạn lại.
- `document_number` được cấp **đúng một lần**, tại thời điểm chuyển sang `ISSUED`, nguyên tử trên `document_register`. Hai yêu cầu phát hành đồng thời không bao giờ nhận cùng một số.
- Cấp số thất bại sau khi đã lấy số thì số đó được đánh dấu `VOIDED` kèm lý do và **không tái sử dụng**.
- Mỗi lần duyệt, ký, đóng dấu, cấp số, phát hành đều sinh một `audit_event` riêng, không gộp.
- **Bản render tại thời điểm phát hành là bất biến.** Nối hai ràng buộc đã có — văn bản đã render phải ghi lại phiên bản template đã dùng (F6), và nội dung từ `APPROVED` trở đi là bất biến — thành một ranh giới rõ: **bản render gắn với `document` ở `SEALED` và `ISSUED` không bao giờ được mất hay bị đè.** Các bản render trung gian sinh ra trong vòng `CHANGES_REQUESTED → DRAFT` thì **không** chịu ràng buộc này; đè nhau hay tích luỹ là quyết định kỹ thuật của Phase 4 (A-021).
- **Không tồn tại đường xoá cứng một `document` đã `ISSUED`.** Không có endpoint, không có thao tác quản trị, không có script vận hành nào xoá được. Văn bản chỉ mất hiệu lực bằng cách chuyển trạng thái.
- Mô hình dữ liệu hỗ trợ `REVOKED` và `SUPERSEDED` ngay từ Sprint đầu, kể cả khi màn hình thu hồi chưa có (F5 là Should). Số văn bản của một văn bản đã `ISSUED` **không bao giờ** được trả lại dải số để tái sử dụng, bất kể văn bản đó về sau ở trạng thái nào.

### F4 — Theo dõi trạng thái (Must)

**Pain point giải quyết:** không theo dõi được trạng thái.
**Request type:** mọi loại đang hỗ trợ.

**User stories**

1. Là nhân viên, tôi muốn biết yêu cầu của tôi đang ở bước nào mà không phải hỏi ai.
2. Là nhân viên, tôi muốn biết mình đang bị chờ vì lý do gì để xử lý ngay.
3. Là cán bộ hành chính, tôi muốn thấy hàng đợi của mình có gì và cái nào chờ lâu nhất.

**AC**

- Nhân viên xem được trạng thái `request` của mình theo đúng tên ở `GLOSSARY.md`, kèm diễn giải tiếng Việt, không hiển thị mã trạng thái trần.
- Khi `request` ở `NEEDS_INFO` hoặc `CHANGES_REQUESTED`, màn hình nêu rõ **thiếu gì hoặc cần sửa gì**, không chỉ nêu tên trạng thái.
- Cán bộ hành chính xem được hàng đợi mọi yêu cầu, sắp xếp được theo thời gian chờ.
- Trạng thái `request` và trạng thái artifact hiển thị riêng: `request` đã `FULFILLED` không có nghĩa artifact đã kết thúc đời của nó.

### F5 — Thu hồi văn bản đã phát hành (Should)

**Pain point giải quyết:** không có; đây là feature xử lý sự cố, không gỡ pain point nào ở mục 1.
**Request type:** `WORK_CONFIRMATION`, `INTRODUCTION_LETTER`.

**Vì sao là Should, không phải Must.** Trạng thái `REVOKED` **bắt buộc tồn tại** trong mô hình dữ liệu và máy trạng thái — đó là ràng buộc domain ở mục Ràng buộc domain bắt buộc phải xử lý của `CLAUDE.md` và đã chốt ở mục Vòng đời `document` của `00-domain.md`, không thương lượng. Nhưng "trạng thái phải tồn tại" và "màn hình thu hồi có trong Sprint đầu" là hai việc khác nhau. Ở `NON_PRODUCTION`, mọi văn bản đều mang watermark *không có giá trị pháp lý* và mang số từ dải `TRIAL`, nên **không có văn bản nào đang có hiệu lực để mà thu hồi**. Feature này chỉ trở nên cần thiết cùng lúc với milestone sản xuất.

Nghĩa vụ phải giữ ở Sprint đầu **không nằm ở đây mà nằm trong AC của F3 (Must)**: mô hình dữ liệu hỗ trợ `REVOKED` và `SUPERSEDED`, không có đường xoá cứng `document` đã `ISSUED`, và số đã cấp không tái sử dụng. Đặt ở F3 để cắt F5 không làm mất bất biến.

**AC**

- `document.revoke_initiate` và `document.revoke_confirm` là hai permission tách rời, phải do hai người khác nhau thực hiện, hoặc rơi vào đường thoát tự duyệt ở NFR-02.
- Thu hồi bắt buộc có `revocation_reason`. Văn bản `REVOKED` vẫn truy xuất được — thu hồi là đánh dấu mất hiệu lực, không phải xoá.

### F6 — Quản lý mẫu, danh mục loại yêu cầu và hồ sơ nhân viên (Must)

**Pain point giải quyết:** mẫu nằm rải rác không có cơ chế điền biến; soạn văn bản thủ công từ bản cũ.
**Request type:** mọi loại — đây là feature làm cho các loại khác tồn tại được.

**User stories**

1. Là cán bộ hành chính, tôi muốn tải mẫu `.docx` mới lên và hệ thống nhận ra các biến trong đó.
2. Là cán bộ hành chính, tôi muốn import CSV hồ sơ nhân viên và thấy rõ đợt import nào ghi đè cái gì.
3. Là cán bộ hành chính, tôi muốn thêm một loại yêu cầu mới mà không phải nhờ lập trình viên.

**AC**

- **Thêm một `request_type` thứ ba chỉ cần: một bản ghi cấu hình (slot schema, người duyệt, `requires_seal`, SLA) và một file template `.docx`. Không sửa code, không deploy lại.** Đây là AC cứng, được kiểm bằng cách thực sự thêm một loại thứ ba trong UAT.
- Template có phiên bản. Văn bản đã render ghi lại phiên bản template đã dùng. Bản gốc của mỗi phiên bản là bất biến.
- Tải template lên mà thiếu biến bắt buộc theo cấu hình loại yêu cầu thì bị từ chối, nêu rõ thiếu biến nào.
- Import CSV ghi `source` và `synced_at` cho từng bản ghi, và sinh `audit_event` cho đợt import.
- Hệ thống **không** kiểm tra thể thức của template. Trách nhiệm thể thức thuộc người soạn template (ADR-001); hệ thống chỉ kiểm sự có mặt của biến.

## 7. Non-functional requirements

### NFR-01 — HITL

Mọi văn bản đi qua **hai cổng người thật** trước khi phát hành: duyệt nội dung tại `PENDING_APPROVAL`, và duyệt dấu tại `PENDING_SEAL` khi `requires_seal = true`. Không có nhánh auto-approve, không có ngưỡng confidence nào bỏ qua được cổng, không có cấu hình tắt. Hai cổng là hai quyết định, hai permission (`document.approve_content` và `document.apply_seal`), hai `audit_event`. Áp dụng cho mọi feature, không lặp lại ở AC từng feature.

### NFR-02 — Tách biệt trách nhiệm

Khi `beneficiary_employee_id == approver_employee_id`, mọi permission duyệt bị chặn trên đối tượng đó (D-006). Cán bộ hành chính nhập hộ người khác rồi duyệt là **hợp lệ** — cái bị chặn là tự duyệt giấy tờ của chính mình.

Hệ thống **không giả định** tổ chức có từ hai người duyệt trở lên. Khi chỉ còn một người đủ quyền, cho phép tự duyệt nhưng chỉ khi đủ cả bốn: `self_approval_reason` không rỗng · cờ `approval_step.self_approved` · `audit_event` mức `WARNING` · hiện ở mục riêng trên dashboard. **Cấm** mọi phương án tự động bỏ qua kiểm tra — tắt cấu hình, whitelist, hay im lặng cho qua.

### NFR-03 — Chế độ phi sản xuất

**Vì sao chế độ này tồn tại.** Tổ chức **không có ai có thẩm quyền nghiệm thu thể thức** văn bản do hệ thống phát hành. Đây là kết luận đã chốt (A-018, D-009), **không phải một ô chờ lấp** — phase sau không hỏi lại. Hệ quả trực tiếp: residual risk của RISK-01 không có người gánh, nên hệ thống không được phép phát hành văn bản có giá trị pháp lý. Chế độ phi sản xuất là cách **xử lý** hệ quả đó, không phải cách bỏ ngỏ nó.

Chừng nào A-018 còn `Mở`, `operating_mode = NON_PRODUCTION` và ba ràng buộc sau bắt buộc đồng thời (D-009):

1. Mọi văn bản mang watermark `BẢN THỬ NGHIỆM — KHÔNG CÓ GIÁ TRỊ PHÁP LÝ` **trong bản render**, không phải một lớp hiển thị của giao diện.
2. `document_register` cấp số từ dải `TRIAL`, tách hẳn khỏi dải `OFFICIAL`. Dải thật không bị tiêu tốn số nào.
3. Không đóng dấu thật. Cổng `PENDING_SEAL` vẫn chạy đủ quy trình duyệt để luồng được kiểm thử, chỉ chặn hành vi vật lý.

Chuyển sang `PRODUCTION` phải là một hành động được ghi nhận và quy trách nhiệm được, **không phải sửa biến môi trường rồi deploy lại**.

### NFR-04 — Người dùng thưa

Nhân viên dùng hệ thống vài lần mỗi năm nên không có thói quen sử dụng. Thiết kế phải chịu được điều đó: hoàn tất một yêu cầu **không cần đào tạo trước, không cần đọc hướng dẫn**; không bắt nhân viên tự tra cứu thông tin của chính mình để nhập vào; không dùng thuật ngữ nội bộ hay mã trạng thái trần trong giao diện của họ; mọi thông báo lỗi nói rõ cần làm gì tiếp. Metric canh giữ: M3, và M7 sau khi mở sản xuất.

### NFR-05 — Bảo mật và dữ liệu cá nhân

Nhân viên chỉ xem được yêu cầu của mình.

**Mask trong log vận hành theo `slot_sensitivity`, không theo danh sách tên trường.** Slot mức `RES` và `PER` không xuất hiện dạng thật trong log kỹ thuật (log, trace, metric) — đây là log cho kỹ sư vận hành, khác với `audit_event`, vốn là nhật ký nghiệp vụ bất biến cho người dùng và kiểm toán, không nằm trong phạm vi mask này. Quy tắc key theo thuộc tính dữ liệu ở mục Slot schema của `00-domain.md`, nên thêm một slot mới là gán độ nhạy cho nó, không phải nhớ bổ sung tên nó vào một danh sách viết tay ở đây. Cùng thuộc tính đó quyết định dữ liệu nào bị xoá khi `request` `EXPIRED` (A-014).

**Sửa nguyên tắc cho prompt gửi LLM — phát hiện ở Phase 2, hệ quả ngoài dự kiến của việc thêm `slot_sensitivity` ở vòng A-014.** Bản trước viết "slot mức `RES` bị mask... trong prompt gửi LLM", nhưng đây là phát biểu **sai**: slot `RES` `purpose` và `work_content` chính là dữ liệu mà bước sinh nội dung tự do ở F2 phải đọc để soạn văn bản — che nó thì bước đó không làm được việc. Nguyên tắc đúng không phải "che thứ nhạy cảm" mà là **tối thiểu hoá theo nhu cầu từng bước**: mỗi prompt module (Phase 7) khai báo tường minh danh sách slot nó cần làm input; tầng gọi LLM (`ai_gateway`, mục System Architecture của `02-architecture.md`) chỉ đưa đúng danh sách đó vào prompt, bất kể mức nhạy cảm cao hay thấp của từng slot. Một slot `RES` như `national_id` không xuất hiện trong bất kỳ prompt sinh nội dung nào vì không bước nào khai cần nó; một slot `RES` như `purpose` xuất hiện đúng ở bước cần nó. Vi phạm là khi một prompt module nhận slot ngoài danh sách nó tự khai — không phải khi nó nhận một slot có độ nhạy cao.

**`slot_sensitivity` không mất vai trò mà chuyển sang chỗ khác.** Sau khi sửa, `slot_sensitivity` không còn quyết định slot nào được vào prompt gửi LLM — allowlist của prompt module làm việc đó. Nhưng nó vẫn là căn cứ duy nhất cho ba quyết định khác:

1. Slot nào bị mask trong log kỹ thuật.
2. Slot nào bị xoá giá trị khi `request` `EXPIRED` (A-014).
3. Slot nào hiển thị ở dạng nào trên màn hình duyệt. Quy tắc hiển thị cụ thể **chưa được đặc tả ở đâu cả** — thuộc Phase 8 (màn hình duyệt) và Phase 9.

Tức là có **hai cơ chế riêng dựa trên cùng một thuộc tính dữ liệu**, và cơ chế này không thay cơ chế kia. Một slot có thể vừa được allowlist cho vào prompt, vừa bị mask trong log của chính lời gọi đó — `purpose` rơi đúng vào trường hợp này. Thiết kế nào coi allowlist là đã xử lý xong độ nhạy — ví dụ bỏ mask log cho slot đã được phép vào prompt — là sai. Allowlist chỉ giới hạn slot nào **đi ra** khỏi hệ thống tới LLM provider; nó không làm slot đó bớt nhạy cảm. `purpose` đã gửi đi vẫn là dữ liệu `RES`, chỉ khác là giờ nó nằm ở một bên thứ ba.

Nội dung do người dùng nhập được đối xử là **dữ liệu, không phải chỉ dẫn**. Nghĩa vụ theo Nghị định 13/2023/NĐ-CP xử lý ở mức mục đích thu thập, thời hạn lưu và quyền của chủ thể; thời hạn lưu cụ thể `TBD` (A-010). Không trích dẫn điều khoản vì văn bản gốc chưa có trong `docs/reference/` — `[CẦN XÁC MINH]`.

### NFR-06 — Chi phí LLM

Model rẻ cho phân loại và trích slot, model mạnh cho soạn nội dung tự do. Khung thể thức không đi qua LLM nên không tốn token lặp lại ở mọi văn bản (ADR-001). Token budget mỗi request và ngưỡng cảnh báo: `TBD`, định cỡ ở Phase 11 khi có giả định giá (A-022).

**Hành vi khi chạm trần là cam kết sản phẩm, con số trần thì không.** Chạm trần token hoặc trần số lần render, hệ thống **không bao giờ** được âm thầm dừng giữa chừng và để lại một `document` dở dang. Nó phải dừng có kiểm soát và **chuyển cho người thật xử lý**, nêu rõ đã dừng ở đâu và vì sao. Một bản nháp thiếu nội dung nhưng trông hoàn chỉnh nguy hiểm hơn hẳn việc không có bản nháp nào. Cấm ghi giá token hay con số benchmark chưa xác minh.

### NFR-07 — Bộ eval

Bộ eval **dẫn xuất** chứ không chọn số tròn. Có hai nguồn dẫn xuất, và mỗi ca phải chỉ được về một trong hai:

1. **Bảng edge case ở mục Edge case nghiệp vụ của `00-domain.md`** — mỗi edge case áp dụng được cho phạm vi Sprint đầu sinh ít nhất một ca.
2. **Ba định nghĩa vận hành — hai ở F1, một ở F2** — mỗi ca "bị coi là KHÔNG đạt" sinh ít nhất một ca. Nguồn này tồn tại vì bảng edge case Phase 0 không đặc tả tới mức **từng biến của template** hay **từng đoạn nguồn của kho quy trình**; nếu chỉ dẫn xuất từ nguồn 1 thì định nghĩa "Văn bản đủ điều kiện trình duyệt" và định nghĩa "Hướng xử lý thủ công đủ căn cứ" có độ phủ eval bằng không.

Mọi ca thuộc **tầng hội thoại và phân loại** đều dẫn xuất từ nguồn 1 — nhóm `EC-CV-xx` ở mục Edge case nghiệp vụ của `00-domain.md`, bổ sung ở phiên bản 0.6 của file đó. Trước đó chúng không có nguồn Phase 0 nào; cách xử lý là **sửa Phase 0 rồi dẫn xuất lại**, không phải giữ chúng như ngoại lệ ở Phase 1.

| Nhóm | Cách dẫn xuất | Nguồn | Ca |
|---|---|---|---|
| A. Đủ điều kiện — happy path | 1 ca cho mỗi `request_type` đang hỗ trợ | — | 2 |
| B. Đủ điều kiện — biến thể có ràng buộc thêm | EC-WC-01 thử việc · EC-WC-02 đã nghỉ việc · EC-IL-03 cơ quan nhà nước | 1 | 3 |
| C. Thiếu thông tin | 1 ca cho mỗi slot `USER_INPUT` bắt buộc, bỏ trống từng cái: `WORK_CONFIRMATION` có `purpose`, `recipient_org`; `INTRODUCTION_LETTER` có `recipient_org`, `work_content`, `valid_from`, `valid_to` | 1 | 6 |
| D. Có giá trị nhưng không đủ điều kiện xử lý | Nhân viên không xác nhận giá trị `HR_PROFILE` · giá trị đề xuất lại từ `request` `EXPIRED` được tính là đã có dù nhân viên chưa xác nhận tường minh · slot có ký tự nhưng rỗng nội dung, ví dụ `purpose` là "cần gấp" · lời khai mâu thuẫn với `HR_PROFILE`, ví dụ khai đã nghỉ việc nhưng `employment_end_date` rỗng | 2 — F1 | 4 |
| E. Không đủ điều kiện theo quy chế | EC-IL-01 chưa có uỷ quyền · EC-IL-02 vượt trần hiệu lực | 1 | 2 |
| F. Ngoài phạm vi | EC-WC-03 đòi ghi lương · `ROOM_BOOKING` chưa hỗ trợ · `SEAL_REQUEST` văn bản ngoài chưa hỗ trợ · yêu cầu không thuộc hành chính | 1 | 4 |
| G. Phân loại ý định | EC-CV-01 → 2 ca: hai nhu cầu đều thuộc loại đang hỗ trợ · một nhu cầu hỗ trợ kèm một chưa hỗ trợ. EC-CV-02 → 1 ca: đổi loại giữa chừng. EC-CV-03 → 2 ca: nhập nhằng giữa hai loại đang hỗ trợ · từ ngữ của `INCOME_CONFIRMATION` nhưng ý định là `WORK_CONFIRMATION` | 1 | 5 |
| H. Văn bản không đủ điều kiện trình duyệt | Agent thêm câu chữ vào phần khung · render từ phiên bản template không còn hiệu lực · agent tự đặt giá trị hợp lý cho biến nhân viên chưa xác nhận · thiếu một biến "không quan trọng" | 2 — F2 | 4 |
| I. Liên tục hội thoại | EC-CV-04 → 2 ca: quay lại trong hạn · quay lại sau `EXPIRED` | 1 | 2 |
| J. Hướng xử lý thủ công | Một ca cho mỗi ca KHÔNG đạt của định nghĩa "Hướng xử lý thủ công đủ căn cứ": đoạn nguồn thiếu chi tiết nhân viên hỏi · cùng quy trình có hai phiên bản, chỉ bản mới còn hiệu lực · có đoạn được truy hồi nhưng không đoạn nào liên quan · **kho rỗng**. Cộng 1 happy path cho **nhánh có kho**. Nhánh kho rỗng được phủ bởi ca thứ tư. Chạy trên kho quy trình giả lập, đánh dấu là dữ liệu giả | 2 — F1 | 5 |
| | **Tổng** | | **37** |

**Trục chia nhóm là *đáp án chuẩn khẳng định cái gì*, không phải *ca dẫn xuất từ đâu*.** Nhóm G và nhóm I cùng dẫn xuất từ `EC-CV-xx` nhưng chấm hai thứ khác nhau: G chấm agent có nhận đúng ý định không, I chấm agent có khôi phục hoặc bỏ đúng trạng thái không. Chính sách giữ hay xoá dữ liệu khi `EXPIRED` không đổi đáp án của bất kỳ ca nào ở G — đó là dấu hiệu cho thấy hai nhóm này tách được và phải tách.

Cùng trục đó tách **nhóm F** khỏi **nhóm J**. F chấm việc agent nhận ra yêu cầu ngoài phạm vi và không ép nó vào một loại gần giống — đáp án không phụ thuộc kho quy trình. J chấm phần hướng xử lý — đáp án đổi theo trạng thái kho. Trạng thái kho đổi đáp án của J mà không đổi đáp án của bất kỳ ca nào ở F.

**EC-CV-02 chấm hai tiêu chí, và phải chấm TÁCH RỜI**, không gộp thành một điểm:

| Tiêu chí | Đạt khi |
|---|---|
| Phân loại | Agent nhận ra nhân viên đã đổi sang `request_type` khác và xác nhận việc đổi |
| Không mang slot cũ sang | Không slot nào của loại cũ được tự động điền vào loại mới, kể cả khi trùng tên |

**Phân loại đúng mà mang slot cũ sang vẫn là TRƯỢT.** Gộp một điểm thì tiêu chí thứ hai — vốn là chế độ hỏng nguy hiểm hơn — bị điểm phân loại che mất.

**Một ca cố tình không đếm hai lần.** Chiều còn lại của EC-CV-03 — dùng từ ngữ của loại **đang** hỗ trợ nhưng ý định thuộc loại **chưa** hỗ trợ — chính là EC-WC-03, đã có ở nhóm F. Nhóm G chỉ lấy hai chiều còn lại.

**Hai ca cố tình không đưa vào bộ eval**, và lý do — cả hai đều là edge case Phase 0 nhưng không phải ca kiểm thử hành vi agent:

- **EC-SR-01** (đòi dấu cho văn bản chưa ký). Phần thuộc Sprint đầu là **bất biến của máy trạng thái**: `PENDING_SEAL` chỉ nhận `document` ở `SIGNED`, và đường đi thẳng từ `DRAFT` hay `APPROVED` tới `PENDING_SEAL` **không tồn tại**. Trong phạm vi Sprint đầu nhân viên không tự xin dấu — đóng dấu là một bước trong vòng đời văn bản (D-003) — nên không có input hội thoại nào kích hoạt được ca này. Nửa còn lại của EC-SR-01 thuộc `SEAL_REQUEST`, đang ở mức **Could**. Kiểm bằng **M4**, không bằng bộ eval.
- **EC-SR-05** (gộp duyệt nội dung và duyệt dấu thành một thao tác). Đây là ca kiểm thử **permission và giao diện người duyệt**, không phải hành vi agent. Kiểm bằng test permission và **M4**, không bằng bộ eval.

Đưa hai ca này vào bộ eval sẽ là viết eval cho một tính năng chưa tồn tại và cho một thứ agent không tham gia.

Phân bố này **chốt trước khi đo**, không chỉnh sau khi thấy kết quả. Khi thêm `request_type`, thêm edge case, hoặc thêm một ca "KHÔNG đạt" vào các định nghĩa vận hành, bộ eval mở rộng theo đúng công thức dẫn xuất trên chứ không thêm ca tuỳ ý. **Đáp án chuẩn do Trưởng phòng Hành chính duyệt** — không phải PO, không phải team kỹ thuật.

### NFR-08 — Hiệu năng

Không đặt ngưỡng p95 trong Sprint đầu vì chưa có số liệu tải (A-002) và ràng buộc Render chưa được khảo sát (Phase 11). Yêu cầu tối thiểu: thao tác chat có phản hồi tăng dần để người dùng biết hệ thống đang làm việc; thao tác duyệt và cấp số không để người dùng chờ mà không có trạng thái.

## 8. Definition of Done

Sprint đầu done khi:

1. **Hành trình end-to-end chạy được cho một `request_type`**: nhân viên đăng nhập → mô tả nhu cầu bằng chat → agent phân loại và hỏi đủ slot → nhân viên xác nhận giá trị `HR_PROFILE` → gửi → cán bộ hành chính duyệt nội dung → duyệt dấu → cấp số và phát hành → nhân viên thấy trạng thái `FULFILLED` và tải được văn bản có watermark.
2. Toàn bộ **Must features (F1, F2, F3, F4, F6)** đạt AC cấp feature ở mục 6.
3. **Đạt toàn bộ metric loại Bất biến** ở mục 2 — M8, M4, M5, M6 — trên bộ eval 37 ca và buổi UAT. Đây là ngưỡng tuyệt đối, không thương lượng.

   Metric loại **Cảnh báo** (M1, M2, M3) **không** phải điều kiện nghiệm thu. Ngưỡng của chúng do chọn và chưa hiệu chỉnh (A-019), nên dùng chúng làm cổng nghiệm thu sẽ là lấy một con số vô căn cứ để quyết định Sprint đầu done hay không. Không đạt thì **ghi nhận và mở rà soát**, không trượt nghiệm thu.
4. AC cứng của F6 được chứng minh bằng cách **thực sự thêm một `request_type` thứ ba trong UAT** bằng cấu hình và một file template, không sửa code.

M7 và milestone sản xuất **không** thuộc Definition of Done này.

## 9. Risk register

*(Mục này bổ sung so với `docs/reference/sample_prd.md` — lý do ở cuối file.)*

| ID | Rủi ro | Likelihood | Impact | Mitigation | Trigger phát hiện | Residual risk |
|---|---|---|---|---|---|---|
| RISK-01 | Văn bản sai thể thức → vô hiệu, bị bên nhận từ chối | Trung bình | Cao | Khung thể thức nằm trong template do người soạn, không do model sinh (ADR-001); HITL tại `PENDING_APPROVAL`; `NON_PRODUCTION` chặn phát hành thật (NFR-03) | Bên nhận từ chối văn bản; đối chiếu ngược với văn bản mẫu thật (A-018) | **Còn lại:** nếu template sai thể thức **và** cán bộ hành chính không phát hiện khi duyệt, văn bản sai vẫn được phát hành. Không có lớp kiểm soát tự động nào phía sau — hệ thống không có khả năng thẩm định thể thức. Chấp nhận có ý thức |
| RISK-02 | Agent phân loại sai `request_type` → sinh đúng thể thức nhưng **sai loại văn bản** | Trung bình | Cao | Agent hỏi lại khi nhập nhằng thay vì đoán (AC F1); nhóm G trong bộ eval với ngưỡng **M8 = 0 ca sai**; tiêu đề loại văn bản hiển thị nổi bật trên màn hình duyệt | M8 trên nhóm G của bộ eval; văn bản bị từ chối ở `PENDING_APPROVAL` với lý do sai loại | **Còn lại:** đây là loại lỗi nguy hiểm nhất vì văn bản **trông hoàn toàn đúng** — đúng thể thức, đúng tên, đúng ngày, chỉ sai loại. Người duyệt quen tay rất dễ bỏ qua. Mitigation dựa vào sự chú ý của con người, thứ suy giảm theo số lượng văn bản duyệt mỗi ngày |
| RISK-03 | Nhân viên không dùng hệ thống, quay lại gửi email | Cao | Cao | NFR-04 về ma sát thấp; M3 đo được ở UAT | **M7** — tỷ lệ yêu cầu vào qua hệ thống trên tổng yêu cầu phòng hành chính nhận | **Còn lại:** M7 chỉ đo được sau khi mở milestone sản xuất. Trước mốc đó, chế độ hỏng này **không quan sát được** bằng bất kỳ metric nào — M1–M6 chỉ nhìn thấy những gì đã vào hệ thống. Đây là điểm mù đã biết, không phải điểm mù bị bỏ sót |
| RISK-04 | Template sai hoặc thiếu biến → mọi văn bản sinh từ nó đều sai | Thấp | Cao | Kiểm biến khi tải template lên (AC F6); template có phiên bản, văn bản ghi lại phiên bản đã dùng | Hàng loạt văn bản cùng loại bị trả lại cùng một lý do | **Còn lại:** hệ thống chỉ kiểm **sự có mặt** của biến, không kiểm **nội dung** khung. Template là điểm lỗi tập trung: một file sai làm hỏng mọi văn bản cùng loại cho tới khi có người nhận ra |
| RISK-05 | Prompt injection qua văn bản người dùng nhập | Thấp | Trung bình | Nội dung do người dùng nhập được đối xử là dữ liệu, không phải chỉ dẫn (NFR-05); LLM chỉ sinh nội dung tự do, không chạm khung thể thức và không gọi tool ghi dữ liệu ở bước soạn thảo | Nội dung văn bản chứa câu chữ không đến từ slot nào | **Còn lại:** hẹp trong Sprint đầu. ADR-001 đã bịt phần lớn bề mặt — khung thể thức không do model sinh nên không bị chèn qua prompt; và văn bản ngoài do người dùng tải lên, bề mặt injection lớn nhất, hiện ở mức **Could** nên chưa tồn tại. Còn lại chủ yếu là text nhân viên tự nhập vào slot, đi vào phần nội dung tự do. Rủi ro này **sẽ tăng đáng kể** khi `SEAL_REQUEST` được kích hoạt, và phải đánh giá lại tại thời điểm đó |
| RISK-06 | Hồ sơ `employee` cũ so với thực tế → văn bản ghi sai thông tin nhân sự | Trung bình | Trung bình | Agent chỉ đề xuất, nhân viên xác nhận từng giá trị, người duyệt thấy `source` và `synced_at` (D-002) | Nhân viên từ chối xác nhận giá trị đề xuất; lệch giữa lời khai và hồ sơ | **Còn lại:** ngưỡng để cảnh báo `synced_at` quá cũ chưa có căn cứ (A-017), nên việc đánh giá độ cũ phụ thuộc vào người đọc màn hình duyệt |
| RISK-07 | Chi phí LLM vượt dự kiến | Trung bình | Trung bình | Model routing theo bước; khung thể thức không qua LLM (ADR-001) | Chi phí mỗi request vượt ngưỡng cảnh báo | **Còn lại:** chưa có ngưỡng vì chưa có giả định giá (NFR-06). Không đo được cho tới Phase 11 |

---

**Lý do thêm mục Risk register so với mẫu:** `sample_prd.md` là PRD của một sản phẩm tra cứu — sai thì người dùng đọc lại nguồn và tự sửa. BO-19 phát hành văn bản có giá trị pháp lý và sử dụng con dấu, nên có một lớp rủi ro không hồi phục được mà mẫu không cần đến. Risk register tồn tại để những rủi ro đó được ghi tên, có mitigation, có trigger phát hiện, và quan trọng nhất là **có phần còn lại sau mitigation được nói thẳng** thay vì để người đọc tưởng đã xử lý xong.

## Open Questions

**Không có câu hỏi mở nào chỉ tồn tại trong PRD.**

Mọi câu hỏi chưa có lời giải đều nằm ở [`ASSUMPTIONS.md`](./ASSUMPTIONS.md), mỗi dòng có **Owner** và **Hạn** riêng. PRD **không** giữ bản sao của bảng đó — một câu hỏi có hai chỗ ghi hạn là một câu hỏi sẽ có hai hạn khác nhau.

Các giả định PRD này phụ thuộc trực tiếp: A-002 (baseline), A-009 (định dạng số), A-011 (trần `copies_count` và trần hiệu lực), A-017 (ngưỡng `synced_at`), A-018 (nghiệm thu thể thức), A-019 (ngưỡng metric Cảnh báo), A-020 (hình hài UAT), A-023 (đáp án chuẩn bộ eval), A-027 (kho quy trình hành chính chưa tồn tại — AC ngoài phạm vi của F1 được thiết kế để đúng cả khi kho rỗng), A-033 (quyền nạp kho quy trình).
