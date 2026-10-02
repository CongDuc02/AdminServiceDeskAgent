# ADR-032 — Nhà cung cấp LLM cho hai tier: một nhà cung cấp, chọn theo hai mốc dữ liệu

**Trạng thái:** Proposed — chưa chọn nhà cung cấp nào; **danh sách ngắn mốc 1 của PO và hồ sơ ứng viên ở mục Danh sách ngắn của mốc 1 (2026-10-02)**. **Vế hai mốc (điều 2, 3 của mục Decision): PO duyệt 2026-09-27, kèm điều kiện eval ở điều 3.** Điều 1 và điều 4 vẫn là đề xuất · **Ngày:** 2026-09-27 · **Quyết định tại:** A-026 (cổng 1.5 của `12-roadmap.md`) · **Liên quan:** mục Yêu cầu năng lực của model — provider chưa chọn và mục Allowlist input của `03-agents.md`, ADR-007, ADR-008, ADR-019, mục Chiến lược ép JSON và xử lý lỗi parse của `07-prompts.md`, A-028 (embedding), A-079, A-080, cổng 4.4 của `12-roadmap.md`

---

## Context

AC-1.1 đòi lời gọi LLM thật, nên cổng 1.5 đòi chọn nhà cung cấp và model cho hai tier. Năng lực bắt buộc đã khai ở mục Yêu cầu năng lực của model — provider chưa chọn của `03-agents.md`. `ai_gateway` được thiết kế độc lập provider: output contract là JSON Schema đóng (ADR-007), và chiến lược ép JSON viết cho hai nhánh năng lực. Chọn provider về sau là chọn nhánh, không viết lại prompt module (đường vòng của A-026).

**Dữ liệu gì rời hệ thống — theo mục Allowlist input của `03-agents.md`:**

| Tier | Prompt module | Input mang dữ liệu cá nhân |
|---|---|---|
| Rẻ | `classify_intent`, `extract_slots` | `current_turn_text` — tin nhắn thô của lượt hiện tại. **Có thể mang mọi thứ**, kể cả dữ liệu `RES` chưa gán vào slot nào |
| Mạnh | `draft_free_content`, `revise_free_content` | `purpose` (`RES`) với `WORK_CONFIRMATION`; `work_content` với `INTRODUCTION_LETTER` |
| — | Không module nào | Giá trị `HR_PROFILE`, `national_id` — không bao giờ tới provider (NFR-05) |

Như vậy **cả hai tier** đều nhận dữ liệu cá nhân khi hệ thống chạy với người thật. Câu hỏi chuyển dữ liệu ra nước ngoài áp cho cả hai, không riêng tier mạnh.

**Vế chuyển dữ liệu cá nhân ra nước ngoài.** Căn cứ là Luật Bảo vệ dữ liệu cá nhân năm 2025 và Nghị định 356/2025/NĐ-CP. **Chưa có văn bản gốc trong `docs/reference/` (A-080), nên mọi nội dung nghĩa vụ là `[CẦN XÁC MINH]`.** ADR này không phán quyết pháp lý. Nó chỉ nêu bốn câu hỏi mà văn bản gốc phải trả lời trước khi dữ liệu thật đi ra:

1. Gửi dữ liệu tới API của một nhà cung cấp xử lý ở nước ngoài có phải là "chuyển dữ liệu cá nhân ra nước ngoài" theo nghĩa của văn bản không?
2. Nếu có, bên chuyển phải làm gì **trước** lần chuyển đầu tiên, và có trường hợp nào được miễn không?
3. Bên nhận — nhà cung cấp — phải cam kết gì, và cam kết đó phải nằm ở loại văn bản nào?
4. Dữ liệu giả, không gắn với người thật, có nằm ngoài phạm vi không? Theo lẽ thường là có, vì không có chủ thể dữ liệu. Nhưng đây là suy luận, không phải trích dẫn.

## Options

Các phương án theo **hình dạng**, không theo tên nhà cung cấp — năng lực của từng nhà cung cấp chưa được xác minh:

- **A — Một nhà cung cấp API, xử lý ở nước ngoài, cho cả hai tier** — hai model của cùng nhà cung cấp.
- **B — Hai nhà cung cấp khác nhau cho hai tier.**
- **C — Một nhà cung cấp xử lý dữ liệu trong lãnh thổ Việt Nam cho cả hai tier** — nhà cung cấp trong nước, hoặc một vùng xử lý đặt tại Việt Nam của nhà cung cấp quốc tế. Có ứng viên nào như vậy đáp ứng bảng năng lực hay không: `[CẦN XÁC MINH]`.
- **D — Model open-weight tự vận hành.**

### So sánh theo tính chất suy ra được từ chính thiết kế

