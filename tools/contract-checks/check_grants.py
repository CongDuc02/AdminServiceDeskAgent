"""Kiểm contract DDL của BO-19: quyền của role runtime `bo19_app` khớp đúng các nhóm quyền
ở mục Nguyên tắc dữ liệu của docs/design/04-data.md.

KHÔNG phải mã ứng dụng. Không đóng gói vào image (Dockerfile chỉ chép backend/ và frontend/).
Nơi đặt, lý do và khi nào chạy lại: tools/contract-checks/README.md.

Ba chế độ:
  --local            Dựng PostgreSQL + pgvector tạm bằng pgserver, tạo hai role, áp schema.sql,
                     chạy setup() của checkpointer, cấp quyền thư viện, rồi kiểm.
  --server-dsn DSN   Đi kèm --local hoặc --local-migrated: dùng một PostgreSQL có sẵn, kết nối bằng
                     superuser — ví dụ container pgvector/pgvector:0.8.1-pg18, cùng bản với Render —
                     thay cho pgserver. Server phải mới, chỉ dùng cho phép kiểm này.
  --local-migrated   Như --local, nhưng bước 1 áp lần lượt backend/migrations/schema/*.sql
                     (0001_initial.sql = schema.sql, rồi 0002, 0003, ...), mỗi file một giao dịch.
                     Kiểm được bảng và quyền của migration sau schema.sql. Sổ schema_migration được
                     tạo từ file DDL của nó nhưng để trống; không chạy data migration — không thay
                     migrate_main.
  --app-dsn DSN      Chỉ kiểm, trên một cơ sở dữ liệu đã được migrate (ví dụ Render).
                     Không tạo role, không áp gì. Mọi phép thử dùng WHERE false hoặc giao dịch
                     rollback; TRUNCATE chỉ kiểm bằng has_table_privilege, không thực thi.

Mã thoát: 0 đạt · 1 có lệch · 2 lỗi môi trường.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import psycopg
from psycopg import errors
from psycopg.conninfo import conninfo_to_dict, make_conninfo

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "docs" / "design" / "contracts" / "schema.sql"
MIGRATIONS = REPO / "backend" / "migrations" / "schema"

DATA_DESIGN = REPO / "docs" / "design" / "04-data.md"
CHECKPOINTER_GRANTS_FILE = REPO / "backend" / "migrations" / "library" / "checkpointer_grants.sql"
LEDGER_FILE = REPO / "backend" / "migrations" / "ledger" / "schema_migration.sql"

# Không giữ bản chép cứng của nội dung file nào trong repo (PO, 2026-10-04 — sự cố file grant rỗng ở S1).
# Mỗi kỳ vọng đọc từ đúng file làm nguồn của nó:
#   - nhóm quyền theo bảng      ← bảng nhóm quyền ở mục "Hai role, và bất biến bằng quyền" của 04-data.md
#   - cột của nhóm sửa theo cột ← các câu GRANT UPDATE (...) ON t TO bo19_app trong file SQL được áp
#                                 (04-data.md: "UPDATE chỉ trên các cột liệt kê trong schema.sql")
#   - bảng của checkpointer, câu GRANT bước 3 ← backend/migrations/library/checkpointer_grants.sql
#   - số chiều embedding         ← vector(N) trong DDL của procedure_chunk_embedding_v1
#   - sổ migration, quyền của bo19_app trên sổ ← backend/migrations/ledger/schema_migration.sql (ADR-017)

# Tên hàng trong bảng nhóm quyền của 04-data.md → nhóm của bộ kiểm.
GROUP_ROWS = {
    "Chỉ đọc": "READ_ONLY",
    "Chỉ thêm": "APPEND_ONLY",
    "Thêm và xoá, không sửa": "INSERT_DELETE",
    "Sửa được, không xoá": "MUTABLE_NO_DELETE",
    "Sửa theo cột": "COLUMN_UPDATE",
    "Đủ vòng đời": "FULL_LIFECYCLE",
    "Chỉ đọc — ghi bằng thao tác vận hành": "MIGRATION_READ_ONLY",
    "Đếm và dọn theo cửa sổ": "MIGRATION_COLUMN_UPDATE",
}


def executable_sql(text: str) -> str:
    """Bỏ chú thích -- và /* */ cùng khoảng trắng. Rỗng nghĩa là file không có câu SQL thực thi được."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    return text.strip()


