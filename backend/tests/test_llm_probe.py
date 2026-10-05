"""`tools/llm-probe/` — che định danh, dữ liệu giả, và chạy thử toàn bộ tool với server giả (không mạng, không khoá thật). B4b.

Yêu cầu của PO (2026-10-05): tin nhắn trần 2.000 ký tự tiếng Việt CÓ DẤU, nhãn "(giả)"; thân response lưu vào `docs/reference/` được che định danh và tool tự quét báo đạt/không;
tool chỉ ghi số và mã, không ghi `message.content` hay nội dung suy luận — áp cho mọi thí nghiệm; ≤ 40 lời gọi, < 60K token mỗi model.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_llm_probe -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import importlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

import httpx

TOOL = Path(__file__).resolve().parents[2] / "tools" / "llm-probe"
sys.path.insert(0, str(TOOL))
sanitize = importlib.import_module("sanitize")
fixtures = importlib.import_module("fixtures")
llm_probe = importlib.import_module("llm_probe")

KEY = "gsk_ABCDEFGH1234567890abcdefghijklmnopqrstuv"
CONTENT_MARK = "NOI_DUNG_MODEL_TRA_VE_KHONG_DUOC_GHI_1234"
REASON_MARK = "NOI_DUNG_SUY_LUAN_KHONG_DUOC_GHI_5678"
ERROR_BODY = {"error": {"message": "Invalid API Key for organization `org_01hxyz9abc23defghijk4567` (Request ID: req_01kabcde12345fghijklmnop) from 203.0.113.9 user a.b@example.com "
                                   f"uuid 123e4567-e89b-12d3-a456-426614174000 key {KEY}", "type": "invalid_request_error", "code": "invalid_api_key"}}


class Sanitize(unittest.TestCase):
    def test_che_tung_loai_dinh_danh(self):
        text = json.dumps(ERROR_BODY, ensure_ascii=False)
        masked = sanitize.mask(text, [KEY])
        for needle in ("org_01hxyz9abc23defghijk4567", "req_01kabcde12345fghijklmnop", "203.0.113.9", "a.b@example.com", "123e4567-e89b-12d3-a456-426614174000", KEY, KEY[:8]):
            self.assertNotIn(needle, masked, needle)
        self.assertIn("<masked>", masked)
        self.assertIn("invalid_request_error", masked)  # loại lỗi và code giữ nguyên
        self.assertIn("invalid_api_key", masked)
        self.assertEqual(sanitize.self_check(masked, [KEY]), [])

    def test_self_check_bat_cai_chua_che(self):
        self.assertIn("PREFIXED_ID", sanitize.self_check("Request ID: req_01kabcde12345fghijklmnop"))
        self.assertIn("UUID", sanitize.self_check("123e4567-e89b-12d3-a456-426614174000"))
        self.assertIn("EMAIL", sanitize.self_check("a.b@example.com"))
        self.assertIn("IPV4", sanitize.self_check("203.0.113.9"))
        self.assertIn("HEX_LONG", sanitize.self_check("deadbeefdeadbeef0123"))
        self.assertIn("IDENT_LIKE", sanitize.self_check("kQ8zX2mP9vL4nR7tY1wB"))
        self.assertIn("SECRET_PRESENT", sanitize.self_check("abc " + KEY, [KEY]))
        self.assertIn("SECRET_PRESENT", sanitize.self_check("abc " + KEY[:8] + "zz", [KEY]))
        self.assertIn("AUTH_HEADER", sanitize.self_check("Authorization: Bearer abcdef123456"))

    def test_khong_che_nham_nhan_va_ma_loi_thong_thuong(self):
        text = "E6-STRONG-include_reasoning-false | invalid_request_error | model_not_found | openai/gpt-oss-120b | context_length_exceeded | HTTP 400"
        self.assertEqual(sanitize.mask(text), text)
        self.assertEqual(sanitize.self_check(text), [])

    def test_ma_ngan_co_tien_to_dinh_danh_van_bi_che(self):  # chỉ bộ che theo tiền tố bắt được — chuỗi quá ngắn để bị coi là "giống định danh"
        masked = sanitize.mask("tổ chức org_9z8y7x, yêu cầu req_abc123, người dùng user_42abcd")
        for needle in ("org_9z8y7x", "req_abc123", "user_42abcd"):
            self.assertNotIn(needle, masked)
        self.assertIn("PREFIXED_ID", sanitize.self_check("req_abc123"))

    def test_che_la_idempotent(self):
        once = sanitize.mask(json.dumps(ERROR_BODY), [KEY])
        self.assertEqual(sanitize.mask(once, [KEY]), once)

    def test_khoa_ngan_chi_che_ca_chuoi(self):
        self.assertNotIn("short1", sanitize.mask("khoa short1 het", ["short1"]))


class DuLieuGia(unittest.TestCase):
    def test_tin_nhan_tran_dai_dung_2000_ky_tu_va_co_nhan_gia(self):
        m = fixtures.bare_message()
        self.assertEqual(len(m), 2000)  # WV-15
        self.assertTrue(m.endswith("(giả)"))

    def test_tieng_viet_co_dau_van_phong_nhan_vien(self):
        m = fixtures.bare_message()
        letters = [c for c in m if c.isalpha()]
        accented = [c for c in letters if ord(c) > 127]
        self.assertGreater(len(accented) / len(letters), 0.12)  # tiếng Việt có dấu: tỷ lệ chữ ngoài ASCII cao; không dấu thì ≈ 0
        for word in ("em", "chị", "ạ", "giúp", "nhắn"):
            self.assertIn(word, m)

    def test_khong_co_dinh_danh_that(self):
        blob = json.dumps([fixtures.bare_message(), fixtures.CATALOG, fixtures.P2_MESSAGE, fixtures.P2_SLOT_SPECS, fixtures.P4_INPUTS], ensure_ascii=False)
        self.assertIsNone(re.search(r"\d{9,}", blob))  # không số giống căn cước
        self.assertIsNone(re.search(r"@\w", blob))
        self.assertEqual(sanitize.self_check(blob), [])

    def test_moi_noi_dung_dang_ke_deu_co_nhan_gia(self):
        for e in fixtures.CATALOG:
            self.assertIn("(giả)", e["name_vi"])
            self.assertIn("(giả)", e["description"])
        for text in (fixtures.P2_MESSAGE, fixtures.P4_INPUTS["purpose"], fixtures.P4_INPUTS["variable_guidance"], fixtures.PING):
            self.assertIn("(giả)", text)
        for spec in fixtures.P2_SLOT_SPECS:
            self.assertIn("(giả)", spec["description"])

    def test_catalog_6_loai_hop_le_voi_p1(self):
        from bo19.ai_gateway.prompt_modules import CLASSIFY_INTENT
        inputs = {"current_turn_text": fixtures.bare_message(), "pending_question": None, "active_request_type": None, "request_type_catalog": fixtures.CATALOG}
        CLASSIFY_INTENT.check_inputs(inputs)
        self.assertEqual(len(fixtures.CATALOG), 6)


def server(*, status=200, usage=None, finish="stop", reasoning=True, reject_schema=False, hits=None):
    """Server giả của Groq: trả nội dung và suy luận mang dấu mốc; ghi lại số request."""
    def handler(request: httpx.Request) -> httpx.Response:
        if hits is not None:
            hits.append(request)
        body = json.loads(request.content)
        if request.headers["authorization"].startswith("Bearer gsk_KHOA_GIA"):
            return httpx.Response(401, json=ERROR_BODY)
        if body["model"] == "openai/model-khong-ton-tai":
            return httpx.Response(404, json={"error": {"message": f"The model does not exist. org_01hxyz9abc23defghijk4567 {KEY}", "type": "invalid_request_error", "code": "model_not_found"}})
        if body.get("reasoning_effort") == "extreme" or body.get("response_format", {}).get("json_schema", {}).get("schema", {}).get("type") == "text":
            return httpx.Response(400, json={"error": {"message": "bad param req_01kabcde12345fghijklmnop", "type": "invalid_request_error", "code": "invalid_value"}})
        if reject_schema and body.get("response_format"):
            return httpx.Response(400, json={"error": {"message": "unsupported keyword", "type": "invalid_request_error", "code": "invalid_json_schema"}})
        message = {"role": "assistant", "content": json.dumps({"intent": "WORK_CONFIRMATION", "secondary_intent": None, "confidence": "high", "retrieval_query": None, "note": CONTENT_MARK})}
        if reasoning and not body.get("include_reasoning") is False and body.get("reasoning_format") != "hidden":
            message["reasoning"] = REASON_MARK
        return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": finish}], "usage": usage or {
            "prompt_tokens": 1800, "completion_tokens": 120, "completion_tokens_details": {"reasoning_tokens": 80}}}, headers={"x-ratelimit-remaining-tokens": "5000"})
    return httpx.MockTransport(handler)


class ChongChayNham(unittest.TestCase):
    def test_tool_khong_doc_env_hay_file_nao_de_tim_khoa(self):  # PO, 2026-10-05
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".env").write_text(f"BO19_LLM_API_KEY={KEY}" + chr(10), encoding="utf-8")
            old = llm_probe.REPO
            llm_probe.REPO = Path(d)  # thư mục gốc giả có `.env` chứa khoá
            try:
                self.assertIsNone(llm_probe.read_key())  # không có biến môi trường → không có khoá, dù `.env` có
            finally:
                llm_probe.REPO = old
        src = (TOOL / "llm_probe.py").read_text(encoding="utf-8")
        self.assertNotIn("read_text(", src.split("def read_key")[1].split("def main")[0])  # read_key không đọc file
        self.assertNotIn('REPO / ".env"', src)

    def test_khoa_chi_tu_bien_moi_truong(self):
        from unittest import mock
        with mock.patch.dict("os.environ", {"BO19_LLM_API_KEY": "  gsk_TU_BIEN_MOI_TRUONG  "}):
            self.assertEqual(llm_probe.read_key(), "gsk_TU_BIEN_MOI_TRUONG")
        self.assertIsNone(llm_probe.read_key())  # chốt chặn của bộ test đã xoá khoá


    """Sau lần chạy nhầm ngày 2026-10-05: không có `--confirm-real` thì tool không bao giờ gọi mạng, kể cả khi có khoá."""

    def test_khong_co_co_xac_nhan_thi_khong_goi_mang_va_khong_doc_khoa(self):
        import io
        from contextlib import redirect_stdout
        from unittest import mock
        buf = io.StringIO()
        with mock.patch.object(llm_probe, "read_key", side_effect=AssertionError("không được đọc khoá")), mock.patch.object(llm_probe, "Probe", side_effect=AssertionError("không được dựng Probe")),                 redirect_stdout(buf):
            code = llm_probe.main([])
        self.assertEqual(code, 3)
        self.assertIn("KHÔNG gọi mạng", buf.getvalue())
        self.assertNotIn("gsk_", buf.getvalue())

    def test_prior_calls_tru_khoi_han_muc(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            llm_probe.main(["--prior-calls", "9"])
        self.assertIn("hạn_mức_còn=31", buf.getvalue())

    def test_probe_ton_trong_max_calls(self):
        p = llm_probe.Probe(KEY, "https://llm.example.test/v1", transport=server(), pace=False, max_calls=3)
        with self.assertRaises(llm_probe.Budget):
            for _ in range(5):
                p.raw("x", "openai/gpt-oss-20b", [{"role": "user", "content": "ping (giả)"}], None, {}, expected_tokens=10)
        self.assertEqual(len(p.calls), 3)


class ChayThuVoiServerGia(unittest.TestCase):
    def probe(self, **kw):
        return llm_probe.Probe(KEY, "https://llm.example.test/openai/v1", transport=server(**kw), pace=False)

    def run_all(self, p):
        for fn in (p.e1_o1_1, p.e2_o1_3, p.e3_a089, p.e4_cap, p.e5_a091, p.e6_reasoning_off):
            fn()

    def test_chay_het_trong_han_muc_40_loi_goi(self):
        p = self.probe()
        self.run_all(p)
        self.assertLessEqual(len(p.calls), 40)
        self.assertGreaterEqual(len(p.calls), 25)

    def test_chi_ghi_so_va_ma_khong_ghi_noi_dung_hay_suy_luan(self):
        p = self.probe()
        self.run_all(p)
        results = json.dumps({"calls": [c.__dict__ for c in p.calls], "o1_3": llm_probe.suggest_o1_3(p.calls)}, ensure_ascii=False)
        for mark in (CONTENT_MARK, REASON_MARK):
            self.assertNotIn(mark, results)
        self.assertTrue(any(c.has_reasoning_field for c in p.calls))  # nhưng biết có trường suy luận hay không — chỉ cờ
        self.assertTrue(all(c.reasoning_field_chars_bucket in (None, "<=200", "rỗng", ">200", "không phải chuỗi") for c in p.calls))
        for call in p.calls:
            self.assertFalse({"content", "message", "reasoning", "text"} & set(call.__dict__))  # không có trường nào cho nội dung

    def test_noi_dung_khong_vao_ca_o_cac_thi_nghiem_e3_e4_e6(self):
        p = self.probe(reject_schema=True)  # ép E3 tách từng từ khoá
        self.run_all(p)
        self.assertTrue(any(c.label.startswith("E3") for c in p.calls))
        blob = json.dumps([c.__dict__ for c in p.calls], ensure_ascii=False)
        self.assertNotIn(CONTENT_MARK, blob)
        self.assertNotIn(REASON_MARK, blob)

    def test_e3_chi_chay_khi_co_400_o_e1_e2(self):
        p = self.probe()
        self.run_all(p)
        self.assertFalse(any(c.label.startswith("E3") for c in p.calls))

    def test_gui_di_tran_output_va_tham_so_tuong_minh_cua_hoso(self):
        hits: list[httpx.Request] = []
        p = self.probe(hits=hits)
        p.e1_o1_1(2)
        body = json.loads(hits[0].content)
        self.assertEqual((body["model"], body["reasoning_effort"], body["temperature"], body["max_completion_tokens"]), ("openai/gpt-oss-20b", "low", 0.2, 512))
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertNotIn("max_tokens", body)
        msgs = json.dumps(body["messages"], ensure_ascii=False)
        self.assertIn("(giả)", msgs)

    def test_han_muc_so_loi_goi(self):
        p = self.probe(usage={"prompt_tokens": 10, "completion_tokens": 5, "completion_tokens_details": {"reasoning_tokens": 0}})
        with self.assertRaises(llm_probe.Budget):
            for _ in range(41):
                p.raw("x", "openai/gpt-oss-20b", [{"role": "user", "content": "ping (giả)"}], None, {}, expected_tokens=10)
        self.assertEqual(len(p.calls), 40)

    def test_han_muc_token_moi_model(self):
        big = {"prompt_tokens": 30_000, "completion_tokens": 100, "completion_tokens_details": {"reasoning_tokens": 0}}
        p = self.probe(usage=big)
        with self.assertRaises(llm_probe.Budget):
            for _ in range(10):
                p.raw("x", "openai/gpt-oss-20b", [{"role": "user", "content": "ping (giả)"}], None, {}, expected_tokens=10)
        self.assertEqual(len(p.calls), 2)  # 60.200 ≥ 60.000 sau hai lời gọi
        self.assertGreaterEqual(p.spent["openai/gpt-oss-20b"], llm_probe.MAX_TOKENS_PER_MODEL)

    def test_e4_gui_tran_nho_va_ghi_finish_reason(self):
        hits: list[httpx.Request] = []
        p = self.probe(hits=hits, finish="length")
        p.e4_cap()
        caps = sorted(json.loads(h.content)["max_completion_tokens"] for h in hits)
        self.assertEqual(caps, [48, 48, 64, 128, 256])
        self.assertTrue(all(c.finish_reason == "length" for c in p.calls))

    def test_e6_thu_hai_tham_so_tat_suy_luan_cho_ca_hai_tier(self):
        hits: list[httpx.Request] = []
        p = self.probe(hits=hits)
        p.e6_reasoning_off()
        bodies = [json.loads(h.content) for h in hits]
        self.assertEqual(sum(1 for b in bodies if b.get("include_reasoning") is False), 2)
        self.assertEqual(sum(1 for b in bodies if b.get("reasoning_format") == "hidden"), 2)
        by_label = {c.label: c for c in p.calls}
        self.assertTrue(by_label["E6-CHEAP-mac-dinh"].has_reasoning_field)
        self.assertFalse(by_label["E6-CHEAP-include_reasoning-false"].has_reasoning_field)  # server giả: tham số tắt được suy luận

    def test_publish_che_dinh_danh_va_self_check_dat(self):
        p = self.probe()
        self.run_all(p)
        with tempfile.TemporaryDirectory() as d:
            old = llm_probe.REFERENCE
            llm_probe.REFERENCE = Path(d) / "ref.md"
            try:
                ok, problems = llm_probe.publish(p, [KEY])
                text = llm_probe.REFERENCE.read_text(encoding="utf-8")
            finally:
                llm_probe.REFERENCE = old
        self.assertEqual((ok, problems), (True, []))
        for needle in (KEY, KEY[:8], "org_01hxyz9abc23defghijk4567", "req_01kabcde12345fghijklmnop", "203.0.113.9", "a.b@example.com", "123e4567-e89b-12d3-a456-426614174000",
                       CONTENT_MARK, REASON_MARK):
            self.assertNotIn(needle, text, needle)
        self.assertIn("<masked>", text)
        self.assertIn("invalid_api_key", text)  # mã lỗi giữ lại — đó là thứ cần ghi

    def test_publish_khong_ghi_file_khi_self_check_khong_dat(self):
        p = self.probe()
        self.run_all(p)
        p.masked_errors.append({"label": "x", "status": 400, "body": "Request ID: req_01kabcde12345fghijklmnop chưa che"})  # giả lập lỗi che sót
        with tempfile.TemporaryDirectory() as d:
            old = llm_probe.REFERENCE
            llm_probe.REFERENCE = Path(d) / "ref.md"
            try:
                ok, problems = llm_probe.publish(p, [KEY])
                exists = llm_probe.REFERENCE.exists()
            finally:
                llm_probe.REFERENCE = old
        self.assertFalse(ok)
        self.assertIn("PREFIXED_ID", problems)
        self.assertFalse(exists)  # không đạt thì không ghi

    def test_khoa_khong_xuat_hien_trong_ket_qua_hay_nhan(self):
        p = self.probe()
        self.run_all(p)
        blob = json.dumps([c.__dict__ for c in p.calls], ensure_ascii=False) + json.dumps(p.spent)
        self.assertNotIn(KEY, blob)
        self.assertNotIn(KEY[:8], blob)
        self.assertEqual(sanitize.self_check(blob, [KEY]), [])

    def test_goi_y_o1_3(self):
        def call(label, comp, reas, vis):
            return llm_probe.Call(label, "m", 200, completion_tokens=comp, reasoning_tokens=reas, visible_tokens=vis)
        gom = [call("E2-a-1", 150, 100, 50), call("E2-a-2", 220, 120, 100)]
        chua = [call("E2-a-1", 50, 100, 50), call("E2-a-2", 100, 120, 100)]
        self.assertEqual(llm_probe.suggest_o1_3(gom)["gợi_ý"], "ĐÃ GỒM reasoning")
        self.assertEqual(llm_probe.suggest_o1_3(chua)["gợi_ý"], "CHƯA GỒM reasoning")
        self.assertEqual(llm_probe.suggest_o1_3([])["gợi_ý"], "KHÔNG ĐO ĐƯỢC")
        self.assertEqual(llm_probe.suggest_o1_3([call("E2-a-1", 150, 100, 50), call("E2-a-2", 50, 100, 50)])["gợi_ý"], "KHÔNG RÕ / LẪN LỘN")


if __name__ == "__main__":
    unittest.main()
