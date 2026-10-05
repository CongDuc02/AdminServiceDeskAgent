"""Adapter provider `httpx` — B4. Dạng request, đọc `usage`, lỗi HTTP, và ba yêu cầu của PO (2026-10-05) có test và có trong phép thử đột biến:

  1. lỗi provider chỉ log mã HTTP, loại lỗi và code; response lỗi chứa chuỗi RES giả không làm chuỗi đó lộ ra log hay lỗi trả lên;
  2. hạn chót tổng cho mỗi lời gọi — bao cả retry và chờ `retry-after`; một transport nhỏ giọt từng byte bị cắt ở hạn chót tổng;
  3. khoá `BO19_LLM_API_KEY` không xuất hiện trong log, lỗi hay `repr` của object nào, kể cả khi provider trả 401.

Không có lời gọi mạng nào: mọi response đến từ `httpx.MockTransport`. Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_provider_adapter -v
"""
from __future__ import annotations

import asyncio
import copy
import io
import json
import logging
import pickle
import time
import traceback
import unittest
from typing import Any

import httpx

from bo19.ai_gateway.providers import CALL_FAILED, RATE_LIMITED, ProviderClient, ProviderError
from bo19.ai_gateway.routing.profiles import ModelProfile
from bo19.config import working_values as wv
from bo19.observability.log import configure_logging

KEY = "KHOA_API_KHONG_DUOC_LOT_RA_9f3a7c1e"
RES = "GIA_TRI_RES_GIA_079123456789_KHONG_DUOC_LOT_RA"
CHEAP = ModelProfile("CHEAP", "openai/gpt-oss-20b", {"reasoning_effort": "low"})
STRONG = ModelProfile("STRONG", "openai/gpt-oss-120b", {})
SCHEMA = {"type": "object", "additionalProperties": False, "properties": {"a": {"type": "string"}}, "required": ["a"]}
MESSAGES = [{"role": "system", "content": "chỉ dẫn"}, {"role": "user", "content": "dữ liệu"}]
OK_BODY = {"id": "x", "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"a":"b"}'}, "finish_reason": "stop"}],
           "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150, "prompt_time": 0.01, "completion_time": 0.25,
                     "completion_tokens_details": {"reasoning_tokens": 12}}}


def ok(body: dict | None = None) -> httpx.Response:
    return httpx.Response(200, json=body or OK_BODY)


class Recorder:
    """Transport giả ghi lại request và trả lần lượt các response (hoặc ném lỗi) đã dựng sẵn."""

    def __init__(self, *script: Any) -> None:
        self.script, self.requests = list(script), []
        self.transport = httpx.MockTransport(self.handle)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return await step() if callable(step) else step


class Drip(httpx.AsyncByteStream):
    """Gửi từng byte một, mỗi byte cách nhau `gap` giây: không một pha đọc nào quá `gap`, nhưng cả thân mất rất lâu."""

    def __init__(self, data: bytes, gap: float, size: int = 1) -> None:
        self.data, self.gap, self.size = data, gap, size

    async def __aiter__(self):
        for i in range(0, len(self.data), self.size):
            await asyncio.sleep(self.gap)
            yield self.data[i:i + self.size]


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.out = io.StringIO()
        h = configure_logging(self.out, logging.DEBUG)
        self.addCleanup(logging.getLogger().removeHandler, h)
        self.addCleanup(setattr, wv, "LLM_RETRY_PAUSE_SECONDS", wv.LLM_RETRY_PAUSE_SECONDS)
        wv.LLM_RETRY_PAUSE_SECONDS = 0.01  # test không chờ 1 s thật

    def client(self, rec: Recorder, key: str | None = KEY, base_url: str = "https://llm.example.test/openai/v1") -> ProviderClient:
        return ProviderClient(base_url=base_url, api_key=key, transport=rec.transport)

    async def call(self, c: ProviderClient, deadline: float = 5, profile: ModelProfile = CHEAP, **kw):
        return await c.call(profile=profile, messages=MESSAGES, schema_name="classify_intent", schema=SCHEMA, total_deadline_s=deadline, **kw)

    def assertNoLeak(self, needle: str, *things: Any):
        for t in things:
            self.assertNotIn(needle, repr(t))
            self.assertNotIn(needle, str(t))
        self.assertNotIn(needle, self.out.getvalue())


