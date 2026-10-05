# Groq — dạng request `response_format` của structured outputs, lấy từ nguồn gốc bằng `curl`

- **Ngày lấy:** 2026-10-05. **Cách lấy:** `curl -sS -L` — không công cụ tóm tắt web (`CLAUDE.md`, mục Luật thao tác). Excerpt chép bằng script từ file đã tải (đã bỏ thẻ HTML).
- **Vì sao có file này:** `llm-groq.md` mục 3 ghi điều kiện của `strict: true` nhưng **không** có ví dụ thân request; ADR-035 nói "`response_format` loại `json_schema` với `strict: true`" mà không nêu cấu trúc lồng. B4 dựng adapter nên cần bản gốc (luật trích dẫn của `CLAUDE.md`).
- **Nguồn:** `https://console.groq.com/docs/structured-outputs` — 764881 byte — sha256 `8b5f30e7dfeb96c457775ad03a8467c0b4bf8b66c41deb0707022ee47718f1ed`. Trang `https://console.groq.com/docs/api-reference` (1531764 byte, sha256 `6c834e38d01d798109d56fa08aaec888c46302cfbce494729c52d2a739004657`) cũng đã tải: không tìm thấy định dạng thân lỗi của chat completions ở đó — xem mục 3.

## 1. Thân request mẫu — dòng 2450–2490 của văn bản đã bỏ thẻ HTML

```text
curl https://api.groq.com/openai/v1/chat/completions \
  -H "Authorization: Bearer $GROQ_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-oss-20b",
    "messages": [
      {
        "role": "system",
        "content": "Extract product review information from the text."
      },
      {
        "role": "user",
        "content": "I bought the UltraSound Headphones last week and I'\''m really impressed! The noise cancellation is amazing and the battery lasts all day. Sound quality is crisp and clear. I'\''d give it 4.5 out of 5 stars."
      }
    ],
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "name": "product_review",
        "strict": true,
        "schema": {
          "type": "object",
          "properties": {
            "product_name": { "type": "string" },
            "rating": { "type": "number" },
            "sentiment": { 
              "type": "string",
              "enum": ["positive", "negative", "neutral"]
            },
            "key_features": { 
              "type": "array",
              "items": { "type": "string" }
            }
          },
          "required": ["product_name", "rating", "sentiment", "key_features"],
          "additionalProperties": false
        }
      }
    }
  }'
```

## 2. Điều rút ra

- `response_format` = `{"type": "json_schema", "json_schema": {"name": <tên>, "strict": true, "schema": <JSON Schema>}}`. Đường dẫn `POST {base_url}/chat/completions`, header `Authorization: Bearer <khoá>`.
- Nội dung trả về nằm ở `choices[0].message.content` dưới dạng chuỗi JSON (ví dụ của trang dùng `JSON.parse(response.choices[0].message.content)`).
- Schema ví dụ có `required` liệt kê mọi property và `additionalProperties: false` — khớp điều kiện đã ghi ở `llm-groq.md` mục 3.

## 3. Không có trong nguồn — nói thẳng

- **Từ khoá `maxLength`, `minLength`, `minItems`, `maxItems`, `const` có được `strict` chấp nhận hay không:** trang không nói. Schema ở `07-prompts.md` dùng chúng. Kiểm bằng lời gọi thật ở B4b (A-089).
- **Định dạng thân lỗi (4xx/5xx) của chat completions:** không có ở hai trang đã tải. Code đọc thân lỗi theo dạng OpenAI một cách dung thứ và chỉ giữ hai trường ngắn có khuôn cố định (A-091).
- **`max_completion_tokens` / `max_tokens`:** không có trong excerpt, nên B4 không gửi (A-090).
