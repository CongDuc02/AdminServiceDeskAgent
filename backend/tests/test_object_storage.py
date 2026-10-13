"""Adapter `bo19.object_storage` trên SeaweedFS 4.47 THẬT (B8a, ADR-031, ADR-037).

**Điều kiện duyệt Q1 (PO, 2026-10-13):** `test_dieu_kien_q1_*` chứng minh SeaweedFS trả `412 PreconditionFailed` thật khi `PutObject` kèm `If-None-Match: *` lên khoá đã có, và byte cũ còn nguyên.
Nếu SeaweedFS bỏ qua header (trả 200 và đè) thì test này ĐỎ — người triển khai dừng và báo PO: giao thức ghi một lần phải thiết kế lại.

Cũng chứng minh: mọi `PUT` đi qua `If-None-Match: *` và adapter không có đường ghi nào khác; 8 luồng cùng khoá — đúng một thắng (T6); ghi lại sau khi xoá trên bucket có versioning (T10);
metadata đi trong cùng lệnh `PUT`; lỗi chỉ mang mã (không endpoint, không credential); `reachable` đúng/sai theo credential và bucket.

Cần BO19_TEST_S3_ENDPOINT (CI đặt BO19_REQUIRE_S3=1 nên không bao giờ bị bỏ qua). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_object_storage -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import ast
import hashlib
import inspect
import threading
import unittest
import uuid

from bo19 import object_storage as os_mod
from bo19.object_storage import AlreadyExists, ObjectMissing, ObjectStorage, ObjectStorageConfig, StorageError
from tests.s3_support import ENDPOINT, S3Base, admin_client, drop_bucket, new_bucket, storage_for

KEY = "renders/" + hashlib.sha256(b"khoa-thu").hexdigest()


class DieuKienQ1(S3Base):
    def test_dieu_kien_q1_put_len_khoa_da_co_tra_412_that_va_byte_cu_nguyen_ven(self):
        self.storage.put_if_absent(KEY, b"byte-cu", content_type="application/pdf")
        with self.assertRaises(AlreadyExists) as cm:
            self.storage.put_if_absent(KEY, b"byte-moi-khac-hoan-toan", content_type="application/pdf")
        self.assertEqual(cm.exception.code, "ALREADY_EXISTS")
        self.assertEqual(self.raw_get(KEY), b"byte-cu")  # không bị đè
        self.assertEqual(self.storage.get(KEY), b"byte-cu")

    def test_dieu_kien_q1_phan_hoi_that_cua_server_la_412_precondition_failed(self):
        """Không qua adapter: chính `boto3` thô, để thấy mã HTTP và mã lỗi do SERVER trả — adapter dịch đúng cái server nói, không tự suy ra."""
        from botocore.exceptions import ClientError
        raw = admin_client()
        raw.put_object(Bucket=self.bucket, Key=KEY, Body=b"a", IfNoneMatch="*")
        with self.assertRaises(ClientError) as cm:
            raw.put_object(Bucket=self.bucket, Key=KEY, Body=b"b", IfNoneMatch="*")
        self.assertEqual(cm.exception.response["ResponseMetadata"]["HTTPStatusCode"], 412)
        self.assertEqual(cm.exception.response["Error"]["Code"], "PreconditionFailed")
        self.assertEqual(self.raw_get(KEY), b"a")

    def test_khong_co_header_thi_server_de_len_khong_dieu_kien_nao_ngoai_adapter(self):
        """Đối chứng: không có `If-None-Match` thì PUT đè được (ADR-031, T8) — bảo vệ nằm ở header adapter gửi. Vì vậy adapter không được có đường ghi nào thiếu nó."""
        raw = admin_client()
        raw.put_object(Bucket=self.bucket, Key=KEY, Body=b"a")
        raw.put_object(Bucket=self.bucket, Key=KEY, Body=b"b")  # không điều kiện: đè được
        self.assertEqual(self.raw_get(KEY), b"b")

    def test_adapter_khong_co_duong_ghi_nao_khac(self):
        src = inspect.getsource(os_mod)
        tree = ast.parse(src)
        puts = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "put_object"]
        self.assertEqual(len(puts), 1)  # đúng một chỗ gọi `put_object` trong cả module
        self.assertEqual([(k.arg, getattr(k.value, "value", None)) for k in puts[0].keywords if k.arg == "IfNoneMatch"], [("IfNoneMatch", "*")])
        for forbidden in ("upload_file", "upload_fileobj", "copy_object", "put_object_acl", "create_multipart_upload", "delete_objects"):
            self.assertNotIn(forbidden, src)
        self.assertNotIn("IfNoneMatch=None", src)
        writers = [n for n, _ in inspect.getmembers(ObjectStorage, inspect.isfunction) if n in ("put_if_absent", "put", "write", "overwrite", "upload")]
        self.assertEqual(writers, ["put_if_absent"])


class GhiMotLan(S3Base):
    def test_ghi_doc_lai_va_metadata_trong_cung_lenh_put(self):
        self.storage.put_if_absent(KEY, b"%PDF-gia", content_type="application/pdf", metadata={"x-bo19-pin-reason": "ISSUED", "x-bo19-document-number": "001-gia"})
        self.assertEqual(self.storage.get(KEY), b"%PDF-gia")
        info = self.storage.head(KEY)
        self.assertEqual((info.size_bytes, info.metadata), (8, {"x-bo19-pin-reason": "ISSUED", "x-bo19-document-number": "001-gia"}))

    def test_tam_luong_cung_khoa_dung_mot_nguoi_thang(self):  # T6
        results, barrier = [], threading.Barrier(8)

        def go(i: int):
            barrier.wait()
            try:
                self.storage.put_if_absent(KEY, f"nguoi-{i}".encode(), content_type="application/pdf")
                results.append(("OK", i))
            except AlreadyExists:
                results.append(("EXISTS", i))

        threads = [threading.Thread(target=go, args=(i,)) for i in range(8)]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
        self.assertEqual(len(results), 8)
        winners = [i for s, i in results if s == "OK"]
        self.assertEqual(len(winners), 1, results)
        self.assertEqual(self.raw_get(KEY), f"nguoi-{winners[0]}".encode())

    def test_xoa_roi_ghi_lai_tren_bucket_versioning_va_lenh_ghi_tre_bi_tu_choi(self):  # T10
        bucket = new_bucket(versioning=True)  # ADR-031: bucket local bật versioning
        self.addCleanup(drop_bucket, bucket)
        storage = storage_for(bucket)
        storage.put_if_absent(KEY, b"claim-1", content_type="application/pdf")
        storage.delete(KEY)
        with self.assertRaises(ObjectMissing):
            storage.get(KEY)
        storage.put_if_absent(KEY, b"claim-2", content_type="application/pdf")  # ghi lại sau delete marker: được
        with self.assertRaises(AlreadyExists):
            storage.put_if_absent(KEY, b"claim-1-ghi-tre", content_type="application/pdf")  # lệnh ghi trễ của claim cũ
        self.assertEqual(storage.get(KEY), b"claim-2")

    def test_khoa_khac_nhau_khong_anh_huong_nhau(self):
        self.storage.put_if_absent("a/1", b"1", content_type="text/plain")
        self.storage.put_if_absent("a/2", b"2", content_type="text/plain")
        self.assertEqual((self.storage.get("a/1"), self.storage.get("a/2")), (b"1", b"2"))


class DocXoaLietKe(S3Base):
    def test_get_va_head_khoa_khong_co(self):
        with self.assertRaises(ObjectMissing):
            self.storage.get("khong/co")
        self.assertIsNone(self.storage.head("khong/co"))

    def test_list_keys_theo_tien_to_va_phan_trang(self):
        for i in range(5):
            self.storage.put_if_absent(f"renders/{i}", b"x", content_type="text/plain")
        self.storage.put_if_absent("khac/0", b"x", content_type="text/plain")
        self.assertEqual(sorted(k for k, _ in self.storage.list_keys("renders/")), [f"renders/{i}" for i in range(5)])
        self.assertEqual([k for k, _ in self.storage.list_keys("khac/")], ["khac/0"])
        self.assertEqual(list(self.storage.list_keys("khong-co/")), [])

    def test_delete_khoa_khong_co_khong_loi(self):
        self.storage.delete("khong/co")


class LoiVaBiMat(S3Base):
    def test_loi_chi_mang_ma_khong_endpoint_khong_credential(self):
        bad = ObjectStorage(ObjectStorageConfig(endpoint_url=ENDPOINT, bucket=self.bucket, access_key_id="KHOA_TRUY_CAP_SAI_9f3a", secret_access_key="BI_MAT_SAI_9f3a"))
        with self.assertRaises(StorageError) as cm:
            bad.get(KEY)
        blob = repr(cm.exception) + str(cm.exception) + repr(bad) + repr(vars(cm.exception))
        self.assertEqual(cm.exception.code, "ACCESS_DENIED")
        for secret in ("KHOA_TRUY_CAP_SAI_9f3a", "BI_MAT_SAI_9f3a", ENDPOINT):  # bucket không phải secret: `repr` của adapter có tên bucket
            self.assertNotIn(secret, blob)

    def test_config_khong_lo_credential_qua_repr(self):
        cfg = ObjectStorageConfig(endpoint_url="http://x", bucket="b", access_key_id="AK_9f3a", secret_access_key="SK_9f3a")
        self.assertNotIn("AK_9f3a", repr(cfg))
        self.assertNotIn("SK_9f3a", repr(cfg))

    def test_reachable(self):
        self.assertTrue(self.storage.reachable())
        self.assertFalse(storage_for(f"khong-co-{uuid.uuid4().hex[:8]}").reachable())
        bad = ObjectStorage(ObjectStorageConfig(endpoint_url=ENDPOINT, bucket=self.bucket, access_key_id="sai", secret_access_key="sai"))
        self.assertFalse(bad.reachable())
        down = ObjectStorage(ObjectStorageConfig(endpoint_url="http://127.0.0.1:9", bucket=self.bucket, access_key_id="a", secret_access_key="b", timeout_s=1))
        self.assertFalse(down.reachable())

    def test_khong_o_noi_nao_khac_import_boto3(self):
        import pathlib
        root = pathlib.Path(os_mod.__file__).resolve().parents[1]
        offenders = [str(p.relative_to(root)) for p in root.rglob("*.py") if "object_storage" not in p.parts and any(
            line.startswith(("import boto3", "from boto3", "import botocore", "from botocore")) for line in p.read_text(encoding="utf-8").splitlines())]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
