"""Họ font của file `.docx` và việc "có mặt trong image" (ADR-015 chốt 1–3, ADR-036; mục Bước kiểm khởi động #6, #7 của 06-structure.md).

**`declared_families`** — họ font mà một `.docx` khai dùng, đọc từ XML trong file: `w:rFonts` (`ascii`, `hAnsi`, `eastAsia`, `cs`) ở thân văn bản, kiểu định dạng (gồm `docDefaults`), đánh số, tiêu đề, chân trang,
chú thích cuối trang/cuối bài; bảng font `w:font`; ký hiệu `w:sym`; và phông của `theme` khi `rFonts` dẫn bằng `*Theme`. **Chỗ hở còn lại, nói thẳng (ADR-015):** đặc tả OOXML chưa có trong `docs/reference/` nên
danh sách này là "đủ theo các nơi đã biết", mỗi nơi có một test; một nơi chưa biết thì font ở đó lọt khỏi manifest, và chốt 2, chốt 3 không thấy nó. Phần XML dùng `lxml` với entity và mạng tắt, kích thước mỗi phần bị chặn.

**`is_present`** — "có mặt" theo hai luật (ADR-036 điểm 4):
- họ có quy tắc ánh xạ fontconfig tường minh (`FONT_ALIASES`; hiện chỉ "Times New Roman" → "Liberation Serif"): `fc-match "<họ>"` phải ra **đúng họ đích**;
- họ khác: **khớp chính xác tên** trong `fc-list : family`, không "tìm font gần nhất".
Công cụ (`fc-match`, `fc-list`) thiếu thì `FontToolMissing` — không coi là "font thiếu" mà là image hỏng.
"""
from __future__ import annotations

import io
import subprocess
import zipfile
from collections.abc import Callable, Iterable

from lxml import etree

from bo19.tool_layer.tools._common import ToolError

FONT_ALIASES = {"Times New Roman": "Liberation Serif"}  # ADR-036 — khớp fonts/50-bo19-times-new-roman.conf (tests/test_fonts.py đối chiếu)
TOOL_TIMEOUT_S = 10
MAX_PART_BYTES = 20 * 1024 * 1024  # mỗi phần XML sau khi giải nén; file .docx của tổ chức nhỏ hơn nhiều

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_ATTRS = ("ascii", "hAnsi", "eastAsia", "cs")
_THEME_ATTRS = {"asciiTheme": "latin", "hAnsiTheme": "latin", "eastAsiaTheme": "ea", "cstheme": "cs"}


class FontToolMissing(ToolError):
    code = "FONT_TOOL_MISSING"  # fc-match / fc-list không chạy được: image hỏng, không phải "thiếu font"


class DocxUnreadable(ToolError):
    code = "DOCX_UNREADABLE"


def _parse(blob: bytes) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, load_dtd=False)
    return etree.fromstring(blob, parser)


def _theme_fonts(root: etree._Element) -> dict[str, str]:
    """`{"majorlatin": …, "minorlatin": …, "majorea": …, …}` từ `a:fontScheme`; phông rỗng (theme để trống) bị bỏ."""
    out: dict[str, str] = {}
    for scheme_kind in ("majorFont", "minorFont"):
        for font in root.iter(f"{{{_A}}}{scheme_kind}"):
            for tag in ("latin", "ea", "cs"):
                el = font.find(f"{{{_A}}}{tag}")
                if el is not None and el.get("typeface"):
                    out[scheme_kind[:5] + tag] = el.get("typeface")  # "major"/"minor" + tag
    return out


def declared_families(docx: bytes) -> frozenset[str]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(docx))
    except zipfile.BadZipFile:
        raise DocxUnreadable from None
    found: set[str] = set()
    parts: dict[str, etree._Element] = {}
    with zf:
        for info in zf.infolist():
            name = info.filename
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            if info.file_size > MAX_PART_BYTES:
                raise DocxUnreadable
            try:
                parts[name] = _parse(zf.read(name))
            except etree.XMLSyntaxError:
                raise DocxUnreadable from None
    theme: dict[str, str] = {}
    for name, root in parts.items():
        if name.startswith("word/theme/"):
            theme.update(_theme_fonts(root))
    for name, root in parts.items():
        if name.startswith("word/theme/"):
            continue
        for el in root.iter(f"{{{_W}}}rFonts"):
            for a in _ATTRS:
                v = el.get(f"{{{_W}}}{a}")
                if v:
                    found.add(v)
            for a, slot in _THEME_ATTRS.items():
                ref = el.get(f"{{{_W}}}{a}")  # vd. "minorHAnsi", "majorBidi", "minorEastAsia"
                if ref:
                    family = theme.get(("major" if ref.startswith("major") else "minor") + slot)
                    if family:
                        found.add(family)
        for el in root.iter(f"{{{_W}}}font"):  # bảng font (fontTable.xml) — và w:sym mang thuộc tính cùng tên
            v = el.get(f"{{{_W}}}name")
            if v:
                found.add(v)
        for el in root.iter(f"{{{_W}}}sym"):
            v = el.get(f"{{{_W}}}font")
            if v:
                found.add(v)
    return frozenset(found)


Runner = Callable[[list[str]], str]


def _run(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=TOOL_TIMEOUT_S, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise FontToolMissing from None
    if out.returncode != 0:
        raise FontToolMissing
    return out.stdout


def _families(output: str) -> set[str]:
    """Dòng `fc-list : family` / `fc-match -f %{family}`: các họ cách nhau bằng dấu phẩy (một font có thể mang nhiều tên)."""
    names: set[str] = set()
    for line in output.splitlines():
        for part in line.split(","):
            if part.strip():
                names.add(part.strip().replace("\\-", "-"))
    return names


def match_families(family: str, run: Runner | None = None) -> set[str]:
    return _families((run or _run)(["fc-match", "-f", "%{family}\n", family]))


def installed_families(run: Runner | None = None) -> set[str]:
    return _families((run or _run)(["fc-list", ":", "family"]))


def is_present(family: str, *, run: Runner | None = None, installed: set[str] | None = None) -> bool:
    target = FONT_ALIASES.get(family)
    if target is not None:
        return target in match_families(family, run)
    return family in (installed if installed is not None else installed_families(run))


def missing(required: Iterable[str], *, run: Runner | None = None) -> list[str]:
    """Các họ trong `required` chưa có mặt, theo thứ tự chữ cái. Gọi `fc-list` một lần."""
    installed = installed_families(run)
    return sorted(f for f in set(required) if not is_present(f, run=run, installed=installed))
