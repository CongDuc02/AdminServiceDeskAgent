"""Bước kiểm khởi động #8 — bản build client có mặt (B10a; mục Bước kiểm khởi động của 06-structure.md; ADR-013, ADR-018). Không cần DB.

- đạt khi `index.html` có và MỌI asset nó tham chiếu là file thật (đạt thì im lặng); trượt mang số asset thiếu (không tên file);
- trượt, mỗi ca một mã: không có `index.html` / thư mục không tồn tại → `STARTUP_08_CLIENT_INDEX_MISSING`; `index.html` không tham chiếu asset nào → `STARTUP_08_CLIENT_NO_ASSETS`;
  thiếu một asset → `STARTUP_08_CLIENT_ASSET_MISSING` (số thiếu ở `info`);
- chỉ tính asset dưới `/assets/`; tham chiếu có `?query` hay `#hash` vẫn tìm đúng file; asset là thư mục hay nằm ngoài thư mục build không tính là có;
- `api` có bước này, `worker`/`cron` không, `combined_main` có (hợp mọi bước), mức **Chặn**; `STATIC_DIR` mặc định `/app/static` và đổi được bằng `BO19_STATIC_DIR`.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_checks_client -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import shutil
import tempfile
import unittest
from pathlib import Path

from bo19.config.settings import load_settings
from bo19.startup.checks_client import step_08
from bo19.startup.model import MATRIX, Context, Entry, Level
from tests.static_support import INDEX, make_build

BASE = {"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": "x", "BO19_SESSION_SECRET": "y" * 32}


def run(root: Path | str):
    s = load_settings({**BASE, "BO19_STATIC_DIR": str(root)})
    return step_08(Context(Entry.API, s, {}, None, Path(".")))


class Buoc8(unittest.TestCase):
    def build(self, **kw) -> Path:
        root = make_build(**kw)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def test_dat(self):
        r = run(self.build())
        self.assertEqual((r.codes, r.info), ((), {}))  # đạt thì im lặng — không thêm dòng STARTUP_CHECK_INFO

    def test_khong_co_thu_muc_hoac_index(self):
        self.assertEqual(run(Path(tempfile.gettempdir()) / "bo19-khong-co-thu-muc-nay").codes, ("STARTUP_08_CLIENT_INDEX_MISSING",))
        root = self.build()
        (root / "index.html").unlink()
        self.assertEqual(run(root).codes, ("STARTUP_08_CLIENT_INDEX_MISSING",))

    def test_index_la_thu_muc_khong_tinh_la_co(self):
        root = self.build()
        (root / "index.html").unlink()
        (root / "index.html").mkdir()
        self.assertEqual(run(root).codes, ("STARTUP_08_CLIENT_INDEX_MISSING",))

    def test_index_khong_tham_chieu_asset_nao(self):
        root = self.build(index="<!doctype html><html><body><div id=root></div></body></html>")
        self.assertEqual(run(root).codes, ("STARTUP_08_CLIENT_NO_ASSETS",))

    def test_thieu_mot_asset(self):
        root = self.build()
        (root / "assets" / "app-a1b2c3.js").unlink()
        r = run(root)
        self.assertEqual((r.codes, r.info), (("STARTUP_08_CLIENT_ASSET_MISSING",), {"missing": 1, "referenced": 2}))

    def test_thieu_het_asset(self):
        r = run(self.build(assets=False))
        self.assertEqual((r.codes, r.info["missing"]), (("STARTUP_08_CLIENT_ASSET_MISSING",), 2))

    def test_chi_tinh_asset_duoi_assets_nhung_tham_chieu_co_query_va_hash_van_dung(self):
        index = INDEX.replace("/assets/app-a1b2c3.js", "/assets/app-a1b2c3.js?v=2").replace("/assets/app-d4e5f6.css", "/assets/app-d4e5f6.css#x") + '<a href="/chat">trang khác</a><link href="https://cdn.example.test/x.css">'
        self.assertEqual(run(self.build(index=index)).codes, ())

    def test_asset_la_thu_muc_khong_tinh_la_file(self):
        root = self.build()
        (root / "assets" / "app-a1b2c3.js").unlink()
        (root / "assets" / "app-a1b2c3.js").mkdir()
        self.assertEqual(run(root).codes, ("STARTUP_08_CLIENT_ASSET_MISSING",))

    def test_tham_chieu_thoat_thu_muc_khong_tinh_la_co(self):
        outside = Path(tempfile.mkdtemp(prefix="bo19-outside-"))
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        (outside / "x.js").write_text("x", encoding="utf-8")
        root = self.build(index='<html><script src="/assets/../../' + outside.name + '/x.js"></script></html>')
        # tham chiếu thoát qua `..` KHÔNG được chấp nhận là asset có mặt, kể cả khi file ở đó có thật
        self.assertEqual(run(root).codes, ("STARTUP_08_CLIENT_ASSET_MISSING",))


class MaTranVaCauHinh(unittest.TestCase):
    def test_chi_api_va_combined_co_buoc_8_muc_chan(self):
        step = next(s for s in MATRIX if s.number == "8")
        self.assertEqual((step.level, step.applies(Entry.API), step.applies(Entry.WORKER), step.applies(Entry.CRON), step.applies(Entry.COMBINED)), (Level.BLOCK, True, False, False, True))

    def test_static_dir_mac_dinh_va_doi_duoc(self):
        self.assertEqual(load_settings(BASE).static_dir, "/app/static")
        self.assertEqual(load_settings({**BASE, "BO19_STATIC_DIR": "  /srv/client  "}).static_dir, "/srv/client")
        self.assertEqual(load_settings({**BASE, "BO19_STATIC_DIR": "   "}).static_dir, "/app/static")
        self.assertEqual(load_settings(BASE).problems, ())


if __name__ == "__main__":
    unittest.main()
