# `tools/chat-cli/` — chat thử với `intake_graph` thật qua Groq (B7b, R1-5)

Không phải mã ứng dụng, không vào image. Cho PO thử **chất lượng hội thoại** (P1 hiểu ý, câu hỏi lại, `example_phrases`) với Groq thật, trước khi có client. Phạm vi đã duyệt: `docs/design/proposals/chat-cli.md` (PO, 2026-10-13).

## Làm gì

Dựng một database tạm trên PostgreSQL local (như `tools/turn-trial/`), một nhân viên giả `(GIẢ)`, rồi cho bạn chat với `IntakeRunner` thật. Mỗi lượt in câu trả lời của agent và **một dòng chỉ có mã và số**: khuôn trả lời, ý định, thời lượng, lời gọi, token, số lời gọi còn lại, lỗi provider (nếu có).

| Lệnh | Việc |
|---|---|
| (nội dung thường) | Một lượt chat |
| `/slots` | Bảng slot của yêu cầu đang mở — **in cả giá trị, kể cả `RES`, chỉ trên màn hình** |
| `/confirm <slot> …` | `request_slot_confirm` cho từng slot gõ đích danh. Không có "xác nhận tất cả" |
| `/submit` | `request_submit` — in `REQUEST_NOT_READY` kèm tên slot, hoặc báo đã gửi (job `render_document` đứng hàng đợi, chưa có worker tới B8a) |
| `/new` | Nhân viên giả mới, phiên mới |
| `/quit` | Thoát, in tổng |

## Luật (PO)

- **Chỉ thông tin bịa.** Mọi nội dung gõ vào được gửi tới Groq ở nước ngoài (A-080). Lúc khởi động CLI in dòng nhắc đó và **bắt nhập `dong y`** — câu khác thoát mã `4`, chưa tạo database, chưa gọi mạng.
- **Không ghi nội dung ra file, log hay history.** Không có file kết quả; log kỹ thuật chỉ đi qua bộ lọc giữ sáu trường lỗi provider; CLI đọc stdin thô, không nạp `readline`; database tạm bị xoá khi thoát — **không có `--keep-db`**.
- **Khoá API chỉ từ biến môi trường `BO19_LLM_API_KEY`**; không trên dòng lệnh, không in, không ghi; tool không đọc `.env`.
- **Gọi mạng thật chỉ khi có `--confirm-real`.** Tối đa 40 lời gọi mỗi lần chạy (`--max-calls` để hạ thấp); giãn nhịp dưới 6.500 token/phút (gói Free: 8K TPM mỗi model).

## Chạy

Cần container `pg` (`docker start pg`). Từ thư mục gốc repo, trong Git Bash, terminal tương tác:

```bash
read -rs BO19_LLM_API_KEY; echo; export BO19_LLM_API_KEY      # nhập khoá local (không hiện ra màn hình)
MSYS_NO_PATHCONV=1 docker run --rm -it --network ci -v "$PWD":/repo -w /repo \
  -e BO19_LLM_API_KEY -e BO19_TRIAL_PG_ADMIN_DSN=postgresql://postgres@pg:5432/postgres \
  -e PYTHONPATH=/repo/backend/src --entrypoint python bo19-b3 tools/chat-cli/chat_cli.py --confirm-real
unset BO19_LLM_API_KEY
```

Mã thoát: `0` xong · `2` thiếu khoá/DSN hay `--max-calls` ngoài 1..40 · `3` chưa `--confirm-real` · `4` không gõ `dong y`.

`backend/tests/test_chat_cli.py` chạy toàn bộ tool với server giả ở mỗi lần CI (không mạng, không khoá thật).
