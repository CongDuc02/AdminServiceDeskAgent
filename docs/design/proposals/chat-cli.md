# Đề xuất phạm vi — CLI chat tối giản ở local (`tools/chat-cli/`), sau B7

**Trạng thái:** chờ PO duyệt · **Ngày:** 2026-10-12 · **Người đề xuất:** người triển khai · **Nguồn:** PO, duyệt kế hoạch B7 (2026-10-12) — rủi ro R1-5 của `12-roadmap.md` · **Khuôn chốt chặn:** `tools/turn-trial/` (B6b)

## 1. Vấn đề

Chất lượng hội thoại — P1 hiểu sai ý, câu hỏi lại gượng, `example_phrases` thiếu cách nói thật — chỉ lộ ra khi người thật chat (R1-5). Test dùng transport giả; turn-trial chạy 11 kịch bản cố định. Client nửa nhân viên ở B10a, sau bốn lát risk-first. CLI cho PO chat với `intake_graph` thật qua Groq **ngay sau B7**, không chờ client.

## 2. Phạm vi đề xuất

**Làm:**

1. Một script Python `tools/chat-cli/chat_cli.py`, **không phải mã ứng dụng, không vào image** — như `tools/turn-trial/`. Chạy trong container `bo19-b3`, cùng mạng `ci` với container `pg`.
2. **Database tạm** cho mỗi lần chạy: tạo database riêng, áp `migrate_main`, dựng **một** `employee` giả mang nhãn `(GIẢ)` — cách dựng của `TrialDb` ở turn-trial. Thoát thì xoá database; `--keep-db` giữ lại để soi.
3. Vòng hỏi đáp: PO gõ một tin → `chat_message_append` → `IntakeRunner.run_turn` thật (graph, checkpointer, tool, gateway thật) → in câu trả lời của agent (đọc tin agent từ DB) và **một dòng trạng thái chỉ có mã**: `reply_template_id`, `intent_result`, trạng thái `request`, thời lượng lượt, số lời gọi và token của lượt.
4. Lệnh trong vòng hỏi đáp, đi qua đúng thao tác của `tool_layer` — không SQL tự viết:
   - `/slots` — bảng slot của `request` đang mở: tên, nhãn, `value_status`, giá trị. Đây là chỗ duy nhất in giá trị — xem câu hỏi Q2.
   - `/confirm <tên slot> …` — `request_slot_confirm` cho từng slot chỉ đích danh, với `row_version` đang có. Không có "xác nhận tất cả", như F1.
   - `/submit` — `request_submit` của B7; in mã kết quả, hoặc `REQUEST_NOT_READY` kèm tên slot.
   - `/new` — mở phiên mới; `/quit`.
5. In tổng cuối lần chạy: số lượt, số lời gọi, token theo model, số lời gọi lỗi kèm `subcode`.

**Không làm:** HTTP, SSE hay client; lưu bản ghi hội thoại; chấm điểm chất lượng tự động; kịch bản cố định — việc của turn-trial; nhân viên thứ hai hay vai trò cán bộ.

## 3. Chốt chặn — cùng khuôn turn-trial

| Chốt | Cách giữ |
|---|---|
| Gọi mạng thật chỉ khi có `--confirm-real` | Thiếu cờ thì in kế hoạch, thoát mã `3` |
| Khoá API chỉ từ biến môi trường `BO19_LLM_API_KEY` | Người chạy nhập bằng `read -rs`; tool không đọc `.env`, không nhận khoá trên dòng lệnh, không in, không ghi |
| Không ghi nội dung ra file | Không file kết quả nào: tin nhắn, câu trả lời, giá trị slot chỉ hiện trên màn hình. Log kỹ thuật bỏ đi; chỉ giữ trường của `LLM_PROVIDER_ERROR` — chỉ mã và số — để in ở tổng cuối |
| Chỉ dữ liệu giả (A-080, ADR-032 mốc 2) | Không ép được bằng mã: PO tự gõ. Tool in nhắc ở đầu mỗi lần chạy; `employee` giả mang nhãn `(GIẢ)` |
| Hạn mức Groq gói Free | Trần lời gọi mỗi lần chạy — câu hỏi Q1; giãn nhịp dưới 6.500 token/phút như turn-trial; hết hạn mức thì dừng nhận tin, in tổng |
| Test | `backend/tests/test_chat_cli.py` chạy tool với server giả ở CI, stdin là kịch bản: không mạng, không khoá thật; đòi không file nào được ghi, khoá không lọt ra stdout, database tạm bị xoá |

## 4. Câu hỏi cho PO — kèm mặc định

| # | Câu hỏi | Mặc định |
|---|---|---|
| Q1 | Trần lời gọi mỗi lần chạy | **40** — khoảng 20 lượt có P1 + P2; Groq Free 8K TPM mỗi model nên giãn nhịp quyết tốc độ, không phải trần này |
| Q2 | `/slots` in giá trị, kể cả `RES` (`purpose`), ra màn hình | **Có** — chỉ màn hình, không file; PO cần thấy model trích gì mới đánh giá được chất lượng. Bỏ thì `/slots` chỉ còn tên và `value_status` |
| Q3 | Có `/confirm` và `/submit` không, hay chỉ chat | **Có** — thử được hành trình nhân viên tới `SUBMITTED`; job `render_document` đứng ở hàng đợi vì chưa có worker (B8a) |

Ước lượng: một lát nhỏ, một script cộng một file test, chen trước B8a. Duyệt thì làm trên nhánh `build/b7b-chat-cli`.
