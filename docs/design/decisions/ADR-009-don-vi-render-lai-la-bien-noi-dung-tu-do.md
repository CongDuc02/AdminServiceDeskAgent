# ADR-009 — Đơn vị render lại là một biến nội dung tự do

**Trạng thái:** Accepted · **Ngày:** 2026-09-12 · **Quyết định tại:** Phase 3 — Agent & Tool Architecture · **Liên quan:** A-022, NFR-06 của `01-prd.md`, ADR-001, ADR-008

---

## Context

`_PLAN.md` Phase 3 cấm mặc định rằng mỗi vòng `CHANGES_REQUESTED → DRAFT` là một lần render đầy đủ. Câu trả lời quyết định đơn vị đo của A-022 (trần số lần render lại, token budget) và cách Phase 11 định cỡ chi phí.

"Render" gồm hai lớp có chi phí khác hẳn nhau:

| Lớp | Có gọi LLM? | Tính chất |
|---|---|---|
| Sinh nội dung tự do cho từng biến | Có — model mạnh | Tốn token, bất định |
| Điền biến vào template, xuất `.docx` và `.pdf` | Không | Tất định, không tốn token, output luôn là nguyên file |

Yêu cầu sửa được phân loại **bắt buộc** bởi người duyệt theo `change_scope` (`FREE_CONTENT` hoặc `SLOT_DATA`) kèm danh sách `change_targets`. LLM không đọc lý do sửa để tự quyết phạm vi (mục Đơn vị render lại của `03-agents.md`).

## Options

**A — Mỗi vòng render đầy đủ:** sinh lại mọi biến nội dung tự do, rồi điền và xuất file.

**B — Render lại từng phần:** chỉ sinh lại những biến nội dung tự do nằm trong phạm vi sửa. Điền template và xuất file luôn chạy lại toàn bộ.

**C — Để LLM sửa trực tiếp văn bản** hoàn chỉnh theo lý do sửa.

## Decision

**Chọn B.** Đơn vị render lại là **một biến nội dung tự do**.

- `FREE_CONTENT`: sinh lại đúng các biến trong `change_targets`. Không chọn biến nào thì sinh lại mọi biến nội dung tự do của template.
- `SLOT_DATA`: sau khi nhân viên bổ sung và gửi lại, sinh lại các biến trong `change_targets` **cộng** các biến có input đã khai bị đổi giá trị. Đồ thị phụ thuộc slot → biến lấy thẳng từ danh sách input tự khai của prompt module (ADR-008) — allowlist đồng thời là đồ thị phụ thuộc. Slot được điền thẳng vào template (ví dụ `recipient_org`) mà đổi thì **không** gọi LLM lần nào.
- Biến không thuộc phạm vi được giữ **nguyên văn**.
- Phiên bản template đang hiệu lực đã đổi và danh mục biến nội dung tự do hoặc hướng dẫn soạn của nó đã đổi: sinh lại mọi biến nội dung tự do. Render từng phần không áp dụng qua hai phiên bản template khác nhau.
- Điền template và xuất file luôn chạy lại nguyên file, vì tất định và không tốn token.

## Consequences

**Tích cực**

- A-022 có đơn vị đo rõ, và tách thành **hai trần độc lập, hai đơn vị khác nhau**:
  - Trần số vòng `CHANGES_REQUESTED` của một `document` — đơn vị là **vòng**, chặn vòng qua lại giữa người và hệ thống, bất kể mỗi vòng tốn bao nhiêu token.
  - Token budget mỗi `request` — nguyên tử chi phí là **một lần sinh một biến nội dung tự do**. Một vòng có thể tốn 0 token (sửa `SLOT_DATA` chỉ chạm biến điền thẳng).
- Người duyệt chỉ phải đọc lại phần mình yêu cầu sửa. Văn bản đã được chấp nhận ở vòng trước không bị viết lại âm thầm.

**Tiêu cực và cái phải chấp nhận**

- **Ở Sprint đầu lợi ích về token gần như bằng không** với `FREE_CONTENT`: mỗi template hiện chỉ có một biến nội dung tự do (`purpose_statement` hoặc `work_content_statement`), nên sinh lại "từng phần" và "toàn bộ" là một. Lợi ích thật nằm ở ca `SLOT_DATA` chạm biến điền thẳng, và ở template về sau có nhiều biến.
- Hai biến sinh ở hai vòng khác nhau có thể lệch giọng hoặc lệch ý với nhau. Chỉ xảy ra khi template có từ hai biến nội dung tự do trở lên.
- Phải lưu lại input đã dùng cho mỗi lần sinh một biến, để tính được biến nào bị ảnh hưởng — thuộc Phase 4.

**Điều kiện đảo ngược** — tín hiệu đo ở rubric human eval của Phase 10: người duyệt đánh dấu văn bản lệch ý giữa các biến sinh ở vòng khác nhau. Khi tín hiệu xuất hiện, xét lại cho **template đó** — ví dụ gộp biến — không đảo cho mọi template.

## Rejected alternatives

**A — Render đầy đủ mỗi vòng.** Bị loại không chỉ vì tốn token — ở Sprint đầu chênh lệch token gần như bằng không. Lý do chính: sinh lại biến mà người duyệt **không** yêu cầu sửa sẽ đổi câu chữ họ đã chấp nhận, buộc họ đọc lại toàn bộ văn bản ở mỗi vòng. Việc đó bào mòn đúng thứ RISK-02 dựa vào — sự chú ý của người duyệt — và làm cổng HITL kém tác dụng theo số vòng.

**C — LLM sửa văn bản hoàn chỉnh.** Bị loại vì model phải chạm vào văn bản có chứa khung thể thức, đi ngược ADR-001. Và "sửa theo lý do" để model tự quyết phạm vi sửa, tức mở lại đúng kênh injection mà việc bắt người duyệt chọn `change_targets` đã đóng.
