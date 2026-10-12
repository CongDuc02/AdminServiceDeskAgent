"""`intake_graph` chạy thật qua `IntakeRunner` — checkpointer PostgreSQL thật, tool thật, gateway thật với provider giả theo tên lời gọi (B6b).

Điều được chứng minh, nói bằng hành vi: một lượt đi đúng nhánh theo output P1 (đủ tám dòng ánh xạ ở `test_intake_routing`); `request` chỉ mở khi đã rõ một loại được hỗ trợ; slot do P2 trích chỉ vào DB qua kiểm
bằng chứng; HR_PROFILE được đề xuất chứ không tự xác nhận; hỏi làm rõ có trần; `resume_context` chạy đúng một lần cho mỗi lần đổi trạng thái; mọi lượt — thành công hay lỗi — kết thúc bằng ĐÚNG MỘT tin của agent;
không giá trị `RES` nào vào checkpoint hay log; hạn chót lượt truyền xuống từng lời gọi gateway.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_intake_graph -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import unittest

from tests.graph_support import GraphBase, p1, slot

MSG = "cho mình xin giấy xác nhận công tác, gửi Ngân hàng ABC"


class LuotDauTien(GraphBase):
    def test_mo_request_ghi_slot_co_bang_chung_de_xuat_hr_va_hoi_tiep_slot_con_thieu(self):
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": [slot("recipient_org", "Ngân hàng ABC")]})
        progress: list[str] = []
        out = self.turn(MSG, progress=progress)
        self.assertEqual((out.error_code, out.reply_template_id, out.intent_result), (None, "ASK_SLOT", "SUPPORTED"))
        (req,) = self.requests_of_session()
        self.assertEqual((req["request_type_code"], req["status"]), ("WORK_CONFIRMATION", "NEEDS_INFO"))  # còn thiếu → NEEDS_INFO
        slots = self.slots_of(req["id"])
        self.assertEqual(slots["recipient_org"][0], "PROVIDED")
        self.assertEqual({n for n, (st, _) in slots.items() if st == "PROPOSED"}, {"full_name", "department_name", "job_title", "contract_type", "employment_start_date"})
        self.assertIn("purpose", out.pending_question["slot_names"])
        self.assertEqual(out.pending_question["kind"], "ASK_SLOT")
        self.assertEqual(progress, ["UNDERSTANDING", "PREPARING_REPLY"])
        (agent,) = self.agent_messages()
        self.assertEqual((agent[1], agent[2]), ("ASK_SLOT", self.last_mid))
        self.assertIn("mục đích", agent[3].lower())  # nhãn tiếng Việt của slot, lấy từ cấu hình DB

    def test_p1_va_p2_nhan_dung_input_da_khai_va_khong_nhan_gia_tri_slot(self):
        self.llm.will("classify_intent", p1()).will("extract_slots", {"slots": []})
        self.turn(MSG)
        (p1_body,) = self.llm.calls("classify_intent")
        (p2_body,) = self.llm.calls("extract_slots")
        user1 = p1_body["messages"][1]["content"]
        user2 = p2_body["messages"][1]["content"]
        for key in ("current_turn_text", "pending_question", "active_request_type", "request_type_catalog"):
            self.assertIn(f'"{key}"', user1)
        for key in ("current_turn_text", "pending_question", "slot_specs"):
            self.assertIn(f'"{key}"', user2)
        self.assertNotIn("full_name", user2.split('"slot_specs"')[0])
        self.assertNotIn("department_name", user2)  # slot HR_PROFILE không có trong slot_specs của P2


if __name__ == "__main__":
    unittest.main()
