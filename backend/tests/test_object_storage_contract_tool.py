"""`tools/object-storage-contract/` (S7, cổng 2.5) chạy toàn bộ với SeaweedFS trong container — không mạng ngoài, không credential thật.

Khoá bằng test những điều PO đặt (2026-10-21): cấu hình chỉ từ biến môi trường; không có `--confirm-real` thì không đụng mạng; chỉ khoá dưới `s7-probe/`, dọn sạch sau khi đo
(khoá ngoài tiền tố còn nguyên); kết quả không chứa endpoint, tên bucket hay khoá; sai nhà cung cấp (thiếu 412) thì phép thử BẮT ĐƯỢC.

Cần BO19_TEST_S3_ENDPOINT (như các test object storage khác). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_object_storage_contract_tool -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import contextlib
import importlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import s3_support

TOOL = Path(__file__).resolve().parents[2] / "tools" / "object-storage-contract"
sys.path.insert(0, str(TOOL))
contract = importlib.import_module("object_storage_contract")


class Tool(s3_support.S3Base):
    def env(self, **over: str) -> dict[str, str]:
        base = {"BO19_OBJECT_STORAGE_ENDPOINT_URL": s3_support.ENDPOINT, "BO19_OBJECT_STORAGE_BUCKET": self.bucket, "BO19_OBJECT_STORAGE_REGION": "us-east-1",
                "BO19_OBJECT_STORAGE_ACCESS_KEY_ID": os.environ["BO19_TEST_S3_ACCESS_KEY_ID"], "BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY": os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"]}
        return {**base, **over}

    def main(self, argv: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        clean = {k: v for k, v in os.environ.items() if not k.startswith("BO19_OBJECT_STORAGE_")}
        with mock.patch.dict(os.environ, {**clean, **(env or {})}, clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = contract.main(argv)
        return code, out.getvalue(), err.getvalue()

    def keys(self) -> list[str]:
        return sorted(o["Key"] for o in self.raw.list_objects_v2(Bucket=self.bucket).get("Contents", []))

    def test_khong_co_confirm_real_thi_chi_in_ke_hoach(self):
        with mock.patch.object(contract.Suite, "run_all", side_effect=AssertionError("không được chạy")):
            code, out, _ = self.main([], self.env())
        self.assertEqual(code, 3)
        self.assertIn("S7_PROBE_PLAN", out)
        self.assertEqual(self.keys(), [])

    def test_thieu_bien_moi_truong(self):
        code, _, err = self.main(["--confirm-real", "--no-publish"], {"BO19_OBJECT_STORAGE_BUCKET": "x"})
        self.assertEqual(code, 2)
        self.assertIn("S7_PROBE_CONFIG_MISSING", err)
        for name in ("ENDPOINT_URL", "REGION", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY"):
            self.assertIn(name, err)
        self.assertNotIn("BO19_OBJECT_STORAGE_BUCKET", err)  # có rồi thì không báo thiếu

    def test_nhan_sai(self):
        self.assertEqual(self.main(["--confirm-real", "--label", "R2/x"], self.env())[0], 2)

    def test_chay_het_dat_don_sach_khong_dung_khoa_ngoai_tien_to(self):
        self.raw.put_object(Bucket=self.bucket, Key="giu-nguyen/keep.txt", Body=b"canary")
        self.raw.put_object(Bucket=self.bucket, Key="s7-probe-khac/keep.txt", Body=b"canary2")  # tiền tố gần giống nhưng KHÁC
        with tempfile.TemporaryDirectory() as out_dir, tempfile.TemporaryDirectory() as ref_dir:
            code, out, err = self.main(["--confirm-real", "--label", "seaweed", "--out-dir", out_dir, "--reference-dir", ref_dir], self.env())
            self.assertEqual(code, 0, out + err)
            self.assertIn("S7_PROBE_RESULT ĐẠT", out)
            for cid in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"):
                self.assertRegex(out, rf"S7_PROBE_CHECK {cid} OK")
            self.assertEqual(self.keys(), ["giu-nguyen/keep.txt", "s7-probe-khac/keep.txt"])
            self.assertEqual(self.raw_get("giu-nguyen/keep.txt"), b"canary")
            self.assertRegex(out, r'S7_PROBE_CLEANUP \{"deleted": \d+, "failed": 0, "left": 0\}')
            published = (Path(ref_dir) / "object-storage-s7-seaweed.md").read_text(encoding="utf-8")
            self.assertTrue((Path(out_dir) / "s7-seaweed.md").is_file())
        for secret in (s3_support.ENDPOINT, self.bucket, os.environ["BO19_TEST_S3_ACCESS_KEY_ID"], os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"]):
            self.assertNotIn(secret, published)
            self.assertNotIn(secret, out + err)
        self.assertIn("Không chạy", published)
        self.assertIn("`region` = `us-east-1`", published)

    def test_no_publish_khong_ghi_docs(self):
        with tempfile.TemporaryDirectory() as out_dir, tempfile.TemporaryDirectory() as ref_dir:
            code, out, err = self.main(["--confirm-real", "--no-publish", "--out-dir", out_dir, "--reference-dir", ref_dir], self.env())
            self.assertEqual(code, 0, out + err)
            self.assertEqual(list(Path(ref_dir).iterdir()), [])
            self.assertTrue((Path(out_dir) / "s7-r2.md").is_file())

    def test_self_check_khong_dat_thi_khong_ghi_file(self):
        """Kết quả chứa endpoint (giả lập lỗi dựng bảng) → mã 1, không ghi file nào, và vẫn dọn bucket."""
        with tempfile.TemporaryDirectory() as out_dir, tempfile.TemporaryDirectory() as ref_dir:
            with mock.patch.object(contract, "render_markdown", return_value="bảng có chứa " + s3_support.ENDPOINT):
                code, out, err = self.main(["--confirm-real", "--out-dir", out_dir, "--reference-dir", ref_dir], self.env())
            self.assertEqual(code, 1)
            self.assertIn("KHÔNG ĐẠT", err)
            self.assertEqual(list(Path(out_dir).iterdir()) + list(Path(ref_dir).iterdir()), [])
        self.assertEqual(self.keys(), [])  # kể cả khi self_check hỏng, đã dọn

    def test_nha_cung_cap_khong_co_dieu_kien_thi_phep_thu_bat_duoc(self):
        """Nhà cung cấp GIẢ chấp nhận ghi đè (không có `If-None-Match`): C2 và C4 phải đỏ, mã thoát 1 — để tool không "đạt" nhầm."""
        def unconditional(self_, key, data, *, content_type, metadata=None):
            self_._client.put_object(Bucket=self_.bucket, Key=key, Body=data, ContentType=content_type, Metadata=metadata or {})  # bỏ IfNoneMatch

        with tempfile.TemporaryDirectory() as out_dir, mock.patch.object(contract.ObjectStorage, "put_if_absent", unconditional):
            code, out, err = self.main(["--confirm-real", "--no-publish", "--out-dir", out_dir], self.env())
        self.assertEqual(code, 1, out + err)
        self.assertRegex(out, r"S7_PROBE_CHECK C2 FAIL")
        self.assertRegex(out, r"S7_PROBE_CHECK C4 FAIL")
        self.assertEqual(self.keys(), [])

    def test_khong_xoa_khoa_ngoai_tien_to_ke_ca_khi_listing_tra_thua(self):
        """Chốt chặn thứ hai ở phía client: dù `list_keys` trả khoá ngoài tiền tố, `cleanup` không xoá chúng."""
        self.raw.put_object(Bucket=self.bucket, Key="ngoai/keep.txt", Body=b"x")
        suite = contract.Suite(contract.Settings(**dict(zip(("endpoint_url", "bucket", "region", "access_key_id", "secret_access_key"),
                                                            (s3_support.ENDPOINT, self.bucket, "us-east-1", os.environ["BO19_TEST_S3_ACCESS_KEY_ID"], os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"])))), "abc123")
        import datetime as dt
        with mock.patch.object(suite.storage, "list_keys", return_value=iter([("ngoai/keep.txt", dt.datetime.now(dt.timezone.utc))])):
            res = suite.cleanup()
        self.assertEqual(res["deleted"], 0)
        self.assertEqual(self.keys(), ["ngoai/keep.txt"])


if __name__ == "__main__":
    unittest.main()
