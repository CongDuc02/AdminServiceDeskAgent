"""Watermark chéo trải thân trang (B8c, PO 2026-10-13; thay dòng chữ ở tiêu đề của B8b — dễ cắt khi in hay chụp).

**Hình thức** — đúng kiểu "Watermark" của Word: một shape VML WordArt (`v:shape` kiểu `#_x0000_t136`, `v:textpath`) **neo trong tiêu đề**, xoay −45° (`rotation:315`), **căn giữa thân trang cả hai chiều** (tương đối với lề), nằm **sau** chữ
(`z-index` âm), tô xám bán trong suốt, không viền. Shape nằm trong một `w:r` của đoạn ĐẦU tiên của tiêu đề (không thêm đoạn, nên không đẩy nội dung tiêu đề xuống). Mỗi loại tiêu đề (mặc định, trang đầu, trang chẵn) có một shape;
tiêu đề "liên kết với phần trước" kế thừa bản đã có của phần đứng trước. Tiêu đề lặp ở mọi trang nên watermark ở **mọi trang**.

**Đã chứng minh với LibreOffice 25.2.3 trong image** (spike B8c): LibreOffice nhập shape VML này và xuất PDF đúng — chéo, giữa trang, sau chữ, nhạt; biến thể DrawingML (`wps:txbx` xoay) thì LibreOffice **bỏ qua góc xoay** (chữ nằm ngang) nên
không dùng. Trong PDF chữ watermark là **đường viền vẽ** (`pdftotext` không đọc ra chữ): kiểm "có watermark" ở PDF bằng pixel (`tests/test_watermark_render.py`), ở `.docx` bằng XML (`textpath string` đúng nguyên văn, đúng một shape mỗi tiêu đề).

**Không gỡ được** (00-domain.md, D-009) theo nghĩa của thiết kế: không có tham số nào tắt nó (xem `docx_fill`). Người nhận `.docx` vẫn xoá được shape trong Word — giới hạn có từ trước, không đổi ở B8c.
Màu, độ mờ, kích thước: hằng số bên dưới. **PO duyệt ảnh mẫu B8c (2026-10-13): giữ `#808080` / `.5`** — PO duyệt, chưa thử in/photo.
"""
from __future__ import annotations

import io
from xml.sax.saxutils import quoteattr

from docx import Document
from docx.oxml import parse_xml

WATERMARK_TEXT = "BẢN THỬ NGHIỆM — KHÔNG CÓ GIÁ TRỊ PHÁP LÝ"  # đúng nguyên văn AC-1.3 của 12-roadmap.md
FILL_COLOR = "#808080"  # PO duyệt ảnh mẫu B8c (2026-10-13); chưa thử in/photo
FILL_OPACITY = ".5"
WIDTH_PT = 640  # ≈ chiều chéo của thân trang A4 chiếu lên một trục, để chữ trải từ góc này sang góc kia của lề
HEIGHT_PT = 40
FONT_FAMILY = "Times New Roman"  # cùng họ font với mẫu; image ánh xạ sang Liberation Serif (ADR-036)

_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:v="urn:schemas-microsoft-com:vml" '
       'xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w10="urn:schemas-microsoft-com:office:word"')
_SHAPETYPE = ('<v:shapetype id="_x0000_t136" coordsize="21600,21600" o:spt="136" adj="10800" path="m@7,l@8,m@5,21600l@6,21600e">'
              '<v:formulas><v:f eqn="sum #0 0 10800"/><v:f eqn="prod #0 2 1"/><v:f eqn="sum 21600 0 @1"/><v:f eqn="sum 0 0 @2"/><v:f eqn="sum 21600 0 @3"/><v:f eqn="if @0 @3 0"/>'
              '<v:f eqn="if @0 21600 @1"/><v:f eqn="if @0 0 @2"/><v:f eqn="if @0 @4 21600"/><v:f eqn="mid @5 @6"/><v:f eqn="mid @8 @5"/><v:f eqn="mid @7 @8"/><v:f eqn="mid @6 @7"/><v:f eqn="sum @6 0 @5"/></v:formulas>'
              '<v:path textpathok="t" o:connecttype="custom" o:connectlocs="@9,0;@10,10800;@11,21600;@12,10800" o:connectangles="270,180,90,0"/><v:textpath on="t" fitshape="t"/>'
              '<v:handles><v:h position="#0,bottomRight" xrange="6629,14971"/></v:handles><o:lock v:ext="edit" text="t" shapetype="t"/></v:shapetype>')


def watermark_run_xml(serial: int) -> str:
    """Một `w:r` mang shape watermark. `serial` làm `id` của shape duy nhất trong file (Word đặt `PowerPlusWaterMarkObject<số>`)."""
    style = (f"position:absolute;margin-left:0;margin-top:0;width:{WIDTH_PT}pt;height:{HEIGHT_PT}pt;rotation:315;z-index:-251658752;mso-position-horizontal:center;"
             "mso-position-horizontal-relative:margin;mso-position-vertical:center;mso-position-vertical-relative:margin")
    textpath_style = f"font-family:&quot;{FONT_FAMILY}&quot;;font-weight:bold;font-size:1pt"
    return (f"<w:r {_NS}><w:rPr><w:noProof/></w:rPr><w:pict>{_SHAPETYPE}"
            f'<v:shape id="PowerPlusWaterMarkObject{serial}" o:spid="_x0000_s{2048 + serial}" type="#_x0000_t136" style="{style}" o:allowincell="f" fillcolor="{FILL_COLOR}" stroked="f">'
            f'<v:fill opacity="{FILL_OPACITY}"/><v:textpath style="{textpath_style}" string={quoteattr(WATERMARK_TEXT)}/><w10:wrap anchorx="margin" anchory="margin"/></v:shape></w:pict></w:r>')


def add_watermark(docx: bytes) -> bytes:
    """Thêm shape watermark vào mọi tiêu đề của file (mặc định, trang đầu, trang chẵn)."""
    document = Document(io.BytesIO(docx))
    even_odd = document.settings.odd_and_even_pages_header_footer
    serial = 0
    for index, section in enumerate(document.sections):
        headers = [section.header]
        if section.different_first_page_header_footer:
            headers.append(section.first_page_header)
        if even_odd:
            headers.append(section.even_page_header)
        for header in headers:
            if header.is_linked_to_previous:
                if index > 0:
                    continue  # kế thừa phần trước — phần trước đã có watermark
                header.is_linked_to_previous = False  # phần đầu chưa có tiêu đề: tạo một cái
            serial += 1
            paragraph = header.paragraphs[0]._p
            run = parse_xml(watermark_run_xml(serial))
            position = 1 if paragraph.pPr is not None else 0  # sau `w:pPr` nếu có: chạy đầu tiên của đoạn đầu tiên
            paragraph.insert(position, run)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()