def read_sql(path: Path) -> str:
    """Đọc một file SQL sẽ áp. Không có câu thực thi được thì dừng — không coi là đạt (luật của ADR-017)."""
    text = path.read_text(encoding="utf-8")
    if not executable_sql(text):
        shown = path.relative_to(REPO) if path.is_relative_to(REPO) else path
        raise OSError(f"file không có câu SQL thực thi được: {shown.as_posix()}")
    return text


class ExpectationError(Exception):
    """Nguồn kỳ vọng hỏng hay mâu thuẫn — bộ kiểm dừng với mã 2, không kiểm trên kỳ vọng sai."""


def design_groups(text: str | None = None) -> dict[str, list[str]]:
    """Đọc bảng nhóm quyền của 04-data.md. Hỏng thành tiếng — PO, 2026-10-04: không tìm thấy bảng,
    hàng lạ, thiếu hàng, hay một nhóm parse ra rỗng đều là ExpectationError."""
    lines = (DATA_DESIGN.read_text(encoding="utf-8") if text is None else text).splitlines()
    start = next((k for k, l in enumerate(lines) if l.startswith("| Nhóm quyền của `bo19_app`")), None)
    if start is None:
        raise ExpectationError("04-data.md: không tìm thấy bảng nhóm quyền của bo19_app")
    groups: dict[str, list[str]] = {}
    for l in lines[start + 2:]:
        if not l.startswith("|"):
            break
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        name = cells[0].replace("**", "").strip()
        if name not in GROUP_ROWS:
            raise ExpectationError(f"04-data.md: hàng nhóm quyền lạ {name!r} — thêm vào GROUP_ROWS")
        tables = re.findall(r"`([a-z_0-9]+)`", cells[1]) if len(cells) > 1 else []
        if not tables:
            raise ExpectationError(f"04-data.md: nhóm {name!r} parse ra rỗng")
        groups[GROUP_ROWS[name]] = tables
    missing = set(GROUP_ROWS.values()) - set(groups)
    if missing:
        raise ExpectationError(f"04-data.md: thiếu hàng nhóm quyền {sorted(missing)}")
    return groups


def schema_tables(files: list[Path]) -> set[str]:
    """Tên bảng có CREATE TABLE trong các file SQL — bỏ qua chú thích."""
    names: set[str] = set()
    for f in files:
        sql = executable_sql(f.read_text(encoding="utf-8"))
        names |= {m.group(1) for m in re.finditer(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-z_0-9]+)", sql, re.I)}
    return names


def validate_groups(groups: dict[str, list[str]], tables: set[str]) -> None:
    """Một bảng thuộc hơn một nhóm, hay bảng có trong schema mà không thuộc nhóm nào → ExpectationError."""
    seen: dict[str, str] = {}
    for g, ts in groups.items():
        for t in ts:
            if t in seen and seen[t] != g:
                raise ExpectationError(f"bảng {t} thuộc hơn một nhóm quyền: {seen[t]}, {g}")
            seen[t] = g
    orphan = sorted(tables - set(seen))
    if orphan:
        raise ExpectationError(f"bảng có trong schema mà không thuộc nhóm quyền nào ở 04-data.md: {orphan}")


def grant_update_columns(files: list[Path]) -> dict[str, list[str]]:
    cols: dict[str, list[str]] = {}
    for f in files:
        sql = executable_sql(f.read_text(encoding="utf-8"))
        for m in re.finditer(r"GRANT\s+UPDATE\s*\(([^)]*)\)\s*ON\s+([a-z_0-9]+)\s+TO\s+bo19_app", sql, re.I):
            cols[m.group(2)] = [c.strip() for c in m.group(1).split(",")]
    return cols


def checkpointer_tables() -> tuple[list[str], list[str]]:
    sql = executable_sql(read_sql(CHECKPOINTER_GRANTS_FILE))
    data, meta = [], []
    for m in re.finditer(r"GRANT\s+([A-Z ,]+?)\s+ON\s+([a-z_0-9 ,]+?)\s+TO\s+bo19_app", sql, re.I):
        privs = {p.strip().upper() for p in m.group(1).split(",")}
        tables = [t.strip() for t in m.group(2).split(",")]
        (data if {"INSERT", "UPDATE", "DELETE"} <= privs else meta).extend(tables)
    return data, meta