class DangRequest(Base):
    async def test_url_header_va_than_theo_nguon_goc(self):
        rec = Recorder(ok())
        await self.call(self.client(rec), profile=CHEAP)
        (req,) = rec.requests
        self.assertEqual((req.method, str(req.url)), ("POST", "https://llm.example.test/openai/v1/chat/completions"))
        self.assertEqual(req.headers["authorization"], f"Bearer {KEY}")
        self.assertEqual(req.headers["content-type"], "application/json")
        body = json.loads(req.content)
        self.assertEqual(body["model"], "openai/gpt-oss-20b")
        self.assertIs(body["stream"], False)  # structured outputs không dùng chung với streaming
        self.assertEqual(body["response_format"], {"type": "json_schema", "json_schema": {"name": "classify_intent", "strict": True, "schema": SCHEMA}})
        self.assertEqual(body["reasoning_effort"], "low")  # hồ sơ model tier rẻ — chỉ đạo của PO
        self.assertEqual(body["messages"], MESSAGES)

    async def test_khong_bao_gio_gui_truong_provider_tu_choi_hay_tham_so_chua_duyet(self):
        rec = Recorder(ok())
        await self.call(self.client(rec), profile=STRONG)
        body = json.loads(rec.requests[0].content)
        for banned in ("logprobs", "logit_bias", "top_logprobs", "n", "temperature", "reasoning_effort", "max_tokens", "max_completion_tokens", "stream_options"):
            self.assertNotIn(banned, body)  # `n` mặc định 1; temperature không đặt (A-090); tier mạnh chưa có reasoning_effort
        for m in body["messages"]:
            self.assertEqual(set(m), {"role", "content"})  # không `messages[].name`

    async def test_base_url_co_dau_gach_cuoi(self):
        rec = Recorder(ok())
        await self.call(self.client(rec, base_url="https://llm.example.test/v1/"))
        self.assertEqual(str(rec.requests[0].url), "https://llm.example.test/v1/chat/completions")

    async def test_khong_theo_redirect_va_khong_doc_proxy_tu_moi_truong(self):
        rec = Recorder(httpx.Response(302, headers={"location": "https://khac.example.test/"}))
        with self.assertRaises(ProviderError) as cm:
            await self.call(self.client(rec))
        self.assertEqual((cm.exception.subcode, cm.exception.http_status), (CALL_FAILED, 302))
        self.assertEqual(len(rec.requests), 1)  # không đi theo chuyển hướng — khoá Authorization không bị gửi sang host khác


class DocPhanHoi(Base):
    async def test_noi_dung_va_usage_day_du(self):
        r = await self.call(self.client(Recorder(ok())))
        self.assertEqual((r.content, r.prompt_tokens, r.completion_tokens, r.reasoning_tokens, r.prompt_time, r.completion_time), ('{"a":"b"}', 120, 30, 12, 0.01, 0.25))

    async def test_truong_usage_khong_co_thi_de_trong_khong_suy_ra(self):  # ADR-035: không suy ra
        body = {"choices": OK_BODY["choices"], "usage": {"prompt_tokens": 5}}
        r = await self.call(self.client(Recorder(ok(body))))
        self.assertEqual((r.prompt_tokens, r.completion_tokens, r.reasoning_tokens, r.prompt_time, r.completion_time), (5, None, None, None, None))
        r = await self.call(self.client(Recorder(ok({"choices": OK_BODY["choices"]}))))
        self.assertEqual((r.prompt_tokens, r.completion_tokens, r.reasoning_tokens), (None, None, None))

    async def test_completion_tokens_details_null_hoac_sai_kieu(self):
        for details in (None, "x", [], {"reasoning_tokens": "12"}, {"reasoning_tokens": True}, {"reasoning_tokens": -1}):
            body = {**OK_BODY, "usage": {**OK_BODY["usage"], "completion_tokens_details": details}}
            self.assertIsNone((await self.call(self.client(Recorder(ok(body))))).reasoning_tokens, repr(details))

    async def test_than_200_hong_la_bad_response_khong_thu_lai(self):
        for body in ({"choices": []}, {"choices": [{"message": {}}]}, {"choices": [{"message": {"content": 5}}]}, {"khong": "co"}, [], "x"):
            rec = Recorder(httpx.Response(200, json=body))
            with self.assertRaises(ProviderError) as cm:
                await self.call(self.client(rec))
            self.assertEqual((cm.exception.subcode, cm.exception.kind), (CALL_FAILED, "BAD_RESPONSE"), body)
            self.assertEqual(len(rec.requests), 1)
        with self.assertRaises(ProviderError) as cm:
            await self.call(self.client(Recorder(httpx.Response(200, content=b"khong phai json {"))))
        self.assertEqual(cm.exception.kind, "BAD_RESPONSE")

    async def test_response_qua_lon_bi_cat(self):
        big = httpx.Response(200, content=b"x" * 2_000_000)
        with self.assertRaises(ProviderError) as cm:
            await self.call(self.client(Recorder(big)))
        self.assertEqual(cm.exception.kind, "BAD_RESPONSE")