Bảng dưới chỉ chứa điều suy ra được từ hình dạng phương án và từ thiết kế đã chốt. Không ô nào nói về năng lực, giá hay điều khoản của một nhà cung cấp cụ thể.

| Tiêu chí | A | B | C | D |
|---|---|---|---|---|
| Số bộ điều khoản xử lý dữ liệu phải đọc và ký | 1 | 2 | 1 | 0 ở ngoài; toàn bộ vận hành ở mình |
| Số lần xét nghĩa vụ chuyển dữ liệu ra nước ngoài, nếu câu hỏi 1 trả lời "có" | 1 | Tới 2 | 0 nếu xử lý thật sự trong nước `[CẦN XÁC MINH]` | 0 |
| Số adapter provider trong `ai_gateway` | 1 | 2 | 1 | 1, cộng hạ tầng phục vụ model |
| Chạy từ Render | Gọi HTTPS | Gọi HTTPS | Gọi HTTPS | Cần máy chạy model. Render có loại instance phù hợp hay không: `[CẦN XÁC MINH]` |
| Ép JSON Schema phía provider | `[CẦN XÁC MINH]` — thiếu thì dùng nhánh tự validate | Như A, cho từng provider | Như A | Tuỳ phần mềm phục vụ model `[CẦN XÁC MINH]` |
| Chất lượng tiếng Việt, văn phong hành chính | **Chỉ đo được bằng bộ eval** (Phase 10) — không nhận lời quảng cáo làm căn cứ | Như A | Như A | Như A |
| Chi phí | `TBD` — giá `[CẦN XÁC MINH]`, tải là A-002 | Như A | Như A | Chi phí hạ tầng thay cho giá token |

### Hồ sơ phải có của mỗi ứng viên trong danh sách ngắn

Đặt bản gốc vào `docs/reference/`, ghi ngày lấy, **trước khi** điền bất kỳ ô nào của bảng năng lực:

1. Điều khoản xử lý dữ liệu: có dùng dữ liệu gửi đi để huấn luyện không, thời hạn lưu, xoá theo yêu cầu.
2. Vị trí xử lý và lưu trữ dữ liệu; có cho chọn vùng xử lý không.
3. Tài liệu cơ chế structured output — ép theo schema, hay chỉ ép JSON.
4. Bảng giá theo token của đúng model dự định dùng, kèm ngày lấy.
5. Giới hạn: độ dài context, rate limit của gói dự định mua.

## Decision — đề xuất

1. **Một nhà cung cấp cho cả hai tier — A hoặc C.** Chọn giữa A và C bằng câu trả lời cho bốn câu hỏi pháp lý ở trên, rồi bằng bộ eval. B và D bị loại (mục Rejected alternatives).
2. **Tách quyết định thành hai mốc, theo loại dữ liệu đi ra:**
   - **Mốc 1 — cổng 1.5: nhà cung cấp cho `dev` và local, chỉ dữ liệu giả.** Điều kiện:
     - hồ sơ 1, 3, 4 của ứng viên đã có trong `docs/reference/`;
     - luật vận hành: **từ Sprint 1 tới trước mốc 2, không nhập dữ liệu thật vào chat**. Chỉ dùng `employee` giả đánh dấu là giả, đúng như AC-1.1 đã ghi. Luật này phải ghi vào tài liệu cho người thử ở Sprint 1.

     Mốc này không đợi A-080, vì — theo suy luận ở câu hỏi 4 — không có dữ liệu cá nhân nào rời hệ thống.
   - **Mốc 2 — trước lần đầu dữ liệu nhân viên thật vào hệ thống: nhà cung cấp cho `staging` và `prod`.** Cùng điều kiện kích hoạt với cổng 4.4 — "hạn sớm hơn nếu dữ liệu cá nhân thật được nạp trước cổng này". Điều kiện: A-080 đã có văn bản gốc và bốn câu hỏi đã có trả lời; đủ năm hồ sơ; bộ eval đạt trên chính nhà cung cấp này.
3. **Mốc 2 được phép chọn nhà cung cấp khác mốc 1 — kèm điều kiện của PO (2026-09-27):** nếu mốc 2 chọn nhà cung cấp **khác** mốc 1, thì **trước khi hệ thống nhận dữ liệu thật**, chạy lại **toàn bộ** bộ eval của `10-eval.md` trên nhà cung cấp mới:
   - mọi bộ ở mục Golden dataset — bộ eval hành vi 37 ca, canary suite, bộ đo retrieval nếu đã có dữ liệu để chạy, ca kiểm cơ chế graph;
   - chạy theo mục Offline eval, và phải qua mục Regression gate — đổi provider vốn đã là một điều kiện kích hoạt ở đó.

   Không chạy đủ hoặc không qua thì không nhận dữ liệu thật: mốc 2 chưa đạt. Cái giá còn lại: viết adapter mới trong `ai_gateway`. Prompt module không đổi (đường vòng của A-026).
