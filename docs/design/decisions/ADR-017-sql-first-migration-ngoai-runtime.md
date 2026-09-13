# ADR-017 — Truy cập DB kiểu SQL-first; migration là file SQL đánh số, chạy ngoài service runtime

**Trạng thái:** Accepted · **Ngày:** 2026-09-13 · **Quyết định tại:** Phase 6 — Project Structure · **Liên quan:** ADR-004, ADR-011, ADR-012, ADR-013, A-037, A-040, A-045, A-047, A-060, mục Nguyên tắc dữ liệu của `04-data.md`, `contracts/schema.sql` · **Nguồn:** `docs/reference/langgraph-checkpoint-postgres.md`, `docs/reference/render-deploys-docker.md`, kết quả chạy ở mục Xác minh contract của `06-structure.md`

---

## Context

- `contracts/schema.sql` là contract DDL, và nó không chỉ khai bảng. Bất biến của mục Nguyên tắc dữ liệu của `04-data.md` đứng bằng **quyền theo bảng và theo cột** cấp cho role runtime. Tên ràng buộc mang tiền tố để lỗi vi phạm ánh xạ được sang mã lỗi của tool.
- **Đúng hai role, tên đã có:** `bo19_migrator` sở hữu mọi bảng và chạy migration; `bo19_app` là role runtime của `api` và `queue_worker`, không sở hữu bảng nào. Hai tên này có trong phần đầu `schema.sql` và mục Nguyên tắc dữ liệu của `04-data.md`. ADR này **không** thêm role thứ ba.
- Trên cùng một cơ sở dữ liệu có **hai hệ thống tạo bảng**: migration của dự án, và hàm `setup()` của checkpointer LangGraph (A-045).
- Kết quả chạy thật ở Phase 6, trên PostgreSQL 16.2 cùng pgvector 0.6.2 ở máy local:
  - `bo19_migrator` **không** tạo được extension `vector` — `permission denied to create extension "vector"`;
  - `setup()` **không** chạy được trong một khối giao dịch — `CREATE INDEX CONCURRENTLY cannot run inside a transaction block`;
  - `bo19_app` gọi `setup()` thì bị từ chối — `permission denied for schema public`;
  - với quyền cấp theo mục Migration và checkpointer của `06-structure.md`, `bo19_app` ghi được checkpoint và gọi `delete_thread` được.

## Options

- **A — SQL-first:** psycopg 3 cùng pool của nó, SQL viết tay, không ORM; migration là file SQL đánh số, do một trình chạy mỏng của dự án áp.
- **B — ORM** (SQLAlchemy) **cộng migration tự sinh** (Alembic autogenerate) từ model.
- **C — Alembic với migration viết tay**, không ORM.
- **D — Chạy migration lúc ứng dụng khởi động.**

## Decision

**Chọn A.**

### Truy cập DB

- Không ORM. Câu SQL chỉ nằm trong các module được phép ghi — `tool_layer`, cộng ba chủ của danh sách ngoại lệ đóng — và trong module đọc của `api`. Luật import ở mục Luật import của `06-structure.md`.
- **Hai lối vào lớp truy cập DB, phân biệt bằng cơ chế của PostgreSQL chứ không bằng quy ước.** Lối **đọc** mở mọi giao dịch ở chế độ `READ ONLY`: đã chạy thử, một lệnh `UPDATE` mà `bo19_app` **có quyền** vẫn bị từ chối với `ReadOnlySqlTransaction` (mục Xác minh contract của `06-structure.md`). Lối **ghi** chỉ `tool_layer` và ba chủ ngoại lệ được import.
- Pool phơi ra hai ngữ nghĩa: **chờ có hạn** cho request nghiệp vụ, và **thử lấy — không có thì bỏ qua ngay** cho vòng poll của stream tín hiệu (ADR-013). Chỉ có API chờ thì quy tắc "pool cạn thì bỏ lượt" không cài được.

### Trình tự migration — một bước triển khai, chạy bằng `bo19_migrator`

| Bước | Việc | Role | Giao dịch |
|---|---|---|---|
| 0 | `CREATE EXTENSION vector` — một lần cho mỗi cơ sở dữ liệu | Role có quyền tạo extension. Trên Render là role nào: A-040 vế (3) | — |
| 1 | Schema migration: file SQL đánh số, áp theo thứ tự. File đầu tiên là `schema.sql` nguyên văn ở trạng thái đóng Phase 6 | `bo19_migrator` | Mỗi file một giao dịch |
| 2 | `setup()` của checkpointer, phiên bản thư viện ghim trong lockfile | `bo19_migrator` | **Autocommit** — bắt buộc, đã chạy thử |
| 3 | Cấp quyền trên bảng của thư viện: `SELECT, INSERT, UPDATE, DELETE` trên `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`; `SELECT` trên `checkpoint_migrations`. **Chạy lại sau mỗi lần nâng thư viện** — một migration mới của thư viện có thể thêm bảng | `bo19_migrator` | Một giao dịch |
| 4 | Data migration: danh mục permission, vai trò, bản đầu của `request_type` (mục Nguyên tắc dữ liệu của `04-data.md`) | `bo19_migrator` | Mỗi file một giao dịch |

