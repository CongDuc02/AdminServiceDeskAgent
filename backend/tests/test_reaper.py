"""Bộ dọn zombie của PID 1 (`observability.reaper`) và huỷ chuyển đổi khi tắt (`convert.abort_all`) — B9a2.

Không cần PostgreSQL hay `soffice` thật: một `soffice` GIẢ (script `sh`, sinh một tiến trình con sống lâu rồi chờ) đứng chỗ LibreOffice. Bằng chứng ở image thật, cgroup 0,1 CPU: `docs/reference/combined-main-b9a2.md`.
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_reaper -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from docx import Document

from bo19.observability import reaper
from bo19.tool_layer.rendering import convert

BACKEND = Path(__file__).resolve().parents[1]
LINUX = sys.platform.startswith("linux")


def docx_bytes() -> bytes:
    d = Document()
    d.add_paragraph("thử")
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def group_members(pgid: int) -> list[tuple[int, str]]:
    """(pid, trạng thái) của mọi tiến trình thuộc nhóm `pgid`, theo /proc."""
    out = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat", encoding="utf-8", errors="replace") as f:
                stat_text = f.read()
            rest = stat_text[stat_text.rindex(")") + 2:].split()
            if int(rest[2]) == pgid:
                out.append((int(name), rest[0]))
        except (OSError, ValueError, IndexError):
            continue
    return out


@unittest.skipUnless(LINUX, "cần /proc và Linux")
class BoDon(unittest.TestCase):
    def test_tien_trinh_pid_1_gia_dong_chi_don_zombie_mo_coi_va_khong_cuop_ma_thoat(self):
        p = subprocess.run([sys.executable, "-m", "tests.reaper_helper"], cwd=BACKEND, env={**os.environ, "PYTHONPATH": "src"}, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr[-1500:])
        out = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertNotIn("error", out)
        self.assertEqual(out["zombies_before"], 1)          # `sleep` mồ côi hết hạn → zombie của "PID 1"
        self.assertEqual(out["first_sweep_reaped"], 0)      # thấy lần đầu: chưa dọn (một Popen vừa chết chưa kịp bị chủ `wait`)
        self.assertEqual(out["second_sweep_reaped"], 1)     # thấy lần hai: dọn
        self.assertEqual(out["zombies_after"], 0)
        self.assertEqual(out["protected_exit_code"], 7)     # con được bảo vệ giữ nguyên mã thoát, kể cả qua quét cuối
        self.assertEqual(out["final_reaped"], 1)            # `final` dọn ngay
        self.assertEqual(out["zombies_end"], 0)

    def test_children_doc_dung_con_truc_tiep_va_trang_thai(self):
        p = subprocess.Popen(["sh", "-c", "exit 0"])
        time.sleep(0.4)
        mine = {c.pid: c for c in reaper.children()}
        self.assertEqual(mine[p.pid].state, "Z")  # chết, chưa `wait`
        p.wait()
        self.assertNotIn(p.pid, {c.pid for c in reaper.children()})

    def test_start_if_init_chi_chay_khi_la_pid_1(self):
        with mock.patch.object(reaper.os, "getpid", return_value=77):
            self.assertIsNone(reaper.start_if_init())
        with mock.patch.object(reaper.os, "getpid", return_value=1):
            r = reaper.start_if_init(interval_s=0.05)
            self.assertIsNotNone(r)
            r.stop()
        r = reaper.start_if_init(force=True, interval_s=0.05)
        self.assertIsNotNone(r)
        r.stop()

    def test_stop_ghi_bang_tien_trinh_khi_thoat_chi_so_va_ten(self):
        import io as _io
        import logging
        from bo19.observability.log import configure_logging
        out = _io.StringIO()
        handler = configure_logging(out)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        r = reaper.Reaper(interval_s=0.05)
        r.start()
        r.stop()
        line = next(json.loads(l) for l in out.getvalue().splitlines() if "PROCESS_TABLE_AT_EXIT" in l)
        for key in ("children", "zombies", "reaped", "alive"):
            self.assertIn(key, line)
        self.assertEqual(line["zombies"], 0)


@unittest.skipUnless(LINUX, "cần /proc, `sh` và Linux")
class HuyChuyenDoi(unittest.TestCase):
    """`abort_all` giết NGAY nhóm tiến trình của chuyển đổi đang chạy; không để lại tiến trình sống; chặn chuyển đổi mới."""

    def setUp(self):
        convert.reset_abort()
        self.addCleanup(convert.reset_abort)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        fake = Path(self.tmp.name) / "soffice"
        self.marker = Path(self.tmp.name) / "started"
        # soffice giả: một tiến trình con sống lâu (như soffice.bin) + chờ nó; ghi PID nhóm vào file mốc
        self.nice_file = Path(self.tmp.name) / "niceness"
        fake.write_text(f"#!/bin/sh\nawk '{{print $19}}' /proc/$$/stat > {self.nice_file}\nsleep 300 &\necho $$ > {self.marker}\nwait\n", encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        patcher = mock.patch.dict(os.environ, {"PATH": f"{self.tmp.name}{os.pathsep}{os.environ['PATH']}"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_conversion(self, results: list, timeout_s: float = 120):
        def work():
            try:
                convert.convert_to_pdf(docx_bytes(), timeout_s=timeout_s)
                results.append("OK")
            except BaseException as e:  # noqa: BLE001
                results.append(e)

        t = threading.Thread(target=work, daemon=True)
        t.start()
        return t

    def wait_started(self) -> int:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.marker.exists() and self.marker.read_text().strip():
                return int(self.marker.read_text().strip())
            time.sleep(0.02)
        self.fail("soffice giả không khởi động")

    def test_abort_giet_nhom_va_chu_chuyen_doi_nhan_conversion_aborted_ngay(self):
        results: list = []
        t = self.run_conversion(results)
        pgid = self.wait_started()
        self.assertEqual(convert.live_pids(), {pgid})  # được theo dõi: bộ dọn zombie không được đụng vào
        self.assertTrue(any(s != "Z" for _, s in group_members(pgid)))
        before = time.monotonic()
        self.assertEqual(convert.abort_all(), 1)
        t.join(5)
        self.assertLess(time.monotonic() - before, 3)  # không chờ 300 s hay timeout 120 s
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], convert.ConversionAborted)
        self.assertEqual(results[0].code, "JOB_CANCELLED")
        self.assertEqual(convert.live_pids(), set())
        self.assertEqual([m for m in group_members(pgid) if m[1] != "Z"], [])  # không còn tiến trình sống nào của nhóm (zombie mồ côi là việc của PID 1 và bộ dọn)

    def test_soffice_chay_voi_nice_19_theo_wv_33_va_nhom_van_la_pid_cua_no(self):
        results: list = []
        t = self.run_conversion(results)
        pgid = self.wait_started()
        self.assertEqual(self.nice_file.read_text().strip(), "19")  # `nice` exec thẳng: tiến trình soffice thật mang niceness 19
        self.assertEqual(convert.live_pids(), {pgid})              # PID đã theo dõi == PID nhóm == PID của script (nice không thêm tầng)
        convert.abort_all()
        t.join(5)

    def test_niceness_0_thi_khong_ha_uu_tien(self):
        def work():
            try:
                convert.convert_to_pdf(docx_bytes(), timeout_s=120, niceness=0)
            except BaseException:  # noqa: BLE001
                pass

        t = threading.Thread(target=work, daemon=True)
        t.start()
        self.wait_started()
        self.assertEqual(self.nice_file.read_text().strip(), "0")
        convert.abort_all()
        t.join(5)

    def test_thu_muc_tam_duoc_don_sau_khi_bi_huy(self):
        tmp_root = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp_root, ignore_errors=True))
        results: list = []

        def work():
            try:
                convert.convert_to_pdf(docx_bytes(), timeout_s=120, tmp_root=tmp_root)
            except BaseException as e:  # noqa: BLE001
                results.append(e)

        t = threading.Thread(target=work, daemon=True)
        t.start()
        self.wait_started()
        self.assertEqual(len(os.listdir(tmp_root)), 1)
        convert.abort_all()
        t.join(5)
        self.assertEqual(os.listdir(tmp_root), [])

    def test_sau_abort_chuyen_doi_moi_bi_chan_khong_chay_soffice(self):
        convert.abort_all()
        with mock.patch.object(convert.subprocess, "Popen", side_effect=AssertionError("không được sinh tiến trình sau abort")):
            with self.assertRaises(convert.ConversionAborted):
                convert.convert_to_pdf(docx_bytes(), timeout_s=5)
        self.assertFalse(self.marker.exists())  # không sinh tiến trình nào

    def test_abort_khi_khong_co_gi_chay_la_vo_hai_va_reset_mo_lai(self):
        self.assertEqual(convert.abort_all(), 0)
        convert.reset_abort()
        self.assertFalse(convert.ABORT.is_set())

    def test_wait_idle(self):
        self.assertTrue(convert.wait_idle(0.1))
        results: list = []
        t = self.run_conversion(results)
        self.wait_started()
        self.assertFalse(convert.wait_idle(0.1))  # đang chạy
        convert.abort_all()
        self.assertTrue(convert.wait_idle(5))
        t.join(5)

    def test_timeout_van_la_conversion_timeout_va_khong_de_lai_nhom(self):
        results: list = []
        t = self.run_conversion(results, timeout_s=0.5)
        pgid = self.wait_started()
        t.join(10)
        self.assertIsInstance(results[0], convert.ConversionTimeout)
        self.assertEqual(convert.live_pids(), set())
        self.assertEqual([m for m in group_members(pgid) if m[1] != "Z"], [])


if __name__ == "__main__":
    unittest.main()
