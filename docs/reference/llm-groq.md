# Groq — hồ sơ ứng viên cho ADR-032

- **Nguồn — lấy bằng `curl`, ngày 2026-10-02:**
  - `https://console.groq.com/docs/your-data` — sha256 của bản đã lấy `d5d963a33f0d52d11ff2ecedbc0193dfa5e710740e32a8d9c858de61c3519248`
  - `https://console.groq.com/docs/legal/services-agreement` — sha256 của bản đã lấy `2230958ea3dc411e97dea07b0fa66ea1fb9133e6476bd47395ce20a21dc8d314`
  - `https://console.groq.com/docs/structured-outputs` — sha256 của bản đã lấy `80636a01ce5c6f89af2eb521c242803728e91b945997d3da2e8918505e605798`
  - `https://console.groq.com/docs/rate-limits` — sha256 của bản đã lấy `baeb1535a5c6f8a45d1c624facc6c0134e1d669adf07f5ba6fc98e5a9a00dbe9`
- **Cách tách:** bỏ `<script>`, `<style>`, `<svg>`; thẻ tiêu đề thành `##`, thẻ khối thành xuống dòng; câu chữ giữ nguyên. Trang tài liệu sống — có thể đổi sau ngày lấy.
- **Dùng cho:** ADR-032, A-026 — cổng 1.5 của `12-roadmap.md`; danh sách ngắn của PO ngày 2026-10-02. Hồ sơ đánh số theo mục Options của ADR-032: 1 điều khoản dữ liệu · 3 structured output · 4 giá · 5 giới hạn.

---

## 1. Điều khoản dữ liệu

### 1a. "Your Data in GroqCloud"

> By default, Groq does not retain customer data for inference requests.
>
> Customer data (inputs, outputs, and related state) is only retained in two cases:
>
> If you use features that require data retention to function (e.g., batch jobs, fine-tuning and LoRAs).
>
> If needed to protect platform reliability (e.g., to troubleshoot system failures or investigate abuse).
>
> You can control these settings yourself in the Data Controls settings.

> ## 2. System Reliability and Abuse Monitoring
>
> As noted above, inference requests are not retained by default. We may temporarily log inputs and outputs only when:
>
> Troubleshooting errors that degrade platform reliability, or
>
> Investigating suspected abuse (e.g. rate-limit circumvention).
>
> These logs are retained for up to 30 days, unless legally required to retain longer. You may opt out of this storage in Data Controls settings, but you remain responsible for ensuring safe, compliant usage of the services in accordance with the terms and Acceptable Use & Responsible AI Policy.

> ## Zero Data Retention
>
> All customers may enable Zero Data Retention (ZDR) in Data Controls settings.
> When ZDR is enabled, Groq will not retain customer data for system reliability and abuse monitoring. As noted above, this also means that features that rely on data retention to function will be disabled. Organization admins can decide to enable ZDR globally or on a per-feature basis at any time on the Data Controls page in Data Controls settings.
>
> ## Data Location
>
> All customer data is retained in Google Cloud Platform (GCP) buckets located in the United States. Groq maintains strict access controls and security standards as detailed in the Groq Trust Center. Where applicable, Customers can rely on standard contractual clauses (SCCs) for transfers between third countries and the U.S.

### 1b. Services Agreement — ba điều liên quan

> 3.4 Protection of Customer Data. Groq will only access, use, and otherwise process any Personal Data contained in the Customer Data in accordance with the DPA and any PHI contained in the Customer Data in accordance with the BAA. Groq has implemented and will maintain technical, organizational, and physical measures to protect Customer Data, as further described in the DPA and BAA, as applicable.

> 8.1 Intellectual Property Rights and Permissions. Except as expressly stated in this Agreement, this Agreement does not grant either party any rights, implied or otherwise, to the other's content or any of the other's intellectual property. As between the parties, Customer retains all Intellectual Property Rights in Customer Data (including in Inputs and Outputs), any Customer Application, Customer Training Data, and Customer supplied AI Model Service. Groq retains all Intellectual Property Rights in the Cloud Services. Customer obtains only a limited right to access and use the Cloud Services. Customer grants Groq the limited rights that may be reasonably necessary for Groq to deliver the Cloud Services and AI Model Services. This limited permission also extends to Groq's Affiliates, sub-processors, and contractors.

> 8.2 Customer's Training Data. Customer may in its sole discretion supply Groq with data for the purposes of prompting, fine-tuning, or customizing the AI Model Services or Cloud Services for Customer's needs ("Customer Training Data"). Groq will not use such Customer Training Data other than to provide the Cloud Services to Customer. Customer grants Groq and its Affiliates a worldwide, non-exclusive, non-sublicensable, non-transferable license to use the Customer Training Data solely for the purpose of providing the Cloud Services to Customer during the Order Term. Customer represents and warrants it has all rights in the Customer Training Data necessary to grant the rights contemplated by this Agreement for Groq and its Affiliates to provide the Cloud Services to Customer for its sole use.

