# syntax=docker/dockerfile:1
# BO-19 — image chung (ADR-015). Giai đoạn 2 của đặc tả ở mục Đặc tả Dockerfile của docs/design/06-structure.md, thêm ở B8b:
# LibreOffice Writer không giao diện, fontconfig, font Liberation Serif và quy tắc ánh xạ "Times New Roman" (ADR-036).
# B10a: giai đoạn build client (Node LTS ghim theo digest, ADR-042) — bản build chép vào /app/static ở `base`, đúng đặc tả ở mục Đặc tả Dockerfile của 06-structure.md (06-structure.md mục 10.4).
#
# THỨ TỰ STAGE LÀ MỘT LUẬT (PO, 2026-10-13): `runtime` LUÔN là stage CUỐI. `docker build` không `--target` — cách Render dựng mặc định —
# phải ra image runtime, không bao giờ ra `test`. CI dựng không `--target` rồi kiểm image không có gói dev và không có poppler.
#   client-build — Node: `npm ci` + `npm run build` (tsc + vite) ra /client/dist. Chỉ kết quả (dist) được chép sang `base`; Node, npm và node_modules KHÔNG lọt vào image triển khai (check_runtime_image.sh kiểm)
#   base    — mọi thứ image triển khai cần
#   test    — base + công cụ test (poppler-utils, lock dev). KHÔNG BAO GIỜ triển khai; test chạy bằng mount mã vào (docker run -v)
#   runtime — base + user không đặc quyền + lệnh khởi động. STAGE CUỐI.
FROM node:24-trixie-slim@sha256:a6155384446670e9719bdc4fd0ebe4d4b29fb32a8d6aa523da3547a6cfbcf22c AS client-build
WORKDIR /client
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    HOME=/tmp

# HOME=/tmp: user bo19 không có thư mục nhà (--no-create-home); fontconfig và LibreOffice (dconf) cần một chỗ ghi cache. Mỗi lần chuyển đổi còn dùng hồ sơ và HOME tạm riêng (tool_layer.rendering.convert).
# User hệ thống không đặc quyền — tiến trình không bao giờ chạy bằng root (PO, 2026-10-04).
RUN groupadd --system bo19 \
 && useradd --system --gid bo19 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin bo19

# LibreOffice Writer không giao diện + fontconfig (ADR-015). Tên gói: docs/reference/debian-trixie-goi-libreoffice-fontconfig-poppler.md.
# Không ghim phiên bản gói apt: bản cũ biến mất khỏi kho khi có bản bảo mật (image nền ghim theo digest, gói apt thì không — rủi ro ghi ở báo cáo B8b).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libreoffice-writer-nogui fontconfig \
 && rm -rf /var/lib/apt/lists/*

# A-058, ADR-036: bốn kiểu chữ Liberation Serif 2.1.5 (SIL OFL 1.1) kèm LICENSE; sha256 ghim bằng test (tests/test_fonts_files.py).
COPY fonts/LiberationSerif-Regular.ttf fonts/LiberationSerif-Bold.ttf fonts/LiberationSerif-Italic.ttf fonts/LiberationSerif-BoldItalic.ttf fonts/LICENSE /usr/local/share/fonts/bo19/
COPY fonts/50-bo19-times-new-roman.conf /etc/fonts/conf.d/50-bo19-times-new-roman.conf
RUN fc-cache -f

WORKDIR /app
COPY backend/requirements-linux.lock ./
# ADR-030 — lock sinh bằng uv pip compile, có hash; không phụ thuộc dev.
RUN pip install --no-deps --require-hashes -r requirements-linux.lock

COPY backend/ ./
COPY --from=client-build /client/dist /app/static

FROM base AS test
# Chỉ để test trong image thật (B8b): đọc chữ và tên font từ PDF. Không vào image triển khai.
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils \
 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements-dev-linux.lock ./
RUN pip install --no-deps --require-hashes -r requirements-dev-linux.lock
USER bo19

# STAGE CUỐI — đừng thêm stage nào sau dòng này.
FROM base AS runtime
USER bo19
CMD ["python", "-m", "bo19.entrypoints.api_main"]
