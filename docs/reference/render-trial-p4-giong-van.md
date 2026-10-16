# Chạy `render_document` với Groq thật — b9a (B9a)

- **Công cụ:** `tools/render-trial/render_trial.py`. **Chỉ số, mã và cờ đúng/sai** — không văn bản do LLM sinh, không giá trị slot. Mọi văn bản đầu vào mang nhãn "(giả)" (A-080).
- **Hồ sơ model của P4:** `openai/gpt-oss-120b`, `max_completion_tokens` 2048. **n nhỏ** (3 job, 3 lời gọi, 2938 token): số đo, không phải thống kê.

| Job | Job `status` | Lỗi | `document` | Cả job (ms) | Lời gọi (tên: ms / ms phía provider / token) | Lần sinh (số · kết quả · độ dài) | Còn cụm đơn xin | Có Ông/Bà | `Subject` đúng | `Author` trung lập | DB `watermark_text` đúng |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | SUCCEEDED |  | PENDING_APPROVAL | 5143 | draft_free_content: 1941 / 408 / 918 | 1 · PASSED · 73 | False | True | True | True | True |
| 2 | SUCCEEDED |  | PENDING_APPROVAL | 4452 | draft_free_content: 1533 / 597 / 1016 | 1 · PASSED · 89 | False* | True | True | True | True |
| 3 | SUCCEEDED |  | PENDING_APPROVAL | 5488 | draft_free_content: 2898 / 568 / 1004 | 1 · PASSED · 106 | False | True | True | True | True |

\* Bản đầu của công cụ đánh dấu `True` vì cụm "xin cấp" trong "làm thủ tục **xin cấp** thị thực" — chữ của chính mục đích, không phải giọng đơn xin. Đã bỏ "xin cấp" khỏi bộ cụm đo; ô được sửa tay ở đây vì đã đọc cả ba PDF.

## Ba câu P4 bản 1.1 sinh ra (dữ liệu giả, đọc từ PDF)

PO yêu cầu 2026-10-16 (P4 giọng bên phát hành). Prompt `draft_free_content` bản `1.1` (`07-prompts.md` mục 4.4); 3 job, 3 lời gọi — **tổng 7 trên 10** lời gọi PO cho phép.

1. "Giấy xác nhận này được cấp để Ông/Bà bổ sung hồ sơ vay vốn tại ngân hàng."
2. "Giấy xác nhận này được cấp để Ông/Bà làm thủ tục xin cấp thị thực đi công tác nước ngoài."
3. "Giấy xác nhận này được cấp để Ông/Bà (giả) mở thẻ tín dụng tại ngân hàng nơi nhân viên có tài khoản lương."

Cả ba đúng giọng bên phát hành, không giọng đơn xin, không lặp nơi nhận hay họ tên. **Điểm còn yếu (n = 3):** câu 3 chép khá sát mục đích — mang nguyên nhãn "(giả)" và cụm "nơi nhân viên có tài khoản lương" (nói về nhân viên ở ngôi thứ ba, trong khi văn bản gọi người được cấp là "Ông/Bà"). Câu 1 không có tên ngân hàng vì `recipient_org` bị cấm làm input của P4 (đúng thiết kế).

**PDF nháp để đọc:** `docs/reference/render-trial-p4-giong-van-ban-nhap.pdf` — sha256 `f62b52651902f45acbcec29991e2b5ccfe6c5f5cf572af206396ba12b510dea6` — job 1. Quét host, khoá, định danh bằng `tools/render-trial/scan_pdf.py`: 0 giá trị biến môi trường; 0 khoá, DSN, email, UUID, chuỗi hex dài, từ chỉ nhà cung cấp hay đường dẫn máy; chỉ còn không gian tên XMP chuẩn, giấy phép phông Liberation Serif và số phiên bản LibreOffice. `/Subject` = chuỗi watermark, `/Author` = tên hệ thống. Cùng hai điều của mẫu giả đã ghi ở `render-trial-b9a-ban-nhap.md` (khổ Letter, ngày XMP 2013).
