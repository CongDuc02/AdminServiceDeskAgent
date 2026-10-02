# ADR-035 — Client gọi LLM: `httpx` gọi thẳng API dạng OpenAI, một adapter, không SDK

**Trạng thái:** Accepted · **Duyệt:** PO, 2026-10-02 — xác nhận cách đọc "hồ sơ model"; kèm điều kiện ở mục Điều kiện duyệt · **Ngày:** 2026-10-02 · **Quyết định tại:** BUILD MODE, trước adapter provider của `ai_gateway` · **Liên quan:** ADR-032 (Groq cho mốc 1, điều kiện đảo ngược sang OpenRouter), ADR-007 (LLM không gọi tool, output JSON), ADR-016 (lượt chat, `turn.progress`), ADR-019 (`llm_usage`), ADR-025 (output contract sinh từ cấu hình), NFR-08 của `01-prd.md`, WV-04…WV-06, mục Luật import của `06-structure.md`, `docs/reference/llm-groq.md`, `docs/reference/llm-openrouter.md`

---

## Context

ADR-032 chọn Groq cho mốc 1: `openai/gpt-oss-20b` tier rẻ, `openai/gpt-oss-120b` tier mạnh. Điều kiện đảo ngược là chuyển hẳn sang OpenRouter `openai/gpt-4o-mini`. Cần chọn cách `ai_gateway` gọi provider.

**Tiêu chí bắt buộc — PO, 2026-10-02:**

1. **Đảo ngược sang OpenRouter chỉ là đổi base URL, key, model.** Không đổi code.
2. **Structured outputs `strict` không dùng chung với streaming** — đối chiếu NFR-08.

**Tiêu chí của thiết kế:**

3. Đọc được `usage` thật, gồm token suy luận và thời lượng — ADR-032 đòi đo token và thời lượng từ `usage`.
4. Retry và timeout là việc của `ai_gateway` — WV-04, WV-05, WV-06 — không chồng hai lớp retry.
5. Ít phụ thuộc mới trong lock (ADR-030).

**Về tiêu chí 2 và NFR-08.** Groq: *"Streaming and tool use are not currently supported with Structured Outputs."* (mục Structured outputs và streaming của `docs/reference/llm-groq.md`). NFR-08 đòi "thao tác chat có phản hồi tăng dần để người dùng biết hệ thống đang làm việc". Thiết kế đáp ứng NFR-08 bằng sự kiện `turn.progress` theo **node** của `intake_graph` (ADR-016), không bằng streaming token của LLM: mọi prompt module trả JSON, và câu trả lời hiển thị cho người dùng được lắp từ khuôn ở `render_reply` (ADR-007). Vậy **mọi lời gọi LLM không streaming, có `strict`, không trái NFR-08**. Điều đó chỉ đổi nếu thiết kế thêm một lời gọi LLM sinh văn bản tự do hiển thị trực tiếp — hiện không có.

## Options

- **A — SDK `groq`.**
- **B — SDK `openai`, đặt `base_url`.**
- **C — `httpx` gọi thẳng `POST {base_url}/chat/completions`.**
- **D — tích hợp LLM của LangChain.**

### Đã kiểm — 2026-10-02

