# Đề xuất diff — `06-structure.md`, mục Bước kiểm khởi động

**Trạng thái:** ✅ Đã áp — 2026-09-16, PO duyệt · **Nguồn:** ADR-023 (Phase 11) · Xem `06-structure.md` mục Bước kiểm khởi động (v0.4) và mục ngày 2026-09-16 của `CHANGELOG.md`

---

## Vì sao cần

ADR-023 (mục Môi trường Render của `11-ops.md`) chốt ba lớp khoá `operating_mode` theo môi trường Render. Lớp 2 là hai bước kiểm khởi động mới, thêm vào bảng 15 bước hiện có (mục Bước kiểm khởi động của `06-structure.md`). **Không đổi bước #15** (giữ nguyên mức "Ghi log").

## Diff đề xuất

Thêm hai dòng vào cuối bảng (sau dòng #15), đúng định dạng bảng hiện có (`# | Kiểm gì | api | worker | cron | Mức | Cơ sở`):

| # | Kiểm gì | `api` | `worker` | cron | Mức | Cơ sở |
|---|---|---|---|---|---|---|
| 16 | Biến môi trường `BO19_ENVIRONMENT` có mặt, giá trị ∈ `{dev, staging, prod}` | ✔ | ✔ | ✔ | **Chặn** — thiếu biến này không được mặc định thành `prod` (fail-closed) | ADR-023 |
| 17 | Nếu `BO19_ENVIRONMENT ≠ prod`: `operating_mode` hiện hành (đọc cùng nguồn với bước #15) phải là `NON_PRODUCTION` | ✔ | ✔ | — | **Chặn** khi lệch | ADR-023 |

**Ghi chú đặt vào cuối mục, sau bảng:** *"Bước #16–17 (ADR-023, Phase 11) là lớp thứ hai trong ba lớp khoá `operating_mode` theo môi trường — không thay thế bước #15 (D-009, chỉ ghi log), và không thay thế chính sách cấp quyền hay chặn tại endpoint (`POST /operating-mode/transitions`, xem mục Endpoint của `05-api.md` sau khi diff riêng cho file đó được duyệt)."*

## Không đổi

- Bước #15 — giữ nguyên mức "Ghi log".
- Không có bước nào trong 15 bước hiện tại bị xoá hay đổi mức.
- `cron` không cần bước #17 vì không có entrypoint `cron_main` nào gọi `POST /operating-mode/transitions`.

## Việc phải làm khi áp (ngoài phạm vi đề xuất này)

- Thêm `BO19_ENVIRONMENT` vào bảng biến môi trường theo môi trường (mục 1.3 của `11-ops.md`) — đã có.
- `docs/design/CHANGELOG.md` ghi rõ: sửa theo quyết định của PO (ADR-023), không viện dẫn rule 5 của `CLAUDE.md` (rule đó nói về đổi tên cho nhất quán, không phải thẩm quyền thêm nội dung mới).
