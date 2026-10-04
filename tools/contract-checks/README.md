# `tools/contract-checks/` — bộ kiểm quyền của contract DDL

Đây là **bằng chứng thi hành** duy nhất của mục Nguyên tắc dữ liệu trong `docs/design/04-data.md`: role runtime `bo19_app` bị từ chối đúng những gì thiết kế nói nó không được làm. Kết quả lần chạy đầu ở mục Xác minh contract của `docs/design/06-structure.md`.

## Vì sao ở đây

- **Không phải mã ứng dụng.** Nó không thuộc `backend/` — `Dockerfile` chỉ chép `backend/` và `frontend/`, nên bộ kiểm không bao giờ có mặt trong image runtime.
- **Không phải tài liệu.** `docs/design/contracts/` giữ contract dạng khai báo (`schema.sql`, `openapi.yaml`). Để mã chạy được ở đó sẽ làm mờ ranh giới "contract là khai báo".
- **Thuộc repo**, vì nó phải chạy lại theo đúng phiên bản `schema.sql` cùng commit.

## Khi nào chạy lại

1. **Sau mỗi lần `docs/design/contracts/schema.sql` đổi**, trước khi merge — và `--local-migrated` sau mỗi lần một file trong `backend/migrations/schema/` được thêm hay sửa.
2. **Trên Render**, ngay khi có môi trường đầu tiên — cùng lượt A-040, A-047 (`docs/design/ASSUMPTIONS.md`).
3. **Sau mỗi lần nâng `langgraph-checkpoint-postgres`** — migration mới của thư viện có thể thêm bảng.
4. **Khi đổi nhóm quyền** ở mục Nguyên tắc dữ liệu của `04-data.md`: sửa danh sách nhóm ở đầu `check_grants.py` trong cùng thay đổi.

## Cách chạy

```bash
cd tools/contract-checks
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip

# Local: dựng PostgreSQL + pgvector tạm, áp schema.sql, rồi kiểm. Không cần Docker.
.venv/bin/python check_grants.py --local

# Local, áp đủ backend/migrations/schema/*.sql theo thứ tự thay cho schema.sql, rồi kiểm.
.venv/bin/python check_grants.py --local-migrated

# Như hai lệnh trên, nhưng trên một PostgreSQL có sẵn thay cho pgserver — cùng bản với Render.
# Server phải mới, chỉ dùng cho phép kiểm này, bind 127.0.0.1:
#   docker run -d --name bo19-pg18 -p 127.0.0.1:55432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust pgvector/pgvector:0.8.1-pg18
.venv/bin/python check_grants.py --local-migrated --server-dsn "postgresql://postgres@127.0.0.1:55432/postgres"

# Cơ sở dữ liệu có sẵn, đã migrate (ví dụ Render): chỉ kiểm, không áp gì.
.venv/bin/python check_grants.py --app-dsn env:BO19_RENDER_APP_DSN --migrator-role bo19_migrator
# env:TÊN — đọc DSN từ biến môi trường; đừng đặt DSN thật trên dòng lệnh (lộ qua danh sách tiến trình)
```

**`--local` hay `--local-migrated`.** `--local` kiểm đúng contract `schema.sql`. `--local-migrated` kiểm toàn bộ schema mà runtime sẽ thấy, gồm bảng và quyền của migration sau `schema.sql` — chạy nó mỗi khi thêm hay sửa một file trong `backend/migrations/schema/`. Nó **không** thay `migrate_main`: sổ `schema_migration` được tạo từ file DDL của nó nhưng để trống, không chạy data migration, không kiểm sha256.

Windows: console mặc định không in được tiếng Việt khi chuyển hướng output ra file — đặt `PYTHONIOENCODING=utf-8` trước lệnh.

**Kết quả đạt** là mã thoát `0` và dòng `Lệch: 0`. Mã `1` là có lệch — danh sách in ngay dưới. Mã `2` là lỗi môi trường.

Mọi phép thử dùng `WHERE false` hoặc giao dịch rollback: PostgreSQL kiểm quyền mà không chạm dòng nào. `TRUNCATE` chỉ kiểm bằng `has_table_privilege`, không thực thi. Chế độ `--app-dsn` vì vậy an toàn trên một cơ sở dữ liệu có dữ liệu.

