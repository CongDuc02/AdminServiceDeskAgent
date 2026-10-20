"""O1-15 (B9b, mức mã + fixture): `request` ở `CHANGES_REQUESTED` ca `SLOT_DATA` còn **sửa được** và **gửi lại được** — PostgreSQL thật, role `bo19_app`.

Ca xác định được từ khi có `document`: `request.status = CHANGES_REQUESTED` **và** quyết định mới nhất của `document` là `CHANGES_REQUESTED` với `change_scope = SLOT_DATA` (`_common.slot_data_reopened`). Thao tác đưa `request` vào
trạng thái đó (`document_request_changes`) là Sprint 2, nên trạng thái ở đây do **fixture dựng bằng chủ bảng**; tích hợp với graph (`await_resubmission`) cũng Sprint 2.

- ba thao tác sửa của nhân viên (`request_slots_write`, `request_slot_confirm`, `request_slots_propose`) không còn `NotEditable` ở ca `SLOT_DATA`; **vẫn** `NotEditable` ở ca `FREE_CONTENT`, khi có quyết định mới hơn, khi không có `document`;
- `request_submit` ở ca `SLOT_DATA`: tự kiểm lại F1 (slot `HR_PROFILE` bị bỏ xác nhận phải xác nhận lại), `CHANGES_REQUESTED → SUBMITTED`, `decision_record` `RESUBMITTED` gắn `document`, job `resume_document_graph`, `audit_event` —
  một giao dịch; lặp lại cùng khoá là no-op; bước `TAKEOVER` đang mở thì `AwaitingTakeover`; ca `FREE_CONTENT` vẫn `StateConflict`.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_slot_data_reopen -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest
import uuid
from unittest import mock

from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.employee_ops.request_slot_confirm import Confirmation, request_slot_confirm
from bo19.tool_layer.gate_ops import request_submit as rs
from bo19.tool_layer.gate_ops._errors import AwaitingTakeover, DecisionIdConflict, StateConflict
from bo19.tool_layer.gate_ops.request_submit import NotReady, request_submit
from bo19.tool_layer.tools._common import NotEditable, slot_data_reopened
from bo19.tool_layer.tools.request_slots_propose import request_slots_propose
from bo19.tool_layer.tools.request_slots_write import request_slots_write
from tests import pg_support
from tests.gate_support import ctx_of, make_officer, make_pending_approval, make_template_version, rows, scalar
from tests.request_support import slot_versions


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class SlotDataBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.get_db()
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-slot-data", min_size=1, max_size=4)
        cls.pool.open()
        cls.version_id = make_template_version(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()

    def returned(self, scope: str = "SLOT_DATA", targets=("full_name",), unconfirm=("full_name",)):
        """Một `document` mà người duyệt vừa trả về (dựng bằng chủ bảng). Trả (doc, ctx của nhân viên, id người duyệt)."""
        eid, _ = self.db.make_employee(roles=("EMPLOYEE",))
        ctx = ctx_of(self.pool, eid)
        doc = make_pending_approval(self.db, self.pool, self.version_id, beneficiary=(eid, ctx))
        officer, _ = make_officer(self.db, self.pool)
        with self.db.connect("bo19_migrator") as c:
            step = c.execute("select id from approval_step where document_id = %s and step_kind = 'CONTENT_REVIEW'", (doc.document_id,)).fetchone()[0]
            c.execute("update approval_step set status = 'DECIDED', closed_at = now() where id = %s", (step,))
            c.execute("insert into decision_record (id, kind, actor_employee_id, request_id, document_id, approval_step_id, change_scope, change_targets) values (%s, 'CHANGES_REQUESTED', %s, %s, %s, %s, %s, %s)",
                      (uuid.uuid4(), officer, doc.request_id, doc.document_id, step, scope, list(targets)))
            c.execute("update document set status = 'CHANGES_REQUESTED' where id = %s", (doc.document_id,))
            c.execute("update request set status = 'CHANGES_REQUESTED' where id = %s", (doc.request_id,))
            for name in unconfirm:  # ca SLOT_DATA bỏ xác nhận slot HR_PROFILE nằm trong change_targets
                c.execute("update request_slot set value_status = 'PROPOSED', confirmed_at = null where request_id = %s and slot_name = %s", (doc.request_id, name))
        return doc, ctx, officer

    def version(self, doc) -> int:
        return scalar(self.db, "select row_version from request where id = %s", doc.request_id)

    def resubmit(self, doc, ctx, key=None, version=None):
        return request_submit(self.pool, ctx, request_id=doc.request_id, decision_id=key or uuid.uuid4(), expected_row_version=version or self.version(doc))

    def written(self, doc) -> tuple:
        return (scalar(self.db, "select status from request where id = %s", doc.request_id), self.version(doc), scalar(self.db, "select count(*) from decision_record where request_id = %s", doc.request_id),
                scalar(self.db, "select count(*) from job where subject_document_id = %s", doc.document_id), scalar(self.db, "select count(*) from audit_event where request_id = %s", doc.request_id))


class ViTu(SlotDataBase):
    def test_slot_data_la_dung(self):
        doc, _, _ = self.returned("SLOT_DATA")
        with self.pool.acquire() as conn, unit_of_work(conn):
            self.assertTrue(slot_data_reopened(conn, doc.request_id))

    def test_free_content_la_sai(self):
        doc, _, _ = self.returned("FREE_CONTENT", targets=("purpose_statement",), unconfirm=())
        with self.pool.acquire() as conn, unit_of_work(conn):
            self.assertFalse(slot_data_reopened(conn, doc.request_id))

    def test_quyet_dinh_moi_hon_lam_vi_tu_sai(self):
        doc, _, officer = self.returned("SLOT_DATA")
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into decision_record (id, kind, actor_employee_id, request_id, document_id, created_at) values (%s, 'RESUBMITTED', %s, %s, %s, now() + interval '1 second')",
                      (uuid.uuid4(), officer, doc.request_id, doc.document_id))
        with self.pool.acquire() as conn, unit_of_work(conn):
            self.assertFalse(slot_data_reopened(conn, doc.request_id))

    def test_quyet_dinh_slot_data_cu_hon_mot_quyet_dinh_free_content_la_sai(self):
        doc, _, officer = self.returned("SLOT_DATA")
        with self.db.connect("bo19_migrator") as c:
            step = c.execute("select id from approval_step where document_id = %s", (doc.document_id,)).fetchone()[0]
            c.execute("insert into approval_step (id, document_id, step_kind, revision_round) values (%s, %s, 'CONTENT_REVIEW', 1)", (uuid.uuid4(), doc.document_id))
            c.execute("insert into decision_record (id, kind, actor_employee_id, request_id, document_id, approval_step_id, change_scope, created_at) "
                      "select %s, 'CHANGES_REQUESTED', %s, %s, %s, id, 'FREE_CONTENT', now() + interval '1 second' from approval_step where document_id = %s and revision_round = 1",
                      (uuid.uuid4(), officer, doc.request_id, doc.document_id, doc.document_id))
        with self.pool.acquire() as conn, unit_of_work(conn):
            self.assertFalse(slot_data_reopened(conn, doc.request_id))

    def test_khong_co_document_la_sai(self):
        eid, _ = self.db.make_employee(roles=("EMPLOYEE",))
        rid = self.db.make_request("CHANGES_REQUESTED")
        with self.pool.acquire() as conn, unit_of_work(conn):
            self.assertFalse(slot_data_reopened(conn, rid))
            self.assertFalse(slot_data_reopened(conn, uuid.uuid4()))


class SuaDuoc(SlotDataBase):
    def test_ba_thao_tac_sua_khong_con_not_editable(self):
        doc, ctx, _ = self.returned("SLOT_DATA")
        versions = slot_versions(self.db, doc.request_id)
        result = request_slot_confirm(self.pool, ctx, request_id=doc.request_id, items=[Confirmation("full_name", versions["full_name"][1])])
        self.assertEqual(result.confirmed, ("full_name",))
        self.assertEqual(result.status, "CHANGES_REQUESTED")  # request không tự đổi trạng thái — chỉ request_submit đi cạnh
        self.assertEqual(request_slots_write(self.pool, ctx, request_id=doc.request_id, items=[]).written, ())
        request_slots_propose(self.pool, ctx, request_id=doc.request_id, origin="HR_PROFILE")  # không ném

    def test_free_content_van_not_editable(self):
        doc, ctx, _ = self.returned("FREE_CONTENT", targets=("purpose_statement",), unconfirm=())
        with self.assertRaises(NotEditable) as cm:
            request_slot_confirm(self.pool, ctx, request_id=doc.request_id, items=[Confirmation("full_name", 1)])
        self.assertEqual(cm.exception.detail, "CHANGES_REQUESTED")
        with self.assertRaises(NotEditable):
            request_slots_write(self.pool, ctx, request_id=doc.request_id, items=[])
        with self.assertRaises(NotEditable):
            request_slots_propose(self.pool, ctx, request_id=doc.request_id, origin="HR_PROFILE")

    def test_khong_co_document_van_not_editable(self):
        eid, _ = self.db.make_employee(roles=("EMPLOYEE",))
        ctx = ctx_of(self.pool, eid)
        from tests.request_support import build_request

        rid = build_request(self.pool, self.db, eid, ctx)
        with self.db.connect("bo19_migrator") as c:
            c.execute("update request set status = 'CHANGES_REQUESTED' where id = %s", (rid,))
        with self.assertRaises(NotEditable):
            request_slots_write(self.pool, ctx, request_id=rid, items=[])

    def test_trang_thai_khac_khong_bi_anh_huong(self):
        doc, ctx, _ = self.returned("SLOT_DATA")
        with self.db.connect("bo19_migrator") as c:
            c.execute("update request set status = 'IN_REVIEW' where id = %s", (doc.request_id,))  # quyết định SLOT_DATA vẫn là mới nhất, nhưng request không còn CHANGES_REQUESTED
        with self.assertRaises(NotEditable):
            request_slots_write(self.pool, ctx, request_id=doc.request_id, items=[])


class GuiLai(SlotDataBase):
    def test_slot_chua_xac_nhan_lai_thi_not_ready(self):
        doc, ctx, _ = self.returned("SLOT_DATA")
        before = self.written(doc)
        with self.assertRaises(NotReady) as cm:
            self.resubmit(doc, ctx)
        self.assertEqual(cm.exception.unconfirmed_slots, ("full_name",))
        self.assertEqual(self.written(doc), before)

    def test_duong_thang_mot_giao_dich(self):
        doc, ctx, _ = self.returned("SLOT_DATA")
        versions = slot_versions(self.db, doc.request_id)
        request_slot_confirm(self.pool, ctx, request_id=doc.request_id, items=[Confirmation("full_name", versions["full_name"][1])])
        key = uuid.uuid4()
        before = self.version(doc)
        r = self.resubmit(doc, ctx, key)
        self.assertEqual((r.decision_record_id, r.replayed), (key, False))
        self.assertEqual((scalar(self.db, "select status from request where id = %s", doc.request_id), self.version(doc)), ("SUBMITTED", before + 1))
        self.assertEqual(rows(self.db, "select kind, actor_employee_id, request_id, document_id, approval_step_id from decision_record where id = %s", key),
                         [("RESUBMITTED", doc.beneficiary_id, doc.request_id, doc.document_id, None)])
        job = rows(self.db, "select job_type, status, subject_document_id, payload, dedupe_key from job where subject_document_id = %s and job_type = 'resume_document_graph'", doc.document_id)
        self.assertEqual(job, [("resume_document_graph", "QUEUED", doc.document_id, {"document_id": str(doc.document_id), "decision_record_id": str(key)}, str(key))])
        self.assertEqual(rows(self.db, "select actor_kind, action, entity_type, document_id, decision_record_id from audit_event where decision_record_id = %s", key),
                         [("EMPLOYEE", "request.resubmit", "request", doc.document_id, key)])
        self.assertEqual(scalar(self.db, "select status from document where id = %s", doc.document_id), "CHANGES_REQUESTED")  # request_submit không đổi document: graph (Sprint 2) mới làm

    def _confirmed(self):
        doc, ctx, officer = self.returned("SLOT_DATA")
        versions = slot_versions(self.db, doc.request_id)
        request_slot_confirm(self.pool, ctx, request_id=doc.request_id, items=[Confirmation("full_name", versions["full_name"][1])])
        return doc, ctx, officer

    def test_lap_lai_cung_khoa_la_no_op(self):
        doc, ctx, _ = self._confirmed()
        key = uuid.uuid4()
        first = self.resubmit(doc, ctx, key)
        snap = self.written(doc)
        again = self.resubmit(doc, ctx, key, version=999)
        self.assertEqual((again.replayed, again.created_at), (True, first.created_at))
        self.assertEqual(self.written(doc), snap)

    def test_khoa_cua_quyet_dinh_khac_la_conflict(self):
        doc, ctx, officer = self._confirmed()
        other_doc, other_ctx, _ = self._confirmed()
        key = uuid.uuid4()
        self.resubmit(other_doc, other_ctx, key)
        before = self.written(doc)
        with self.assertRaises(DecisionIdConflict):
            self.resubmit(doc, ctx, key)  # khoá là quyết định của người khác
        self.assertEqual(self.written(doc), before)

    def test_dang_cho_tiep_quan_thi_tu_choi_va_khong_ghi_gi(self):
        doc, ctx, _ = self._confirmed()
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into approval_step (id, document_id, step_kind, status) values (%s, %s, 'TAKEOVER', 'OPEN')", (uuid.uuid4(), doc.document_id))
        before = self.written(doc)
        with self.assertRaises(AwaitingTakeover):
            self.resubmit(doc, ctx)
        self.assertEqual(self.written(doc), before)

    def test_ca_free_content_van_state_conflict(self):
        doc, ctx, _ = self.returned("FREE_CONTENT", targets=("purpose_statement",), unconfirm=())
        before = self.written(doc)
        with self.assertRaises(StateConflict) as cm:
            self.resubmit(doc, ctx)
        self.assertEqual(cm.exception.current_status, "CHANGES_REQUESTED")
        self.assertEqual(self.written(doc), before)

    def test_row_version_lech(self):
        doc, ctx, _ = self._confirmed()
        before = self.written(doc)
        with self.assertRaises(StateConflict):
            self.resubmit(doc, ctx, version=self.version(doc) + 1)
        self.assertEqual(self.written(doc), before)

    def test_enqueue_hong_thi_khong_con_gi(self):
        doc, ctx, _ = self._confirmed()
        before = self.written(doc)
        with mock.patch.object(rs, "enqueue", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.resubmit(doc, ctx)
        self.assertEqual(self.written(doc), before)
        self.assertEqual(scalar(self.db, "select status from request where id = %s", doc.request_id), "CHANGES_REQUESTED")


if __name__ == "__main__":
    unittest.main()
