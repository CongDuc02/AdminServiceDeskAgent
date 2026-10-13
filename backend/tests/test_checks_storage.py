"""Cấu hình object storage trong `Settings` và bước kiểm khởi động #14 (B8a; mục Bước kiểm khởi động của 06-structure.md).

Điều được chứng minh, nói bằng hành vi:
- nhóm biến vắng hẳn là hợp lệ (chưa dùng); có một phần thì mọi phần còn lại bắt buộc — mỗi biến thiếu một mã; `https://` bắt buộc ngoài `dev`, `http://` chỉ ở `dev` (SeaweedFS local);
- hai khoá không bao giờ vào `repr` của `Settings` hay `problems`;
- #14 là CẢNH BÁO, không chặn: nhóm vắng → `STARTUP_14_NOT_CONFIGURED`; bucket không với tới / sai credential → `STARTUP_14_UNREACHABLE`; đạt khi bucket với tới được bằng đúng credential (SeaweedFS 4.47 thật);
- mã cảnh báo không mang endpoint, bucket hay credential.

Cần BO19_TEST_S3_ENDPOINT cho các ca với server thật (CI đặt BO19_REQUIRE_S3=1). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_checks_storage -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import os
import unittest
import uuid
from pathlib import Path

from bo19.config.settings import load_settings
from bo19.startup.checks_storage import step_14
from bo19.startup.model import Context, Entry, MATRIX
from tests.s3_support import ENDPOINT, REQUIRED, S3Base

BASE = {"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": "x", "BO19_SESSION_SECRET": "y" * 32}
AK, SK = "AK_BI_MAT_9f3a", "SK_BI_MAT_9f3a"
FULL = {"BO19_OBJECT_STORAGE_ENDPOINT_URL": "http://localhost:8333", "BO19_OBJECT_STORAGE_BUCKET": "bucket-gia", "BO19_OBJECT_STORAGE_ACCESS_KEY_ID": AK, "BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY": SK}


def settings(**env):
    return load_settings({**BASE, **env})


class CauHinh(unittest.TestCase):
    def test_vang_ca_nhom_la_hop_le(self):
        s = settings()
        self.assertEqual(s.problems, ())
        self.assertEqual((s.object_storage_endpoint_url, s.object_storage_bucket, s.object_storage_region), (None, None, "us-east-1"))

    def test_day_du_o_dev_nhan_http(self):
        s = settings(**FULL)
        self.assertEqual(s.problems, ())
        self.assertEqual((s.object_storage_endpoint_url, s.object_storage_bucket, s.object_storage_access_key_id, s.object_storage_secret_access_key), ("http://localhost:8333", "bucket-gia", AK, SK))

    def test_co_mot_phan_thi_phan_con_lai_la_van_de(self):
        for present in FULL:
            s = settings(**{present: FULL[present]})
            missing = {k for k in FULL if k != present}
            codes = {dict(s.problems).get(name) for name in ("object_storage_endpoint_url", "object_storage_bucket", "object_storage_access_key_id", "object_storage_secret_access_key")} - {None}
            self.assertEqual(len(codes), 3, present)
            self.assertTrue(all(c.endswith("_MISSING") for c in codes))
            self.assertTrue(all(env.removeprefix("BO19_") in " ".join(codes) for env in missing))

    def test_ngoai_dev_bat_buoc_https(self):
        for env in ("staging", "prod"):
            s = settings(**{**FULL, "BO19_ENVIRONMENT": env})
            self.assertEqual(dict(s.problems).get("object_storage_endpoint_url"), "CONFIG_OBJECT_STORAGE_ENDPOINT_URL_INVALID", env)
            self.assertIsNone(s.object_storage_endpoint_url)
            ok = settings(**{**FULL, "BO19_ENVIRONMENT": env, "BO19_OBJECT_STORAGE_ENDPOINT_URL": "https://s3.example.test"})
            self.assertEqual(ok.problems, (), env)

    def test_endpoint_hong(self):
        for bad in ("ftp://x", "localhost:8333", "http://", "http://co khoang trang", "javascript:alert(1)"):
            s = settings(**{**FULL, "BO19_OBJECT_STORAGE_ENDPOINT_URL": bad})
            self.assertEqual(dict(s.problems).get("object_storage_endpoint_url"), "CONFIG_OBJECT_STORAGE_ENDPOINT_URL_INVALID", bad)

    def test_hai_khoa_khong_lo_qua_repr_hay_problems(self):
        s = settings(**{**FULL, "BO19_OBJECT_STORAGE_BUCKET": " "})  # bucket thiếu → có problems
        blob = repr(s) + repr(s.problems)
        self.assertNotIn(AK, blob)
        self.assertNotIn(SK, blob)
        self.assertIn("<ẩn>", repr(s))

    def test_vung_tuy_chinh(self):
        self.assertEqual(settings(**FULL, BO19_OBJECT_STORAGE_REGION="ap-southeast-1").object_storage_region, "ap-southeast-1")

    def test_ma_van_de_khong_mang_gia_tri(self):
        s = settings(BO19_OBJECT_STORAGE_ENDPOINT_URL="http://mat.khau:SK_BI_MAT_9f3a@host:1")
        self.assertNotIn("SK_BI_MAT_9f3a", repr(s.problems))

    def test_bang_ma_tran_buoc_14_la_canh_bao_cho_api_va_worker(self):
        (step,) = [s for s in MATRIX if s.number == "14"]
        self.assertEqual((step.level.value, sorted(e.value for e in step.entries)), ("WARN", ["api", "worker"]))


class Buoc14(S3Base):
    def ctx(self, **env) -> Context:
        return Context(Entry.WORKER, settings(**env), {}, None, Path("."))

    def good(self, **over) -> dict[str, str]:
        return {"BO19_OBJECT_STORAGE_ENDPOINT_URL": ENDPOINT, "BO19_OBJECT_STORAGE_BUCKET": self.bucket, "BO19_OBJECT_STORAGE_ACCESS_KEY_ID": os.environ["BO19_TEST_S3_ACCESS_KEY_ID"],
                "BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY": os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"], **over}

    def test_dat_khi_bucket_voi_toi_duoc(self):
        self.assertEqual(step_14(self.ctx(**self.good())).codes, ())

    def test_chua_cau_hinh(self):
        self.assertEqual(step_14(self.ctx()).codes, ("STARTUP_14_NOT_CONFIGURED",))

    def test_bucket_khong_co(self):
        self.assertEqual(step_14(self.ctx(**self.good(BO19_OBJECT_STORAGE_BUCKET=f"khong-co-{uuid.uuid4().hex[:8]}"))).codes, ("STARTUP_14_UNREACHABLE",))

    def test_sai_credential(self):
        self.assertEqual(step_14(self.ctx(**self.good(BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY="sai"))).codes, ("STARTUP_14_UNREACHABLE",))

    def test_khong_toi_duoc_host(self):
        self.assertEqual(step_14(self.ctx(**self.good(BO19_OBJECT_STORAGE_ENDPOINT_URL="http://127.0.0.1:9", BO19_OBJECT_STORAGE_TIMEOUT_SECONDS="1"))).codes, ("STARTUP_14_UNREACHABLE",))

    def test_ma_canh_bao_khong_mang_endpoint_bucket_hay_khoa(self):
        codes = step_14(self.ctx(**self.good(BO19_OBJECT_STORAGE_SECRET_ACCESS_KEY="sai"))).codes
        blob = " ".join(codes)
        for secret in (ENDPOINT, self.bucket, "sai", os.environ["BO19_TEST_S3_ACCESS_KEY_ID"]):
            self.assertNotIn(secret, blob)

    def test_ham_dung_adapter_chi_qua_tool_layer_storage(self):
        from bo19.tool_layer.storage import from_settings
        self.assertIsNone(from_settings(settings()))
        adapter = from_settings(settings(**self.good()))
        self.assertTrue(adapter.reachable())
        self.assertNotIn(os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"], repr(adapter))


if __name__ == "__main__":
    unittest.main()
