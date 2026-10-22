"""`observability.tmp_info` — dòng log `TMP_INFO` (A-095): loại hệ thống file của `/tmp` và chỗ trống; không bao giờ ném, không in gì ngoài tên và số.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_tmp_info -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bo19.observability import tmp_info

OVERLAY = "36 35 0:30 / / rw,relatime - overlay overlay rw,lowerdir=/l1:/l2,upperdir=/u,workdir=/w\n"
TMPFS = OVERLAY + "40 36 0:34 / /tmp rw,nosuid,nodev - tmpfs tmpfs rw,size=65536k\n"
TMPFS_SUB = OVERLAY + r"40 36 0:34 / /tmp/work\040dir rw - tmpfs tmpfs rw" + "\n"  # `mountinfo` mã hoá khoảng trắng thành \040 (chuỗi thô)


def usage(total_mib: int, free_mib: int):
    return lambda _p: (total_mib * 1024 * 1024, (total_mib - free_mib) * 1024 * 1024, free_mib * 1024 * 1024)


class MountOf(unittest.TestCase):
    def test_tmp_la_thu_muc_cua_overlay_khi_khong_co_diem_gan_rieng(self):
        self.assertEqual(tmp_info.mount_of("/tmp", OVERLAY), ("/", "overlay"))

    def test_tmp_la_tmpfs_khi_co_diem_gan_rieng(self):
        self.assertEqual(tmp_info.mount_of("/tmp", TMPFS), ("/tmp", "tmpfs"))

    def test_diem_gan_dai_nhat_thang_va_khong_khop_tien_to_ten(self):
        self.assertEqual(tmp_info.mount_of("/tmp", TMPFS_SUB), ("/", "overlay"))  # /tmp/work dir không chứa /tmp
        self.assertEqual(tmp_info.mount_of("/tmpfoo", TMPFS), ("/", "overlay"))  # "/tmp" không phải tiền tố thư mục của "/tmpfoo"

    def test_giai_ma_khoang_trang(self):
        self.assertEqual(tmp_info.mount_of("/tmp/work dir/x", TMPFS_SUB), ("/tmp/work dir", "tmpfs"))

    def test_dong_hong_bi_bo_qua(self):
        self.assertIsNone(tmp_info.mount_of("/tmp", "khong phai mountinfo\n\n36 35\n"))


class ReadAndLog(unittest.TestCase):
    def mountinfo(self, text: str) -> str:
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: [p.unlink() for p in Path(d).iterdir()] or Path(d).rmdir())
        p = Path(d) / "mountinfo"
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_doc_ra_loai_va_chi_tiet_bang_mib(self):
        info = tmp_info.read_tmp_info(path="/tmp", mountinfo=self.mountinfo(TMPFS), disk_usage=usage(64, 60))
        self.assertEqual(info, tmp_info.TmpInfo(fstype="tmpfs", mount_point="/tmp", total_mib=64, free_mib=60))

    def test_log_chi_mang_ten_va_so(self):
        with mock.patch.object(tmp_info, "log") as log:
            info = tmp_info.log_tmp_info(path="/tmp", mountinfo=self.mountinfo(OVERLAY), disk_usage=usage(2048, 1500))
        self.assertEqual(info.fstype, "overlay")
        log.info.assert_called_once_with("TMP_INFO", fstype="overlay", mount_point="/", total_mib=2048, free_mib=1500)

    def test_khong_doc_duoc_thi_ghi_skipped_va_khong_nem(self):
        with mock.patch.object(tmp_info, "log") as log:
            self.assertIsNone(tmp_info.log_tmp_info(mountinfo="/khong/ton/tai"))
        log.info.assert_called_once_with("TMP_INFO_SKIPPED", reason="UNREADABLE")

    def test_loi_bat_ngo_thanh_skipped_khong_lam_hong_khoi_dong(self):
        def boom(_p):
            raise ValueError("x")

        with mock.patch.object(tmp_info, "log") as log:
            self.assertIsNone(tmp_info.log_tmp_info(path="/tmp", mountinfo=self.mountinfo(OVERLAY), disk_usage=boom))
        self.assertEqual(log.warning.call_args.args, ("TMP_INFO_SKIPPED",))
        self.assertEqual(log.warning.call_args.kwargs["reason"], "ERROR")


if __name__ == "__main__":
    unittest.main()
