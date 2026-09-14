# `tools/contract-checks/` — bộ kiểm quyền của contract DDL

Đây là **bằng chứng thi hành** duy nhất của mục Nguyên tắc dữ liệu trong `docs/design/04-data.md`: role runtime `bo19_app` bị từ chối đúng những gì thiết kế nói nó không được làm. Kết quả lần chạy đầu ở mục Xác minh contract của `docs/design/06-structure.md`.

## Vì sao ở đây

- **Không phải mã ứng dụng.** Nó không thuộc `backend/` — `Dockerfile` chỉ chép `backend/` và `frontend/`, nên bộ kiểm không bao giờ có mặt trong image runtime.
- **Không phải tài liệu.** `docs/design/contracts/` giữ contract dạng khai báo (`schema.sql`, `openapi.yaml`). Để mã chạy được ở đó sẽ làm mờ ranh giới "contract là khai báo".
- **Thuộc repo**, vì nó phải chạy lại theo đúng phiên bản `schema.sql` cùng commit.

## Khi nào chạy lại

1. **Sau mỗi lần `docs/design/contracts/schema.sql` đổi**, trước khi merge.
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

# Cơ sở dữ liệu có sẵn, đã migrate (ví dụ Render): chỉ kiểm, không áp gì.
.venv/bin/python check_grants.py --app-dsn "<dsn của bo19_app>" --migrator-role bo19_migrator
```

**Kết quả đạt** là mã thoát `0` và dòng `Lệch: 0`. Mã `1` là có lệch — danh sách in ngay dưới. Mã `2` là lỗi môi trường.

Mọi phép thử dùng `WHERE false` hoặc giao dịch rollback: PostgreSQL kiểm quyền mà không chạm dòng nào. `TRUNCATE` chỉ kiểm bằng `has_table_privilege`, không thực thi. Chế độ `--app-dsn` vì vậy an toàn trên một cơ sở dữ liệu có dữ liệu.

## Nó kiểm gì

- **Độ phủ:** mọi bảng trong `public` thuộc đúng một nhóm quyền; bảng mới chưa được xếp nhóm thì tính là lệch.
- **Kiểm phủ định và kiểm khẳng định** cho sáu nhóm quyền, từng cột với nhóm sửa theo cột, cộng bảng của checkpointer.
- **Kiểm thêm:** `bo19_app` không sở hữu bảng nào; giao dịch `READ ONLY` chặn cả lệnh có quyền; số chiều embedding đọc từ catalog.
- **Chỉ ở `--local`:** `bo19_app` ghi và xoá được checkpoint; `bo19_app` gọi `setup()` bị từ chối; `bo19_migrator` có tự tạo được extension `vector` không — dòng thông tin cho A-040 vế (3).
