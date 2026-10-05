"""Seed dữ liệu GIẢ có nhãn cho DB local — `employee`, `employee_role`, `employee_credential`, `employee_permission_grant`.

KHÔNG phải mã ứng dụng, không vào image (Dockerfile chỉ chép backend/ và frontend/); KHÔNG phải data migration — `migrate_main` áp mọi file
`backend/migrations/data/` kể cả trên Render, mà PO chốt (2026-10-05) seed chỉ chạy trên Postgres local; Render seed ở mốc riêng của Sprint 2, sau A-062.
Nơi đặt, cách chạy, vị trí file mật khẩu: tools/seed-dev/README.md. Tài liệu: mục AuthZ của 09-security.md, mục Vận hành seed của 12-roadmap.md.

Luật thao tác (CLAUDE.md, mục Luật thao tác):
  - credential `bo19_migrator` đọc từ biến môi trường BO19_MIGRATOR_DATABASE_URL — không bao giờ trên dòng lệnh, không in, không ghi vào đâu;
  - mật khẩu giả sinh ngẫu nhiên, ghi vào MỘT file gitignored cục bộ, **không in** ra màn hình hay log;
  - người triển khai (kể cả Claude) không đọc file mật khẩu.

Chặn chạy nhầm (không có cờ nào tắt được hai chặn đầu):
  - host của DSN phải là localhost, 127.0.0.1, ::1 hoặc socket Unix; host khác (container, CI) phải khai rõ bằng --allow-host TÊN;
  - role đang nối phải là bo19_migrator;
  - `operating_mode` hiện hành của DB phải là NON_PRODUCTION.

Mọi lệnh chạy trong MỘT giao dịch. Chạy lại không đổi gì đã có (mã nhân viên và id cố định); --reset-passwords đặt lại mật khẩu của mọi tài khoản giả.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import secrets
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import psycopg
from psycopg.conninfo import conninfo_to_dict

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "src"))  # tool chạy ngoài image: dùng lại hasher của api — một mã, không viết hai lần (ADR-034)

from bo19.api.auth.hasher import ALGORITHM, PasswordVerifier  # noqa: E402
from bo19.config.settings import load_settings  # noqa: E402
from bo19.startup.checks_security import ARGON2_MIN_MEMORY_COST_KIB, ARGON2_MIN_TIME_COST, ARGON2_PARALLELISM  # noqa: E402

ENV_DSN = "BO19_MIGRATOR_DATABASE_URL"
DEFAULT_PASSWORDS_FILE = REPO / "tools" / "seed-dev" / "out" / "passwords.local.txt"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
SOURCE = "SEED_DEV_FAKE"  # cột employee.source — nhãn giả (D-002: provenance)
NAMESPACE = uuid.UUID("b0190000-0000-4000-8000-5eed00de0001")  # id cố định theo mã → chạy lại không sinh dòng mới


@dataclass(frozen=True)
class FakeEmployee:
    code: str
    full_name: str
    role: str


# Mã bắt đầu GIA- và tên mang "(GIẢ)": nhìn là biết giả. Không có `national_id`, `date_of_birth`: không dữ liệu nào trông như thật.
EMPLOYEES: tuple[FakeEmployee, ...] = (
    FakeEmployee("GIA-0001", "NHÂN VIÊN GIẢ 01 (GIẢ)", "EMPLOYEE"),
    FakeEmployee("GIA-0002", "NHÂN VIÊN GIẢ 02 (GIẢ)", "EMPLOYEE"),
    FakeEmployee("GIA-0003", "NHÂN VIÊN GIẢ 03 (GIẢ)", "EMPLOYEE"),
    FakeEmployee("GIA-0101", "CÁN BỘ HÀNH CHÍNH GIẢ 01 (GIẢ)", "ADMIN_OFFICER"),
    FakeEmployee("GIA-0102", "CÁN BỘ HÀNH CHÍNH GIẢ 02 (GIẢ)", "ADMIN_OFFICER"),
)
# Một dòng cấp lẻ — lớp 1 của ADR-023: KHÔNG cấp `operating_mode.change` cho ai.
SIGNER_CODE, SIGNER_PERMISSION = "GIA-0101", "document.sign"


class SeedRefused(Exception):
    """Dừng có chủ đích — thông điệp là mã, không mang DSN hay host."""


@dataclass(frozen=True)
class SeedReport:
    employees_created: int
    credentials_written: int
    roles_created: int
    grants_created: int


def employee_id(code: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, code)


def check_host(dsn: str, allow_hosts: frozenset[str]) -> None:
    host = conninfo_to_dict(dsn).get("host") or ""
    hosts = [h for h in host.split(",") if h] or [""]  # host rỗng → socket Unix của máy này
    for h in hosts:
        if h and not h.startswith("/") and h not in LOCAL_HOSTS and h not in allow_hosts:
            raise SeedRefused("SEED_HOST_NOT_LOCAL")


def read_passwords(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "\t" in line:
            code, password = line.split("\t", 1)
            out[code] = password
    return out


def write_passwords(path: Path, passwords: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "# Mật khẩu của TÀI KHOẢN GIẢ (dữ liệu giả) — file cục bộ, gitignored, không in ra, người triển khai không đọc. Mỗi dòng: mã<TAB>mật khẩu\n"
    body += "".join(f"{c}\t{p}\n" for c, p in sorted(passwords.items()))
    path.write_text(body, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass  # Windows: quyền file kế thừa từ thư mục người dùng


def default_verifier() -> PasswordVerifier:
    s = load_settings(os.environ)
    if s.argon2_time_cost < ARGON2_MIN_TIME_COST or s.argon2_memory_cost_kib < ARGON2_MIN_MEMORY_COST_KIB or s.argon2_parallelism != ARGON2_PARALLELISM:
        raise SeedRefused("SEED_ARGON2_PARAMS_BELOW_WV16")  # WV-16 không ngoại lệ theo môi trường — seed không hash bằng tham số yếu hơn ứng dụng chịu chạy
    return PasswordVerifier.from_settings(s)


def run(dsn: str, passwords_file: Path = DEFAULT_PASSWORDS_FILE, *, allow_hosts: frozenset[str] = frozenset(), reset_passwords: bool = False,
        verifier: PasswordVerifier | None = None, out: IO[str] | None = None) -> SeedReport:
    out = out or sys.stdout
    check_host(dsn, allow_hosts)
    verifier = verifier or default_verifier()
    now = dt.datetime.now(dt.timezone.utc)
    with psycopg.connect(dsn, connect_timeout=10, application_name="bo19-seed-dev") as conn:
        if conn.execute("select current_user").fetchone()[0] != "bo19_migrator":
            raise SeedRefused("SEED_ROLE_NOT_MIGRATOR")
        mode = conn.execute("select to_mode from operating_mode_change where effective_at <= now() order by effective_at desc limit 1").fetchone()
        if mode and mode[0] != "NON_PRODUCTION":
            raise SeedRefused("SEED_DB_NOT_NON_PRODUCTION")  # dữ liệu giả không vào DB đang ở PRODUCTION (D-009)

        employees = roles = grants = 0
        for e in EMPLOYEES:
            employees += conn.execute(
                "insert into employee (id, employee_code, full_name, department_code, department_name, job_title, contract_type, "
                "employment_start_date, source, synced_at) values (%s, %s, %s, 'GIA-PB', 'Phòng giả (dữ liệu giả)', 'Chức danh giả', 'INDEFINITE', "
                "date '2020-01-01', %s, %s) on conflict do nothing", (employee_id(e.code), e.code, e.full_name, SOURCE, now)).rowcount
            roles += conn.execute("insert into employee_role (employee_id, role_code) values (%s, %s) on conflict do nothing",
                                  (employee_id(e.code), e.role)).rowcount
        grants += conn.execute(
            "insert into employee_permission_grant (id, employee_id, permission_code) values (%s, %s, %s) on conflict do nothing",
            (uuid.uuid5(NAMESPACE, f"grant:{SIGNER_CODE}:{SIGNER_PERMISSION}"), employee_id(SIGNER_CODE), SIGNER_PERMISSION)).rowcount

        have = {r[0] for r in conn.execute("select employee_id from employee_credential where employee_id = any(%s)",
                                           ([employee_id(e.code) for e in EMPLOYEES],))}
        passwords = read_passwords(passwords_file)
        written = 0
        for e in EMPLOYEES:
            eid = employee_id(e.code)
            if eid in have and not reset_passwords:
                continue
            password = secrets.token_urlsafe(18)
            conn.execute(
                "insert into employee_credential (employee_id, password_hash, hash_algorithm) values (%s, %s, %s) "
                "on conflict (employee_id) do update set password_hash = excluded.password_hash, hash_algorithm = excluded.hash_algorithm, updated_at = now()",
                (eid, verifier.hash(password), ALGORITHM))
            passwords[e.code] = password
            written += 1
        if written:
            write_passwords(passwords_file, passwords)  # ghi file TRƯỚC khi commit: mất file sau khi đã commit hash là mất mật khẩu
        conn.commit()
    print(f"SEED_DEV_DONE employees_created={employees} roles_created={roles} grants_created={grants} credentials_written={written}", file=out)
    if written:
        print(f"SEED_DEV_PASSWORDS_FILE {passwords_file}", file=out)  # đường dẫn — không phải nội dung
    return SeedReport(employees, written, roles, grants)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Seed dữ liệu giả có nhãn cho DB local (tools/seed-dev/README.md)")
    ap.add_argument("--passwords-file", type=Path, default=DEFAULT_PASSWORDS_FILE, help="file ghi mật khẩu giả (gitignored)")
    ap.add_argument("--allow-host", action="append", default=[], metavar="TÊN", help="cho phép host không phải localhost (ví dụ tên container trong CI)")
    ap.add_argument("--reset-passwords", action="store_true", help="đặt lại mật khẩu của mọi tài khoản giả")
    args = ap.parse_args(argv)
    dsn = os.environ.get(ENV_DSN, "").strip()
    if not dsn:
        print(f"SEED_DEV_CONFIG_MISSING {ENV_DSN}", file=sys.stderr)
        return 2
    try:
        run(dsn, args.passwords_file, allow_hosts=frozenset(args.allow_host), reset_passwords=args.reset_passwords)
    except SeedRefused as e:
        print(f"SEED_DEV_REFUSED {e}", file=sys.stderr)
        return 1
    except psycopg.Error as e:
        print(f"SEED_DEV_DB_ERROR {type(e).__name__}", file=sys.stderr)  # chỉ kiểu lỗi: thông điệp có thể mang host
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