class LoiHttpVaThuLai(Base):
    async def test_400_va_401_khong_thu_lai(self):
        for status in (400, 401, 403, 404, 422):
            rec = Recorder(httpx.Response(status, json={"error": {"type": "invalid_request_error", "code": "bad"}}))
            with self.assertRaises(ProviderError) as cm:
                await self.call(self.client(rec))
            e = cm.exception
            self.assertEqual((e.subcode, e.kind, e.http_status, e.error_type, e.error_code, e.attempts), (CALL_FAILED, "HTTP_STATUS", status, "invalid_request_error", "bad", 1))
            self.assertEqual(len(rec.requests), 1, status)

    async def test_5xx_thu_lai_dung_mot_lan_roi_thanh_cong(self):
        for status in (500, 502, 503, 504):
            rec = Recorder(httpx.Response(status), ok())
            self.assertEqual((await self.call(self.client(rec))).completion_tokens, 30)
            self.assertEqual(len(rec.requests), 2, status)

    async def test_hai_lan_5xx_thi_dung_o_hai_lan(self):
        rec = Recorder(httpx.Response(503, json={"error": {"type": "overloaded", "code": "busy"}}))
        with self.assertRaises(ProviderError) as cm:
            await self.call(self.client(rec))
        self.assertEqual((cm.exception.http_status, cm.exception.attempts, len(rec.requests)), (503, 2, 2))  # WV-05: tổng hai lần gọi

    async def test_dut_ket_noi_la_thoang_qua(self):
        rec = Recorder(httpx.ConnectError("khong noi duoc"), ok())
        self.assertEqual((await self.call(self.client(rec))).prompt_tokens, 120)
        rec = Recorder(httpx.ConnectError(f"loi co {RES}"))
        with self.assertRaises(ProviderError) as cm:
            await self.call(self.client(rec))
        self.assertEqual((cm.exception.subcode, cm.exception.kind, cm.exception.http_status, cm.exception.attempts), (CALL_FAILED, "CONNECTION", None, 2))
        self.assertNoLeak(RES, cm.exception, "".join(traceback.format_exception(cm.exception)))

    async def test_429_khong_retry_after_thu_lai_sau_quang_nghi(self):
        rec = Recorder(httpx.Response(429), ok())
        await self.call(self.client(rec))
        self.assertEqual(len(rec.requests), 2)

    async def test_429_lan_hai_la_rate_limited(self):
        rec = Recorder(httpx.Response(429, headers={"retry-after": "0"}))
        with self.assertRaises(ProviderError) as cm:
            await self.call(self.client(rec))
        self.assertEqual((cm.exception.subcode, cm.exception.http_status, cm.exception.retry_after_seconds, cm.exception.attempts), (RATE_LIMITED, 429, 0, 2))

    async def test_retry_after_khong_hop_le_bi_bo(self):
        for raw in ("abc", "-3", "1.5", "99999999", ""):
            rec = Recorder(httpx.Response(429, headers={"retry-after": raw}), ok())
            await self.call(self.client(rec))  # dùng quãng nghỉ thường, không chờ lâu
            self.assertEqual(len(rec.requests), 2, raw)


