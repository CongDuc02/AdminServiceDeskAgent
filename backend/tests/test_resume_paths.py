"""Các nhánh của `DocumentRunner.resume_document` (ADR-040 mục 5, 9) với một graph GIẢ trả `Snapshot` do test dựng — tất định, không phụ thuộc thời điểm tiến trình bị giết (bản `SIGKILL` thật ở `test_document_restart`
phụ thuộc việc LangGraph đã kịp ghi checkpoint kế tiếp hay chưa). Và `route_review` / `route_after_signature` tự từ chối loại quyết định không hỗ trợ (chốt chặn thứ hai sau `WAKES` của runner).

Cần BO19_TEST_PG_SUPERUSER_DSN (để đọc `decision_record`). Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_resume_paths -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest
import uuid
from unittest import mock

from bo19.orchestrator import runner as runner_module
from bo19.orchestrator.document_graph.runtime import DocumentDeps
from bo19.orchestrator.runner import DocumentRunner, RenderFailed
from bo19.orchestrator.runtime.builder import Snapshot
from bo19.tool_layer.tools.document_reads import DecisionRead


class FakeGraph:
    def __init__(self, snapshot: Snapshot) -> None:
        self.snap, self.calls = snapshot, []

    def snapshot(self, thread_id):
        return self.snap

    def resume(self, thread_id, value, **kw):
        self.calls.append(("resume", value))
        return {}

    def invoke(self, thread_id, state_input, **kw):
        self.calls.append(("invoke", state_input))
        return {}


STATE = {"document_id": "x"}


class NhanhResume(unittest.TestCase):
    def runner(self, snap: Snapshot) -> tuple[DocumentRunner, FakeGraph]:
        graph = FakeGraph(snap)
        r = DocumentRunner(DocumentDeps(pool=mock.Mock(), gateway=mock.Mock(), storage=mock.Mock(), fingerprinter=mock.Mock()), graph)
        return r, graph

    def resume(self, snap: Snapshot, kind: str = "SIGNED"):
        r, graph = self.runner(snap)
        with mock.patch.object(runner_module, "decision_record_read", return_value=DecisionRead(kind, None, ())), \
                mock.patch.object(runner_module, "mark_document_thread"), mock.patch.object(runner_module, "document_thread_id", return_value="document:x"):
            try:
                out = r.resume_document(document_id=uuid.uuid4(), decision_record_id=uuid.uuid4())
            except RenderFailed as e:
                return e, graph
        return out, graph

    def test_graph_da_ket_thuc_thi_no_op_ma_khong_doc_quyet_dinh(self):
        out, graph = self.resume(Snapshot(STATE, (), None, has_tasks=False))
        self.assertEqual((out.status, out.already), ("ENDED", True))
        self.assertEqual(graph.calls, [])

    def test_chua_co_thread(self):
        out, graph = self.resume(Snapshot(None, (), None))
        self.assertEqual((type(out), out.raw_code), (RenderFailed, "THREAD_NOT_WAITING"))
        self.assertEqual(graph.calls, [])

    def test_cho_dung_diem_thi_resume(self):
        out, graph = self.resume(Snapshot(STATE, ("await_signature",), "await_signature", has_tasks=True), "SIGNED")
        self.assertEqual([c[0] for c in graph.calls], ["resume"])

    def test_cho_o_diem_sau_thi_no_op(self):
        out, graph = self.resume(Snapshot(STATE, ("await_seal",), "await_seal", has_tasks=True), "SIGNED")
        self.assertEqual((out.already, out.waiting_at), (True, "await_seal"))
        self.assertEqual(graph.calls, [])

    def test_cho_o_diem_truoc_thi_loi(self):
        out, graph = self.resume(Snapshot(STATE, ("await_content_review",), "await_content_review", has_tasks=True), "SIGNED")
        self.assertEqual((type(out), out.raw_code), (RenderFailed, "THREAD_NOT_WAITING"))
        self.assertEqual(graph.calls, [])

    def test_con_node_ke_ma_khong_cho_thi_tiep_tu_checkpoint(self):
        out, graph = self.resume(Snapshot(STATE, ("route_signing",), None, has_tasks=True), "APPROVED")
        self.assertEqual(graph.calls, [("invoke", None)])

    def test_next_rong_nhung_con_task_da_xong_cung_tiep_tu_checkpoint(self):
        """Trạng thái sau `SIGKILL` ngay khi một node vừa xong: `next` rỗng, task còn (pending writes) — KHÔNG phải graph đã kết thúc."""
        out, graph = self.resume(Snapshot(STATE, (), None, has_tasks=True), "APPROVED")
        self.assertEqual(graph.calls, [("invoke", None)])

    def test_loai_quyet_dinh_khong_ho_tro(self):
        for kind in ("REJECTED", "CHANGES_REQUESTED", "ISSUE_ORDERED", "RESUBMITTED"):
            out, graph = self.resume(Snapshot(STATE, ("await_content_review",), "await_content_review", has_tasks=True), kind)
            self.assertEqual((type(out), out.raw_code, out.permanent), (RenderFailed, "UNSUPPORTED_DECISION", True), kind)
            self.assertEqual(graph.calls, [])


@unittest.skipUnless(__import__("tests.pg_support", fromlist=["x"]).SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class NodeTuTuChoi(unittest.TestCase):
    """`route_review` và `route_after_signature` gọi trực tiếp (không qua graph): quyết định sai loại là `UNSUPPORTED_DECISION`."""

    @classmethod
    def setUpClass(cls):
        from bo19.persistence.pool import Pool
        from tests import pg_support
        from tests.gate_support import make_template_version

        cls.db = pg_support.get_db()
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-resume-paths", min_size=1, max_size=2)
        cls.pool.open()
        cls.version_id = make_template_version(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()

    def call(self, node: str, kind: str):
        from bo19.orchestrator.document_graph.nodes import make_nodes
        from bo19.orchestrator.document_graph.runtime import RenderRuntime
        from bo19.tool_layer.kernel.permission import system_context
        from tests.gate_support import make_officer, make_pending_approval

        doc = make_pending_approval(self.db, self.pool, self.version_id)
        officer, _ = make_officer(self.db, self.pool)
        decision = uuid.uuid4()
        with self.db.connect("bo19_migrator") as c:
            step = c.execute("select id from approval_step where document_id = %s and step_kind = 'CONTENT_REVIEW'", (doc.document_id,)).fetchone()[0]  # APPROVED/SIGNED/SEALED đòi bước (ck_decision_record_step_kinds)
            c.execute("insert into decision_record (id, kind, actor_employee_id, request_id, document_id, approval_step_id) values (%s, %s, %s, %s, %s, %s)", (decision, kind, officer, doc.request_id, doc.document_id, step))
        deps = DocumentDeps(pool=self.pool, gateway=mock.Mock(), storage=mock.Mock(), fingerprinter=mock.Mock())
        state = {"document_id": str(doc.document_id), "request_id": str(doc.request_id), "last_signal": {"decision_record_id": str(decision), "kind": None, "change_scope": None, "change_targets": []}}
        return make_nodes(deps)[node](state, {"configurable": {"run": RenderRuntime(sys=system_context())}})

    def test_route_review_chi_nhan_approved(self):
        from bo19.orchestrator.runtime.node_boundary import NodeError

        self.assertEqual(self.call("route_review", "APPROVED")["last_signal"]["kind"], "APPROVED")
        for kind in ("REJECTED", "SIGNED", "SEALED"):
            with self.assertRaises(NodeError, msg=kind) as cm:
                self.call("route_review", kind)
            self.assertEqual(cm.exception.code, "UNSUPPORTED_DECISION")

    def test_route_after_signature_chi_nhan_signed(self):
        from bo19.orchestrator.runtime.node_boundary import NodeError

        for kind in ("APPROVED", "REJECTED", "SEALED"):
            with self.assertRaises(NodeError, msg=kind) as cm:
                self.call("route_after_signature", kind)
            self.assertEqual(cm.exception.code, "UNSUPPORTED_DECISION")


if __name__ == "__main__":
    unittest.main()
