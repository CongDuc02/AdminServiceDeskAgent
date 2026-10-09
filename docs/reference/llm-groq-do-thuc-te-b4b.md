# Groq — số đo lời gọi thật ở B4b (số và mã; không có nội dung model trả về)

- **Ngày đo:** 2026-10-05. **Công cụ:** `tools/llm-probe/llm_probe.py`. Nội dung gửi đi: văn bản bịa có nhãn "(giả)" (A-080).
- **Nguồn gốc — ghi rõ (PO, 2026-10-05):** đây là kết quả của một lần chạy **ngoài kế hoạch**: tool tự đọc khoá trong `.env` khi bị gọi để kiểm mã thoát thiếu khoá, rồi một phép đột biến kích hoạt lại nó (29 lời gọi, `--prior-calls 9`). Nội dung gửi vẫn chỉ là văn bản bịa có nhãn "(giả)"; kết quả vẫn qua `self_check`. **Không có `tiktoken`** nên cột "nhìn thấy" trống và O1-3 chưa kết luận được. Số đo được PO cho phép dùng. Chi tiết sự cố: `CHANGELOG.md`, mục B4b. Lần chạy có `tiktoken`: `llm-groq-do-thuc-te-b4b-lan2.md` (khi có).
- Bảng dưới chỉ có số token, mã HTTP, `finish_reason` và cờ. Thân lỗi bên dưới đã che định danh bằng `<masked>` và `self_check` của tool đạt trước khi ghi.

## Lời gọi

| nhãn | model | HTTP | prompt | completion | reasoning | nhìn thấy | finish | hợp schema | có trường suy luận | loại lỗi | code |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E1-p1-1 | openai/gpt-oss-20b | 200 | 1640 | 63 | 19 | None | stop | True | True (<=200) | None | None |
| E1-p1-2 | openai/gpt-oss-20b | 200 | 1640 | 65 | 21 | None | stop | True | True (<=200) | None | None |
| E1-p1-3 | openai/gpt-oss-20b | 200 | 1640 | 65 | 21 | None | stop | True | True (<=200) | None | None |
| E1-p1-4 | openai/gpt-oss-20b | 200 | 1640 | 63 | 19 | None | stop | True | True (<=200) | None | None |
| E1-p1-5 | openai/gpt-oss-20b | 200 | 1640 | 64 | 20 | None | stop | True | True (<=200) | None | None |
| E2-classify_intent-1 | openai/gpt-oss-20b | 200 | 1642 | 74 | 28 | None | stop | True | True (<=200) | None | None |
| E2-classify_intent-2 | openai/gpt-oss-20b | 200 | 1642 | 70 | 31 | None | stop | True | True (<=200) | None | None |
| E2-classify_intent-3 | openai/gpt-oss-20b | 200 | 1642 | 70 | 31 | None | stop | True | True (<=200) | None | None |
| E2-extract_slots-1 | openai/gpt-oss-20b | 200 | 598 | 817 | 691 | None | stop | True | True (>200) | None | None |
| E2-extract_slots-2 | openai/gpt-oss-20b | 200 | 598 | 663 | 540 | None | stop | True | True (>200) | None | None |
| E2-extract_slots-3 | openai/gpt-oss-20b | 200 | 598 | 521 | 398 | None | stop | True | True (>200) | None | None |
| E2-draft_free_content-1 | openai/gpt-oss-120b | 200 | 463 | 238 | 177 | None | stop | True | True (>200) | None | None |
| E2-draft_free_content-2 | openai/gpt-oss-120b | 200 | 463 | 341 | 272 | None | stop | True | True (>200) | None | None |
| E2-draft_free_content-3 | openai/gpt-oss-120b | 200 | 463 | 297 | 240 | None | stop | True | True (>200) | None | None |
| E4-p1-cap48 | openai/gpt-oss-20b | 400 | None | None | None | None | None | None | None (None) | invalid_request_error | json_validate_failed |
| E4-p1-cap48 | openai/gpt-oss-20b | 400 | None | None | None | None | None | None | None (None) | invalid_request_error | json_validate_failed |
| E4-p1-cap128 | openai/gpt-oss-20b | 200 | 1640 | 84 | 40 | None | stop | True | True (<=200) | None | None |
| E4-p4-cap64 | openai/gpt-oss-120b | 400 | None | None | None | None | None | None | None (None) | invalid_request_error | json_validate_failed |
| E4-p4-cap256 | openai/gpt-oss-120b | 400 | None | None | None | None | None | None | None (None) | invalid_request_error | json_validate_failed |
| E5-khoa-sai | openai/gpt-oss-20b | 401 | None | None | None | None | None | None | None (None) | invalid_request_error | invalid_api_key |
| E5-model-khong-ton-tai | openai/model-khong-ton-tai | 404 | None | None | None | None | None | None | None (None) | invalid_request_error | model_not_found |
| E5-reasoning-effort-ngoai-mien | openai/gpt-oss-20b | 400 | None | None | None | None | None | None | None (None) | invalid_request_error | None |
| E5-schema-sai | openai/gpt-oss-20b | 400 | None | None | None | None | None | None | None (None) | invalid_request_error | None |
| E6-CHEAP-mac-dinh | openai/gpt-oss-20b | 200 | 76 | 33 | 22 | None | stop | None | True (<=200) | None | None |
| E6-CHEAP-include_reasoning-false | openai/gpt-oss-20b | 200 | 76 | 33 | 22 | None | stop | None | False (None) | None | None |
| E6-CHEAP-reasoning_format-hidden | openai/gpt-oss-20b | 200 | 76 | 128 | 31 | None | length | None | False (None) | None | None |
| E6-STRONG-mac-dinh | openai/gpt-oss-120b | 200 | 76 | 68 | 58 | None | stop | None | True (>200) | None | None |
| E6-STRONG-include_reasoning-false | openai/gpt-oss-120b | 200 | 76 | 84 | 72 | None | stop | None | False (None) | None | None |
| E6-STRONG-reasoning_format-hidden | openai/gpt-oss-120b | 200 | 76 | 83 | 60 | None | stop | None | False (None) | None | None |

## Gợi ý O1-3 (không phải kết luận)

```json
{
  "gợi_ý": "KHÔNG ĐO ĐƯỢC",
  "dung_sai": "max(5 token, 5%) — do người triển khai chọn",
  "dòng": []
}
```

## Thân lỗi (E5, E6) — đã che

### E5-khoa-sai — HTTP 401

```json
{
  "error": {
    "message": "Invalid API Key",
    "type": "invalid_request_error",
    "code": "invalid_api_key"
  }
}
```

### E5-model-khong-ton-tai — HTTP 404

```json
{
  "error": {
    "message": "The model `openai/model-khong-ton-tai` does not exist or you do not have access to it.",
    "type": "invalid_request_error",
    "code": "model_not_found"
  }
}
```

### E5-reasoning-effort-ngoai-mien — HTTP 400

```json
{
  "error": {
    "message": "'reasoning_effort' : value is not one of the allowed values ['none','default','minimal','low','medium','high','xhigh','max']",
    "type": "invalid_request_error"
  }
}
```

### E5-schema-sai — HTTP 400

```json
{
  "error": {
    "message": "invalid JSON schema for response_format: 'E5_schema_sai': preprocess pipeline: expected object root, got bool",
    "type": "invalid_request_error",
    "param": "response_format"
  }
}
```

