# Groq — số đo lời gọi thật ở B4b, lần 2 (có `tiktoken`; số và mã; không có nội dung model trả về)

- **Ngày đo:** 2026-10-05. **Công cụ:** `tools/llm-probe/llm_probe.py`. Nội dung gửi đi: văn bản bịa có nhãn "(giả)" (A-080). Lần 1 (ngoài kế hoạch, không có `tiktoken`): `llm-groq-do-thuc-te-b4b.md`.
- Bảng dưới chỉ có số token, mã HTTP, `finish_reason` và cờ. Thân lỗi bên dưới đã che định danh bằng `<masked>` và `self_check` của tool đạt trước khi ghi.

## Lời gọi

| nhãn | model | HTTP | prompt | completion | reasoning | nhìn thấy | finish | hợp schema | có trường suy luận | loại lỗi | code |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E2-classify_intent-1 | openai/gpt-oss-20b | 200 | 1642 | 74 | 28 | 27 | stop | True | False (None) | None | None |
| E2-classify_intent-2 | openai/gpt-oss-20b | 200 | 1642 | 71 | 32 | 27 | stop | True | False (None) | None | None |
| E2-classify_intent-3 | openai/gpt-oss-20b | 200 | 1642 | 70 | 31 | 27 | stop | True | False (None) | None | None |
| E2-extract_slots-1 | openai/gpt-oss-20b | 200 | 598 | 667 | 544 | 106 | stop | True | False (None) | None | None |
| E2-extract_slots-2 | openai/gpt-oss-20b | 200 | 598 | 797 | 674 | 106 | stop | True | False (None) | None | None |
| E2-extract_slots-3 | openai/gpt-oss-20b | 200 | 598 | 649 | 523 | 109 | stop | True | False (None) | None | None |
| E2-draft_free_content-1 | openai/gpt-oss-120b | 200 | 463 | 279 | 223 | 37 | stop | True | False (None) | None | None |
| E2-draft_free_content-2 | openai/gpt-oss-120b | 200 | 463 | 180 | 121 | 40 | stop | True | False (None) | None | None |
| E2-draft_free_content-3 | openai/gpt-oss-120b | 200 | 463 | 366 | 290 | 57 | stop | True | False (None) | None | None |
| E4b-p4-cap87-1 | openai/gpt-oss-120b | 400 | None | None | None | None | None | None | None (None) | invalid_request_error | json_validate_failed |
| E4b-p4-cap87-2 | openai/gpt-oss-120b | 400 | None | None | None | None | None | None | None (None) | invalid_request_error | json_validate_failed |
| E4b-p4-cap87-3 | openai/gpt-oss-120b | 400 | None | None | None | None | None | None | None (None) | invalid_request_error | json_validate_failed |

## Gợi ý O1-3 (không phải kết luận)

```json
{
  "gợi_ý": "KHÔNG RÕ / LẪN LỘN",
  "dung_sai": "max(5 token, 5%) — do người triển khai chọn",
  "dòng": [
    {
      "label": "E2-classify_intent-1",
      "completion": 74,
      "reasoning": 28,
      "visible": 27,
      "da_gom_reasoning": false,
      "chua_gom_reasoning": false,
      "khong_ro": true
    },
    {
      "label": "E2-classify_intent-2",
      "completion": 71,
      "reasoning": 32,
      "visible": 27,
      "da_gom_reasoning": false,
      "chua_gom_reasoning": false,
      "khong_ro": true
    },
    {
      "label": "E2-classify_intent-3",
      "completion": 70,
      "reasoning": 31,
      "visible": 27,
      "da_gom_reasoning": false,
      "chua_gom_reasoning": false,
      "khong_ro": true
    },
    {
      "label": "E2-extract_slots-1",
      "completion": 667,
      "reasoning": 544,
      "visible": 106,
      "da_gom_reasoning": true,
      "chua_gom_reasoning": false,
      "khong_ro": false
    },
    {
      "label": "E2-extract_slots-2",
      "completion": 797,
      "reasoning": 674,
      "visible": 106,
      "da_gom_reasoning": true,
      "chua_gom_reasoning": false,
      "khong_ro": false
    },
    {
      "label": "E2-extract_slots-3",
      "completion": 649,
      "reasoning": 523,
      "visible": 109,
      "da_gom_reasoning": true,
      "chua_gom_reasoning": false,
      "khong_ro": false
    },
    {
      "label": "E2-draft_free_content-1",
      "completion": 279,
      "reasoning": 223,
      "visible": 37,
      "da_gom_reasoning": false,
      "chua_gom_reasoning": false,
      "khong_ro": true
    },
    {
      "label": "E2-draft_free_content-2",
      "completion": 180,
      "reasoning": 121,
      "visible": 40,
      "da_gom_reasoning": false,
      "chua_gom_reasoning": false,
      "khong_ro": true
    },
    {
      "label": "E2-draft_free_content-3",
      "completion": 366,
      "reasoning": 290,
      "visible": 57,
      "da_gom_reasoning": false,
      "chua_gom_reasoning": false,
      "khong_ro": true
    }
  ]
}
```

