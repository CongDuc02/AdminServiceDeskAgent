# Đề xuất — migration mới `backend/migrations/schema/0005_rate_limit_window_column_grant.sql`

**Trạng thái:** ✅ Đã áp — 2026-09-25, PO duyệt · Xem `backend/migrations/schema/0005_rate_limit_window_column_grant.sql`, `tools/contract-checks/check_grants.py` (nhóm `MIGRATION_COLUMN_UPDATE`), ghi chú ở mục Migration bổ sung của Phase 9 trong `09-security.md`, và mục ngày 2026-09-25 (đợt sửa A-068, A-073, A-075) của `CHANGELOG.md`. Chạy lại sau khi áp: `--local-migrated` 176 / 68 / **Lệch 0**; `--local` 169 / 63 / **Lệch 0** · **Nguồn:** vòng duyệt Phase 12 (2026-09-25), phát hiện số 2 ở Open Questions của `12-roadmap.md` · **PO đã chốt chuẩn:** quyền theo cột ở `04-data.md` là đúng; `0002_phase9_security.sql` cấp rộng hơn thiết kế.

**Không sửa `contracts/schema.sql`**, và **không sửa `0002_phase9_security.sql`** — mỗi thay đổi một file (mục Cây backend của `06-structure.md`), cùng tiền lệ `migration-0004-trace-id-format.md`.

---

## Lệch đang có

| Nguồn | `bo19_app` được `UPDATE` gì trên `rate_limit_window` |
|---|---|
| `04-data.md`, mục Hai role, và bất biến bằng quyền — nhóm "Đếm và dọn theo cửa sổ" | `INSERT`, **`UPDATE (attempt_count)`**, `DELETE` — **theo cột** |
| `backend/migrations/schema/0002_phase9_security.sql`, dòng `GRANT` cuối | `GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limit_window TO bo19_app` — `UPDATE` **cả bảng** |
| `09-security.md`, mục Migration bổ sung của Phase 9 — khối SQL tóm tắt | Chép đúng dòng `GRANT` của `0002`, tức cũng cả bảng |
| `tools/contract-checks/check_grants.py` (vòng duyệt Phase 12) | Theo `09-security.md` như chỉ thị lúc đó — `UPDATE` cả bảng |

**Hệ quả của `UPDATE` cả bảng:** `bo19_app` sửa được `scope` và `window_start` của một cửa sổ đang đếm — tức dời một bộ đếm sang IP khác hay sang cửa sổ khác mà không để lại dấu vết. Thao tác duy nhất cần ghi đè tại chỗ là tăng `attempt_count` (mục Rate limit của `09-security.md`); hai cột kia là khoá chính, không có lý do nghiệp vụ nào để sửa. Đây đúng loại quyền thừa mà nguyên tắc "`bo19_app` chỉ có đúng các quyền được cấp" (mục Nguyên tắc dữ liệu của `04-data.md`) cấm.

## 1. Migration mới (hiện vật chính)

`backend/migrations/schema/0005_rate_limit_window_column_grant.sql`:

```sql
-- =============================================================================
-- BO-19 Admin Service Desk Agent — schema migration 0005
-- Vòng duyệt Phase 12. Diễn giải: docs/design/proposals/
-- migration-0005-rate-limit-window-column-grant.md
-- =============================================================================
--
-- Áp SAU 0004_observability_trace_id.sql, bằng bo19_migrator, trong một giao
-- dịch riêng (mục Trình tự migration của ADR-017). KHÔNG sửa 0002 — mỗi thay
-- đổi một file (mục 3 của 06-structure.md).
--
-- Thu hẹp quyền UPDATE của bo19_app trên rate_limit_window từ cả bảng xuống
-- đúng cột attempt_count, khớp nhóm "Đếm và dọn theo cửa sổ" ở mục Nguyên tắc
-- dữ liệu của 04-data.md. scope và window_start là khoá chính: không thao tác
-- nào cần sửa chúng tại chỗ.
-- =============================================================================

REVOKE UPDATE ON rate_limit_window FROM bo19_app;
GRANT UPDATE (attempt_count) ON rate_limit_window TO bo19_app;
```

Không đổi `SELECT`, `INSERT`, `DELETE`; không cấp `TRUNCATE`.

## 2. `tools/contract-checks/check_grants.py` — áp **cùng một commit** với migration

Thay nhóm `MIGRATION_WINDOW_COUNTER` bằng nhóm quyền theo cột:

```diff
-MIGRATION_WINDOW_COUNTER = ["rate_limit_window"]    # SELECT, INSERT, UPDATE, DELETE; không TRUNCATE
+MIGRATION_COLUMN_UPDATE = {"rate_limit_window": ["attempt_count"]}   # + SELECT, INSERT, DELETE; không TRUNCATE (0005)
```

