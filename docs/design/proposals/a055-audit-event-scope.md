# Đề xuất — A-055: `audit_event` ghi cho thao tác nào

**Trạng thái:** ⏳ Chờ PO duyệt — chưa áp vào file nào · **Ngày:** 2026-09-27 · **Người đề xuất:** người triển khai · **Cổng:** 1.3 của `12-roadmap.md` — chặn khởi động, vì luật này quyết mọi thao tác của `tool_layer` · **Nguồn:** A-055, đầu mục Tool Registry của `03-agents.md`, dòng `audit_event` ở mục Entity của `GLOSSARY.md`, mục Audit log của `08-hitl.md`, mục Rate limit của `09-security.md`, mục Thao tác của `tool_layer` được đặt tên ở Phase 5 của `05-api.md`

---

## 1. Hai hướng A-055 đã nêu

- **Hướng 1 — thu hẹp luật.** Mọi thao tác ghi sinh `audit_event`, trừ một **danh sách miễn đóng**.
- **Hướng 2 — giữ luật, mở rộng định nghĩa.** `audit_event` thành bản ghi của **mọi** lệnh ghi, và chấp nhận hai hệ quả A-055 đã nêu:
  - nhật ký nghiệp vụ lẫn các dòng về hội thoại;
  - mỗi tin nhắn để lại một dòng gắn với một cá nhân mà ứng dụng không xoá được.

## 2. Khuyến nghị: hướng 1

**Lý do, theo thứ tự nặng nhẹ:**

1. **Hệ quả thứ hai của hướng 2 va vào nghĩa vụ xoá.** Văn bản tin nhắn bị xoá khi `EXPIRED` (A-014, đã chốt), nhưng dòng `audit_event` về tin nhắn đó mang `actor_employee_id` và thời điểm, và `bo19_app` chỉ có `INSERT` trên bảng này. Hệ thống sẽ xoá nội dung mà vẫn giữ vĩnh viễn dấu vết "người này nhắn lúc này", cho **từng** tin nhắn. Phạm vi xoá theo Luật Bảo vệ dữ liệu cá nhân năm 2025 và Nghị định 356/2025/NĐ-CP `[CẦN XÁC MINH]` — chưa có văn bản gốc trong `docs/reference/` (A-080). Hướng 1 không tạo ra các dòng đó, nên câu hỏi không phát sinh cho hội thoại.
2. **Thực tế đã là hướng 1, chỉ chưa có tên.** Đã có hai lệch có tên khỏi chữ của luật:
   - module hàng đợi không sinh `audit_event` (vòng duyệt Phase 6; ghi chú "chờ A-055" ở mục Cây backend của `06-structure.md`);
   - `rate_limit_window` cũng không (mục Rate limit của `09-security.md`).

   Ngoài `tool_layer` còn ba mục không sinh `audit_event` — checkpoint, `graph_thread`, `llm_usage` — với cùng lý do "sổ sách kỹ thuật". Hướng 2 buộc gỡ cả hai lệch; hướng 1 chỉ đặt tên cho cái đang có.
3. **Nhật ký nghiệp vụ là thứ người dùng đọc.** `audit.read_own` và phần hiển thị tự duyệt đọc nhật ký này. Loãng bởi hội thoại thì dòng `WARNING` của tự duyệt khó thấy hơn.
4. **Chi phí ghi.** Mỗi index trên `audit_event` được cập nhật ở mọi lệnh ghi (lập luận loại `ix_audit_event_entity` ở `05-api.md`). Hướng 2 nhân số lệnh đó theo số tin nhắn.

**Cái hướng 1 phải trả:** một danh sách miễn phải được giữ đóng. Nếu mỗi phase tự thêm một mục, luật lại trôi. Vì vậy luật đề xuất dưới đây có điều kiện thêm mục.

## 3. Luật đề xuất

**Thay luật ở đầu mục Tool Registry của `03-agents.md`:**

> Mọi thao tác ghi của `tool_layer` sinh `audit_event` trong cùng giao dịch, **trừ** các thao tác trong danh sách miễn ở mục này. Mặc định là sinh: một thao tác mới không có trong danh sách thì sinh `audit_event`. Thêm một mục vào danh sách miễn cần Product Owner duyệt và một dòng `CHANGELOG.md`, kèm lý do thuộc một trong hai loại: **hội thoại** hoặc **sổ sách kỹ thuật**. `stored_file_fetch` là thao tác **đọc** duy nhất sinh `audit_event` (ADR-014).

**Thay định nghĩa `audit_event` ở mục Entity của `GLOSSARY.md`:**

> Bản ghi bất biến về một hành động có ảnh hưởng nghiệp vụ, hoặc về một lần tải bản văn bản ra khỏi hệ thống. Có mức `severity`. Thao tác nào sinh: luật ở đầu mục Tool Registry của `03-agents.md`.

