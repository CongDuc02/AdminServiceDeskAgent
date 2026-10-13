"""`bo19.tool_layer.jobs` (B8a) — giành, gia hạn lease và kết thúc job trên PostgreSQL thật, role `bo19_app`.

Điều được chứng minh, nói bằng hành vi:
- **giành:** `FOR UPDATE SKIP LOCKED` — nhiều worker giành đồng thời, mỗi job đúng MỘT người; cũ nhất trước; job chưa tới `run_after` và loại không có handler không bị giành; `attempts` tăng lúc giành;
- **hàng rào chủ lease:** worker đã mất lease (bị `reclaim_expired`, kể cả đã được giành lại bởi chính `worker_id` đó) không `heartbeat`, `succeed`, `fail`, `release` được;
- **retry:** backoff `base × 2^attempts` theo loại; `max(backoff, retry_after)`; `retry_after` vượt WV-19 thì `FAILED` `PROVIDER_RATE_LIMITED`; hết lượt thì `FAILED`;
- **`release` không tiêu lượt thử; lease hết hạn tính một lượt** (PO, 2026-10-13);
- không `audit_event`; không giá trị nào ngoài mã trong `last_error_code`; payload từ `request_submit` chỉ mang id.

Mỗi lớp test có DATABASE RIÊNG đã migrate: hàng đợi là tài nguyên dùng chung toàn DB, nên job của test khác không được lẫn vào.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_jobs -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import datetime as dt
import threading
import unittest
import uuid
from pathlib import Path

from bo19.config import working_values as wv
from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer import jobs
from bo19.tool_layer.kernel.enqueue import enqueue
from tests import pg_support

TYPES = ("render_document",)


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class JobsBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-jobs", min_size=1, max_size=12)
        cls.pool.open()

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()
        cls.db.drop()

    def setUp(self):
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("delete from job")
        self.worker = f"w-{uuid.uuid4().hex[:8]}"

    # ---- dữ liệu và đọc kiểm (bằng chủ bảng) ------------------------------------------------------------------------------------

    def add(self, job_type: str = "render_document", *, offset_s: float = 0, attempts: int = 0, max_attempts: int | None = None, payload: str = "{}", age_s: float = 0) -> uuid.UUID:
        """Một job `QUEUED`. `offset_s` — `run_after` = now + offset; `age_s` — đã nằm trong hàng đợi bấy lâu (`enqueued_at`)."""
        jid = uuid.uuid4()
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("insert into job (id, job_type, payload, max_attempts, attempts, run_after, enqueued_at) values (%s, %s, %s::jsonb, %s, %s, now() + make_interval(secs => %s), now() - make_interval(secs => %s))",
                      (jid, job_type, payload, max_attempts or wv.JOB_MAX_ATTEMPTS[job_type], attempts, offset_s, age_s))
        return jid

    def row(self, jid: uuid.UUID) -> dict:
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select status, attempts, max_attempts, locked_by, locked_at, lease_expires_at, started_at, finished_at, last_error_code, "
                            "extract(epoch from run_after - now()) as run_in_s, extract(epoch from lease_expires_at - now()) as lease_in_s from job where id = %s", (jid,))
            return dict(zip([d.name for d in cur.description], cur.fetchone()))

    def claim_row(self, jid: uuid.UUID) -> dict:
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select id, job_type, payload, subject_document_id, dedupe_key, attempts, max_attempts, locked_by, locked_at from job where id = %s", (jid,))
            return dict(zip([d.name for d in cur.description], cur.fetchone()))

    def expire(self, jid: uuid.UUID) -> None:
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("update job set lease_expires_at = now() - interval '1 second' where id = %s", (jid,))

    def make_ready(self, jid: uuid.UUID) -> None:
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("update job set run_after = now() where id = %s", (jid,))

    def audit_count(self) -> int:
        with self.db.connect("bo19_migrator") as c:
            return c.execute("select count(*) from audit_event").fetchone()[0]

    def claim(self, types=TYPES, worker=None, lease_s=wv.JOB_LEASE_S):
        return jobs.claim(self.pool, worker_id=worker or self.worker, job_types=types, lease_s=lease_s)


class Giành(JobsBase):
    def test_giành_dat_running_tang_attempts_va_dat_lease(self):
        jid = self.add(payload='{"request_id": "r-1"}')
        job = self.claim()
        self.assertEqual((job.id, job.job_type, job.attempts, job.max_attempts, job.locked_by, job.payload), (jid, "render_document", 1, 5, self.worker, {"request_id": "r-1"}))
        r = self.row(jid)
        self.assertEqual((r["status"], r["attempts"], r["locked_by"]), ("RUNNING", 1, self.worker))
        self.assertIsNotNone(r["started_at"])
        self.assertIsNone(r["finished_at"])
        self.assertAlmostEqual(r["lease_in_s"], wv.JOB_LEASE_S, delta=3)
        self.assertEqual(job.locked_at, r["locked_at"])

    def test_cu_nhat_truoc_roi_het_thi_none(self):
        newer, older = self.add(offset_s=-10), self.add(offset_s=-100)  # đến hạn sớm hơn thì trước
        self.assertEqual([self.claim().id, self.claim().id], [older, newer])
        self.assertIsNone(self.claim())

    def test_run_after_tuong_lai_va_loai_khac_khong_bi_gianh(self):
        future = self.add(offset_s=3600)
        other = self.add("notification_send")
        self.assertIsNone(self.claim())
        self.assertEqual(self.row(future)["status"], "QUEUED")
        self.assertEqual(self.row(other)["status"], "QUEUED")
        self.assertIsNone(self.claim(types=()))  # không handler nào: không giành gì
        self.assertEqual(self.claim(types=("notification_send", "render_document")).id, other)

    def test_job_dang_running_va_da_xong_khong_bi_gianh_lai(self):
        self.add()
        job = self.claim()
        self.assertIsNone(self.claim(worker="w-khac"))
        jobs.succeed(self.pool, job)
        self.assertIsNone(self.claim(worker="w-khac"))

    def test_dong_thoi_moi_job_dung_mot_nguoi(self):
        ids = {self.add(age_s=i) for i in range(30)}
        got: list[uuid.UUID] = []
        lock, barrier = threading.Lock(), threading.Barrier(6)

        def run(i: int):
            barrier.wait()
            while (job := jobs.claim(self.pool, worker_id=f"w-{i}", job_types=TYPES)) is not None:
                with lock:
                    got.append(job.id)

        threads = [threading.Thread(target=run, args=(i,)) for i in range(6)]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
        self.assertEqual(len(got), 30)
        self.assertEqual(set(got), ids)  # mỗi job một lần, không sót, không trùng
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select count(*) from job where status = 'RUNNING' and attempts = 1").fetchone()[0], 30)

    def test_job_do_enqueue_cua_b7_chi_mang_id(self):
        rid, did = uuid.uuid4(), uuid.uuid4()
        with self.pool.acquire() as conn, unit_of_work(conn):
            enqueue(conn, job_type="render_document", payload={"request_id": str(rid), "decision_record_id": str(did)}, dedupe_key=str(rid))
        job = self.claim()
        self.assertEqual(job.payload, {"request_id": str(rid), "decision_record_id": str(did)})
        self.assertEqual(job.dedupe_key, str(rid))


class Lease(JobsBase):
    def test_heartbeat_gia_han_va_chi_chu_lease(self):
        jid = self.add()
        job = self.claim(lease_s=30)
        self.assertAlmostEqual(self.row(jid)["lease_in_s"], 30, delta=3)
        self.assertTrue(jobs.heartbeat(self.pool, job, lease_s=500))
        self.assertAlmostEqual(self.row(jid)["lease_in_s"], 500, delta=3)
        stranger = jobs.ClaimedJob(**{**job.__dict__, "locked_by": "w-la"})
        self.assertFalse(jobs.heartbeat(self.pool, stranger, lease_s=9999))
        self.assertAlmostEqual(self.row(jid)["lease_in_s"], 500, delta=3)

    def test_heartbeat_khi_lease_da_het_la_false(self):
        jid = self.add()
        job = self.claim()
        self.expire(jid)
        self.assertFalse(jobs.heartbeat(self.pool, job))

    def test_worker_mat_lease_khong_ghi_de_ke_ca_khi_job_duoc_gianh_lai_boi_chinh_worker_id_do(self):
        jid = self.add()
        old = self.claim()
        self.expire(jid)
        self.assertEqual([r.status for r in jobs.reclaim_expired(self.pool)], ["QUEUED"])
        self.make_ready(jid)
        new = self.claim()  # CÙNG worker_id
        self.assertEqual((new.id, new.locked_by, new.attempts), (jid, old.locked_by, 2))
        self.assertNotEqual(new.locked_at, old.locked_at)
        for stale in (lambda: jobs.heartbeat(self.pool, old), lambda: jobs.succeed(self.pool, old), lambda: jobs.release(self.pool, old), lambda: jobs.fail(self.pool, old, "LOI_CU")):
            self.assertIn(stale(), (False, None))
        r = self.row(jid)
        self.assertEqual((r["status"], r["attempts"], r["last_error_code"]), ("RUNNING", 2, "LEASE_EXPIRED"))  # lượt mới nguyên vẹn
        self.assertTrue(jobs.succeed(self.pool, new))

    def test_release_roi_giành_lai_khong_de_token_cu_song_lai(self):
        jid = self.add()
        old = self.claim()
        self.assertTrue(jobs.release(self.pool, old))
        new = self.claim()
        self.assertEqual(new.attempts, 1)  # trùng `attempts` với lượt cũ — token hàng rào phải là thứ khác
        self.assertFalse(jobs.succeed(self.pool, old))
        self.assertFalse(jobs.heartbeat(self.pool, old))
        self.assertEqual(self.row(jid)["status"], "RUNNING")


class KetThuc(JobsBase):
    def test_succeed(self):
        jid = self.add()
        job = self.claim()
        self.assertTrue(jobs.succeed(self.pool, job))
        r = self.row(jid)
        self.assertEqual((r["status"], r["lease_expires_at"], r["last_error_code"]), ("SUCCEEDED", None, None))
        self.assertIsNotNone(r["finished_at"])
        self.assertFalse(jobs.succeed(self.pool, job))  # lần hai: không làm gì

    def test_nguoi_la_khong_succeed_fail_release_duoc(self):
        jid = self.add()
        job = self.claim()
        stranger = jobs.ClaimedJob(**{**job.__dict__, "locked_by": "w-la"})
        self.assertFalse(jobs.succeed(self.pool, stranger))
        self.assertIsNone(jobs.fail(self.pool, stranger, "LOI"))
        self.assertFalse(jobs.release(self.pool, stranger))
        r = self.row(jid)
        self.assertEqual((r["status"], r["locked_by"], r["attempts"]), ("RUNNING", self.worker, 1))

    def test_fail_con_luot_ve_queued_voi_backoff_theo_loai_va_attempts(self):
        for job_type, base in (("render_document", 10), ("procedure_ingest", 30)):
            jid = self.add(job_type)
            for attempt in (1, 2):
                job = self.claim(types=(job_type,))
                self.assertEqual(job.attempts, attempt)
                self.assertEqual(jobs.fail(self.pool, job, "LOI_TAM"), jobs.FailOutcome("QUEUED", "LOI_TAM"))
                r = self.row(jid)
                self.assertEqual(r["status"], "QUEUED")
                self.assertAlmostEqual(r["run_in_s"], base * 2 ** attempt, delta=3, msg=(job_type, attempt))
                self.assertIsNone(r["lease_expires_at"])
                self.make_ready(jid)
            with self.db.connect("bo19_migrator", autocommit=True) as c:
                c.execute("delete from job where id = %s", (jid,))

    def test_fail_het_luot_la_failed_vinh_vien_khong_chay_lai(self):
        jid = self.add(max_attempts=2)
        for attempt in (1, 2):
            job = self.claim()
            out = jobs.fail(self.pool, job, "HET_LUOT")
            self.make_ready(jid)
        self.assertEqual(out, jobs.FailOutcome("FAILED", "HET_LUOT"))
        r = self.row(jid)
        self.assertEqual((r["status"], r["attempts"], r["last_error_code"]), ("FAILED", 2, "HET_LUOT"))
        self.assertIsNotNone(r["finished_at"])
        self.assertIsNone(self.claim())  # FAILED không tự retry (mục Job lỗi vĩnh viễn của 11-ops.md)

    def test_retry_after_lay_max_voi_backoff(self):
        jid = self.add()
        job = self.claim()
        jobs.fail(self.pool, job, "PROVIDER_RATE_LIMITED_TAM", retry_after_s=90)  # backoff lần 1 = 20 s < 90 s
        self.assertAlmostEqual(self.row(jid)["run_in_s"], 90, delta=3)
        self.make_ready(jid)
        job = self.claim()
        jobs.fail(self.pool, job, "LOI", retry_after_s=5)  # backoff lần 2 = 40 s > 5 s
        self.assertAlmostEqual(self.row(jid)["run_in_s"], 40, delta=3)

    def test_retry_after_vuot_wv19_la_failed_ngay_voi_provider_rate_limited(self):
        jid = self.add()
        job = self.claim()
        out = jobs.fail(self.pool, job, "LOI_BAT_KY", retry_after_s=wv.LLM_RETRY_AFTER_CEILING_SECONDS + 1)
        self.assertEqual(out, jobs.FailOutcome("FAILED", "PROVIDER_RATE_LIMITED"))
        r = self.row(jid)
        self.assertEqual((r["status"], r["attempts"], r["last_error_code"]), ("FAILED", 1, "PROVIDER_RATE_LIMITED"))  # bỏ các lượt còn lại
        jid2 = self.add()
        job2 = self.claim()
        self.assertEqual(jobs.fail(self.pool, job2, "LOI", retry_after_s=wv.LLM_RETRY_AFTER_CEILING_SECONDS).status, "QUEUED")  # đúng ngưỡng thì vẫn chờ

    def test_ma_loi_chi_la_ma(self):
        self.add()
        job = self.claim()
        for bad in ("co khoang trang", "chu thuong", "", "LOI: ghi chú dài có giá trị slot", "x" * 5):
            with self.assertRaises(ValueError):
                jobs.fail(self.pool, job, bad)
        with self.assertRaises(ValueError):
            jobs.fail(self.pool, job, "LOI", retry_after_s=-1)
        self.assertEqual(self.row(job.id)["status"], "RUNNING")

    def test_release_khong_tieu_luot_thu(self):
        jid = self.add()
        job = self.claim()
        self.assertEqual(self.row(jid)["attempts"], 1)
        self.assertTrue(jobs.release(self.pool, job))
        r = self.row(jid)
        self.assertEqual((r["status"], r["attempts"], r["lease_expires_at"], r["locked_at"]), ("QUEUED", 0, None, None))
        self.assertLess(r["run_in_s"], 1)  # chạy lại ngay
        again = self.claim(worker="w-khac")
        self.assertEqual((again.id, again.attempts), (jid, 1))
        self.assertFalse(jobs.release(self.pool, job))  # bản cũ không trả được lượt của người khác


class ThuHoiLease(JobsBase):
    def test_lease_het_han_tinh_mot_luot_ve_queued_sau_backoff(self):
        jid = self.add()
        self.claim()
        self.expire(jid)
        out = jobs.reclaim_expired(self.pool)
        self.assertEqual(out, [jobs.Reclaimed(jid, "render_document", "QUEUED")])
        r = self.row(jid)
        self.assertEqual((r["status"], r["attempts"], r["last_error_code"], r["lease_expires_at"], r["locked_at"]), ("QUEUED", 1, "LEASE_EXPIRED", None, None))  # lượt đã tính
        self.assertAlmostEqual(r["run_in_s"], 20, delta=3)

    def test_het_luot_thi_failed(self):
        jid = self.add(attempts=4, max_attempts=5)
        self.claim()  # attempts 5/5
        self.expire(jid)
        self.assertEqual([r.status for r in jobs.reclaim_expired(self.pool)], ["FAILED"])
        r = self.row(jid)
        self.assertEqual((r["status"], r["attempts"], r["last_error_code"]), ("FAILED", 5, "LEASE_EXPIRED"))
        self.assertIsNotNone(r["finished_at"])

    def test_chua_het_han_va_job_khac_khong_bi_dong_toi(self):
        running = self.add()
        self.claim()
        queued = self.add(offset_s=100)
        done = self.add()
        jobs.succeed(self.pool, self.claim())
        self.assertEqual(jobs.reclaim_expired(self.pool), [])
        self.assertEqual((self.row(running)["status"], self.row(queued)["status"], self.row(done)["status"]), ("RUNNING", "QUEUED", "SUCCEEDED"))

    def test_nhieu_worker_cung_thu_hoi_moi_job_mot_lan(self):
        ids = [self.add(age_s=i) for i in range(5)]
        for _ in ids:
            self.claim()
        for jid in ids:
            self.expire(jid)
        results, barrier = [], threading.Barrier(4)

        def run():
            barrier.wait()
            results.extend(jobs.reclaim_expired(self.pool))

        threads = [threading.Thread(target=run) for _ in range(4)]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
        self.assertEqual(sorted(r.id for r in results), sorted(ids))  # không job nào bị thu hồi hai lần
        self.assertTrue(all(self.row(j)["attempts"] == 1 for j in ids))

    def test_worker_chet_lap_lai_khong_tao_vong_vo_han(self):
        jid = self.add(max_attempts=3)
        for _ in range(3):
            self.make_ready(jid)
            self.assertIsNotNone(self.claim())
            self.expire(jid)
            jobs.reclaim_expired(self.pool)
        r = self.row(jid)
        self.assertEqual((r["status"], r["attempts"]), ("FAILED", 3))


class SoSachKyThuat(JobsBase):
    def test_khong_audit_event(self):
        before = self.audit_count()
        jid = self.add()
        job = self.claim()
        jobs.heartbeat(self.pool, job)
        jobs.fail(self.pool, job, "LOI")
        self.make_ready(jid)
        job = self.claim()
        jobs.release(self.pool, job)
        job = self.claim()
        self.expire(jid)
        jobs.reclaim_expired(self.pool)
        self.make_ready(jid)
        jobs.succeed(self.pool, self.claim())
        self.assertEqual(self.audit_count(), before)

    def test_ma_nguon_khong_dung_audit(self):
        src = (Path(jobs.__file__)).read_text(encoding="utf-8")
        self.assertNotIn("audit.", src)
        self.assertNotIn("import audit", src)
        self.assertNotIn("audit_event", src.replace("không sinh `audit_event`", "").replace("`audit_event`", ""))

    def test_backoff_la_so_hoc_theo_bang_11_ops(self):
        self.assertEqual([jobs.backoff_seconds("render_document", n) for n in (1, 2, 3, 4)], [20, 40, 80, 160])
        self.assertEqual(jobs.backoff_seconds("procedure_ingest", 1), 60)
        self.assertEqual(set(wv.JOB_BACKOFF_BASE_S), set(wv.JOB_MAX_ATTEMPTS))  # mọi loại đều có base
        self.assertEqual((wv.JOB_LEASE_S, wv.JOB_HEARTBEAT_S, wv.JOB_POLL_S, wv.WORKER_CONCURRENCY), (120, 40, 2, 1))  # WV-20, WV-21, WV-22

    def test_moi_trang_thai_deu_qua_rang_buoc_cua_db(self):
        """Mọi chuyển đổi đi qua `ck_job_running_has_lease` và `ck_job_finished_iff_terminal` — nếu một hàm bỏ sót cột, DB từ chối chứ không lưu hàng sai."""
        jid = self.add()
        self.assertTrue(jobs.heartbeat(self.pool, self.claim()))
        job = jobs.ClaimedJob(**{**self.claim_row(jid), "locked_by": self.worker})
        self.assertTrue(jobs.release(self.pool, job))
        jobs.fail(self.pool, self.claim(), "LOI")
        self.make_ready(jid)
        jobs.succeed(self.pool, self.claim())
        self.assertEqual(self.row(jid)["status"], "SUCCEEDED")


if __name__ == "__main__":
    unittest.main()
