"""`request_submit` (B7) — trên PostgreSQL thật, role `bo19_app`.

Điều được chứng minh, nói bằng hành vi:
- **AC-1.4:** còn MỘT giá trị `HR_PROFILE` chưa xác nhận thì `REQUEST_NOT_READY`, kể cả khi mọi giá trị khác đã xác nhận — với từng slot `HR_PROFILE` bắt buộc; không ghi gì;
- hàm kiểm F1 chạy LẠI trên dữ liệu trong giao dịch: một giá trị đổi sau lúc graph thấy "đủ" vẫn bị chặn;
- đạt thì `DRAFT → SUBMITTED`, một `decision_record` `SUBMITTED` (id = khoá), một `audit_event`, một job `render_document` — payload **chỉ mang id**, không giá trị slot;
- hai lần gửi đồng thời: một `decision_record`, một job; gửi lại cùng khoá là lặp lại, không ghi thêm; `dedupe_key` của job là lớp thứ hai;
- chỉ người tạo gửi được; khoá của người khác không trả gì về dòng của họ; `row_version` lệch hay trạng thái khác thì `STATE_CONFLICT`.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_request_submit -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import json
import threading
import unittest
import uuid

from bo19.tool_layer.gate_ops.request_submit import DecisionIdConflict, NotReady, StateConflict, request_submit
from bo19.tool_layer.kernel.permission import PermissionDenied
from bo19.tool_layer.tools._common import NotOwnRequest
from tests.request_support import HR_REQUIRED, build_request
from tests.tool_support import RES, ToolBase


class SubmitBase(ToolBase):
    def ready(self, *, leave_unconfirmed: tuple[str, ...] = (), ctx_pair=None) -> tuple[uuid.UUID, object, uuid.UUID]:
        """Một `request` `WORK_CONFIRMATION` của một nhân viên mới (hoặc `ctx_pair`) — mọi slot `HR_PROFILE` bắt buộc đã xác nhận trừ `leave_unconfirmed`."""
        eid, ctx = ctx_pair or self.employee()
        return eid, ctx, build_request(self.pool, self.db, eid, ctx, leave_unconfirmed=leave_unconfirmed)

    def submit(self, ctx, rid, *, key=None, version=None):
        return request_submit(self.pool, ctx, request_id=rid, decision_id=key or uuid.uuid4(), expected_row_version=self.request_row(rid)["row_version"] if version is None else version)

    def decisions(self, rid) -> list[dict]:
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select id, kind, actor_employee_id, request_id, document_id from decision_record where request_id = %s", (rid,))
            return [dict(zip([d.name for d in cur.description], r)) for r in cur.fetchall()]

    def jobs(self, rid) -> list[dict]:
        with self.db.connect("bo19_migrator") as c:
            cur = c.execute("select id, job_type, status, payload, dedupe_key, subject_document_id, max_attempts, attempts from job where dedupe_key = %s or payload->>'request_id' = %s",
                            (str(rid), str(rid)))
            return [dict(zip([d.name for d in cur.description], r)) for r in cur.fetchall()]

    def submits(self, rid) -> list[dict]:
        return [a for a in self.audit(rid) if a["action"] == "request.submit"]

    def assert_nothing_written(self, rid, status="DRAFT"):
        self.assertEqual(self.request_row(rid)["status"], status)
        self.assertEqual(self.decisions(rid), [])
        self.assertEqual(self.jobs(rid), [])
        self.assertEqual(self.submits(rid), [])


class Ac14(SubmitBase):
    def test_ac_1_4_mot_slot_hr_chua_xac_nhan_thi_not_ready_ke_ca_khi_moi_slot_khac_da_xac_nhan(self):
        for name in HR_REQUIRED:
            with self.subTest(slot=name):
                eid, ctx, rid = self.ready(leave_unconfirmed=(name,))
                slots = self.slot_rows(rid)
                self.assertEqual({n for n, s in slots.items() if s["value_status"] == "PROPOSED"}, {name})  # đúng một giá trị chưa xác nhận
                self.assertTrue(all(slots[n]["value_status"] == "CONFIRMED" for n in HR_REQUIRED if n != name))
                with self.assertRaises(NotReady) as cm:
                    self.submit(ctx, rid)
                self.assertEqual(cm.exception.unconfirmed_slots, (name,))
                self.assertEqual((cm.exception.missing_slots, cm.exception.failed_rules), ((), ()))
                self.assert_nothing_written(rid)

    def test_du_dieu_kien_thi_gui_duoc(self):
        eid, ctx, rid = self.ready()
        before = self.request_row(rid)
        key = uuid.uuid4()
        out = self.submit(ctx, rid, key=key, version=before["row_version"])
        self.assertEqual((out.decision_record_id, out.replayed), (key, False))
        after = self.request_row(rid)
        self.assertEqual(after["status"], "SUBMITTED")
        self.assertEqual(after["row_version"], before["row_version"] + 1)
        with self.db.connect("bo19_migrator") as c:
            submitted_at = c.execute("select submitted_at from request where id = %s", (rid,)).fetchone()[0]
        self.assertIsNotNone(submitted_at)
        self.assertEqual(self.decisions(rid), [{"id": key, "kind": "SUBMITTED", "actor_employee_id": eid, "request_id": rid, "document_id": None}])
        audits = self.submits(rid)
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0]["actor_employee_id"], eid)
        self.assertEqual(audits[0]["payload"]["status_to"], "SUBMITTED")

    def test_ham_kiem_chay_lai_khong_tin_ket_qua_truoc_do(self):
        """Graph đã thấy "đủ" (mọi slot qua); sau đó một giá trị đổi thành trượt rule — `submit` vẫn chặn, vì nó kiểm lại trong chính giao dịch của nó."""
        eid, ctx, rid = self.ready()
        with self.db.connect("bo19_migrator") as c:
            c.execute("update request_slot set value = '\"vay\"'::jsonb where request_id = %s and slot_name = 'purpose'", (rid,))  # 1 tiếng < min_tokens 3
        with self.assertRaises(NotReady) as cm:
            self.submit(ctx, rid)
        self.assertEqual(cm.exception.failed_rules, (("purpose", "RULE_MIN_TOKENS"),))
        self.assert_nothing_written(rid)

    def test_slot_bat_buoc_bi_xoa_la_thieu(self):
        eid, ctx, rid = self.ready()
        with self.db.connect("bo19_migrator") as c:
            c.execute("delete from request_slot where request_id = %s and slot_name = 'recipient_org'", (rid,))
        with self.assertRaises(NotReady) as cm:
            self.submit(ctx, rid)
        self.assertEqual(cm.exception.missing_slots, ("recipient_org",))
        self.assert_nothing_written(rid)

    def test_loi_khong_mang_gia_tri(self):
        eid, ctx, rid = self.ready(leave_unconfirmed=("full_name",))
        with self.assertRaises(NotReady) as cm:
            self.submit(ctx, rid)
        blob = repr(cm.exception) + str(cm.exception) + repr(vars(cm.exception))
        self.assertNotIn(RES, blob)
        self.assertNotIn("GIẢ", blob)  # họ tên giả và nơi nhận giả


class JobVaPayload(SubmitBase):
    def test_job_render_document_chi_mang_id(self):
        eid, ctx, rid = self.ready()
        key = uuid.uuid4()
        self.submit(ctx, rid, key=key)
        jobs = self.jobs(rid)
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual((job["job_type"], job["status"], job["attempts"], job["max_attempts"]), ("render_document", "QUEUED", 0, 5))
        self.assertEqual(job["payload"], {"request_id": str(rid), "decision_record_id": str(key)})  # đúng hai khoá, đúng hai id
        self.assertEqual(job["dedupe_key"], str(rid))
        self.assertIsNone(job["subject_document_id"])
        audit = self.submits(rid)[0]["payload"]
        self.assertEqual((audit["job_id"], audit["job_created"]), (str(job["id"]), True))

    def test_payload_va_audit_khong_chua_gia_tri_slot(self):
        eid, ctx, rid = self.ready()
        self.submit(ctx, rid)
        blob = json.dumps([self.jobs(rid), self.submits(rid)], ensure_ascii=False, default=str)
        for name, row in self.slot_rows(rid).items():
            value = row["value"]
            if isinstance(value, str) and name not in ("beneficiary_employee_id",):  # id người thụ hưởng là uuid — không phải giá trị nội dung
                self.assertNotIn(value, blob, name)
        self.assertNotIn(RES, blob)

    def test_khoa_chong_trung_job_la_lop_thu_hai(self):
        """Một job `render_document` còn `QUEUED` cho cùng `request` (đường nào đó lách khoá hàng) — `submit` không tạo job thứ hai."""
        eid, ctx, rid = self.ready()
        existing = uuid.uuid4()
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into job (id, job_type, payload, dedupe_key, max_attempts) values (%s, 'render_document', '{}'::jsonb, %s, 5)", (existing, str(rid)))
        self.submit(ctx, rid)
        jobs = [j for j in self.jobs(rid) if j["status"] == "QUEUED"]
        self.assertEqual([j["id"] for j in jobs], [existing])
        self.assertEqual(self.submits(rid)[0]["payload"]["job_created"], False)


class LapLaiVaDongThoi(SubmitBase):
    def test_gui_lai_cung_khoa_la_lap_lai_khong_ghi_them(self):
        eid, ctx, rid = self.ready()
        key = uuid.uuid4()
        first = self.submit(ctx, rid, key=key)
        again = self.submit(ctx, rid, key=key, version=1)  # `row_version` cũ: lặp lại không cần khớp — trả quyết định đã có
        self.assertEqual((again.decision_record_id, again.replayed, again.created_at), (key, True, first.created_at))
        self.assertEqual(len(self.decisions(rid)), 1)
        self.assertEqual(len(self.jobs(rid)), 1)
        self.assertEqual(len(self.submits(rid)), 1)

    def test_khoa_moi_sau_khi_da_gui_la_state_conflict(self):
        eid, ctx, rid = self.ready()
        version = self.request_row(rid)["row_version"]
        self.submit(ctx, rid, version=version)
        with self.assertRaises(StateConflict) as cm:
            self.submit(ctx, rid, version=version)
        self.assertEqual(cm.exception.current_status, "SUBMITTED")
        self.assertEqual(len(self.decisions(rid)), 1)

    def test_hai_lan_gui_dong_thoi_khac_khoa_mot_decision_mot_job(self):
        eid, ctx, rid = self.ready()
        version = self.request_row(rid)["row_version"]
        out, errors, barrier = [], [], threading.Barrier(4)

        def go():
            barrier.wait()
            try:
                out.append(request_submit(self.pool, ctx, request_id=rid, decision_id=uuid.uuid4(), expected_row_version=version))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=go) for _ in range(4)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        self.assertEqual(len(out), 1)
        self.assertEqual(len(errors), 3)
        self.assertTrue(all(isinstance(e, StateConflict) and e.current_status == "SUBMITTED" for e in errors), errors)
        self.assertEqual(len(self.decisions(rid)), 1)
        self.assertEqual(len(self.jobs(rid)), 1)
        self.assertEqual(len(self.submits(rid)), 1)

    def test_hai_lan_gui_dong_thoi_cung_khoa_mot_decision_mot_job(self):
        eid, ctx, rid = self.ready()
        version, key = self.request_row(rid)["row_version"], uuid.uuid4()
        out, errors, barrier = [], [], threading.Barrier(4)

        def go():
            barrier.wait()
            try:
                out.append(request_submit(self.pool, ctx, request_id=rid, decision_id=key, expected_row_version=version))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=go) for _ in range(4)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual({o.decision_record_id for o in out}, {key})
        self.assertEqual(sum(not o.replayed for o in out), 1)
        self.assertEqual(len(self.decisions(rid)), 1)
        self.assertEqual(len(self.jobs(rid)), 1)


class QuyenVaTrangThai(SubmitBase):
    def test_nguoi_khac_khong_gui_duoc_va_khong_biet_request_ton_tai(self):
        eid, ctx, rid = self.ready()
        _, other = self.employee()
        with self.assertRaises(NotOwnRequest):
            self.submit(other, rid)
        with self.assertRaises(NotOwnRequest):
            self.submit(other, uuid.uuid4(), version=1)
        self.assert_nothing_written(rid)

    def test_thieu_permission(self):
        eid, ctx, rid = self.ready()
        with self.db.connect("bo19_migrator") as c:
            c.execute("delete from employee_role where employee_id = %s", (eid,))
        with self.assertRaises(PermissionDenied):
            self.submit(self.ctx(eid), rid)
        self.assert_nothing_written(rid)

    def test_khoa_da_la_quyet_dinh_cua_nguoi_khac_hay_request_khac(self):
        eid, ctx, rid = self.ready()
        key = uuid.uuid4()
        self.submit(ctx, rid, key=key)
        e2, ctx2, rid2 = self.ready()
        with self.assertRaises(DecisionIdConflict):
            self.submit(ctx2, rid2, key=key)  # khoá là quyết định của người khác
        self.assert_nothing_written(rid2)
        _, _, rid3 = self.ready(ctx_pair=(eid, ctx))
        with self.assertRaises(DecisionIdConflict):
            self.submit(ctx, rid3, key=key)  # cùng người, `request` khác
        self.assert_nothing_written(rid3)

    def test_row_version_lech_la_state_conflict(self):
        eid, ctx, rid = self.ready()
        version = self.request_row(rid)["row_version"]
        with self.assertRaises(StateConflict) as cm:
            self.submit(ctx, rid, version=version + 1)
        self.assertEqual(cm.exception.current_status, "DRAFT")
        self.assert_nothing_written(rid)

    def test_trang_thai_ngoai_draft_needs_info(self):
        for status in ("SUBMITTED", "IN_REVIEW", "CHANGES_REQUESTED", "APPROVED", "CANCELLED", "EXPIRED"):
            with self.subTest(status=status):
                eid, ctx, rid = self.ready()
                self.set_status(rid, status)
                with self.assertRaises(StateConflict) as cm:
                    self.submit(ctx, rid)
                self.assertEqual(cm.exception.current_status, status)
                self.assertEqual(self.decisions(rid), [])
                self.assertEqual(self.jobs(rid), [])

    def test_trang_thai_kiem_truoc_ham_kiem(self):
        """`CHANGES_REQUESTED` ca `SLOT_DATA` bỏ xác nhận slot `HR_PROFILE` — tới O1-15 nó phải là `STATE_CONFLICT`, không phải `REQUEST_NOT_READY` (bảo nhân viên bổ sung vào yêu cầu không sửa được)."""
        for status in ("CHANGES_REQUESTED", "SUBMITTED"):
            with self.subTest(status=status):
                eid, ctx, rid = self.ready(leave_unconfirmed=("full_name",))
                self.set_status(rid, status)
                with self.assertRaises(StateConflict) as cm:
                    self.submit(ctx, rid)
                self.assertEqual(cm.exception.current_status, status)

    def test_needs_info_chua_du_thi_not_ready_du_roi_van_state_conflict(self):
        eid, ctx, rid = self.ready(leave_unconfirmed=("job_title",))
        self.set_status(rid, "NEEDS_INFO")
        with self.assertRaises(NotReady) as cm:
            self.submit(ctx, rid)
        self.assertEqual(cm.exception.unconfirmed_slots, ("job_title",))
        with self.db.connect("bo19_migrator") as c:  # đủ điều kiện mà vẫn NEEDS_INFO (lượt sau chưa kịp đưa về DRAFT): không tự đi hai cạnh
            c.execute("update request_slot set value_status = 'CONFIRMED', confirmed_at = now() where request_id = %s and slot_name = 'job_title'", (rid,))
        with self.assertRaises(StateConflict) as cm:
            self.submit(ctx, rid)
        self.assertEqual(cm.exception.current_status, "NEEDS_INFO")
        self.assert_nothing_written(rid, status="NEEDS_INFO")


if __name__ == "__main__":
    unittest.main()
