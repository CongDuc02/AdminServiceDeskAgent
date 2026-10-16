"""Phép kiểm watermark của bản render sau UAT (M5, B9a — PO 2026-10-13; ADR-038; thủ tục: mục 18 của docs/design/11-ops.md). KHÔNG phải mã ứng dụng, không vào image runtime.

Mỗi dòng `document_render` phải đạt **ba chân độc lập**:
  1. DB       — `NON_PRODUCTION` thì `watermark_text` có mặt và bằng chuỗi của AC-1.3; `PRODUCTION` thì `NULL`;
  2. Checksum — sha256 byte PDF tải từ `object_storage` bằng `stored_object_commit.checksum_sha256` (lệch thì dừng chân 3 của dòng đó: metadata đọc từ byte khác với byte đã commit thì vô nghĩa);
  3. Metadata — `pdfinfo` (poppler — công cụ chuẩn, độc lập với mã của dự án) đọc `Subject` và so với `watermark_text` của dòng; `PRODUCTION` thì `Subject` không được mang chuỗi watermark.
Chân phụ: `Author` của PDF bằng tên hệ thống (tên người soạn mẫu không lọt vào PDF phát hành).

**Chạy trong image `test`** (có `pdfinfo`); runtime không đọc lại PDF và image `runtime` không có poppler.

Credential **không** qua tham số dòng lệnh: biến môi trường `BO19_DATABASE_URL` (role `bo19_app`, chỉ `SELECT`) và `BO19_OBJECT_STORAGE_ENDPOINT_URL`, `_BUCKET`, `_ACCESS_KEY_ID`, `_SECRET_ACCESS_KEY` (chỉ đọc object), nạp bằng
`docker run --env-file <file ngoài repo>`. Script không in credential, không in nội dung văn bản hay giá trị slot — chỉ id, loại bản, chế độ và mã trượt.

Mã thoát: `0` mọi dòng đạt · `1` có dòng trượt · `2` KHÔNG kiểm được (thiếu `pdfinfo`, thiếu biến, không kết nối DB hay storage) — mã 2 không bao giờ in "đạt".
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend" / "src"))

import psycopg  # noqa: E402

from bo19.object_storage import ObjectStorage, ObjectStorageConfig, StorageError  # noqa: E402
from bo19.tool_layer.rendering.doc_properties import SYSTEM_AUTHOR  # noqa: E402
from bo19.tool_layer.rendering.watermark import WATERMARK_TEXT  # noqa: E402

EXIT_OK, EXIT_FAILED, EXIT_CANNOT_CHECK = 0, 1, 2
PDFINFO_TIMEOUT_S = 60

DB_WATERMARK_MISSING = "DB_WATERMARK_MISSING"
DB_WATERMARK_MISMATCH = "DB_WATERMARK_MISMATCH"
DB_WATERMARK_UNEXPECTED = "DB_WATERMARK_UNEXPECTED"
CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
PDF_UNAVAILABLE = "PDF_UNAVAILABLE"
PDF_UNREADABLE = "PDF_UNREADABLE"
PDF_SUBJECT_MISSING = "PDF_SUBJECT_MISSING"
PDF_SUBJECT_MISMATCH = "PDF_SUBJECT_MISMATCH"
PDF_SUBJECT_UNEXPECTED = "PDF_SUBJECT_UNEXPECTED"
PDF_AUTHOR_NOT_NEUTRAL = "PDF_AUTHOR_NOT_NEUTRAL"


class CannotCheck(Exception):
    """Không thực hiện được phép kiểm (mã thoát 2) — không phải "đạt" và không phải "trượt"."""


def pdfinfo(pdf: bytes) -> dict[str, str]:
    """Các trường `Khoá: giá trị` của `pdfinfo`. `pdfinfo` vắng → `CannotCheck`; không đọc được file → `PdfUnreadable`."""
    if shutil.which("pdfinfo") is None:
        raise CannotCheck("PDFINFO_MISSING")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "x.pdf")
        with open(path, "wb") as f:
            f.write(pdf)
        try:
            proc = subprocess.run(["pdfinfo", "-enc", "UTF-8", path], capture_output=True, timeout=PDFINFO_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise PdfUnreadable from None
    if proc.returncode != 0:
        raise PdfUnreadable
    fields: dict[str, str] = {}
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


class PdfUnreadable(Exception):
    pass


def audit_render(*, operating_mode: str, db_watermark_text: str | None, expected_checksum: bytes, pdf: bytes | None) -> list[str]:
    """Mã trượt của MỘT dòng `document_render` (rỗng = đạt cả ba chân và chân phụ). `pdf = None` nghĩa là không tải được byte."""
    codes: list[str] = []
    # Chân 1 — DB
    if operating_mode == "NON_PRODUCTION":
        if not db_watermark_text:
            codes.append(DB_WATERMARK_MISSING)
        elif db_watermark_text != WATERMARK_TEXT:
            codes.append(DB_WATERMARK_MISMATCH)
    elif db_watermark_text is not None:
        codes.append(DB_WATERMARK_UNEXPECTED)
    # Chân 2 — checksum
    if pdf is None:
        codes.append(PDF_UNAVAILABLE)
        return codes
    if hashlib.sha256(pdf).digest() != bytes(expected_checksum):
        codes.append(CHECKSUM_MISMATCH)
        return codes  # byte khác byte đã commit: không đọc metadata của nó
    # Chân 3 — metadata
    try:
        info = pdfinfo(pdf)
    except PdfUnreadable:
        codes.append(PDF_UNREADABLE)
        return codes
    subject = info.get("Subject")
    if operating_mode == "NON_PRODUCTION":
        if subject is None:
            codes.append(PDF_SUBJECT_MISSING)
        elif subject != db_watermark_text:
            codes.append(PDF_SUBJECT_MISMATCH)
    elif subject is not None and WATERMARK_TEXT in subject:
        codes.append(PDF_SUBJECT_UNEXPECTED)
    if info.get("Author") != SYSTEM_AUTHOR:
        codes.append(PDF_AUTHOR_NOT_NEUTRAL)
    return codes


@dataclass(frozen=True)
class Row:
    render_id: object
    document_id: object
    render_kind: str
    operating_mode: str
    watermark_text: str | None
    pdf_object_key: str
    checksum: bytes


def fetch_rows(conn: psycopg.Connection, *, document_id: str | None, limit: int | None) -> list[Row]:
    sql = ("SELECT r.id, r.document_id, r.render_kind, r.operating_mode, r.watermark_text, r.pdf_object_key, c.checksum_sha256 "
           "FROM document_render r JOIN stored_object_commit c ON c.object_key = r.pdf_object_key ")
    args: list[object] = []
    if document_id is not None:
        sql += "WHERE r.document_id = %s "
        args.append(document_id)
    sql += "ORDER BY r.created_at, r.id"
    if limit is not None:
        sql += " LIMIT %s"
        args.append(limit)
    return [Row(*r) for r in conn.execute(sql, args).fetchall()]


def audit_all(conn: psycopg.Connection, storage: ObjectStorage, *, document_id: str | None = None, limit: int | None = None) -> tuple[int, list[tuple[Row, list[str]]]]:
    rows = fetch_rows(conn, document_id=document_id, limit=limit)
    failed: list[tuple[Row, list[str]]] = []
    for row in rows:
        try:
            pdf: bytes | None = storage.get(row.pdf_object_key)
        except StorageError:
            pdf = None
        codes = audit_render(operating_mode=row.operating_mode, db_watermark_text=row.watermark_text, expected_checksum=row.checksum, pdf=pdf)
        if codes:
            failed.append((row, codes))
    return len(rows), failed


def _storage_from_env(env: Mapping[str, str]) -> ObjectStorage:
    names = ("BO19_OBJECT_STORAGE_ENDPOINT_URL", "BO19_OBJECT_STORAGE_BUCKET", "BO19_OBJECT_STORAGE_ACCESS_KEY_ID", "BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY")
    missing = [n for n in names if not env.get(n)]
    if missing:
        raise CannotCheck("MISSING_ENV:" + ",".join(missing))  # chỉ TÊN biến
    return ObjectStorage(ObjectStorageConfig(endpoint_url=env[names[0]], bucket=env[names[1]], access_key_id=env[names[2]], secret_access_key=env[names[3]],
                                             region=env.get("BO19_OBJECT_STORAGE_REGION") or "us-east-1"))


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None, out: TextIO | None = None) -> int:
    env = os.environ if env is None else env
    out = out or sys.stdout
    parser = argparse.ArgumentParser(description="Kiểm watermark của bản render sau UAT (ba chân: DB, checksum, metadata PDF).")
    parser.add_argument("--document-id", help="chỉ kiểm các bản render của document này (uuid)")
    parser.add_argument("--limit", type=int, help="chỉ kiểm N dòng đầu (theo thời điểm tạo)")
    args = parser.parse_args(argv)
    try:
        if shutil.which("pdfinfo") is None:
            raise CannotCheck("PDFINFO_MISSING")
        dsn = env.get("BO19_DATABASE_URL")
        if not dsn:
            raise CannotCheck("MISSING_ENV:BO19_DATABASE_URL")
        storage = _storage_from_env(env)
        try:
            with psycopg.connect(dsn, connect_timeout=15) as conn:
                checked, failed = audit_all(conn, storage, document_id=args.document_id, limit=args.limit)
        except psycopg.Error:
            raise CannotCheck("DATABASE_ERROR") from None
    except CannotCheck as e:
        print(f"KHÔNG KIỂM ĐƯỢC: {e}. Đây không phải kết quả đạt.", file=out)
        return EXIT_CANNOT_CHECK
    for row, codes in failed:
        print(f"TRƯỢT render_id={row.render_id} document_id={row.document_id} loại={row.render_kind} chế_độ={row.operating_mode} mã={','.join(codes)}", file=out)
    print(f"Đã kiểm {checked} bản render: {checked - len(failed)} đạt, {len(failed)} trượt.", file=out)
    return EXIT_FAILED if failed else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
