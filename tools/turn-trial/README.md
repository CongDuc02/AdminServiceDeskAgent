# `tools/turn-trial/` — đo thời lượng một lượt `intake_graph` với Groq thật (B6b, O1-13)

Không phải mã ứng dụng, không vào image. Đóng **O1-13** (P1 + P2 nối tiếp có vừa WV-04 = 8 s mỗi lời gọi và WV-02 = 20 s mỗi lượt không) và báo **hai tỷ lệ riêng** của `request_slots_write`:
`QUOTE_NOT_IN_MESSAGE` và `VALUE_NOT_IN_QUOTE` (PO, 2026-10-09).

## Làm gì

Chạy `IntakeRunner.run_turn` thật — graph, checkpointer, tool, gateway — trên một **database tạm** do tool tự tạo trên PostgreSQL local (áp `migrate_main`, dựng nhân viên giả, chạy các lượt, xoá database).
11 lượt kịch bản (`SCENARIOS` trong `turn_trial.py`), khoảng 18 lời gọi thật, tối đa 24. Có lượt cố ý đủ dấu/thiếu dấu, viết hoa, hai khoảng trắng, dạng tổ hợp (NFD) — để thử luật so khớp của `value`.

## Luật

- **Chỉ văn bản bịa có nhãn "(giả)"** (A-080). **Chỉ ghi số và mã** — không văn bản tin nhắn, không văn bản trả lời, không giá trị slot.
- **Khoá API:** chỉ biến môi trường `BO19_LLM_API_KEY` do người chạy tự nhập (`read -rs`). Tool không đọc `.env`; không trên dòng lệnh, không in, không ghi.
- **Hạn mức:** tối đa 24 lời gọi; dưới 60.000 token mỗi model (kể cả token suy luận); giãn nhịp dưới 6.500 token/phút (gói Free: 8K TPM mỗi model, `docs/reference/llm-groq.md` mục 5).
- **Gọi mạng thật chỉ khi có `--confirm-real`** — không có cờ này tool chỉ in kế hoạch và thoát mã `3`.

## Chạy

Cần container `pg` (PostgreSQL local, mạng `ci`) đang chạy: `docker start pg`. Từ thư mục gốc repo, trong Git Bash:

```bash
read -rs BO19_LLM_API_KEY; echo; export BO19_LLM_API_KEY      # nhập khoá local (không hiện ra màn hình)
MSYS_NO_PATHCONV=1 docker run --rm --network ci -v "$PWD":/repo -w /repo \
  -e BO19_LLM_API_KEY -e BO19_TRIAL_PG_ADMIN_DSN=postgresql://postgres@pg:5432/postgres \
  -e PYTHONPATH=/repo/backend/src --entrypoint python bo19-b3 tools/turn-trial/turn_trial.py --confirm-real
unset BO19_LLM_API_KEY
```

Tuỳ chọn: `--only S1,S2,S2b` chạy một phần · `--prior-calls N` trừ số lời gọi đã tiêu ở lần trước khỏi hạn mức 24 · `--turn-deadline 20` · `--no-publish` không ghi `docs/reference/` · `--keep-db` giữ database tạm để soi.
`-e BO19_LLM_API_KEY` (không có `=`) chuyển giá trị từ shell của bạn vào container mà không đưa nó lên dòng lệnh.

Mã thoát: `0` xong · `2` thiếu khoá hoặc DSN · `3` chưa `--confirm-real`.
Kết quả: in ra màn hình, `tools/turn-trial/out/results.json` (gitignored) và `docs/reference/turn-trial-b6b.md` (chỉ số và mã; tool in sha256 của file).

`backend/tests/test_turn_trial.py` chạy toàn bộ tool với server giả ở mỗi lần CI (không mạng, không khoá thật).
