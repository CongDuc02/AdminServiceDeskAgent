#!/usr/bin/env bash
# BO-19 — chạy bước 0 (step0.sql) bằng user mặc định của Render. Do PO chạy, từ gốc repo, trong Git Bash.
# Cách dùng và trình tự: tools/db-bootstrap/README.md.
#
# - Credential bo19_admin đọc từ file NGOÀI repo — mặc định ~/.bo19/admin.env, biến BO19_RENDER_ADMIN_DSN
#   (PO, 2026-10-04) — vào biến môi trường; không trên dòng lệnh, không in ra. Không đọc .env của repo.
# - Verifier vào container qua --env-file; file verifier bị xoá khi bước 0 đạt.
# - psql chạy trong image ghim của ADR-033, --single-transaction: hỏng một câu thì không còn gì.
set -euo pipefail

ADMIN_ENV_FILE="${ADMIN_ENV_FILE:-$HOME/.bo19/admin.env}"
VERIFIER_FILE="${VERIFIER_FILE:-${TMP:-${TEMP:-/tmp}}/bo19-step0/verifiers.env}"
IMAGE="pgvector/pgvector:0.8.1-pg18@sha256:508c5290cda481d4f5f846446a26e9c1b804766828a394a5861de1b348a18b4c"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

[ -f "$ADMIN_ENV_FILE" ] || { echo "không thấy $ADMIN_ENV_FILE"; exit 2; }
case "$(cd "$(dirname "$ADMIN_ENV_FILE")" && pwd)/" in
  "$REPO"/*) echo "file credential bo19_admin nằm trong repo — chuyển ra ngoài, mặc định ~/.bo19/admin.env"; exit 2 ;;
esac
[ -f "$VERIFIER_FILE" ] || { echo "không thấy file verifier — cần role_secrets.py generate trước"; exit 2; }
BO19_STEP0_ADMIN_DSN="$(grep '^BO19_RENDER_ADMIN_DSN=' "$ADMIN_ENV_FILE" | head -n1 | cut -d= -f2- | tr -d '\r' | sed 's/^"//; s/"$//')"
[ -n "$BO19_STEP0_ADMIN_DSN" ] || { echo "thiếu BO19_RENDER_ADMIN_DSN trong $ADMIN_ENV_FILE"; exit 2; }
export BO19_STEP0_ADMIN_DSN
# docker là chương trình Windows: đường dẫn kiểu MSYS (/tmp/...) phải đổi sang dạng Windows. MSYS_NO_PATHCONV
# tắt việc đổi tự động — cần cho lệnh sh -c bên dưới — nên đổi tay bằng cygpath. Linux không có cygpath: giữ nguyên.
VERIFIER_FILE_DOCKER="$(cygpath -w "$VERIFIER_FILE" 2>/dev/null || printf '%s' "$VERIFIER_FILE")"

MSYS_NO_PATHCONV=1 docker run --rm -i \
  -e BO19_STEP0_ADMIN_DSN --env-file "$VERIFIER_FILE_DOCKER" \
  "$IMAGE" \
  sh -c 'psql "$BO19_STEP0_ADMIN_DSN" -X -q --single-transaction -v ON_ERROR_STOP=1 -f -' \
  < "$HERE/step0.sql"

rm -f "$VERIFIER_FILE"
echo "bước 0 đạt — đã xoá file verifier"