Vế "tải bản văn bản" đưa `stored_file_fetch` vào định nghĩa, thay vì để nó là ngoại lệ ngược.

## 4. Danh sách miễn đề xuất

| Thao tác | Loại | Vì sao miễn | Trạng thái hiện tại |
|---|---|---|---|
| `chat_session_open` | Hội thoại | Mở phiên chat không đổi dữ liệu nghiệp vụ nào. Việc nghiệp vụ bắt đầu ở `request_open`, vẫn sinh `audit_event` | Mới |
| `chat_message_append` | Hội thoại | Lý do 1 ở mục 2. Nội dung tin nhắn đã có bảng riêng với thời hạn lưu riêng (A-010). Hệ quả nghiệp vụ của một tin nhắn đi qua `request_open`, `request_slots_write`, `request_transition` — cả ba vẫn sinh `audit_event` | Mới — thay cho câu "có ghi cho từng tin nhắn chat hay không — A-055" ở mục Audit log của `08-hitl.md` |
| Giành, gia hạn lease, kết thúc job — module hàng đợi | Sổ sách kỹ thuật | Không phải hành động của ai. Thay đổi nghiệp vụ do job gây ra được ghi bởi thao tác mà job gọi | Đang là lệch có tên, Phase 6 |
| Tăng bộ đếm `rate_limit_window` · `rate_limit_window_sweep` | Sổ sách kỹ thuật | Mục Rate limit của `09-security.md` | Đang là lệch có tên, Phase 9 |
| `object_claim_reconcile` | Sổ sách kỹ thuật | Xoá claim chưa commit và object của nó — theo cấu tạo, không gì trong DB trỏ tới chúng (mục Lưu trữ file và bất biến bản render của `04-data.md`) | Chưa ghi rõ ở đâu — luật hiện tại buộc sinh |

**Giữ nguyên — vẫn sinh `audit_event`, dù có thể bị hỏi:**

- **`chat_session_idle_close`** — mỗi phiên một dòng, không phải mỗi tin nhắn. Nó enqueue `checkpoint_purge`, tức xoá dữ liệu cá nhân trong checkpoint. Dòng `audit_event` là bằng chứng hệ thống đã khởi động việc xoá — đúng loại bằng chứng mà nghĩa vụ xoá cần. Bỏ câu "trừ khi A-055 quyết khác" ở mục Audit log của `08-hitl.md`.
- **`notification_send`** — hiếm, và là bằng chứng một người đã được báo về một văn bản dừng hay đã phát hành. Trách nhiệm ở HITL dựa vào việc biết ai đã được báo.
- **`request_slots_write`** — ghi theo lượt, nên dày hơn các thao tác khác. Nhưng nó đổi nội dung của `request`, tức đổi thứ sẽ vào văn bản. Là ảnh hưởng nghiệp vụ.

## 5. Nếu PO duyệt — việc áp

| File | Sửa |
|---|---|
| `03-agents.md` | Luật ở đầu mục Tool Registry theo mục 3, kèm bảng miễn ở mục 4 |
| `GLOSSARY.md` | Định nghĩa `audit_event` theo mục 3 |
| `08-hitl.md` | Mục Audit log: dòng "Hội thoại" bỏ vế A-055; câu về `chat_session_idle_close` bỏ "trừ khi A-055 quyết khác" |
| `05-api.md` | Câu dẫn của mục Thao tác của `tool_layer` được đặt tên ở Phase 5 trỏ luật mới |
| `06-structure.md` | Ghi chú "chờ A-055" ở mục Cây backend thành "thuộc danh sách miễn (A-055)" |
| `09-security.md` | Mục Không sinh `audit_event` — xếp nhóm, không tự giải A-055: đổi tên mục và đổi từ "lệch có tên" thành "thuộc danh sách miễn" |
| `ASSUMPTIONS.md` | A-055 → `Đã chốt — hướng 1` |
| `12-roadmap.md` | Cổng 1.3 → Đạt |
| `CHANGELOG.md` | Một mục |

Không đổi DDL, không đổi quyền của `bo19_app`, không đổi `check_grants.py`.

## Open Questions

- Việc xoá dữ liệu cá nhân **có cần** bằng chứng trong `audit_event` hay không là câu hỏi pháp lý, `[CẦN XÁC MINH]` theo văn bản gốc (A-080). Đề xuất này giữ bằng chứng ở mức phiên (`chat_session_idle_close`) và không đòi thêm. Nếu văn bản gốc đòi nhiều hơn, việc đó thuộc A-079 (quyền của chủ thể dữ liệu), không thuộc A-055.
