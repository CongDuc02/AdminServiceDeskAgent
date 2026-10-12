# Đo thời lượng một lượt `intake_graph` với Groq thật — B6b (O1-13)

- **Công cụ:** `tools/turn-trial/turn_trial.py`. **Chỉ số và mã** — không văn bản tin nhắn, không văn bản trả lời, không giá trị slot. Mọi tin nhắn thử mang nhãn "(giả)".
- **Hồ sơ model:** {"classify_intent": {"model": "openai/gpt-oss-20b", "reasoning_effort": "low", "temperature": 0.2, "include_reasoning": false, "max_completion_tokens": 512}, "extract_slots": {"model": "openai/gpt-oss-20b", "reasoning_effort": "low", "temperature": 0.2, "include_reasoning": false, "max_completion_tokens": 2048}}. **n nhỏ** (11 lượt, 18 lời gọi): phân phối dưới đây là số đo, không phải kết luận thống kê.

## Thời lượng (ms)

| Đại lượng | n | min | p50 | p90 | max | mean |
|---|---|---|---|---|---|---|
| P1 `classify_intent` — mỗi lời gọi (WV-04 = 8.000) | 11 | 904 | 1081 | 1246 | 8022 | 1694 |
| P2 `extract_slots` — mỗi lời gọi (WV-04 = 8.000) | 7 | 1079 | 1482 | 1689 | 1746 | 1465 |
| Cả lượt có P1 + P2 (WV-02 = 20.000) | 7 | 2380 | 2781 | 2850 | 2884 | 2690 |
| Cả lượt, mọi lượt (WV-02 = 20.000) | 11 | 982 | 2582 | 2884 | 8591 | 2813 |

Lời gọi vượt WV-04: P1 **1**, P2 **0**. Lượt vượt WV-02: **0**. Lời gọi không `OK`/`PARSE_REPAIRED`: **1**. Lượt đi nhánh lỗi: **1**.

## `EVIDENCE_MISMATCH` — hai tỷ lệ riêng (PO, 2026-10-09)

- Slot P2 trả về (đã ghi + bị loại): **13** trong 7 lượt gọi P2.
- `QUOTE_NOT_IN_MESSAGE`: **1** — tỷ lệ **0.077**.
- `VALUE_NOT_IN_QUOTE`: **0** — tỷ lệ **0.0**.
- Lượt có ít nhất một `EVIDENCE_MISMATCH`: **1** / 7.

## Từng lượt

| Kịch bản | Khuôn trả lời | `intent_result` | Lỗi | Cả lượt (ms) | Lời gọi (tên: ms / ms phía provider) | Slot trả về | Mã loại |
|---|---|---|---|---|---|---|---|
| S1 | ASK_SLOT_RETRY | SUPPORTED |  | 2884 | classify_intent: 1246 / 64; extract_slots: 1458 / 711 | 3 | EVIDENCE_MISMATCH:QUOTE_NOT_IN_MESSAGE |
| S2 | CONFIRM_PROPOSALS | SUPPORTED |  | 2582 | classify_intent: 959 / 92; extract_slots: 1482 / 429 | 2 |  |
| S2b | CONFIRM_PROPOSALS | SUPPORTED |  | 2551 | classify_intent: 1093 / 133; extract_slots: 1193 / 468 | 1 |  |
| S3 | CONFIRM_PROPOSALS | SUPPORTED |  | 2804 | classify_intent: 909 / 81; extract_slots: 1746 / 954 | 2 |  |
| S4 | CONFIRM_PROPOSALS | SUPPORTED |  | 2380 | classify_intent: 1067 / 85; extract_slots: 1079 / 318 | 2 |  |
| S5 | ASK_PURPOSE_RETRY | SUPPORTED |  | 2850 | classify_intent: 1063 / 91; extract_slots: 1689 / 888 | 2 | RULE_FAILED:RULE_MIN_TOKENS |
| S5b | CONFIRM_PROPOSALS | SUPPORTED |  | 2781 | classify_intent: 1081 / 100; extract_slots: 1610 / 760 | 1 |  |
| S6 | OUT_OF_SCOPE_GENERIC | OUT_OF_SCOPE |  | 982 | classify_intent: 904 / 73 | 0 |  |
| S7 | ERROR_BUSY | None | PROVIDER_CALL_FAILED | 8591 | classify_intent: 8022 / None (ước lượng) [PROVIDER_ERROR] | 0 |  |
| S8 | CLARIFY_TYPE_NO_CANDIDATE | AMBIGUOUS |  | 1321 | classify_intent: 1142 / 116 | 0 |  |
| S9 | CLARIFY_TYPE | MULTIPLE |  | 1218 | classify_intent: 1148 / 215 | 0 |  |

Điều kiện O1-13 (`12-roadmap.md`): P1 + P2 nối tiếp phải vừa WV-04 cho từng lời gọi và WV-02 cho cả lượt — PO quyết trên số đo này nếu chưa vừa.
