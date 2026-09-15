# ADR-023 — Ba lớp khoá `operating_mode` theo môi trường Render

**Trạng thái:** Accepted · **Ngày:** 2026-09-15 · **Quyết định tại:** Phase 11 — Ops, Cost & Deployment · **Liên quan:** D-009, ADR-020, A-018, mục Môi trường Render của `11-ops.md`, mục Enum khác của `GLOSSARY.md` (định nghĩa `WARNING`)

---

## Context

`00-domain.md` (D-009) và ADR-020 đã chốt: `operating_mode` (`NON_PRODUCTION`/`PRODUCTION`) là một trục hoàn toàn độc lập với môi trường triển khai (`dev`/`staging`/`prod`, mục Môi trường Render của `11-ops.md`). Chừng nào A-018 còn ở trạng thái "không có ai nghiệm thu thể thức" (mở vĩnh viễn theo thiết kế), không môi trường nào ngoài `prod` thật sự cần `PRODUCTION`. Câu hỏi của phase này: ràng buộc "`dev`/`staging` chỉ chạy `NON_PRODUCTION`" nên đứng bằng gì.

Phép thử áp dụng (tiền lệ J3, `CHANGELOG.md` mục 2026-09-13 lần 3): **"có điều kiện đảo ngược không"**, không phải "có phải mẫu hình kiến trúc mới không". Ràng buộc này có điều kiện đảo ngược nêu được (tổ chức cần một môi trường tiền-sản-xuất chạy `PRODUCTION` thật, ví dụ UAT với dấu thật) — cùng dạng với điều kiện đảo ngược của `argon2id` (ADR-021). Cần ADR.

## Options

- **A — Một lớp: chỉ chính sách cấp quyền.** Không cấp `operating_mode.change` cho ai ở `dev`/`staging`.
- **B — Hai lớp: chính sách + bước kiểm khởi động.** Thêm một bước kiểm khởi động so khớp `BO19_ENVIRONMENT` (biến môi trường mới) với `operating_mode` hiện hành trong DB; lệch thì **Chặn**, không khởi động.
- **C — Hai lớp: chính sách + chặn tại endpoint.** `POST /operating-mode/transitions` từ chối chuyển sang `PRODUCTION` khi `BO19_ENVIRONMENT ≠ prod`.
- **D — Ba lớp: chính sách + bước kiểm khởi động + chặn tại endpoint.**

## Decision

**Chọn D.** Ba lớp bắt ba thất bại khác nhau, không lớp nào thừa:

| Lớp | Cơ chế | Bắt được gì | Không bắt được gì |
|---|---|---|---|
| 1 | Chính sách cấp quyền | Đường đi thông thường: không ai *được phép* gọi endpoint | Cấp nhầm; dữ liệu `operating_mode_change` tới bằng đường khác (migration, restore) |
| 2 | Bước kiểm khởi động — so khớp `BO19_ENVIRONMENT` với `operating_mode` hiện hành, lệch thì **Chặn** | Trạng thái đã nằm trong DB, bất kể đến bằng đường nào, kể cả khi Lớp 1 thất bại | Chỉ kiểm lúc khởi động; một tiến trình đang chạy bị đổi `operating_mode` giữa chừng (qua endpoint) không bị chặn tới lần khởi động sau |
| 3 | Chặn tại endpoint — `POST /operating-mode/transitions` từ chối khi `BO19_ENVIRONMENT ≠ prod` | Mọi lần gọi endpoint, tại thời điểm gọi, không chờ khởi động lại — đúng lỗ của Lớp 2 | Dữ liệu đưa vào **ngoài** endpoint (ví dụ restore chèn thẳng một dòng `operating_mode_change`) — vẫn là việc của Lớp 2 |

Lấy A làm nền — không loại, vì nó vẫn là lớp rẻ nhất và không loại trừ hai lớp kia.

**Cấu hình mới:** biến môi trường `BO19_ENVIRONMENT` (`dev`/`staging`/`prod`), đọc ở cả hai lớp 2 và 3. **Fail-closed khi thiếu:** coi như môi trường hạn chế nhất, không mặc định `prod` — Lớp 2 thêm một bước kiểm khởi động **riêng** (không gộp vào bước kiểm việc lệch môi trường) cho ca thiếu biến này, mức **Chặn**.

**Không nâng mức bước kiểm khởi động #15** (mục Bước kiểm khởi động của `06-structure.md`: hiện tại mức "Ghi log — chưa có dòng nào là `NON_PRODUCTION`", D-009) — đó là bước ghi log trạng thái hiện hành, không phải bước so khớp với môi trường. Lớp 2 là hai bước **mới** (#16, #17 — đề xuất diff riêng, `docs/design/proposals/diff-06-structure-startup-checks.md`), không sửa #15.

### `audit_event` cho lần bị Lớp 3 từ chối

