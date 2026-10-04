"""Lối thử quyền và đọc catalog cho bước kiểm khởi động — mục Cây backend của 06-structure.md.

Phép thử ghi chạy trong một giao dịch thường và LUÔN rollback, chỉ nhận câu có `WHERE false`:
PostgreSQL kiểm quyền mà không chạm dòng nào. Giao dịch READ ONLY không dùng được — nó báo lỗi chỉ đọc
trước khi kiểm quyền (luật import, contract `probe`, của 06-structure.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import psycopg
from psycopg import errors

_WHERE_FALSE = re.compile(r"\bwhere\s+false\s*;?\s*$", re.IGNORECASE)


class _Rollback(Exception):
    pass


def write_probe(conn: psycopg.Connection, sql: str) -> str:
    """Trả `DENIED` khi thiếu quyền, `ALLOWED` khi câu chạy được. Lỗi khác — ví dụ bảng không tồn tại —
    trả `ERROR:<sqlstate>`. Giao dịch luôn rollback."""
    if not _WHERE_FALSE.search(sql):
        raise ValueError("write_probe chỉ nhận câu kết thúc bằng WHERE false")
    try:
        with conn.transaction():
            conn.execute(sql)
            raise _Rollback
    except _Rollback:
        return "ALLOWED"
    except errors.InsufficientPrivilege:
        return "DENIED"
    except psycopg.Error as e:
        return f"ERROR:{e.sqlstate or type(e).__name__}"


@dataclass(frozen=True)
class RoleFacts:
    """Sự thật về role đang nối — đầu vào của vế role của bước kiểm khởi động #2."""
    user: str
    superuser: bool
    createrole: bool
    createdb: bool
    owns_database: bool
    owns_public: bool
    owned_public_tables: int


def role_facts(conn: psycopg.Connection) -> RoleFacts:
    row = conn.execute(
        """
        select current_user,
               r.rolsuper, r.rolcreaterole, r.rolcreatedb,
               (select pg_has_role(current_user, d.datdba, 'USAGE')
                  from pg_database d where d.datname = current_database()),
               (select pg_has_role(current_user, n.nspowner, 'USAGE')
                  from pg_namespace n where n.nspname = 'public'),
               (select count(*) from pg_tables t
                 where t.schemaname = 'public' and pg_has_role(current_user, t.tableowner, 'USAGE'))
          from pg_roles r where r.rolname = current_user
        """
    ).fetchone()
    conn.rollback()
    return RoleFacts(row[0], bool(row[1]), bool(row[2]), bool(row[3]), bool(row[4]), bool(row[5]), int(row[6]))


def read_ledger(conn: psycopg.Connection) -> dict[str, tuple[str, str]] | None:
    """Sổ `schema_migration`: {filename: (kind, sha256)}. Trả None khi sổ chưa có."""
    exists = conn.execute("select to_regclass('public.schema_migration') is not null").fetchone()[0]
    if not exists:
        conn.rollback()
        return None
    rows = conn.execute("select filename, kind, sha256 from schema_migration").fetchall()
    conn.rollback()
    return {f: (k, s) for f, k, s in rows}
