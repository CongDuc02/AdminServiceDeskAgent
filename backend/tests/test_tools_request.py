"""`request_open`, `request_transition`, `request_slots_read` (`tool_layer.tools`) trên PostgreSQL thật — B6a.

Điều được chứng minh: mở `request` idempotent theo tin nhắn của lượt (kể cả đồng thời); chỉ loại `SUPPORTED`; lập hộ người khác cần `request.create_on_behalf`; đổi loại huỷ `request` cũ cùng giao dịch và
không huỷ ngầm `request` đã gửi; `request_transition` chỉ `DRAFT ↔ NEEDS_INFO` và chỉ tác nhân hệ thống; `request_slots_read` từ chối slot không khai TRƯỚC khi đọc.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_tools_request -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import threading
import unittest
import uuid

from psycopg.types.json import Jsonb

from bo19.tool_layer.checks.eligibility import RequestNotFound
from bo19.tool_layer.endpoint_ops.chat import chat_message_append, chat_session_open
from bo19.tool_layer.kernel.permission import PermissionDenied, SystemActorRequired
from bo19.tool_layer.kernel.transition import IllegalTransition, RowNotFound
from bo19.tool_layer.tools import request_open as ro
from bo19.tool_layer.tools._common import NotOwnRequest
from bo19.tool_layer.tools.request_slots_read import SlotNotDeclared, request_slots_read
from bo19.tool_layer.tools.request_transition import request_transition
from tests.tool_support import RES, ToolBase


class MoRequest(ToolBase):
    def test_mo_request_ghi_dung_cac_cot_slot_he_thong_audit_va_gan_tin_nhan(self):
        eid, ctx = self.employee()
        sid, mid, rid, result = self.open_request(eid, ctx)
        self.assertEqual((result.created, result.replaced_request_id), (True, None))
        row = self.request_row(rid)
        self.assertEqual((row["status"], row["created_by_employee_id"], row["beneficiary_employee_id"], row["chat_session_id"], row["opened_by_message_id"], row["replaces_request_id"]),
                         ("DRAFT", eid, eid, sid, mid, None))
        with self.db.connect("bo19_migrator") as c:
            code = c.execute("select employee_code from employee where id = %s", (eid,)).fetchone()[0]
            self.assertEqual(c.execute("select request_id from chat_message where id = %s", (mid,)).fetchone()[0], rid)
        slots = self.slot_rows(rid)
        self.assertEqual({n: (s["value"], s["value_status"]) for n, s in slots.items()},
                         {"requester_employee_code": (code, "SYSTEM_SET"), "beneficiary_employee_id": (str(eid), "SYSTEM_SET")})
        (event,) = self.audit(rid)
        self.assertEqual((event["actor_kind"], event["actor_employee_id"], event["action"], event["entity_type"], event["entity_id"], event["severity"]), ("EMPLOYEE", eid, "request.open", "request", str(rid), "INFO"))
        self.assertEqual(event["payload"], {"request_type": "WORK_CONFIRMATION", "on_behalf": False, "replaced": False})

    def test_goi_lai_cung_tin_nhan_tra_dung_request_do_khong_nhan_doi(self):
        eid, ctx = self.employee()
        sid, mid, rid, first = self.open_request(eid, ctx)
        again = ro.request_open(self.pool, ctx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=eid, opened_by_message_id=mid)
        self.assertEqual((again.created, again.request_id), (False, rid))
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select count(*) from request where opened_by_message_id = %s", (mid,)).fetchone()[0], 1)
        self.assertEqual(len(self.audit(rid)), 1)
        self.assertEqual(len(self.slot_rows(rid)), 2)

    def test_dong_thoi_cung_tin_nhan_chi_mot_request(self):
        eid, ctx = self.employee()
        sid, mid = self.say(eid, ctx, "xin giấy xác nhận công tác")
        out, errors, barrier = [], [], threading.Barrier(5)

        def go():
            barrier.wait()
            try:
                out.append(ro.request_open(self.pool, ctx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=eid, opened_by_message_id=mid))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=go) for _ in range(5)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(len({o.request_id for o in out}), 1)
        self.assertEqual(sum(o.created for o in out), 1)

    def test_loai_chua_ho_tro_hoac_khong_co_bi_tu_choi_khong_ghi_gi(self):
        eid, ctx = self.employee()
        sid, mid = self.say(eid, ctx, "xin giấy giới thiệu")
        for code in ("INTRODUCTION_LETTER", "INCOME_CONFIRMATION", "KHONG_CO_LOAI_NAY", "x" * 100):
            with self.assertRaises(ro.TypeNotSupported, msg=code):
                ro.request_open(self.pool, ctx, chat_session_id=sid, request_type=code, beneficiary_employee_id=eid, opened_by_message_id=mid)
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select count(*) from request where chat_session_id = %s", (sid,)).fetchone()[0], 0)

    def test_quyen(self):
        noperm, noperm_ctx = self.employee(roles=())
        eid, ctx = self.employee()  # có request.create nhưng không có create_on_behalf
        other, _ = self.employee()
        sid, mid = self.say(eid, ctx, "xin giấy")
        with self.assertRaises(PermissionDenied):  # kiểm quyền đến trước mọi lần đọc DB: id bất kỳ cũng được
            ro.request_open(self.pool, noperm_ctx, chat_session_id=uuid.uuid4(), request_type="WORK_CONFIRMATION", beneficiary_employee_id=noperm, opened_by_message_id=uuid.uuid4())
        with self.assertRaises(PermissionDenied):
            ro.request_open(self.pool, ctx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=other, opened_by_message_id=mid)
        with self.assertRaises(NotOwnRequest):  # tác nhân hệ thống không mở request
            ro.request_open(self.pool, self.sys, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=eid, opened_by_message_id=mid)
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select count(*) from request where chat_session_id = %s", (sid,)).fetchone()[0], 0)

    def test_lap_ho_nguoi_khac_can_create_on_behalf(self):
        officer, octx = self.employee(roles=("ADMIN_OFFICER",))
        target, _ = self.employee()
        sid, mid = self.say(officer, octx, "lập giấy giúp đồng nghiệp")
        result = ro.request_open(self.pool, octx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=target, opened_by_message_id=mid)
        row = self.request_row(result.request_id)
        self.assertEqual((row["created_by_employee_id"], row["beneficiary_employee_id"]), (officer, target))
        self.assertEqual(self.slot_rows(result.request_id)["beneficiary_employee_id"]["value"], str(target))
        self.assertEqual(self.audit(result.request_id)[0]["payload"]["on_behalf"], True)

    def test_nguoi_thu_huong_khong_ton_tai_hoac_nghi_viec(self):
        officer, octx = self.employee(roles=("ADMIN_OFFICER",))
        gone, _ = self.db.make_employee(active=False)  # nghỉ việc: không dựng được ngữ cảnh, chỉ làm người thụ hưởng
        sid, mid = self.say(officer, octx, "lập giấy")
        for target in (uuid.uuid4(), gone):
            with self.assertRaises(ro.BeneficiaryNotFound):
                ro.request_open(self.pool, octx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=target, opened_by_message_id=mid)

    def test_phien_va_tin_nhan_phai_hop_le(self):
        eid, ctx = self.employee()
        other, octx = self.employee()
        sid, mid = self.say(eid, ctx, "tin của tôi")
        osid, omid = self.say(other, octx, "tin của người khác")
        for session, message in ((osid, omid), (sid, omid), (uuid.uuid4(), mid)):  # phiên người khác · tin ở phiên khác · phiên không tồn tại
            with self.assertRaises((ro.ChatSessionInvalid, ro.MessageInvalid)):
                ro.request_open(self.pool, ctx, chat_session_id=session, request_type="WORK_CONFIRMATION", beneficiary_employee_id=eid, opened_by_message_id=message)
        agent = uuid.uuid4()
        chat_message_append(self.pool, self.sys, chat_session_id=sid, message_id=agent, author="AGENT", body="trả lời", reply_template_id="ASK_SLOT")
        with self.assertRaises(ro.MessageInvalid):  # tin của agent không thể mở request
            ro.request_open(self.pool, ctx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=eid, opened_by_message_id=agent)
        with self.db.connect("bo19_migrator") as c:
            c.execute("update chat_session set status = 'CLOSED', closed_at = now(), close_reason = 'IDLE_TIMEOUT' where id = %s", (sid,))
        with self.assertRaises(ro.ChatSessionInvalid):
            ro.request_open(self.pool, ctx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=eid, opened_by_message_id=mid)

    def test_doi_loai_huy_request_cu_cung_giao_dich(self):
        eid, ctx = self.employee()
        sid, mid, old, _ = self.open_request(eid, ctx)
        mid2 = uuid.uuid4()
        chat_message_append(self.pool, ctx, chat_session_id=sid, message_id=mid2, author="EMPLOYEE", body="à nhầm, làm lại")
        new = ro.request_open(self.pool, ctx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=eid, opened_by_message_id=mid2, replaces_request_id=old)
        self.assertEqual((new.created, new.replaced_request_id), (True, old))
        old_row = self.request_row(old)
        self.assertEqual(old_row["status"], "CANCELLED")
        self.assertIsNotNone(old_row["closed_at"])
        self.assertEqual(self.request_row(new.request_id)["replaces_request_id"], old)
        self.assertEqual([e["action"] for e in self.audit(old)], ["request.open", "request.cancel"])
        self.assertEqual(self.audit(old)[1]["payload"], {"reason": "REPLACED_BY_NEW_TYPE"})

    def test_request_cu_da_gui_khong_bi_huy_ngam(self):
        eid, ctx = self.employee()
        sid, mid, old, _ = self.open_request(eid, ctx)
        self.set_status(old, "SUBMITTED")
        mid2 = uuid.uuid4()
        chat_message_append(self.pool, ctx, chat_session_id=sid, message_id=mid2, author="EMPLOYEE", body="làm thêm một cái nữa")
        with self.assertRaises(ro.ReplacedNotDraft):
            ro.request_open(self.pool, ctx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=eid, opened_by_message_id=mid2, replaces_request_id=old)
        self.assertEqual(self.request_row(old)["status"], "SUBMITTED")  # nguyên vẹn
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select count(*) from request where opened_by_message_id = %s", (mid2,)).fetchone()[0], 0)  # và không có request mới

    def test_khong_huy_ho_request_cua_nguoi_khac(self):
        eid, ctx = self.employee()
        other, octx = self.employee()
        _, _, theirs, _ = self.open_request(other, octx)
        sid, mid = self.say(eid, ctx, "xin giấy")
        for target in (theirs, uuid.uuid4()):
            with self.assertRaises(NotOwnRequest):
                ro.request_open(self.pool, ctx, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=eid, opened_by_message_id=mid, replaces_request_id=target)
        self.assertEqual(self.request_row(theirs)["status"], "DRAFT")


class ChuyenTrangThaiCuaGraph(ToolBase):
    def setUp(self):
        super().setUp()
        self.eid, self.ctx_ = self.employee()
        _, _, self.rid, _ = self.open_request(self.eid, self.ctx_)

    def test_draft_sang_needs_info_va_ve(self):
        r = request_transition(self.pool, self.sys, request_id=self.rid, to="NEEDS_INFO")
        self.assertEqual((r.status, r.changed), ("NEEDS_INFO", True))
        row = self.request_row(self.rid)
        self.assertEqual(row["status"], "NEEDS_INFO")
        self.assertIsNotNone(row["needs_info_asked_at"])
        r = request_transition(self.pool, self.sys, request_id=self.rid, to="DRAFT")
        self.assertEqual((r.status, r.changed), ("DRAFT", True))
        events = [e for e in self.audit(self.rid) if e["action"] == "request.transition"]
        self.assertEqual([(e["actor_kind"], e["payload"]) for e in events], [("SYSTEM", {"from": "DRAFT", "to": "NEEDS_INFO"}), ("SYSTEM", {"from": "NEEDS_INFO", "to": "DRAFT"})])

    def test_chuyen_sang_trang_thai_dang_co_khong_lam_gi_va_khong_audit(self):
        request_transition(self.pool, self.sys, request_id=self.rid, to="NEEDS_INFO")
        before = (self.request_row(self.rid), len(self.audit(self.rid)))
        r = request_transition(self.pool, self.sys, request_id=self.rid, to="NEEDS_INFO")
        self.assertFalse(r.changed)
        self.assertEqual((self.request_row(self.rid), len(self.audit(self.rid))), before)

    def test_graph_khong_co_quyen_di_cac_canh_khac_ke_ca_canh_hop_le_cua_may(self):
        for target in ("SUBMITTED", "CANCELLED", "IN_REVIEW", "APPROVED", "EXPIRED", "KHONG_CO"):
            with self.assertRaises(IllegalTransition, msg=target):
                request_transition(self.pool, self.sys, request_id=self.rid, to=target)
        self.assertEqual(self.request_row(self.rid)["status"], "DRAFT")

    def test_request_da_roi_giai_doan_thu_thap_khong_keo_ve_duoc(self):
        for status in ("SUBMITTED", "IN_REVIEW", "CHANGES_REQUESTED", "APPROVED", "EXPIRED", "CANCELLED"):
            self.set_status(self.rid, status)
            for target in ("DRAFT", "NEEDS_INFO"):
                with self.assertRaises(IllegalTransition, msg=(status, target)):
                    request_transition(self.pool, self.sys, request_id=self.rid, to=target)
            self.assertEqual(self.request_row(self.rid)["status"], status)

    def test_chi_tac_nhan_he_thong_va_request_phai_ton_tai(self):
        with self.assertRaises(SystemActorRequired):
            request_transition(self.pool, self.ctx_, request_id=self.rid, to="NEEDS_INFO")
        with self.assertRaises(RowNotFound):
            request_transition(self.pool, self.sys, request_id=uuid.uuid4(), to="NEEDS_INFO")


class DocSlot(ToolBase):
    DECLARED = frozenset({"purpose", "recipient_org"})

    def setUp(self):
        super().setUp()
        self.eid, self.ctx_ = self.employee()
        _, self.mid, self.rid, _ = self.open_request(self.eid, self.ctx_)
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into request_slot (request_id, request_type_code, slot_name, value, value_status, confirmed_at) values (%s, 'WORK_CONFIRMATION', 'recipient_org', %s, 'CONFIRMED', now())",
                      (self.rid, Jsonb("Ngân hàng X")))
            c.execute("insert into request_slot (request_id, request_type_code, slot_name, value, value_status, value_erased_at) values (%s, 'WORK_CONFIRMATION', 'purpose', NULL, 'ERASED', now())", (self.rid,))

    def test_chi_tra_slot_duoc_xin_va_bo_slot_da_xoa(self):
        got = request_slots_read(self.pool, self.sys, request_id=self.rid, slot_names=["recipient_org", "purpose"], declared_slots=self.DECLARED)
        self.assertEqual(got, {"recipient_org": "Ngân hàng X"})  # purpose đã ERASED: không trả
        self.assertEqual(request_slots_read(self.pool, self.sys, request_id=self.rid, slot_names=[], declared_slots=self.DECLARED), {})

    def test_slot_khong_khai_bi_tu_choi_truoc_khi_doc(self):
        with self.assertRaises(SlotNotDeclared) as cm:
            request_slots_read(self.pool, self.sys, request_id=uuid.uuid4(), slot_names=["recipient_org", "national_id"], declared_slots=self.DECLARED)  # request không tồn tại, nhưng lỗi khai báo đến trước
        self.assertEqual(cm.exception.detail, "national_id")
        self.assertNotIn("Ngân hàng", str(cm.exception))

    def test_request_khong_ton_tai_va_tac_nhan_khong_phai_he_thong(self):
        with self.assertRaises(RequestNotFound):
            request_slots_read(self.pool, self.sys, request_id=uuid.uuid4(), slot_names=["purpose"], declared_slots=self.DECLARED)
        with self.assertRaises(SystemActorRequired):
            request_slots_read(self.pool, self.ctx_, request_id=self.rid, slot_names=["purpose"], declared_slots=self.DECLARED)

    def test_ten_slot_la_khong_vao_sql_nhu_chuoi(self):
        with self.assertRaises(SlotNotDeclared):
            request_slots_read(self.pool, self.sys, request_id=self.rid, slot_names=["purpose'; DROP TABLE request_slot; --"], declared_slots=self.DECLARED)
        self.assertEqual(len(self.slot_rows(self.rid)), 4)  # 2 slot SYSTEM_SET lúc mở + 2 slot thêm trong setUp


if __name__ == "__main__":
    unittest.main()