| Phép kiểm | Kết quả | Nguồn |
|---|---|---|
| Groq nhận client dạng OpenAI không | Có — đổi `base_url` thành `https://api.groq.com/openai/v1`. Groq cũng "encourage" dùng SDK riêng | Mục Tương thích OpenAI của `docs/reference/llm-groq.md` |
| OpenRouter nhận client dạng OpenAI không | Có — `baseURL: 'https://openrouter.ai/api/v1'`; đường dẫn `https://openrouter.ai/api/v1/chat/completions` | Mục Base URL dạng OpenAI của `docs/reference/llm-openrouter.md` |
| Trường Groq từ chối | `logprobs`, `logit_bias`, `top_logprobs`, `messages[].name` trả 400; `n` phải bằng 1; `temperature` 0 bị đổi thành 1e-8 | Mục Tương thích OpenAI của `docs/reference/llm-groq.md` |
| `usage` của Groq | `prompt_tokens`, `completion_tokens`, `completion_tokens_details.reasoning_tokens`, `prompt_time`, `completion_time` | Mục Đặc tả OpenAPI — ba schema liên quan của `docs/reference/llm-groq.md` |
| `reasoning_effort` cho `gpt-oss` | `'low'`, `'medium'`, `'high'`; mặc định `'medium'`; giá trị ngoài tập của model trả 400 | Mục Đặc tả OpenAPI — ba schema liên quan của `docs/reference/llm-groq.md` |
| Phụ thuộc của `groq` 1.7.0 | `anyio`, `distro`, `httpx`, `pydantic`, `sniffio`, `typing-extensions` — **cả sáu đã có trong lock** | `METADATA` của wheel |
| Phụ thuộc của `openai` 3.23.0 | `anyio`, `httpx2`, `jiter`, `pydantic`, `sniffio`, `typing-extensions` — **`httpx2` và `jiter` chưa có trong lock** | `METADATA` của wheel — **kiểm lại theo yêu cầu của PO, 2026-10-02:** wheel `openai-3.23.0-py3-none-any.whl` sha256 `7fbec2e50a05ac0fa858629505688e5998fd82245058390ac1b6d98960174bd5`, dòng 26 của `METADATA` là nguyên văn `Requires-Dist: httpx2<3,>=2.12.0`. `httpx2` là một gói khác `httpx`: PyPI có dự án `httpx2`, bản 2.13.1, mô tả "The next generation HTTP client", mã nguồn ở `github.com/pydantic/httpx2` |
| `httpx` trong lock hiện tại | `httpx==0.28.1`, kéo vào bởi `langchain-core` và `langgraph-sdk` | `backend/requirements-linux.lock` |
| Khoá thử, thêm ghim trực tiếp `httpx==0.28.1` | Danh sách gói **không đổi** | Khoá thử cùng lệnh của ADR-030 |

## Decision

**Đề xuất C — `httpx`, một adapter "chat completions dạng OpenAI" trong `bo19.ai_gateway.providers`.**

- **Ghim trực tiếp `httpx==0.28.1`** — đúng bản đang có trong lock, nên lock không thêm gói nào.
- **Cấu hình, không phải code**, cho mỗi môi trường:
  - `base_url`, và key là secret — mục Secret management trên Render của `09-security.md`;
  - mỗi tier một **hồ sơ model**: mã model, và các tham số riêng của model gửi kèm thân request. Tier rẻ trên Groq: `reasoning_effort: "low"` — chỉ đạo của PO.
- **Mọi request:** `POST {base_url}/chat/completions`, `stream: false`, `response_format` loại `json_schema` với `strict: true` — schema dựng lúc gọi theo ADR-025. Không bao giờ gửi `logprobs`, `logit_bias`, `top_logprobs`, `messages[].name`; `n` luôn 1; `temperature` không đặt 0 — giá trị lấy từ hồ sơ model.
- **`usage`:** đọc `prompt_tokens`, `completion_tokens`, `completion_tokens_details.reasoning_tokens`, và nếu có thì `prompt_time`, `completion_time`. Token ghi vào `llm_usage` (ADR-019) — `reasoning_tokens` vào cột mới của migration 0009. `prompt_time`, `completion_time` ghi vào log kỹ thuật, không vào DB. Trường nào provider không trả thì để trống — **không suy ra**.
- **Retry và timeout:** chỉ ở `ai_gateway` — WV-04, WV-05, WV-06. `httpx` không retry; timeout của `httpx` đặt bằng timeout của lời gọi.
- **Lỗi HTTP** ánh xạ về mã của `ai_gateway`: 429 và 5xx là lỗi thoáng qua, đi vào retry; 400 là lỗi của request, không retry — trong `document_graph` dẫn tới `SYSTEM_DEFECT` (mục Bảng mã của `08-hitl.md`).
- **Đảo ngược sang OpenRouter — tiêu chí 1:** đổi `base_url` thành `https://openrouter.ai/api/v1`, key, và hồ sơ model — mã model `openai/gpt-4o-mini`, **bỏ** `reasoning_effort` vì đó là tham số của `gpt-oss`. **Không đổi dòng code nào.**

