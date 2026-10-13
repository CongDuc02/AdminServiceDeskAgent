#!/usr/bin/env bash
# Kiểm image `runtime` — cái mà Render dựng khi `docker build` KHÔNG có `--target` (B8b; PO 2026-10-13, Q1).
# KHÔNG phải mã ứng dụng, không vào image.
#
# Dùng:  tools/image-checks/check_runtime_image.sh <image>      (image dựng bằng `docker build -t <image> .`, không `--target`)
#
# Đỏ (thoát mã khác 0) nếu image dựng không `--target`:
#   1. có gói PHÁT TRIỂN — gói nằm trong requirements-dev-linux.lock mà không nằm trong requirements-linux.lock (import-linter, grimp, rich, pygments, …), hoặc `pytest`;
#   2. có poppler (`pdftotext`, `pdffonts`) — công cụ của target `test`;
#   3. thiếu thứ image triển khai CẦN: `soffice`, `fc-match`, bốn file Liberation Serif, quy tắc fontconfig;
#   4. không chạy bằng user `bo19`, hoặc lệnh khởi động không phải `api_main`.
# Đặt stage `test` làm stage cuối của Dockerfile thì bước 1 và 2 đỏ (CI kiểm điều đó bằng đột biến — B8b).
set -euo pipefail

IMAGE="${1:?cần tên image}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fail=0
say() { echo "  $*"; }

lock_names() { grep -oE '^[A-Za-z0-9_.-]+==' "$1" | sed 's/==$//' | tr 'A-Z_' 'a-z-' | sort -u; }
DEV_ONLY="$(comm -13 <(lock_names "$ROOT/backend/requirements-linux.lock") <(lock_names "$ROOT/backend/requirements-dev-linux.lock") | sort -u)"
DEV_ONLY="$(printf '%s\npytest\n' "$DEV_ONLY" | sort -u)"

echo "== $IMAGE: gói Python phát triển không được có mặt"
INSTALLED="$(docker run --rm --entrypoint python "$IMAGE" -m pip list --format=freeze | cut -d= -f1 | tr 'A-Z_' 'a-z-' | sort -u)"
LEAKED="$(comm -12 <(printf '%s\n' "$DEV_ONLY") <(printf '%s\n' "$INSTALLED") | tr '\n' ' ')"
if [ -n "${LEAKED// /}" ]; then say "ĐỎ — image có gói phát triển: $LEAKED"; fail=1; else say "đạt ($(printf '%s\n' "$DEV_ONLY" | wc -l | tr -d ' ') gói phát triển, không gói nào có mặt)"; fi

echo "== $IMAGE: công cụ của target test không được có mặt"
for tool in pdftotext pdffonts pytest lint-imports; do
  if docker run --rm --entrypoint sh "$IMAGE" -c "command -v $tool >/dev/null 2>&1"; then say "ĐỎ — image có \`$tool\`"; fail=1; else say "đạt — không có \`$tool\`"; fi
done

echo "== $IMAGE: thứ image triển khai cần"
for tool in soffice fc-match fc-list; do
  if docker run --rm --entrypoint sh "$IMAGE" -c "command -v $tool >/dev/null 2>&1"; then say "đạt — có \`$tool\`"; else say "ĐỎ — thiếu \`$tool\`"; fail=1; fi
done
for f in /usr/local/share/fonts/bo19/LiberationSerif-Regular.ttf /usr/local/share/fonts/bo19/LiberationSerif-Bold.ttf /usr/local/share/fonts/bo19/LiberationSerif-Italic.ttf \
         /usr/local/share/fonts/bo19/LiberationSerif-BoldItalic.ttf /usr/local/share/fonts/bo19/LICENSE /etc/fonts/conf.d/50-bo19-times-new-roman.conf; do
  if docker run --rm --entrypoint sh "$IMAGE" -c "test -s $f"; then say "đạt — có $f"; else say "ĐỎ — thiếu $f"; fail=1; fi
done

echo "== $IMAGE: user và lệnh khởi động"
USER_NAME="$(docker image inspect "$IMAGE" --format '{{.Config.User}}')"
CMD="$(docker image inspect "$IMAGE" --format '{{join .Config.Cmd " "}}')"
[ "$USER_NAME" = "bo19" ] && say "đạt — user bo19" || { say "ĐỎ — user là '$USER_NAME'"; fail=1; }
[ "$CMD" = "python -m bo19.entrypoints.api_main" ] && say "đạt — CMD $CMD" || { say "ĐỎ — CMD là '$CMD'"; fail=1; }

if [ "$fail" -ne 0 ]; then echo "KẾT QUẢ: ĐỎ"; exit 1; fi
echo "KẾT QUẢ: đạt"
