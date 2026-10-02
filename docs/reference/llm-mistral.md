# Mistral — hồ sơ ứng viên cho ADR-032

- **Nguồn — lấy bằng `curl`, ngày 2026-10-02:**
  - `https://legal.mistral.ai/terms/commercial-terms-of-service` — sha256 của bản đã lấy `69e568ea3c941cd49efc00ad0bb96f70511948020335f7d9f2ffb991a4739ed3`
  - `https://docs.mistral.ai/studio/conversations/structured-output/custom.md` — sha256 của bản đã lấy `dacc769d81e04b8b0ffd97c0e0b40ba976f8feacd4bbe0ff6ab3046ff8c08237`
  - `https://docs.mistral.ai/admin/billing-usage/usage-limits.md` — sha256 của bản đã lấy `aef164ca640b7480d637f7ab36436810ee57710ce418a0c223ee185f0e11308c`
  - `https://docs.mistral.ai/admin/workspaces/usage-limits.md` — sha256 của bản đã lấy `4c54c5e3d67d54e6a75d2c311603fb83246e6f5f93cbfa61cdc00345fc4d3066`
- **Cách tách:** bỏ `<script>`, `<style>`, `<svg>`; thẻ tiêu đề thành `##`, thẻ khối thành xuống dòng; câu chữ giữ nguyên. Trang tài liệu sống — có thể đổi sau ngày lấy.
- **Dùng cho:** ADR-032, A-026 — cổng 1.5 của `12-roadmap.md`; danh sách ngắn của PO ngày 2026-10-02. Hồ sơ đánh số theo mục Options của ADR-032: 1 điều khoản dữ liệu · 3 structured output · 4 giá · 5 giới hạn.

---

## 1. Điều khoản dữ liệu — Commercial Terms of Service

> 4.1. Providing the Mistral AI Products. Customer grants Mistral AI a worldwide, non-exclusive, non-transferable (except as permitted in Section 14.2 (Assignment)), royalty-free, fully-paid license (with the right to sublicense to our service providers) to use Customer Data and Outputs for the purposes of (a) providing, maintaining, and optimizing the Mistral AI Products, which includes debugging, assessing, reviewing, and correcting the performance of the Mistral AI Products but excludes model training, and (b) performing our obligations under these Terms or the Additional Terms.

> 4.2. Training. Mistral AI will not use Customer Data or Outputs to train its artificial intelligence models except (a) when you (i) opted-in to training on a Mistral AI Product set to opt-out by default or (ii) have not opted-out of training on a Mistral AI Product set to opt-in by default, (b) when Customer or an End User provides Feedback to Mistral AI, (c) as otherwise may be provided in an Order Form or (d) when Customer uses Labs or Preview Models. Customer grants Mistral AI a perpetual, irrevocable, worldwide, non-exclusive, non-transferable (except as permitted in Section 14.2 (Assignment)), royalty-free, fully-paid license (with the right to sublicense to our service providers) to use Customer Data and Outputs solely as provided in the preceding sentence to train Mistral AI’s artificial intelligence models. Notwithstanding anything to the contrary, the foregoing Customer Data and Outputs will not be considered Customer Confidential Information.

**Đọc cho BO-19:** điều 4.2 — không huấn luyện trên Customer Data và Output, **trừ** khi khách đã opt-in ở sản phẩm mặc định tắt, **hoặc chưa opt-out ở sản phẩm mặc định bật**. Gói free có thuộc loại mặc định bật hay không, các trang đã lấy không nói. PO báo đã tắt training (2026-10-02) — cần **lưu bằng chứng** cấu hình đó trước lần gọi đầu. Ngoại lệ (d): dữ liệu **được** dùng để huấn luyện khi dùng "Labs or Preview Models" — không chọn model nào thuộc loại đó. Vị trí xử lý dữ liệu: chưa lấy được — `[CẦN XÁC MINH]`.

## 3. Structured output

> Custom Structured Outputs allow you to ensure the model provides an answer in a very specific JSON format by supplying a clear JSON schema. This approach allows the model to consistently deliver responses with the correct typing and keywords.

Ví dụ trong trang có `"strict": true` và `"additionalProperties": false`:

```json
"json_schema": {
    "schema": {
      "properties": {
        "name": {
          "title": "Name",
          "type": "string"
        },
        "authors": {
          "items": {
            "type": "string"
          },
          "title": "Authors",
          "type": "array"
        }
      },
      "required": [
        "name",
        "authors"
      ],
      "title": "Book",
      "type": "object",
      "additionalProperties": false
    },
    "name": "book",
    "strict": true
  }
```

**Đọc cho BO-19:** có `strict`. Trang không liệt kê từ khoá JSON Schema nào bị hạn chế — thử ở BUILD MODE.

## 4. Giá và 5. Giới hạn

> Your Mistral plan defines the included monthly usage and limits available to your Organization.
>
> - **Free mode** lets you create API keys and use included monthly usage within the limits shown on the Limits page.
> - **Pay-as-you-go** lets you extend usage beyond included monthly usage. It is not a separate plan for the API.
>
> For current pricing and model availability, see [Mistral pricing](https://mistral.ai/pricing/). To review your plan, included monthly usage, and pay-as-you-go settings, see [Subscriptions](/admin/billing-usage/subscriptions).
>
>

> Rate limits apply at the Workspace level and are shared across all API keys in that Workspace. If multiple applications use keys from the same Workspace, their combined traffic counts against the same limits.
>
> Rate limits include:
>
> - **Requests per second (RPS)**: maximum concurrent API requests.
> - **Tokens per minute**: throughput limit for token processing.
> - **Tokens per month**: overall consumption cap.
>
>

**Đọc cho BO-19:** "Free mode" — tên hiện tại của gói PO gọi là Experiment — dùng được trong "included monthly usage within the limits shown on the Limits page". **Con số cụ thể chỉ có trên trang Limits của tài khoản**, không có trong tài liệu công khai: `[CẦN XÁC MINH]` — PO chụp hoặc chép trang Limits của tài khoản vào đây. Model Mistral cho hai tier: PO chưa chọn.
