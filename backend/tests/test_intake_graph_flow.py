"""`intake_graph` qua nhiều lượt và qua các nhánh — B6b. Nền ở `graph_support.py` (PostgreSQL thật, checkpointer thật, provider giả theo tên lời gọi).

Điều được chứng minh: luồng đầy đủ tới `offer_submit` (chỉ sau khi nhân viên xác nhận đề xuất HR_PROFILE); state sống qua lượt và qua một `IntakeRunner` mới (resume sau khi khởi động lại);
hỏi làm rõ có trần WV-11 và bộ đếm đặt lại đúng luật (`CANCELLED`/`EXPIRED` không đặt lại); `resume_context` chạy đúng một lần cho mỗi lần đổi trạng thái; nhánh ngoài phạm vi không mở `request`
và không gọi P2; `MULTIPLE` và `TYPE_CHANGED` rẽ sang hỏi lại ở Sprint 1; slot bị loại ra khuôn thử lại kèm mã con; tên slot do LLM bịa không vào state.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_intake_graph_flow -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest
import uuid

from bo19.orchestrator.intake_graph import reply_templates as rt
from bo19.orchestrator.runner import IntakeRunner
from bo19.tool_layer.checks import config as cfg
from bo19.tool_layer.employee_ops.request_slot_confirm import Confirmation, request_slot_confirm
from tests.graph_support import KEY, GraphBase, p1, slot  # noqa: F401

MSG = "cho mình xin giấy xác nhận công tác, gửi Ngân hàng ABC"
PURPOSE_MSG = "mục đích là bổ sung hồ sơ vay vốn tại ngân hàng"


class LuongDayDu(GraphBase):
    def transitions(self, request_id) -> list[str]:
        with self.db.connect("bo19_migrator") as c:
            rows = c.execute("select payload->>'to' from audit_event where request_id = %s and action = 'request.transition' order by occurred_at, id", (request_id,)).fetchall()
        return [r[0] for r in rows]

    def test_tu_tin_nhan_dau_toi_offer_submit_chi_sau_khi_xac_nhan_de_xuat(self):
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": [slot("recipient_org", "Ngân hàng ABC")]})
        self.assertEqual(self.turn(MSG).reply_template_id, "ASK_SLOT")  # thiếu purpose
        (req,) = self.requests_of_session()

        self.llm.set("extract_slots", {"slots": [slot("purpose", "bổ sung hồ sơ vay vốn tại ngân hàng")]})
        out = self.turn(PURPOSE_MSG)
        self.assertEqual(out.reply_template_id, "CONFIRM_PROPOSALS")  # đủ slot nhân viên nói, còn đề xuất HR chờ xác nhận — F1 chưa đủ
        self.assertEqual(out.pending_question["kind"], "CONFIRM_PROPOSALS")
        self.assertEqual({req["id"]}, {r["id"] for r in self.requests_of_session()})  # vẫn một request, không mở thêm
        self.assertEqual(self.requests_of_session()[0]["status"], "NEEDS_INFO")
        self.assertEqual(self.slots_of(req["id"])["purpose"][0], "PROVIDED")
        self.assertEqual(self.transitions(req["id"]), ["NEEDS_INFO", "DRAFT", "NEEDS_INFO"])  # nhân viên bổ sung → về DRAFT qua `request_transition`, rồi còn đề xuất chờ xác nhận → NEEDS_INFO

        with self.db.connect("bo19_migrator") as c:  # nhân viên xác nhận từng đề xuất trên màn hình yêu cầu
            versions = dict(c.execute("select slot_name, row_version from request_slot where request_id = %s and value_status = 'PROPOSED'", (req["id"],)).fetchall())
        confirmed = request_slot_confirm(self.pool, self.ctx_, request_id=req["id"], items=[Confirmation(n, v) for n, v in versions.items()])
        self.assertTrue(confirmed.confirmed)
        self.assertEqual(self.requests_of_session()[0]["status"], "DRAFT")  # đủ điều kiện → NEEDS_INFO về DRAFT (tool xác nhận)

        self.llm.set("extract_slots", {"slots": []})
        out = self.turn("xong chưa bạn")
        self.assertEqual((out.reply_template_id, out.pending_question["kind"]), ("OFFER_SUBMIT", "OFFER_SUBMIT"))
        self.assertEqual(self.requests_of_session()[0]["status"], "DRAFT")  # graph không tự gửi: submit là thao tác của nhân viên (INV)
        self.assertEqual([m[1] for m in self.agent_messages()], ["ASK_SLOT", "CONFIRM_PROPOSALS", "OFFER_SUBMIT"])  # đúng một tin agent mỗi lượt

    def test_pending_question_cua_luot_truoc_la_input_cua_luot_sau_chi_ma(self):
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": []})
        self.turn(MSG)
        self.llm.requests.clear()
        self.turn("cho Ngân hàng ABC")
        user = self.llm.calls("classify_intent")[0]["messages"][1]["content"]
        self.assertIn('"pending_question":{"template_id":"ASK_SLOT","candidate_types":[]}', user)
        self.assertNotIn("Để làm", user)  # mã khuôn, không phải văn bản câu hỏi

    def test_cung_mot_tin_nhan_chay_hai_lan_khong_mo_them_request_va_van_mot_tin_agent(self):
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": [slot("recipient_org", "Ngân hàng ABC")]})
        mid = self.send(MSG)
        first = self.turn(MSG, message_id=mid)
        second = self.turn(MSG, message_id=mid)
        self.assertEqual(first.reply_message_id, second.reply_message_id)
        self.assertEqual(len(self.requests_of_session()), 1)
        self.assertEqual(len(self.agent_messages()), 1)


class SongQuaLuotVaKhoiDongLai(GraphBase):
    def test_ma_loai_cua_luot_truoc_khong_ro_ri_sang_luot_sau(self):
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": [slot("purpose", "xin visa")]})
        self.assertEqual(self.turn("xin giấy xác nhận, mục đích xin visa").rejection_codes, ("RULE_FAILED:RULE_MIN_TOKENS",))
        self.llm.set("extract_slots", {"slots": []})
        out = self.turn("à thôi để mình nghĩ lại")
        self.assertEqual((out.rejected_slots, out.rejection_codes), ((), ()))  # đặt lại ở đầu lượt
        self.assertEqual(self.graph_state()["rejection_codes"], [])

    def test_state_song_qua_mot_runner_moi(self):
        self.llm.will("classify_intent", p1("NEED_CLARIFICATION", confidence="low"))
        self.turn("ừm cái đó")
        self.assertEqual(self.graph_state()["clarification_count"], 1)
        fresh = IntakeRunner.open(pool=self.pool, gateway=self.gateway, dsn=self.db.dsn("bo19_app"))  # tiến trình khởi động lại: checkpointer và graph mới
        self.addCleanup(fresh.close)
        out = self.turn("vẫn cái đó", runner=fresh)
        self.assertEqual(out.reply_template_id, "CLARIFY_TYPE_NO_CANDIDATE")
        self.assertEqual(fresh._graph.values(f"intake:{self.sid}")["clarification_count"], 2)  # noqa: SLF001
        self.assertEqual(self.graph_state()["pending_question"]["template_id"], "CLARIFY_TYPE_NO_CANDIDATE")

    def test_graph_thread_duoc_ghi(self):
        self.llm.will("classify_intent", p1("OUT_OF_SCOPE"))
        self.turn("hôm nay trời đẹp quá")
        with self.db.connect("bo19_migrator") as c:
            row = c.execute("select graph_name, status, state_schema_version from graph_thread where thread_id = %s", (f"intake:{self.sid}",)).fetchone()
        self.assertEqual(row, ("intake_graph", "ACTIVE", 1))


class HoiLamRo(GraphBase):
    def test_co_tran_wv11_hai_lan_roi_khuon_lien_he(self):
        self.llm.will("classify_intent", p1("NEED_CLARIFICATION", confidence="low"))
        templates = [self.turn(t).reply_template_id for t in ("ừm", "cái đó", "ý mình là", "thôi")]
        self.assertEqual(templates, ["CLARIFY_TYPE_NO_CANDIDATE", "CLARIFY_TYPE_NO_CANDIDATE", "CLARIFY_LIMIT_REACHED", "CLARIFY_LIMIT_REACHED"])
        self.assertEqual(self.graph_state()["clarification_count"], 2)  # đứng ở trần: khuôn liên hệ không cấp thêm lượt
        self.assertEqual(self.requests_of_session(), [])  # hỏi làm rõ không để lại request rác
        self.assertEqual(self.llm.calls("extract_slots"), [])

    def test_khuon_lien_he_khong_hua_thong_tin_lien_he_khong_co(self):
        self.llm.will("classify_intent", p1("NEED_CLARIFICATION", confidence="low"))
        for t in ("a", "b", "c"):
            self.turn(t)
        body = self.agent_messages()[-1][3]
        self.assertIn("Phòng Hành chính", body)
        self.assertNotRegex(body, r"\\d{5,}|@")  # không số điện thoại, không thư điện tử bịa

    def test_loai_duoc_hoi_la_loai_duoc_ho_tro_khong_phai_loai_chua_ho_tro(self):
        self.llm.will("classify_intent", p1("WORK_CONFIRMATION", confidence="low"))
        out = self.turn("giấy gì đó cho ngân hàng")
        self.assertEqual(out.reply_template_id, "CLARIFY_TYPE")
        self.assertEqual(out.pending_question["candidate_types"], ["WORK_CONFIRMATION"])
        self.assertIn(cfg.type_names(self.pool)["WORK_CONFIRMATION"], self.agent_messages()[0][3])

    def test_multiple_o_sprint_1_hoi_lai_khong_mo_request(self):  # G2: MULTIPLE thuộc Sprint 2
        self.llm.will("classify_intent", p1("WORK_CONFIRMATION", "ROOM_BOOKING"))
        out = self.turn("xin giấy xác nhận công tác, tiện đặt phòng họp luôn")
        self.assertEqual((out.intent_result, out.reply_template_id), ("MULTIPLE", "CLARIFY_TYPE"))
        self.assertEqual(self.requests_of_session(), [])
        self.assertEqual(self.llm.calls("extract_slots"), [])
        self.assertEqual(self.graph_state()["pending_intents"], [])  # Sprint 1 chưa lưu nhu cầu thứ hai

    def test_json_p1_hong_hai_lan_la_unparseable_va_hoi_lai(self):
        self.llm.will("classify_intent", "không phải json", "vẫn không phải json")
        out = self.turn("xin giấy")
        self.assertEqual((out.intent_result, out.reply_template_id), ("UNPARSEABLE", "CLARIFY_TYPE_NO_CANDIDATE"))
        self.assertEqual(len(self.llm.calls("classify_intent")), 2)  # sửa parse đúng một lần
        self.assertEqual(self.graph_state()["last_error_code"], "PARSE_FAILED")
        self.assertEqual(self.requests_of_session(), [])


class DatLaiBoDem(GraphBase):
    def open_and_ask(self):
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": []})
        self.turn(MSG)
        (req,) = self.requests_of_session()
        self.llm.script["classify_intent"] = [p1("NEED_CLARIFICATION", confidence="low")]
        self.turn("ừm cái đó")  # một lần hỏi làm rõ khi request đang ở giai đoạn thu thập
        self.assertEqual(self.graph_state()["clarification_count"], 1)
        return req["id"]

    def set_status(self, rid, status):
        terminal = status in ("CANCELLED", "EXPIRED", "FULFILLED", "REJECTED")
        with self.db.connect("bo19_migrator") as c:
            c.execute("update request set status = %s, closed_at = " + ("now()" if terminal else "null") + ", row_version = row_version + 1 where id = %s", (status, rid))

    def test_roi_giai_doan_thu_thap_thi_dat_lai_dung_mot_lan_va_resume_context_dung_mot_lan(self):
        rid = self.open_and_ask()
        self.set_status(rid, "SUBMITTED")
        self.llm.script["classify_intent"] = [p1("NEED_CLARIFICATION", confidence="low")]
        out = self.turn("tình hình sao rồi")
        self.assertEqual(out.reply_template_id, "RESUME_STATUS")  # vừa đổi sang SUBMITTED: báo trạng thái, không phân loại
        self.assertEqual(self.graph_state()["clarification_count"], 0)
        self.assertIn(cfg.type_names(self.pool)["WORK_CONFIRMATION"], self.agent_messages()[-1][3])
        calls_before = len(self.llm.calls("classify_intent"))
        out = self.turn("còn gì nữa không")
        self.assertEqual(out.reply_template_id, "CLARIFY_TYPE_NO_CANDIDATE")  # lần sau đi classify: resume chỉ chạy một lần cho mỗi lần đổi
        self.assertEqual(len(self.llm.calls("classify_intent")), calls_before + 1)
        self.assertEqual(self.graph_state()["clarification_count"], 1)  # đếm lại từ 0 sau lần đặt lại
        out = self.turn("vậy thôi")
        self.assertEqual(self.graph_state()["clarification_count"], 2)  # đã không đặt lại lần hai (last_seen đã là SUBMITTED)

    def test_cancelled_va_expired_khong_bao_gio_dat_lai(self):
        for status in ("CANCELLED", "EXPIRED"):
            with self.subTest(status):
                self.setUp()
                rid = self.open_and_ask()
                self.set_status(rid, status)
                out = self.turn("tình hình sao rồi")
                self.assertEqual(out.reply_template_id, "RESUME_STATUS")
                self.assertEqual(self.graph_state()["clarification_count"], 1, status)  # không cấp lại ngân sách làm rõ

    def test_request_da_gui_roi_nhu_cau_moi_mo_request_moi_khong_kem_replaces(self):
        rid = self.open_and_ask()
        self.set_status(rid, "SUBMITTED")
        self.llm.script["classify_intent"] = [p1()]
        self.llm.script["extract_slots"] = [{"slots": []}]
        self.turn("tình hình sao rồi")  # RESUME_STATUS, tiêu mất lần "vừa đổi"
        out = self.turn("cho mình xin thêm một giấy xác nhận công tác nữa")
        self.assertEqual(out.reply_template_id, "ASK_SLOT")
        rows = self.requests_of_session()
        self.assertEqual([r["status"] for r in rows], ["SUBMITTED", "NEEDS_INFO"])
        with self.db.connect("bo19_migrator") as c:
            self.assertIsNone(c.execute("select replaces_request_id from request where id = %s", (rows[1]["id"],)).fetchone()[0])  # nhu cầu mới, không phải đổi loại


class NgoaiPhamVi(GraphBase):
    def test_ngoai_pham_vi_chung_khong_mo_request_khong_goi_p2_va_procedure_store_not_ready(self):
        self.llm.will("classify_intent", p1("OUT_OF_SCOPE"))
        out = self.turn("hôm nay ăn gì")
        self.assertEqual((out.intent_result, out.reply_template_id), ("OUT_OF_SCOPE", "OUT_OF_SCOPE_GENERIC"))
        self.assertEqual(self.requests_of_session(), [])
        self.assertEqual(self.llm.calls("extract_slots"), [])
        self.assertEqual(self.graph_state()["procedure_store"], "NOT_READY")  # Sprint 1: hằng, không gọi tool (PO Q4)
        self.assertIn(cfg.type_names(self.pool, supported_only=True)["WORK_CONFIRMATION"], self.agent_messages()[0][3])

    def test_loai_da_biet_chua_ho_tro_khuon_neu_ten_loai_va_moi_loai_dang_ho_tro(self):  # EC-WC-03
        self.llm.will("classify_intent", p1("INCOME_CONFIRMATION"))
        out = self.turn("xin giấy xác nhận thu nhập")
        self.assertEqual(out.reply_template_id, "OUT_OF_SCOPE_KNOWN")
        body = self.agent_messages()[0][3]
        names = cfg.type_names(self.pool)
        self.assertIn(names["INCOME_CONFIRMATION"], body)
        self.assertIn(names["WORK_CONFIRMATION"], body)  # liệt kê loại đang hỗ trợ, không chọn "gần nhất"
        self.assertEqual(self.requests_of_session(), [])


class SlotBiLoai(GraphBase):
    def test_rule_min_tokens_voi_purpose_ra_khuon_co_vi_du_va_ma_con(self):  # V2: "xin visa" = 2 tiếng bị hỏi lại
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": [slot("recipient_org", "Ngân hàng ABC"), slot("purpose", "xin visa")]})
        out = self.turn("xin giấy xác nhận, gửi Ngân hàng ABC, mục đích xin visa")
        self.assertEqual(out.reply_template_id, "ASK_PURPOSE_RETRY")
        self.assertEqual((out.rejected_slots, out.rejection_codes), (("purpose",), ("RULE_FAILED:RULE_MIN_TOKENS",)))
        self.assertIn("ví dụ", self.agent_messages()[0][3])
        self.assertEqual(self.graph_state()["rejection_codes"], ["RULE_FAILED:RULE_MIN_TOKENS"])

    def test_hai_ma_con_evidence_mismatch_tach_rieng(self):
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": [
            slot("recipient_org", "Ngân hàng XYZ", "Ngân hàng XYZ"),  # quote không có trong tin nhắn
            slot("purpose", "bổ sung hồ sơ vay vốn tại ngân hàng khác", "bổ sung hồ sơ vay vốn")]})  # value dài hơn quote
        out = self.turn("xin giấy xác nhận, gửi Ngân hàng ABC, mục đích bổ sung hồ sơ vay vốn")
        self.assertEqual(out.reply_template_id, "ASK_SLOT_RETRY")
        self.assertEqual(dict(zip(out.rejected_slots, out.rejection_codes)),
                         {"recipient_org": "EVIDENCE_MISMATCH:QUOTE_NOT_IN_MESSAGE", "purpose": "EVIDENCE_MISMATCH:VALUE_NOT_IN_QUOTE"})
        (req,) = self.requests_of_session()
        self.assertNotIn("recipient_org", {n for n, (st, _) in self.slots_of(req["id"]).items() if st == "PROVIDED"})  # suy diễn không vào DB

    def test_value_viet_hoa_lai_va_gop_khoang_trang_van_duoc_ghi(self):  # PO, B6b: so khớp nới của value
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": [slot("recipient_org", "Ngân hàng Vietcombank", "ngân hàng  vietcombank")]})
        out = self.turn("xin giấy xác nhận, gửi ngân hàng  vietcombank")
        self.assertEqual(out.rejected_slots, ())
        (req,) = self.requests_of_session()
        self.assertEqual(self.slots_of(req["id"])["recipient_org"], ("PROVIDED", "Ngân hàng Vietcombank"))

    def test_ten_slot_do_llm_bia_khong_vao_state(self):
        fake = "ten_slot_bia_RES_9f3a"
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": [slot(fake, "x")]})
        out = self.turn("xin giấy xác nhận")
        self.assertEqual(out.rejected_slots, ("UNKNOWN_SLOT",))
        self.assertEqual(out.rejection_codes, ("SLOT_NOT_ALLOWED",))
        self.assertNotIn(fake, self.checkpoint_dump())

    def test_p2_json_hong_coi_nhu_khong_hieu_va_hoi_lai_slot(self):
        self.llm.will("classify_intent", p1()).will("extract_slots", "không phải json", "vẫn không")
        out = self.turn("xin giấy xác nhận")
        self.assertEqual(out.reply_template_id, "ASK_SLOT")
        self.assertEqual(self.graph_state()["last_error_code"], "PARSE_FAILED")
        self.assertEqual(len(self.agent_messages()), 1)


if __name__ == "__main__":
    unittest.main()
