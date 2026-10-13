"""Nền chung cho test chạm object storage THẬT (B8a): SeaweedFS 4.47 do `tools/object-storage-local/start.sh` dựng, nối qua `BO19_TEST_S3_ENDPOINT`, `BO19_TEST_S3_ACCESS_KEY_ID`,
`BO19_TEST_S3_SECRET_ACCESS_KEY`. Không có test nào ở đây.

Thiếu endpoint thì test tự bỏ qua — **trừ khi `BO19_REQUIRE_S3=1`** (CI đặt): khi đó thiếu endpoint là LỖI, không phải bỏ qua, để một CI cấu hình hỏng không im lặng bỏ cả nhóm test này (điều kiện duyệt Q1 của ADR-037).
Mỗi test dùng một bucket riêng (có versioning, như ADR-031) nên không đè lên nhau và `list_keys` chỉ thấy dữ liệu của mình.
"""
from __future__ import annotations

import os
import unittest
import uuid

import boto3
from botocore.config import Config

from bo19.object_storage import ObjectStorage, ObjectStorageConfig

ENDPOINT = os.environ.get("BO19_TEST_S3_ENDPOINT")
REQUIRED = os.environ.get("BO19_REQUIRE_S3") == "1"


def admin_client():
    return boto3.client("s3", endpoint_url=ENDPOINT, region_name="us-east-1", aws_access_key_id=os.environ["BO19_TEST_S3_ACCESS_KEY_ID"],
                        aws_secret_access_key=os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"],
                        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 1}))


def new_bucket(versioning: bool = False) -> str:
    """Một bucket mới. Mặc định KHÔNG versioning (chỉ test T10 cần); bucket phải được xoá sau test (`drop_bucket`) — mỗi bucket giữ volume của SeaweedFS, và `-volume.max=200` cạn sau vài chục bucket (ADR-031)."""
    name = f"t{uuid.uuid4().hex[:20]}"
    client = admin_client()
    client.create_bucket(Bucket=name)
    if versioning:
        client.put_bucket_versioning(Bucket=name, VersioningConfiguration={"Status": "Enabled"})
    return name


def drop_bucket(name: str) -> None:
    """Xoá mọi version, delete marker và object rồi xoá bucket. Lỗi dọn dẹp không được làm hỏng test."""
    client = admin_client()
    try:
        for page in client.get_paginator("list_object_versions").paginate(Bucket=name):
            for item in [*page.get("Versions", []), *page.get("DeleteMarkers", [])]:
                client.delete_object(Bucket=name, Key=item["Key"], VersionId=item["VersionId"])
        client.delete_bucket(Bucket=name)
    except Exception:  # noqa: BLE001
        pass


def storage_for(bucket: str, timeout_s: int = 30) -> ObjectStorage:
    return ObjectStorage(ObjectStorageConfig(endpoint_url=ENDPOINT, bucket=bucket, access_key_id=os.environ["BO19_TEST_S3_ACCESS_KEY_ID"],
                                             secret_access_key=os.environ["BO19_TEST_S3_SECRET_ACCESS_KEY"], timeout_s=timeout_s))


class S3Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENDPOINT:
            if REQUIRED:
                raise AssertionError("BO19_REQUIRE_S3=1 nhưng thiếu BO19_TEST_S3_ENDPOINT — test object storage không được bỏ qua trong CI")
            raise unittest.SkipTest("cần BO19_TEST_S3_ENDPOINT (tools/object-storage-local/start.sh)")

    def setUp(self):
        self.bucket = new_bucket()
        self.addCleanup(drop_bucket, self.bucket)
        self.storage = storage_for(self.bucket)
        self.raw = admin_client()

    def raw_get(self, key: str) -> bytes:
        return self.raw.get_object(Bucket=self.bucket, Key=key)["Body"].read()
