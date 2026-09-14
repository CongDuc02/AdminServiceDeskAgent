# ADR-020 — `operating_mode_change` qua endpoint có permission, không qua thao tác vận hành

**Trạng thái:** Accepted · **Ngày:** 2026-09-14 · **Quyết định tại:** Phase 9 — Security & Guardrails · **Liên quan:** D-009, ADR-010, ADR-013, A-048, mục Nhãn phạm vi và loại trừ có chủ đích của `05-api.md`, mục Hai role và bất biến bằng quyền của `04-data.md`

---

## Context

D-009 (mục Chế độ phi sản xuất của `00-domain.md`) đòi việc chuyển `operating_mode` từ `NON_PRODUCTION` sang `PRODUCTION` là "một hành động được ghi nhận và quy trách nhiệm được — không phải sửa biến môi trường rồi deploy lại. Cơ chế cụ thể thuộc Phase 9 và Phase 11."

Phase 4 đã tạo bảng `operating_mode_change` (`id`, `from_mode`, `to_mode`, `decided_by_employee_id`, `decision_reference` không rỗng — CHECK ở DB, `effective_at` — `UNIQUE`) và cấp `bo19_app` quyền `INSERT` trên nó, nhóm "Chỉ thêm" cùng `audit_event`, `decision_record` (mục Hai role và bất biến bằng quyền của `04-data.md`). Phase 5 cố ý **không** mở đường ghi: `05-api.md` liệt `operating_mode_change` vào ba loại trừ có chủ đích, chỉ mở `GET /me` đọc chế độ hiện hành, và giao "Phase 9" xử lý phần còn lại.

Câu hỏi đứng trước việc cấp permission `operating_mode.change` cho ai: cơ chế ghi là một **endpoint** (đi qua `api`, có permission, sinh `audit_event` qua `tool_layer`) hay một **thao tác vận hành** (chạy bằng `bo19_migrator`, ngoài ứng dụng — cùng khuôn với seed/đổi mật khẩu của `employee_credential`, H1)?

## Options

- **A — Endpoint có permission.** `POST /operating-mode/transitions`, permission `operating_mode.change`, ghi qua `tool_layer` trong một giao dịch cùng `audit_event`.
- **B — Thao tác vận hành.** Người giữ credential `bo19_migrator` chạy một câu lệnh ghi trực tiếp, kèm tài liệu quyết định có người ký, giống cách `employee_credential` được seed/đổi (H1).

## Decision

**Chọn A.**

1. **Quyền đã cấp đi ngược hướng B.** `bo19_app` đã có `INSERT` trên `operating_mode_change` từ Phase 4. `employee_credential` — nơi B thật sự đứng được — được thiết kế ngược lại: `bo19_app` cố tình **chỉ đọc**, để ứng dụng không có lệnh ghi credential nào. Chọn B ở đây nghĩa là phải thu hồi quyền `INSERT` đã cấp bằng một migration khác (đảo một quyết định Phase 4 không ai yêu cầu đảo), hoặc để nguyên một quyền ghi mà không dòng code nào dùng tới — cả hai đều phạm nguyên tắc "`bo19_app` chỉ có đúng các quyền được cấp" (mục Hai role và bất biến bằng quyền của `04-data.md`).
2. **Thao tác vận hành không đi qua `tool_layer`, nên không sinh `audit_event`.** Đây là hành động hệ trọng nhất của hệ thống — nó bật/tắt toàn bộ ba ràng buộc của chế độ phi sản xuất (mục 6.2 của `00-domain.md`: watermark, dải số, cấm đóng dấu thật). Ghi nó ngoài `tool_layer` để nó nằm ngoài đúng nhật ký mà `audit.read_all` đọc là làm yếu chữ của D-009 ("được ghi nhận và quy trách nhiệm được"), không phải một cách khác để đạt cùng mục tiêu.

**Điều kiện đi kèm quyết định:**

- Idempotency-Key = id của dòng `operating_mode_change` được tạo — theo quy tắc chuẩn, không thêm ngoại lệ mới vào danh sách ba ngoại lệ đã đóng của mục Idempotency ở `05-api.md`.
- `audit_event` mức `WARNING` — hành động đúng luật nhưng cần người khác nhìn thấy, cùng họ với đường thoát tự duyệt của D-006.
- Một permission `operating_mode.change`, gác cả hai chiều `NON_PRODUCTION ↔ PRODUCTION`. Không gác chiều lùi chặt hơn: chặn đường lùi về chế độ an toàn hơn nguy hiểm hơn chặn đường tiến.
- `api` không thêm phép kiểm hình thức nào cho `decision_reference` ngoài CHECK không rỗng đã có ở DB — một tham chiếu văn bản có người ký là thứ hệ thống không thẩm định được (cùng nguyên tắc đã dùng ở A-033, A-018).
- `request_type.manage`, `procedure.read_all`, `operating_mode.change` cấp lẻ — không thuộc gói vai trò nào (mục AuthZ của `09-security.md`).

## Consequences

**Tích cực**

- Hành động hệ trọng nhất của hệ thống được ghi vào đúng nhật ký nghiệp vụ, xem được qua `audit.read_all` và qua `GET /operating-mode/transitions`.
- Không đảo quyền đã cấp ở Phase 4; không để lại quyền ghi không dùng.
- Cùng khuôn thao tác cổng đã có (permission → `tool_layer` → chuyển trạng thái + `audit_event` trong một giao dịch, ADR-010) — không thêm một mẫu hình mới.

**Tiêu cực và cái phải chấp nhận**

- Endpoint có permission là một bề mặt tồn tại trong sản phẩm, dù mặc định không ai được cấp `operating_mode.change`. Rủi ro thật nằm ở việc cấp permission này cho đúng người, không nằm ở việc endpoint tồn tại.
- Phạm vi contract đã đóng ở Phase 5 thay đổi: 48 → 49 endpoint có contract (mục Nhãn phạm vi và loại trừ có chủ đích của `05-api.md`). `openapi.yaml` phải cập nhật cùng lượt.
- Bộ kiểm đối chiếu tự động (`tools/contract-checks/`, A-047) cần chạy lại sau thay đổi này — thuộc trách nhiệm người triển khai, ngoài phạm vi DESIGN MODE.

## Rejected alternatives

**B — Thao tác vận hành, cùng khuôn `employee_credential`.** Có vẻ nhất quán ở lần nhìn đầu (một hành động hiếm, rủi ro cao, xử lý ngoài ứng dụng), nhưng khác `employee_credential` ở đúng chỗ quan trọng: bảng credential được thiết kế **từ đầu** cho `bo19_app` chỉ đọc; bảng `operating_mode_change` được thiết kế **từ đầu** cho `bo19_app` ghi được. Áp cùng một khuôn xử lý cho hai thiết kế ngược hướng là bỏ qua tín hiệu mà Phase 4 đã để lại. Mất `audit_event` tự động là cái giá không bù được bằng việc tránh mở một endpoint mới.