class HanChotTong(Base):
    """Yêu cầu của PO: hạn chót tổng bao cả retry và chờ retry-after; không dựa vào timeout từng pha của httpx."""

    def drip_ok(self, gap: float, size: int = 1):
        data = json.dumps(OK_BODY).encode()
        return httpx.Response(200, stream=Drip(data, gap, size))

    async def test_transport_nho_giot_tung_byte_bi_cat_o_han_chot_tong(self):
        rec = Recorder(self.drip_ok(0.01))  # ~ 280 byte × 0.01 s ≈ 2.8 s nếu để chạy hết; mỗi pha đọc chỉ 0.01 s nên timeout từng pha không bao giờ chạm
        t = time.monotonic()
        with self.assertRaises(ProviderError) as cm:
            await self.call(self.client(rec), deadline=0.3)
        elapsed = time.monotonic() - t
        self.assertEqual((cm.exception.subcode, cm.exception.kind, cm.exception.http_status), (CALL_FAILED, "DEADLINE", None))
        self.assertLess(elapsed, 0.7, elapsed)
        self.assertGreaterEqual(elapsed, 0.28)

    async def test_nho_giot_ma_du_thoi_gian_thi_van_thanh_cong(self):  # đối chứng: cùng transport, hạn chót đủ dài
        r = await self.call(self.client(Recorder(self.drip_ok(0.01, size=64))), deadline=5)  # sáu mảnh, vài chục ms
        self.assertEqual(r.completion_tokens, 30)

    async def test_treo_sau_header_khong_gui_byte_nao(self):
        async def stall():
            await asyncio.sleep(10)
            return ok()
        t = time.monotonic()
        with self.assertRaises(ProviderError) as cm:
            await self.call(self.client(Recorder(stall)), deadline=0.3)
        self.assertEqual(cm.exception.kind, "DEADLINE")
        self.assertLess(time.monotonic() - t, 0.7)

    async def test_han_chot_bao_ca_lan_thu_lai(self):
        rec = Recorder(httpx.Response(500), self.drip_ok(0.01))  # lần một 500 ngay, lần hai nhỏ giọt
        t = time.monotonic()
        with self.assertRaises(ProviderError) as cm:
            await self.call(self.client(rec), deadline=0.4)
        self.assertEqual(cm.exception.kind, "DEADLINE")
        self.assertEqual(len(rec.requests), 2)  # đã thử lại
        self.assertLess(time.monotonic() - t, 0.8)  # nhưng tổng vẫn bị chặn ở hạn chót, không phải mỗi lần thử một hạn

    async def test_han_chot_bao_ca_quang_nghi_va_chi_thu_lai_khi_con_thoi_gian(self):
        wv.LLM_RETRY_PAUSE_SECONDS = 0.5
        rec = Recorder(httpx.Response(500))
        t = time.monotonic()
        with self.assertRaises(ProviderError) as cm:
            await self.call(self.client(rec), deadline=0.3)  # nghỉ 0.5 s không vừa trong 0.3 s → không thử lại
        self.assertEqual((cm.exception.http_status, cm.exception.attempts, len(rec.requests)), (500, 1, 1))
        self.assertLess(time.monotonic() - t, 0.2)

    async def test_retry_after_lon_hon_thoi_gian_con_lai_thi_khong_cho(self):
        rec = Recorder(httpx.Response(429, headers={"retry-after": "30"}), ok())
        t = time.monotonic()
        with self.assertRaises(ProviderError) as cm:
            await self.call(self.client(rec), deadline=2)
        e = cm.exception
        self.assertEqual((e.subcode, e.retry_after_seconds, e.attempts, len(rec.requests)), (RATE_LIMITED, 30, 1, 1))
        self.assertLess(time.monotonic() - t, 0.5)  # trả lỗi ngay, không ngủ 30 s

    async def test_retry_after_nho_hon_thi_cho_roi_thu_lai(self):
        rec = Recorder(httpx.Response(429, headers={"retry-after": "1"}), ok())
        t = time.monotonic()
        r = await self.call(self.client(rec), deadline=4)
        self.assertEqual((r.completion_tokens, len(rec.requests)), (30, 2))
        self.assertGreaterEqual(time.monotonic() - t, 0.95)  # đã chờ theo retry-after, và đó là lần thử lại duy nhất

    async def test_tran_retry_after_cua_job_wv19(self):
        self.assertEqual(wv.LLM_RETRY_AFTER_CEILING_SECONDS, 120)
        rec = Recorder(httpx.Response(429, headers={"retry-after": "5"}), ok())
        with self.assertRaises(ProviderError) as cm:
            await self.call(self.client(rec), deadline=60, retry_after_cap_s=2)  # trần của job nhỏ hơn retry-after: không chờ dù hạn chót còn dài
        self.assertEqual((cm.exception.subcode, cm.exception.retry_after_seconds, len(rec.requests)), (RATE_LIMITED, 5, 1))

    async def test_gia_tri_wv04_wv06(self):
        self.assertEqual((wv.LLM_CALL_DEADLINE_CHEAP_SECONDS, wv.LLM_CALL_DEADLINE_STRONG_SECONDS, wv.LLM_RETRY_COUNT), (8, 60, 1))


