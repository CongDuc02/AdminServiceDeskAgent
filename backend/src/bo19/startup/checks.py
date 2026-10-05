"""Bước kiểm khởi động #1 và #2 — mục Bước kiểm khởi động của 06-structure.md. Viết ở S2 của Spike 1; B2 chuyển vào bộ chạy `runner.py`.

Hàm `evaluate_*` là hàm thuần trên dữ liệu đã đọc, để test không cần PostgreSQL; `step_01`, `step_02` đọc rồi gọi chúng.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import psycopg

from bo19.persistence import probe
from bo19.startup.model import Context, Result

# /app/src/bo19/startup/checks.py → /app/migrations ; backend/src/bo19/startup → backend/migrations
MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"

# Phép thử phủ định của bước #2 — bảng "chỉ thêm" (mục Hai role, và bất biến bằng quyền của 04-data.md).
AUDIT_EVENT_UPDATE_PROBE = "UPDATE audit_event SET id = id WHERE false"


@dataclass(frozen=True)
class KnownMigration:
    filename: str  # tương đối với migrations/, ví dụ schema/0001_initial.sql
    kind: str      # schema | data
    sha256: str


def known_migrations(root: Path = MIGRATIONS_DIR) -> list[KnownMigration]:
    out: list[KnownMigration] = []
    for kind in ("schema", "data"):
        for f in sorted((root / kind).glob("*.sql")):
            out.append(KnownMigration(f"{kind}/{f.name}", kind, hashlib.sha256(f.read_bytes()).hexdigest()))
    return out


def evaluate_ledger(ledger: dict[str, tuple[str, str]] | None, known: list[KnownMigration]) -> list[str]:
    """Bước #1: mọi migration mà image mang theo đã có trong sổ, cùng loại và sha256."""
    if ledger is None:
        return ["STARTUP_01_LEDGER_MISSING"]
    if not known:
        return ["STARTUP_01_NO_MIGRATIONS_IN_IMAGE"]
    fails: list[str] = []
    for m in known:
        got = ledger.get(m.filename)
        if got is None:
            fails.append(f"STARTUP_01_NOT_APPLIED:{m.filename}")
        elif got[0] != m.kind:
            fails.append(f"STARTUP_01_KIND_MISMATCH:{m.filename}")
        elif got[1] != m.sha256:
            fails.append(f"STARTUP_01_SHA256_MISMATCH:{m.filename}")
    return fails


def evaluate_role(facts: probe.RoleFacts, audit_event_update: str) -> list[str]:
    """Bước #2: role runtime chỉ có đúng quyền được cấp — mở rộng 2026-10-04 theo PO."""
    fails: list[str] = []
    if facts.superuser:
        fails.append("STARTUP_02_SUPERUSER")
    if facts.createrole:
        fails.append("STARTUP_02_CREATEROLE")
    if facts.createdb:
        fails.append("STARTUP_02_CREATEDB")
    if facts.owns_database:
        fails.append("STARTUP_02_OWNS_DATABASE")
    if facts.owns_public:
        fails.append("STARTUP_02_OWNS_SCHEMA_PUBLIC")
    if facts.owned_public_tables:
        fails.append("STARTUP_02_OWNS_TABLES")
    if audit_event_update == "ALLOWED":
        fails.append("STARTUP_02_AUDIT_EVENT_WRITABLE")
    elif audit_event_update != "DENIED":
        fails.append(f"STARTUP_02_PROBE_{audit_event_update}")
    return fails


def step_01(ctx: Context) -> Result:
    return Result(tuple(evaluate_ledger(probe.read_ledger(ctx.conn), known_migrations(ctx.migrations_root))))


def step_02(ctx: Context) -> Result:
    return Result(tuple(evaluate_role(probe.role_facts(ctx.conn), probe.write_probe(ctx.conn, AUDIT_EVENT_UPDATE_PROBE))))
