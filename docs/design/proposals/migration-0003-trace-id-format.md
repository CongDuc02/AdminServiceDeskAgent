# Đề xuất — migration mới `backend/migrations/schema/0003_observability_trace_id.sql`

**Trạng thái:** Chờ duyệt · **Nguồn:** ADR-024 (định dạng `trace_id`), mục Log schema của `11-ops.md` (6.1) · **Không sửa `contracts/schema.sql`** — file đó đã đóng ở Phase 6 (sha256 xác nhận nguyên vẹn qua `tools/contract-checks`, chạy 2026-09-15), và mục 3 của `06-structure.md` đã chốt quy ước: *"`0001_initial.sql` = `contracts/schema.sql` ở trạng thái đóng Phase 6; về sau mỗi thay đổi một file"* — đúng tiền lệ Phase 9 (`0002_phase9_security.sql`).

---

## Sửa tên file trước — hiện vật đúng phải là migration, không phải "diff `04-data.md`"

Bản trước của đề xuất này tên `diff-04-data-trace-id-format.md`, ngụ ý sửa `04-data.md`/`contracts/schema.sql` trực tiếp — sai hiện vật. `CHECK` sống ở DDL runtime, không sống ở tài liệu, và `contracts/schema.sql` là artifact **đóng**, không sửa. Đề xuất đúng gồm **hai hiện vật riêng**:

## 1. Migration mới (hiện vật chính)

`backend/migrations/schema/0003_observability_trace_id.sql`:

```sql
-- Migration 0003 — Phase 11 (Observability): định dạng trace_id (ADR-024)
-- Chạy bằng bo19_migrator, đúng trình tự ADR-017 (bước 1: schema migration).

ALTER TABLE llm_usage
    ADD CONSTRAINT ck_llm_usage_trace_id
    CHECK (trace_id IS NULL OR trace_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$');
```

Không đổi tính `NULL` được của cột (giữ nguyên như `contracts/schema.sql` đã định nghĩa). Không cấp thêm quyền nào — `bo19_app` đã có đúng quyền cần trên `llm_usage` (nhóm "Chỉ thêm", mục Nguyên tắc dữ liệu của `04-data.md`); thêm `CHECK` không đổi nhóm quyền.

**Dữ liệu đã có (nếu có) trước migration này:** hiện chưa có dữ liệu thật (chưa lên `PRODUCTION`), nên không có ca `trace_id` cũ vi phạm `CHECK` mới. Nếu áp sau khi đã có dữ liệu, `ALTER TABLE ... ADD CONSTRAINT` sẽ validate toàn bộ dòng hiện có — dòng nào không khớp định dạng làm migration **thất bại**, không âm thầm bỏ qua.

## 2. Cập nhật prose ở `04-data.md` (hiện vật phụ, chỉ sửa mô tả — không sửa DDL)

Dòng mô tả `llm_usage` ở mục Bảng chi tiết của `04-data.md` hiện không nói gì về định dạng `trace_id`. Thêm một câu, trỏ tới ADR-024 và migration 0003, xoá mọi ngụ ý "chưa chốt" nếu có.

## Việc phải làm khi áp

- `tools/contract-checks/check_grants.py` chạy lại sau khi thêm migration này (đúng mục Khi nào chạy lại của `README.md`) — thêm `CONSTRAINT` không đổi nhóm quyền nên không cần sửa danh sách nhóm trong script, nhưng vẫn phải chạy để xác nhận không lệch.
- `CHANGELOG.md` ghi rõ: migration mới, không phải sửa `contracts/schema.sql`; quyết định của PO khi duyệt đề xuất này.
- `schema_migration` (sổ migration, mục Tầng kỹ thuật của `04-data.md`) tự động có một dòng mới sau khi trình chạy migration áp file `0003_observability_trace_id.sql` — không cần thao tác thủ công nào khác.

## Không đổi

- `contracts/schema.sql` — không một ký tự.
- Không áp `CHECK` tương tự cho `audit_event.trace_id` — ngoài phạm vi câu bỏ ngỏ của ADR-019 (chỉ nói về `llm_usage`). Mở rộng sang `audit_event` là một đề xuất khác, chưa xét.
- Không đổi kiểu cột `trace_id` (`text`), không ép `NOT NULL`.
