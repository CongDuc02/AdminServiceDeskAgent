"""Bước kiểm khởi động #6 và #7 — `soffice` và font (mục Bước kiểm khởi động của 06-structure.md; ADR-015 chốt 3; ADR-036). Chỉ `worker`, **Chặn**: thiếu thì không khởi động — deploy đó hỏng, Render giữ bản trước.

**#6 (B8c, PO 2026-10-13, O1-19: kiểm nhẹ)** — `soffice --headless --version` chạy được, thoát mã 0 và trả dòng phiên bản trong hạn WV-25 (20 s); cộng `fc-list` và `fc-match` chạy được (cùng cần công cụ trong image, ADR-036 điểm 4). **Không chuyển đổi tài liệu**: phép chuyển đổi thật mất ≈ 47 s ở 0,1 CPU mỗi lần thức dậy trên gói Free (B8b) — nó chỉ chạy ở CI, trong image (`tests/test_convert.py`, `tests/test_render_tools.py`). **Log phiên bản LibreOffice thật** (trường `libreoffice` của `STARTUP_CHECK_INFO`) mỗi lần khởi động, cho A-094. Mã: `STARTUP_06_SOFFICE_MISSING`, `STARTUP_06_VERSION_FAILED`, `STARTUP_06_VERSION_TIMEOUT`, `STARTUP_06_FONT_TOOL_MISSING`.

**#7** — tập font cần = hợp của `required_fonts` trên **mọi phiên bản `ACTIVE`** và trên mọi phiên bản mà một `document` **chưa tới trạng thái kết thúc** đang dùng (`finalize_issue` render bản cuối bằng đúng phiên bản đã duyệt, có thể
đã `RETIRED`). Mỗi họ phải "có mặt" theo `rendering.fonts.is_present`: họ có ánh xạ fontconfig tường minh ("Times New Roman" → Liberation Serif) thì `fc-match` phải ra đúng họ đích; họ khác thì khớp chính xác tên.
Mã: `STARTUP_07_FONT_MISSING` (tên các họ thiếu ở trường log `families` — tên font, không phải dữ liệu người dùng), `STARTUP_07_FONT_TOOL_MISSING`. Không có phiên bản nào: tập rỗng, đạt.
"""
from __future__ import annotations

from bo19.config import working_values as wv
from bo19.startup.model import Context, Result, code
from bo19.tool_layer.rendering import convert, fonts

TERMINAL_DOCUMENT_STATUSES = ("ISSUED", "REVOKED", "SUPERSEDED", "ARCHIVED", "REJECTED")  # không còn cần render


def step_06(ctx: Context) -> Result:
    if not convert.available():
        return Result((code("6", "SOFFICE_MISSING"),))
    if wv.SOFFICE_NICENESS and not convert.nice_available():
        return Result((code("6", "NICE_MISSING"),))  # WV-33: `soffice` chạy qua `nice`; thiếu nó thì chuyển đổi đầu tiên mới hỏng — báo ngay lúc khởi động
    try:
        fonts.installed_families()
        fonts.match_families("serif")
    except fonts.FontToolMissing:
        return Result((code("6", "FONT_TOOL_MISSING"),))
    try:
        version = convert.soffice_version(timeout_s=wv.SOFFICE_STARTUP_CHECK_TIMEOUT_S)
    except convert.ConversionTimeout:
        return Result((code("6", "VERSION_TIMEOUT"),))
    except convert.VersionFailed:
        return Result((code("6", "VERSION_FAILED"),))
    return Result(info={"libreoffice": version})  # A-094: phiên bản LibreOffice thật của image, ghi mỗi lần `worker` khởi động


_REQUIRED = (
    "SELECT DISTINCT unnest(required_fonts) FROM template_version WHERE status = 'ACTIVE' OR id IN "
    "(SELECT template_version_id FROM document WHERE status <> ALL(%s))"
)


def step_07(ctx: Context) -> Result:
    required = {r[0] for r in ctx.conn.execute(_REQUIRED, (list(TERMINAL_DOCUMENT_STATUSES),)).fetchall()}
    try:
        lacking = fonts.missing(required)
    except fonts.FontToolMissing:
        return Result((code("7", "FONT_TOOL_MISSING"),))
    if lacking:
        return Result((code("7", "FONT_MISSING"),), info={"families": ",".join(lacking)})
    return Result()