class LoiKhongLoThanThô(Base):
    """Yêu cầu của PO: response lỗi chứa chuỗi RES giả không làm chuỗi đó xuất hiện trong log hay trong lỗi trả lên."""

    def bodies(self):
        trich = f"This model's maximum context length was exceeded. Your input was: {RES}"
        return {
            "message trích input": {"error": {"message": trich, "type": "invalid_request_error", "code": "context_length_exceeded"}},
            "failed_generation": {"error": {"message": "x", "type": "invalid_request_error", "code": "json_validate_failed", "failed_generation": RES}},
            "type và code chứa RES (không khớp khuôn)": {"error": {"message": "x", "type": f"{RES} có khoảng trắng", "code": f"{RES}!"}},
            "trường lạ ở gốc": {"input_echo": RES, "error": {"type": "t", "code": "c"}},
            "error là chuỗi": {"error": RES},
            "mảng lồng": {"error": {"type": ["a", RES], "code": {"x": RES}}},
        }

    async def test_moi_dang_than_loi_chua_res_khong_lo_ra_loi_hay_log(self):
        for status in (400, 401, 422, 429, 500, 503):
            for name, body in self.bodies().items():
                self.out.truncate(0), self.out.seek(0)
                rec = Recorder(httpx.Response(status, json=body))
                with self.assertRaises(ProviderError) as cm:
                    await self.call(self.client(rec))
                e = cm.exception
                text = "".join(traceback.format_exception(e))
                self.assertNoLeak(RES, e, e.__dict__, e.log_fields(), text, e.args)
                self.assertIsNone(e.__cause__)
                self.assertTrue(e.__context__ is None or e.__suppress_context__)  # không có chuỗi nguyên nhân nào đi kèm

    async def test_chi_giu_loai_loi_va_code_khop_khuon(self):
        e = await self.fail_with(httpx.Response(400, json=self.bodies()["message trích input"]))
        self.assertEqual((e.http_status, e.error_type, e.error_code), (400, "invalid_request_error", "context_length_exceeded"))
        for name in ("type và code chứa RES (không khớp khuôn)", "error là chuỗi", "mảng lồng", "trường lạ ở gốc"):
            e = await self.fail_with(httpx.Response(400, json=self.bodies()[name]))
            self.assertEqual(e.http_status, 400)
            if name == "trường lạ ở gốc":
                self.assertEqual((e.error_type, e.error_code), ("t", "c"))
            else:
                self.assertEqual((e.error_type, e.error_code), (None, None), name)

    async def test_code_so_nguyen_duoc_doi_thanh_chuoi_ngan(self):
        e = await self.fail_with(httpx.Response(400, json={"error": {"type": "x", "code": 4001}}))
        self.assertEqual(e.error_code, "4001")

    async def test_than_khong_phai_json_hoac_cat_cut_va_html_echo_input(self):
        for raw in (f"<html>{RES}</html>".encode(), b"", b"\xff\xfe" + RES.encode(), ('{"error":{"type":"a","code":"b","message":"' + RES * 4000).encode()):
            e = await self.fail_with(httpx.Response(400, content=raw))
            self.assertEqual((e.http_status, e.error_type, e.error_code), (400, None, None))
            self.assertNoLeak(RES, e, e.__dict__, "".join(traceback.format_exception(e)))

    async def test_gateway_ghi_log_chi_ba_truong(self):
        e = await self.fail_with(httpx.Response(400, json=self.bodies()["message trích input"]))
        self.assertEqual(set(e.log_fields()), {"subcode", "kind", "http_status", "provider_error_type", "provider_error_code", "retry_after_seconds", "attempts"})

    async def test_log_cua_httpx_cua_ban_than_cung_khong_lo(self):
        logging.getLogger("httpx").setLevel(logging.DEBUG)
        logging.getLogger("httpcore").setLevel(logging.DEBUG)
        await self.fail_with(httpx.Response(400, json=self.bodies()["message trích input"]))
        self.assertNotIn(RES, self.out.getvalue())
        self.assertNotIn("example.test", self.out.getvalue())  # handler mask bỏ nội dung log của thư viện bên thứ ba

    async def fail_with(self, response: httpx.Response) -> ProviderError:
        with self.assertRaises(ProviderError) as cm:
            await self.call(self.client(Recorder(response)))
        return cm.exception


