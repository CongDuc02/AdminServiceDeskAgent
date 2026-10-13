"""`bo19.queue_worker.dispatcher` (B8a) — vòng poll, heartbeat, tắt êm trên PostgreSQL thật, role `bo19_app`.

Điều được chứng minh, nói bằng hành vi:
- chỉ giành loại job có handler — `render_document` do `request_submit` đưa vào vẫn `QUEUED` khi chưa có handler (B8a: production không đăng ký handler nào);
- handler thành công → `SUCCEEDED`; `JobFailure` → thất bại có mã, `retry_after_s` đi vào backoff; ngoại lệ khác → `HANDLER_CRASHED` và **thông điệp của ngoại lệ không vào DB hay log**;
- một job một lúc (WV-22); hai dispatcher cùng hàng đợi: mỗi job một lần;
- `heartbeat` giữ lease cho job chạy lâu hơn lease; mất lease thì cờ huỷ đặt lên handler và lệnh ghi muộn bị từ chối;
- tắt êm: ngừng giành job mới; job xong trong hạn drain thì hoàn tất; quá hạn drain thì cờ huỷ + `release` KHÔNG tiêu lượt thử;
- lease hết hạn của worker chết được thu hồi ở vòng kế tiếp.

Mỗi lớp test có DATABASE RIÊNG đã migrate. Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_dispatcher -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import io
import logging
import threading
import time
import unittest
import uuid

from bo19.config import working_values as wv
from bo19.observability.log import configure_logging
from bo19.persistence.pool import Pool
from bo19.queue_worker.dispatcher import CRASHED, Dispatcher, JobFailure
from bo19.queue_worker.handlers import DEFAULT_HANDLERS
from tests import pg_support

RES = "NOI_DUNG_RES_KHONG_DUOC_LOT_RA_77aa"


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class DispatcherBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-dispatcher", min_size=1, max_size=12)
        cls.pool.open()

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()
        cls.db.drop()

    def setUp(self):
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("delete from job")
        self.out = io.StringIO()
        handler = configure_logging(self.out)
        self.addCleanup(logging.getLogger().removeHandler, handler)

    def add(self, job_type: str = "render_document", *, offset_s: float = 0, payload: str = "{}", attempts: int = 0) -> uuid.UUID:
        jid = uuid.uuid4()
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("insert into job (id, job_type, payload, max_attempts, attempts, run_after) values (%s, %s, %s::jsonb, %s, %s, now() + make_interval(secs => %s))",
                      (jid, job_type, payload, wv.JOB_MAX_ATTEMPTS[job_type], attempts, offset_s))
        return jid

    def row(self, jid: uuid.UUID) -> dict:
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select status, attempts, last_error_code, locked_by, extract(epoch from run_after - now()) as run_in_s, extract(epoch from lease_expires_at - now()) as lease_in_s from job where id = %s", (jid,))
            return dict(zip([d.name for d in cur.description], cur.fetchone()))

    def dispatcher(self, handlers, **kw) -> Dispatcher:
        kw.setdefault("poll_s", 0.05)
        kw.setdefault("heartbeat_s", 0.1)
        kw.setdefault("lease_s", 5)
        kw.setdefault("drain_s", 5)
        return Dispatcher(self.pool, handlers, **kw)

    def log_text(self) -> str:
        return self.out.getvalue()


class ChiGianhLoaiCoHandler(DispatcherBase):
    def test_production_chua_dang_ky_handler_nao_nen_render_document_van_queued(self):
        self.assertEqual(DEFAULT_HANDLERS, {})
        jid = self.add("render_document")
        d = self.dispatcher(DEFAULT_HANDLERS)
        self.assertFalse(d.run_once())
        self.assertEqual((self.row(jid)["status"], self.row(jid)["attempts"]), ("QUEUED", 0))

    def test_chi_loai_co_handler_bi_giành(self):
        mine, other = self.add("notification_send"), self.add("render_document")
        seen = []
        d = self.dispatcher({"notification_send": lambda job, ctx: seen.append(job.id)})
        self.assertTrue(d.run_once())
        self.assertFalse(d.run_once())
        self.assertEqual(seen, [mine])
        self.assertEqual((self.row(mine)["status"], self.row(other)["status"], self.row(other)["attempts"]), ("SUCCEEDED", "QUEUED", 0))


class KetQuaHandler(DispatcherBase):
    def test_thanh_cong(self):
        jid = self.add(payload='{"request_id": "r-1"}')
        got = {}
        d = self.dispatcher({"render_document": lambda job, ctx: got.update(payload=job.payload, attempts=job.attempts)})
        self.assertTrue(d.run_once())
        self.assertEqual(got, {"payload": {"request_id": "r-1"}, "attempts": 1})
        self.assertEqual(self.row(jid)["status"], "SUCCEEDED")

    def test_job_failure_ve_queued_voi_backoff_va_retry_after(self):
        jid = self.add()

        def handler(job, ctx):
            raise JobFailure("RENDER_FAILED", retry_after_s=90)

        self.assertTrue(self.dispatcher({"render_document": handler}).run_once())
        r = self.row(jid)
        self.assertEqual((r["status"], r["attempts"], r["last_error_code"]), ("QUEUED", 1, "RENDER_FAILED"))
        self.assertAlmostEqual(r["run_in_s"], 90, delta=3)  # max(backoff 20 s, retry_after 90 s)

    def test_job_failure_het_luot_la_failed(self):
        jid = self.add(attempts=4)  # lượt giành này là lượt 5/5

        def handler(job, ctx):
            raise JobFailure("RENDER_FAILED")

        self.dispatcher({"render_document": handler}).run_once()
        r = self.row(jid)
        self.assertEqual((r["status"], r["attempts"], r["last_error_code"]), ("FAILED", 5, "RENDER_FAILED"))

    def test_ngoai_le_la_handler_crashed_khong_lo_thong_diep(self):
        jid = self.add()

        def handler(job, ctx):
            raise RuntimeError(f"giá trị slot {RES}")

        self.assertTrue(self.dispatcher({"render_document": handler}).run_once())
        r = self.row(jid)
        self.assertEqual((r["status"], r["last_error_code"]), ("QUEUED", CRASHED))
        self.assertNotIn(RES, self.log_text())  # log chỉ mang kiểu ngoại lệ
        self.assertIn("JOB_HANDLER_CRASHED", self.log_text())
        self.assertIn("RuntimeError", self.log_text())


class MotJobMotLuc(DispatcherBase):
    def test_tuan_tu_va_khong_bao_gio_hai_job_cung_luc(self):
        ids = [self.add(offset_s=-i) for i in range(5)]
        active, peak, done = [0], [0], []
        lock = threading.Lock()

        def handler(job, ctx):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            with lock:
                active[0] -= 1
                done.append(job.id)

        d = self.dispatcher({"render_document": handler})
        runner = threading.Thread(target=d.run_forever)
        runner.start()
        deadline = time.monotonic() + 20
        while len(done) < 5 and time.monotonic() < deadline:
            time.sleep(0.05)
        d.stop()
        runner.join(10)
        self.assertEqual((sorted(done), peak[0]), (sorted(ids), 1))  # WV-22 = 1
        self.assertTrue(all(self.row(i)["status"] == "SUCCEEDED" for i in ids))

    def test_hai_dispatcher_cung_hang_doi_moi_job_mot_lan(self):
        ids = {self.add(offset_s=-i) for i in range(12)}
        seen, lock = [], threading.Lock()

        def handler(job, ctx):
            time.sleep(0.02)
            with lock:
                seen.append(job.id)

        ds = [self.dispatcher({"render_document": handler}, worker_id=f"w{i}") for i in range(2)]
        threads = [threading.Thread(target=d.run_forever) for d in ds]
        [t.start() for t in threads]
        deadline = time.monotonic() + 30
        while len(seen) < 12 and time.monotonic() < deadline:
            time.sleep(0.05)
        [d.stop() for d in ds]
        [t.join(10) for t in threads]
        self.assertEqual((len(seen), set(seen)), (12, ids))  # mỗi job đúng một lần


class Heartbeat(DispatcherBase):
    def test_job_chay_lau_hon_lease_van_giu_duoc_nho_heartbeat(self):
        jid = self.add()
        samples = []

        def handler(job, ctx):
            time.sleep(3.2)  # lâu hơn lease 1,5 s hơn gấp đôi; lease rộng so với nhịp heartbeat để runner chậm không làm test chập chờn
            samples.append(ctx.cancelled)

        d = self.dispatcher({"render_document": handler}, lease_s=1.5, heartbeat_s=0.2)
        self.assertTrue(d.run_once())
        self.assertEqual(samples, [False])
        self.assertEqual(self.row(jid)["status"], "SUCCEEDED")  # lease được gia hạn liên tục: không ai thu hồi giữa chừng

    def test_mat_lease_thi_dat_co_huy_va_lenh_ghi_muon_bi_tu_choi(self):
        jid = self.add()
        started, release = threading.Event(), threading.Event()
        cancelled_seen = []

        def handler(job, ctx):
            started.set()
            ctx.cancel.wait(10)  # đợi tới khi bị huỷ
            cancelled_seen.append(ctx.cancelled)
            release.wait(10)

        d = self.dispatcher({"render_document": handler}, lease_s=5, heartbeat_s=0.1)
        t = threading.Thread(target=d.run_once)
        t.start()
        self.assertTrue(started.wait(10))
        with self.db.connect("bo19_migrator", autocommit=True) as c:  # worker khác thu hồi: lease đã hết
            c.execute("update job set lease_expires_at = now() - interval '1 second' where id = %s", (jid,))
        deadline = time.monotonic() + 10
        while not cancelled_seen and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(cancelled_seen, [True])  # heartbeat thấy mất lease → cờ huỷ
        from bo19.tool_layer import jobs
        jobs.reclaim_expired(self.pool)  # worker khác thu hồi và giành lại job
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("update job set run_after = now() where id = %s", (jid,))
        taken = jobs.claim(self.pool, worker_id="w-khac", job_types=("render_document",))
        self.assertEqual((taken.id, taken.attempts), (jid, 2))
        release.set()
        t.join(10)  # handler cũ trả về bình thường → dispatcher cũ gọi `succeed` với token cũ
        r = self.row(jid)
        self.assertEqual((r["status"], r["locked_by"], r["attempts"]), ("RUNNING", "w-khac", 2))  # lượt của worker khác nguyên vẹn
        self.assertIn("JOB_LEASE_LOST", self.log_text())
        self.assertIn('"recorded":false', self.log_text().replace(" ", ""))  # kết quả muộn không được ghi


class TatEm(DispatcherBase):
    def test_sau_stop_khong_giành_job_moi(self):
        jid = self.add()
        d = self.dispatcher({"render_document": lambda job, ctx: None})
        d.stop()
        self.assertFalse(d.run_once())
        self.assertEqual((self.row(jid)["status"], self.row(jid)["attempts"]), ("QUEUED", 0))

    def test_job_xong_trong_han_drain_thi_hoan_tat(self):
        jid = self.add()
        started = threading.Event()

        def handler(job, ctx):
            started.set()
            time.sleep(0.3)

        d = self.dispatcher({"render_document": handler}, drain_s=5)
        t = threading.Thread(target=d.run_once)
        t.start()
        self.assertTrue(started.wait(10))
        d.stop()
        t.join(10)
        self.assertEqual(self.row(jid)["status"], "SUCCEEDED")

    def test_qua_han_drain_thi_huy_va_release_khong_tieu_luot_thu(self):
        jid = self.add()
        started, saw_cancel = threading.Event(), []

        def handler(job, ctx):
            started.set()
            ctx.cancel.wait(10)
            saw_cancel.append(ctx.cancelled)

        d = self.dispatcher({"render_document": handler}, drain_s=0.3)
        t = threading.Thread(target=d.run_once)
        t.start()
        self.assertTrue(started.wait(10))
        before = time.monotonic()
        d.stop()
        t.join(10)
        self.assertLess(time.monotonic() - before, 3)  # bỏ cuộc chờ đúng hạn drain, không chờ handler
        r = self.row(jid)
        self.assertEqual((r["status"], r["attempts"], r["locked_by"] is not None), ("QUEUED", 0, True))  # không tiêu lượt thử
        deadline = time.monotonic() + 5
        while not saw_cancel and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(saw_cancel, [True])  # handler được báo huỷ
        self.assertIn("JOB_RELEASED_ON_DRAIN", self.log_text())
        # job về hàng đợi: worker khác giành lại ngay, lượt thử 1
        again = self.dispatcher({"render_document": lambda job, ctx: None}, worker_id="w-khac")
        self.assertTrue(again.run_once())
        self.assertEqual(self.row(jid)["attempts"], 1)

    def test_release_xong_thi_handler_cu_khong_ghi_de_ket_qua_cua_worker_khac(self):
        jid = self.add()
        started, finish = threading.Event(), threading.Event()

        def slow(job, ctx):
            started.set()
            finish.wait(10)  # bỏ qua cờ huỷ: ca xấu nhất — handler không hợp tác

        d = self.dispatcher({"render_document": slow}, drain_s=0.2)
        t = threading.Thread(target=d.run_once)
        t.start()
        self.assertTrue(started.wait(10))
        d.stop()
        t.join(10)  # đã release
        calls = []
        other = self.dispatcher({"render_document": lambda job, ctx: calls.append(job.attempts)}, worker_id="w-khac", lease_s=5)
        self.assertTrue(other.run_once())
        self.assertEqual(self.row(jid)["status"], "SUCCEEDED")
        finish.set()  # handler cũ chạy xong sau đó; kết quả của nó (`succeed`) phải bị hàng rào từ chối
        time.sleep(0.5)
        self.assertEqual((self.row(jid)["status"], self.row(jid)["attempts"], calls), ("SUCCEEDED", 1, [1]))


class VongPollBen(DispatcherBase):
    def test_loi_db_tam_thoi_khong_lam_vong_poll_sap(self):
        import psycopg
        from unittest import mock
        jid = self.add()
        calls = []
        real_claim = __import__("bo19.tool_layer.jobs", fromlist=["claim"]).claim
        state = {"n": 0}

        def flaky(*a, **k):
            state["n"] += 1
            if state["n"] <= 2:
                raise psycopg.OperationalError(f"giá trị slot {RES} trong thông điệp lỗi")
            return real_claim(*a, **k)

        d = self.dispatcher({"render_document": lambda job, ctx: calls.append(job.id)})
        with mock.patch("bo19.queue_worker.dispatcher.jobs.claim", side_effect=flaky):
            t = threading.Thread(target=d.run_forever)
            t.start()
            deadline = time.monotonic() + 20
            while not calls and time.monotonic() < deadline:
                time.sleep(0.05)
            d.stop()
            t.join(10)
        self.assertEqual(calls, [jid])  # sau hai lỗi, vòng poll vẫn sống và xử lý job
        self.assertGreaterEqual(self.log_text().count("WORKER_LOOP_ERROR"), 2)
        self.assertIn("OperationalError", self.log_text())
        self.assertNotIn(RES, self.log_text())  # chỉ kiểu lỗi


class ThuHoi(DispatcherBase):
    def test_worker_chet_lease_het_han_duoc_thu_hoi_o_vong_ke_tiep(self):
        jid = self.add()
        from bo19.tool_layer import jobs
        dead = jobs.claim(self.pool, worker_id="w-chet", job_types=("render_document",), lease_s=5)
        self.assertIsNotNone(dead)
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("update job set lease_expires_at = now() - interval '1 second' where id = %s", (jid,))
        calls = []
        d = self.dispatcher({"render_document": lambda job, ctx: calls.append(job.attempts)})
        self.assertFalse(d.run_once())  # vòng này chỉ thu hồi: job về QUEUED sau backoff
        self.assertEqual((self.row(jid)["status"], self.row(jid)["last_error_code"]), ("QUEUED", "LEASE_EXPIRED"))
        with self.db.connect("bo19_migrator", autocommit=True) as c:
            c.execute("update job set run_after = now() where id = %s", (jid,))
        self.assertTrue(d.run_once())
        self.assertEqual((calls, self.row(jid)["status"]), ([2], "SUCCEEDED"))  # lượt của worker chết đã bị tính
        self.assertIn("JOB_LEASE_RECLAIMED", self.log_text())


if __name__ == "__main__":
    unittest.main()