```diff
-        migration_groups = MIGRATION_READ_ONLY + MIGRATION_WINDOW_COUNTER
+        migration_groups = MIGRATION_READ_ONLY + list(MIGRATION_COLUMN_UPDATE)
```

```diff
-        for t in (x for x in MIGRATION_WINDOW_COUNTER if x in tables):
-            rep.expect(f"{t} SELECT", probe(a, f"select 1 from {t} limit 0"), "ALLOW")
-            rep.expect(f"{t} INSERT", probe(a, f"insert into {t} default values"), "ALLOW")
-            rep.expect(f"{t} UPDATE", probe(a, upd(t)), "ALLOW")
-            rep.expect(f"{t} DELETE", probe(a, f"delete from {t} where false"), "ALLOW")
-            rep.expect(f"{t} TRUNCATE", trunc(t), "DENY")
+        for t, allowed in MIGRATION_COLUMN_UPDATE.items():
+            if t not in tables:
+                continue
+            rep.expect(f"{t} SELECT", probe(a, f"select 1 from {t} limit 0"), "ALLOW")
+            rep.expect(f"{t} INSERT", probe(a, f"insert into {t} default values"), "ALLOW")
+            for col in allowed:
+                rep.expect(f"{t} UPDATE({col})", probe(a, upd(t, col)), "ALLOW")
+            for col in (c for c in columns(t) if c not in allowed):
+                rep.expect(f"{t} UPDATE({col})", probe(a, upd(t, col)), "DENY")
+            rep.expect(f"{t} DELETE", probe(a, f"delete from {t} where false"), "ALLOW")
+            rep.expect(f"{t} TRUNCATE", trunc(t), "DENY")
```

**Vì sao phải cùng commit:** checker mới chạy trên DB chưa có `0005` sẽ báo lệch đúng hai dòng — `UPDATE(scope)`, `UPDATE(window_start)` — và ngược lại, `0005` chạy dưới checker cũ cũng báo lệch ở dòng `UPDATE` cả bảng. Tách hai thay đổi thì CI đỏ ở giữa.

## 3. Sửa văn bản kèm theo

| File | Sửa |
|---|---|
| `09-security.md`, mục Migration bổ sung của Phase 9 | Dưới khối SQL tóm tắt `0002`, thêm một câu: quyền `UPDATE` trên `rate_limit_window` được thu hẹp về `UPDATE (attempt_count)` bởi `0005`, trỏ đề xuất này. Không sửa khối SQL — nó chép đúng `0002`, và `0002` không đổi |
| `tools/contract-checks/README.md`, mục Nó kiểm gì | `rate_limit_window` đổi thành "`SELECT`, `INSERT`, `UPDATE (attempt_count)`, `DELETE`, không `TRUNCATE`" |
| `04-data.md` | **Không đổi** — đây là nguồn chuẩn |
| `CHANGELOG.md` | Migration mới, quyết định PO, số đo ở mục Bằng chứng |

## Bằng chứng — đã chạy trước, trên PostgreSQL 16.2 local, ngày 2026-09-25

Chạy trên DB dựng như `check_grants.py --local-migrated` (`0001`→`0004`), thêm SQL của mục 1 bằng `bo19_migrator`, rồi thao tác bằng `bo19_app` trong giao dịch rollback. Script chạy inline, không để lại file.

| Phép thử bằng `bo19_app`, sau `0005` | Kết quả |
|---|---|
| UPSERT của mục Rate limit của `09-security.md` — `INSERT … ON CONFLICT (scope, window_start) DO UPDATE SET attempt_count = rate_limit_window.attempt_count + 1` — chạy hai lần để lần hai đi nhánh `ON CONFLICT` | **Được**; `attempt_count` = 2 |
| `DELETE` cửa sổ hết hạn theo `window_start` | **Được** |
| `UPDATE attempt_count` | **Được** |
| `UPDATE scope` | **Từ chối** — `permission denied for table rate_limit_window` |
| `UPDATE window_start` | **Từ chối** — cùng lỗi |
| `has_table_privilege(…, 'TRUNCATE')` | `false` |

| Chạy `--local-migrated` với checker đã sửa theo mục 2 | Từ chối đúng | Cho phép đúng | Lệch |
|---|---|---|---|
| Có `0005` | 176 | 68 | **0** |
| Không có `0005` | 174 | 68 | **2** — `UPDATE(scope)`, `UPDATE(window_start)`: muốn `DENY`, được `ALLOW` |

So với checker hiện hành (174 / 68 / 0): +2 từ chối đúng, là hai cột khoá chính.

**Chưa kiểm:** trên PostgreSQL managed của Render — cùng lượt A-040, A-047 (bước S1 của Spike 1).

## Không đổi

- `contracts/schema.sql`, `0002_phase9_security.sql` — không một ký tự.
- Không có dữ liệu nào bị ảnh hưởng: `REVOKE`/`GRANT` chỉ đổi quyền.
