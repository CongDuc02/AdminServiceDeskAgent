"""Dựng ảnh MẪU của watermark chéo (B8c) để PO xem bằng mắt và chỉnh màu, độ mờ. KHÔNG phải mã ứng dụng, không vào image.

Dùng (từ thư mục gốc repo, image target `test`):
    docker run --rm -v "$PWD":/repo -w /repo/backend -e PYTHONPATH=src:. --entrypoint python bo19-test /repo/tools/watermark-sample/render_sample.py /repo/docs/design/proposals/b8c-watermark-mau.png
Văn bản là MẪU GIẢ (tests/render_support.py): không dữ liệu thật. Ảnh: trang 1 của PDF `NON_PRODUCTION` do `soffice` dựng, 70 dpi.
Chỉnh màu và độ mờ: `FILL_COLOR`, `FILL_OPACITY` ở `bo19/tool_layer/rendering/watermark.py`.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from bo19.tool_layer.rendering import convert, docx_fill
from tests.render_support import DECLARED, VALUES, VIETNAMESE, build_template

out = Path(sys.argv[1])
template = build_template(extra_paragraphs=tuple(f"Đoạn thân văn bản số {i}: " + VIETNAMESE * 2 for i in range(14)))
pdf = convert.convert_to_pdf(docx_fill.fill_docx(template, VALUES, declared=DECLARED, operating_mode="NON_PRODUCTION"), timeout_s=300)
with tempfile.TemporaryDirectory() as d:
    Path(d, "x.pdf").write_bytes(pdf)
    subprocess.run(["pdftoppm", "-r", "70", "-png", "-f", "1", "-l", "1", "-singlefile", "x.pdf", "page"], cwd=d, check=True)
    out.write_bytes(Path(d, "page.png").read_bytes())
print("đã ghi", out, out.stat().st_size, "byte")
