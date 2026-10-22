#!/usr/bin/env python3
"""Tài khoản GIẢ có thời hạn trên Render để đo `combined_main` (O1-6, A-095) — NGOẠI LỆ của cổng 2.7 (PO, 2026-10-21; `docs/design/12-roadmap.md`, hàng 2.7).

KHÔNG phải mã ứng dụng, không vào image. Chạy trong image `bo19-runtime` (có `psycopg` và hasher của `api`) — máy Windows của dự án không có `psycopg`:

    docker run --rm --env-file <file-env> -v "${PWD}\\tools:/tools" bo19-runtime \\
        python /tools/render-probes/render_probe_accounts.py seed --allow-host <host-ngoài-của-DB-Render> --confirm-gate-2-7-exception

(`tools/` gắn đọc-ghi: công cụ ghi file mật khẩu và giờ seed vào `tools/render-probes/out/`, thư mục gitignored.)

`<file-env>` chỉ có `BO19_MIGRATOR_DATABASE_URL` (credential `bo19_migrator`, đọc từ biến môi trường — không bao giờ trên dòng lệnh, không in).

Lệnh con:
  seed      dựng 2–3 tài khoản giả `DO-0001`… (vai trò `EMPLOYEE`, tên có "(GIẢ)"), mật khẩu ngẫu nhiên GHI vào out/probe_passwords.txt — KHÔNG in; ghi giờ seed và hạn (mặc định 72 giờ, tối đa 72) vào out/probe_window.json
  usage     số dòng `llm_usage` từ lúc seed — để theo dõi trần 20 lời gọi Groq của phép đo
  teardown  THU HỒI ngay sau đo: xoá credential, vai trò và quyền lẻ; đặt `is_active = false`, `source = 'RENDER_PROBE_REVOKED'`; thử xoá hẳn `employee`. Ghi giờ xoá; xoá file mật khẩu

**Nói thẳng về "xoá":** `audit_event`, `decision_record`, `chat_session`, `request`… có khoá ngoại tới `employee` và `audit_event` chỉ thêm, không xoá — nên khi tài khoản đã tạo dòng nào đó, `employee` KHÔNG xoá được (teardown báo rõ). Phần xoá được và đủ để không ai đăng nhập lại là credential + vai trò + `is_active`.

Chặn chạy nhầm (không cờ nào tắt chúng):
  - phải khai `--allow-host` đúng host của DSN VÀ `--confirm-gate-2-7-exception` — Render không phải localhost nên `seed_dev` từ chối; công cụ này là đường duy nhất, có chủ ý và có thời hạn;
  - role đang nối phải là `bo19_migrator`; `operating_mode` hiện hành phải là NON_PRODUCTION;
  - tham số argon2 của cấu hình không thấp hơn WV-16 (cùng luật của seed);
  - hết hạn (quá `expires_at`) thì `seed` từ chối chạy lại — chỉ `teardown` còn chạy.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import secrets
import sys
import uuid
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

REPO = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("PROBE_OUT", str(REPO / "tools" / "render-probes" / "out")))
ENV_DSN = "BO19_MIGRATOR_DATABASE_URL"
PASSWORDS = "probe_passwords.txt"
WINDOW = "probe_window.json"
MAX_HOURS = 72
MAX_ACCOUNTS = 3
SOURCE = "RENDER_PROBE_FAKE"
REVOKED = "RENDER_PROBE_REVOKED"
NAMESPACE = uuid.UUID("b0190000-0000-4000-8000-5eed00de0002")  # khác của seed-dev: không đụng id của tài khoản local


def _seed_dev():
    spec = importlib.util.spec_from_file_location("seed_dev_for_probe", REPO / "tools" / "seed-dev" / "seed_dev.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("seed_dev_for_probe", mod)
    spec.loader.exec_module(mod)
    return mod


class ProbeRefused(Exception):
    """Lý do từ chối, chỉ là một mã (không chứa DSN hay giá trị)."""


def codes(count: int, first: int = 1) -> list[str]:
    return [f"DO-{i:04d}" for i in range(first, first + count)]


def employee_id(code: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"employee:{code}")


def check_host(dsn: str, allow_host: str) -> None:
    """Render không phải localhost: host của DSN phải đúng bằng `--allow-host` (không dấu phẩy, không socket)."""
    host = conninfo_to_dict(dsn).get("host") or ""
    if not allow_host or host != allow_host:
        raise ProbeRefused("PROBE_HOST_NOT_ALLOWED")


def read_window(out: Path) -> dict | None:
    p = out / WINDOW
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def write_window(out: Path, data: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / WINDOW).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _connect(dsn: str, *, allow_host: str) -> psycopg.Connection:
    check_host(dsn, allow_host)
    conn = psycopg.connect(dsn, connect_timeout=15, application_name="bo19-render-probe-accounts")
    if conn.execute("select current_user").fetchone()[0] != "bo19_migrator":
        conn.close()
        raise ProbeRefused("PROBE_ROLE_NOT_MIGRATOR")
    mode = conn.execute("select to_mode from operating_mode_change where effective_at <= now() order by effective_at desc limit 1").fetchone()
    if mode and mode[0] != "NON_PRODUCTION":
        conn.close()
        raise ProbeRefused("PROBE_DB_NOT_NON_PRODUCTION")
    return conn


def seed(dsn: str, *, allow_host: str, confirmed: bool, count: int, hours: int, first: int = 1, out: Path = OUT, now: dt.datetime | None = None, verifier=None, echo=print) -> dict:
    if not confirmed:
        raise ProbeRefused("PROBE_EXCEPTION_NOT_CONFIRMED")
    if not 1 <= count <= MAX_ACCOUNTS or not 1 <= hours <= MAX_HOURS or not 1 <= first <= 99:
        raise ProbeRefused("PROBE_LIMITS")
    now = now or dt.datetime.now(dt.timezone.utc)
    window = read_window(out)
    if window and window.get("torn_down_at") is None and dt.datetime.fromisoformat(window["expires_at"]) < now:
        raise ProbeRefused("PROBE_WINDOW_EXPIRED")  # hết hạn mà chưa thu hồi: chỉ teardown
    sd = _seed_dev()
    verifier = verifier or sd.default_verifier()
    with _connect(dsn, allow_host=allow_host) as conn:
        created = 0
        passwords: dict[str, str] = {}
        for code in codes(count, first):
            eid = employee_id(code)
            created += conn.execute(
                "insert into employee (id, employee_code, full_name, department_code, department_name, job_title, contract_type, employment_start_date, source, synced_at) "
                "values (%s, %s, %s, 'DO-PB', 'Phòng đo (dữ liệu giả)', 'Chức danh giả', 'INDEFINITE', date '2020-01-01', %s, %s) on conflict (id) do update "
                "set is_active = true, source = excluded.source", (eid, code, f"NGƯỜI ĐO {code[-2:]} (GIẢ)", SOURCE, now)).rowcount
            conn.execute("insert into employee_role (employee_id, role_code) values (%s, 'EMPLOYEE') on conflict do nothing", (eid,))
            password = secrets.token_urlsafe(18)
            conn.execute("insert into employee_credential (employee_id, password_hash, hash_algorithm) values (%s, %s, %s) "
                         "on conflict (employee_id) do update set password_hash = excluded.password_hash, hash_algorithm = excluded.hash_algorithm, updated_at = now()",
                         (eid, verifier.hash(password), sd.ALGORITHM))
            passwords[code] = password
        sd.write_passwords(out / PASSWORDS, passwords)  # ghi file TRƯỚC khi commit: mất file sau khi đã commit hash là mất mật khẩu
        data = {"seeded_at": now.isoformat(timespec="seconds"), "expires_at": (now + dt.timedelta(hours=hours)).isoformat(timespec="seconds"), "accounts": codes(count, first), "torn_down_at": None}
        if window:  # seed lần hai trong CÙNG ngoại lệ (ví dụ thêm DO-0004 cho bước 4b sau khi thu hồi ba tài khoản đầu): giữ giờ seed đầu, mọi tài khoản đã seed, và các trường template
            data["first_seeded_at"] = window.get("first_seeded_at") or window["seeded_at"]
            data["accounts_all"] = sorted(set(window.get("accounts_all") or window.get("accounts") or []) | set(data["accounts"]))
            for key in ("template_installed_at", "template_version_id", "template_retired_at"):
                if key in window:
                    data[key] = window[key]
        else:
            data["first_seeded_at"], data["accounts_all"] = data["seeded_at"], list(data["accounts"])
        write_window(out, data)
        conn.commit()
    echo(f"PROBE_SEEDED accounts={count} seeded_at={data['seeded_at']} expires_at={data['expires_at']}")  # không in mật khẩu
    echo(f"PROBE_PASSWORDS_FILE {out / PASSWORDS}")  # đường dẫn, không phải nội dung
    return data


def usage(dsn: str, *, allow_host: str, out: Path = OUT, echo=print) -> int:
    window = read_window(out)
    if not window:
        raise ProbeRefused("PROBE_NO_WINDOW")
    with _connect(dsn, allow_host=allow_host) as conn:
        since = window.get("first_seeded_at") or window["seeded_at"]  # trần Groq tính cho CẢ ngoại lệ, kể từ lần seed đầu
        n = conn.execute("select count(*) from llm_usage where created_at >= %s::timestamptz", (since,)).fetchone()[0]
    echo(f"PROBE_LLM_USAGE since={since} rows={n}")
    return n


def teardown(dsn: str, *, allow_host: str, out: Path = OUT, now: dt.datetime | None = None, echo=print) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    window = read_window(out) or {"accounts": codes(MAX_ACCOUNTS)}
    ids = [employee_id(c) for c in (window.get("accounts_all") or window["accounts"])]  # thu hồi mọi tài khoản đã seed trong ngoại lệ
    with _connect(dsn, allow_host=allow_host) as conn:
        creds = conn.execute("delete from employee_credential where employee_id = any(%s)", (ids,)).rowcount
        roles = conn.execute("delete from employee_role where employee_id = any(%s)", (ids,)).rowcount
        grants = conn.execute("delete from employee_permission_grant where employee_id = any(%s)", (ids,)).rowcount
        conn.execute("update employee set is_active = false, source = %s where id = any(%s)", (REVOKED, ids))
        deleted = kept = 0
        for eid in ids:
            try:
                with conn.transaction():  # savepoint: khoá ngoại tới dòng đã tạo làm lệnh này hỏng mà không làm hỏng cả teardown
                    deleted += conn.execute("delete from employee where id = %s", (eid,)).rowcount
            except psycopg.errors.ForeignKeyViolation:
                kept += 1
        conn.commit()
    pw = out / PASSWORDS
    if pw.exists():
        pw.unlink()
    window.update({"torn_down_at": now.isoformat(timespec="seconds")})
    write_window(out, window)
    summary = {"credentials_deleted": creds, "roles_deleted": roles, "grants_deleted": grants, "employees_deleted": deleted, "employees_kept_revoked": kept, "torn_down_at": window["torn_down_at"]}
    echo("PROBE_TORN_DOWN " + " ".join(f"{k}={v}" for k, v in summary.items()))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("seed", "usage", "teardown"):
        p = sub.add_parser(name)
        p.add_argument("--allow-host", required=True, help="host của DSN Render (khai tường minh; Render không phải localhost)")
        if name == "seed":
            p.add_argument("--confirm-gate-2-7-exception", action="store_true", help="xác nhận đây là ngoại lệ có thời hạn của cổng 2.7")
            p.add_argument("--count", type=int, default=3)
            p.add_argument("--first", type=int, default=1, help="số thứ tự tài khoản đầu (DO-000N); 4 để thêm DO-0004 sau khi đã thu hồi ba tài khoản đầu")
            p.add_argument("--hours", type=int, default=MAX_HOURS)
    a = ap.parse_args()
    dsn = os.environ.get(ENV_DSN, "")
    if not dsn:
        print(f"THIẾU {ENV_DSN}", file=sys.stderr)
        return 2
    try:
        if a.cmd == "seed":
            seed(dsn, allow_host=a.allow_host, confirmed=a.confirm_gate_2_7_exception, count=a.count, hours=a.hours, first=a.first)
        elif a.cmd == "usage":
            usage(dsn, allow_host=a.allow_host)
        else:
            teardown(dsn, allow_host=a.allow_host)
    except ProbeRefused as e:
        print(f"PROBE_REFUSED {e}", file=sys.stderr)
        return 1
    except psycopg.Error as e:
        print(f"PROBE_DB_ERROR {type(e).__name__}", file=sys.stderr)  # chỉ tên lớp lỗi: thông điệp có thể mang host
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
