# OpenRouter — hồ sơ ứng viên cho ADR-032 (ngoại lệ PO cho phép)

- **Nguồn — lấy bằng `curl`, ngày 2026-10-02:**
  - `https://openrouter.ai/docs/guides/privacy/provider-logging` — sha256 của bản đã lấy `943aee0d3042d45c1a2f4d68522afae4e74db0bd4dce9da4b246e2dcb2ec4c9a`
  - `https://openrouter.ai/docs/guides/features/structured-outputs` — sha256 của bản đã lấy `90acae57e85cf19e7196fc9255563e7c41d282c38e3d3b215cad3d6d447efcf5`
  - `https://openrouter.ai/docs/api_reference/limits` — sha256 của bản đã lấy `8984de7249e74ae7f7c5870f37447ac5a699ba228260816209382b5a8759ffd8`
  - `https://openrouter.ai/api/v1/models` — sha256 của bản đã lấy `75d731772423eb47a4d4306ba008e304d438047dc22b5cd9877f6e8d3c86573b`
  - `https://openrouter.ai/api/v1/models/openai/gpt-4o-mini/endpoints` — sha256 của bản đã lấy `b84ed94938e08a246a2948caf980ca88a309b681e0e822a58608b83155a6d8d1`
- **Cách tách:** bỏ `<script>`, `<style>`, `<svg>`; thẻ tiêu đề thành `##`, thẻ khối thành xuống dòng; câu chữ giữ nguyên. Trang tài liệu sống — có thể đổi sau ngày lấy.
- **Dùng cho:** ADR-032, A-026 — cổng 1.5 của `12-roadmap.md`; danh sách ngắn của PO ngày 2026-10-02. Hồ sơ đánh số theo mục Options của ADR-032: 1 điều khoản dữ liệu · 3 structured output · 4 giá · 5 giới hạn. **Không phải gói free** — dùng credit; PO cho phép ngoại lệ với A-085 (2026-10-02).

---

## 1. Điều khoản dữ liệu

> Each provider on OpenRouter has its own data handling policies. We reflect those policies in structured data on each AI endpoint that we offer.
> On your account settings page, you can set whether you would like to allow routing to providers that may train on your data (according to their own policies). There are separate settings for paid and free models.
> Wherever possible, OpenRouter works with providers to ensure that prompts will not be trained on, but there are exceptions. If you opt out of training in your account settings, OpenRouter will not route to providers that train. This setting has no bearing on OpenRouter’s own policies and what we do with your prompts.

> Providers also have their own data retention policies, often for compliance reasons. OpenRouter does not have routing rules that change based on data retention policies of providers, but the retention policies as reflected in each provider’s terms are shown below. Any user of OpenRouter can ignore providers that don’t meet their own data retention requirements.
> The full terms of service for each provider are linked from the provider’s page, and aggregated in the documentation.

Endpoint đang phục vụ `openai/gpt-4o-mini`, theo API `…/endpoints` cùng ngày: `Azure` (azure), `OpenAI` (openai), `Azure` (azure/swedencentral).

**Đọc cho BO-19:** dữ liệu đi qua **hai** bên — OpenRouter và nhà cung cấp phía sau (OpenAI hoặc Azure). Phải tắt "allow routing to providers that may train" trong cài đặt tài khoản, và đọc điều khoản dữ liệu của chính OpenAI và Azure cho endpoint này: chưa lấy — `[CẦN XÁC MINH]`. Câu cuối của đoạn trích: thiết lập đó "has no bearing on OpenRouter’s own policies" — chính sách riêng của OpenRouter: chưa lấy, `[CẦN XÁC MINH]`.

## 3. Structured output

> Structured outputs are supported by select models.
> You can find a list of models that support structured outputs on the models page.
> Support is determined per endpoint, not just per model: the same model may be served by multiple providers, and only some of those providers may support structured outputs. Endpoint support can also change over time. To see which providers support structured outputs for a specific model, check the structured_outputs parameter in the Providers section of the model’s page.
> For details on each provider’s implementation, see their documentation, for example:
>
> OpenAI
>
> Google Gemini
>
> Anthropic
>
> Fireworks
>
> To ensure your request is only routed to endpoints that support structured outputs:
>
> Check the model’s supported parameters on the models page
>
> Set require_parameters: true in your provider preferences (see Provider Routing)
>
> Include response_format and set type: json_schema in the required parameters
>
> ##
> ​
> Best Practices
>
> Include descriptions: Add clear descriptions to your schema properties to guide the model
>
> Use strict mode: Set strict: true so that providers with a native strict mode enforce your schema exactly. Enforcement varies by provider: some guarantee schema-conforming output, while others translate your schema into their own structured-output format or treat it as a strong hint, so exact compliance is not guaranteed on every endpoint. Strict modes may also restrict which JSON Schema features you can use. See the provider’s documentation for details
>
> ##
> ​
> Example Implementation
> Here’s a complete example using the Fetch API:
>
> ##
> ​
> Streaming with Structured Outputs

Theo `GET /api/v1/models` cùng ngày, `supported_parameters` có `response_format` và `structured_outputs` cho:

| Model | Context | Giá prompt (USD/token) | Giá completion (USD/token) |
|---|---|---|---|
| `openai/gpt-oss-120b` | 131072 | 0.000000037 | 0.00000017 |
| `openai/gpt-oss-20b` | 131072 | 0.000000018 | 0.00000009 |
| `openai/gpt-4o-mini` | 128000 | 0.00000015 | 0.0000006 |

## 4. Giá

Bảng ở mục 3, lấy nguyên từ trường `pricing` của API. Không có biến thể `:free` nào của ba model này trong danh sách cùng ngày.

## 5. Giới hạn

> Rate limits govern how many requests you can make. There are a few rate limits that apply to certain types of requests, regardless of account status:
>
> Free usage limits: If you’re using a free model variant (with an ID ending in :), the following limits apply:

**Đọc cho BO-19:** trang chỉ nêu giới hạn cho biến thể free (ID kết thúc bằng `:free`) và lớp chống DDoS. Con số trong bảng giới hạn free render bằng JavaScript, không có trong HTML đã lấy. Model trả phí như `openai/gpt-4o-mini` không có hạn mức TPM, TPD công bố trên trang này — giới hạn thực tế là credit trong tài khoản.

---

## 6. Base URL dạng OpenAI — thêm 2026-10-02 (ADR-035)

- **Nguồn:** `https://openrouter.ai/docs/quickstart` — sha256 `7a4fdb3d375b3cbc7961a4582e7e94c90e4dec8a45b5f288070b48fd30804c16`; `https://openrouter.ai/docs/api-reference/overview` — sha256 `e7d2fe70a23c6de9627e61a1af6fbc16cb52abe51509c961a86496b90bf2c905`. Lấy ngày 2026-10-02.

Ví dụ dùng SDK OpenAI trên trang quickstart, nguyên văn tới trước `defaultHeaders`:

```javascript
import OpenAI from 'openai';

const openai = new OpenAI({
 baseURL: 'https://openrouter.ai/api/v1',
 apiKey: '<OPENROUTER_API_KEY>',
```

Đường dẫn chat completions xuất hiện trên cả hai trang: `https://openrouter.ai/api/v1/chat/completions`.
