"""Bước kiểm khởi động #8 — bản build client có mặt (mục Bước kiểm khởi động của 06-structure.md; ADR-013, ADR-018). Chỉ `api` (và `combined_main`, hợp mọi bước), **Chặn**.

`index.html` có trong thư mục build (`Settings.static_dir`, mặc định `/app/static` — nơi Dockerfile chép `dist/` vào) và **mọi asset nó tham chiếu** (`/assets/…`, tên đã băm) đều là file thật; `index.html` phải
tham chiếu ít nhất một asset (một `index.html` không có asset là bản build rỗng). Thiếu thì `api` không khởi động: phục vụ một SPA thiếu file là trang trắng mà không ai biết vì sao.
Mã: `STARTUP_08_CLIENT_INDEX_MISSING`, `STARTUP_08_CLIENT_NO_ASSETS`, `STARTUP_08_CLIENT_ASSET_MISSING` (số asset thiếu ở trường log `missing`).
"""
from __future__ import annotations

import re
from pathlib import Path

from bo19.startup.model import Context, Result, code

_ASSET = re.compile(r"""(?:src|href)\s*=\s*["'](/assets/[^"'?#]+)""")


def _is_asset(root: Path, ref: str) -> bool:
    target = (root / ref.lstrip("/")).resolve()
    return target.is_file() and target.is_relative_to(root)  # tham chiếu thoát thư mục build bằng `..` không tính là asset có mặt


def step_08(ctx: Context) -> Result:
    root = Path(ctx.settings.static_dir).resolve()
    index = root / "index.html"
    if not index.is_file():
        return Result((code("8", "CLIENT_INDEX_MISSING"),))
    try:
        refs = sorted(set(_ASSET.findall(index.read_text(encoding="utf-8"))))
    except (OSError, UnicodeDecodeError):
        return Result((code("8", "CLIENT_INDEX_MISSING"),))
    if not refs:
        return Result((code("8", "CLIENT_NO_ASSETS"),))
    missing = [r for r in refs if not _is_asset(root, r)]
    if missing:
        return Result((code("8", "CLIENT_ASSET_MISSING"),), info={"missing": len(missing), "referenced": len(refs)})
    return Result()