4. **Embedding (A-028) ngoài phạm vi ADR này.** Retrieval vào ở Sprint 2. Cùng khung hai mốc áp được cho embedding khi tới lúc.

## Consequences

**Tích cực**

- Cổng 1.5 không còn phải đợi văn bản pháp lý gốc — thứ không nằm trong tay đội.
- Câu hỏi pháp lý được hỏi đúng một lần cho một nhà cung cấp. B nhân đôi việc đó.
- Luật "không dữ liệu thật trước mốc 2" nói ra thành lời một điều Sprint 1 vốn đã làm.

**Tiêu cực và cái phải chấp nhận**

- **Mốc 1 dựa trên một suy luận, không phải trích dẫn** — câu hỏi 4. Nếu văn bản gốc nói khác, mốc 1 phải dời theo mốc 2.
- **Luật "không dữ liệu thật" là kiểm soát bằng quy trình**, không phải bằng máy. Người thử gõ dữ liệu thật vào chat thì dữ liệu đó đi ra. Mitigation: dải báo chế độ thử nghiệm trên `client` (Sprint 1) và tài liệu cho người thử; không có chặn kỹ thuật.
- Đổi nhà cung cấp ở mốc 2 làm mất giá trị các số đo chất lượng đã có trên nhà cung cấp mốc 1.
- Một nhà cung cấp cho hai tier là **một điểm hỏng**: provider sập thì cả intake lẫn soạn thảo dừng. Chấp nhận ở quy mô hiện tại. Nhánh lỗi đã có: khuôn "hệ thống đang bận" cho `intake_agent`; retry của job rồi `halt_for_human` cho `drafting_agent`.

**Điều kiện đảo ngược**

- Không nhà cung cấp nào đáp ứng cả hai tier → xét B.
- Văn bản gốc (A-080) cấm hoặc làm quá nặng việc chuyển ra nước ngoài, và không có ứng viên C nào đạt bộ eval → xét D, với ADR riêng về hạ tầng.

## Rejected alternatives

**B — Hai nhà cung cấp.** Nhân đôi hồ sơ pháp lý và điều khoản, thêm một adapter, mà chưa có lợi ích nào được chỉ ra. Giữ làm điều kiện đảo ngược đầu tiên.

**D — Model tự vận hành.** Đưa vào dự án một hạ tầng phục vụ model mà tech stack bắt buộc của `CLAUDE.md` không có, chưa biết Render có chạy được không, và thêm gánh vận hành cho một đội mà năng lực còn chưa biết (A-071). Chỉ xét khi văn bản gốc chặn A và không có C.

## Danh sách ngắn của mốc 1 — PO, 2026-10-02

PO gửi danh sách ngắn; người triển khai lập hồ sơ 1, 3, 4, 5 cho từng ứng viên và đo token của P1, P2. Mọi dữ kiện dưới đây lấy từ tài liệu tham chiếu ghi ở từng dòng, lấy ngày 2026-10-02 — không dữ kiện nào ghi từ trí nhớ.

| Ứng viên | Hồ sơ 1 — dữ liệu | Hồ sơ 3 — structured output | Hồ sơ 4 — giá · 5 — giới hạn | Kết luận |
|---|---|---|---|---|
| **Groq** — `openai/gpt-oss-20b` tier rẻ, `openai/gpt-oss-120b` tier mạnh (`docs/reference/llm-groq.md`) | Mặc định không lưu dữ liệu suy luận; log tạm tối đa 30 ngày khi khắc phục sự cố hay điều tra lạm dụng; bật được Zero Data Retention. Services Agreement 8.1 chỉ cấp quyền cần để cung cấp dịch vụ — **không có câu "không huấn luyện" nguyên văn**. Lưu ở Mỹ | `strict: true` có cho cả hai model — constrained decoding; mọi property phải `required` | Free: RPM 30, RPD 1K, TPM 8K, TPD 200K mỗi model — bảng của tab Free, suy luận từ HTML, xác nhận khi có key | **Đạt điều kiện mốc 1**, kèm hai giới hạn ở dưới |
| **Mistral** — Free mode, PO đã tắt training (`docs/reference/llm-mistral.md`) | Commercial Terms 4.2: không huấn luyện, **trừ** khi chưa opt-out ở sản phẩm mặc định bật, hoặc dùng model Labs, Preview | Có `strict` | Con số chỉ có trên trang Limits của tài khoản — `[CẦN XÁC MINH]`. Model hai tier: PO chưa chọn | **Chưa đủ hồ sơ** — thiếu giới hạn, model, bằng chứng đã tắt training, vị trí xử lý dữ liệu |
| **GitHub Models** — dự phòng (`docs/reference/llm-github-models.md`) | — | — | — | **Loại**: trang chính thức ghi dịch vụ đã ngừng hoàn toàn từ 30/07/2026 |
| **Gemini, gói free** | — | — | — | **Loại theo PO**: dùng dữ liệu để cải thiện sản phẩm, trái mục Yêu cầu năng lực của model — provider chưa chọn của `03-agents.md`. Căn cứ do PO nêu; bản gốc chưa có trong `docs/reference/` |
| **OpenRouter** — `openai/gpt-4o-mini`; **ngoại lệ PO cho phép**, trả phí bằng credit (`docs/reference/llm-openrouter.md`) | Dữ liệu qua **hai** bên: OpenRouter và OpenAI hoặc Azure. Tắt được định tuyến tới provider có huấn luyện; chính sách riêng của OpenRouter và của OpenAI, Azure: `[CẦN XÁC MINH]` | Có `structured_outputs` cho endpoint này; mức tuân thủ `strict` tuỳ provider | Giá từ API: 0,00000015 USD mỗi token vào, 0,0000006 mỗi token ra. Không công bố TPM, TPD cho model trả phí | Dùng được làm **ngoại lệ** — trái A-085 (gói free), PO chấp nhận |

