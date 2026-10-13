"""Adapter S3-compatible — MỘT adapter cho mọi môi trường (ADR-003, ADR-031, ADR-037). Chỉ `tool_layer.storage` được import; `boto3`/`botocore` chỉ được import ở đây (contract `object-storage`).

**Mọi `PUT` mang `If-None-Match: *`** (`put_object(IfNoneMatch="*")`): bảo vệ nằm ở header adapter gửi, không ở sản phẩm (ADR-031, T8). Adapter **không có đường ghi nào khác** và không có tham số tắt điều kiện.
Khoá đã có thì storage trả `412 PreconditionFailed` → `AlreadyExists`; byte cũ nguyên vẹn. Quyết định làm gì với 412 (đọc lại, so checksum — A-084) là việc của `tool_layer.storage`, không phải của adapter.

Không retry: `retries.max_attempts = 1` — retry là việc của tầng trên, không chồng hai lớp. Timeout kết nối và đọc theo WV-08. Credential không bao giờ vào `repr`, log hay thông điệp lỗi: lỗi chỉ mang mã.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from dataclasses import dataclass, field

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

ALREADY_EXISTS, OBJECT_MISSING, ACCESS_DENIED, UNAVAILABLE = "ALREADY_EXISTS", "OBJECT_MISSING", "ACCESS_DENIED", "STORAGE_UNAVAILABLE"


class StorageError(Exception):
    """Lỗi của adapter. Chỉ mang một mã — thông điệp của botocore có thể chứa endpoint, tên bucket hay khoá."""

    code = UNAVAILABLE

    def __init__(self, code: str | None = None) -> None:
        super().__init__(code or self.code)
        if code:
            self.code = code


class AlreadyExists(StorageError):
    code = ALREADY_EXISTS


class ObjectMissing(StorageError):
    code = OBJECT_MISSING


@dataclass(frozen=True)
class ObjectStorageConfig:
    endpoint_url: str
    bucket: str
    access_key_id: str = field(repr=False)
    secret_access_key: str = field(repr=False)
    region: str = "us-east-1"
    timeout_s: int = 30  # WV-08


@dataclass(frozen=True)
class ObjectInfo:
    size_bytes: int
    last_modified: dt.datetime
    metadata: dict[str, str]


class ObjectStorage:
    def __init__(self, config: ObjectStorageConfig) -> None:
        self.bucket = config.bucket
        self._client = boto3.client(
            "s3", endpoint_url=config.endpoint_url, region_name=config.region, aws_access_key_id=config.access_key_id, aws_secret_access_key=config.secret_access_key,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 1}, connect_timeout=config.timeout_s, read_timeout=config.timeout_s))

    def __repr__(self) -> str:
        return f"ObjectStorage(bucket={self.bucket!r})"

    # ---- ghi -------------------------------------------------------------------------------------------------------------------

    def put_if_absent(self, key: str, data: bytes, *, content_type: str, metadata: dict[str, str] | None = None) -> None:
        """Ghi `data` chỉ khi `key` chưa có. Đã có → `AlreadyExists` (byte cũ nguyên vẹn). `metadata` đi trong CÙNG lệnh `PUT` (mục Giao thức ghi một lần của 04-data.md)."""
        try:
            self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, Metadata=metadata or {}, IfNoneMatch="*")
        except ClientError as e:
            raise self._translate(e) from None
        except BotoCoreError:
            raise StorageError(UNAVAILABLE) from None

    # ---- đọc -------------------------------------------------------------------------------------------------------------------

    def get(self, key: str) -> bytes:
        try:
            return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as e:
            raise self._translate(e) from None
        except BotoCoreError:
            raise StorageError(UNAVAILABLE) from None

    def head(self, key: str) -> ObjectInfo | None:
        try:
            r = self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            error = self._translate(e)
            if isinstance(error, ObjectMissing):
                return None
            raise error from None
        except BotoCoreError:
            raise StorageError(UNAVAILABLE) from None
        return ObjectInfo(int(r["ContentLength"]), r["LastModified"], dict(r.get("Metadata") or {}))

    def list_keys(self, prefix: str) -> Iterator[tuple[str, dt.datetime]]:
        """(khoá, thời điểm sửa) của mọi object có tiền tố — cho `object_claim_reconcile`."""
        token: str | None = None
        while True:
            try:
                r = self._client.list_objects_v2(Bucket=self.bucket, Prefix=prefix, **({"ContinuationToken": token} if token else {}))
            except ClientError as e:
                raise self._translate(e) from None
            except BotoCoreError:
                raise StorageError(UNAVAILABLE) from None
            for item in r.get("Contents", []):
                yield item["Key"], item["LastModified"]
            if not r.get("IsTruncated"):
                return
            token = r["NextContinuationToken"]

    def delete(self, key: str) -> None:
        """Xoá một object. Không có thì không lỗi (S3 xoá idempotent). Chỉ dùng trong `object_claim_reconcile` và dọn bản trung gian — không bao giờ xoá bản đã commit."""
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            raise self._translate(e) from None
        except BotoCoreError:
            raise StorageError(UNAVAILABLE) from None

    def reachable(self) -> bool:
        """Bước kiểm khởi động #14: bucket với tới được bằng đúng credential. Chỉ `True`/`False` — không thông điệp."""
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return True
        except (ClientError, BotoCoreError):
            return False

    @staticmethod
    def _translate(e: ClientError) -> StorageError:
        code = str(e.response.get("Error", {}).get("Code", ""))
        status = int(e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0)
        if code == "PreconditionFailed" or status == 412:
            return AlreadyExists()
        if code in ("NoSuchKey", "NotFound", "404") or status == 404:
            return ObjectMissing()
        if code in ("AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "403") or status == 403:
            return StorageError(ACCESS_DENIED)
        return StorageError(UNAVAILABLE)
