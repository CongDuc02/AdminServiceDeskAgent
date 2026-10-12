"""`chat_turn_context_read` và `tool_layer.checks.config` — B6b, trên PostgreSQL thật.

Điều được chứng minh: chỉ chủ phiên đọc được, chỉ tin `EMPLOYEE` của chính phiên đó; ba lý do từ chối cho cùng một mã (không lộ sự tồn tại); lỗi và `repr` không mang văn bản tin nhắn;
`request` gắn với phiên là cái mới nhất ở mọi trạng thái; hàm đọc cấu hình trả đúng catalog (năm trường mà `catalog_fingerprint` hash), `slot_specs` chỉ slot `USER_INPUT`, nhãn và tên loại.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_tools_turn_context -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest
import uuid

from bo19.ai_gateway.prompt_modules import catalog_fingerprint
from bo19.tool_layer.checks import config as cfg
from bo19.tool_layer.endpoint_ops import chat as ch
from bo19.tool_layer.kernel.permission import PermissionDenied
from bo19.tool_layer.tools.chat_turn_context_read import MessageNotFound, chat_turn_context_read
from tests.tool_support import RES, ToolBase


class DocLuot(ToolBase):
    def setUp(self):
        super().setUp()
        self.eid, self.ctx_ = self.employee()
        self.sid, self.mid = self.say(self.eid, self.ctx_, "xin giấy xác nhận " + RES)

    def read(self, *, ctx=None, sid=None, mid=None):
        return chat_turn_context_read(self.pool, ctx or self.ctx_, chat_session_id=sid or self.sid, message_id=mid or self.mid)

    def test_tra_van_ban_tin_nhan_cua_chu_phien_va_chua_co_request(self):
        r = self.read()
        self.assertEqual((r.message_id, r.body, r.active_request), (self.mid, "xin giấy xác nhận " + RES, None))

    def test_repr_khong_mang_van_ban(self):
        self.assertNotIn(RES, repr(self.read()))

    def test_request_gan_voi_phien_moi_nhat_o_moi_trang_thai(self):
        _, _, rid, _ = self.open_request(self.eid, self.ctx_)  # phiên mở của chính nhân viên có sẵn → request đầu
        sid = ch.chat_session_open(self.pool, self.ctx_).chat_session_id
        first = self.read(sid=sid, mid=self.msg_in(sid))
        self.assertEqual((first.active_request.request_id, first.active_request.request_type_code, first.active_request.status), (rid, "WORK_CONFIRMATION", "DRAFT"))
        self.assertEqual(first.active_request.row_version, self.request_row(rid)["row_version"])
        with self.db.connect("bo19_migrator") as c:  # đổi sang trạng thái ngoài giai đoạn thu thập: vẫn trả về, không bị gỡ khỏi phiên
            c.execute("update request set status = 'SUBMITTED', row_version = row_version + 1 where id = %s", (rid,))
        self.assertEqual(self.read(sid=sid, mid=self.msg_in(sid)).active_request.status, "SUBMITTED")

    def msg_in(self, sid) -> uuid.UUID:
        return self.say(self.eid, self.ctx_, "tin mới", session_id=sid)[1]

    def test_lay_request_moi_nhat_khi_co_hai(self):
        sid, _, first, _ = self.open_request(self.eid, self.ctx_)
        with self.db.connect("bo19_migrator") as c:
            c.execute("update request set status = 'CANCELLED', closed_at = now() where id = %s", (first,))
        mid = self.msg_in(sid)
        from bo19.tool_layer.tools.request_open import request_open
        second = request_open(self.pool, self.ctx_, chat_session_id=sid, request_type="WORK_CONFIRMATION", beneficiary_employee_id=self.eid, opened_by_message_id=mid).request_id
        self.assertEqual(self.read(sid=sid, mid=mid).active_request.request_id, second)

    def test_ba_ly_do_tu_choi_tin_cung_mot_ma(self):
        other_eid, other = self.employee()
        _, foreign_mid = self.say(other_eid, other, "tin của người khác")
        agent = ch.chat_message_append(self.pool, self.sys, chat_session_id=self.sid, message_id=uuid.uuid4(), author="AGENT", body="đã nhận " + RES, reply_template_id="ASK_SLOT").message_id
        for label, mid in (("tin phiên khác", foreign_mid), ("tin của agent", agent), ("không tồn tại", uuid.uuid4())):
            with self.assertRaises(MessageNotFound, msg=label) as cm:
                self.read(mid=mid)
            self.assertNotIn(RES, str(cm.exception))

    def test_phien_cua_nguoi_khac_hay_khong_ton_tai_cung_mot_ma(self):
        _, other = self.employee()
        for sid in (self.sid, uuid.uuid4()):
            with self.assertRaises(ch.ChatSessionNotFound):
                self.read(ctx=other, sid=sid)

    def test_thieu_quyen_va_tac_nhan_he_thong(self):
        _, no_perm = self.employee(roles=())
        with self.assertRaises(PermissionDenied):
            self.read(ctx=no_perm)
        with self.assertRaises(Exception) as cm:  # hệ thống không "sở hữu" phiên nào — không đọc được văn bản tin nhắn
            self.read(ctx=self.sys)
        self.assertNotIn(RES, str(cm.exception))

    def test_van_ban_da_xoa_thi_body_none(self):
        with self.db.connect("bo19_migrator") as c:
            c.execute("update chat_message set body = null, content_erased_at = now() where id = %s", (self.mid,))
        self.assertIsNone(self.read().body)

    def test_chi_doc_khong_sinh_audit_va_khong_ghi(self):
        before = self.count_rows()
        self.read()
        self.assertEqual(self.count_rows(), before)

    def count_rows(self):
        with self.db.connect("bo19_migrator") as c:
            return c.execute("select (select count(*) from audit_event), (select count(*) from chat_message), (select count(*) from request)").fetchone()


class DocCauHinh(ToolBase):
    def test_catalog_dung_nam_truong_va_dung_vao_fingerprint(self):
        catalog = cfg.load_catalog(self.pool)
        self.assertEqual([c["code"] for c in catalog], sorted(c["code"] for c in catalog))
        self.assertTrue(all(set(c) == {"code", "support_status", "name_vi", "description", "example_phrases"} for c in catalog))
        by = {c["code"]: c for c in catalog}
        self.assertEqual(by["WORK_CONFIRMATION"]["support_status"], "SUPPORTED")
        self.assertEqual(sum(c["support_status"] == "SUPPORTED" for c in catalog), 1)
        self.assertTrue(by["WORK_CONFIRMATION"]["example_phrases"])
        self.assertTrue(all(isinstance(p, str) for p in by["WORK_CONFIRMATION"]["example_phrases"]))
        self.assertEqual(len(catalog_fingerprint(catalog)), 64)

    def test_slot_specs_chi_user_input(self):
        specs = cfg.slot_specs(self.pool, "WORK_CONFIRMATION")
        self.assertEqual({s["slot_name"] for s in specs}, {"purpose", "recipient_org", "copies_count"})
        self.assertTrue(all(set(s) == {"slot_name", "data_type", "description"} and s["description"] for s in specs))
        self.assertEqual(cfg.slot_specs(self.pool, "KHONG_CO"), [])

    def test_nhan_slot_va_ten_loai(self):
        labels = cfg.slot_labels(self.pool, "WORK_CONFIRMATION")
        self.assertTrue(labels["purpose"].strip() and labels["recipient_org"].strip())
        self.assertEqual(set(cfg.type_names(self.pool, supported_only=True)), {"WORK_CONFIRMATION"})
        self.assertGreater(len(cfg.type_names(self.pool)), 1)

    def test_check_completeness_dung_ham_f1(self):
        eid, ctx = self.employee()
        _, _, rid, _ = self.open_request(eid, ctx)
        r = cfg.check_completeness(self.pool, rid)
        self.assertFalse(r.eligible)
        self.assertTrue(r.reasons)


if __name__ == "__main__":
    unittest.main()
