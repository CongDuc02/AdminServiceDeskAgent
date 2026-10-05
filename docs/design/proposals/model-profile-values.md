# Đề xuất giá trị hồ sơ model — tham số ảnh hưởng output và trần output cứng

**Trạng thái:** ✅ **PO duyệt làm giá trị khởi đầu, nhãn "chưa hiệu chỉnh" (2026-10-05)** — đã vào `model_profiles.json` (B4b). Nếu đo cho thấy `max_completion_tokens` tính cả `reasoning_tokens` thì đề xuất lại 512/1536/2048 **trước khi dùng thật** (PO). · **Ngày:** 2026-10-05 · **Người đề xuất:** người triển khai · **Theo:** A-090 (3), quyết định PO 2026-10-05 · **Nguồn tham số:** `docs/reference/llm-groq-chat-params.md`, `docs/reference/llm-groq.md` mục 6c

Mọi giá trị dưới đây là **lựa chọn có lý do**, không phải số đo. Cột Nguồn nói tài liệu nào căn cứ cho *tham số* và *miền giá trị*; **giá trị cụ thể** thì không nguồn nào cho — nên đều nhãn "chưa hiệu chỉnh" cho tới khi có bộ eval của `10-eval.md`. Đổi bất kỳ giá trị nào là một dòng `CHANGELOG.md` và kích hoạt Regression gate (ADR-035, điều kiện 2).

## 1. Tham số lấy mẫu và suy luận — mỗi tier

| Tham số | `CHEAP` — `openai/gpt-oss-20b` | `STRONG` — `openai/gpt-oss-120b` | Nguồn và lý do |
|---|---|---|---|
| `reasoning_effort` | `"low"` | `"medium"` | `low`: chỉ đạo của PO (ADR-035). `medium`: **bằng mặc định đã ghi của Groq** — chỉ chuyển từ ngầm định sang tường minh, không đổi hành vi. Miền `low`/`medium`/`high`: `llm-groq.md` mục 6c |
| `temperature` | `0.2` | `0.3` | Tài liệu: "lower values like 0.2 will make it more focused and deterministic"; miền 0–2, mặc định 1. P1 và P2 là phân loại và trích — cần ổn định. P4 soạn văn bản hành chính ngắn — cần ổn định hơn mặc định 1 nhưng cho chút biến thiên khi sinh lại sau trượt kiểm (mục P4 của `07-prompts.md`) |
| `top_p` | **không đặt** (mặc định 1) | **không đặt** | Tài liệu: "We generally recommend altering this or top_p but not both" — đã đổi `temperature` |
| `seed` | **không đặt** | **không đặt** | "Determinism is not guaranteed" — đặt `seed` cho cảm giác tất định giả |
| `reasoning_format`, `include_reasoning` | **không đặt ở B4** | **không đặt ở B4** | Trang không nói `gpt-oss` có hỗ trợ không; hai tham số loại trừ nhau. Đo ở B4b — nếu `message.content` lẫn suy luận thì mới cần |

"Không đặt" ở đây là quyết định **tường minh có ghi trong đề xuất này**, khác với "dựa mặc định chưa ai xem xét".

**Cập nhật PO, 2026-10-05 (sau B4b):** `include_reasoning: false` vào hồ sơ cả hai tier (thay hàng "`reasoning_format`, `include_reasoning` — không đặt" ở trên). Số đo: cả hai tham số `include_reasoning: false` và `reasoning_format: "hidden"` được hai model chấp nhận và làm biến mất trường suy luận (`llm-groq-do-thuc-te-b4b.md`); chọn `include_reasoning: false`.

## 2. Trần output cứng — theo từng module (`max_completion_tokens`)

| Module | Đề xuất | Căn cứ | Ghi chú |
|---|---|---|---|
| `classify_intent` | `512` | Output JSON bốn trường, `retrieval_query` ≤ 200 ký tự (`07-prompts.md` mục 3.1) — hàng chục token nhìn thấy; phần còn lại là chỗ cho suy luận mức `low` | Trần tổng mỗi lời gọi `classify_intent` là 1.500 (input + output) — output 512 giữ chỗ cho input |
| `extract_slots` | `1536` | Tối đa 8 slot × (`value` + `evidence_quote` ≤ 300 ký tự) (`07-prompts.md` mục 3.2) — ước lượng thô, chưa đo | Biên rộng vì đây là ô ước lượng thô nhất của bảng A-022 |
| `draft_free_content` | `2048` | `body` ≤ `max_length` của biến (vài trăm ký tự) — vài trăm token nhìn thấy; suy luận mức `medium` tốn hơn `low` | Trần tổng mỗi lời gọi `drafting_agent` là 4.000 (cận trên cứng) |

**Ba điều chưa biết — nói thẳng:**

1. **`max_completion_tokens` có tính `reasoning_tokens` không** — nguồn không nói. Nếu có: trần quá thấp làm output bị cắt (`PARSE_FAILED`, hoặc `finish_reason: length`); nếu không: trần chỉ chặn phần JSON nhìn thấy. **Đo ở B4b.**
2. **Số token nhìn thấy thật** của ba module — số trên là ước lượng theo kích thước schema, chưa đo. B4b đo rồi đề xuất lại.
3. **Chọn tên token mà "ceiling" của `11-ops.md` mục 10.2 dùng** (tổng input + output + reasoning) khác `max_completion_tokens` (chỉ output, có thể gồm reasoning) — hai trần khác nhau, cùng tồn tại: trần output chặn từng lời gọi; trần mục 10.2 chỉ cảnh báo phía input và chặn theo chủ budget.

