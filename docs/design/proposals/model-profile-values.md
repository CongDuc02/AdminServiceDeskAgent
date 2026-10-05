# Đề xuất giá trị hồ sơ model — tham số ảnh hưởng output và trần output cứng

**Trạng thái:** ✋ **Chờ PO duyệt** — chưa sửa `model_profiles.json`, chưa sửa code. · **Ngày:** 2026-10-05 · **Người đề xuất:** người triển khai · **Theo:** A-090 (3), quyết định PO 2026-10-05 · **Nguồn tham số:** `docs/reference/llm-groq-chat-params.md`, `docs/reference/llm-groq.md` mục 6c

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
