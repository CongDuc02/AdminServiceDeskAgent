"""Fixture PostgreSQL dùng chung cho test tích hợp từ B3: MỘT database mới đã `migrate_main` xong, tạo lúc cần, xoá khi tiến trình thoát.

Cần BO19_TEST_PG_SUPERUSER_DSN (PostgreSQL mới, ví dụ pgvector/pgvector:0.8.1-pg18 — ADR-033); không có thì `get_db()` trả None và
test tích hợp tự bỏ qua. Mỗi test dùng mã nhân viên và `scope` riêng (uuid) nên chia sẻ một DB không làm hai test đè lên nhau.
Test B2 (`test_ac_1_7`, ...) có DB riêng của chúng — không đổi.
"""
from __future__ import annotations

import atexit
import datetime as dt
import itertools
import logging
import os
import random
import shutil
import tempfile
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from bo19.entrypoints import migrate_main as mm

SUPERUSER_DSN = os.environ.get("BO19_TEST_PG_SUPERUSER_DSN")
_db: "PgDb | None" = None


class PgDb:
    def __init__(self, su_dsn: str) -> None:
        self.su = su_dsn
        self.name = f"t_b3_{uuid.uuid4().hex[:8]}"
        with psycopg.connect(su_dsn, autocommit=True) as c:
            for r in ("bo19_migrator", "bo19_app"):
                if not c.execute("select 1 from pg_roles where rolname = %s", (r,)).fetchone():
                    c.execute(f"create role {r} login")
            c.execute(f"create database {self.name}")
        with psycopg.connect(self.dsn(), autocommit=True) as c:  # bước 0 như runbook, bằng role mạnh
            c.execute("create extension if not exists vector")
            c.execute("grant create on schema public to bo19_migrator")
        self._root = Path(tempfile.mkdtemp(prefix="bo19-b3-"))
        shutil.copytree(mm.MIGRATIONS_DIR, self._root / "m")
        logging.disable(logging.CRITICAL)
        try:
            mm.run(self.dsn("bo19_migrator"), self._root / "m")
        finally:
            logging.disable(logging.NOTSET)

    def dsn(self, user: str | None = None) -> str:
        d = {**conninfo_to_dict(self.su), "dbname": self.name}
        if user:
            d["user"] = user
            d.pop("password", None)
        return make_conninfo(**d)

    def connect(self, user: str | None = None, **kw) -> psycopg.Connection:
        return psycopg.connect(self.dsn(user), **kw)

    def drop(self) -> None:
        with psycopg.connect(self.su, autocommit=True) as c:
            c.execute(f"drop database if exists {self.name} with (force)")
        shutil.rmtree(self._root, ignore_errors=True)

    # --- dữ liệu mẫu — luôn là dữ liệu giả của test, ghi bằng bo19_migrator (chủ bảng) -------------------------------------------

    def make_employee(self, code: str | None = None, *, active: bool = True, roles: tuple[str, ...] = (),
                      grants: tuple[str, ...] = (), password_hash: str | None = None, revoked_grants: tuple[str, ...] = ()) -> tuple[uuid.UUID, str]:
        employee_id, code = uuid.uuid4(), code or f"T{uuid.uuid4().hex[:10]}"
        with self.connect("bo19_migrator") as c:
            c.execute(
                "insert into employee (id, employee_code, full_name, department_code, department_name, job_title, contract_type, "
                "employment_start_date, is_active, source, synced_at) values (%s, %s, %s, 'PB-GIA', 'Phòng giả', 'Chức danh giả', 'INDEFINITE', "
                "date '2020-01-01', %s, 'TEST_FAKE', %s)",
                (employee_id, code, f"NGƯỜI GIẢ {code}", active, dt.datetime.now(dt.timezone.utc)))
            for r in roles:
                c.execute("insert into employee_role (employee_id, role_code) values (%s, %s)", (employee_id, r))
            for g in grants:
                c.execute("insert into employee_permission_grant (id, employee_id, permission_code) values (%s, %s, %s)",
                          (uuid.uuid4(), employee_id, g))
            for g in revoked_grants:
                c.execute("insert into employee_permission_grant (id, employee_id, permission_code, granted_at, revoked_at) "
                          "values (%s, %s, %s, now() - interval '2 day', now() - interval '1 day')", (uuid.uuid4(), employee_id, g))
            if password_hash is not None:
                c.execute("insert into employee_credential (employee_id, password_hash) values (%s, %s)", (employee_id, password_hash))
        return employee_id, code

    def make_chat_session(self, employee_id: uuid.UUID) -> uuid.UUID:
        sid = uuid.uuid4()
        with self.connect("bo19_migrator") as c:
            c.execute("insert into chat_session (id, employee_id) values (%s, %s)", (sid, employee_id))
        return sid

    def make_request(self) -> uuid.UUID:
        """Một dòng `request` tối thiểu cho khoá ngoại của `llm_usage` — superuser, tắt kiểm khoá ngoại (như `set_operating_mode` của test_ac_1_7): fixture không cần dựng loại yêu cầu."""
        rid = uuid.uuid4()
        with self.connect(autocommit=True) as c:
            c.execute("set session_replication_role = replica")
            c.execute("insert into request (id, request_type_code, status, created_by_employee_id, beneficiary_employee_id) values (%s, 'WORK_CONFIRMATION', 'DRAFT', %s, %s)",
                      (rid, uuid.uuid4(), uuid.uuid4()))
        return rid

    def usage_rows(self, **owner) -> list[tuple]:
        """Các dòng `llm_usage` của một chủ budget: (call_name, model_tier, prompt_module_version, input, output, reasoning, outcome, trace_id)."""
        (col, value), = owner.items()
        with self.connect("bo19_migrator") as c:
            return c.execute(f"select call_name, model_tier, prompt_module_version, input_tokens, output_tokens, reasoning_tokens, outcome, trace_id "
                             f"from llm_usage where {col} = %s order by created_at, id", (value,)).fetchall()

    def usage_rows_ext(self, **owner) -> list[dict]:
        """Như `usage_rows` nhưng trả dict kèm ba cột B5: `estimated`, `duration_ms`, `provider_completion_ms` (và `outcome`, `input_tokens`, `output_tokens`)."""
        (col, value), = owner.items()
        with self.connect("bo19_migrator") as c:
            cur = c.execute(f"select call_name, outcome, input_tokens, output_tokens, reasoning_tokens, estimated, duration_ms, provider_completion_ms "
                            f"from llm_usage where {col} = %s order by created_at, id", (value,))
            names = [d.name for d in cur.description]
            return [dict(zip(names, r)) for r in cur.fetchall()]

    def set_active(self, employee_id: uuid.UUID, active: bool) -> None:
        with self.connect("bo19_migrator") as c:
            c.execute("update employee set is_active = %s where id = %s", (active, employee_id))


_ip_counter = itertools.count(random.randrange(1 << 15))


def unique_ip() -> str:
    """Một IPv4 thuộc dải 198.18.0.0/15 (dành cho benchmark, RFC 2544 — không bao giờ là IP thật) chưa dùng ở lần chạy này: mỗi test một `scope` rate limit riêng."""
    n = next(_ip_counter)
    return f"198.18.{(n >> 8) & 255}.{n & 255}"


def get_db() -> "PgDb | None":
    global _db
    if SUPERUSER_DSN is None:
        return None
    if _db is None:
        _db = PgDb(SUPERUSER_DSN)
        atexit.register(_db.drop)
    return _db
