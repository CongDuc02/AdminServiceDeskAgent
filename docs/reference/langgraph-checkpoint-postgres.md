# LangGraph — checkpointer PostgreSQL: bảng, cách tạo, kết nối, lưu lỗi

- **Nguồn:**
  - `https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/checkpoint-postgres/langgraph/checkpoint/postgres/base.py`
  - `https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/checkpoint-postgres/langgraph/checkpoint/postgres/__init__.py`
  - `https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/checkpoint-postgres/README.md`
  - `https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/checkpoint-postgres/pyproject.toml`
  - `https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/checkpoint/langgraph/checkpoint/base/__init__.py`
  - `https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/langgraph/langgraph/pregel/_runner.py`
- **Ngày lấy:** 2026-09-13, bằng `curl` trên nhánh `main`.
- **Phiên bản mà nguồn mô tả:** `langgraph-checkpoint-postgres` **3.1.2** (theo `pyproject.toml`); commit gần nhất chạm `libs/checkpoint-postgres` là `2efb0073a52599ff9c82b7ff6e80c55273b9fbdf` (2026-09-02). `langgraph` **1.2.11** (theo `libs/langgraph/pyproject.toml` cùng ngày lấy).
- **Dùng cho:** A-045. Mọi trích dẫn dưới đây là nguyên văn; chỗ lược ghi `# ...`.

---

## 1. Phiên bản và phụ thuộc — `pyproject.toml`

```toml
name = "langgraph-checkpoint-postgres"
version = "3.1.2"
requires-python = ">=3.10"
dependencies = [
  "langgraph-checkpoint>=4.1.0,<5.0.0",
  "orjson>=3.11.5",
  "psycopg>=3.2.0",
  "psycopg-pool>=3.2.0",
]
```

## 2. Bảng mà thư viện tạo — `base.py`

```python
To add a new migration, add a new string to the MIGRATIONS list.
The position of the migration in the list is the version number.
"""
MIGRATIONS = [
    """CREATE TABLE IF NOT EXISTS checkpoint_migrations (
    v INTEGER PRIMARY KEY
);""",
    """CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);""",
    """CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);""",
    """CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);""",
    "ALTER TABLE checkpoint_blobs ALTER COLUMN blob DROP not null;",
    # NOTE: this is a no-op migration to ensure that the versions in the migrations table are correct.
    # This is necessary due to an empty migration previously added to the list.
    "SELECT 1;",
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS checkpoints_thread_id_idx ON checkpoints(thread_id);
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id);
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS checkpoint_writes_thread_id_idx ON checkpoint_writes(thread_id);
    """,
    """ALTER TABLE checkpoint_writes ADD COLUMN IF NOT EXISTS task_path TEXT NOT NULL DEFAULT '';""",
]
```

## 3. Cơ chế tạo bảng — `setup()` trong `__init__.py`

```python
    def setup(self) -> None:
        """Set up the checkpoint database asynchronously.

        This method creates the necessary tables in the Postgres database if they don't
        already exist and runs database migrations. It MUST be called directly by the user
        the first time checkpointer is used.
        """
        with self._cursor() as cur:
            cur.execute(self.MIGRATIONS[0])
            results = cur.execute(
                "SELECT v FROM checkpoint_migrations ORDER BY v DESC LIMIT 1"
            )
            row = results.fetchone()
            if row is None:
                version = -1
            else:
                version = row["v"]
            for v, migration in zip(
                range(version + 1, len(self.MIGRATIONS)),
                self.MIGRATIONS[version + 1 :],
                strict=False,
            ):
                cur.execute(migration)
                cur.execute("INSERT INTO checkpoint_migrations (v) VALUES (%s)", (v,))
        if self.pipe:
            self.pipe.sync()
```

`from_conn_string` mở kết nối như sau (dòng 77 của `__init__.py`; `aio.py` dòng 82 giống hệt):

```python
            conn_string, autocommit=True, prepare_threshold=0, row_factory=dict_row
```

## 4. Xoá một thread — `delete_thread()` trong `__init__.py`

```python
    def delete_thread(self, thread_id: str) -> None:
        """Delete all checkpoints and writes associated with a thread ID.

        Args:
            thread_id: The thread ID to delete.

        Returns:
            None
        """
        with self._cursor(pipeline=True) as cur:
            cur.execute(
                "DELETE FROM checkpoints WHERE thread_id = %s",
                (str(thread_id),),
            )
            cur.execute(
                "DELETE FROM checkpoint_blobs WHERE thread_id = %s",
                (str(thread_id),),
            )
            cur.execute(
                "DELETE FROM checkpoint_writes WHERE thread_id = %s",
# ...
```