## Nó kiểm gì

- **Độ phủ:** mọi bảng trong `public` thuộc đúng một nhóm quyền; bảng mới chưa được xếp nhóm thì tính là lệch.
- **Bảng của migration sau `schema.sql`** — hiện là `employee_credential` (chỉ `SELECT`) và `rate_limit_window` (`SELECT`, `INSERT`, `UPDATE (attempt_count)`, `DELETE`, không `TRUNCATE`) — bảng của `0002_phase9_security.sql`, nhóm lấy từ mục Migration bổ sung của Phase 9 trong `docs/design/09-security.md`, quyền `UPDATE` thu hẹp theo cột bởi `0005_rate_limit_window_column_grant.sql`. `--local` chỉ áp `schema.sql` nên hai bảng này vắng mặt và được bỏ qua kèm dòng `INFO`; `--local-migrated` và `--app-dsn` chạy trên DB đã migrate đủ nên vắng mặt là lệch.
- **Kiểm phủ định và kiểm khẳng định** cho sáu nhóm quyền, từng cột với nhóm sửa theo cột, cộng bảng của checkpointer.
- **Sổ `schema_migration`:** như một bảng chỉ đọc — `SELECT` cho phép, `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE` từ chối. Hai chế độ local tạo sổ từ file DDL; `--app-dsn` trên DB chưa có sổ là lệch — `migrate_main` chưa chạy.
- **Kiểm thêm:** `bo19_app` không sở hữu bảng nào; giao dịch `READ ONLY` chặn cả lệnh có quyền; số chiều embedding đọc từ catalog.
- **Chỉ ở `--local`:** `bo19_app` ghi và xoá được checkpoint; `bo19_app` gọi `setup()` bị từ chối; `bo19_migrator` có tự tạo được extension `vector` không — dòng thông tin cho A-040 vế (3).

## Kỳ vọng đọc từ đâu — không có bản chép cứng

*Thêm 2026-10-04, sau sự cố file grant rỗng ở S1 (`docs/reference/render-postgres-s1.md`).*

| Kỳ vọng | Đọc từ |
|---|---|
| Nhóm quyền theo bảng — gồm hai nhóm của migration sau `schema.sql` | Bảng nhóm quyền ở mục "Hai role, và bất biến bằng quyền" của `docs/design/04-data.md` |
| Cột của nhóm sửa theo cột | Câu `GRANT UPDATE (...) ON t TO bo19_app` trong file SQL được áp — `04-data.md` giao danh sách cột cho `schema.sql` |
| Bảng của checkpointer, câu `GRANT` của bước 3 | `backend/migrations/library/checkpointer_grants.sql` |
| Số chiều embedding | `vector(N)` của `procedure_chunk_embedding_v1` trong DDL |
| Sổ `schema_migration` và quyền của `bo19_app` trên sổ | `backend/migrations/ledger/schema_migration.sql` — file cấp cho `bo19_app` khác đúng `SELECT` thì dừng mã 2 (PO, 2026-10-04; ADR-017) |

File SQL sẽ áp mà không có câu thực thi được thì bộ kiểm dừng với mã 2 — cùng luật với trình chạy migration (ADR-017).

## Test của bộ kiểm

*Thêm 2026-10-04 theo PO.* Parser bảng nhóm quyền hỏng thành tiếng — mã thoát `2` khi: một nhóm parse ra rỗng; một bảng có `CREATE TABLE` trong file SQL được áp mà không thuộc nhóm nào; một bảng thuộc hơn một nhóm. Cộng: không tìm thấy bảng nhóm quyền, hàng lạ, thiếu hàng. Sổ: file DDL sổ cấp thêm quyền ghi cho `bo19_app`, hay rỗng, thì mã `2`.

```bash
.venv/bin/python -m unittest test_check_grants -v      # Windows: .venv\Scripts\python
```

Không cần PostgreSQL — mọi ca dừng ở bước nạp kỳ vọng.
