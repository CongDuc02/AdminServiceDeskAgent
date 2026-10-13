#!/usr/bin/env bash
# Dựng SeaweedFS 4.47 (`weed server`) trong một container trên network Docker `ci` — object storage S3-compatible CHO TEST (B8a, ADR-031, ADR-037).
# KHÔNG phải mã ứng dụng, không vào image, không lên Render. Dùng chung cho CI và máy người triển khai.
#
# Dùng:  tools/object-storage-local/start.sh <file-env-ra>      # ghi endpoint và credential TEST ngẫu nhiên vào <file-env-ra> (chmod 600); in tên biến, không in giá trị
#        tools/object-storage-local/start.sh --stop             # dừng và xoá container
#
# - Binary tải từ bản phát hành 4.47, **kiểm sha256 ghim ở dưới** (docs/reference/seaweedfs-4.47-linux.md) — sai thì dừng, không chạy.
# - Cờ của ADR-031 (`weed server`, không `weed mini`; telemetry tắt; volume). Khác ADR-031 ở MỘT chỗ: trong container phải bind mọi giao diện của container để container khác trên network `ci` nối được;
#   cổng KHÔNG được publish ra máy chủ, nên vẫn không ra khỏi network `ci`.
# - Credential sinh ngẫu nhiên mỗi lần chạy, chỉ nằm trong file env ngoài repo; không đưa lên dòng lệnh của tiến trình khác.
set -euo pipefail

NAME="${BO19_S3_CONTAINER:-bo19-s3}"
NETWORK="${BO19_S3_NETWORK:-ci}"
IMAGE="${BO19_S3_IMAGE:-python:3.11-slim@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b}"  # cùng digest với CI và Dockerfile
VERSION=4.47
URL="https://github.com/seaweedfs/seaweedfs/releases/download/${VERSION}/linux_amd64.tar.gz"
SHA256=31fb804858885f9e7f18b6d3b1da09e824baac3e6a55b5a62c3c4c77e6ed6d7d
CACHE="${BO19_S3_CACHE:-${HOME}/.cache/bo19-seaweedfs-${VERSION}}"
export MSYS_NO_PATHCONV=1

if [ "${1:-}" = "--stop" ]; then
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  exit 0
fi
OUT="${1:?cần đường dẫn file env ra (ngoài repo)}"

mkdir -p "$CACHE"
if [ ! -x "$CACHE/weed" ]; then
  curl -sSfL -o "$CACHE/linux_amd64.tar.gz" "$URL"
  echo "$SHA256  $CACHE/linux_amd64.tar.gz" | sha256sum -c - >/dev/null || { echo "sha256 của SeaweedFS ${VERSION} KHÔNG khớp — dừng." >&2; rm -f "$CACHE/linux_amd64.tar.gz"; exit 1; }
  (cd "$CACHE" && tar -xzf linux_amd64.tar.gz weed)
  chmod +x "$CACHE/weed"
fi

ACCESS="bo19test$(openssl rand -hex 6)"
SECRET="$(openssl rand -hex 24)"
CONF="$(mktemp -d)"
cat > "$CONF/s3.json" <<EOF
{"identities":[{"name":"bo19_test","credentials":[{"accessKey":"$ACCESS","secretKey":"$SECRET"}],"actions":["Admin","Read","Write"]}]}
EOF

docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK" >/dev/null
docker rm -f "$NAME" >/dev/null 2>&1 || true
HOST_CACHE="$CACHE"; HOST_CONF="$CONF"
if command -v cygpath >/dev/null 2>&1; then HOST_CACHE="$(cygpath -w "$CACHE")"; HOST_CONF="$(cygpath -w "$CONF")"; fi
docker run -d --name "$NAME" --network "$NETWORK" -v "$HOST_CACHE/weed:/usr/local/bin/weed:ro" -v "$HOST_CONF:/conf:ro" "$IMAGE" \
  sh -c "mkdir -p /tmp/data && exec weed server -dir=/tmp/data -ip=$NAME -ip.bind=0.0.0.0 -filer -s3 -s3.config=/conf/s3.json -master.telemetry=false -master.volumeSizeLimitMB=64 -volume.max=200" >/dev/null

for _ in $(seq 1 60); do
  if docker exec "$NAME" python -c "import urllib.request,urllib.error
try: urllib.request.urlopen('http://127.0.0.1:8333/', timeout=2)
except urllib.error.HTTPError: pass" >/dev/null 2>&1; then READY=1; break; fi
  sleep 1
done
[ "${READY:-0}" = 1 ] || { echo "SeaweedFS không sẵn sàng sau 60 s." >&2; docker logs --tail 20 "$NAME" >&2; exit 1; }

umask 077
cat > "$OUT" <<EOF
BO19_TEST_S3_ENDPOINT=http://$NAME:8333
BO19_TEST_S3_ACCESS_KEY_ID=$ACCESS
BO19_TEST_S3_SECRET_ACCESS_KEY=$SECRET
EOF
echo "SeaweedFS ${VERSION} sẵn sàng. Đã ghi $OUT (BO19_TEST_S3_ENDPOINT, BO19_TEST_S3_ACCESS_KEY_ID, BO19_TEST_S3_SECRET_ACCESS_KEY)."
