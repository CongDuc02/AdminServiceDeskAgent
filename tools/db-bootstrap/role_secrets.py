"""Bước 0 của ADR-017 — sinh mật khẩu và SCRAM-SHA-256 verifier cho bo19_migrator, bo19_app.

KHÔNG phải mã ứng dụng — không vào image. Cách dùng và trình tự: tools/db-bootstrap/README.md.
Không in giá trị bí mật nào; chỉ in tên biến. Chỉ dùng thư viện chuẩn.

  generate      Đọc host[:cổng] ngoài (BO19_RENDER_EXTERNAL_HOST) và tên database (BO19_RENDER_DB_NAME) từ
                .env của repo — hai giá trị không bí mật. Sinh mật khẩu mới cho hai role; ghi hai DSN vào
                .env (thay dòng cũ tại chỗ, hoặc thêm); ghi hai verifier ra một file env NGOÀI repo để
                step0.sh đưa vào container. Máy chủ chỉ nhận verifier (PO, 2026-10-04).
                KHÔNG đọc credential bo19_admin: nó ở ~/.bo19/admin.env, chỉ step0.sh đọc. .env của repo
                còn dòng BO19_RENDER_ADMIN_DSN thì dừng — credential đó không được nằm trong repo.
  retarget      Ghi lại host[:cổng] và tên database của BO19_RENDER_MIGRATOR_DSN, BO19_RENDER_APP_DSN theo
                BO19_RENDER_EXTERNAL_HOST, BO19_RENDER_DB_NAME — GIỮ NGUYÊN credential. Dùng khi hai giá trị đó
                sai lúc generate mà bước 0 đã chạy: verifier trên máy chủ vẫn khớp mật khẩu cũ. Chạy lại
                internal-dsn sau đó.
  internal-dsn  Dựng DSN của bo19_app trên host NỘI BỘ của Render, cho BO19_DATABASE_URL của Web Service
                (mục Biến môi trường theo môi trường của 11-ops.md): lấy credential từ BO19_RENDER_APP_DSN,
                host[:cổng] từ BO19_RENDER_INTERNAL_HOST. Ghi vào BO19_RENDER_APP_INTERNAL_DSN.

Mật khẩu: 40 ký tự chữ và số — không cần SASLprep, không cần mã hoá trong URL.
Verifier: SCRAM-SHA-256$<iter>:<salt>$<StoredKey>:<ServerKey>, iter 4096, salt 16 byte.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import re
import secrets
import string
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

REPO = Path(__file__).resolve().parents[2]
DEFAULT_VERIFIER_FILE = Path(tempfile.gettempdir()) / "bo19-step0" / "verifiers.env"
ROLES = (("bo19_migrator", "BO19_RENDER_MIGRATOR_DSN", "BO19_STEP0_MIGRATOR_VERIFIER"),
         ("bo19_app", "BO19_RENDER_APP_DSN", "BO19_STEP0_APP_VERIFIER"))


def scram(password: str, iters: int = 4096) -> str:
    salt = secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iters)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    b = lambda x: base64.b64encode(x).decode()  # noqa: E731
    return "SCRAM-SHA-256$%d:%s$%s:%s" % (iters, b(salt), b(hashlib.sha256(client_key).digest()), b(server_key))


def new_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(40))


def read_env(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")


def get_var(lines: list[str], name: str) -> str | None:
    found = [l.split("=", 1)[1].strip().strip('"') for l in lines if l.startswith(name + "=")]
    if len(found) > 1:
        sys.exit(f"{name} xuất hiện {len(found)} lần trong .env — dừng")
    return found[0] if found else None


def set_var(lines: list[str], name: str, value: str) -> None:
    idx = [k for k, l in enumerate(lines) if l.startswith(name + "=")]
    if idx:
        lines[idx[0]] = f"{name}={value}"
    else:
        if lines and lines[-1] == "":
            lines.pop()
        lines += [f"{name}={value}", ""]


def _is_host_port(v: str) -> bool:
    host, _, port = v.partition(":")
    return bool(host) and not any(c in host for c in "/@?# ") and (not port or port.isdigit())


def write_atomic(path: Path, lines: list[str]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    # Windows từ chối thay file khi chương trình khác đang mở nó trong chốc lát (gặp 2026-10-04) — thử lại.
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 9:
                sys.exit(f"không thay được {path.name} — đóng chương trình đang mở file rồi chạy lại; dừng")
            time.sleep(0.5)


def generate(env: Path, verifier_file: Path, sslmode: str) -> None:
    if verifier_file.resolve().is_relative_to(REPO):
        sys.exit("file verifier phải nằm ngoài repo — dừng")
    lines = read_env(env)
    if any(l.startswith("BO19_RENDER_ADMIN_DSN=") for l in lines):
        sys.exit("BO19_RENDER_ADMIN_DSN còn trong .env của repo — chuyển sang ~/.bo19/admin.env rồi xoá dòng đó; dừng")
    host_port, db = endpoint(lines)
    verifiers = []
    for role, var, vvar in ROLES:
        pw = new_password()
        set_var(lines, var, urlunsplit(("postgresql", f"{role}:{pw}@{host_port}", f"/{db}", f"sslmode={sslmode}", "")))
        verifiers.append(f"{vvar}={scram(pw)}")
    verifier_file.parent.mkdir(parents=True, exist_ok=True)
    verifier_file.write_text("\n".join(verifiers) + "\n", encoding="utf-8", newline="\n")
    write_atomic(env, lines)
    print("đã ghi .env:", ", ".join(v for _, v, _ in ROLES))
    print("đã ghi verifier:", ", ".join(v for _, _, v in ROLES), "→", verifier_file.as_posix())


def endpoint(lines: list[str]) -> tuple[str, str]:
    host_port, db = get_var(lines, "BO19_RENDER_EXTERNAL_HOST"), get_var(lines, "BO19_RENDER_DB_NAME")
    if not host_port or not db:
        sys.exit("cần BO19_RENDER_EXTERNAL_HOST và BO19_RENDER_DB_NAME trong .env — dừng")
    if not _is_host_port(host_port) or not re.fullmatch(r"[A-Za-z0-9_]+", db):
        sys.exit("BO19_RENDER_EXTERNAL_HOST chỉ là host hoặc host:cổng, BO19_RENDER_DB_NAME chỉ là tên — dừng")
    return host_port, db


def retarget(env: Path) -> None:
    lines = read_env(env)
    host_port, db = endpoint(lines)
    for role, var, _ in ROLES:
        cur = get_var(lines, var)
        if not cur:
            sys.exit(f"thiếu {var} trong .env — chạy generate; dừng")
        u = urlsplit(cur)
        cred = u.netloc.rsplit("@", 1)[0]
        if not cred.startswith(role + ":"):
            sys.exit(f"{var} không mang credential {role} — dừng")
        set_var(lines, var, urlunsplit((u.scheme, f"{cred}@{host_port}", f"/{db}", u.query, "")))
    write_atomic(env, lines)
    print("đã ghi lại host và database, giữ credential:", ", ".join(v for _, v, _ in ROLES))


def internal_dsn(env: Path) -> None:
    lines = read_env(env)
    app, host = get_var(lines, "BO19_RENDER_APP_DSN"), get_var(lines, "BO19_RENDER_INTERNAL_HOST")
    if not app or not host:
        sys.exit("cần cả BO19_RENDER_APP_DSN và BO19_RENDER_INTERNAL_HOST trong .env — dừng")
    if "/" in host or "@" in host:
        sys.exit("BO19_RENDER_INTERNAL_HOST chỉ là host hoặc host:cổng — dừng")
    u = urlsplit(app)
    cred = u.netloc.rsplit("@", 1)[0]
    if not cred.startswith("bo19_app:"):
        sys.exit("BO19_RENDER_APP_DSN không mang credential bo19_app — dừng")
    set_var(lines, "BO19_RENDER_APP_INTERNAL_DSN", urlunsplit((u.scheme, f"{cred}@{host}", u.path, "sslmode=require", "")))
    write_atomic(env, lines)
    print("đã ghi .env: BO19_RENDER_APP_INTERNAL_DSN")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # console Windows mặc định cp1252 — thông báo là tiếng Việt
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["generate", "retarget", "internal-dsn"])
    ap.add_argument("--env-file", type=Path, default=REPO / ".env")
    ap.add_argument("--verifier-file", type=Path, default=DEFAULT_VERIFIER_FILE)
    ap.add_argument("--sslmode", default="require", help="chỉ đổi khi thử trên container local không TLS")
    a = ap.parse_args()
    if a.command == "generate":
        generate(a.env_file, a.verifier_file, a.sslmode)
    elif a.command == "retarget":
        retarget(a.env_file)
    else:
        internal_dsn(a.env_file)


if __name__ == "__main__":
    main()
