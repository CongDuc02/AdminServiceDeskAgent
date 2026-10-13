"""`bo19.tool_layer.storage` — giao thức ghi một lần và `object_claim_reconcile` (B8a; mục Lưu trữ file và bất biến bản render của 04-data.md, mục 5.3 và 5.4; A-084), trên PostgreSQL THẬT (role `bo19_app`)
và SeaweedFS 4.47 THẬT.

Điều được chứng minh, nói bằng hành vi:
- **ca (a)** render lại cùng khoá: dùng object và checksum của lần ghi đầu, không `PUT` lần hai; tám luồng cùng khoá: đúng một `PUT`, một commit;
- **claim:** lease còn hạn → `ClaimHeld`, không ghi; lease đã hết → `ClaimStale`; lease hết trước lúc ghi → `LeaseExpired`, không `PUT`;
- **412 (A-084):** storage đã có byte của CHÍNH mình (response bị mất) → coi là thành công, commit; byte KHÁC → `StorageWriteConflict`, không commit;
- **commit muộn của claim đã bị dọn bị khoá ngoại từ chối** (`ClaimLost`); checksum ghi đúng một lần và bằng checksum của byte đã gửi;
- **`object_claim_reconcile`:** chỉ dọn claim chưa commit và đã hết lease; xoá object trước, dòng sau; storage lỗi thì giữ dòng; không đụng bản đã commit;
- chỉ `tool_layer.storage` ghi `stored_object`/`stored_object_commit`; lỗi chỉ mang mã.

Mỗi lớp test có DATABASE RIÊNG đã migrate và bucket riêng mỗi test.

Cần BO19_TEST_PG_SUPERUSER_DSN và BO19_TEST_S3_ENDPOINT (CI đặt BO19_REQUIRE_S3=1). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_storage -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import hashlib
import pathlib
import threading
import unittest
import uuid

import psycopg

from bo19.object_storage import ObjectStorage, StorageError
from bo19.persistence.errors import IntegrityViolation
from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer import storage as st
from bo19.tool_layer.storage import reconcile as rc
from tests import pg_support
from tests.s3_support import ENDPOINT, REQUIRED, drop_bucket, new_bucket, storage_for

LEASE = 120.0


class Spy:
    """Bọc `ObjectStorage`: đếm lệnh `PUT` và cho test chèn việc vào GIỮA lúc `PUT` (ca claim bị dọn khi upload còn bay)."""

    def __init__(self, inner: ObjectStorage, during=None, fail_delete: bool = False) -> None:
        self.inner, self.during, self.fail_delete = inner, during, fail_delete
        self.puts: list[str] = []
        self.deletes: list[str] = []
        self.bucket = inner.bucket

    def put_if_absent(self, key, data, *, content_type, metadata=None):
        self.puts.append(key)
        if self.during:
            self.during()
        return self.inner.put_if_absent(key, data, content_type=content_type, metadata=metadata)

    def get(self, key):
        return self.inner.get(key)

    def head(self, key):
        return self.inner.head(key)

    def delete(self, key):
        self.deletes.append(key)
        if self.fail_delete:
            raise StorageError("STORAGE_UNAVAILABLE")
        return self.inner.delete(key)


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class StorageBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENDPOINT:
            if REQUIRED:
                raise AssertionError("BO19_REQUIRE_S3=1 nhưng thiếu BO19_TEST_S3_ENDPOINT")
            raise unittest.SkipTest("cần BO19_TEST_S3_ENDPOINT")
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-storage", min_size=1, max_size=12)
        cls.pool.open()

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()
        cls.db.drop()

    def setUp(self):
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("delete from stored_object_commit")
            c.execute("delete from stored_object")
        self.bucket = new_bucket()
        self.addCleanup(drop_bucket, self.bucket)
        self.real = storage_for(self.bucket)
        self.spy = Spy(self.real)
        self.key = f"renders/doc-{uuid.uuid4().hex[:12]}/{uuid.uuid4().hex}.pdf"

    def put(self, data: bytes = b"%PDF-1.7 gia", *, key: str | None = None, storage=None, lease_s: float = LEASE, **kw):
        return st.put_once(self.pool, storage or self.spy, object_key=key or self.key, purpose="RENDER_PDF", content_type="application/pdf", data=data, lease_s=lease_s, **kw)

    def claim_row(self, key: str | None = None):
        with self.db.connect("bo19_migrator") as c:
            return c.execute("select object_key, purpose, content_type, claim_token, lease_expires_at > now() from stored_object where object_key = %s", (key or self.key,)).fetchone()

    def commit_row(self, key: str | None = None):
        with self.db.connect("bo19_migrator") as c:
            return c.execute("select committed_claim_token, checksum_sha256, size_bytes from stored_object_commit where object_key = %s", (key or self.key,)).fetchone()

    def counts(self) -> tuple[int, int]:
        with self.db.connect("bo19_migrator") as c:
            return (c.execute("select count(*) from stored_object").fetchone()[0], c.execute("select count(*) from stored_object_commit").fetchone()[0])

    def expire(self, key: str | None = None) -> None:
        """Lease đã hết — `ck_stored_object_lease` đòi `lease_expires_at > claimed_at`, nên lùi cả `claimed_at`."""
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("update stored_object set claimed_at = now() - interval '2 hours', lease_expires_at = now() - interval '1 second' where object_key = %s", (key or self.key,))

    def plant_claim(self, key: str | None = None, *, expired: bool = False) -> uuid.UUID:
        token = uuid.uuid4()
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("insert into stored_object (object_key, purpose, content_type, claim_token, claimed_at, lease_expires_at) values (%s, 'RENDER_PDF', 'application/pdf', %s, now() - interval '10 minutes', "
                      + ("now() - interval '5 minutes'" if expired else "now() + interval '5 minutes'") + ")", (key or self.key, token))
        return token


class GhiMotLan(StorageBase):
    def test_ghi_moi_claim_put_commit_dung_checksum_cua_byte_da_gui(self):
        data = b"%PDF-1.7 noi dung gia cua test"
        out = self.put(data, metadata={"x-bo19-pin-reason": "ISSUED"})
        digest = hashlib.sha256(data).digest()
        self.assertEqual((out.object_key, out.checksum_sha256, out.size_bytes, out.reused), (self.key, digest, len(data), False))
        key, purpose, ctype, token, valid = self.claim_row()
        self.assertEqual((key, purpose, ctype, valid), (self.key, "RENDER_PDF", "application/pdf", True))
        committed_token, checksum, size = self.commit_row()
        self.assertEqual((committed_token, bytes(checksum), size), (token, digest, len(data)))
        self.assertEqual(self.real.get(self.key), data)
        self.assertEqual(self.real.head(self.key).metadata, {"x-bo19-pin-reason": "ISSUED"})  # metadata trong cùng lệnh PUT
        self.assertEqual(self.spy.puts, [self.key])

    def test_ca_a_render_lai_cung_khoa_dung_object_cu_khong_put_lan_hai(self):
        first = self.put(b"byte-lan-dau")
        again = self.put(b"byte-lan-hai-khac-hoan-toan")
        self.assertEqual((again.checksum_sha256, again.size_bytes, again.reused), (first.checksum_sha256, first.size_bytes, True))
        self.assertEqual(self.spy.puts, [self.key])  # chỉ một PUT
        self.assertEqual(self.real.get(self.key), b"byte-lan-dau")  # byte cũ nguyên vẹn
        self.assertEqual(self.counts(), (1, 1))
        self.assertEqual(bytes(self.commit_row()[1]), hashlib.sha256(b"byte-lan-dau").digest())  # checksum của lần ghi đầu là chuẩn

    def test_tam_luong_cung_khoa_dung_mot_put_mot_commit(self):
        results, errors, barrier = [], [], threading.Barrier(8)

        def go(i: int):
            barrier.wait()
            try:
                results.append(self.put(f"nguoi-{i}".encode()))
            except st.ClaimHeld:
                errors.append("HELD")  # thua cuộc lúc người thắng còn đang ghi: trả job về hàng đợi
            except Exception as e:  # noqa: BLE001
                errors.append(repr(e))

        threads = [threading.Thread(target=go, args=(i,)) for i in range(8)]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
        self.assertEqual([e for e in errors if e != "HELD"], [])
        self.assertEqual(len(self.spy.puts), 1)  # đúng một lệnh ghi
        self.assertEqual(sum(not r.reused for r in results), 1)
        self.assertEqual(self.counts(), (1, 1))
        winner = next(r for r in results if not r.reused)
        self.assertEqual(bytes(self.commit_row()[1]), winner.checksum_sha256)
        self.assertEqual(hashlib.sha256(self.real.get(self.key)).digest(), winner.checksum_sha256)

    def test_khoa_khac_nhau_doc_lap(self):
        a = self.put(b"A", key="renders/a.pdf")
        b = self.put(b"B", key="renders/b.pdf")
        self.assertNotEqual(a.checksum_sha256, b.checksum_sha256)
        self.assertEqual(self.counts(), (2, 2))

    def test_purpose_la_ngoai_danh_muc_bi_tu_choi_khong_ghi_gi(self):
        with self.assertRaises(ValueError):
            st.put_once(self.pool, self.spy, object_key=self.key, purpose="KHAC", content_type="x/y", data=b"x", lease_s=LEASE)
        self.assertEqual((self.counts(), self.spy.puts), ((0, 0), []))


class Claim(StorageBase):
    def test_claim_con_han_cua_nguoi_khac_thi_khong_ghi(self):
        self.plant_claim()
        with self.assertRaises(st.ClaimHeld):
            self.put()
        self.assertEqual((self.spy.puts, self.counts()), ([], (1, 0)))

    def test_claim_het_han_chua_commit_thi_claim_stale_cho_doi_soat(self):
        self.plant_claim(expired=True)
        with self.assertRaises(st.ClaimStale):
            self.put()
        self.assertEqual((self.spy.puts, self.counts()), ([], (1, 0)))
        result = rc.object_claim_reconcile(self.pool, self.spy)
        self.assertEqual((result.removed, result.failed), (1, 0))
        self.assertEqual(self.put(b"sau-doi-soat").reused, False)  # claim mới từ đầu

    def test_lease_het_truoc_luc_ghi_thi_khong_put(self):
        with self.assertRaises(st.LeaseExpired):
            self.put(lease_s=0.001)
        self.assertEqual(self.spy.puts, [])
        self.assertEqual(self.counts(), (1, 0))  # claim còn đó cho đối soát dọn

    def test_da_co_commit_thi_claim_khong_duoc_tao(self):
        self.put(b"x")
        before = self.claim_row()
        self.put(b"y")
        self.assertEqual(self.claim_row(), before)


class Ca412(StorageBase):
    def test_412_khop_byte_cua_chinh_minh_coi_nhu_ghi_thanh_cong_va_commit(self):
        """Lần ghi trước của chính người giữ claim đã tới storage nhưng response bị mất; DB chưa có commit. `PUT` lại nhận 412 → đọc lại, checksum khớp → commit."""
        data = b"byte-da-toi-storage"
        self.real.put_if_absent(self.key, data, content_type="application/pdf")  # ghi trực tiếp, DB không biết
        out = self.put(data)
        self.assertEqual((out.reused, out.checksum_sha256), (False, hashlib.sha256(data).digest()))
        self.assertEqual(self.spy.puts, [self.key])
        self.assertEqual(bytes(self.commit_row()[1]), hashlib.sha256(data).digest())

    def test_412_lech_byte_thi_storage_write_conflict_khong_commit(self):
        self.real.put_if_absent(self.key, b"BYTE-CUA-NGUOI-KHAC", content_type="application/pdf")  # lệnh ghi trễ của claim cũ
        with self.assertRaises(st.StorageWriteConflict) as cm:
            self.put(b"byte-cua-minh")
        self.assertEqual(cm.exception.code, "STORAGE_WRITE_CONFLICT")
        self.assertIsNone(self.commit_row())
        self.assertEqual(self.real.get(self.key), b"BYTE-CUA-NGUOI-KHAC")  # không đè
        self.assertEqual(self.counts(), (1, 0))

    def test_sau_conflict_doi_soat_don_object_la_roi_ghi_lai_duoc(self):
        """A-084: claim hết lease → `object_claim_reconcile` xoá cả object lạ lẫn claim → lần thử lại ghi byte của mình."""
        self.real.put_if_absent(self.key, b"LA", content_type="application/pdf")
        with self.assertRaises(st.StorageWriteConflict):
            self.put(b"cua-minh")
        self.expire()
        result = rc.object_claim_reconcile(self.pool, self.spy)
        self.assertEqual(result.removed, 1)
        out = self.put(b"cua-minh")
        self.assertEqual(out.reused, False)
        self.assertEqual(self.real.get(self.key), b"cua-minh")


class CommitMuon(StorageBase):
    def test_claim_bi_don_giua_luc_upload_thi_commit_bi_tu_choi(self):
        """Upload còn bay, lease hết, đối soát dọn claim; commit muộn bị khoá ngoại ghép từ chối (ClaimLost) — không bao giờ thành chuẩn."""
        def reconcile_during_put():
            self.expire()
            rc.object_claim_reconcile(self.pool, self.real)  # xoá object (chưa có) và claim

        spy = Spy(self.real, during=reconcile_during_put)
        with self.assertRaises(st.ClaimLost):
            self.put(b"upload-bay", storage=spy)
        self.assertEqual(self.counts(), (0, 0))  # không claim, không commit

    def test_commit_cua_claim_cu_khong_the_ghi_de_claim_moi(self):
        old = self.plant_claim()
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("delete from stored_object where object_key = %s", (self.key,))  # đối soát đã dọn claim cũ
        new = self.put(b"claim-moi")
        with self.pool.acquire() as conn, self.assertRaises(IntegrityViolation) as cm:  # commit muộn của claim cũ, đi bằng đúng quyền của ứng dụng
            with unit_of_work(conn):
                conn.execute("insert into stored_object_commit (object_key, committed_claim_token, checksum_sha256, size_bytes) values (%s, %s, %s, 1)", (self.key, old, hashlib.sha256(b"x").digest()))
        self.assertNotIn(self.key, cm.exception.code)  # chỉ mã, không tên khoá
        self.assertEqual(bytes(self.commit_row()[1]), new.checksum_sha256)  # checksum của lần ghi đầu là chuẩn

    def test_checksum_ghi_mot_lan_khong_the_sua_hay_xoa_qua_quyen_ung_dung(self):
        self.put(b"x")
        with self.pool.acquire() as conn:
            for sql in ("update stored_object_commit set checksum_sha256 = decode(repeat('00', 32), 'hex') where object_key = %s", "update stored_object set lease_expires_at = now() where object_key = %s"):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with unit_of_work(conn):
                        conn.execute(sql, (self.key,))


class DoiSoat(StorageBase):
    def test_chi_don_claim_chua_commit_va_da_het_lease(self):
        expired, live, committed = f"renders/het-{uuid.uuid4().hex[:8]}", f"renders/con-{uuid.uuid4().hex[:8]}", f"renders/xong-{uuid.uuid4().hex[:8]}"
        self.plant_claim(expired, expired=True)
        self.plant_claim(live)
        self.put(b"da-commit", key=committed)
        self.expire(committed)  # claim đã commit mà lease cũ: vẫn không được dọn
        self.real.put_if_absent(expired, b"upload-do-dang", content_type="application/pdf")
        result = rc.object_claim_reconcile(self.pool, self.spy)
        self.assertEqual((result.removed, result.objects_deleted, result.failed, result.skipped), (1, 1, 0, 0))
        self.assertIsNone(self.claim_row(expired))
        self.assertIsNone(self.real.head(expired))  # object đã bị xoá trước
        self.assertIsNotNone(self.claim_row(live))
        self.assertIsNotNone(self.claim_row(committed))
        self.assertEqual(self.real.get(committed), b"da-commit")
        self.assertEqual(self.spy.deletes, [expired])  # không xoá object nào khác

    def test_khoa_chua_co_object_van_don_duoc_dong_claim(self):
        self.plant_claim(expired=True)
        self.assertEqual(rc.object_claim_reconcile(self.pool, self.spy).removed, 1)
        self.assertEqual(self.counts(), (0, 0))

    def test_storage_loi_thi_giu_dong_claim_va_thu_lai_lan_sau(self):
        self.plant_claim(expired=True)
        broken = Spy(self.real, fail_delete=True)
        result = rc.object_claim_reconcile(self.pool, broken)
        self.assertEqual((result.removed, result.failed), (0, 1))
        self.assertIsNotNone(self.claim_row())  # chưa xoá dòng: xoá object trước, dòng sau
        self.assertEqual(rc.object_claim_reconcile(self.pool, self.spy).removed, 1)

    def test_chay_lai_va_chay_dong_thoi_khong_don_hai_lan(self):
        for i in range(6):
            self.plant_claim(f"renders/c{i}-{uuid.uuid4().hex[:6]}", expired=True)
        results, barrier = [], threading.Barrier(3)

        def go():
            barrier.wait()
            results.append(rc.object_claim_reconcile(self.pool, self.real))

        threads = [threading.Thread(target=go) for _ in range(3)]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
        self.assertEqual(sum(r.removed for r in results), 6)  # mỗi claim đúng một lần
        self.assertEqual(self.counts(), (0, 0))
        self.assertEqual(rc.object_claim_reconcile(self.pool, self.real), rc.ReconcileResult(0, 0, 0, 0))

    def test_limit(self):
        for i in range(5):
            self.plant_claim(f"renders/l{i}-{uuid.uuid4().hex[:6]}", expired=True)
        self.assertEqual(rc.object_claim_reconcile(self.pool, self.real, limit=2).removed, 2)
        self.assertEqual(self.counts(), (3, 0))


class RangBuoc(StorageBase):
    def test_chi_tool_layer_storage_ghi_hai_bang_nay(self):
        root = pathlib.Path(st.__file__).resolve().parents[2]
        storage_dir = pathlib.Path(st.__file__).resolve().parent
        offenders = []
        for p in root.rglob("*.py"):
            if storage_dir in p.parents:
                continue
            text = p.read_text(encoding="utf-8").lower()
            if any(s in text for s in ("insert into stored_object", "delete from stored_object", "update stored_object")):
                offenders.append(str(p.relative_to(root)))
        self.assertEqual(offenders, [])

    def test_loi_chi_mang_ma(self):
        self.plant_claim(expired=True)
        with self.assertRaises(st.ClaimStale) as cm:
            self.put()
        blob = repr(cm.exception) + str(cm.exception) + repr(vars(cm.exception))
        self.assertEqual(cm.exception.code, "CLAIM_STALE")
        self.assertNotIn(self.key, blob)
        self.assertNotIn(self.bucket, blob)

    def test_khong_import_boto3(self):
        for mod in (st, rc):
            src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
            self.assertNotIn("boto3", src.replace("ADR-037", ""))  # chỉ nhắc ADR; không import
            self.assertNotIn("import botocore", src)


if __name__ == "__main__":
    unittest.main()
