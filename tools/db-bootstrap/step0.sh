#!/usr/bin/env bash
# BO-19 — chạy bước 0 (step0.sql) bằng user mặc định của Render. Do PO chạy, từ gốc repo, trong Git Bash.
# Cách dùng và trình tự: tools/db-bootstrap/README.md.
#
# - DSN của bo19_admin đọc từ .env vào biến môi trường — không trên dòng lệnh, không in ra.
# - Verifier vào container qua --env-file; file verifier bị xoá khi bước 0 đạt.
# - psql chạy trong image ghim của ADR-033; --single-transaction: hỏng một câu thì không còn gì.
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
VERIFIER_FILE="${VERIFIER_FILE:-${TMP:-${TEMP:-/tmp}}/bo19-step0/verifiers.env}"
ADMIN_VAR="${ADMIN_VAR:-BO19_RENDER_ADMIN_DSN}"
IMAGE="pgvector/pgvector:0.8.1-pg18@sha256:508c5290cda481d4f5f846446a26e9c1b804766828a394a5861de1b348a18b4c"
HERE="$(cd "$(dirname "$0")" && pwd)"

[ -f "$ENV_FILE" ] || { echo "không thấy $ENV_FILE — chạy từ gốc repo"; exit 2; }
[ -f "$VERIFIER_FILE" ] || { echo "không thấy file verifier — chạy role_secrets.py generate trước"; exit 2; }
BO19_STEP0_ADMIN_DSN="$(grep "^${ADMIN_VAR}=" "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d '\r' | sed 's/^"//; s/"$//')"
[ -n "$BO19_STEP0_ADMIN_DSN" ] || { echo "thiếu $ADMIN_VAR trong $ENV_FILE"; exit 2; }
export BO19_STEP0_ADMIN_DSN

MSYS_NO_PATHCONV=1 docker run --rm -i \
  -e BO19_STEP0_ADMIN_DSN --env-file "$VERIFIER_FILE" \
  "$IMAGE" \
  sh -c 'psql "$BO19_STEP0_ADMIN_DSN" -X -q --single-transaction -v ON_ERROR_STOP=1 -f -' \
  < "$HERE/step0.sql"

rm -f "$VERIFIER_FILE"
echo "bước 0 đạt — đã xoá file verifier"