**Cách đọc tiêu chí 1 — để PO xác nhận:** "đổi model" ở đây gồm cả hồ sơ model — mã model cùng tham số riêng của nó. Nếu tiêu chí là **chỉ** mã model thì `reasoning_effort` phải bỏ khỏi tier rẻ, trái chỉ đạo "tier rẻ dùng mức suy luận thấp". Đề xuất giữ hồ sơ model.

## Consequences

**Tích cực**

- Đáp ứng tiêu chí 1 bằng cấu hình — Groq và OpenRouter đều tự mô tả là nhận client dạng OpenAI tại base URL của họ.
- Lock không thêm gói nào.
- Một lớp retry, một lớp timeout — đúng WV-04…WV-06.
- Thân request khớp đúng ví dụ và đặc tả của tài liệu provider — kiểm được bằng mắt, không qua tầng biến đổi của SDK.

**Tiêu cực và cái phải chấp nhận**

- **Dự án tự viết phần SDK làm sẵn:** dựng request, đọc response, ánh xạ lỗi. Phần đọc response dùng model `pydantic` chỉ cho các trường dùng tới — `pydantic` đã có trong phụ thuộc. Test bằng response mẫu lấy từ đặc tả của Groq.
- **"Tương thích OpenAI" là lời của provider, có thể lệch.** Groq tự nêu các trường không hỗ trợ. Khi điều kiện đảo ngược phát ra, phải chạy lại bộ eval — ADR-032 đã đòi.
- **Luật import:** `httpx` chỉ được import trong `bo19.ai_gateway.providers` trong số các module gọi tới provider — contract `allowlist-gate` của mục Luật import của `06-structure.md`, đã điền `httpx` vào chỗ của `<sdk-llm>` (2026-10-02).

**Điều kiện đảo ngược**

- Thiết kế thêm một lời gọi LLM cần streaming → xét lại tiêu chí 2; Groq hiện không cho streaming cùng structured outputs.
- Provider đổi định dạng API ra khỏi dạng OpenAI → xét SDK riêng của provider đó, với ADR mới.

## Rejected alternatives

**A — SDK `groq`.** Phụ thuộc đã có sẵn trong lock — điểm cộng thật. Nhưng trượt tiêu chí 1: chuyển sang OpenRouter là đổi thư viện, tức đổi code; trỏ SDK `groq` vào base URL của OpenRouter thì cả hai bên đều không mô tả là được.

**B — SDK `openai`.** Đạt tiêu chí 1 — cả Groq lẫn OpenRouter dùng chính SDK này trong ví dụ. Loại vì thêm hai gói chưa có trong lock (`httpx2`, `jiter`). Thứ nó cho thêm — retry, timeout, kiểu dữ liệu — thì retry và timeout trùng với `ai_gateway`; còn lại chỉ là kiểu dữ liệu, không đủ bù.

**D — tích hợp LLM của LangChain.** Thêm các gói LangChain mà không tài liệu thiết kế nào chọn — `backend/pyproject.toml` ghi rõ `langchain` cố ý không có. `ai_gateway` vẫn phải bọc ngoài để làm allowlist, budget, ép JSON (ADR-008, ADR-019); lớp LangChain ở giữa không bớt được việc nào trong ba việc đó.

## Điều kiện duyệt — PO, 2026-10-02

**Cách đọc tiêu chí 1 được xác nhận:** "đổi model" gồm hồ sơ model.

