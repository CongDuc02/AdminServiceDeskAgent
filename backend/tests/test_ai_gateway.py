"""`ai_gateway.call` trên PostgreSQL thật đã migrate, provider là `httpx.MockTransport` — B4.

AC-1.9 (phần `ai_gateway`): khoá thừa hay thiếu bị `ALLOWLIST_REJECTED`, không một request nào tới provider; tập khoá gửi đi của `draft_free_content` đúng bằng `purpose`,
`variable_guidance`, `request_type`. Cộng: thứ tự allowlist → budget → provider → ép JSON → ghi sổ; sổ `llm_usage`; hạn chót tổng; log không lộ RES hay khoá API.

Cần BO19_TEST_PG_SUPERUSER_DSN. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_ai_gateway -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import asyncio
import io
import json
import logging
import time
import traceback
import unittest
import uuid
from typing import Any
from unittest import mock

import httpx

from bo19.ai_gateway.allowlist import AllowlistRejected
from bo19.ai_gateway.budget import Budget, BudgetExceeded, BudgetOwner, BudgetOwnerMissing, BudgetUnavailable
from bo19.ai_gateway.gateway import Gateway, ParseFailed, build_gateway
from bo19.ai_gateway.prompt_modules import CLASSIFY_INTENT, DRAFT_FREE_CONTENT, EXTRACT_SLOTS, InputInvalid, VariableSpec, catalog_fingerprint
from bo19.ai_gateway.providers import CALL_FAILED, RATE_LIMITED, ProviderClient, ProviderError
from bo19.ai_gateway.routing.profiles import load_profiles
from bo19.config import working_values as wv
from bo19.config.settings import load_settings
from bo19.observability.log import configure_logging
from bo19.observability.trace import is_trace_id, trace_scope
from bo19.persistence.pool import Pool
from tests import pg_support
from tests.test_provider_adapter import Drip, Recorder

RES = "GIA_TRI_RES_GIA_079123456789_KHONG_DUOC_LOT_RA"
KEY = "KHOA_API_KHONG_DUOC_LOT_RA_9f3a7c1e"
CATALOG = [{"code": "WORK_CONFIRMATION", "support_status": "SUPPORTED", "name_vi": "Xác nhận công tác", "description": "mô tả riêng của loại", "example_phrases": ["xin giấy xác nhận"]},
           {"code": "ROOM_BOOKING", "support_status": "KNOWN_UNSUPPORTED", "name_vi": "Đặt phòng", "description": "d", "example_phrases": ["đặt phòng họp"]}]
P1 = {"current_turn_text": f"xin giấy xác nhận, mục đích {RES}", "pending_question": None, "active_request_type": None, "request_type_catalog": CATALOG}
P2 = {"current_turn_text": f"gửi Công ty ABC {RES}", "pending_question": "ASK_SLOT", "slot_specs": [{"name": "recipient_org", "data_type": "STRING", "description": "d"}]}
VAR = VariableSpec("purpose_statement", 120, ("purpose",))
P4 = {"purpose": f"bổ sung hồ sơ {RES}", "variable_guidance": "ngắn gọn", "request_type": "WORK_CONFIRMATION"}
GOOD_P1 = {"intent": "WORK_CONFIRMATION", "secondary_intent": None, "confidence": "high", "retrieval_query": None}
GOOD_P4 = {"variable_name": "purpose_statement", "body": "Bổ sung hồ sơ vay vốn tại Ngân hàng X theo yêu cầu của đơn vị tiếp nhận."}
USAGE = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150, "prompt_time": 0.01, "completion_time": 0.2, "completion_tokens_details": {"reasoning_tokens": 12}}


def reply(content: Any, usage: dict | None = None) -> httpx.Response:
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    return httpx.Response(200, json={"choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}], "usage": usage or USAGE})


@unittest.skipUnless(pg_support.SUPERUSER_DSN, "cần BO19_TEST_PG_SUPERUSER_DSN")
class Base(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = pg_support.get_db()
        cls.pool = Pool(cls.db.dsn("bo19_app"), application_name="bo19-test-gateway", min_size=1, max_size=4)
        cls.pool.open()
        cls.profiles = load_profiles().profiles

    @classmethod
    def tearDownClass(cls):
        cls.pool.close()

    def setUp(self):
        self.out = io.StringIO()
        h = configure_logging(self.out, logging.DEBUG)
        self.addCleanup(logging.getLogger().removeHandler, h)
        self.addCleanup(setattr, wv, "LLM_RETRY_PAUSE_SECONDS", wv.LLM_RETRY_PAUSE_SECONDS)
        wv.LLM_RETRY_PAUSE_SECONDS = 0.01
        employee_id, _ = self.db.make_employee()
        self.session = self.db.make_chat_session(employee_id)
        self.owner = BudgetOwner(chat_session_id=self.session)

    def gateway(self, rec: Recorder, key: str | None = KEY, pool: Pool | None = None) -> Gateway:
        client = ProviderClient(base_url="https://llm.example.test/openai/v1", api_key=key, transport=rec.transport)
        return Gateway(profiles=self.profiles, client=client, budget=Budget(pool or self.pool))

    def rows(self, owner: BudgetOwner | None = None) -> list[tuple]:
        return self.db.usage_rows(chat_session_id=(owner or self.owner).chat_session_id)

    def logged(self) -> list[dict]:
        return [json.loads(x) for x in self.out.getvalue().splitlines() if x.startswith("{")]

    def sent(self, rec: Recorder, i: int = 0) -> dict:
        return json.loads(rec.requests[i].content)

    def assertNoLeak(self, needle: str, *extra: Any):
        self.assertNotIn(needle, self.out.getvalue())
        for t in extra:
            self.assertNotIn(needle, repr(t))
            self.assertNotIn(needle, str(t))


class DuongChinh(Base):
    async def test_p1_ok_tra_output_da_validate_va_ghi_dung_mot_dong_so(self):
        rec = Recorder(reply(GOOD_P1))
        with trace_scope() as trace_id:
            r = await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual((r.output, r.outcome, r.model, r.prompt_module_version), (GOOD_P1, "OK", "openai/gpt-oss-20b", "1.0"))
        self.assertEqual((r.input_tokens, r.output_tokens, r.reasoning_tokens), (120, 30, 12))
        (row,) = self.rows()
        self.assertEqual(row[:7], ("classify_intent", "CHEAP", "1.0", 120, 30, 12, "OK"))
        self.assertEqual(row[7], trace_id)  # trace_id lấy từ ngữ cảnh trace, không chuỗi tự do
        self.assertEqual(len(rec.requests), 1)

    async def test_request_gui_di_dung_hinh_dang(self):
        rec = Recorder(reply(GOOD_P1))
        await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner)
        body = self.sent(rec)
        self.assertEqual((body["model"], body["reasoning_effort"], body["temperature"], body["max_completion_tokens"], body["stream"]),
                         ("openai/gpt-oss-20b", "low", 0.2, 512, False))  # tham số tường minh + trần output cứng của module (A-090)
        self.assertNotIn("max_tokens", body)
        self.assertIs(body["include_reasoning"], False)  # không nhận văn bản suy luận (PO, 2026-10-05)
        schema = body["response_format"]["json_schema"]
        self.assertEqual((schema["name"], schema["strict"]), ("classify_intent", True))
        self.assertEqual(schema["schema"]["properties"]["intent"]["enum"], ["WORK_CONFIRMATION", "ROOM_BOOKING", "OUT_OF_SCOPE", "NEED_CLARIFICATION"])  # sinh từ catalog (ADR-025)
        system, user = body["messages"]
        self.assertEqual((system["role"], system["content"]), ("system", CLASSIFY_INTENT.instructions))
        sent_inputs = json.loads(user["content"].split("\n", 1)[1])
        self.assertEqual(set(sent_inputs), set(CLASSIFY_INTENT.fixed_inputs))  # chỉ khoá đã khai — INV-03

    async def test_ac_1_9_tap_khoa_gui_di_cua_draft_free_content(self):
        rec = Recorder(reply(GOOD_P4))
        r = await self.gateway(rec).call(DRAFT_FREE_CONTENT, P4, self.owner, variable=VAR)
        self.assertEqual(r.output, GOOD_P4)
        body = self.sent(rec)
        self.assertEqual(set(json.loads(body["messages"][1]["content"].split("\n", 1)[1])), {"purpose", "variable_guidance", "request_type"})
        self.assertEqual(body["model"], "openai/gpt-oss-120b")  # tier mạnh
        self.assertEqual((body["reasoning_effort"], body["temperature"], body["max_completion_tokens"]), ("medium", 0.3, 2048))  # tier mạnh: tường minh, không dựa mặc định
        self.assertIs(body["include_reasoning"], False)
        self.assertNotIn("max_tokens", body)
        prop = body["response_format"]["json_schema"]["schema"]["properties"]
        self.assertEqual((prop["variable_name"]["const"], prop["body"]["maxLength"]), ("purpose_statement", 120))
        (row,) = self.rows()
        self.assertEqual(row[:2], ("draft_free_content", "STRONG"))

    async def test_p2_ok(self):
        out = {"slots": [{"slot_name": "recipient_org", "value": "Công ty ABC", "evidence_span": [4, 15], "evidence_quote": "Công ty ABC"}]}
        r = await self.gateway(Recorder(reply(out))).call(EXTRACT_SLOTS, P2, self.owner)
        self.assertEqual(r.output, out)

    async def test_ca_chu_budget_la_request(self):
        rid = self.db.make_request()
        owner = BudgetOwner(request_id=rid)
        await self.gateway(Recorder(reply(GOOD_P4))).call(DRAFT_FREE_CONTENT, P4, owner, variable=VAR)
        self.assertEqual(len(self.db.usage_rows(request_id=rid)), 1)


class Allowlist(Base):
    """AC-1.9: khoá thừa hay thiếu → ALLOWLIST_REJECTED, không có lời gọi nào tới provider."""

    async def test_khoa_thua_va_thieu_khong_toi_provider_va_co_dong_so(self):
        for module, good, var in ((CLASSIFY_INTENT, P1, None), (EXTRACT_SLOTS, P2, None), (DRAFT_FREE_CONTENT, P4, VAR)):
            for bad in ({**good, "lich_su": RES}, {k: v for k, v in good.items() if k != next(iter(good))}):
                self.out.truncate(0), self.out.seek(0)
                owner = BudgetOwner(chat_session_id=self.db.make_chat_session(self.db.make_employee()[0]))
                rec = Recorder(reply(GOOD_P1))
                with self.assertRaises(AllowlistRejected) as cm:
                    await self.gateway(rec).call(module, bad, owner, variable=var)
                self.assertEqual(len(rec.requests), 0, module.call_name)
                (row,) = self.rows(owner)
                self.assertEqual((row[0], row[3], row[4], row[5], row[6]), (module.call_name, 0, None, None, "ALLOWLIST_REJECTED"))
                self.assertNoLeak(RES, cm.exception, cm.exception.__dict__, row)

    async def test_log_chi_ten_khoa_khong_gia_tri(self):
        with self.assertRaises(AllowlistRejected):
            await self.gateway(Recorder(reply(GOOD_P1))).call(EXTRACT_SLOTS, {**P2, "employee": {"national_id": RES}}, self.owner)
        (event,) = [e for e in self.logged() if e["message"] == "LLM_ALLOWLIST_REJECTED"]
        self.assertEqual((event["extra"], event["missing"]), ("employee", ""))
        self.assertNotIn(RES, self.out.getvalue())

    async def test_khoa_cam_cua_p4_bi_tu_choi_ke_ca_khi_template_khai(self):
        rec = Recorder(reply(GOOD_P4))
        var = VariableSpec("purpose_statement", 120, ("purpose", "national_id"))
        with self.assertRaises(AllowlistRejected):
            await self.gateway(rec).call(DRAFT_FREE_CONTENT, {**P4, "national_id": RES}, self.owner, variable=var)
        self.assertEqual(len(rec.requests), 0)
        self.assertNotIn(RES, self.out.getvalue())

    async def test_allowlist_chay_truoc_budget(self):
        self.db_spend(self.session, 10**9)  # budget đã cạn
        with self.assertRaises(AllowlistRejected):  # không phải BudgetExceeded
            await self.gateway(Recorder(reply(GOOD_P1))).call(EXTRACT_SLOTS, {**P2, "them": 1}, self.owner)

    async def test_input_sai_kieu_la_loi_lap_trinh_khong_ghi_so_khong_goi_provider(self):
        rec = Recorder(reply(GOOD_P1))
        with self.assertRaises(InputInvalid):
            await self.gateway(rec).call(CLASSIFY_INTENT, {**P1, "request_type_catalog": []}, self.owner)
        with self.assertRaises(InputInvalid):
            await self.gateway(rec).call(DRAFT_FREE_CONTENT, P4, self.owner)  # thiếu `variable`
        self.assertEqual((len(rec.requests), self.rows()), (0, []))

    def db_spend(self, session_id, tokens: int):
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into llm_usage (id, call_name, model_tier, input_tokens, output_tokens, outcome, trace_id, chat_session_id) values (%s, 'classify_intent', 'CHEAP', %s, 0, 'OK', %s, %s)",
                      (uuid.uuid4(), tokens, str(uuid.uuid4()), session_id))


class ChuBudget(Base):
    async def test_thieu_chu_budget_la_loi_lap_trinh(self):
        rec = Recorder(reply(GOOD_P1))
        for owner in (BudgetOwner(), BudgetOwner(document_id=uuid.uuid4())):
            with self.assertRaises(BudgetOwnerMissing):
                await self.gateway(rec).call(CLASSIFY_INTENT, P1, owner)
        self.assertEqual(len(rec.requests), 0)

    def spend(self, session_id=None, request_id=None, **cols):
        cols = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, **cols}
        with self.db.connect("bo19_migrator") as c:
            c.execute("insert into llm_usage (id, call_name, model_tier, input_tokens, output_tokens, reasoning_tokens, outcome, trace_id, chat_session_id, request_id) "
                      "values (%s, 'classify_intent', 'CHEAP', %s, %s, %s, 'OK', %s, %s, %s)",
                      (uuid.uuid4(), cols["input_tokens"], cols["output_tokens"], cols["reasoning_tokens"], str(uuid.uuid4()), session_id, request_id))

    async def test_tran_chat_session_46500_dung_ngay_bien(self):
        self.assertEqual(wv.TOKEN_CEILING_CHAT_SESSION, 46_500)
        self.spend(self.session, input_tokens=20_000, output_tokens=16_000, reasoning_tokens=10_499)  # 46.499 — cộng cả completion lẫn reasoning (tính dư, O1-3)
        rec = Recorder(reply(GOOD_P1))
        await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner)  # còn dưới trần: qua
        self.assertEqual(len(rec.requests), 1)
        rows = self.rows()
        self.assertEqual([r[6] for r in rows], ["OK", "OK"])
        # dòng vừa ghi thêm 162 token → tổng 46.661 ≥ 46.500: lần sau bị chặn
        rec2 = Recorder(reply(GOOD_P1))
        with self.assertRaises(BudgetExceeded) as cm:
            await self.gateway(rec2).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual((cm.exception.dimension, len(rec2.requests)), ("chat_session", 0))  # không tới provider
        self.assertEqual(self.rows()[-1][6], "BUDGET_EXCEEDED")
        self.assertEqual(self.rows()[-1][3], 0)

    async def test_dung_bang_tran_la_chan_va_thieu_mot_token_thi_qua(self):
        for spent, blocked in ((46_500, True), (46_499, False)):
            owner = BudgetOwner(chat_session_id=self.db.make_chat_session(self.db.make_employee()[0]))
            self.spend(owner.chat_session_id, input_tokens=spent)
            rec = Recorder(reply(GOOD_P1))
            if blocked:
                with self.assertRaises(BudgetExceeded):
                    await self.gateway(rec).call(CLASSIFY_INTENT, P1, owner)
                self.assertEqual(len(rec.requests), 0)
            else:
                await self.gateway(rec).call(CLASSIFY_INTENT, P1, owner)
                self.assertEqual(len(rec.requests), 1)

    async def test_reasoning_tokens_duoc_tinh_vao_tran(self):
        self.spend(self.session, input_tokens=0, output_tokens=0, reasoning_tokens=46_500)  # chỉ reasoning
        with self.assertRaises(BudgetExceeded):
            await self.gateway(Recorder(reply(GOOD_P1))).call(CLASSIFY_INTENT, P1, self.owner)

    async def test_tran_request_92000(self):
        self.assertEqual(wv.TOKEN_CEILING_REQUEST, 92_000)
        rid = self.db.make_request()
        owner = BudgetOwner(request_id=rid)
        self.spend(request_id=rid, input_tokens=91_999)
        rec = Recorder(reply(GOOD_P4))
        await self.gateway(rec).call(DRAFT_FREE_CONTENT, P4, owner, variable=VAR)
        self.assertEqual(len(rec.requests), 1)
        with self.assertRaises(BudgetExceeded) as cm:
            await self.gateway(Recorder(reply(GOOD_P4))).call(DRAFT_FREE_CONTENT, P4, owner, variable=VAR)
        self.assertEqual(cm.exception.dimension, "request")

    async def test_chu_la_ca_hai_thi_chu_nao_cham_tran_cung_chan(self):
        rid = self.db.make_request()
        owner = BudgetOwner(request_id=rid, chat_session_id=self.session)
        self.spend(request_id=rid, input_tokens=92_000)  # chỉ `request` cạn
        with self.assertRaises(BudgetExceeded) as cm:
            await self.gateway(Recorder(reply(GOOD_P1))).call(CLASSIFY_INTENT, P1, owner)
        self.assertEqual(cm.exception.dimension, "request")

    async def test_chu_khac_khong_anh_huong(self):
        self.spend(self.session, input_tokens=10**6)
        other = BudgetOwner(chat_session_id=self.db.make_chat_session(self.db.make_employee()[0]))
        await self.gateway(Recorder(reply(GOOD_P1))).call(CLASSIFY_INTENT, P1, other)

    async def test_khong_doc_duoc_so_da_tieu_thi_tu_choi_va_khong_goi_provider(self):  # ADR-019 ca 1
        small = Pool(self.db.dsn("bo19_app"), application_name="bo19-test-gw-small", min_size=1, max_size=1, acquire_timeout_s=0.2)
        small.open()
        self.addCleanup(small.close)
        rec = Recorder(reply(GOOD_P1))
        with small.acquire():  # giữ connection duy nhất: cả đọc lẫn ghi sổ đều không được
            with self.assertRaises(BudgetUnavailable):
                await self.gateway(rec, pool=small).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual(len(rec.requests), 0)
        self.assertEqual(self.rows(), [])  # DB không đọc được thì cũng không ghi được — chỉ còn log
        self.assertIn("LLM_BUDGET_UNAVAILABLE", self.out.getvalue())
        self.assertIn("LLM_USAGE_WRITE_FAILED", self.out.getvalue())

    async def test_dong_budget_unavailable_duoc_ghi_khi_doc_loi_nhung_ghi_duoc(self):
        with mock.patch.object(Budget, "check", side_effect=BudgetUnavailable):
            rec = Recorder(reply(GOOD_P1))
            with self.assertRaises(BudgetUnavailable):
                await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual((len(rec.requests), [r[6] for r in self.rows()]), (0, ["BUDGET_UNAVAILABLE"]))

    async def test_ghi_so_hong_khong_lam_hong_loi_goi_da_co_ket_qua_nhung_phai_log(self):
        with mock.patch("bo19.ai_gateway.budget.unit_of_work", side_effect=RuntimeError("DB hỏng")):
            r = await self.gateway(Recorder(reply(GOOD_P1))).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual(r.output, GOOD_P1)
        self.assertEqual(self.rows(), [])
        (event,) = [e for e in self.logged() if e["message"] == "LLM_USAGE_WRITE_FAILED"]
        self.assertEqual(event["error_type"], "RuntimeError")
        self.assertNotIn("DB hỏng", self.out.getvalue())


class EpJson(Base):
    async def test_json_hong_sua_dung_mot_lan_roi_dat(self):
        rec = Recorder(reply("{khong phai json"), reply(GOOD_P1))
        r = await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual((r.outcome, r.output, len(rec.requests)), ("PARSE_REPAIRED", GOOD_P1, 2))
        (row,) = self.rows()  # một dòng cho cả lời gọi, token cộng dồn
        self.assertEqual((row[3], row[4], row[5], row[6]), (240, 60, 24, "PARSE_REPAIRED"))
        repair = self.sent(rec, 1)["messages"]
        self.assertEqual([m["role"] for m in repair], ["system", "user", "assistant", "user"])
        self.assertEqual(repair[2]["content"], "{khong phai json")
        self.assertIn("$: NOT_JSON", repair[3]["content"])

    async def test_ma_ngoai_catalog_la_json_hong(self):  # 07-prompts.md mục 4.1 Failure
        rec = Recorder(reply({**GOOD_P1, "intent": "MA_LA"}), reply(GOOD_P1))
        r = await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual(r.outcome, "PARSE_REPAIRED")
        self.assertIn("intent: ENUM", self.sent(rec, 1)["messages"][3]["content"])

    async def test_hong_hai_lan_la_parse_failed_va_khong_sua_lan_ba(self):
        rec = Recorder(reply({**GOOD_P1, "intent": "MA_LA"}))
        with self.assertRaises(ParseFailed) as cm:
            await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual(len(rec.requests), 2)  # đúng một lần sửa
        self.assertEqual([(v.path, v.code) for v in cm.exception.violations], [("intent", "ENUM")])
        (row,) = self.rows()
        self.assertEqual((row[3], row[6]), (240, "PARSE_FAILED"))  # token của cả hai lần vẫn được tính

    async def test_thong_bao_sua_loi_khong_mang_gia_tri_cua_output(self):
        bad = {**GOOD_P1, "intent": RES, RES: RES}
        rec = Recorder(reply(bad), reply(GOOD_P1))
        await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner)
        msgs = self.sent(rec, 1)["messages"]
        self.assertNotIn(RES.replace("GIA_TRI_RES_GIA_", "")[:10], msgs[3]["content"])  # tin nhắn lỗi chỉ có đường dẫn và mã
        self.assertNotIn(RES, msgs[3]["content"])
        self.assertIn(RES, msgs[2]["content"])  # output cũ được gửi lại cho CHÍNH provider đó (cùng loại dữ liệu đã gửi) — nhưng không vào log
        self.assertNoLeak(RES)

    async def test_p4_vuot_max_length_la_hong(self):
        rec = Recorder(reply({**GOOD_P4, "body": "x" * 121}), reply(GOOD_P4))
        r = await self.gateway(rec).call(DRAFT_FREE_CONTENT, P4, self.owner, variable=VAR)
        self.assertEqual(r.outcome, "PARSE_REPAIRED")
        self.assertIn("body: MAX_LENGTH", self.sent(rec, 1)["messages"][3]["content"])

    async def test_dung_mot_ten_bien(self):
        rec = Recorder(reply({**GOOD_P4, "variable_name": "work_content_statement"}), reply({**GOOD_P4, "variable_name": "work_content_statement"}))
        with self.assertRaises(ParseFailed) as cm:
            await self.gateway(rec).call(DRAFT_FREE_CONTENT, P4, self.owner, variable=VAR)
        self.assertEqual([(v.path, v.code) for v in cm.exception.violations], [("variable_name", "CONST")])


class JsonValidateFailed(Base):
    """PO, 2026-10-05: HTTP 400 `json_validate_failed` (output bị cắt do trần thấp / không hợp schema) đi đường sửa parse một lần; log mã con riêng."""

    def jvf(self) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": f"Failed to generate JSON. {RES}", "type": "invalid_request_error", "code": "json_validate_failed",
                                                   "failed_generation": RES}})

    async def test_lan_dau_400_json_validate_failed_roi_sua_dat(self):
        rec = Recorder(self.jvf(), reply(GOOD_P1))
        r = await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual((r.outcome, r.output, len(rec.requests)), ("PARSE_REPAIRED", GOOD_P1, 2))
        roles = [m["role"] for m in self.sent(rec, 1)["messages"]]
        self.assertEqual(roles, ["system", "user", "user"])  # không có output cũ để gửi lại
        self.assertIn("$: JSON_VALIDATE_FAILED", self.sent(rec, 1)["messages"][2]["content"])
        self.assertIn("quá dài", self.sent(rec, 1)["messages"][2]["content"])
        (row,) = self.rows()
        self.assertEqual((row[3], row[4], row[5], row[6]), (120, 30, 12, "PARSE_REPAIRED"))  # token chỉ của lần có usage
        self.assertEqual(self.sent(rec, 0)["max_completion_tokens"], 512)

    async def test_log_ma_con_rieng_co_tran_va_so_lan_thu(self):
        await self.gateway(Recorder(self.jvf(), reply(GOOD_P1))).call(CLASSIFY_INTENT, P1, self.owner)
        (event,) = [e for e in self.logged() if e["message"] == "LLM_PROVIDER_JSON_VALIDATE_FAILED"]
        self.assertEqual((event["provider_error_code"], event["max_completion_tokens"], event["attempt"], event["call_name"], event["tier"]),
                         ("json_validate_failed", 512, 1, "classify_intent", "CHEAP"))
        self.assertNotIn("LLM_PROVIDER_ERROR", self.out.getvalue())  # không phải lỗi provider
        self.assertNoLeak(RES)

    async def test_hai_lan_deu_400_la_parse_failed_khong_phai_provider_error(self):
        rec = Recorder(self.jvf())
        with self.assertRaises(ParseFailed) as cm:
            await self.gateway(rec).call(DRAFT_FREE_CONTENT, P4, self.owner, variable=VAR)
        self.assertEqual(len(rec.requests), 2)  # đúng một lần sửa
        self.assertEqual([(v.path, v.code) for v in cm.exception.violations], [("$", "JSON_VALIDATE_FAILED")])
        (row,) = self.rows()
        self.assertEqual((row[0], row[1], row[3], row[6]), ("draft_free_content", "STRONG", 0, "PARSE_FAILED"))
        events = [e for e in self.logged() if e["message"] == "LLM_PROVIDER_JSON_VALIDATE_FAILED"]
        self.assertEqual([(e["attempt"], e["max_completion_tokens"]) for e in events], [(1, 2048), (2, 2048)])
        self.assertNoLeak(RES, cm.exception, cm.exception.__dict__, "".join(traceback.format_exception(cm.exception)), self.rows())

    async def test_400_khac_ma_van_la_provider_error_khong_sua(self):
        for body in ({"error": {"type": "invalid_request_error", "code": "invalid_api_key"}}, {"error": {"type": "invalid_request_error"}},
                     {"error": {"type": "invalid_request_error", "code": "json_validate_failed_khac"}}):
            rec = Recorder(httpx.Response(400, json=body))
            with self.assertRaises(ProviderError):
                await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner)
            self.assertEqual(len(rec.requests), 1)

    async def test_ma_json_validate_failed_o_status_khac_400_la_provider_error(self):
        rec = Recorder(httpx.Response(422, json={"error": {"type": "x", "code": "json_validate_failed"}}))
        with self.assertRaises(ProviderError):
            await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual(len(rec.requests), 1)

    async def test_json_validate_failed_dung_chung_han_chot(self):
        self.addCleanup(setattr, wv, "LLM_CALL_DEADLINE_CHEAP_SECONDS", wv.LLM_CALL_DEADLINE_CHEAP_SECONDS)
        wv.LLM_CALL_DEADLINE_CHEAP_SECONDS = 0.3

        async def slow_jvf():
            await asyncio.sleep(0.4)
            return self.jvf()

        with self.assertRaises(ProviderError) as cm:
            await self.gateway(Recorder(slow_jvf)).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual(cm.exception.kind, "DEADLINE")


class LoiProvider(Base):
    async def test_loi_http_ghi_provider_error_va_chi_log_ba_thu(self):
        body = {"error": {"message": f"input của bạn: {RES}", "type": "invalid_request_error", "code": "context_length_exceeded", "failed_generation": RES}}
        with self.assertRaises(ProviderError) as cm:
            await self.gateway(Recorder(httpx.Response(400, json=body))).call(CLASSIFY_INTENT, P1, self.owner)
        e = cm.exception
        self.assertEqual((e.subcode, e.http_status, e.error_type, e.error_code), (CALL_FAILED, 400, "invalid_request_error", "context_length_exceeded"))
        (row,) = self.rows()
        self.assertEqual((row[3], row[4], row[5], row[6]), (0, None, None, "PROVIDER_ERROR"))
        (event,) = [x for x in self.logged() if x["message"] == "LLM_PROVIDER_ERROR"]
        self.assertEqual((event["http_status"], event["provider_error_type"], event["provider_error_code"]), (400, "invalid_request_error", "context_length_exceeded"))
        # RES (cả trong thân lỗi lẫn trong input) không lộ ra log, lỗi trả lên, hay sổ
        self.assertNoLeak(RES, e, e.__dict__, row, "".join(traceback.format_exception(e)))

    async def test_401_khong_lo_khoa(self):
        echo = {"error": {"message": f"Invalid API Key {KEY}", "type": "invalid_request_error", "code": "invalid_api_key"}}
        gw = self.gateway(Recorder(httpx.Response(401, json=echo)))
        with self.assertRaises(ProviderError) as cm:
            await gw.call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual((cm.exception.http_status, cm.exception.attempts), (401, 1))
        self.assertNoLeak(KEY, cm.exception, cm.exception.__dict__, gw, gw.__dict__, gw._client, "".join(traceback.format_exception(cm.exception)), self.rows())

    async def test_khong_khoa_thi_provider_error_khong_goi_mang_van_ghi_so(self):
        rec = Recorder(reply(GOOD_P1))
        with self.assertRaises(ProviderError) as cm:
            await self.gateway(rec, key=None).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual((cm.exception.kind, len(rec.requests), [r[6] for r in self.rows()]), ("NO_API_KEY", 0, ["PROVIDER_ERROR"]))

    async def test_429_trong_job_vuot_wv19_khong_cho(self):
        wv_old = wv.LLM_CALL_DEADLINE_STRONG_SECONDS
        self.addCleanup(setattr, wv, "LLM_CALL_DEADLINE_STRONG_SECONDS", wv_old)
        wv.LLM_CALL_DEADLINE_STRONG_SECONDS = 1000
        rec = Recorder(httpx.Response(429, headers={"retry-after": "121"}))
        t = time.monotonic()
        with self.assertRaises(ProviderError) as cm:
            await self.gateway(rec).call(DRAFT_FREE_CONTENT, P4, self.owner, variable=VAR)  # không có turn_deadline = chạy trong job
        self.assertEqual((cm.exception.subcode, cm.exception.retry_after_seconds, len(rec.requests)), (RATE_LIMITED, 121, 1))
        self.assertLess(time.monotonic() - t, 1)

    async def test_loi_thoang_qua_roi_thanh_cong_van_mot_dong_so(self):
        rec = Recorder(httpx.Response(503), reply(GOOD_P1))
        r = await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual((r.outcome, len(rec.requests), [x[6] for x in self.rows()]), ("OK", 2, ["OK"]))


class HanChotTong(Base):
    def drip(self, content: Any, gap: float = 0.01) -> httpx.Response:
        data = json.dumps({"choices": [{"message": {"content": json.dumps(content)}}], "usage": USAGE}).encode()
        return httpx.Response(200, stream=Drip(data, gap))

    async def test_nho_giot_bi_cat_o_han_chot_cua_tier(self):
        self.addCleanup(setattr, wv, "LLM_CALL_DEADLINE_CHEAP_SECONDS", wv.LLM_CALL_DEADLINE_CHEAP_SECONDS)
        wv.LLM_CALL_DEADLINE_CHEAP_SECONDS = 0.3
        t = time.monotonic()
        with self.assertRaises(ProviderError) as cm:
            await self.gateway(Recorder(self.drip(GOOD_P1))).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual(cm.exception.kind, "DEADLINE")
        self.assertLess(time.monotonic() - t, 0.8)
        self.assertEqual([r[6] for r in self.rows()], ["PROVIDER_ERROR"])

    async def test_han_chot_luot_den_truoc_han_chot_tier(self):
        loop = asyncio.get_running_loop()
        t = time.monotonic()
        with self.assertRaises(ProviderError) as cm:
            await self.gateway(Recorder(self.drip(GOOD_P1))).call(CLASSIFY_INTENT, P1, self.owner, turn_deadline=loop.time() + 0.3)  # tier rẻ còn 8 s
        self.assertEqual(cm.exception.kind, "DEADLINE")
        self.assertLess(time.monotonic() - t, 0.8)

    async def test_han_chot_luot_da_qua_thi_khong_goi_provider(self):
        rec = Recorder(reply(GOOD_P1))
        with self.assertRaises(ProviderError) as cm:
            await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner, turn_deadline=asyncio.get_running_loop().time() - 1)
        self.assertEqual((cm.exception.kind, len(rec.requests), [r[6] for r in self.rows()]), ("DEADLINE", 0, ["PROVIDER_ERROR"]))

    async def test_lan_sua_parse_dung_chung_han_chot_va_token_lan_dau_van_ghi(self):
        self.addCleanup(setattr, wv, "LLM_CALL_DEADLINE_CHEAP_SECONDS", wv.LLM_CALL_DEADLINE_CHEAP_SECONDS)
        wv.LLM_CALL_DEADLINE_CHEAP_SECONDS = 1.0

        async def slow_bad():
            await asyncio.sleep(0.5)  # lần đầu hỏng sau 0.5 s: lần sửa chỉ còn ~0.5 s trong hạn chót tổng 1.0 s — biên rộng để không flaky khi máy tải
            return reply("{hong")

        rec = Recorder(slow_bad, self.drip(GOOD_P1))  # lần sửa nhỏ giọt
        t = time.monotonic()
        with self.assertRaises(ProviderError) as cm:
            await self.gateway(rec).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual((cm.exception.kind, len(rec.requests)), ("DEADLINE", 2))
        self.assertLess(time.monotonic() - t, 1.25)  # nếu lần sửa được cấp lại cả 1.0 s thì tổng ≈ 1.5 s
        (row,) = self.rows()
        self.assertEqual((row[3], row[4], row[5], row[6]), (120, 30, 12, "PROVIDER_ERROR"))  # token của lần đầu đã tiêu thật — không mất khỏi sổ

    async def test_gia_tri_mac_dinh_theo_wv(self):
        self.assertEqual((wv.LLM_CALL_DEADLINE_CHEAP_SECONDS, wv.LLM_CALL_DEADLINE_STRONG_SECONDS), (8, 60))


class LogVaCanhBao(Base):
    async def test_log_khong_chua_input_output_hay_khoa(self):
        out = {**GOOD_P1, "retrieval_query": f"truy vấn {RES}"}
        await self.gateway(Recorder(reply(out))).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertNoLeak(RES)
        self.assertNotIn(KEY, self.out.getvalue())
        self.assertNotIn("mô tả riêng của loại", self.out.getvalue())  # catalog là input — chỉ dấu vân tay vào log

    async def test_log_co_dau_van_tay_catalog_p1_va_khong_vao_so(self):
        await self.gateway(Recorder(reply(GOOD_P1))).call(CLASSIFY_INTENT, P1, self.owner)
        (event,) = [e for e in self.logged() if e["message"] == "LLM_CALL_DONE"]
        self.assertEqual(event["catalog_fingerprint"], catalog_fingerprint(CATALOG))
        self.assertEqual((event["call_name"], event["tier"], event["outcome"], event["input_tokens"], event["output_tokens"], event["reasoning_tokens"],
                          event["prompt_module_version"], event["model"]), ("classify_intent", "CHEAP", "OK", 120, 30, 12, "1.0", "openai/gpt-oss-20b"))
        self.assertEqual(event["prompt_time"], 0.01)
        self.assertNotIn(catalog_fingerprint(CATALOG), repr(self.rows()))  # ADR-019: không thêm cột vào llm_usage

    async def test_p2_p4_khong_co_dau_van_tay(self):
        await self.gateway(Recorder(reply({"slots": []}))).call(EXTRACT_SLOTS, P2, self.owner)
        (event,) = [e for e in self.logged() if e["message"] == "LLM_CALL_DONE"]
        self.assertIsNone(event["catalog_fingerprint"])

    async def test_vuot_tran_moi_loi_goi_chi_canh_bao_khong_chan(self):  # A-090
        big = {**USAGE, "prompt_tokens": 1700, "completion_tokens": 100}  # > 1.500 của classify_intent
        r = await self.gateway(Recorder(reply(GOOD_P1, big))).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual(r.outcome, "OK")
        (event,) = [e for e in self.logged() if e["message"] == "LLM_CALL_OVER_CEILING"]
        self.assertEqual((event["total_tokens"], event["ceiling"], event["call_name"]), (1812, 1500, "classify_intent"))
        self.assertEqual(self.rows()[0][3], 1700)  # và vẫn được ghi, cộng vào tổng của chủ budget

    async def test_van_ban_suy_luan_cua_provider_khong_vao_log_hay_so(self):  # PO, 2026-10-05
        body = {"choices": [{"message": {"content": json.dumps(GOOD_P1), "reasoning": f"suy luận {RES}"}, "finish_reason": "stop"}], "usage": USAGE}
        r = await self.gateway(Recorder(httpx.Response(200, json=body))).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertEqual((r.output, r.reasoning_tokens), (GOOD_P1, 12))
        self.assertNoLeak(RES, r, self.rows())
        (event,) = [e for e in self.logged() if e["message"] == "LLM_CALL_DONE"]
        self.assertEqual((event["reasoning_tokens"], event["finish_reason"]), (12, "stop"))

    async def test_trong_tran_thi_khong_canh_bao(self):
        await self.gateway(Recorder(reply(GOOD_P1))).call(CLASSIFY_INTENT, P1, self.owner)
        self.assertNotIn("LLM_CALL_OVER_CEILING", self.out.getvalue())

    async def test_usage_thieu_thi_ghi_0_va_null_khong_suy_ra(self):
        resp = httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(GOOD_P1)}}]})
        r = await self.gateway(Recorder(resp)).call(CLASSIFY_INTENT, P1, self.owner)
        (row,) = self.rows()
        self.assertEqual((r.input_tokens, row[3], row[4], row[5]), (0, 0, None, None))


class DungGateway(Base):
    async def test_build_gateway_tu_settings(self):
        s = load_settings({"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": "x", "BO19_SESSION_SECRET": "y" * 32, "BO19_LLM_API_KEY": KEY})
        gw = build_gateway(s, self.pool)
        self.assertEqual(repr(gw), "Gateway()")
        for obj in (gw, gw._client, gw._budget, gw.__dict__, vars(gw._client)):
            self.assertNotIn(KEY, repr(obj))

    async def test_build_gateway_tu_choi_base_url_hong(self):
        s = load_settings({"BO19_ENVIRONMENT": "dev", "BO19_DATABASE_URL": "x", "BO19_SESSION_SECRET": "y" * 32, "BO19_LLM_BASE_URL": "http://x"})
        with self.assertRaises(RuntimeError):
            build_gateway(s, self.pool)


if __name__ == "__main__":
    unittest.main()