Bản async là `adelete_thread` ở `aio.py` dòng 340.

## 5. Yêu cầu kết nối — `README.md`

> [!IMPORTANT]
> When using Postgres checkpointers for the first time, make sure to call `.setup()` method on them to create required tables. See example below.

> [!IMPORTANT]
> When manually creating Postgres connections and passing them to `PostgresSaver` or `AsyncPostgresSaver`, make sure to include `autocommit=True` and `row_factory=dict_row` (`from psycopg.rows import dict_row`). See a full example in this [how-to guide](https://langchain-ai.github.io/langgraph/how-tos/persistence_postgres/).
>
> **Why these parameters are required:**
>
> - `autocommit=True`: Required for the `.setup()` method to properly commit the checkpoint tables to the database. Without this, table creation may not be persisted.
> - `row_factory=dict_row`: Required because the PostgresSaver implementation accesses database rows using dictionary-style syntax (e.g., `row["column_name"]`). The default `tuple_row` factory returns tuples that only support index-based access (e.g., `row[0]`), which will cause `TypeError` exceptions when the checkpointer tries to access columns by name.

## 6. Lỗi của node được lưu vào checkpointer — `langgraph/pregel/_runner.py`

```python
    def commit(
        self,
        task: PregelExecutableTask,
        exception: BaseException | None,
    ) -> None:
        if isinstance(exception, asyncio.CancelledError):
            # for cancelled tasks, also save error in task,
            # so loop can finish super-step
            task.writes.append((ERROR, exception))
            self.put_writes()(task.id, task.writes)  # type: ignore[misc]
        elif exception:
            if isinstance(exception, GraphInterrupt):
                # save interrupt to checkpointer
                if exception.args[0]:
                    writes = [(INTERRUPT, exception.args[0])]
                    if resumes := [w for w in task.writes if w[0] == RESUME]:
                        writes.extend(resumes)
                    self.put_writes()(task.id, writes)  # type: ignore[misc]
            elif isinstance(exception, GraphBubbleUp):
                # exception will be raised in _panic_or_proceed
                pass
            else:
                # save error to checkpointer
                task.writes.append((ERROR, exception))
# ...
                self.put_writes()(task.id, task.writes)  # type: ignore[misc]
```

`langgraph/checkpoint/base/__init__.py` dòng 796:

```python
WRITES_IDX_MAP = {ERROR: -1, SCHEDULED: -2, INTERRUPT: -3, RESUME: -4}
```

---

## Nguồn này trả lời gì — và không trả lời gì

| Câu hỏi của A-045 | Nguồn nói |
|---|---|
| Bảng nào | `checkpoint_migrations`, `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, cùng ba index `*_thread_id_idx` (mục 2) |
| Tạo bằng cơ chế nào | Hàm `setup()` của thư viện chạy danh sách `MIGRATIONS` và ghi số phiên bản vào `checkpoint_migrations` (mục 3). Người dùng phải tự gọi |
| Lịch sử theo từng bước | Khoá chính của `checkpoints` gồm `checkpoint_id`, có `parent_checkpoint_id` — một thread giữ nhiều checkpoint (mục 2) |
| Lỗi của node có vào checkpoint không | **Có.** Exception của node được ghi thành một write kênh `ERROR` qua `put_writes` (mục 6) |
| Có ghi cùng giao dịch với bảng ứng dụng không | Kết nối được yêu cầu `autocommit=True` (mục 3, mục 5), nên checkpoint commit trên kết nối riêng của nó, không dự phần vào giao dịch của ứng dụng |
| Quyền cần có | **Nguồn không nói.** Suy ra từ câu lệnh: `setup()` cần quyền tạo bảng và index; chạy thường cần `SELECT`, `INSERT`, `UPDATE` (upsert) trên ba bảng dữ liệu, và `DELETE` cho `delete_thread` |

Hai điều **không** có trong nguồn: `CREATE INDEX CONCURRENTLY` có chạy được trong một khối giao dịch hay không — đó là hành vi của PostgreSQL, tài liệu PostgreSQL chưa có trong `docs/reference/`; và cách bộ tuần tự hoá lưu một exception — nội dung thông điệp có vào `blob` hay không.
