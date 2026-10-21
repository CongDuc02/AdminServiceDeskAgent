"""`Snapshot` của mặt tiền graph (B9b1): `finished` chỉ đúng khi graph THẬT SỰ xong — không còn node kế **và** không còn task nào (kể cả task đã xong mà kết quả chưa thành checkpoint mới).

Lý do (phát hiện bằng test tiến trình thật, B9b1): tiến trình bị `SIGKILL` ngay sau khi một node xong và trước khi checkpoint kế tiếp được ghi để lại một checkpoint có task đã xong (pending writes) nhưng `next` rỗng;
bản đầu của `finished` (`exists and not next_nodes`) coi đó là graph đã kết thúc và job resume trả "đã xong" trong khi chưa có gì chạy tiếp. Test này khoá định nghĩa; hành vi đầu-cuối ở `test_document_restart`.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_graph_snapshot -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest

from bo19.orchestrator.runtime.builder import Snapshot

STATE = {"document_id": "x"}


class SnapshotDinhNghia(unittest.TestCase):
    def test_chua_co_thread(self):
        s = Snapshot(None, (), None)
        self.assertEqual((s.exists, s.pending, s.finished), (False, False, False))

    def test_con_node_ke(self):
        s = Snapshot(STATE, ("route_signing",), None)
        self.assertEqual((s.exists, s.pending, s.finished), (True, True, False))

    def test_dang_cho_o_interrupt(self):
        s = Snapshot(STATE, ("await_signature",), "await_signature", has_tasks=True)
        self.assertEqual((s.pending, s.finished, s.waiting_at), (True, False, "await_signature"))

    def test_next_rong_nhung_con_task_da_xong_chua_thanh_checkpoint_la_pending_khong_phai_finished(self):
        s = Snapshot(STATE, (), None, has_tasks=True)
        self.assertEqual((s.pending, s.finished), (True, False))

    def test_het_ca_node_ke_lan_task_la_finished(self):
        s = Snapshot(STATE, (), None, has_tasks=False)
        self.assertEqual((s.pending, s.finished), (False, True))


if __name__ == "__main__":
    unittest.main()
