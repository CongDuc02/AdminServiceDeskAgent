# Chạy `render_document` với Groq thật — b9a (B9a)

- **Công cụ:** `tools/render-trial/render_trial.py`. **Chỉ số, mã và cờ đúng/sai** — không văn bản do LLM sinh, không giá trị slot. Mọi văn bản đầu vào mang nhãn "(giả)" (A-080).
- **Hồ sơ model của P4:** `openai/gpt-oss-120b`, `max_completion_tokens` 2048. **n nhỏ** (3 job, 3 lời gọi, 2797 token): số đo, không phải thống kê.

| Job | Job `status` | Lỗi | `document` | Cả job (ms) | Lời gọi (tên: ms / ms phía provider / token) | Lần sinh (số · kết quả · độ dài) | `Subject` đúng | `Author` trung lập | DB `watermark_text` đúng |
|---|---|---|---|---|---|---|---|---|---|
| 1 | SUCCEEDED |  | PENDING_APPROVAL | 4366 | draft_free_content: 1950 / 727 / 805 | 1 · PASSED · 79 | True | True | True |
| 2 | SUCCEEDED |  | PENDING_APPROVAL | 4420 | draft_free_content: 1747 / 958 / 923 | 1 · PASSED · 96 | True | True | True |
| 3 | SUCCEEDED |  | PENDING_APPROVAL | 4318 | draft_free_content: 2108 / 1255 / 1069 | 1 · PASSED · 101 | True | True | True |
