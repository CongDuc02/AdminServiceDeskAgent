"""`bo19.tool_layer.rendering.convert` (B8b; ADR-015) — chuyển `.docx` sang PDF bằng `soffice` THẬT trong image target `test`.

Điều được chứng minh, nói bằng hành vi:
- **PDF thật:** ra từ `.docx` điền biến; chữ tiếng Việt đủ dấu đọc lại được từ PDF; watermark có trong PDF ở `NON_PRODUCTION`; không có ở `PRODUCTION`;
- **font (ADR-036):** `.docx` khai "Times New Roman", image không có font đó, và **PDF nhúng Liberation Serif** — không DejaVu, không font nào khác;
- **hết hạn:** quá `timeout_s` thì giết CẢ nhóm tiến trình (`soffice` sinh `soffice.bin`), không còn tiến trình nào của lần đó, thư mục tạm bị xoá, mã `TIMEOUT`;
- **lỗi chỉ mang mã:** file hỏng là `CONVERSION_FAILED`, thông điệp không mang văn bản của file;
- **hồ sơ riêng:** hai lần chuyển đổi đồng thời đều xong và mỗi PDF mang đúng chữ của mình; sau mỗi lần không còn thư mục tạm.

Cần `soffice`, `pdftotext`, `pdffonts` — có trong image target `test`; thiếu thì bỏ qua, trừ khi `BO19_REQUIRE_SOFFICE=1` (CI).
Chạy từ backend/ với PYTHONPATH=src:  python -m unittest tests.test_convert -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from bo19.tool_layer.rendering import convert, docx_fill
from tests.render_support import DECLARED, VALUES, VIETNAMESE, build_template, pdf_fonts, pdf_text, require_tool

TIMEOUT = 180  # rộng: lần chạy đầu của `soffice` nạp cache; không phải số hiệu chỉnh


def render(values=None, mode="PRODUCTION") -> bytes:
    return docx_fill.fill_docx(build_template(), values or VALUES, declared=DECLARED, operating_mode=mode)


def soffice_pids(marker: str) -> list[int]:
    pids = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                cmd = (entry / "cmdline").read_bytes().decode("utf-8", "replace")
            except OSError:
                continue
            if marker in cmd and "soffice" in cmd:
                pids.append(int(entry.name))
    return pids


class ChuyenDoi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for tool in ("soffice", "pdftotext", "pdffonts"):
            require_tool(cls, tool)
        cls.tmp = tempfile.TemporaryDirectory(prefix="bo19-test-convert-")
        cls.pdf = convert.convert_to_pdf(render(mode="NON_PRODUCTION"), timeout_s=TIMEOUT, tmp_root=cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_ra_pdf_that(self):
        self.assertTrue(self.pdf.startswith(b"%PDF-"))
        self.assertGreater(len(self.pdf), 1000)

    def test_chu_tieng_viet_du_dau_doc_lai_duoc_tu_pdf(self):
        text = " ".join(pdf_text(self.pdf).split())
        for piece in ("GIẤY XÁC NHẬN GIẢ", "Nguyễn Thị Hương Giang", "CÔNG TY GIẢ", "Lưu: VT"):
            self.assertIn(piece, text)
        self.assertIn("đã công tác tại Phòng Hành chính", text)

    def test_watermark_co_trong_pdf_o_non_production_va_khong_co_o_production(self):
        self.assertIn(docx_fill.WATERMARK_TEXT, " ".join(pdf_text(self.pdf).split()))
        prod = convert.convert_to_pdf(render(mode="PRODUCTION"), timeout_s=TIMEOUT, tmp_root=self.tmp.name)
        self.assertNotIn("THỬ NGHIỆM", pdf_text(prod))

    def test_pdf_nhung_liberation_serif_khi_docx_khai_times_new_roman(self):
        embedded = pdf_fonts(self.pdf)
        self.assertTrue(embedded)
        for name in embedded:
            self.assertIn("LiberationSerif", name, embedded)  # không DejaVu, không font nào khác
        self.assertFalse(any("TimesNewRoman" in n or "DejaVu" in n for n in embedded))

    def test_moi_lan_xong_khong_con_thu_muc_tam(self):
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_hai_lan_chuyen_doi_dong_thoi_hai_ho_so_rieng(self):
        out: dict[str, bytes] = {}
        errors: list[BaseException] = []

        def go(name: str):
            try:
                out[name] = convert.convert_to_pdf(render({**VALUES, "ho_ten": f"Người {name} Đặng"}), timeout_s=TIMEOUT, tmp_root=self.tmp.name)
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=go, args=(n,)) for n in ("AAA", "BBB")]
        [t.start() for t in threads]
        [t.join(TIMEOUT + 30) for t in threads]
        self.assertEqual(errors, [])
        self.assertIn("Người AAA Đặng", " ".join(pdf_text(out["AAA"]).split()))
        self.assertIn("Người BBB Đặng", " ".join(pdf_text(out["BBB"]).split()))
        self.assertNotIn("BBB", pdf_text(out["AAA"]))
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])


class HetHanVaLoi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_tool(cls, "soffice")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="bo19-test-convert-")
        self.addCleanup(self.tmp.cleanup)

    def test_qua_han_giet_ca_nhom_tien_trinh_va_xoa_thu_muc_tam(self):
        started = time.monotonic()
        with self.assertRaises(convert.ConversionTimeout) as cm:
            # Văn bản NẶNG (một giá trị nhiều nghìn dòng: `soffice` dựng mất hàng chục giây — superlinear, đo ở B8b: 800 dòng ≈ 30 s) để việc giết tiến trình là thứ duy nhất đưa hàm về sớm
            convert.convert_to_pdf(render({**VALUES, "noi_dung": "\n".join([VIETNAMESE * 6] * 800)}), timeout_s=0.3, tmp_root=self.tmp.name)
        self.assertEqual(cm.exception.code, "TIMEOUT")
        self.assertLess(time.monotonic() - started, 5)  # SIGKILL cả nhóm tiến trình trả về ngay; không giết được thì `wait(10)` của bộ dọn làm quá 10 s
        self.assertEqual(soffice_pids("bo19-convert-"), [])  # không còn soffice hay soffice.bin của lần đó
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_file_hong_la_conversion_failed_va_khong_mang_noi_dung(self):
        secret = "VĂN-BẢN-BÍ-MẬT-98765"
        for blob in (b"", b"PK\x03\x04 hong " + secret.encode("utf-8"), secret.encode("utf-8") * 50):
            with self.assertRaises(convert.ConversionFailed) as cm:
                convert.convert_to_pdf(blob, timeout_s=180, tmp_root=self.tmp.name)
            self.assertNotIn(secret, f"{cm.exception!r} {cm.exception}")
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_khong_co_soffice_la_conversion_failed(self):
        old = convert.SOFFICE
        convert.SOFFICE = "soffice-khong-ton-tai-bo19"
        try:
            with self.assertRaises(convert.ConversionFailed):
                convert.convert_to_pdf(render(), timeout_s=5, tmp_root=self.tmp.name)
        finally:
            convert.SOFFICE = old
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_lenh_dung_dung_tham_so_cua_adr_015(self):
        cmd = convert.soffice_command(Path("/tmp/w"), Path("/tmp/w/input.docx"))
        self.assertEqual(cmd[0], "soffice")
        for flag in ("--headless", "--norestore", "--nolockcheck", "-env:UserInstallation=file:///tmp/w/profile", "--convert-to", "pdf", "--outdir", "/tmp/w/out"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[-1], "/tmp/w/input.docx")

    def test_tien_trinh_con_khong_dung_shell(self):
        import inspect
        self.assertNotIn("shell=True", inspect.getsource(convert))
        self.assertIn("start_new_session=True", inspect.getsource(convert))

    def test_hai_lan_goi_dung_hai_thu_muc_rieng(self):
        cmds = [convert.soffice_command(Path(f"/tmp/{n}"), Path(f"/tmp/{n}/input.docx")) for n in ("a", "b")]
        profiles = [next(c for c in cmd if c.startswith("-env:UserInstallation=")) for cmd in cmds]
        self.assertNotEqual(profiles[0], profiles[1])
        self.assertTrue(os.environ.get("HOME") is not None or True)


if __name__ == "__main__":
    unittest.main()