**Đọc cho BO-19:** hai trang trên **không có câu "không huấn luyện" nguyên văn**. Điều 8.1 chỉ cấp cho Groq "the limited rights that may be reasonably necessary for Groq to deliver the Cloud Services and AI Model Services" — không có quyền nào ngoài việc cung cấp dịch vụ. Dữ liệu cá nhân xử lý theo DPA (điều 3.4). Lưu ở Mỹ; có Zero Data Retention bật được trong Data Controls. Chưa đọc DPA; chưa đọc Privacy Policy.

## 3. Structured output

> ## Strict Mode (strict: true)
> With strict: true, the model uses constrained decoding to guarantee that the output will always match your schema exactly. This mode:
>
> Never errors or produces invalid

> ## Models with Strict Mode (strict: true)
> The following models support strict: true, which uses constrained decoding to guarantee schema-compliant output:
>
> Model ID
> Model
>
> openai/gpt-oss-20b
>
> GPT-OSS 20B
>
> openai/gpt-oss-120b
>
> GPT-OSS 120B
>
> qwen/qwen3.8-27b
>
> Qwen 3.8 27B

> ## Schema Constraints by Mode
>
> Best-effort ModeStrict Mode
>
> When using strict: true, your schema must follow these mandatory constraints:
> Required fields: All schema properties must be marked as required. Optional fields are not supported.

> Closed objects: All objects must set additionalProperties: false to prevent undefined properties. This ensures strict schema adherence.
>
> Handling optional fields: Use union types with null to represent optional values:

**Đọc cho BO-19:** `gpt-oss-20b` và `gpt-oss-120b` có `strict: true` (constrained decoding). Điều kiện: **mọi property phải nằm trong `required`**, trường tuỳ chọn viết bằng kiểu hợp với `null`. `ClassifyIntentResult` ở `07-prompts.md` hiện để `secondary_intent`, `retrieval_query` ngoài `required` — dùng `strict` thì phải đưa vào. Trang không nói `maxLength`, `minItems`, `maxItems`, `format` có được hỗ trợ ở `strict` hay không — thử ở BUILD MODE.

## 4. Giá

Gói Free: không tính phí trong giới hạn ở mục 5. `https://groq.com/pricing` chuyển hướng về trang chủ khi lấy bằng `curl`; giá gói trả phí **không lấy được** — không cần cho giai đoạn build (A-085).

## 5. Giới hạn — gói Free

> Rate limits are measured in:
>
> RPM: Requests per minute
>
> RPD: Requests per day
>
> TPM: Tokens per minute
>
> TPD: Tokens per day
>
> ASH: Audio seconds per hour
>
> ASD: Audio seconds per day
>
> ITPM: Input tokens per minute
>
> OTPM: Output tokens per minute

> Cached tokens do not count towards your rate limits.
>
> Rate limits apply at the organization level, not individual users. You can hit any limit type depending on which threshold you reach first.

> The following is a high level summary and there may be exceptions to these limits. You can view the current, exact rate limits for your organization on the limits page in your account settings.
>
> Need higher rate limits? Upgrade to Developer plan to access higher limits, Batch and Flex processing, and more. Note that the limits shown below are the base limits for the Developer plan, and higher limits are available for select workloads and enterprise use cases.

Bảng trên trang, dựng lại cho hai model liên quan — chuỗi ô theo thứ tự cột `MODEL ID · RPM · RPD · TPM · TPD · ASH · ASD`:

| Model | RPM | RPD | TPM | TPD |
|---|---|---|---|---|
| `openai/gpt-oss-120b` | 30 | 1K | 8K | 200K |
| `openai/gpt-oss-20b` | 30 | 1K | 8K | 200K |

**Bảng này là của gói Free.** Trang có hai tab, "Free Plan Limits" và "Developer Plan Limits", và chỉ một bảng được render sẵn trong HTML. Trong HTML, nút "Free Plan Limits" mang class của tab đang chọn (`bg-black … text-white`), nút kia không. Câu "Note that the limits shown below are the base limits for the Developer plan" đứng trước hai tab và **trái** với tab đang chọn. Người triển khai đọc theo tab đang chọn — đây là suy luận từ HTML, không phải câu chữ của trang. **Xác nhận** trên trang Limits của tài khoản Groq khi PO tạo key, và ghi con số đó vào đây.

Giới hạn đặt ở cấp **organization**, theo từng model. Hai model có hàng riêng — chúng có dùng chung hạn mức với nhau hay không, trang không nói: `[CẦN XÁC MINH]`.

---

## 6. Tương thích API dạng OpenAI, streaming, và `usage` — thêm 2026-10-02 (ADR-035)

- **Nguồn:** `https://console.groq.com/docs/openai` — sha256 `bbd699241946fd652e1b738659ad303c0de483f52722a889aa6ddfcccfe7111f`; trang `https://console.groq.com/docs/structured-outputs` ở mục 3; đặc tả OpenAPI nhúng trong `https://console.groq.com/docs/rate-limits` ở mục 5. Lấy ngày 2026-10-02.

