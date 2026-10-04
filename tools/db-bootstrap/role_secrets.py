"""Bước 0 của ADR-017 — sinh mật khẩu và SCRAM-SHA-256 verifier cho bo19_migrator, bo19_app.

KHÔNG phải mã ứng dụng — không vào image. Cách dùng và trình tự: tools/db-bootstrap/README.md.
Không in giá trị bí mật nào; chỉ in tên biến. Chỉ dùng thư viện chuẩn.

  generate      Đọc DSN của user mặc định Render (BO19_RENDER_ADMIN_DSN) từ file .env để lấy host, cổng,
                tên database. Sinh mật khẩu mới cho hai role; ghi hai DSN vào .env (thay dòng cũ tại chỗ,
                hoặc thêm); ghi hai verifier ra một file env NGOÀI repo để step0.sh đưa vào container.
                Máy chủ chỉ nhận verifier — mật khẩu thô không rời máy này (PO, 2026-10-04).
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
import secrets
import string
import sys
import tempfile
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


def write_atomic(path: Path, lines: list[str]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def generate(env: Path, verifier_file: Path, sslmode: str) -> None:
    if verifier_file.resolve().is_relative_to(REPO):
        sys.exit("file verifier phải nằm ngoài repo — dừng")
    lines = read_env(env)
    admin = get_var(lines, "BO19_RENDER_ADMIN_DSN")
    if not admin:
        sys.exit("thiếu BO19_RENDER_ADMIN_DSN trong .env — dừng")
    u = urlsplit(admin)
    if u.scheme not in ("postgres", "postgresql") or "@" not in u.netloc or not u.path.strip("/"):
        sys.exit("BO19_RENDER_ADMIN_DSN không phải URL postgresql://user:pass@host/db — dừng")
    host_port = u.netloc.rsplit("@", 1)[1]
    verifiers = []
    for role, var, vvar in ROLES:
        pw = new_password()
        set_var(lines, var, urlunsplit((u.scheme, f"{role}:{pw}@{host_port}", u.path, f"sslmode={sslmode}", "")))
        verifiers.append(f"{vvar}={scram(pw)}")
    verifier_file.parent.mkdir(parents=True, exist_ok=True)
    verifier_file.write_text("\n".join(verifiers) + "\n", encoding="utf-8", newline="\n")
    write_atomic(env, lines)
    print("đã ghi .env:", ", ".join(v for _, v, _ in ROLES))
    print("đã ghi verifier:", ", ".join(v for _, _, v in ROLES), "→", verifier_file.as_posix())


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
    ap.add_argument("command", choices=["generate", "internal-dsn"])
    ap.add_argument("--env-file", type=Path, default=REPO / ".env")
    ap.add_argument("--verifier-file", type=Path, default=DEFAULT_VERIFIER_FILE)
    ap.add_argument("--sslmode", default="require", help="chỉ đổi khi thử trên container local không TLS")
    a = ap.parse_args()
    if a.command == "generate":
        generate(a.env_file, a.verifier_file, a.sslmode)
    else:
        internal_dsn(a.env_file)


if __name__ == "__main__":
    main()
