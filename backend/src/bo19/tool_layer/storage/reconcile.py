"""`object_claim_reconcile` — đối soát claim `stored_object` chưa commit đã hết lease (ca (b) của mục 5.4 của 04-data.md; mục 5.3 của 03-agents.md).

Chạy theo lịch (Cron Job của `queue_worker`; lịch ở chỗ khác — B8a chỉ có thao tác). Với mỗi claim **chưa có commit và đã hết lease**, theo đúng thứ tự của thiết kế: (1) xoá object ở `object_storage` nếu có,
(2) xoá dòng `stored_object`. An toàn vì **không có gì trong DB trỏ tới một object chưa commit** (khoá ngoại của `document_render`). Lần thử lại của job giành claim mới từ đầu; người giữ claim cũ mà hoá ra còn sống
thì commit muộn bị khoá ngoại ghép từ chối (`ClaimLost`) — không bao giờ thành chuẩn.

Ca object lạ (A-084): một lệnh ghi trễ của claim cũ để lại byte trên storage sau khi claim đã dọn — lần reconcile sau claim mới hết lease cũng xoá nó.

Xoá object trước, xoá dòng sau: chết giữa hai bước thì claim còn nguyên và lần chạy sau dọn tiếp (không để lại object không có dòng nào). Một claim mà storage không xoá được (lỗi tạm) thì giữ nguyên dòng, tính vào `failed`.
Dòng đã có commit (xảy ra giữa lúc chọn và lúc xoá) bị khoá ngoại chặn xoá — bỏ qua, tính vào `skipped`. Không `audit_event`: sổ sách kỹ thuật, không đổi dữ liệu nghiệp vụ.
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg

from bo19.object_storage import ObjectStorage, StorageError
from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work


@dataclass(frozen=True)
class ReconcileResult:
    removed: int  # dòng claim đã xoá
    objects_deleted: int  # đã gọi xoá object (kể cả khoá không có object)
    failed: int  # storage lỗi — dòng giữ nguyên, lần sau thử lại
    skipped: int  # đã được commit hoặc claim đã bị người khác dọn giữa chừng


def object_claim_reconcile(pool: Pool, storage: ObjectStorage, *, limit: int = 100) -> ReconcileResult:
    with pool.acquire() as conn, unit_of_work(conn):
        stale = conn.execute("SELECT s.object_key, s.claim_token FROM stored_object s WHERE s.lease_expires_at < now() "
                             "AND NOT EXISTS (SELECT 1 FROM stored_object_commit c WHERE c.object_key = s.object_key) ORDER BY s.lease_expires_at, s.object_key LIMIT %s", (limit,)).fetchall()
    removed = objects = failed = skipped = 0
    for key, token in stale:
        try:
            storage.delete(key)
        except StorageError:
            failed += 1
            continue
        objects += 1
        with pool.acquire() as conn, unit_of_work(conn):
            try:
                with conn.transaction():
                    deleted = conn.execute("DELETE FROM stored_object WHERE object_key = %s AND claim_token = %s AND lease_expires_at < now() RETURNING object_key", (key, token)).fetchone()
            except psycopg.errors.ForeignKeyViolation:
                skipped += 1  # commit xuất hiện giữa chừng: khoá ngoại giữ dòng claim
                continue
        if deleted is None:
            skipped += 1
        else:
            removed += 1
    return ReconcileResult(removed, objects, failed, skipped)
