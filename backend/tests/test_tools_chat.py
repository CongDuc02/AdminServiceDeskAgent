"""`chat_session_open` và `chat_message_append` (`tool_layer.endpoint_ops.chat`) trên PostgreSQL thật — B6a.

Điều được chứng minh: mở phiên idempotent kể cả khi đồng thời; `seq` liên tục không trùng dưới đồng thời; `id` do người gọi cấp nên gọi lại không làm gì; `body` lưu NFC; quyền theo chủ phiên; tin agent
bắt buộc mã khuôn và chỉ tác nhân hệ thống ghi được; cả hai thao tác KHÔNG sinh `audit_event` (danh sách miễn A-055).

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_tools_chat -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import threading
import unicodedata
import unittest
import uuid

from bo19.config import working_values as wv
from bo19.tool_layer.endpoint_ops import chat as ch
from bo19.tool_layer.kernel.permission import PermissionDenied, SystemActorRequired
from bo19.tool_layer.tools._common import NotOwnRequest
from tests.tool_support import RES, ToolBase


class MoPhien(ToolBase):
    def test_tao_phien_roi_tra_lai_chinh_phien_do(self):
        eid, ctx = self.employee()
        first = ch.chat_session_open(self.pool, ctx)
        again = ch.chat_session_open(self.pool, ctx)
        self.assertEqual((first.created, again.created, again.chat_session_id), (True, False, first.chat_session_id))
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select count(*), min(status) from chat_session where employee_id = %s", (eid,)).fetchone(), (1, "OPEN"))

    def test_phien_da_dong_khong_duoc_tra_lai(self):
        eid, ctx = self.employee()
        first = ch.chat_session_open(self.pool, ctx)
        with self.db.connect("bo19_migrator") as c:
            c.execute("update chat_session set status = 'CLOSED', closed_at = now(), close_reason = 'IDLE_TIMEOUT' where id = %s", (first.chat_session_id,))
        second = ch.chat_session_open(self.pool, ctx)
        self.assertTrue(second.created)
        self.assertNotEqual(second.chat_session_id, first.chat_session_id)

    def test_dong_thoi_chi_mot_phien(self):
        eid, ctx = self.employee()
        out: list[ch.SessionOpen] = []
        barrier = threading.Barrier(6)

        def go():
            barrier.wait()
            out.append(ch.chat_session_open(self.pool, ctx))

        threads = [threading.Thread(target=go) for _ in range(6)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        self.assertEqual(len(out), 6)
        self.assertEqual(len({o.chat_session_id for o in out}), 1)
        self.assertEqual(sum(o.created for o in out), 1)

    def test_phien_cua_hai_nguoi_khac_nhau(self):
        _, a = self.employee()
        _, b = self.employee()
        self.assertNotEqual(ch.chat_session_open(self.pool, a).chat_session_id, ch.chat_session_open(self.pool, b).chat_session_id)

    def test_thieu_quyen_hoac_la_he_thong_bi_tu_choi(self):
        _, no_perm = self.employee(roles=())
        with self.assertRaises(PermissionDenied):
            ch.chat_session_open(self.pool, no_perm)
        with self.assertRaises(NotOwnRequest):  # hệ thống không "sở hữu" phiên nào
            ch.chat_session_open(self.pool, self.sys)

    def test_khong_sinh_audit_event(self):  # A-055: mở phiên thuộc danh sách miễn
        eid, ctx = self.employee()
        ch.chat_session_open(self.pool, ctx)
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select count(*) from audit_event where trace_id = %s", (ctx.trace_id,)).fetchone()[0], 0)


class GhiTinNhan(ToolBase):
    def setUp(self):
        super().setUp()
        self.eid, self.ctx_ = self.employee()
        self.sid = ch.chat_session_open(self.pool, self.ctx_).chat_session_id

    def append(self, **kw):
        args = {"chat_session_id": self.sid, "message_id": uuid.uuid4(), "author": "EMPLOYEE", "body": "xin giấy xác nhận"} | kw
        return ch.chat_message_append(self.pool, self.ctx_, **args)

    def rows(self):
        with self.db.connect("bo19_migrator") as c:
            return c.execute("select seq, author, body, reply_template_id from chat_message where chat_session_id = %s order by seq", (self.sid,)).fetchall()

    def test_seq_tang_dan_va_cap_nhat_last_message_at(self):
        with self.db.connect("bo19_migrator") as c:
            before = c.execute("select last_message_at, row_version from chat_session where id = %s", (self.sid,)).fetchone()
        a = self.append(body="một")
        b = self.append(body="hai")
        r = ch.chat_message_append(self.pool, self.sys, chat_session_id=self.sid, message_id=uuid.uuid4(), author="AGENT", body="ba", reply_template_id="ASK_SLOT")
        self.assertEqual([a.seq, b.seq, r.seq], [1, 2, 3])
        self.assertEqual([(x[0], x[1]) for x in self.rows()], [(1, "EMPLOYEE"), (2, "EMPLOYEE"), (3, "AGENT")])
        with self.db.connect("bo19_migrator") as c:
            after = c.execute("select last_message_at, row_version from chat_session where id = %s", (self.sid,)).fetchone()
        self.assertGreater(after[0], before[0])
        self.assertEqual(after[1], before[1] + 3)

    def test_body_luu_nfc(self):
        decomposed = unicodedata.normalize("NFD", "bổ sung hồ sơ")
        self.assertNotEqual(decomposed, unicodedata.normalize("NFC", decomposed))
        self.append(body=decomposed)
        (stored,) = [r[2] for r in self.rows()]
        self.assertEqual(stored, unicodedata.normalize("NFC", "bổ sung hồ sơ"))

    def test_goi_lai_cung_id_khong_lam_gi(self):
        mid = uuid.uuid4()
        first = self.append(message_id=mid, body="lần đầu")
        again = self.append(message_id=mid, body="nội dung khác hẳn")
        self.assertEqual((first.created, again.created, again.seq), (True, False, first.seq))
        self.assertEqual([r[2] for r in self.rows()], ["lần đầu"])  # không ghi đè

    def test_id_trung_phien_khac_hoac_tac_gia_khac_la_xung_dot(self):
        mid = uuid.uuid4()
        self.append(message_id=mid)
        _, other = self.employee()
        other_sid = ch.chat_session_open(self.pool, other).chat_session_id
        with self.assertRaises(ch.MessageIdConflict):
            ch.chat_message_append(self.pool, other, chat_session_id=other_sid, message_id=mid, author="EMPLOYEE", body="x")
        with self.assertRaises(ch.MessageIdConflict):
            ch.chat_message_append(self.pool, self.sys, chat_session_id=self.sid, message_id=mid, author="AGENT", body="x", reply_template_id="ASK_SLOT")

    def test_phien_cua_nguoi_khac_hoac_khong_ton_tai_cung_mot_loi(self):
        _, other = self.employee()
        for sid in (self.sid, uuid.uuid4()):
            with self.assertRaises(ch.ChatSessionNotFound):
                ch.chat_message_append(self.pool, other, chat_session_id=sid, message_id=uuid.uuid4(), author="EMPLOYEE", body="x")

    def test_tin_agent_chi_tac_nhan_he_thong_va_bat_buoc_ma_khuon(self):
        with self.assertRaises(SystemActorRequired):
            ch.chat_message_append(self.pool, self.ctx_, chat_session_id=self.sid, message_id=uuid.uuid4(), author="AGENT", body="x", reply_template_id="ASK_SLOT")
        for tpl in (None, "", "ask_slot", "1ASK", "A B", "ASK-SLOT"):
            with self.assertRaises(ch.MessageInvalid, msg=repr(tpl)):
                ch.chat_message_append(self.pool, self.sys, chat_session_id=self.sid, message_id=uuid.uuid4(), author="AGENT", body="x", reply_template_id=tpl)
        self.assertEqual(self.rows(), [])

    def test_tin_nhan_vien_khong_duoc_mang_ma_khuon_va_tac_gia_la_bi_chan(self):
        with self.assertRaises(ch.MessageInvalid):
            self.append(reply_template_id="ASK_SLOT")
        with self.assertRaises(ch.MessageInvalid):
            self.append(author="ADMIN")

    def test_body_rong_hoac_qua_dai(self):
        for bad in ("", "   ", "\n\t"):
            with self.assertRaises(ch.MessageInvalid, msg=repr(bad)):
                self.append(body=bad)
        with self.assertRaises(ch.MessageInvalid):
            self.append(body="x" * (wv.CHAT_MESSAGE_MAX_CHARS + 1))
        ok = self.append(body="x" * wv.CHAT_MESSAGE_MAX_CHARS)  # đúng bằng trần thì qua
        self.assertTrue(ok.created)

    def test_loi_khong_mang_noi_dung_tin_nhan(self):
        with self.assertRaises(ch.MessageInvalid) as cm:
            self.append(body=RES + " " * 5 + "x" * wv.CHAT_MESSAGE_MAX_CHARS)
        self.assertNotIn(RES, str(cm.exception))

    def test_phien_dong_khong_nhan_tin_moi_nhung_goi_lai_tin_cu_van_tra_ve(self):
        mid = uuid.uuid4()
        self.append(message_id=mid)
        with self.db.connect("bo19_migrator") as c:
            c.execute("update chat_session set status = 'CLOSED', closed_at = now(), close_reason = 'IDLE_TIMEOUT' where id = %s", (self.sid,))
        with self.assertRaises(ch.ChatSessionClosed):
            self.append()
        self.assertFalse(self.append(message_id=mid).created)  # lượt gửi lại vẫn nhận lại kết quả cũ

    def test_dong_thoi_seq_khong_trung_khong_lo(self):
        n, out, errors = 10, [], []
        barrier = threading.Barrier(n)

        def go(i):
            barrier.wait()
            try:
                out.append(self.append(body=f"tin {i}").seq)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=go, args=(i,)) for i in range(n)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        self.assertEqual((errors, sorted(out)), ([], list(range(1, n + 1))))

    def test_khong_sinh_audit_event(self):
        self.append()
        ch.chat_message_append(self.pool, self.sys, chat_session_id=self.sid, message_id=uuid.uuid4(), author="AGENT", body="x", reply_template_id="ASK_SLOT")
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select count(*) from audit_event where trace_id in (%s, %s)", (self.ctx_.trace_id, self.sys.trace_id)).fetchone()[0], 0)

    def test_thieu_quyen_bi_tu_choi(self):
        _, no_perm = self.employee(roles=())
        with self.assertRaises(PermissionDenied):
            ch.chat_message_append(self.pool, no_perm, chat_session_id=self.sid, message_id=uuid.uuid4(), author="EMPLOYEE", body="x")


if __name__ == "__main__":
    unittest.main()
