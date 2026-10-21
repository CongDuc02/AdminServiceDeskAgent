"""Bản build client GIẢ cho test (B10a): một thư mục tạm có `index.html` tham chiếu `/assets/app-<hash>.js` và `.css`, cùng các tệp ở gốc. Không có test nào ở đây."""
from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

INDEX = ('<!doctype html><html lang="vi"><head><meta charset="UTF-8"><title>BO-19</title>'
         '<script type="module" crossorigin src="/assets/app-a1b2c3.js"></script><link rel="stylesheet" crossorigin href="/assets/app-d4e5f6.css"></head>'
         '<body><div id="root"></div></body></html>')
JS = "console.log('bo19 gia');"
CSS = "body{margin:0}"


def make_build(root: Path | None = None, *, index: str = INDEX, assets: bool = True) -> Path:
    """Dựng bản build giả; trả thư mục. `root=None`: thư mục tạm do người gọi tự dọn (`tempfile.mkdtemp`)."""
    root = root or Path(tempfile.mkdtemp(prefix="bo19-static-"))
    (root / "assets").mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(index, encoding="utf-8")
    (root / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    if assets:
        (root / "assets" / "app-a1b2c3.js").write_text(JS, encoding="utf-8")
        (root / "assets" / "app-d4e5f6.css").write_text(CSS, encoding="utf-8")
    return root


_SHARED: Path | None = None


def shared_build() -> Path:
    """Một bản build giả dùng chung cho test khởi động `api`/`combined_main` (bước kiểm #8 chặn khi thiếu). Dọn khi tiến trình test thoát."""
    global _SHARED
    if _SHARED is None:
        _SHARED = make_build()
        atexit.register(shutil.rmtree, _SHARED, True)
    return _SHARED