## Gợi ý ngữ nghĩa trần output — E4b (không phải kết luận)

```json
{
  "gợi_ý": "CÓ TÍNH reasoning vào trần",
  "trần": 87,
  "bị_cắt": 3,
  "qua_dù_tổng_sinh_ra_vượt_trần": 0,
  "số_lời_gọi": 3,
  "dòng": [
    {
      "label": "E4b-p4-cap87-1",
      "http": 400,
      "finish": null,
      "completion": null,
      "reasoning": null,
      "visible": null
    },
    {
      "label": "E4b-p4-cap87-2",
      "http": 400,
      "finish": null,
      "completion": null,
      "reasoning": null,
      "visible": null
    },
    {
      "label": "E4b-p4-cap87-3",
      "http": 400,
      "finish": null,
      "completion": null,
      "reasoning": null,
      "visible": null
    }
  ]
}
```

## Thân lỗi (E5, E6) — đã che

## Đọc kết quả (người triển khai, 2026-10-05 — tính từ các số ở bảng trên, không có số nào mới)

**O1-3 — `completion_tokens` so với token nhìn thấy và `reasoning_tokens`** (token nhìn thấy đếm bằng `o200k_harmony`, nội dung bị vứt):

| Lời gọi | completion | nhìn thấy | reasoning | nhìn thấy + reasoning | phần dư (completion − nhìn thấy − reasoning) | completion ÷ nhìn thấy |
|---|---|---|---|---|---|---|
| P1-1 | 74 | 27 | 28 | 55 | 19 | 2,7 |
| P1-2 | 71 | 27 | 32 | 59 | 12 | 2,6 |
| P1-3 | 70 | 27 | 31 | 58 | 12 | 2,6 |
| P2-1 | 667 | 106 | 544 | 650 | 17 | 6,3 |
| P2-2 | 797 | 106 | 674 | 780 | 17 | 7,5 |
| P2-3 | 649 | 109 | 523 | 632 | 17 | 6,0 |
| P4-1 | 279 | 37 | 223 | 260 | 19 | 7,5 |
| P4-2 | 180 | 40 | 121 | 161 | 19 | 4,5 |
| P4-3 | 366 | 57 | 290 | 347 | 19 | 6,4 |

`completion_tokens` **không** gần token nhìn thấy (gấp 2,6–7,5 lần) và **gần** token nhìn thấy cộng `reasoning_tokens`, hơn một phần dư nhỏ, gần không đổi (12–19 token). Gợi ý tự động của tool ghi "KHÔNG RÕ" chỉ vì dung sai `max(5 token, 5%)` do người triển khai chọn hẹp hơn phần dư này ở các lời gọi nhỏ; đọc số thì suy luận **đã nằm trong** `completion_tokens`. Phần dư 12–19 token có thể là khung định dạng của model (chưa xác minh — không nguồn nào trong `docs/reference/` nói).

**Ngữ nghĩa `max_completion_tokens` — E4B:** P4 tier mạnh, trần 87 = token nhìn thấy lớn nhất của P4 (57) + 30, ba lần: **3/3 HTTP 400 `json_validate_failed`**. Nếu trần chỉ đếm token nhìn thấy thì cả ba qua (nhìn thấy 37–57 < 87). Chúng không qua ⇒ trần so với tổng sinh ra **gồm suy luận**. Mẫu nhỏ (n = 3 ở E4B); các điểm của lần chạy 1 (`llm-groq-do-thuc-te-b4b.md`) cùng chiều, không điểm nào ngược.

**Điều không đo được:** (1) phần dư 12–19 token là gì; (2) token đã tiêu của lời gọi bị cắt (HTTP 400 không trả `usage`) — sổ `llm_usage` đếm thiếu các lần đó; (3) thời lượng (`completion_time`) — tool không ghi, nên không biết P2 (~650–800 token sinh ra) có vừa hạn chót tổng 8 s của WV-04 hay không.
