# Groq — tham số của chat completions ảnh hưởng tới output (trần output, lấy mẫu, suy luận), từ nguồn gốc bằng `curl`

- **Ngày lấy:** 2026-10-05. **Cách lấy:** `curl -sS -L https://console.groq.com/docs/api-reference` — 1531764 byte — sha256 `6c834e38d01d798109d56fa08aaec888c46302cfbce494729c52d2a739004657` (cùng bản đã tải ở `llm-groq-structured-request.md`). Excerpt chép bằng script từ văn bản đã bỏ thẻ HTML; số dòng là dòng của văn bản đó.
- **Dùng cho:** A-090 — hồ sơ model ghi tường minh mọi tham số ảnh hưởng output, và trần output cứng theo module (PO, 2026-10-05).

## 1. `max_completion_tokens` — dòng 1142–1160

```text
max_completion_tokens
integer
 or null
Optional
The maximum number of tokens that can be generated in the chat completion. The total length of input tokens and generated tokens is limited by the model's context length.
max_tokens
```

## 2. `temperature` — dòng 1585–1612 và `top_p` — dòng 1718–1745

```text
temperature
number
 or null
Optional
Defaults to 
1
Range:
0 - 2
What sampling temperature to use, between 0 and 2. Higher values like 0.8 will make the output more random, while lower values like 0.2 will make it more focused and deterministic. We generally recommend altering this or top_p but not both.
tool_choice
string / object
```

```text
top_p
number
 or null
Optional
Defaults to 
1
Range:
0 - 1
An alternative to sampling with temperature, called nucleus sampling, where the model considers the results of the tokens with top_p probability mass. So 0.1 means only the tokens comprising the top 10% probability mass are considered. We generally recommend altering this or temperature but not both.
user
string
```

## 3. `reasoning_effort` — dòng 1268–1300; `reasoning_format` — 1319–1330; `include_reasoning` — 1077–1105; `seed` — 1417–1432

```text
reasoning_effort
string
 or null
Optional
Allowed values:
none, default, minimal, low, medium, high, xhigh, max
qwen3 models support 
none
 to disable reasoning and 
default
 or null
to use the model default.
qwen/qwen3.8-27b additionally supports 
low
, 
medium
, and 
high
.
Its default is 
none
```

```text
reasoning_format
string
 or null
Optional
Allowed values:
hidden, raw, parsed
```

```text
include_reasoning
boolean
 or null
Optional
Whether to include reasoning in the response.  If true, the response will include a 
reasoning
 field. If false, the model's reasoning will not be included in the response.
This field is mutually exclusive with 
reasoning_format
.
logit_bias
object
 or null
Optional
```

```text
seed
integer
 or null
Optional
If specified, our system will make a best effort to sample deterministically, such that repeated requests with the same 
seed
 and parameters should return the same result.
Determinism is not guaranteed, and you should refer to the 
system_fingerprint
 response parameter to monitor changes in the backend.
```

## 4. Điều rút ra — và điều **không** rút ra

- Tham số giới hạn output là **`max_completion_tokens`** (`max_tokens` đã bị ghi "Deprecated in favor of `max_completion_tokens`"). Mô tả: "The maximum number of tokens that can be generated in the chat completion."
- **Không nói** token suy luận (`reasoning_tokens`) có nằm trong "tokens that can be generated" hay không. **Chưa rõ — đo ở B4b** (so `completion_tokens`, `reasoning_tokens` và token nhìn thấy của cùng lời gọi, ở một giá trị `max_completion_tokens` đủ nhỏ để chạm trần). Cho tới khi đo, coi là **có thể có**: trần phải dư cho cả suy luận, hoặc output JSON có thể bị cắt giữa chừng.
- `temperature`: mặc định 1, miền 0–2; "lower values like 0.2 will make it more focused and deterministic"; "We generally recommend altering this or top_p but not both". `top_p`: mặc định 1, miền 0–1, cùng khuyến nghị.
- `reasoning_effort`: `openai/gpt-oss-20b` và `openai/gpt-oss-120b` nhận `low`, `medium`, `high`, mặc định `medium` (`llm-groq.md` mục 6c — văn bản ở dòng 1268–1300 của trang này chỉ nói rõ qwen3; phần gpt-oss nằm ở khối OpenAPI nhúng).
- `reasoning_format` (`hidden`, `raw`, `parsed`) và `include_reasoning` loại trừ nhau; trang không nói model nào hỗ trợ. **Chưa biết** `gpt-oss` có hỗ trợ không — đo ở B4b.
- `seed`: "best effort", "Determinism is not guaranteed".