## 3. Thay đổi mã nếu duyệt — làm ở B4b, sau khi PO duyệt giá trị

- `model_profiles.json`: thêm `temperature`, `reasoning_effort` cho cả hai tier và mục `module_params` — `max_completion_tokens` theo `call_name`; schema cho phép tham số số nguyên có miền (khoảng), không chỉ danh sách giá trị; bước kiểm #21 từ chối tham số ngoài danh sách của model và giá trị ngoài miền (đã có cho danh sách giá trị).
- `providers`: gửi `max_completion_tokens` của module trong thân request; **không bao giờ** gửi `max_tokens` (deprecated).
- Test: request mang đúng tham số tường minh của từng tier; thiếu tham số bắt buộc trong hồ sơ → #21 trượt; đột biến "bỏ `max_completion_tokens` khỏi request" làm test đỏ.

## Open Questions

- PO duyệt, sửa hay bác từng giá trị ở mục 1 và 2?
- Có muốn đặt `reasoning_effort` của `STRONG` thấp hơn `medium` (rẻ hơn, nhanh hơn) hay cao hơn (`high`) — hay để eval quyết?

## 4. Đề xuất lại trần output theo số đo B4b — **CHƯA ÁP, chờ PO duyệt** (2026-10-05)

Ngữ nghĩa đã kết luận (ADR-035, mục B4b): `max_completion_tokens` so với tổng token sinh ra **gồm suy luận**; trần quá thấp trả HTTP 400 `json_validate_failed` (đi đường sửa parse, tốn thêm một lời gọi, và nếu lần sửa cũng hỏng thì `NEED_CLARIFICATION` ở lượt chat hay `halt_for_human` ở `document_graph`).

### 4.1 Số đo — `completion_tokens` (đã gồm suy luận) ở cấu hình hồ sơ hiện tại, hai lần chạy

| Module | Model, mức suy luận | Mẫu | Min | Max | Ghi chú |
|---|---|---|---|---|---|
| `classify_intent` | 20b, `low` | 11 (5 lần E1 + 3 lần E2 ở lần chạy 1, 3 lần E2 ở lần chạy 2) | 63 | 74 | prompt 1.640–1.642; nhìn thấy 27 |
| `extract_slots` | 20b, `low` | 6 | 521 | 817 | suy luận 398–691 — **phương sai lớn**; nhìn thấy 106–109 với 3 slot |
| `draft_free_content` | 120b, `medium` | 6 | 180 | 366 | suy luận 121–290; nhìn thấy 37–57 |

Mẫu nhỏ, đầu vào giả, một mức suy luận mỗi module. Tin nhắn thật dài hơn, mơ hồ hơn hay nhiều slot hơn (P2 cho tới 8 slot) sẽ suy luận lâu hơn.

### 4.2 Nguyên tắc — trần là **chốt chặn cho lời gọi chạy lạc**, không phải tối ưu hoá

Cái giá của trần thấp là một lần 400 và một lần sửa parse (hai lời gọi, gấp đôi độ trễ trong hạn chót 8 s của WV-04) rồi có thể hỏng cả luồng; cái giá của trần cao là một lời gọi chạy lạc tiêu tối đa đúng trần. Với hai bên chênh nhau như vậy, đặt trần ở **khoảng 5× số đo lớn nhất nếu vừa trần mỗi lời gọi của `11-ops.md`, và không dưới 2,5×**.

### 4.3 Đề xuất

| Module | Hiện tại | **Đề xuất** | Tỷ lệ so với max đo được | Lý do |
|---|---|---|---|---|
| `classify_intent` | 512 | **512 (giữ)** | 6,9× | Max đo 74; output JSON bốn trường. Lưu ý: 512 + prompt 1.642 = 2.154 vượt trần cảnh báo 1.800 nếu lời gọi chạy lạc tới trần — chấp nhận, vì trần 1.800 chỉ cảnh báo (A-090) và lời gọi thật ~1.716 |
| `extract_slots` | 1.536 | **2.048** | 2,5× | 1.536 chỉ 1,9× max đo (817) trong khi phương sai suy luận lớn (398–691) và P2 có thể trích tới 8 slot (schema `maxItems: 8`): nguy cơ cắt cao nhất ở module này. 2.048 + prompt ~600 = ~2.650 < trần 3.500 của lời gọi |
| `draft_free_content` | 2.048 | **2.048 (giữ)** | 5,6× | Max đo 366; hỏng ở đây dẫn tới `halt_for_human` (giá cao). 2.048 + prompt ~460 = ~2.500 < trần 4.000 cận trên cứng của lời gọi |

**Chỉ một giá trị đổi:** `extract_slots` 1.536 → 2.048. Hai chỗ chưa biết còn lại — thời lượng một lời gọi so với hạn chót 8 s (tool chưa ghi `completion_time`), và token đã tiêu của lời gọi bị cắt (HTTP 400 không trả `usage`, sổ đếm thiếu) — nằm ngoài đề xuất này; đo ở lần chạy có người thật.

Nếu duyệt: sửa `model_profiles.json` (một dòng), test `HoSoModel`, CHANGELOG, và kích hoạt Regression gate (ADR-035 điều kiện 2).
