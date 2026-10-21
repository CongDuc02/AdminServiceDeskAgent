"""Kernel B9b1 (ADR-040): `transition(..., set_values=)` ghi cột đi kèm của cạnh trong CÙNG câu `UPDATE`, và `approval_step` có máy trạng thái — PostgreSQL thật, role `bo19_app`.

- `ck_document_approved_complete` / `ck_document_signer_assigned` đòi cột có mặt cùng lúc với trạng thái: cạnh `APPROVED` và `PENDING_SIGNATURE` đi được **chỉ** khi đưa đủ đúng tập cột;
- cột ngoài danh sách cho phép của trạng thái đích (kể cả `status`, tên SQL độc) bị từ chối **trước** khi đụng DB; thiếu cột thì `SetValuesIncomplete` — không để `CHECK` của DB là lớp duy nhất;
- đã ở trạng thái đích thì không ghi gì, kể cả `set_values`;
- `approval_step`: `OPEN → DECIDED`/`CANCELLED` đặt `closed_at`; không cạnh quay lại; không `status_changed_at`.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_kernel_set_values -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest
import uuid

from bo19.domain.approval_step_machine import APPROVAL_STEP_STATUSES, APPROVAL_STEP_TRANSITIONS, APPROVAL_STEP_TERMINAL, can_transition
from bo19.persistence.pool import Pool
from bo19.persistence.write import unit_of_work
from bo19.tool_layer.kernel import transition as tr
from tests import pg_support
from tests.gate_support import document_row, make_pending_approval, make_template_version, rows, scalar


class MayApprovalStep(unittest.TestCase):
    def test_bang_canh(self):
        self.assertEqual(APPROVAL_STEP_STATUSES, ("OPEN", "DECIDED", "CANCELLED"))
        self.assertEqual({k: set(v) for k, v in APPROVAL_STEP_TRANSITIONS.items()}, {"OPEN": {"DECIDED", "CANCELLED"}, "DECIDED": set(), "CANCELLED": set()})
        self.assertEqual(APPROVAL_STEP_TERMINAL, {"DECIDED", "CANCELLED"})
        self.assertTrue(can_transition("OPEN", "DECIDED"))
        self.assertFalse(can_transition("DECIDED", "OPEN"))
        self.assertFalse(can_transition("CANCELLED", "DECIDED"))


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class SetValues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.get_db()
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-set-values", min_size=1, max_size=4)
        cls.pool.open()
        cls.version_id = make_template_version(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()

    def go(self, table, row_id, **kw):
        with self.pool.acquire() as conn, unit_of_work(conn):
            return tr.transition(conn, table, row_id, **kw)

    def approved_values(self, doc):
        decision = uuid.uuid4()
        with self.db.connect("bo19_migrator") as c:
            step = c.execute("select id from approval_step where document_id = %s and step_kind = 'CONTENT_REVIEW'", (doc.document_id,)).fetchone()[0]
            c.execute("insert into decision_record (id, kind, actor_employee_id, request_id, document_id, approval_step_id) values (%s, 'APPROVED', %s, %s, %s, %s)",
                      (decision, doc.beneficiary_id, doc.request_id, doc.document_id, step))
        return {"approved_content_hash": b"\x05" * 32, "approved_decision_id": decision, "approved_render_id": doc.render_id}

    def test_approved_ghi_ba_cot_cung_cau_va_db_chap_nhan(self):
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        values = self.approved_values(doc)
        r = self.go("document", doc.document_id, to="APPROVED", expected_from="PENDING_APPROVAL", set_values=values)
        row = document_row(self.db, doc.document_id)
        self.assertEqual((r.status, r.changed, row["status"]), ("APPROVED", True, "APPROVED"))
        self.assertEqual((bytes(row["approved_content_hash"]), row["approved_decision_id"], row["approved_render_id"]), (b"\x05" * 32, values["approved_decision_id"], doc.render_id))

    def test_thieu_cot_la_set_values_incomplete_va_khong_ghi_gi(self):
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        values = self.approved_values(doc)
        before = document_row(self.db, doc.document_id)
        for missing in values:
            partial = {k: v for k, v in values.items() if k != missing}
            with self.assertRaises(tr.SetValuesIncomplete, msg=missing):
                self.go("document", doc.document_id, to="APPROVED", set_values=partial)
        with self.assertRaises(tr.SetValuesIncomplete):
            self.go("document", doc.document_id, to="APPROVED")  # không đưa cột nào
        self.assertEqual(document_row(self.db, doc.document_id), before)

    def test_cot_ngoai_danh_sach_bi_tu_choi_truoc_khi_dung_db(self):
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        values = self.approved_values(doc)
        before = document_row(self.db, doc.document_id)
        for bad in ("status", "row_version", "issued_at", "signer_employee_id", "id; DROP TABLE document", ""):
            with self.assertRaises(tr.ExtraColumnNotAllowed, msg=bad):
                self.go("document", doc.document_id, to="APPROVED", set_values={**values, bad: "x"})
        self.assertEqual(document_row(self.db, doc.document_id), before)

    def test_trang_thai_khong_co_cot_di_kem_khong_nhan_set_values(self):
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        with self.assertRaises(tr.ExtraColumnNotAllowed):
            self.go("document", doc.document_id, to="CHANGES_REQUESTED", set_values={"approved_content_hash": b"\x01" * 32})
        self.assertEqual(document_row(self.db, doc.document_id)["status"], "PENDING_APPROVAL")

    def test_da_o_trang_thai_dich_thi_khong_ghi_gi(self):
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        self.go("document", doc.document_id, to="APPROVED", set_values=self.approved_values(doc))
        before = document_row(self.db, doc.document_id)
        r = self.go("document", doc.document_id, to="APPROVED", set_values={"approved_content_hash": b"\x09" * 32, "approved_decision_id": before["approved_decision_id"], "approved_render_id": doc.render_id})
        self.assertFalse(r.changed)
        self.assertEqual(document_row(self.db, doc.document_id), before)  # hash cũ đứng

    def test_pending_signature_can_signer(self):
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        self.go("document", doc.document_id, to="APPROVED", set_values=self.approved_values(doc))
        with self.assertRaises(tr.SetValuesIncomplete):
            self.go("document", doc.document_id, to="PENDING_SIGNATURE")
        signer, _ = self.db.make_employee(roles=("EMPLOYEE",))
        self.go("document", doc.document_id, to="PENDING_SIGNATURE", set_values={"signer_employee_id": signer})
        self.assertEqual(document_row(self.db, doc.document_id)["signer_employee_id"], signer)

    def test_ten_cot_di_vao_sql_chi_qua_danh_sach_cho_phep(self):
        """Giá trị đi qua tham số, tên cột qua `TableSpec.value_columns`: một giá trị độc không phá câu lệnh."""
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        values = self.approved_values(doc)
        self.go("document", doc.document_id, to="APPROVED", set_values={**values, "approved_content_hash": b"'; DROP TABLE document; --"})
        self.assertEqual(bytes(document_row(self.db, doc.document_id)["approved_content_hash"]), b"'; DROP TABLE document; --")


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class ApprovalStep(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.get_db()
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-approval-step", min_size=1, max_size=4)
        cls.pool.open()
        cls.version_id = make_template_version(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()

    def step_of(self, doc):
        return scalar(self.db, "select id from approval_step where document_id = %s and step_kind = 'CONTENT_REVIEW'", doc.document_id)

    def go(self, step_id, **kw):
        with self.pool.acquire() as conn, unit_of_work(conn):
            return tr.transition(conn, "approval_step", step_id, **kw)

    def test_open_sang_decided_dat_closed_at_va_tang_row_version(self):
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        step = self.step_of(doc)
        before = rows(self.db, "select status, closed_at, row_version, updated_at from approval_step where id = %s", step)[0]
        self.assertEqual((before[0], before[1]), ("OPEN", None))
        r = self.go(step, to="DECIDED", expected_from="OPEN")
        after = rows(self.db, "select status, closed_at is not null, row_version, updated_at > %s from approval_step where id = %s", before[3], step)[0]
        self.assertEqual((r.status, r.changed, r.row_version), ("DECIDED", True, before[2] + 1))
        self.assertEqual(after, ("DECIDED", True, before[2] + 1, True))

    def test_open_sang_cancelled(self):
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        step = self.step_of(doc)
        self.go(step, to="CANCELLED")
        self.assertEqual(rows(self.db, "select status, closed_at is not null from approval_step where id = %s", step), [("CANCELLED", True)])

    def test_khong_canh_quay_lai(self):
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        step = self.step_of(doc)
        self.go(step, to="DECIDED")
        for target in ("OPEN", "CANCELLED"):
            with self.assertRaises(tr.IllegalTransition, msg=target):
                self.go(step, to=target)
        self.assertEqual(scalar(self.db, "select status from approval_step where id = %s", step), "DECIDED")

    def test_da_decided_thi_khong_lam_gi(self):
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        step = self.step_of(doc)
        self.go(step, to="DECIDED")
        before = rows(self.db, "select status, closed_at, row_version, updated_at from approval_step where id = %s", step)
        self.assertFalse(self.go(step, to="DECIDED").changed)
        self.assertEqual(rows(self.db, "select status, closed_at, row_version, updated_at from approval_step where id = %s", step), before)

    def test_expected_from_lech(self):
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        step = self.step_of(doc)
        with self.assertRaises(tr.StaleStatus):
            self.go(step, to="DECIDED", expected_from="DECIDED")

    def test_khong_nhan_cot_moc_hay_set_values_la(self):
        doc = make_pending_approval(self.db, self.pool, self.version_id)
        step = self.step_of(doc)
        with self.assertRaises(tr.ExtraColumnNotAllowed):
            self.go(step, to="DECIDED", extra_now=("self_approval_reason",))
        with self.assertRaises(tr.ExtraColumnNotAllowed):
            self.go(step, to="DECIDED", set_values={"self_approved": True})
        self.assertEqual(scalar(self.db, "select status from approval_step where id = %s", step), "OPEN")


if __name__ == "__main__":
    unittest.main()