1. **Hồ sơ model nằm trong cấu hình có schema.** Schema liệt kê, cho từng mã model, các tham số được phép gửi kèm và miền giá trị của chúng — với `openai/gpt-oss-20b`, `openai/gpt-oss-120b`: `reasoning_effort` ∈ `low`, `medium`, `high`, theo đặc tả của Groq (mục Đặc tả OpenAPI — ba schema liên quan của `docs/reference/llm-groq.md`). **Bước kiểm khởi động #21** của `06-structure.md` từ chối chạy khi một hồ sơ thiếu trường bắt buộc, hoặc có tham số không thuộc model đó.
2. **Đổi hồ sơ model — kể cả chỉ `reasoning_effort` — là một thay đổi có ghi:** một dòng `CHANGELOG.md`, và kích hoạt Regression gate của `10-eval.md` (mục Khi nào kích hoạt).
3. **`reasoning_tokens` tính vào token budget** của mục Định cỡ A-022 của `11-ops.md`, và ghi vào `llm_usage` — cột `reasoning_tokens`, migration `0009_llm_usage_reasoning_tokens.sql`. `completion_tokens` của Groq đã gồm token suy luận hay chưa, đặc tả không nói: **mục mở O1-3 của Sprint 1** — xác định trên số đo thật bằng phép so `total_tokens` với `prompt_tokens + completion_tokens`. Tới khi có kết luận, budget cộng **cả hai** — `completion_tokens` và `reasoning_tokens` — tức tính dư chứ không tính thiếu. **Cách đóng — PO, 2026-10-02:** ở loạt gọi Groq thật đầu tiên, đếm token của output **nhìn thấy** — JSON trả về — bằng tokenizer offline `o200k_harmony` (`docs/reference/llm-token-count-p1-p2.md`), rồi so với `completion_tokens` và `reasoning_tokens` của **cùng** lời gọi. Nếu `completion_tokens` ≈ token nhìn thấy + `reasoning_tokens` thì token suy luận đã nằm trong `completion_tokens` — budget chỉ cộng `completion_tokens`; nếu `completion_tokens` ≈ token nhìn thấy thì cộng thêm `reasoning_tokens`. Có kết quả thì **bỏ tính dư**, ghi `CHANGELOG.md`.
4. **429 trong lượt chat.** Groq đặt header `retry-after`, tính bằng giây, chỉ khi trả 429 (mục Header giới hạn và 429 của `docs/reference/llm-groq.md`). `ai_gateway` **chỉ chờ** theo `retry-after` khi thời gian còn lại của hạn chót lượt — WV-02 — còn ít nhất `retry-after` cộng một timeout lời gọi WV-04. Không đủ thì không chờ: trả khuôn "hệ thống đang bận". Lần chờ này **là** lần retry duy nhất của WV-05, không cộng thêm. Ghi cả vào dòng WV-05 của `proposals/sprint1-working-values-a031-a048.md`.
5. **429 trong job của `worker` — PO duyệt 2026-10-02:** trong `document_graph` không có WV-02. Lần chạy lại chờ `max(backoff thường, retry-after)`; 429 vẫn tính vào `job.max_attempts`; log và `audit_event` của lần dừng mang mã con `PROVIDER_RATE_LIMITED`, tách với `PROVIDER_CALL_FAILED`. **`retry-after` vượt WV-19 — 120 giây — thì không chờ:** coi là hết hạn mức theo ngày, job `FAILED` ngay với `PROVIDER_RATE_LIMITED` (PO, 2026-10-02). Hai mã con thuộc enum `provider_failure_subcode` của `GLOSSARY.md`; không vào danh mục `error_code` của `05-api.md`, không đổi `openapi.yaml`. Chi tiết ở mục Retry, backoff và job lỗi vĩnh viễn của `11-ops.md`.

## Open Questions

- Không có — cách đọc tiêu chí 1 đã được xác nhận. Mục mở O1-3 nằm ở `12-roadmap.md`.
