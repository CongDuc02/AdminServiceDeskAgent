# `tools/llm-probe/` — đo lời gọi Groq thật (B4b)

Không phải mã ứng dụng, không vào image. Đóng **O1-1**, **O1-3**, **A-089**, **A-091**, ngữ nghĩa trần output (`max_completion_tokens`, A-090) và tìm tham số tắt việc trả nội dung suy luận.
Quyết định: PO duyệt kế hoạch B4b, 2026-10-05.

## Luật

- **Chỉ văn bản bịa có nhãn "(giả)"** (`fixtures.py`; A-080; `docs/testing/nguoi-thu.md`). Tin nhắn trần dài đúng 2.000 ký tự (WV-15), tiếng Việt **có dấu**, văn phong tin nhắn nhân viên.
- **Chỉ ghi số và mã.** Không ghi `message.content`, không ghi nội dung suy luận — ở mọi thí nghiệm. Kết quả thô: `out/results.json` (gitignored).
- **Khoá API:** biến môi trường `BO19_LLM_API_KEY`, hoặc dòng `BO19_LLM_API_KEY=` trong `.env` ở thư mục gốc — **chính tool đọc**; người triển khai không đọc `.env`. Không bao giờ trên dòng lệnh, không in, không ghi.
- **Thân response lưu vào `docs/reference/`** (repo public) được che định danh (`<masked>`: mã tổ chức, request id, chuỗi giống khoá, UUID, email, IP) và **tool tự quét lại** (`self_check`); không đạt thì **không ghi file** và tool báo `KHÔNG ĐẠT`.
- **Hạn mức:** tối đa 40 lời gọi; dưới 60.000 token mỗi model (kể cả token suy luận); giãn nhịp dưới 6.500 token/phút (gói Free: 8K TPM mỗi model, `docs/reference/llm-groq.md` mục 5).

## Thí nghiệm

| # | Đóng | Làm gì |
|---|---|---|
| E1 | O1-1 | P1 với tin nhắn trần 2.000 ký tự và catalog 6 loại giả, 5 lần, `reasoning_effort` `low` — `prompt_tokens`, `completion_tokens`, `reasoning_tokens` thật |
| E2 | O1-3 | P1, P2, P4 (3 lần mỗi module): token nhìn thấy đếm bằng `o200k_harmony` (nội dung bị vứt ngay) so với `completion_tokens` và `reasoning_tokens`. Đồng thời là E3: nếu schema thật được chấp nhận (HTTP 200) thì từ khoá `maxLength`, `minItems`… đã được `strict` chấp nhận |
| E3 | A-089 | Chỉ chạy khi E1/E2 có HTTP 400: tách từng từ khoá bằng schema tối thiểu |
| E4 | Trần output | `max_completion_tokens` nhỏ (48 ×2, 128 với P1; 64, 256 với P4): `finish_reason`, `completion_tokens`, `reasoning_tokens` — trần có tính suy luận không |
| E5 | A-091 | Lỗi cố ý với nội dung giả: khoá sai (chuỗi giả), model không tồn tại, `reasoning_effort` ngoài miền, schema sai — thân lỗi **đã che** vào tài liệu tham chiếu |
| E6 | Suy luận | `include_reasoning: false` và `reasoning_format: "hidden"` trên cả hai tier — tham số nào được chấp nhận và làm biến mất trường suy luận (chỉ cờ có/không và nhóm độ dài, không nội dung) |

## Chạy

`tiktoken` **không** vào lock (PO, 2026-10-05): cài trong container tạm, cùng bản đã dùng ở `docs/reference/llm-token-count-p1-p2.md`.

```bash
# từ thư mục gốc repo; Git Bash cần MSYS_NO_PATHCONV=1
docker run --rm -v "$PWD":/repo -w /repo -e HOME=/tmp -e PYTHONPATH=/repo/backend/src:/tmp/tk --entrypoint sh bo19-b3 -c \
  "pip install -q --target /tmp/tk tiktoken==0.14.0 && python tools/llm-probe/llm_probe.py --confirm-real"
python tools/llm-probe/llm_probe.py --confirm-real --experiments E1,E4 --no-publish      # chạy một phần, không ghi docs/reference/
```

**Gọi mạng thật chỉ khi có `--confirm-real`** — không có cờ này tool chỉ in kế hoạch và thoát mã `3` (thêm sau một lần chạy nhầm ngày 2026-10-05, xem CHANGELOG). `--prior-calls N` trừ số lời gọi đã tiêu ở các lần chạy trước khỏi hạn mức 40.

Mã thoát: `0` xong và `self_check` đạt · `1` `self_check` không đạt · `2` thiếu khoá · `3` chưa xác nhận. Kết quả công bố: `docs/reference/llm-groq-do-thuc-te-b4b.md`.

`backend/tests/test_llm_probe.py` chạy toàn bộ tool với server giả (không mạng, không khoá thật) ở mỗi lần CI.
