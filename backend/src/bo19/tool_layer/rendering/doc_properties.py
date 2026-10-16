"""Thuộc tính tài liệu của `.docx` mà LibreOffice chuyển sang metadata PDF (B9a / M5, ADR-038).

LibreOffice 25.2.3.2 chuyển `subject` → `/Subject` và `author` → `/Author` của từ điển `Info` của PDF (số đo của B9a — A-096, chưa có tài liệu gốc về ánh xạ này; mục 14.3.3 của ISO 32000-1 ở
`docs/reference/pdf-document-information-dictionary.md` chỉ nói `Subject` và `Author` là mục tuỳ chọn của `Info`).

- **`subject`**: chuỗi watermark ở `NON_PRODUCTION` — để PDF có chuỗi đọc được bằng máy (`pdfinfo`), vì watermark trong PDF là đường vẽ. `PRODUCTION`: **xoá** `subject`, để PDF không bao giờ mang chuỗi
  watermark do thuộc tính của mẫu.
- **`author`, `lastModifiedBy`**: ghi đè bằng tên hệ thống ở **cả hai chế độ** — mẫu thật có thể mang tên người soạn, và `author` đi thẳng vào `/Author` của PDF phát hành (PO, 2026-10-13).
- **`title` và mọi thuộc tính khác: không chạm** — `title` thuộc mốc M1.1 (PO).

Hàm thuần trên byte `.docx`: không DB, không đồng hồ.
"""
from __future__ import annotations

import io

from docx import Document

SYSTEM_AUTHOR = "Admin Service Desk Agent"  # tên hệ thống, trung lập — không phải tên một người


def apply_properties(docx: bytes, watermark_text: str | None) -> bytes:
    document = Document(io.BytesIO(docx))
    props = document.core_properties
    props.author = SYSTEM_AUTHOR
    props.last_modified_by = SYSTEM_AUTHOR
    props.subject = watermark_text if watermark_text is not None else ""
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()
