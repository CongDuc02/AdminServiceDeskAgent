# syntax=docker/dockerfile:1
# BO-19 — image chung (ADR-015). Bản S2 của Spike 1: CHỈ giai đoạn 2 của đặc tả ở mục Đặc tả Dockerfile
# của docs/design/06-structure.md. Chưa có: giai đoạn build client, LibreOffice, công cụ liệt kê font,
# fonts/ — thêm ở S5 và track build Sprint 1.
FROM python:3.11-slim@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

# User hệ thống không đặc quyền — tiến trình không bao giờ chạy bằng root (PO, 2026-10-04).
RUN groupadd --system bo19 \
 && useradd --system --gid bo19 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin bo19

WORKDIR /app
COPY backend/requirements-linux.lock ./
# ADR-030 — lock sinh bằng uv pip compile, có hash; không phụ thuộc dev.
RUN pip install --no-deps --require-hashes -r requirements-linux.lock

COPY backend/ ./
USER bo19
CMD ["python", "-m", "bo19.entrypoints.api_main"]
