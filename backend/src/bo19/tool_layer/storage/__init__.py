"""Giao thức ghi một lần — NƠI DUY NHẤT ghi `stored_object` và `stored_object_commit` (mục Lưu trữ file và bất biến bản render của 04-data.md, mục 5.3 và 5.4; ADR-003, ADR-031, ADR-037; A-084).

`put_once` — bản render, bản gốc template và mọi object khác đi qua đúng một đường:

1. **Đã có commit** cho khoá → dùng khoá và checksum của lần ghi đầu, **bỏ** chuỗi byte vừa tạo, không ghi (ca (a): giao job ít nhất một lần, retry, hai worker cùng một job là chuyện bình thường).
2. **Giành khoá** — một giao dịch riêng, commit ngay: thêm dòng `stored_object` (`claim_token` mới, lease). Khoá chính quyết định ai thắng. Khoá đã có claim chưa commit: lease còn hạn → `ClaimHeld` (người gọi trả job về hàng đợi,
   không ghi); lease đã hết → `ClaimStale` (ca (b): `object_claim_reconcile` dọn rồi thử lại).
3. **Kiểm lease còn hạn lúc BẮT ĐẦU ghi** — hết hạn thì `LeaseExpired`, không `PUT`.
4. **`PUT` ghi có điều kiện** (adapter luôn gửi `If-None-Match: *`). Nhận **412** (A-084): đọc lại object đang có, tính checksum trên **byte đọc lại**; **khớp** checksum của chuỗi byte mình vừa gửi → coi là ghi thành công (lần ghi trước
   của chính mình đã tới storage, response bị mất); **lệch** → KHÔNG commit, `StorageWriteConflict` — byte trên storage là của người khác (lệnh ghi trễ của một claim cũ).
5. **Commit** — thêm dòng `stored_object_commit` với checksum của đúng chuỗi byte vừa ghi. Khoá ngoại ghép (`object_key`, `committed_claim_token`) chỉ nhận đúng `claim_token` của dòng claim: claim đã bị dọn (`object_claim_reconcile`)
   thì commit muộn bị từ chối → `ClaimLost`. Checksum ghi đúng một lần (khoá chính; bảng không có quyền `UPDATE`) — checksum của lần ghi đầu là chuẩn.

**Rủi ro còn lại, nói thẳng** (mục 5.4 của 04-data.md): DB chặn mọi lệnh ghi MỚI nhưng không thu hồi được lệnh ghi ĐÃ gửi đi; lease dài hơn hẳn timeout của tool (WV-10 > WV-08) và `render_integrity_check` ngay trước người đầu tiên dựa vào byte thu hẹp nó;
cơ chế ở tầng lưu trữ của A-024 (ở đây: ghi có điều kiện, ADR-037) đóng nó.

`fetch` (B8b) đọc ngược: kiểm checksum rồi mới trả byte. Lỗi chỉ mang mã. Không `audit_event`: đây là tầng kỹ thuật; thao tác gọi nó (`docx_render`, `pdf_export`, `stored_file_fetch`) ghi `audit_event` của chính nó.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

import psycopg

from bo19.config.settings import Settings
from bo19.object_storage import AlreadyExists, ObjectMissing, ObjectStorage, ObjectStorageConfig, StorageError
from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.tools._common import ToolError

PURPOSES = ("TEMPLATE_SOURCE", "RENDER_DOCX", "RENDER_PDF", "PROCEDURE_SOURCE")  # khớp ck_stored_object_purpose


class ClaimHeld(ToolError):
    code = "CLAIM_HELD"  # người khác đang giữ claim còn hạn: không ghi, trả job về hàng đợi


class ClaimStale(ToolError):
    code = "CLAIM_STALE"  # claim chưa commit đã hết lease: chờ `object_claim_reconcile` rồi thử lại


class LeaseExpired(ToolError):
    code = "CLAIM_LEASE_EXPIRED"  # claim của chính mình hết lease trước khi bắt đầu ghi: không `PUT`


class ClaimLost(ToolError):
    code = "CLAIM_LOST"  # lúc commit, claim của mình không còn (đã bị dọn): không commit


class StorageWriteConflict(ToolError):
    code = "STORAGE_WRITE_CONFLICT"  # 412 và byte trên storage khác byte mình gửi (A-084)


def from_settings(settings: Settings) -> ObjectStorage | None:
    """Adapter dựng từ cấu hình; `None` khi nhóm biến object storage vắng (chưa dùng — bước kiểm #14 cảnh báo). Cấu hình có lỗi thì `Settings.problems` đã chặn từ trước."""
    s = settings
    if not (s.object_storage_endpoint_url and s.object_storage_bucket and s.object_storage_access_key_id and s.object_storage_secret_access_key):
        return None
    return ObjectStorage(ObjectStorageConfig(endpoint_url=s.object_storage_endpoint_url, bucket=s.object_storage_bucket, access_key_id=s.object_storage_access_key_id,
                                             secret_access_key=s.object_storage_secret_access_key, region=s.object_storage_region, timeout_s=s.object_storage_timeout_s or 30))


@dataclass(frozen=True)
class StoredObject:
    object_key: str
    checksum_sha256: bytes
    size_bytes: int
    reused: bool  # True: đã có commit từ trước — byte vừa tạo bị bỏ, không ghi


def _committed(conn: psycopg.Connection, key: str) -> tuple[bytes, int] | None:
    row = conn.execute("SELECT checksum_sha256, size_bytes FROM stored_object_commit WHERE object_key = %s", (key,)).fetchone()
    return (bytes(row[0]), row[1]) if row else None


def _claim(pool: Pool, key: str, purpose: str, content_type: str, lease_s: float) -> uuid.UUID | StoredObject:
    """Giành khoá. Trả `claim_token` nếu thắng; `StoredObject` (reused) nếu đã có commit; ném `ClaimHeld`/`ClaimStale` nếu người khác giữ."""
    for _ in range(3):  # claim có thể biến mất giữa hai câu lệnh (đối soát dọn đúng lúc) — thử lại
        with pool.acquire() as conn, unit_of_work(conn):
            token = uuid.uuid4()
            row = conn.execute("INSERT INTO stored_object (object_key, purpose, content_type, claim_token, lease_expires_at) VALUES (%s, %s, %s, %s, now() + make_interval(secs => %s)) "
                               "ON CONFLICT (object_key) DO NOTHING RETURNING claim_token", (key, purpose, content_type, token, lease_s)).fetchone()
            if row is not None:
                return row[0]
            done = _committed(conn, key)
            if done is not None:
                return StoredObject(key, done[0], done[1], reused=True)
            held = conn.execute("SELECT lease_expires_at > now() FROM stored_object WHERE object_key = %s", (key,)).fetchone()
            if held is None:
                continue
            raise ClaimHeld if held[0] else ClaimStale
    raise ClaimHeld


def _lease_valid(pool: Pool, key: str, token: uuid.UUID) -> bool:
    with pool.acquire() as conn, unit_of_work(conn):
        row = conn.execute("SELECT lease_expires_at > now() FROM stored_object WHERE object_key = %s AND claim_token = %s", (key, token)).fetchone()
    return bool(row and row[0])


def _commit(pool: Pool, key: str, token: uuid.UUID, checksum: bytes, size: int) -> None:
    with pool.acquire() as conn, unit_of_work(conn):
        try:
            with conn.transaction():  # savepoint: bắt lỗi toàn vẹn TRƯỚC khi `unit_of_work` quy về mã chung
                conn.execute("INSERT INTO stored_object_commit (object_key, committed_claim_token, checksum_sha256, size_bytes) VALUES (%s, %s, %s, %s)", (key, token, checksum, size))
        except psycopg.errors.ForeignKeyViolation:
            raise ClaimLost from None  # claim của mình đã bị dọn — commit muộn của claim cũ không bao giờ thành chuẩn
        except psycopg.errors.UniqueViolation:
            return  # đã có commit (checksum của lần ghi đầu là chuẩn): không ghi đè — chỉ xảy ra khi chính mình đã commit rồi


def put_once(pool: Pool, storage: ObjectStorage, *, object_key: str, purpose: str, content_type: str, data: bytes, lease_s: float, metadata: dict[str, str] | None = None) -> StoredObject:
    """`lease_s` — lease của `stored_object` (WV-10, `BO19_STORED_OBJECT_LEASE_SECONDS`); người gọi truyền từ cấu hình. `metadata` đi trong CÙNG lệnh `PUT`."""
    if purpose not in PURPOSES:
        raise ValueError("purpose")
    checksum, size = hashlib.sha256(data).digest(), len(data)
    with pool.acquire() as conn, unit_of_work(conn):
        done = _committed(conn, object_key)
    if done is not None:
        return StoredObject(object_key, done[0], done[1], reused=True)  # ca (a): dùng object đã có, bỏ byte vừa tạo
    claimed = _claim(pool, object_key, purpose, content_type, lease_s)
    if isinstance(claimed, StoredObject):
        return claimed
    token = claimed
    if not _lease_valid(pool, object_key, token):
        raise LeaseExpired
    try:
        storage.put_if_absent(object_key, data, content_type=content_type, metadata=metadata)
    except AlreadyExists:
        existing = storage.get(object_key)  # byte ĐỌC LẠI, không dựa vào trường nào storage tự trả về
        if hashlib.sha256(existing).digest() != checksum:
            raise StorageWriteConflict from None
    _commit(pool, object_key, token, checksum, size)
    return StoredObject(object_key, checksum, size, reused=False)


class FileUnavailable(ToolError):
    code = "FILE_UNAVAILABLE"  # mất object, lệch checksum, quá trần kích thước, storage không với tới — GỘP một mã (05-api.md); chi tiết chỉ ở log (`reason`)

    def __init__(self, reason: str) -> None:
        super().__init__()
        self.reason = reason  # MISSING | CHECKSUM_MISMATCH | TOO_LARGE | NOT_COMMITTED | STORAGE_UNAVAILABLE — chỉ cho log, không bao giờ cho client


def fetch(pool: Pool, storage: ObjectStorage, object_key: str, *, max_bytes: int) -> bytes:
    """Đọc một object đã commit và **kiểm checksum trước khi trả byte đầu tiên** (ADR-014; `stored_file_fetch` ở mục Tool Registry của 03-agents.md).

    Đọc cả object vào bộ nhớ (trần `max_bytes`, WV-24): checksum chỉ kiểm được khi đã có đủ byte, mà byte đầu tiên không được ra trước khi kiểm. Trần được so với `size_bytes` đã commit **trước khi** đọc;
    byte đọc về còn bị so độ dài lần nữa (storage có thể trả nhiều hơn đã commit). Thiếu dòng commit (claim chưa commit, khoá lạ), object mất, lệch checksum, quá trần, storage không với tới:
    đều `FileUnavailable` — người gọi không phân biệt được (không lộ đã mất hay đã bị sửa); `reason` chỉ để log.
    """
    with pool.acquire() as conn, unit_of_work(conn):
        done = _committed(conn, object_key)
    if done is None:
        raise FileUnavailable("NOT_COMMITTED")
    checksum, size = done
    if size > max_bytes:
        raise FileUnavailable("TOO_LARGE")
    try:
        data = storage.get(object_key)
    except ObjectMissing:
        raise FileUnavailable("MISSING") from None
    except StorageError:
        raise FileUnavailable("STORAGE_UNAVAILABLE") from None
    if len(data) != size or hashlib.sha256(data).digest() != checksum:
        raise FileUnavailable("CHECKSUM_MISMATCH")
    return data


def committed(pool: Pool, object_key: str) -> StoredObject | None:
    """Object đã commit cho khoá này (`reused=True`), hoặc `None`. Cho tool kiểm "đã có chưa" trước khi làm việc nặng (điền biến, chuyển đổi) — ADR-015."""
    with pool.acquire() as conn, unit_of_work(conn):
        done = _committed(conn, object_key)
    return StoredObject(object_key, done[0], done[1], reused=True) if done else None
