"""Dữ liệu thử cho test của `rendering` và tool render (B8b) — **mẫu `.docx` GIẢ, có nhãn giả**: không phải mẫu thật của tổ chức (mẫu thật là mốc M1.1, do Product Owner soạn).

`build_template` dựng một file Word thật bằng `python-docx`: Times New Roman (tên mà mẫu thật sẽ khai — ADR-036), tiếng Việt đủ dấu, biến `{{ ... }}` ở thân văn bản, tiêu đề và chân trang.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import unittest
import os

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt

FAKE_LABEL = "MẪU GIẢ — chỉ để thử, không phải mẫu của tổ chức"
FONT = "Times New Roman"

# Tiếng Việt đủ dấu: mọi nguyên âm có dấu thanh và dấu mũ/móc, chữ Đ/đ — dùng làm giá trị và để đo ngắt dòng.
VIETNAMESE = "Nguyễn Thị Hương Giang đã công tác tại Phòng Hành chính — Quản trị từ ngày 01/01/2020; quyền hạn được giao theo văn bản số 123/QĐ-GIẢ."


def build_template(*, header_text: str | None = "{{ co_quan }}", footer_text: str | None = "Trang — {{ noi_nhan }}", extra_paragraphs: tuple[str, ...] = (),
                   font: str = FONT, two_sections: bool = False, properties: dict[str, str] | None = None) -> bytes:
    """`properties`: thuộc tính tài liệu của mẫu (`author`, `last_modified_by`, `title`, `subject`, …) — để thử rằng tên người soạn mẫu không lọt vào PDF (B9a)."""
    document = Document()
    for name, value in (properties or {}).items():
        setattr(document.core_properties, name, value)
    for style in ("Normal", "Header", "Footer"):
        s = document.styles[style]
        s.font.name = font
        s.font.size = Pt(13)
        rpr = s.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            rfonts.set(qn(attr), font)
    document.add_paragraph(FAKE_LABEL)
    title = document.add_paragraph("{{ tieu_de }}")
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.runs[0].bold = True
    document.add_paragraph("Họ và tên: {{ ho_ten }}")
    document.add_paragraph("{{ noi_dung }}")
    for text in extra_paragraphs:
        document.add_paragraph(text)
    if header_text is not None:
        document.sections[0].header.paragraphs[0].text = header_text
    if footer_text is not None:
        document.sections[0].footer.paragraphs[0].text = footer_text
    if two_sections:
        from docx.enum.section import WD_SECTION
        document.add_section(WD_SECTION.NEW_PAGE)
        document.add_paragraph("Phần hai — {{ ho_ten }}")
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


DECLARED = ("co_quan", "noi_nhan", "tieu_de", "ho_ten", "noi_dung")
VALUES = {"co_quan": "CÔNG TY GIẢ", "noi_nhan": "Lưu: VT", "tieu_de": "GIẤY XÁC NHẬN GIẢ", "ho_ten": "Nguyễn Thị Hương Giang", "noi_dung": VIETNAMESE}


def docx_text(docx: bytes) -> str:
    """Toàn bộ chữ của file: thân văn bản, tiêu đề, chân trang (mọi phần)."""
    document = Document(io.BytesIO(docx))
    out = [p.text for p in document.paragraphs]
    for section in document.sections:
        for part in (section.header, section.first_page_header, section.even_page_header, section.footer):
            out.extend(p.text for p in part.paragraphs)
    return "\n".join(out)


def docx_props(docx: bytes):
    """`core_properties` của file (python-docx): `subject`, `author`, `last_modified_by`, `title`."""
    return Document(io.BytesIO(docx)).core_properties


def watermark_count(docx: bytes) -> int:
    """Số shape watermark (`v:shape` kiểu WordArt mang đúng chữ AC-1.3) ở mọi phần tiêu đề của file — kiểm "có watermark trong file" ở mức `.docx` (M5)."""
    import zipfile
    from bo19.tool_layer.rendering.watermark import WATERMARK_TEXT
    zf = zipfile.ZipFile(io.BytesIO(docx))
    return sum(zf.read(n).decode("utf-8").count(f'string="{WATERMARK_TEXT}"') for n in zf.namelist() if n.startswith("word/header"))


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def require_tool(testcase_cls_or_none, tool: str) -> None:
    """Thiếu công cụ: bỏ qua test — TRỪ khi `BO19_REQUIRE_SOFFICE=1` (CI), khi đó là LỖI (như `BO19_REQUIRE_S3`): CI không được âm thầm bỏ qua việc chứng minh `soffice` và font trong image thật."""
    if have(tool):
        return
    if os.environ.get("BO19_REQUIRE_SOFFICE") == "1":
        raise AssertionError(f"BO19_REQUIRE_SOFFICE=1 nhưng thiếu `{tool}`")
    raise unittest.SkipTest(f"cần `{tool}` (chạy trong image target test)")


def pdf_text(pdf: bytes) -> str:
    out = subprocess.run(["pdftotext", "-layout", "-", "-"], input=pdf, capture_output=True, timeout=60, check=True)
    return out.stdout.decode("utf-8")


def pdfinfo_fields(pdf: bytes) -> dict[str, str]:
    """Các trường `Khoá: giá trị` của `pdfinfo` (poppler) — công cụ CHUẨN, độc lập với mã của dự án (ADR-038). Trường vắng thì không có khoá."""
    out = _pdfinfo(pdf)
    fields = {}
    for line in out.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def pdfinfo_xmp(pdf: bytes) -> str:
    return _pdfinfo(pdf, "-meta")


def _pdfinfo(pdf: bytes, *flags: str) -> str:
    """`pdfinfo` cần đọc ngẫu nhiên nên không nhận ống dẫn: ghi ra tệp tạm."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "x.pdf")
        with open(path, "wb") as f:
            f.write(pdf)
        return subprocess.run(["pdfinfo", "-enc", "UTF-8", *flags, path], capture_output=True, timeout=60, check=True).stdout.decode("utf-8")


def pdf_fonts(pdf: bytes) -> list[str]:
    """Tên font NHÚNG trong PDF (`pdffonts`): cột `name` của từng dòng sau hai dòng đầu."""
    out = subprocess.run(["pdffonts", "-"], input=pdf, capture_output=True, timeout=60, check=True).stdout.decode("utf-8").splitlines()[2:]
    return [line.split()[0] for line in out if line.strip()]