### 6a. Tương thích OpenAI

> We designed Groq API to be mostly compatible with OpenAI's client libraries, making it easy to
> configure your existing applications to run on Groq and try our inference speed.
>
> We also have our own Groq Python and Groq TypeScript libraries that we encourage you to use.
>
> ## Configuring OpenAI to Use Groq API
>
> To start using Groq with OpenAI's client libraries, pass your Groq API key to the api_key parameter
> and change the base_url to https://api.groq.com/openai/v1:
>
> PythonJavaScript
>
> Python
>
> import os
> import openai
>
> client = openai.OpenAI(
> base_url="https://api.groq.com/openai/v1",
> api_key=os.environ.get("GROQ_API_KEY")
> )

> ## Currently Unsupported OpenAI Features
>
> Note that although Groq API is mostly OpenAI compatible, there are a few features we don't support just yet:
>
> ## Text Completions
>
> The following fields are currently not supported and will result in a 400 error (yikes) if they are supplied:
>
> logprobs
>
> logit_bias
>
> top_logprobs
>
> messages[].name
>
> If N is supplied, it must be equal to 1.
>
> ## Temperature
>
> If you set a temperature value of 0, it will be converted to 1e-8. If you run into any issues, please try setting the value to a float32 > 0 and <= 2.

### 6b. Structured outputs và streaming

> Streaming and tool use are not currently supported with Structured Outputs.

### 6c. Đặc tả OpenAPI — ba schema liên quan, chép nguyên chuỗi JSON

```json
"CompletionUsage":{"description":"Usage statistics for the completion request.","properties":{"completion_time":{"description":"Time spent generating tokens","type":"number"},"completion_tokens":{"description":"Number of tokens in the generated completion.","type":"integer"},"completion_tokens_details":{"description":"Breakdown of tokens in the completion.","nullable":true,"properties":{"reasoning_tokens":{"description":"Number of tokens used for reasoning (for reasoning models).","type":"integer"}},"required":["reasoning_tokens"],"type":"object"},"prompt_time":{"description":"Time spent processing input tokens","type":"number"},"prompt_tokens":{"description":"Number of tokens in the prompt.","type":"integer"},"prompt_tokens_details":{"description":"Breakdown of tokens in the prompt.","nullable":true,"properties":{"cached_tokens":{"description":"Number of tokens that were cached and reused.","type":"integer"}},"required":["cached_tokens"],"type":"object"},"queue_time":{"description":"Time the requests was spent queued","type":"number"},"total_time":{"description":"completion time and prompt time combined","type":"number"},"total_tokens":{"description":"Total number of tokens used in the request (prompt + completion).","type":"integer"}},"required":["prompt_tokens","completion_tokens","total_tokens"],"type":"object"}
```

```json
"reasoning_effort":{"description":"qwen3 models support `none` to disable reasoning and `default` or null\\nto use the model default.\\n\\nqwen/qwen3.8-27b additionally supports `low`, `medium`, and `high`.\\nIts default is `none`; `high` selects the model's native `xhigh` mode.\\n\\nopenai/gpt-oss-20b and openai/gpt-oss-120b support 'low', 'medium', or 'high'.\\n'medium' is the default value.\\n\\nValues outside a model's supported set are rejected with a 400.\\n","enum":["none","default","minimal","low","medium","high","xhigh","max"],"nullable":true,"type":"string"}
```

```json
"stream":{"default":false,"description":"If set, partial message deltas will be sent. Tokens will be sent as data-only [server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events#Event_stream_format) as they become available, with the stream terminated by a `data: [DONE]` message. [Example code](/docs/text-chat#streaming-a-chat-completion).\\n","nullable":true,"type":"boolean"}
```

### 6d. Header giới hạn và 429 — trang `https://console.groq.com/docs/rate-limits`, cùng bản đã lấy ở mục 5

> In addition to viewing your limits on your account's limits page, you can also view rate limit information such as remaining requests and tokens in HTTP response
> headers as follows:
>
> The following headers are set (values are illustrative):
>
> Header
> Value
> Notes
>
> retry-after
> 2
> In seconds
>
> x-ratelimit-limit-requests
> 14400
> Always refers to Requests Per Day (RPD)
>
> x-ratelimit-limit-tokens
> 18000
> Always refers to Tokens Per Minute (TPM)
>
> x-ratelimit-remaining-requests
> 14370
> Always refers to Requests Per Day (RPD)
>
> x-ratelimit-remaining-tokens
> 17997
> Always refers to Tokens Per Minute (TPM)
>
> x-ratelimit-reset-requests
> 2m59.56s
> Always refers to Requests Per Day (RPD)
>
> x-ratelimit-reset-tokens
> 7.66s
> Always refers to Tokens Per Minute (TPM)
>
> ## Handling Rate Limits
>
> When you exceed rate limits, our API returns a 429 Too Many Requests HTTP status code.
>
> Note: retry-after is only set if you hit the rate limit and status code 429 is returned. The other headers are always included.