- **Sổ migration.** Trình chạy tự tạo một bảng sổ — tên `schema_migration`: tên file, loại (schema hay data), sha256, thời điểm áp — do `bo19_migrator` sở hữu, `bo19_app` chỉ có `SELECT`. Bảng này nằm ngoài `schema.sql`, cùng loại với bảng của thư viện checkpointer (xem Open Questions của `06-structure.md`). **Một file đã áp mà sha256 khác thì trình chạy dừng.** Migration đã áp là bất biến, sửa là viết file mới.
- **Runtime không bao giờ gọi `setup()`.** Bước kiểm khởi động đọc `max(v)` của `checkpoint_migrations` và so với số mà phiên bản thư viện đã ghim cần — `9` với `langgraph-checkpoint-postgres` 3.1.2, đã chạy thử. Lỡ có đoạn mã gọi `setup()` thì nó hỏng to vì quyền, chứ không lặng lẽ migrate.
- **Migration chỉ mở rộng**, tương thích với phiên bản ứng dụng đang chạy. Bước kiểm khởi động đòi **mọi** migration mà bản build biết đã có trong sổ; sổ có thêm migration mới hơn thì vẫn chạy.

### Migration chạy ở đâu — ngoài hai service runtime

- Credential của `bo19_migrator` là ranh giới tin cậy của mọi bất biến bằng quyền (mục Nguyên tắc dữ liệu của `04-data.md`). Nó **không được** có mặt trong biến môi trường của `api`, `queue_worker` hay cron job. Có mặt ở đó thì tiến trình runtime tự nối được bằng role sở hữu, và mọi phép kiểm phủ định ở mục Xác minh contract chỉ còn là chữ.
- Vì vậy migration là **một bước triển khai tách riêng**, chạy lệnh `migrate` của cùng image, trong một ngữ cảnh chỉ giữ credential `bo19_migrator`, **trước** khi deploy `api` và `queue_worker`. Ngữ cảnh đó là gì: A-060.
- **Pre-deploy command của Render bị loại cho việc này.** Nguồn cho biết nó "executes on a separate instance", nhưng không nói nó dùng biến môi trường riêng hay biến của service — `[CẦN XÁC MINH]`. Nếu dùng chung thì credential migrator nằm trong môi trường của service runtime.
- **Quên chạy migration trước deploy thì deploy hỏng, không phải ứng dụng chạy sai.** Bước kiểm khởi động từ chối khởi động, và theo nguồn của Render, "If any command fails or times out, the entire deploy fails… Your service continues running its most recent successful deploy". Việc một tiến trình thoát với mã khác 0 ngay lúc khởi động có được Render tính là "command fails" hay không `[CẦN XÁC MINH]` bằng một lần deploy thật.

## Consequences

**Tích cực**

- `schema.sql` là nguồn duy nhất của cấu trúc lẫn quyền. Không có bản sao thứ hai của schema dưới dạng model.
- Thứ tự giữa migration của dự án và migration của thư viện được chốt bằng bằng chứng chạy thật, không bằng suy đoán.
- Quyền đọc hay ghi của một module thấy được ngay trong import của nó, và lối đọc bị PostgreSQL chặn ghi.

**Tiêu cực và cái phải chấp nhận**

- Không có migration tự sinh. Mọi thay đổi schema viết tay bằng SQL, kể cả phần `GRANT`.
- Trình chạy migration là mã của dự án, phải tự viết và tự test.
- Một bước triển khai nữa ngoài Render. Quên nó thì deploy hỏng — an toàn, nhưng phiền.

**Điều kiện đảo ngược** — tín hiệu kiến trúc: A-040 trả lời rằng Render không cho tách role sở hữu với role runtime. Khi đó mọi bất biến bằng quyền rơi về tầng ứng dụng, và cả ADR này lẫn mục Nguyên tắc dữ liệu của `04-data.md` phải xét lại.

## Rejected alternatives

**B — ORM cộng migration tự sinh.** Loại vì ba lý do:

1. Model ORM là một bản sao thứ hai của `schema.sql` — 45 bảng, index partial, cột generated, khoá ngoại ghép — phải giữ khớp bằng tay.
2. Migration tự sinh so model với DB, không biết gì về quyền theo cột. Chính lớp bất biến quan trọng nhất của mục Nguyên tắc dữ liệu của `04-data.md` sẽ nằm ngoài tầm của công cụ migration.
3. Mẫu dùng ORM khiến "ai có session thì ghi được" thành tự nhiên — ngược với luật mọi ghi đi qua `tool_layer`.

**C — Alembic với migration viết tay.** Không sai. Loại cho Sprint đầu vì mọi migration vẫn là SQL viết tay, nên công cụ không bớt được việc. Trong khi đó mô hình giao dịch và sổ riêng của nó phải được dung hoà với bước `setup()` không giao dịch của thư viện checkpointer, và với hai loại migration schema và data. Mô hình giao dịch của Alembic `[CẦN XÁC MINH]` — tài liệu chưa có trong `docs/reference/`.

**D — Migration lúc ứng dụng khởi động.** Loại vì tiến trình runtime khi đó phải giữ credential `bo19_migrator` — đúng thứ mục "Migration chạy ở đâu" cấm. Thêm vào đó, nhiều instance khởi động cùng lúc sẽ tranh nhau chạy migration.
