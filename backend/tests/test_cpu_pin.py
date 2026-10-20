"""Ghim tiến trình vào một CPU khi hạn mức cgroup < 1 CPU (`observability.cpu_pin`; WV-34; B9a2, PO 2026-10-20).

Hàm đọc hạn mức và quyết định chạy trên file giả và hàm affinity giả; một ca chạy `sched_setaffinity` THẬT trong tiến trình con để chứng minh luồng và tiến trình con sinh sau thừa hưởng.
Số đo hiệu quả (lượt chat khi `soffice` chạy): `docs/reference/combined-main-b9a2.md`.
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_cpu_pin -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bo19.config import working_values as wv
from bo19.observability import cpu_pin
from bo19.observability.log import configure_logging

BACKEND = Path(__file__).resolve().parents[1]
LINUX = sys.platform.startswith("linux")


class Files:
    def __init__(self, case: unittest.TestCase) -> None:
        self.dir = tempfile.TemporaryDirectory()
        case.addCleanup(self.dir.cleanup)

    def write(self, name: str, text: str) -> str:
        p = Path(self.dir.name) / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    def missing(self, name: str) -> str:
        return str(Path(self.dir.name) / name)


class DocHanMuc(unittest.TestCase):
    def setUp(self):
        self.f = Files(self)

    def limit(self, v2: str | None = None, v1_quota: str | None = None, v1_period: str | None = None):
        f = Files(self)  # thư mục riêng mỗi lần gọi: file của lần trước không được rò sang lần sau
        return cpu_pin.cgroup_cpu_limit(f.write("cpu.max", v2) if v2 is not None else f.missing("cpu.max"),
                                        f.write("q", v1_quota) if v1_quota is not None else f.missing("q"),
                                        f.write("p", v1_period) if v1_period is not None else f.missing("p"))

    def test_v2_hai_so_la_quota_chia_period(self):
        self.assertAlmostEqual(self.limit("10000 100000\n"), 0.1)
        self.assertAlmostEqual(self.limit("50000 100000"), 0.5)
        self.assertAlmostEqual(self.limit("200000 100000"), 2.0)

    def test_v2_max_hay_rac_la_khong_gioi_han(self):
        for text in ("max 100000", "max", "", "abc def", "10000", "0 100000", "10000 0", "-1 100000"):
            self.assertIsNone(self.limit(text), repr(text))

    def test_v1_quota_chia_period_va_am_1_la_khong_gioi_han(self):
        self.assertAlmostEqual(self.limit(v1_quota="10000", v1_period="100000"), 0.1)
        self.assertIsNone(self.limit(v1_quota="-1", v1_period="100000"))
        self.assertIsNone(self.limit(v1_quota="abc", v1_period="100000"))
        self.assertIsNone(self.limit(v1_quota="10000"))  # thiếu period

    def test_v2_co_mat_thi_v1_khong_duoc_xet(self):
        self.assertIsNone(self.limit("max 100000", v1_quota="10000", v1_period="100000"))

    def test_khong_co_file_nao_la_khong_gioi_han(self):
        self.assertIsNone(self.limit())


class QuyetDinh(unittest.TestCase):
    def setUp(self):
        self.f = Files(self)
        self.calls: list = []
        self.out = io.StringIO()
        handler = configure_logging(self.out)
        self.addCleanup(logging.getLogger().removeHandler, handler)

    def pin(self, cpu_max: str | None, allowed=frozenset({3, 5, 7}), **kw):
        return cpu_pin.pin_if_limited(v2_path=self.f.write("cpu.max", cpu_max) if cpu_max is not None else self.f.missing("cpu.max"), v1_quota=self.f.missing("q"), v1_period=self.f.missing("p"),
                                      getaffinity=lambda pid: set(allowed), setaffinity=lambda pid, cpus: self.calls.append((pid, set(cpus))), **kw)

    def test_han_muc_duoi_mot_cpu_thi_ghim_vao_cpu_dau_tien_cua_tap_hien_co(self):
        r = self.pin("10000 100000")
        self.assertEqual((r.pinned, r.reason, r.cpu, r.allowed), (True, "PINNED", 3, 3))
        self.assertEqual(self.calls, [(0, {3})])  # 0 = luồng gọi; CPU nhỏ nhất của tập {3, 5, 7}, không phải CPU 0
        self.assertIn("CPU_PINNED", self.out.getvalue())

    def test_chon_cpu_nho_nhat_du_tap_khong_sap_xep(self):
        self.pin("10000 100000", allowed=[9, 4, 6])
        self.assertEqual(self.calls, [(0, {4})])

    def test_tu_mot_cpu_tro_len_hoac_khong_gioi_han_thi_khong_ghim(self):
        for text, reason in (("100000 100000", "NOT_BELOW"), ("200000 100000", "NOT_BELOW"), ("max 100000", "NO_LIMIT"), (None, "NO_LIMIT")):
            r = self.pin(text)
            self.assertEqual((r.pinned, r.reason), (False, reason), text)
        self.assertEqual(self.calls, [])
        self.assertIn("CPU_PIN_SKIPPED", self.out.getvalue())

    def test_nguong_la_wv_34_khong_phai_so_cung(self):
        self.assertEqual(wv.PIN_CPU_WHEN_QUOTA_BELOW, 1.0)
        self.assertTrue(self.pin("50000 100000", below=0.4).reason == "NOT_BELOW")
        self.assertTrue(self.pin("50000 100000", below=0.6).pinned)

    def test_da_chi_con_mot_cpu_thi_khong_goi_setaffinity(self):
        r = self.pin("10000 100000", allowed={2})
        self.assertEqual((r.pinned, r.reason, r.cpu), (False, "SINGLE_CPU", 2))
        self.assertEqual(self.calls, [])

    def test_loi_cua_he_dieu_hanh_khong_lam_sap_tien_trinh(self):
        def boom(pid, cpus):
            raise PermissionError("không có quyền")

        r = cpu_pin.pin_if_limited(v2_path=self.f.write("cpu.max", "10000 100000"), v1_quota=self.f.missing("q"), v1_period=self.f.missing("p"), getaffinity=lambda pid: {1, 2}, setaffinity=boom)
        self.assertEqual((r.pinned, r.reason), (False, "ERROR"))
        self.assertIn("CPU_PIN_FAILED", self.out.getvalue())
        self.assertNotIn("không có quyền", self.out.getvalue())  # chỉ kiểu lỗi, không thông điệp

    def test_nen_tang_khong_ho_tro_affinity(self):
        orig = getattr(os, "sched_setaffinity", None)
        try:
            if orig is not None:
                del os.sched_setaffinity
            r = cpu_pin.pin_if_limited(v2_path=self.f.write("cpu.max", "10000 100000"), v1_quota=self.f.missing("q"), v1_period=self.f.missing("p"))
            self.assertEqual((r.pinned, r.reason), (False, "UNSUPPORTED"))
        finally:
            if orig is not None:
                os.sched_setaffinity = orig

    def test_log_chi_mang_so(self):
        self.pin("10000 100000")
        line = next(json.loads(l) for l in self.out.getvalue().splitlines() if "CPU_PINNED" in l)
        self.assertEqual((line["cpu"], line["cpu_limit"], line["cpus_allowed_before"]), (3, 0.1, 3))


CHILD = r"""
import json, os, subprocess, sys, threading
sys.path.insert(0, "src")
from bo19.observability import cpu_pin
r = cpu_pin.pin_if_limited(v2_path=sys.argv[1], v1_quota="/khong/co", v1_period="/khong/co")
box = {}
t = threading.Thread(target=lambda: box.setdefault("thread", sorted(os.sched_getaffinity(0))))
t.start(); t.join()
sh = subprocess.run(["sh", "-c", "grep Cpus_allowed_list /proc/self/status | cut -f2"], capture_output=True, text=True).stdout.strip()
print(json.dumps({"pinned": r.pinned, "cpu": r.cpu, "main": sorted(os.sched_getaffinity(0)), "thread": box["thread"], "child_allowed_list": sh}))
"""


@unittest.skipUnless(LINUX and len(getattr(os, "sched_getaffinity", lambda _: ())(0)) >= 2, "cần Linux và >= 2 CPU")
class ThatTrongTienTrinh(unittest.TestCase):
    """`sched_setaffinity` thật: luồng sinh sau và tiến trình con (như `soffice`) thừa hưởng."""

    def run_child(self, cpu_max: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "cpu.max"
            p.write_text(cpu_max, encoding="utf-8")
            out = subprocess.run([sys.executable, "-c", CHILD, str(p)], cwd=BACKEND, env={**os.environ, "PYTHONPATH": "src"}, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr[-1500:])
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_ghim_that_luong_va_tien_trinh_con_thua_huong(self):
        first = min(os.sched_getaffinity(0))
        got = self.run_child("10000 100000")
        self.assertTrue(got["pinned"])
        self.assertEqual((got["cpu"], got["main"], got["thread"], got["child_allowed_list"]), (first, [first], [first], str(first)))

    def test_khong_gioi_han_thi_giu_nguyen_tap_affinity(self):
        got = self.run_child("max 100000")
        self.assertFalse(got["pinned"])
        self.assertEqual(got["main"], sorted(os.sched_getaffinity(0)))
        self.assertEqual(got["thread"], got["main"])


if __name__ == "__main__":
    unittest.main()