**Token đo được** (`docs/reference/llm-token-count-p1-p2.md`, đếm offline, chưa gồm khung chat và token suy luận): một lượt chat — P1 và P2, đầu vào cộng đầu ra hiển thị — khoảng **1.663 token** với tin nhắn ngắn, **2.657** với tin nhắn trần WV-15, theo `o200k_harmony` và `o200k_base`; **1.829** và **2.895** theo `tekken_240911`.

**So với gói Free của Groq:** TPM 8K cho khoảng **3–4 lượt chat mỗi phút cho cả tổ chức**, TPD 200K cho khoảng **75–120 lượt mỗi ngày** — cận trên, trước khi trừ token suy luận của `gpt-oss`, mặc định mức `medium`. Đủ cho một người thử và cho một lượt bộ eval mỗi lần. **Có thể không đủ cho buổi UAT nhiều người** — kiểm lại khi có số đo thật và con số A-020.

**Hai phát hiện chạm thiết kế:**

1. **`strict` của Groq đòi mọi property nằm trong `required`.** `ClassifyIntentResult` ở mục Output contract — JSON Schema đóng của `07-prompts.md` để `secondary_intent`, `retrieval_query` ngoài `required`, dù cả hai đã cho `null`. Đề xuất: đưa hai trường vào `required` — đúng cho mọi nhánh ép JSON, không riêng Groq. **Chưa áp** — chờ PO.
2. **Tin nhắn trần WV-15 đẩy đầu vào P1 chạm trần 1.500 token** của mục Định cỡ A-022 của `11-ops.md`: 1.467 theo `o200k`, 1.602 theo `tekken`, chưa cộng khung chat. Hai hướng: hạ WV-15, hoặc nâng trần của `classify_intent`. **Chưa áp** — chờ số đo thật từ `usage` của API.

**Khuyến nghị cho mốc 1: Groq** — `gpt-oss-20b` tier rẻ, `gpt-oss-120b` tier mạnh. Lý do: là ứng viên duy nhất đủ hồ sơ 1, 3, 4, 5 từ nguồn công khai; gói free; `strict` cho cả hai model; mặc định không lưu dữ liệu và có Zero Data Retention. **Dự phòng:** OpenRouter `gpt-4o-mini` cho tier rẻ — ngoại lệ PO đã cho phép — nếu giới hạn TPM của Groq chặn công việc. **Mistral** xét lại khi PO đưa được con số Limits, tên model và bằng chứng đã tắt training. Tier mạnh để bộ eval quyết, đúng chỉ đạo của PO.

**Điều kiện trước lần gọi đầu, áp cho ứng viên được chọn:** bật Zero Data Retention (Groq) hoặc tắt định tuyến tới provider có huấn luyện (OpenRouter); ghi bằng chứng cấu hình vào tài liệu tham chiếu của ứng viên; chỉ dữ liệu giả — luật của mốc 1.

## Open Questions

- **Danh sách ngắn** ứng viên cho mốc 1 — PO lập, như PO lập danh sách ngắn nhà cung cấp object storage cho S7. ADR này không xếp hạng nhà cung cấp nào. **Thêm 2026-10-02 (A-085, F14):** giai đoạn build chỉ dùng gói free — danh sách ngắn chỉ gồm ứng viên có gói free, và năng lực bắt buộc không hạ. Điều khoản dữ liệu phải đọc cho **chính gói free** của ứng viên.
- Bốn câu hỏi pháp lý ở mục Context — chờ văn bản gốc (A-080), có thể cần pháp chế trả lời (cùng người với A-079).
- Tài liệu cho người thử ở Sprint 1, mang luật "không dữ liệu thật", đặt ở đâu — quyết khi chuyển BUILD MODE.