def ledger_tables() -> list[str]:
    """Bảng sổ, từ file DDL sổ. PO, 2026-10-04: bo19_app chỉ SELECT trên sổ — file cấp khác thì dừng,
    không kiểm trên kỳ vọng sai."""
    sql = executable_sql(read_sql(LEDGER_FILE))
    tables = sorted({m.group(1) for m in re.finditer(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-z_0-9]+)", sql, re.I)})
    if not tables:
        raise ExpectationError("schema_migration.sql: không có CREATE TABLE")
    grants: dict[str, set[str]] = {}
    for m in re.finditer(r"GRANT\s+([A-Z ,]+?)\s+ON\s+(?:TABLE\s+)?([a-z_0-9 ,]+?)\s+TO\s+bo19_app\b", sql, re.I):
        for t in (x.strip() for x in m.group(2).split(",")):
            grants.setdefault(t, set()).update(x.strip().upper() for x in m.group(1).split(","))
    for t in tables:
        if grants.get(t) != {"SELECT"}:
            raise ExpectationError(
                f"schema_migration.sql: bo19_app trên {t} phải đúng SELECT, file cấp {sorted(grants.get(t, set()))}")
    return tables


def embedding_dim(files: list[Path]) -> int:
    for f in files:
        m = re.search(r"CREATE TABLE procedure_chunk_embedding_v1\b.*?vector\((\d+)\)",
                      executable_sql(f.read_text(encoding="utf-8")), re.S)
        if m:
            return int(m.group(1))
    raise ExpectationError("không tìm thấy vector(N) của procedure_chunk_embedding_v1 trong file SQL")


def load_expectations(migrated: bool) -> None:
    """Nạp mọi kỳ vọng từ file repo vào biến module — gọi một lần trước khi dựng hay kiểm."""
    global READ_ONLY, APPEND_ONLY, INSERT_DELETE, MUTABLE_NO_DELETE, COLUMN_UPDATE, FULL_LIFECYCLE
    global MIGRATION_READ_ONLY, MIGRATION_COLUMN_UPDATE, CHECKPOINT_DATA, CHECKPOINT_META
    global CHECKPOINTER_GRANTS, EXPECTED_EMBEDDING_DIM, LEDGER, LEDGER_DDL
    g = design_groups()
    files = sorted(MIGRATIONS.glob("*.sql")) if migrated else [SCHEMA]
    validate_groups(g, schema_tables(files))
    all_files = sorted(MIGRATIONS.glob("*.sql"))
    upd = grant_update_columns(files)
    upd_all = grant_update_columns(all_files)
    READ_ONLY, APPEND_ONLY = g["READ_ONLY"], g["APPEND_ONLY"]
    INSERT_DELETE, MUTABLE_NO_DELETE = g["INSERT_DELETE"], g["MUTABLE_NO_DELETE"]
    FULL_LIFECYCLE = g["FULL_LIFECYCLE"]
    MIGRATION_READ_ONLY = g["MIGRATION_READ_ONLY"]
    COLUMN_UPDATE = {t: upd.get(t, []) for t in g["COLUMN_UPDATE"]}
    MIGRATION_COLUMN_UPDATE = {t: upd_all.get(t, []) for t in g["MIGRATION_COLUMN_UPDATE"]}
    for t, c in {**COLUMN_UPDATE, **MIGRATION_COLUMN_UPDATE}.items():
        if not c:
            raise ExpectationError(f"nhóm sửa theo cột: không tìm thấy GRANT UPDATE (...) ON {t} TO bo19_app")
    CHECKPOINT_DATA, CHECKPOINT_META = checkpointer_tables()
    CHECKPOINTER_GRANTS = read_sql(CHECKPOINTER_GRANTS_FILE)
    EXPECTED_EMBEDDING_DIM = embedding_dim(files)
    LEDGER = ledger_tables()
    LEDGER_DDL = read_sql(LEDGER_FILE)



class _Rollback(Exception):
    pass


def dsn_with(dsn: str, user: str | None = None, db: str | None = None) -> str:
    d = conninfo_to_dict(dsn)
    if user:
        d["user"] = user
        d.pop("password", None)
    if db:
        d["dbname"] = db
    return make_conninfo(**d)


def probe(conn: psycopg.Connection, sql: str) -> str:
    """DENY nếu PostgreSQL từ chối vì thiếu quyền; ALLOW nếu qua được bước kiểm quyền. Luôn rollback."""
    try:
        with conn.transaction():
            conn.execute(sql)
            raise _Rollback
    except _Rollback:
        return "ALLOW"
    except errors.InsufficientPrivilege:
        return "DENY"
    except psycopg.Error:
        return "ALLOW"   # lỗi khác (NOT NULL, ...) nghĩa là đã qua bước kiểm quyền


class Report:
    def __init__(self) -> None:
        self.deny_ok = 0
        self.allow_ok = 0
        self.mismatch: list[str] = []
        self.lines: list[str] = []

    def log(self, *parts: object) -> None:
        line = " ".join(str(p) for p in parts)
        print(line)
        self.lines.append(line)

    def expect(self, what: str, got: str, want: str) -> None:
        if got == want:
            if want == "DENY":
                self.deny_ok += 1
            else:
                self.allow_ok += 1
        else:
            self.mismatch.append(f"{what}: muốn {want}, được {got}")


def setup_local(workdir: Path, rep: Report, migrated: bool = False, server_dsn: str | None = None):
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row

    if server_dsn:
        srv, su = None, server_dsn
    else:
        import pgserver  # chỉ cần khi không có --server-dsn
        srv = pgserver.get_server(workdir, cleanup_mode="stop")
        su = srv.get_uri()
    # Database thuộc superuser — đứng thay user mặc định của Render, chủ database và schema public
    # trên Render (docs/reference/render-postgres-s0.md). bo19_migrator nhận CREATE trên public ở
    # bước 0 (mục Migration và checkpointer của 06-structure.md).
    with psycopg.connect(su, autocommit=True) as c:
        rep.log("PostgreSQL:", c.execute("select version()").fetchone()[0])
        c.execute("create role bo19_migrator login")
        c.execute("create role bo19_app login")
        c.execute("create database bo19")
        c.execute("create database bo19_probe owner bo19_migrator")
    su_db = dsn_with(su, db="bo19")
    mig = dsn_with(su, "bo19_migrator", "bo19")
    app = dsn_with(su, "bo19_app", "bo19")

    # Thông tin cho A-040 vế (3): role sở hữu bảng có tự tạo được extension không.
    with psycopg.connect(dsn_with(su, "bo19_migrator", "bo19_probe"), autocommit=True) as c:
        try:
            c.execute("create extension vector")
            rep.log("INFO bo19_migrator tạo extension vector: ĐƯỢC")
        except errors.InsufficientPrivilege as e:
            rep.log("INFO bo19_migrator tạo extension vector: BỊ TỪ CHỐI |", str(e).splitlines()[0])

    # Bước 0 — bằng role có quyền (mục Migration và checkpointer của 06-structure.md):
    # extension, và quyền CREATE trên public cho bo19_migrator.
    with psycopg.connect(su_db, autocommit=True) as c:
        c.execute("create extension if not exists vector")
        c.execute("grant create on schema public to bo19_migrator")
        rep.log("Chủ schema public:", c.execute(
            "select pg_get_userbyid(nspowner) from pg_namespace where nspname = 'public'").fetchone()[0])
    # Sổ migration — migrate_main tạo nó trước bước 1, bằng bo19_migrator (ADR-017). Ở đây để trống.
    with psycopg.connect(mig) as c:
        with c.transaction():
            c.execute(LEDGER_DDL)
        rep.log("Đã áp:", LEDGER_FILE.relative_to(REPO).as_posix())
    # Bước 1 — schema.sql, hoặc mọi file của backend/migrations/schema theo thứ tự; bằng bo19_migrator,
    # mỗi file một giao dịch (ADR-017).
    files = sorted(MIGRATIONS.glob("*.sql")) if migrated else [SCHEMA]
    with psycopg.connect(mig) as c:
        for f in files:
            with c.transaction():
                c.execute(read_sql(f))
            rep.log("Đã áp:", f.relative_to(REPO).as_posix())
    # Bước 2 — setup() của checkpointer, autocommit (docs/reference/langgraph-checkpoint-postgres.md).
    with psycopg.connect(mig, autocommit=True, prepare_threshold=0, row_factory=dict_row) as c:
        PostgresSaver(c).setup()
    # Bước 3 — quyền trên bảng của thư viện.
    with psycopg.connect(mig) as c:
        with c.transaction():
            c.execute(CHECKPOINTER_GRANTS)
    rep.log("Đã dựng: extension → " + ("migrations/schema/*.sql" if migrated else "schema.sql")
            + " → setup() → quyền thư viện")
    return srv, app


def run_checks(app_dsn: str, rep: Report, migrator_role: str | None, local: bool,
               migrated: bool = True) -> None:
    with psycopg.connect(app_dsn) as a:
        ext = a.execute("select extversion from pg_extension where extname = 'vector'").fetchone()
        rep.log("pgvector:", ext[0] if ext else "KHÔNG CÓ")
        tables = {r[0] for r in a.execute("select tablename from pg_tables where schemaname = 'public'")}
        rep.log("Bảng trong public:", len(tables))

        def columns(t: str) -> list[str]:
            return [r[0] for r in a.execute(
                "select column_name from information_schema.columns "
                "where table_schema = 'public' and table_name = %s order by ordinal_position", (t,))]

        # Độ phủ: mọi bảng thuộc đúng một nhóm; mọi bảng của nhóm tồn tại.
        schema_groups = (READ_ONLY + APPEND_ONLY + INSERT_DELETE + MUTABLE_NO_DELETE
                         + list(COLUMN_UPDATE) + FULL_LIFECYCLE)
        migration_groups = MIGRATION_READ_ONLY + list(MIGRATION_COLUMN_UPDATE)
        known = (set(schema_groups) | set(migration_groups)
                 | set(CHECKPOINT_DATA) | set(CHECKPOINT_META) | set(LEDGER))
        for t in sorted(tables - known):
            rep.mismatch.append(f"bảng {t} không thuộc nhóm quyền nào ở 04-data.md")
        for t in schema_groups:
            if t not in tables:
                rep.mismatch.append(f"bảng {t} có trong nhóm quyền nhưng không có trong DB")
        for t in migration_groups:
            if t in tables:
                continue
            if not migrated:
                rep.log(f"INFO bảng {t} của migration sau schema.sql không có ở --local — bỏ qua")
            else:
                rep.mismatch.append(f"bảng {t} có trong nhóm quyền nhưng không có trong DB đã migrate")

        def upd(t: str, col: str | None = None) -> str:
            col = col or columns(t)[0]
            return f'update {t} set "{col}" = "{col}" where false'

        def trunc(t: str) -> str:
            ok = a.execute("select has_table_privilege(current_user, %s, 'TRUNCATE')", (t,)).fetchone()[0]
            return "ALLOW" if ok else "DENY"

        for t in LEDGER:
            if t not in tables:
                rep.mismatch.append(f"sổ {t} không có trong DB — migrate_main chưa chạy")
        for t in (x for x in READ_ONLY + MIGRATION_READ_ONLY + LEDGER if x in tables):
            rep.expect(f"{t} SELECT", probe(a, f"select 1 from {t} limit 0"), "ALLOW")
            rep.expect(f"{t} INSERT", probe(a, f"insert into {t} default values"), "DENY")
            rep.expect(f"{t} UPDATE", probe(a, upd(t)), "DENY")
            rep.expect(f"{t} DELETE", probe(a, f"delete from {t} where false"), "DENY")
            rep.expect(f"{t} TRUNCATE", trunc(t), "DENY")
        for t in (x for x in APPEND_ONLY if x in tables):
            rep.expect(f"{t} UPDATE", probe(a, upd(t)), "DENY")
            rep.expect(f"{t} DELETE", probe(a, f"delete from {t} where false"), "DENY")
            rep.expect(f"{t} TRUNCATE", trunc(t), "DENY")
        for t in (x for x in INSERT_DELETE if x in tables):
            rep.expect(f"{t} UPDATE", probe(a, upd(t)), "DENY")
            rep.expect(f"{t} DELETE", probe(a, f"delete from {t} where false"), "ALLOW")
            rep.expect(f"{t} TRUNCATE", trunc(t), "DENY")
        for t in (x for x in MUTABLE_NO_DELETE if x in tables):
            rep.expect(f"{t} UPDATE", probe(a, upd(t)), "ALLOW")
            rep.expect(f"{t} DELETE", probe(a, f"delete from {t} where false"), "DENY")
            rep.expect(f"{t} TRUNCATE", trunc(t), "DENY")
        for t, allowed in COLUMN_UPDATE.items():
            if t not in tables:
                continue
            for col in allowed:
                rep.expect(f"{t} UPDATE({col})", probe(a, upd(t, col)), "ALLOW")
            for col in (c for c in columns(t) if c not in allowed):
                rep.expect(f"{t} UPDATE({col})", probe(a, upd(t, col)), "DENY")
            rep.expect(f"{t} DELETE", probe(a, f"delete from {t} where false"), "DENY")
            rep.expect(f"{t} TRUNCATE", trunc(t), "DENY")
        for t in (x for x in FULL_LIFECYCLE if x in tables):
            rep.expect(f"{t} UPDATE", probe(a, upd(t)), "ALLOW")
            rep.expect(f"{t} DELETE", probe(a, f"delete from {t} where false"), "ALLOW")
        for t, allowed in MIGRATION_COLUMN_UPDATE.items():
            if t not in tables:
                continue
            rep.expect(f"{t} SELECT", probe(a, f"select 1 from {t} limit 0"), "ALLOW")
            rep.expect(f"{t} INSERT", probe(a, f"insert into {t} default values"), "ALLOW")
            for col in allowed:
                rep.expect(f"{t} UPDATE({col})", probe(a, upd(t, col)), "ALLOW")
            for col in (c for c in columns(t) if c not in allowed):
                rep.expect(f"{t} UPDATE({col})", probe(a, upd(t, col)), "DENY")
            rep.expect(f"{t} DELETE", probe(a, f"delete from {t} where false"), "ALLOW")
            rep.expect(f"{t} TRUNCATE", trunc(t), "DENY")

        if all(t in tables for t in CHECKPOINT_DATA + CHECKPOINT_META):
            for t in CHECKPOINT_DATA:
                rep.expect(f"{t} UPDATE", probe(a, upd(t)), "ALLOW")
                rep.expect(f"{t} DELETE", probe(a, f"delete from {t} where false"), "ALLOW")
                rep.expect(f"{t} TRUNCATE", trunc(t), "DENY")
            rep.expect("checkpoint_migrations INSERT",
                       probe(a, "insert into checkpoint_migrations (v) values (-1)"), "DENY")
            v = a.execute("select max(v) from checkpoint_migrations").fetchone()[0]
            rep.log("checkpoint_migrations max(v):", v)
        else:
            rep.log("INFO chưa có bảng của checkpointer — bỏ qua nhóm đó")

        rep.expect("public CREATE TABLE", probe(a, "create table public.x_contract_probe (i int)"), "DENY")

        # Các phép kiểm ngoài bảng nhóm quyền — báo riêng, không cộng vào hai con số chính.
        extra: list[tuple[str, bool]] = []
        owned = a.execute("select count(*) from pg_tables where schemaname = 'public' "
                          "and tableowner = current_user").fetchone()[0]
        extra.append(("bo19_app không sở hữu bảng nào", owned == 0))
        if migrator_role:
            others = a.execute("select count(*) from pg_tables where schemaname = 'public' and tableowner <> %s "
                               "and tablename <> all(%s)", (migrator_role, CHECKPOINT_DATA + CHECKPOINT_META)).fetchone()[0]
            extra.append((f"mọi bảng của schema.sql do {migrator_role} sở hữu", others == 0))
        try:
            with a.transaction():
                a.execute("set transaction read only")
                a.execute("update request set updated_at = updated_at where false")
            extra.append(("giao dịch READ ONLY chặn UPDATE có quyền", False))
        except errors.ReadOnlySqlTransaction:
            extra.append(("giao dịch READ ONLY chặn UPDATE có quyền", True))
        dim = a.execute("select atttypmod from pg_attribute where attrelid = 'procedure_chunk_embedding_v1'::regclass "
                        "and attname = 'embedding'").fetchone()
        extra.append((f"số chiều embedding đọc từ catalog = {EXPECTED_EMBEDDING_DIM}",
                      bool(dim) and dim[0] == EXPECTED_EMBEDDING_DIM))
        for name, ok in extra:
            rep.log("KIỂM THÊM", "ĐẠT" if ok else "LỆCH", "|", name)
            if not ok:
                rep.mismatch.append(name)

    if local:
        from langgraph.checkpoint.base import empty_checkpoint
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        thread = "document:00000000-0000-0000-0000-000000000001"
        with psycopg.connect(app_dsn, autocommit=True, prepare_threshold=0, row_factory=dict_row) as c:
            saver = PostgresSaver(c)
            saver.put({"configurable": {"thread_id": thread, "checkpoint_ns": ""}},
                      empty_checkpoint(), {"source": "input", "step": -1}, {})
            n1 = c.execute("select count(*) as n from checkpoints where thread_id = %s", (thread,)).fetchone()["n"]
            saver.delete_thread(thread)
            n2 = c.execute("select count(*) as n from checkpoints where thread_id = %s", (thread,)).fetchone()["n"]
            rep.log("KIỂM THÊM", "ĐẠT" if (n1, n2) == (1, 0) else "LỆCH", "| bo19_app put rồi delete_thread:", n1, "→", n2)
            if (n1, n2) != (1, 0):
                rep.mismatch.append("checkpointer put/delete_thread dưới quyền bo19_app")
            try:
                saver.setup()
                rep.mismatch.append("bo19_app gọi được setup() — runtime không được migrate")
            except errors.InsufficientPrivilege:
                rep.log("KIỂM THÊM ĐẠT | bo19_app gọi setup() bị từ chối")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--local", action="store_true")
    mode.add_argument("--local-migrated", action="store_true")
    mode.add_argument("--app-dsn", help="DSN, hoặc env:TÊN_BIẾN để đọc từ biến môi trường")
    ap.add_argument("--migrator-role", default="bo19_migrator")
    ap.add_argument("--server-dsn")
    args = ap.parse_args()
    if args.server_dsn and args.app_dsn:
        ap.error("--server-dsn chỉ đi với --local hoặc --local-migrated")

    rep = Report()
    rep.log("schema.sql sha256:", hashlib.sha256(SCHEMA.read_bytes()).hexdigest())
    try:
        load_expectations(migrated=not args.local)
    except (ExpectationError, OSError) as e:
        rep.log("LỖI NGUỒN KỲ VỌNG:", str(e) or type(e).__name__)
        return 2
    rep.log("Kỳ vọng đọc từ: 04-data.md, " + ("backend/migrations/schema/*.sql" if not args.local else "schema.sql")
            + ", checkpointer_grants.sql, ledger/schema_migration.sql — nhóm:", len(READ_ONLY), len(APPEND_ONLY), len(INSERT_DELETE),
            len(MUTABLE_NO_DELETE), len(COLUMN_UPDATE), len(FULL_LIFECYCLE), "· checkpoint:",
            len(CHECKPOINT_DATA), "+", len(CHECKPOINT_META), "· sổ:", len(LEDGER), "· số chiều:", EXPECTED_EMBEDDING_DIM)
    workdir = None
    try:
        local = args.local or args.local_migrated
        migrated = not args.local
        if local:
            workdir = Path(tempfile.mkdtemp(prefix="bo19-contract-"))
            _srv, app_dsn = setup_local(workdir / "pgdata", rep, migrated, args.server_dsn)
        else:
            app_dsn = args.app_dsn
            if app_dsn.startswith("env:"):
                app_dsn = os.environ[app_dsn[4:]]
        run_checks(app_dsn, rep, args.migrator_role, local, migrated)
    except (psycopg.Error, OSError) as e:
        rep.log("LỖI MÔI TRƯỜNG:", type(e).__name__, str(e).splitlines()[0] if str(e) else "")
        return 2
    finally:
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)

    rep.log("Kiểm phủ định — từ chối đúng:", rep.deny_ok)
    rep.log("Kiểm khẳng định — cho phép đúng:", rep.allow_ok)
    rep.log("Lệch:", len(rep.mismatch))
    for m in rep.mismatch:
        rep.log("   ", m)
    return 1 if rep.mismatch else 0


if __name__ == "__main__":
    sys.exit(main())
