"""Kiểm contract DDL của BO-19: quyền của role runtime `bo19_app` khớp đúng các nhóm quyền
ở mục Nguyên tắc dữ liệu của docs/design/04-data.md.

KHÔNG phải mã ứng dụng. Không đóng gói vào image (Dockerfile chỉ chép backend/ và frontend/).
Nơi đặt, lý do và khi nào chạy lại: tools/contract-checks/README.md.

Hai chế độ:
  --local            Dựng PostgreSQL + pgvector tạm bằng pgserver, tạo hai role, áp schema.sql,
                     chạy setup() của checkpointer, cấp quyền thư viện, rồi kiểm.
  --app-dsn DSN      Chỉ kiểm, trên một cơ sở dữ liệu đã được migrate (ví dụ Render).
                     Không tạo role, không áp gì. Mọi phép thử dùng WHERE false hoặc giao dịch
                     rollback; TRUNCATE chỉ kiểm bằng has_table_privilege, không thực thi.

Mã thoát: 0 đạt · 1 có lệch · 2 lỗi môi trường.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

import psycopg
from psycopg import errors
from psycopg.conninfo import conninfo_to_dict, make_conninfo

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "docs" / "design" / "contracts" / "schema.sql"

# --- Nhóm quyền — nguồn: mục Nguyên tắc dữ liệu của docs/design/04-data.md -------------------
# Đổi nhóm ở 04-data.md và schema.sql thì đổi ở đây. Bảng mới không thuộc nhóm nào → lệch.
READ_ONLY = ["role", "permission", "role_permission", "employee_role", "employee_permission_grant"]
APPEND_ONLY = ["audit_event", "decision_record", "document_render_pin", "document_register_format",
               "template_variable", "template_variable_input", "seal_action", "document_halt",
               "operating_mode_change", "llm_usage", "procedure_chunk"]
INSERT_DELETE = ["decision_record_text", "document_render", "document_free_content", "stored_object",
                 "stored_object_commit", "procedure_chunk_embedding_v1"]
MUTABLE_NO_DELETE = ["employee", "request", "request_slot", "chat_session", "document", "approval_step",
                     "graph_thread", "delegation", "request_type", "slot_definition", "template",
                     "procedure_document", "room", "room_booking"]
COLUMN_UPDATE = {
    "chat_message": ["request_id", "body", "retrieval_query", "content_erased_at"],
    "template_version": ["status", "activated_at", "retired_at", "updated_at", "row_version"],
    "document_register": ["name", "is_active", "updated_at", "row_version"],
    "document_register_counter": ["next_seq", "updated_at"],
    "document_register_entry": ["status", "voided_at", "void_reason"],
    "notification": ["pushed_at", "read_at"],
    "procedure_document_version": ["is_active", "activated_at", "deactivated_at", "updated_at", "row_version"],
    "embedding_collection": ["status", "activated_at", "retired_at", "updated_at", "row_version"],
}
FULL_LIFECYCLE = ["job"]

# --- Bảng ngoài schema.sql ----------------------------------------------------------------------
CHECKPOINT_DATA = ["checkpoints", "checkpoint_blobs", "checkpoint_writes"]
CHECKPOINT_META = ["checkpoint_migrations"]
LEDGER = ["schema_migration"]            # ADR-017 — chỉ có sau khi có trình chạy migration

# Khớp mục Migration và checkpointer của docs/design/06-structure.md.
CHECKPOINTER_GRANTS = (
    "GRANT SELECT, INSERT, UPDATE, DELETE ON checkpoints, checkpoint_blobs, checkpoint_writes TO bo19_app;\n"
    "GRANT SELECT ON checkpoint_migrations TO bo19_app;"
)
EXPECTED_EMBEDDING_DIM = 1024            # ADR-012: procedure_chunk_embedding_v1.embedding vector(1024)


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


def setup_local(workdir: Path, rep: Report):
    import pgserver  # chỉ cần cho --local
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row

    srv = pgserver.get_server(workdir, cleanup_mode="stop")
    su = srv.get_uri()
    with psycopg.connect(su, autocommit=True) as c:
        rep.log("PostgreSQL:", c.execute("select version()").fetchone()[0])
        c.execute("create role bo19_migrator login")
        c.execute("create role bo19_app login")
        c.execute("create database bo19 owner bo19_migrator")
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

    # Bước 0 — extension, bằng role có quyền (mục Migration và checkpointer của 06-structure.md).
    with psycopg.connect(su_db, autocommit=True) as c:
        c.execute("create extension if not exists vector")
    # Bước 1 — schema.sql, bằng bo19_migrator, một giao dịch.
    with psycopg.connect(mig) as c:
        with c.transaction():
            c.execute(SCHEMA.read_text(encoding="utf-8"))
    # Bước 2 — setup() của checkpointer, autocommit (docs/reference/langgraph-checkpoint-postgres.md).
    with psycopg.connect(mig, autocommit=True, prepare_threshold=0, row_factory=dict_row) as c:
        PostgresSaver(c).setup()
    # Bước 3 — quyền trên bảng của thư viện.
    with psycopg.connect(mig) as c:
        with c.transaction():
            c.execute(CHECKPOINTER_GRANTS)
    rep.log("Đã dựng: extension → schema.sql → setup() → quyền thư viện")
    return srv, app


def run_checks(app_dsn: str, rep: Report, migrator_role: str | None, local: bool) -> None:
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
        known = set(schema_groups) | set(CHECKPOINT_DATA) | set(CHECKPOINT_META) | set(LEDGER)
        for t in sorted(tables - known):
            rep.mismatch.append(f"bảng {t} không thuộc nhóm quyền nào ở 04-data.md")
        for t in schema_groups:
            if t not in tables:
                rep.mismatch.append(f"bảng {t} có trong nhóm quyền nhưng không có trong DB")

        def upd(t: str, col: str | None = None) -> str:
            col = col or columns(t)[0]
            return f'update {t} set "{col}" = "{col}" where false'

        def trunc(t: str) -> str:
            ok = a.execute("select has_table_privilege(current_user, %s, 'TRUNCATE')", (t,)).fetchone()[0]
            return "ALLOW" if ok else "DENY"

        for t in (x for x in READ_ONLY if x in tables):
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
    mode.add_argument("--app-dsn")
    ap.add_argument("--migrator-role", default="bo19_migrator")
    args = ap.parse_args()

    rep = Report()
    rep.log("schema.sql sha256:", hashlib.sha256(SCHEMA.read_bytes()).hexdigest())
    workdir = None
    try:
        if args.local:
            workdir = Path(tempfile.mkdtemp(prefix="bo19-contract-"))
            _srv, app_dsn = setup_local(workdir / "pgdata", rep)
        else:
            app_dsn = args.app_dsn
        run_checks(app_dsn, rep, args.migrator_role, args.local)
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
