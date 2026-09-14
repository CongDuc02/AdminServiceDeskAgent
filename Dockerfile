# Đặc tả Dockerfile — xem 06-structure.md:6.2
# Một image cho mọi tiến trình (api, worker, cron, migrate).
# Giai đoạn 1: client-build (node) — sinh openapi.d.ts và build Vite.
# Giai đoạn 2: runtime (python) — cài LibreOffice headless + fonts, COPY backend + static.
# Chưa ghim digest <node-image>, <python-image> — chốt ở BUILD MODE.
