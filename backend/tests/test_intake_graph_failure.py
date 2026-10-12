"""`intake_graph` khi có lỗi, quá hạn, bị huỷ, hoặc ghi cùng lúc — B6b. Nền ở `graph_support.py`.

Điều được chứng minh:
- **Mọi lượt đã nhận kết thúc bằng ĐÚNG MỘT tin của agent**, kể cả lượt lỗi (provider 5xx, hết budget, exception trong node, thread sai schema, thread đã đóng) — và khuôn lỗi đúng loại;
- **hạn chót lượt đi vào từng lời gọi gateway (PO, B6b):** P1 chậm thì P2 nhận hạn chót ngắn hơn đúng bằng phần còn lại và cả lượt dừng ≤ hạn chót của lượt, không phải WV-04 cho mỗi lời gọi;
- **cờ huỷ hợp tác:** sau khi cờ bật, thread không gọi thêm tool hay gateway nào — không ghi gì;
- **ghi cùng lúc** (bộ giám sát lượt ghi khuôn lỗi lúc hạn chót, thread ghi câu trả lời): DB giữ đúng một tin;
- **biên node:** exception mang giá trị `RES` không vào bảng checkpoint, `graph_thread` hay log; `RES` trong tin nhắn và trong output của P2 cũng không vào checkpoint.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_intake_graph_failure -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import io
import logging
import threading
import time
import unittest
from unittest import mock

from bo19.config import working_values as wv
from bo19.observability.log import configure_logging
from bo19.tool_layer.checks import config as cfg
from tests.graph_support import GraphBase, p1, slot

RES = "NOI_DUNG_RES_KHONG_DUOC_LOT_RA_9f3a"
MSG = "cho mình xin giấy xác nhận công tác, gửi Ngân hàng ABC"


class Base(GraphBase):
    def setUp(self):
        super().setUp()
        self.out = io.StringIO()
        h = configure_logging(self.out, logging.DEBUG)
        self.addCleanup(logging.getLogger().removeHandler, h)

    def assertOneAgentReply(self, template: str):
        rows = self.agent_messages()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual((rows[0][1], rows[0][2]), (template, self.last_mid))


class LoiThanhKhuonLoi(Base):
    def test_provider_5xx_la_error_busy_va_dung_mot_tin(self):
        out = self.turn(MSG)  # không có kịch bản → fake trả 500
        self.assertEqual((out.reply_template_id, out.error_code is not None), ("ERROR_BUSY", True))
        self.assertOneAgentReply("ERROR_BUSY")
        self.assertEqual(self.requests_of_session(), [])  # lỗi ở P1: chưa có request

    def test_het_budget_la_budget_limit(self):
        self.llm.will("classify_intent", p1())
        self.addCleanup(setattr, wv, "TOKEN_CEILING_CHAT_SESSION", wv.TOKEN_CEILING_CHAT_SESSION)
        wv.TOKEN_CEILING_CHAT_SESSION = 100
        self.turn("lượt đầu dùng hết")  # một lời gọi P1 ghi 150 token vào sổ → chạm trần
        self.llm.requests.clear()
        out = self.turn("lượt hai")
        self.assertEqual((out.reply_template_id, out.error_code), ("BUDGET_LIMIT", "BUDGET_EXCEEDED"))
        self.assertEqual([m[1] for m in self.agent_messages()][-1], "BUDGET_LIMIT")
        self.assertEqual(self.llm.requests, [])  # bị chặn trước provider (ADR-019)

    def test_thread_sai_schema_khong_chay_graph(self):
        self.llm.will("classify_intent", p1("OUT_OF_SCOPE"))
        self.turn("lượt đầu")
        with self.db.connect("bo19_migrator") as c:
            c.execute("update graph_thread set state_schema_version = 2 where thread_id = %s", (f"intake:{self.sid}",))
        self.llm.requests.clear()
        out = self.turn("lượt hai")
        self.assertEqual((out.reply_template_id, out.error_code), ("ERROR_BUSY", "THREAD_SCHEMA_MISMATCH"))
        self.assertEqual(self.llm.requests, [])  # không resume bằng state sai hình

    def test_thread_da_ket_thuc_khong_chay_graph(self):
        self.llm.will("classify_intent", p1("OUT_OF_SCOPE"))
        self.turn("lượt đầu")
        with self.db.connect("bo19_migrator") as c:
            c.execute("update graph_thread set status = 'ENDED', ended_at = now() where thread_id = %s", (f"intake:{self.sid}",))
        self.llm.requests.clear()
        out = self.turn("lượt hai")
        self.assertEqual((out.reply_template_id, out.error_code), ("ERROR_BUSY", "THREAD_NOT_ACTIVE"))
        self.assertEqual(self.llm.requests, [])

    def test_nhan_vien_bi_tat_giua_chung_la_khuon_loi(self):
        self.llm.will("classify_intent", p1())
        mid = self.send(MSG)
        with self.db.connect("bo19_migrator") as c:
            c.execute("update employee set is_active = false where id = %s", (self.eid,))
        out = self.turn(MSG, message_id=mid)
        self.assertEqual(out.reply_template_id, "ERROR_BUSY")
        self.assertOneAgentReply("ERROR_BUSY")
        self.assertEqual(self.llm.requests, [])


class BienNode(Base):
    def test_exception_mang_res_khong_vao_checkpoint_graph_thread_hay_log(self):
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": []})
        with mock.patch.object(cfg, "slot_specs", side_effect=RuntimeError(f"khoá {RES} không tồn tại")):
            out = self.turn(MSG)
        self.assertEqual((out.reply_template_id, out.error_code), ("ERROR_BUSY", "NODE_UNEXPECTED"))
        dump = self.checkpoint_dump()
        self.assertNotIn(RES, dump)
        self.assertIn("NODE_UNEXPECTED", dump)  # chỉ mã rời node và nằm trong bảng
        self.assertNotIn(RES, self.out.getvalue())
        self.assertOneAgentReply("ERROR_BUSY")

    def test_ma_cua_tool_di_qua_bien_node_nguyen_ve(self):
        self.llm.will("classify_intent", p1())
        from bo19.tool_layer.tools._common import ToolError

        class Boom(ToolError):
            code = "MA_CUA_TOOL"

        with mock.patch.object(cfg, "slot_specs", side_effect=Boom(RES)):
            out = self.turn(MSG)
        self.assertEqual(out.error_code, "MA_CUA_TOOL")
        self.assertNotIn(RES, self.checkpoint_dump())

    def test_res_trong_tin_nhan_va_trong_output_p2_khong_vao_checkpoint(self):
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": [slot("purpose", f"bổ sung hồ sơ {RES}", f"bổ sung hồ sơ {RES}")]})
        out = self.turn(f"xin giấy xác nhận, mục đích bổ sung hồ sơ {RES}".replace(RES, RES))
        self.assertEqual(out.error_code, None)
        (req,) = self.requests_of_session()
        self.assertIn(RES, self.slots_of(req["id"])["purpose"][1])  # giá trị có trong request_slot (nơi duy nhất, có `slot_sensitivity`)
        self.assertEqual(self.agent_messages()[0][1] in ("ASK_SLOT", "CONFIRM_PROPOSALS"), True)
        self.assertNotIn(RES, self.checkpoint_dump())  # không vào checkpoint, không vào graph_thread
        self.assertNotIn(RES, str(self.graph_state()))
        self.assertNotIn(RES, self.out.getvalue())  # không vào log kỹ thuật

    def test_metadata_checkpoint_chi_co_trace_id_khong_doi_tuong_cua_luot(self):
        self.llm.will("classify_intent", p1("OUT_OF_SCOPE"))
        self.turn("xin chào")
        with self.db.connect("bo19_migrator") as c:
            metas = [m[0] for m in c.execute("select metadata from checkpoints where thread_id = %s", (f"intake:{self.sid}",)).fetchall()]
        self.assertTrue(metas)
        for meta in metas:
            self.assertLessEqual(set(meta), {"step", "source", "parents", "trace_id"})
            self.assertNotIn("turn", meta)


class HanChotLuot(Base):
    def test_p1_cham_thi_p2_nhan_han_chot_ngan_hon_va_ca_luot_dung_trong_han(self):
        """P1 mất 1,2 s trong lượt 2,5 s; P2 sẽ trả sau 5 s. Không truyền hạn chót: P2 chạy tới WV-04 (8 s) → lượt 6,2 s. Có truyền: P2 chỉ còn ~1,3 s."""
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": []})
        self.llm.delays.update(classify_intent=1.2, extract_slots=5.0)
        started = time.monotonic()
        out = self.turn(MSG, budget_s=2.5)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 3.6, elapsed)  # ≤ hạn chót lượt + độ trễ ghi tin lỗi — rất xa 6,2 s
        self.assertEqual(out.reply_template_id, "ERROR_BUSY")
        self.assertOneAgentReply("ERROR_BUSY")
        rows = {r["call_name"]: r for r in self.usage_rows()}
        self.assertLess(rows["extract_slots"]["duration_ms"], 1700)  # hạn chót tổng của P2 là phần còn lại của lượt, không phải WV-04
        self.assertGreater(rows["extract_slots"]["duration_ms"], 800)
        self.assertEqual(len(self.llm.calls("extract_slots")), 1)  # hết hạn chót thì không thử lại lần hai

    def test_p1_vuot_qua_han_chot_cua_luot(self):
        self.llm.will("classify_intent", p1())
        self.llm.delays.update(classify_intent=4.0)
        started = time.monotonic()
        out = self.turn(MSG, budget_s=1.0)
        self.assertLess(time.monotonic() - started, 2.5)
        self.assertEqual(out.reply_template_id, "ERROR_BUSY")
        self.assertEqual(self.llm.calls("extract_slots"), [])
        self.assertOneAgentReply("ERROR_BUSY")

    def test_het_han_chot_truoc_khi_goi_gi_thi_khong_goi_provider(self):
        self.llm.will("classify_intent", p1())
        out = self.turn(MSG, budget_s=-1.0)
        self.assertEqual((out.reply_template_id, out.error_code), ("ERROR_BUSY", "TURN_DEADLINE"))
        self.assertEqual(self.llm.requests, [])
        self.assertEqual(self.requests_of_session(), [])

    def usage_rows(self) -> list[dict]:
        return self.db.usage_rows_ext(chat_session_id=self.sid)


class CoHuy(Base):
    def test_co_huy_giua_p1_thi_khong_goi_them_tool_hay_gateway_nao(self):
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": [slot("recipient_org", "Ngân hàng ABC")]})
        self.llm.delays.update(classify_intent=1.0)
        cancel = threading.Event()
        timer = threading.Timer(0.3, cancel.set)
        timer.start()
        self.addCleanup(timer.cancel)
        out = self.turn(MSG, cancel=cancel)
        self.assertEqual((out.reply_template_id, out.error_code), ("ERROR_BUSY", "TURN_CANCELLED"))
        self.assertEqual(self.requests_of_session(), [])  # P1 trả về nhưng không có `request_open`, không có ghi nào
        self.assertEqual(self.llm.calls("extract_slots"), [])
        self.assertOneAgentReply("ERROR_BUSY")

    def test_co_da_bat_truoc_khi_vao_thi_khong_goi_gi(self):
        cancel = threading.Event()
        cancel.set()
        out = self.turn(MSG, cancel=cancel)
        self.assertEqual(out.error_code, "TURN_CANCELLED")
        self.assertEqual(self.llm.requests, [])


class GhiCungLuc(Base):
    def test_bo_giam_sat_ghi_khuon_loi_luc_thread_dang_chay_thi_chi_mot_tin_vao(self):
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": []})
        self.llm.delays.update(extract_slots=1.0)
        mid = self.send(MSG)
        result: dict = {}

        def run_thread():
            result["out"] = self.turn(MSG, message_id=mid)

        t = threading.Thread(target=run_thread)
        t.start()
        time.sleep(0.5)  # thread đang chờ P2
        supervisor = self.runner.write_error_reply(chat_session_id=self.sid, message_id=mid, trace_id="00000000-0000-4000-8000-000000000000", error_code="TURN_DEADLINE")
        t.join(30)
        self.assertIsNotNone(supervisor)
        rows = self.agent_messages()
        self.assertEqual(len(rows), 1, rows)  # đúng một tin: ai tới trước thắng
        self.assertEqual(rows[0][1], "ERROR_BUSY")  # bộ giám sát tới trước
        self.assertEqual(result["out"].reply_message_id, supervisor)  # thread cũng nhận về đúng tin đó, không tạo tin thứ hai

    def test_viec_ghi_khuon_loi_lap_lai_la_idempotent(self):
        mid = self.send(MSG)
        first = self.runner.write_error_reply(chat_session_id=self.sid, message_id=mid, trace_id="00000000-0000-4000-8000-000000000000", error_code="X")
        again = self.runner.write_error_reply(chat_session_id=self.sid, message_id=mid, trace_id="00000000-0000-4000-8000-000000000000", error_code="BUDGET_EXCEEDED")
        self.assertEqual(first, again)
        self.assertEqual([m[1] for m in self.agent_messages()], ["ERROR_BUSY"])  # tin đầu thắng

    def test_phien_khong_ton_tai_khong_nem(self):
        import uuid
        self.assertIsNone(self.runner.write_error_reply(chat_session_id=uuid.uuid4(), message_id=uuid.uuid4(), trace_id="00000000-0000-4000-8000-000000000000", error_code="X"))


if __name__ == "__main__":
    unittest.main()
