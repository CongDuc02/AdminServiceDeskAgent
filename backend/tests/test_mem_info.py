"""`observability.mem_info` — log `MEM_INFO` / `MEM_JOB_DONE` khi worker chạy job (A-095, bước 4b; PO 2026-10-22): chỉ quan sát, chỉ khi có job, không bao giờ ném.

Nguồn file cgroup: `docs/reference/linux-cgroup-bo-nho-do-trong-container.md`. Test dựng thư mục cgroup giả (v2 và v1), không đọc cgroup thật.
Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_mem_info -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from bo19.observability import mem_info
from bo19.observability.mem_info import CgroupReader, JobMemWatch, Reading

MIB = 1024 * 1024


def v2_dir(root: Path, *, current=300 * MIB, peak=350 * MIB, limit="536870912", oom_kill=0) -> None:
    (root / "memory.current").write_text(f"{current}\n")
    if peak is not None:
        (root / "memory.peak").write_text(f"{peak}\n")
    (root / "memory.max").write_text(f"{limit}\n")
    (root / "memory.events").write_text(f"low 0\nhigh 0\nmax 3\noom 1\noom_kill {oom_kill}\noom_group_kill 0\n")


class ScriptedReader:
    """Đọc lần lượt các `Reading` đã soạn; hết thì lặp lại cái cuối."""

    def __init__(self, readings):
        self.readings, self.i = list(readings), 0

    def read(self) -> Reading:
        r = self.readings[min(self.i, len(self.readings) - 1)]
        self.i += 1
        return r


class DocCgroup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="bo19-cg-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_v2_doc_dung_hien_tai_dinh_gioi_han_va_oom_kill(self):
        v2_dir(self.root, oom_kill=2)
        self.assertEqual(CgroupReader(str(self.root)).read(), Reading(300 * MIB, 350 * MIB, 536870912, 2))

    def test_v2_gioi_han_max_la_none_va_thieu_peak_van_doc_phan_con_lai(self):
        v2_dir(self.root, peak=None, limit="max")
        r = CgroupReader(str(self.root)).read()
        self.assertEqual((r.current, r.peak, r.limit, r.oom_kill), (300 * MIB, None, None, 0))  # không bịa số

    def test_v1_doc_usage_max_usage_limit_va_oom_kill_tu_oom_control(self):
        v1 = self.root / "memory"
        v1.mkdir()
        (v1 / "memory.usage_in_bytes").write_text(str(200 * MIB))
        (v1 / "memory.max_usage_in_bytes").write_text(str(250 * MIB))
        (v1 / "memory.limit_in_bytes").write_text("536870912")
        (v1 / "memory.oom_control").write_text("oom_kill_disable 0\nunder_oom 0\noom_kill 4\n")
        self.assertEqual(CgroupReader(str(self.root)).read(), Reading(200 * MIB, 250 * MIB, 536870912, 4))

    def test_v1_khong_gioi_han_la_none(self):
        v1 = self.root / "memory"
        v1.mkdir()
        (v1 / "memory.usage_in_bytes").write_text("100")
        (v1 / "memory.limit_in_bytes").write_text("9223372036854771712")
        self.assertIsNone(CgroupReader(str(self.root)).read().limit)

    def test_khong_co_cgroup_thi_toan_none_khong_nem(self):
        self.assertEqual(CgroupReader(str(self.root / "khong-ton-tai")).read(), Reading())

    def test_file_hong_khong_nem(self):
        (self.root / "memory.current").write_text("không phải số")
        (self.root / "memory.events").write_text("oom_kill chu\n")
        self.assertEqual(CgroupReader(str(self.root)).read(), Reading())

    def test_khong_bao_gio_ghi_vao_memory_peak(self):
        v2_dir(self.root)
        before = (self.root / "memory.peak").read_text()
        for _ in range(3):
            CgroupReader(str(self.root)).read()
        self.assertEqual((self.root / "memory.peak").read_text(), before)  # ghi sẽ đặt lại đỉnh (tài liệu kernel)


class TheoDoiJob(unittest.TestCase):
    def run_watch(self, readings, *, seconds=0.35, log_s=0.1, sample_s=0.02):
        reader = ScriptedReader(readings)
        watch = JobMemWatch("job-1", "render_document", reader=reader, log_s=log_s, sample_s=sample_s)
        with mock.patch.object(mem_info, "log") as log:
            watch.start()
            time.sleep(seconds)
            watch.stop()
        return log

    def calls(self, log, name):
        return [c for c in log.info.call_args_list if c.args and c.args[0] == name]

    def test_ghi_meminfo_dinh_ky_va_mot_dong_job_done_voi_dinh_trong_job(self):
        readings = [Reading(100 * MIB, 120 * MIB, 512 * MIB, 0), Reading(300 * MIB, 320 * MIB, 512 * MIB, 0), Reading(450 * MIB, 460 * MIB, 512 * MIB, 0), Reading(200 * MIB, 460 * MIB, 512 * MIB, 1)]
        log = self.run_watch(readings)
        infos, done = self.calls(log, "MEM_INFO"), self.calls(log, "MEM_JOB_DONE")
        self.assertGreaterEqual(len(infos), 2)
        self.assertEqual(len(done), 1)
        kw = done[0].kwargs
        self.assertEqual((kw["job_id"], kw["job_type"]), ("job-1", "render_document"))
        self.assertEqual(kw["job_max_mib"], 450.0)  # đỉnh lấy mẫu trong job
        self.assertEqual(kw["peak_mib"], 460.0)  # đỉnh của cgroup
        self.assertEqual((kw["oom_kill"], kw["job_oom_kill"]), (1, 1))  # tăng thêm 1 trong job
        self.assertEqual(kw["limit_mib"], 512.0)
        self.assertEqual(set(infos[0].kwargs), {"job_id", "job_type", "elapsed_s", "current_mib", "peak_mib", "job_max_mib", "limit_mib", "oom_kill"})  # chỉ số và id

    def test_khong_ghi_gi_khi_khong_co_job(self):
        with mock.patch.object(mem_info, "log") as log:
            JobMemWatch("x", "t", reader=ScriptedReader([Reading()]))  # tạo mà chưa start: không luồng, không log
            time.sleep(0.1)
        log.info.assert_not_called()

    def test_job_ngan_hon_chu_ky_log_chi_co_job_done(self):
        log = self.run_watch([Reading(10 * MIB, 20 * MIB, None, 0)], seconds=0.05, log_s=10.0, sample_s=0.01)
        self.assertEqual(len(self.calls(log, "MEM_INFO")), 0)
        self.assertEqual(len(self.calls(log, "MEM_JOB_DONE")), 1)

    def test_khong_doc_duoc_thi_log_null_khong_bia_so(self):
        log = self.run_watch([Reading()], seconds=0.15)
        kw = self.calls(log, "MEM_JOB_DONE")[0].kwargs
        self.assertEqual((kw["current_mib"], kw["peak_mib"], kw["job_max_mib"], kw["limit_mib"], kw["oom_kill"], kw["job_oom_kill"]), (None,) * 6)

    def test_loi_cua_reader_khong_lam_hong_job(self):
        class Boom:
            def read(self):
                raise RuntimeError("x")

        watch = JobMemWatch("j", "t", reader=Boom(), log_s=0.01, sample_s=0.01)
        with mock.patch.object(mem_info, "log"):
            watch.start()  # không ném
            time.sleep(0.05)
            watch.stop()  # không ném
        self.assertTrue(True)

    def test_luong_la_daemon_va_stop_dung_luong(self):
        watch = JobMemWatch("j", "t", reader=ScriptedReader([Reading(1, 1, None, 0)]), log_s=0.01, sample_s=0.01)
        with mock.patch.object(mem_info, "log"):
            watch.start()
            self.assertTrue(watch._thread.daemon)
            watch.stop()
        self.assertFalse(watch._thread.is_alive())


class TrongDispatcher(unittest.TestCase):
    def test_dispatcher_goi_start_roi_stop_quanh_job_ke_ca_khi_job_hong(self):
        from bo19.queue_worker import dispatcher as d

        events: list[str] = []

        class Fake:
            def __init__(self, job_id, job_type):
                events.append(f"new:{job_type}")

            def start(self):
                events.append("start")

            def stop(self):
                events.append("stop")

        for handler, expect in ((lambda job, ctx: events.append("run"), ["new:x", "start", "run", "stop"]),
                                (lambda job, ctx: (_ for _ in ()).throw(RuntimeError("boom")), ["new:x", "start", "stop"])):
            events.clear()
            disp = d.Dispatcher(mock.Mock(), {"x": handler}, mem_watch=Fake)
            job = mock.Mock(id="1", job_type="x", attempts=1)
            with mock.patch.object(d.jobs, "succeed", return_value=True), mock.patch.object(d.jobs, "fail", return_value=None):
                disp._execute(job)
            self.assertEqual(events, expect)


if __name__ == "__main__":
    unittest.main()