**Ghi `audit_event` mức `WARNING`.** Người gọi có `operating_mode.change` hợp lệ (qua được AuthZ), chỉ bị chặn bởi luật môi trường — đây đúng tình huống D-006 (tự duyệt) đã xử lý: hành động hợp lệ về quyền nhưng cần người khác nhìn thấy, khác hẳn tiền lệ `ai_gateway` (`BUDGET_EXCEEDED`/`ALLOWLIST_REJECTED` không sinh `audit_event`, vì đó là ma sát kỹ thuật thường gặp, không phải hành vi cần giám sát).

**Định nghĩa `WARNING` phải mở rộng tường minh** (mục Enum khác của `GLOSSARY.md`), thành danh sách đóng — không dùng tiêu chí tự quy chiếu kiểu "hành động cần được nhìn thấy" (phase sau sẽ dùng nó để kéo bất cứ thứ gì vào):

> `WARNING` (hành động đúng luật nhưng cần người khác nhìn thấy — áp cho tự duyệt theo đường thoát ở mục Tách biệt trách nhiệm của `00-domain.md` (D-006), và cho lần thử chuyển `operating_mode` bị chặn bởi luật môi trường (ADR-023). Thêm ca mới vào danh sách này là một quyết định có ADR, không phải một phép suy.)

**Tên thao tác: `operating_mode_transition_reject`** — **không** dùng lại `operating_mode_transition` (Phase 9): thao tác đó có hợp đồng "ghi một dòng `operating_mode_change`"; ở đây không dòng nào được ghi (transition bị chặn), dùng chung tên làm Phase 13 không truy vết được theo đúng luật "mỗi lệnh ghi do endpoint gây ra phải có tên" (`05-api.md`). `operating_mode_transition_reject` chỉ ghi `audit_event` mức `WARNING`, action `operating_mode.transition_reject` — không ghi `operating_mode_change`, không đổi `operating_mode` hiện hành. **`audit_event.action` không cần danh mục đóng để thêm giá trị này:** DDL (`ck_audit_event_action`) chỉ kiểm hình dạng `entity.action` bằng regex, không có bảng mã đóng nào được tuyên bố ở bất kỳ phase nào — khác `notification.event_code`/`document_halt.reason_code`, hai cột có tuyên bố rõ "bảng mã thuộc Phase 8". Tên thao tác `operating_mode_transition_reject` vẫn cần thêm vào mục Agent, graph, node, tool của `GLOSSARY.md` (nhóm "Thao tác do endpoint gọi") — lý do khác: nó là một thao tác có tên, không phải vì giá trị `action`.

**Mã lỗi HTTP cho Lớp 3** — chưa có trong `05-api.md`, đề xuất riêng (`docs/design/proposals/diff-05-api-job-failed-and-reject-error.md`), chờ duyệt cùng lượt với contract `job_failed`.

## Consequences

**Tích cực**

- Ba lớp độc lập, mỗi lớp bắt đúng một khoảng trống của các lớp còn lại — không có "lớp trang trí".
- Không đảo ngược quyết định đã chốt của ADR-020 (endpoint có permission) — chỉ thêm điều kiện chặn, không đổi cơ chế ghi thành công.
- `WARNING` được định nghĩa lại thành danh sách đóng, ngăn phase sau suy rộng tuỳ tiện.

**Tiêu cực và cái phải chấp nhận**

- Thêm một biến môi trường bắt buộc (`BO19_ENVIRONMENT`) ở cả ba môi trường — sai giá trị này (ví dụ đặt nhầm `dev` build cho `prod`) tự nó là một lớp rủi ro vận hành mới, giảm nhẹ bằng fail-closed.
- Residual risk còn lại, nói thẳng: một lần restore dữ liệu (không qua endpoint) chèn thẳng một dòng `operating_mode_change` mang `PRODUCTION` vào DB của `staging`, xảy ra **giữa** hai lần khởi động — Lớp 2 chỉ bắt ở lần khởi động kế tiếp, không tức thời; Lớp 3 không áp vì không đi qua endpoint. Chấp nhận, vì tần suất restore thấp hơn nhiều tần suất khởi động.
- Ba đề xuất diff (hai file `06-structure.md`/`05-api.md`+`openapi.yaml`, chưa kể `04-data.md` của mục Backup & Restore) cần duyệt riêng trước khi áp — ADR này tự nó không hoàn tất tới khi các diff đó được chấp nhận.

## Rejected alternatives

**A — chỉ chính sách cấp quyền.** Không có gì buộc chính sách này đứng vững ngoài kỷ luật vận hành — không có `CHECK` nào trong DB hay code chặn một người vận hành cấp nhầm permission ở `staging`.

**B — chính sách + bước kiểm khởi động, không chặn endpoint.** Đóng được lỗ dữ liệu-tới-bằng-đường-khác, nhưng để lỗ một tiến trình đang chạy bị đổi `operating_mode` giữa chừng qua chính endpoint hợp lệ — đúng lỗ Lớp 3 được thêm để đóng.

**C — chính sách + chặn endpoint, không có bước kiểm khởi động.** Đóng được lỗ runtime, nhưng để lỗ dữ liệu tới bằng đường ngoài endpoint (migration, restore) không bao giờ bị phát hiện cho tới khi ai đó thử gọi endpoint lần nữa — có thể không bao giờ xảy ra, để trạng thái sai âm thầm tồn tại.
