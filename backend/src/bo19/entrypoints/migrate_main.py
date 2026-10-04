"""Migrate — trình chạy migration của ADR-017, bằng bo19_migrator — composition root, không ai import entrypoints.

Trình tự (mục Migration và checkpointer của 06-structure.md). Bước 0 KHÔNG ở đây — chạy bằng user mặc định
của Render, do PO (ADR-022, cập nhật 2026-10-04):

  sổ  migrations/ledger/schema_migration.sql — tạo sổ nếu chưa có; idempotent; mỗi lần chạy
  1   migrations/schema/*.sql theo thứ tự — mỗi file một giao dịch, ghi sổ trong cùng giao dịch
  2   setup() của langgraph-checkpoint-postgres — autocommit
  3   migrations/library/checkpointer_grants.sql — một giao dịch, NGOÀI sổ, chạy lại mỗi lần
  4   migrations/data/*.sql theo thứ tự — như bước 1, kind = data

Luật: file không có câu SQL thực thi được thì dừng (ADR-017, 2026-10-04). File đã có trong sổ mà sha256 khác
thì dừng — migration đã áp là bất biến. DSN đọc từ biến BO19_MIGRATOR_DATABASE_URL; không bao giờ ghi ra log.
Mã thoát: 0 đạt · 1 dừng vì luật hoặc lỗi SQL · 2 cấu hình thiếu.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
from pathlib import Path

import psycopg

log = logging.getLogger("bo19.migrate")

# /app/src/bo19/entrypoints/migrate_main.py → /app/migrations ; backend/src/... → backend/migrations
MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


class MigrationStop(Exception):
    """Dừng có mã — không áp tiếp file nào."""


def executable_sql(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines()).strip()


def read_sql(path: Path, root: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if not executable_sql(text):
        raise MigrationStop(f"MIGRATE_EMPTY_FILE {path.relative_to(root).as_posix()}")
    return text, hashlib.sha256(raw).hexdigest()


def apply_numbered(conn: psycopg.Connection, root: Path, kind: str) -> tuple[int, int]:
    """Bước 1 hoặc 4. Trả (đã áp, đã có sẵn)."""
    applied = skipped = 0
    ledger = {f: (k, s) for f, k, s in conn.execute("select filename, kind, sha256 from schema_migration")}
    conn.commit()
    for path in sorted((root / kind).glob("*.sql")):
        name = f"{kind}/{path.name}"
        text, sha = read_sql(path, root)
        if name in ledger:
            if ledger[name] != (kind, sha):
                raise MigrationStop(f"MIGRATE_LEDGER_MISMATCH {name}")
            skipped += 1
            continue
        with conn.transaction():
            conn.execute(text)
            conn.execute("insert into schema_migration (filename, kind, sha256) values (%s, %s, %s)", (name, kind, sha))
        log.info("MIGRATE_APPLIED %s sha256=%s", name, sha[:12])
        applied += 1
    return applied, skipped


def run(dsn: str, root: Path = MIGRATIONS_DIR) -> None:
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row

    with psycopg.connect(dsn, connect_timeout=10, application_name="bo19-migrate") as conn:
        user = conn.execute("select current_user").fetchone()[0]
        conn.commit()
        log.info("MIGRATE_START user=%s", user)
        ledger_sql, _ = read_sql(root / "ledger" / "schema_migration.sql", root)
        with conn.transaction():
            conn.execute(ledger_sql)
        log.info("MIGRATE_LEDGER_READY")
        a, s = apply_numbered(conn, root, "schema")
        log.info("MIGRATE_STEP_1 applied=%d already=%d", a, s)
    with psycopg.connect(dsn, autocommit=True, prepare_threshold=0, row_factory=dict_row,
                         connect_timeout=10, application_name="bo19-migrate") as conn:
        PostgresSaver(conn).setup()
        v = conn.execute("select max(v) as v from checkpoint_migrations").fetchone()["v"]
        log.info("MIGRATE_STEP_2 checkpointer setup() max(v)=%s", v)
    with psycopg.connect(dsn, connect_timeout=10, application_name="bo19-migrate") as conn:
        grants, _ = read_sql(root / "library" / "checkpointer_grants.sql", root)
        with conn.transaction():
            conn.execute(grants)
        log.info("MIGRATE_STEP_3 checkpointer_grants")
        a, s = apply_numbered(conn, root, "data")
        log.info("MIGRATE_STEP_4 applied=%d already=%d", a, s)


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    dsn = os.environ.get("BO19_MIGRATOR_DATABASE_URL", "").strip()
    if not dsn:
        log.error("MIGRATE_FAIL CONFIG_MIGRATOR_DATABASE_URL_MISSING")
        sys.exit(2)
    try:
        run(dsn)
    except MigrationStop as e:
        log.error("MIGRATE_FAIL %s", e)
        sys.exit(1)
    except psycopg.Error as e:
        log.error("MIGRATE_FAIL SQL class=%s sqlstate=%s", type(e).__name__, e.sqlstate)
        sys.exit(1)
    log.info("MIGRATE_OK")


if __name__ == "__main__":
    main()
