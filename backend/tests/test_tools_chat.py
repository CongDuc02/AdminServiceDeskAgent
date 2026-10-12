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

import psycopg

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

    def test_mo_phien_khoa_hang_nhan_vien_de_khong_tao_hai_phien(self):  # xác định, không dựa vào may rủi của thời điểm
        eid, ctx = self.employee()
        done = {}

        def go():
            done["r"] = ch.chat_session_open(self.pool, ctx)

        with self.db.connect("bo19_migrator") as c:
            c.execute("select id from employee where id = %s for no key update", (eid,))  # giữ khoá hàng employee chưa commit; NO KEY UPDATE xung đột với FOR UPDATE của tool nhưng KHÔNG với khoá KEY SHARE của khoá ngoại, nên phân biệt được "có khoá" với "chỉ chờ khoá ngoại"
            t = threading.Thread(target=go)
            t.start()
            t.join(0.6)
            self.assertTrue(t.is_alive(), "chat_session_open phải chờ khoá hàng employee, không chạy chen")
            c.commit()
        t.join(10)
        self.assertEqual(done["r"].created, True)

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


class LienKetTraLoi(ToolBase):
    """Migration 0012 (B6b, Q6): mỗi tin nhân viên có tối đa một tin agent trả lời — DB giữ, không dựa vào tool, thời điểm của cờ huỷ hay của bộ giám sát."""

    def setUp(self):
        super().setUp()
        self.eid, self.ctx_ = self.employee()
        self.sid = ch.chat_session_open(self.pool, self.ctx_).chat_session_id
        self.q = self.ask(self.sid, self.ctx_)

    def ask(self, sid, ctx) -> uuid.UUID:
        mid = uuid.uuid4()
        ch.chat_message_append(self.pool, ctx, chat_session_id=sid, message_id=mid, author="EMPLOYEE", body="xin giấy xác nhận")
        return mid

    def reply(self, to, *, mid=None, sid=None):
        return ch.chat_message_append(self.pool, self.sys, chat_session_id=sid or self.sid, message_id=mid or uuid.uuid4(), author="AGENT", body="đã nhận", reply_template_id="ASK_SLOT",
                                      in_reply_to_message_id=to)

    def raw_insert(self, user, *, sid, author, reply_to, seq, mid=None, body="x", tpl=None):
        """INSERT thẳng bằng SQL — bỏ qua tool, để chứng minh chính DB từ chối."""
        with self.db.connect(user) as c:
            c.execute("insert into chat_message (id, chat_session_id, seq, author, body, reply_template_id, in_reply_to_message_id) values (%s, %s, %s, %s, %s, %s, %s)",
                      (mid or uuid.uuid4(), sid, seq, author, body, tpl if tpl is not None else ("ASK_SLOT" if author == "AGENT" else None), reply_to))

    def agent_rows(self, to):
        with self.db.connect("bo19_migrator") as c:
            return c.execute("select id, seq from chat_message where in_reply_to_message_id = %s and author = 'AGENT' order by seq", (to,)).fetchall()

    # --- tool ---------------------------------------------------------------------------------------------------------------------

    def test_tra_loi_tin_cua_chinh_phien_thi_ghi_lien_ket(self):
        r = self.reply(self.q)
        self.assertTrue(r.created)
        self.assertEqual([x[0] for x in self.agent_rows(self.q)], [r.message_id])

    def test_da_co_cau_tra_loi_thi_khong_ghi_them_va_tra_tin_cu(self):
        first = self.reply(self.q)
        second = self.reply(self.q)  # id khác — như bộ giám sát ghi sau thread của lượt
        self.assertEqual((second.created, second.message_id, second.seq), (False, first.message_id, first.seq))
        self.assertEqual(len(self.agent_rows(self.q)), 1)

    def test_goi_lai_cung_id_van_idempotent(self):
        mid = uuid.uuid4()
        first = self.reply(self.q, mid=mid)
        again = self.reply(self.q, mid=mid)
        self.assertEqual((again.created, again.message_id), (False, first.message_id))

    def test_tin_duoc_tra_loi_phai_la_tin_nhan_vien_cua_chinh_phien(self):
        _, other = self.employee()
        other_sid = ch.chat_session_open(self.pool, other).chat_session_id
        foreign = self.ask(other_sid, other)
        agent_msg = self.reply(self.q).message_id
        for label, target in (("tin của phiên khác", foreign), ("tin của agent", agent_msg), ("không tồn tại", uuid.uuid4())):
            with self.assertRaises(ch.MessageInvalid, msg=label):
                self.reply(target)
        self.assertEqual(self.agent_rows(foreign), [])

    def test_tin_nhan_vien_khong_duoc_mang_lien_ket(self):
        with self.assertRaises(ch.MessageInvalid):
            ch.chat_message_append(self.pool, self.ctx_, chat_session_id=self.sid, message_id=uuid.uuid4(), author="EMPLOYEE", body="x", in_reply_to_message_id=self.q)

    def test_tin_agent_khong_tra_loi_tin_nao_van_hop_le_va_khong_bi_gioi_han(self):  # ví dụ câu báo khi quay lại phiên mới (EC-CV-04)
        a = ch.chat_message_append(self.pool, self.sys, chat_session_id=self.sid, message_id=uuid.uuid4(), author="AGENT", body="a", reply_template_id="ASK_SLOT")
        b = ch.chat_message_append(self.pool, self.sys, chat_session_id=self.sid, message_id=uuid.uuid4(), author="AGENT", body="b", reply_template_id="ASK_SLOT")
        self.assertEqual((a.created, b.created), (True, True))

    def test_phien_dong_van_tra_lai_cau_tra_loi_da_co_nhung_khong_ghi_moi(self):
        first = self.reply(self.q)
        with self.db.connect("bo19_migrator") as c:
            c.execute("update chat_session set status = 'CLOSED', closed_at = now(), close_reason = 'IDLE_TIMEOUT' where id = %s", (self.sid,))
        self.assertEqual(self.reply(self.q).message_id, first.message_id)
        q2 = self.ask_closed()
        with self.assertRaises(ch.ChatSessionClosed):
            self.reply(q2)

    def ask_closed(self) -> uuid.UUID:  # tin nhân viên chèn thẳng trước khi phiên đóng thì không được nữa — dựng bằng chủ bảng
        mid = uuid.uuid4()
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into chat_message (id, chat_session_id, seq, author, body) values (%s, %s, 99, 'EMPLOYEE', 'x')", (mid, self.sid))
        return mid

    # --- đồng thời: bộ giám sát và thread của lượt cùng ghi lúc hạn chót ------------------------------------------------------------

    def test_hai_ben_ghi_dong_thoi_dung_mot_tin(self):
        n, out, errors = 6, [], []
        barrier = threading.Barrier(n)

        def go():
            barrier.wait()
            try:
                out.append(self.reply(self.q))  # mỗi bên một id riêng
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=go) for _ in range(n)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(sum(r.created for r in out), 1)
        self.assertEqual(len({r.message_id for r in out}), 1)  # ai cũng nhận về cùng một tin
        self.assertEqual(len(self.agent_rows(self.q)), 1)

    def test_luoi_an_toan_unique_khi_pre_check_bi_vong(self):
        """Mô phỏng đường ghi vòng khoá/kiểm của tool: pre-check không thấy câu trả lời → INSERT đụng UNIQUE của DB → tool bắt, trả tin đã có, không lỗi."""
        first = self.reply(self.q)
        real = ch._agent_reply
        calls = {"n": 0}

        def blind(conn, mid):
            calls["n"] += 1
            return None if calls["n"] == 1 else real(conn, mid)  # lần đầu (pre-check) mù; lần hai (sau unique_violation) thấy

        ch._agent_reply = blind
        try:
            second = self.reply(self.q)
        finally:
            ch._agent_reply = real
        self.assertEqual((second.created, second.message_id), (False, first.message_id))
        self.assertEqual(len(self.agent_rows(self.q)), 1)

    # --- DB tự từ chối, kể cả khi bỏ qua tool -------------------------------------------------------------------------------------

    def test_db_tu_choi_hai_tin_agent_cung_tra_loi_mot_tin(self):
        self.reply(self.q)
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.raw_insert("bo19_app", sid=self.sid, author="AGENT", reply_to=self.q, seq=50)

    def test_db_tu_choi_tin_agent_tro_toi_tin_cua_phien_khac_ke_ca_khi_bo_kiem_o_tool(self):
        _, other = self.employee()
        other_sid = ch.chat_session_open(self.pool, other).chat_session_id
        foreign = self.ask(other_sid, other)
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.raw_insert("bo19_app", sid=self.sid, author="AGENT", reply_to=foreign, seq=50)
        self.assertEqual(self.agent_rows(foreign), [])

    def test_db_tu_choi_tin_nhan_vien_mang_lien_ket_va_tu_tra_loi_chinh_minh(self):
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.raw_insert("bo19_app", sid=self.sid, author="EMPLOYEE", reply_to=self.q, seq=50)
        me = uuid.uuid4()
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.raw_insert("bo19_app", sid=self.sid, author="AGENT", reply_to=me, seq=51, mid=me)

    def test_db_cho_phep_nhieu_tin_agent_khong_tra_loi_tin_nao(self):
        self.raw_insert("bo19_app", sid=self.sid, author="AGENT", reply_to=None, seq=60)
        self.raw_insert("bo19_app", sid=self.sid, author="AGENT", reply_to=None, seq=61)

    def test_cot_lien_ket_khong_sua_duoc_sau_khi_ghi(self):
        r = self.reply(self.q)
        with self.db.connect("bo19_app") as c:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                c.execute("update chat_message set in_reply_to_message_id = null where id = %s", (r.message_id,))

    # --- đường xoá: luật xoá hội thoại xoá NỘI DUNG, không xoá dòng ----------------------------------------------------------------

    def test_xoa_noi_dung_khong_bi_fk_chan_va_lien_ket_con_nguyen(self):
        r = self.reply(self.q)
        with self.db.connect("bo19_app") as c:  # đúng câu `expire_request` chạy: bo19_app, UPDATE ba cột nội dung
            c.execute("update chat_message set body = null, retrieval_query = null, content_erased_at = now() where chat_session_id = %s", (self.sid,))
        self.assertEqual([x[0] for x in self.agent_rows(self.q)], [r.message_id])
        again = self.reply(self.q)  # gửi lại sau khi xoá nội dung: vẫn nhận tin cũ, không sinh tin thứ hai
        self.assertEqual((again.created, again.message_id), (False, r.message_id))
        with self.db.connect("bo19_migrator") as c:
            self.assertEqual(c.execute("select count(*), count(body) from chat_message where chat_session_id = %s and author = 'AGENT'", (self.sid,)).fetchone(), (1, 0))

    def test_runtime_khong_co_delete_tren_chat_message(self):
        with self.db.connect("bo19_app") as c:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                c.execute("delete from chat_message where chat_session_id = %s", (self.sid,))

    def test_xoa_cung_chi_qua_chu_bang_xoa_ca_phien_mot_cau_lenh_chay_con_xoa_le_tin_da_duoc_tra_loi_bi_chan(self):
        self.reply(self.q)
        with self.db.connect("bo19_migrator") as c:
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                c.execute("delete from chat_message where id = %s", (self.q,))  # còn tin agent trả lời nó: NO ACTION làm việc này ồn ào
        with self.db.connect("bo19_migrator") as c:
            c.execute("delete from chat_message where chat_session_id = %s", (self.sid,))  # cả phiên, một câu lệnh: chạy
            self.assertEqual(c.execute("select count(*) from chat_message where chat_session_id = %s", (self.sid,)).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
