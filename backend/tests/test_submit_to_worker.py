"""Từ `request_submit` (B7) tới `queue_worker` (B8a) — hai lần gửi đồng thời rồi N worker cùng hàng đợi: đúng một `decision_record`, đúng một job `render_document`, đúng MỘT lần chạy handler.

Điều được chứng minh, nói bằng hành vi: job do `request_submit` đưa vào hàng đợi là loại và payload mà `tool_layer.jobs` giành được; payload mang đúng hai id (không giá trị slot, không `RES`);
bốn dispatcher chạy cùng lúc trên một hàng đợi — handler được gọi đúng một lần; sau khi job `SUCCEEDED`, gửi lại không đẻ thêm job.

DATABASE RIÊNG đã migrate. Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_submit_to_worker -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import threading
import time
import unittest
import uuid

from bo19.persistence.pool import Pool
from bo19.queue_worker.dispatcher import Dispatcher
from bo19.tool_layer.gate_ops.request_submit import StateConflict, request_submit
from bo19.tool_layer.kernel.permission import employee_context
from tests import pg_support
from tests.request_support import build_request
from tests.tool_support import RES


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class SubmitToWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.PgDb(pg_support.SUPERUSER_DSN)
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-submit-worker", min_size=1, max_size=16)
        cls.pool.open()

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()
        cls.db.drop()

    def setUp(self):
        self.eid, _ = self.db.make_employee(roles=("EMPLOYEE",))
        with self.pool.acquire() as conn:
            self.ctx = employee_context(conn, self.eid)
        self.rid = build_request(self.pool, self.db, self.eid, self.ctx)
        with self.db.connect("bo19_migrator") as c:
            self.version = c.execute("select row_version from request where id = %s", (self.rid,)).fetchone()[0]

    def jobs(self):
        with self.db.connect("bo19_migrator") as c:
            return c.execute("select status, attempts, payload from job where payload->>'request_id' = %s", (str(self.rid),)).fetchall()

    def decisions(self) -> int:
        with self.db.connect("bo19_migrator") as c:
            return c.execute("select count(*) from decision_record where request_id = %s", (self.rid,)).fetchone()[0]

    def test_hai_submit_dong_thoi_roi_bon_worker_mot_job_mot_lan_chay(self):
        results, barrier = [], threading.Barrier(2)

        def submit():
            barrier.wait()
            try:
                results.append(request_submit(self.pool, self.ctx, request_id=self.rid, decision_id=uuid.uuid4(), expected_row_version=self.version))
            except StateConflict:
                results.append("CONFLICT")

        threads = [threading.Thread(target=submit) for _ in range(2)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        self.assertEqual(sorted(type(r).__name__ for r in results), ["Submitted", "str"])  # một thắng, một `STATE_CONFLICT`
        self.assertEqual((self.decisions(), len(self.jobs())), (1, 1))
        (status, attempts, payload) = self.jobs()[0]
        self.assertEqual((status, attempts), ("QUEUED", 0))
        self.assertEqual(set(payload), {"request_id", "decision_record_id"})
        self.assertNotIn(RES, str(payload))

        calls, lock = [], threading.Lock()

        def handler(job, ctx):
            time.sleep(0.2)  # đủ lâu để các worker khác kịp poll và KHÔNG giành lại
            with lock:
                calls.append(job.payload)

        dispatchers = [Dispatcher(self.pool, {"render_document": handler}, worker_id=f"w{i}", poll_s=0.05, heartbeat_s=0.1, lease_s=5) for i in range(4)]
        threads = [threading.Thread(target=d.run_forever) for d in dispatchers]
        [t.start() for t in threads]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and (not calls or self.jobs()[0][0] != "SUCCEEDED"):
            time.sleep(0.05)
        time.sleep(0.5)  # thêm vài chu kỳ poll: không worker nào được chạy lại
        [d.stop() for d in dispatchers]
        [t.join(10) for t in threads]
        self.assertEqual(calls, [payload])  # đúng một lần, đúng payload của B7
        self.assertEqual(self.jobs()[0][:2], ("SUCCEEDED", 1))

        with self.assertRaises(StateConflict):  # gửi lại sau khi job đã chạy: không đẻ thêm job
            request_submit(self.pool, self.ctx, request_id=self.rid, decision_id=uuid.uuid4(), expected_row_version=self.version + 1)
        self.assertEqual((self.decisions(), len(self.jobs())), (1, 1))


if __name__ == "__main__":
    unittest.main()
