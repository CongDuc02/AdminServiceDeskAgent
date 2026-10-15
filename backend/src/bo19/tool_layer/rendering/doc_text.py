"""Chữ nhìn thấy được của một file `.docx` — thân văn bản, tiêu đề, chân trang, chú thích — mỗi đoạn một chuỗi (A-098: phép kiểm bản `FINAL` không còn dấu giữ chỗ).

Đọc XML trực tiếp, không dựng lại bằng `python-docx`: chữ của một đoạn có thể bị Word cắt qua nhiều `w:t` (run), nên nối mọi `w:t` trong cùng một `w:p` rồi mới so khuôn.
Không đọc nội dung ra ngoài hàm gọi — kết quả chỉ để so khuôn, không vào log hay lỗi.
"""
from __future__ import annotations

import html
import io
import re
import zipfile

_PARTS = re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$")
_PARAGRAPH = re.compile(r"<w:p[ >].*?</w:p>", re.DOTALL)
_TEXT = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.DOTALL)


def paragraph_texts(docx: bytes) -> list[str]:
    out: list[str] = []
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        for name in sorted(n for n in z.namelist() if _PARTS.match(n)):
            xml = z.read(name).decode("utf-8")
            for p in _PARAGRAPH.findall(xml):
                out.append("".join(html.unescape(t) for t in _TEXT.findall(p)))
    return out