class KhoaApi(Base):
    """Yêu cầu của PO: BO19_LLM_API_KEY không xuất hiện trong log, lỗi hay repr của object nào, kể cả khi provider trả 401."""

    def objects(self, c: ProviderClient) -> list[Any]:
        return [c, c.__dict__, c._key, vars(c), dir(c), c.__class__.__dict__.keys()]

    async def test_khong_lo_trong_repr_cua_client_va_cac_vat_dung_quanh(self):
        c = self.client(Recorder(ok()))
        for obj in self.objects(c):
            self.assertNotIn(KEY, repr(obj))
        self.assertNotIn(KEY, str(c))
        self.assertNotIn(KEY, f"{c!r} {c._key} {c._key!r}")

    async def test_khong_tuan_tu_hoa_khong_sao_chep_sau(self):
        c = self.client(Recorder(ok()))
        with self.assertRaises(TypeError):
            pickle.dumps(c._key)
        with self.assertRaises(TypeError):
            copy.deepcopy(c)
        with self.assertRaises(TypeError):
            copy.copy(c._key)

    async def test_khoa_chi_xuat_hien_trong_header_authorization(self):
        rec = Recorder(ok())
        await self.call(self.client(rec))
        (req,) = rec.requests
        self.assertEqual([k for k, v in req.headers.items() if KEY in v], ["authorization"])
        self.assertNotIn(KEY.encode(), req.content)
        self.assertNotIn(KEY, str(req.url))
        self.assertNotIn(KEY, self.out.getvalue())

    async def test_provider_tra_401_ke_ca_khi_than_loi_trich_lai_khoa(self):
        echoes = [{"error": {"message": f"Invalid API Key: {KEY}", "type": "invalid_request_error", "code": "invalid_api_key"}},
                  {"error": f"bad key {KEY}"}, {"detail": KEY}]
        for body in echoes:
            self.out.truncate(0), self.out.seek(0)
            rec = Recorder(httpx.Response(401, json=body, headers={"x-echo": KEY}))
            with self.assertRaises(ProviderError) as cm:
                await self.call(self.client(rec))
            e = cm.exception
            self.assertEqual((e.subcode, e.http_status, e.attempts), (CALL_FAILED, 401, 1))
            self.assertNoLeak(KEY, e, e.__dict__, e.log_fields(), "".join(traceback.format_exception(e)), e.args)
            for obj in self.objects(self.client(rec)):
                self.assertNotIn(KEY, repr(obj))

    async def test_khoa_khong_lo_qua_loi_ket_noi_hay_het_gio(self):
        for script in ([httpx.ConnectError(f"khong noi duoc voi khoa {KEY}")], [httpx.ReadTimeout(f"het gio {KEY}")]):
            with self.assertRaises(ProviderError) as cm:
                await self.call(self.client(Recorder(*script)))
            self.assertNoLeak(KEY, cm.exception, "".join(traceback.format_exception(cm.exception)))

    async def test_khong_co_khoa_thi_khong_goi_mang(self):
        for key in (None, ""):
            rec = Recorder(ok())
            with self.assertRaises(ProviderError) as cm:
                await self.call(self.client(rec, key=key))
            self.assertEqual((cm.exception.subcode, cm.exception.kind, cm.exception.attempts, len(rec.requests)), (CALL_FAILED, "NO_API_KEY", 0, 0))


if __name__ == "__main__":
    unittest.main()
