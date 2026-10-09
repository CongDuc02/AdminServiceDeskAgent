"""`ai_gateway.json_contract` — validate phía client, dựng schema lúc gọi (ADR-025), điều kiện `strict` của Groq. B4.

Chạy từ backend/:  PYTHONPATH=src python -m unittest tests.test_json_contract -v
"""
from __future__ import annotations

from tests import _guard  # noqa: F401 — chốt chặn mạng và khoá API của bộ test (tests/_guard.py)

import json
import unittest

from bo19.ai_gateway.json_contract import schemas
from bo19.ai_gateway.json_contract.validator import UnsupportedSchema, Violation, assert_supported, validate

SECRET = "GIA_TRI_RES_KHONG_DUOC_LOT_RA"
CATALOG = [
    {"code": "WORK_CONFIRMATION", "support_status": "SUPPORTED", "name_vi": "Xác nhận công tác", "description": "d", "example_phrases": ["xin giấy xác nhận"]},
    {"code": "INTRODUCTION_LETTER", "support_status": "SUPPORTED", "name_vi": "Giấy giới thiệu", "description": "d", "example_phrases": ["xin giấy giới thiệu"]},
    {"code": "ROOM_BOOKING", "support_status": "KNOWN_UNSUPPORTED", "name_vi": "Đặt phòng", "description": "d", "example_phrases": ["đặt phòng họp"]},
]


class Validator(unittest.TestCase):
    def test_kieu(self):
        for schema, good, bad in (({"type": "string"}, "a", 1), ({"type": "integer"}, 3, 3.5), ({"type": "integer"}, 3, True), ({"type": "number"}, 2.5, "x"),
                                  ({"type": "boolean"}, False, 0), ({"type": "null"}, None, ""), ({"type": "array"}, [], {}), ({"type": "object"}, {}, []),
                                  ({"type": ["string", "null"]}, None, 1)):
            self.assertEqual(validate(schema, good), [], schema)
            self.assertEqual(validate(schema, bad), [Violation("$", "TYPE")], (schema, bad))

    def test_enum_va_const_khong_nham_bool_voi_so(self):
        self.assertEqual(validate({"enum": ["a", None]}, None), [])
        self.assertEqual(validate({"enum": ["a"]}, "b"), [Violation("$", "ENUM")])
        self.assertEqual(validate({"enum": [1]}, True), [Violation("$", "ENUM")])
        self.assertEqual(validate({"const": "x"}, "y"), [Violation("$", "CONST")])
        self.assertEqual(validate({"const": 1}, True), [Violation("$", "CONST")])

    def test_do_dai_chuoi_va_mang(self):
        self.assertEqual(validate({"type": "string", "minLength": 2, "maxLength": 3}, "a"), [Violation("$", "MIN_LENGTH")])
        self.assertEqual(validate({"type": "string", "minLength": 2, "maxLength": 3}, "abcd"), [Violation("$", "MAX_LENGTH")])
        self.assertEqual(validate({"type": "string", "maxLength": 3}, "đặc"), [])  # đếm ký tự, không đếm byte
        self.assertEqual(validate({"type": "array", "minItems": 2}, [1]), [Violation("$", "MIN_ITEMS")])
        self.assertEqual(validate({"type": "array", "maxItems": 1}, [1, 2]), [Violation("$", "MAX_ITEMS")])

    def test_doi_tuong_dong(self):
        schema = {"type": "object", "additionalProperties": False, "properties": {"a": {"type": "string"}}, "required": ["a"]}
        self.assertEqual(validate(schema, {"a": "x"}), [])
        self.assertEqual(validate(schema, {}), [Violation("a", "REQUIRED")])
        self.assertEqual(validate(schema, {"a": "x", SECRET: 1}), [Violation("<trường lạ>", "EXTRA")])  # không ghi tên trường: do model đặt

    def test_duong_dan_long_nhau_chi_co_ten_va_chi_so(self):
        schema = schemas.extract_slots_schema()
        v = validate(schema, {"slots": [{"slot_name": "x", "value": "v", "evidence_span": [1], "evidence_quote": "q"}]})
        self.assertEqual(v, [Violation("slots[0].evidence_span", "MIN_ITEMS")])

    def test_ket_qua_khong_bao_gio_mang_gia_tri(self):
        schema = {"type": "object", "additionalProperties": False, "properties": {"a": {"type": "string", "maxLength": 3}, "b": {"enum": ["x"]}}, "required": ["a", "b"]}
        for value in ({"a": SECRET, "b": SECRET, SECRET: SECRET}, {"a": [SECRET], "b": {SECRET: 1}}, SECRET, [SECRET]):
            self.assertNotIn(SECRET, repr(validate(schema, value)))

    def test_sai_kieu_thi_dung_o_do(self):
        self.assertEqual(validate({"type": "string", "minLength": 5, "enum": ["abcde"]}, 7), [Violation("$", "TYPE")])

    def test_tu_khoa_la_bi_tu_choi_chu_khong_bi_lo(self):  # fail-closed
        for schema in ({"pattern": "x"}, {"$ref": "#/x"}, {"oneOf": []}, {"format": "date"}, {"minimum": 1}, {"additionalProperties": True},
                       {"type": "text"}, {"type": []}, {"minLength": -1}, {"maxItems": "3"}, {"required": "a"}, {"properties": {"a": {"pattern": "x"}}},
                       {"items": {"uniqueItems": True}}, [], "x"):
            with self.assertRaises(UnsupportedSchema, msg=str(schema)):
                assert_supported(schema)

    def test_chu_thich_duoc_bo_qua(self):
        assert_supported({"$schema": "x", "description": "d", "title": "t", "type": "string"})

    def test_mang_cho_phep_item_hon_hop(self):
        schema = {"type": ["string", "number", "boolean", "null", "array"], "items": {"type": "string", "minLength": 1}}
        self.assertEqual(validate(schema, ["a", "b"]), [])
        self.assertEqual(validate(schema, ["a", ""]), [Violation("[1]", "MIN_LENGTH")])
        self.assertEqual(validate(schema, "chuỗi"), [])  # `items` chỉ áp khi là mảng


class SchemaP1(unittest.TestCase):
    def test_enum_sinh_tu_chinh_catalog(self):
        s = schemas.classify_intent_schema(CATALOG)
        codes = ["WORK_CONFIRMATION", "INTRODUCTION_LETTER", "ROOM_BOOKING"]
        self.assertEqual(s["properties"]["intent"]["enum"], [*codes, "OUT_OF_SCOPE", "NEED_CLARIFICATION"])
        self.assertEqual(s["properties"]["secondary_intent"]["enum"], [*codes, "OUT_OF_SCOPE", None])  # bỏ NEED_CLARIFICATION, cộng null

    def test_loai_them_qua_f6_xuat_hien_trong_enum_khong_sua_ma(self):  # A-075, ADR-025
        extra = {"code": "SEAL_REQUEST", "support_status": "SUPPORTED", "name_vi": "Dấu", "description": "d", "example_phrases": []}
        s = schemas.classify_intent_schema([*CATALOG, extra])
        self.assertIn("SEAL_REQUEST", s["properties"]["intent"]["enum"])
        self.assertEqual(validate(s, {"intent": "SEAL_REQUEST", "secondary_intent": None, "confidence": "high", "retrieval_query": None}), [])

    def test_ma_ngoai_catalog_bi_tu_choi(self):
        s = schemas.classify_intent_schema(CATALOG)
        out = validate(s, {"intent": "MA_LA", "secondary_intent": "NEED_CLARIFICATION", "confidence": "high", "retrieval_query": None})
        self.assertEqual(sorted((v.path, v.code) for v in out), [("intent", "ENUM"), ("secondary_intent", "ENUM")])

    def test_catalog_hong(self):
        bad = [[], [{"code": "A", "support_status": "RETIRED"}], [{"code": "A", "support_status": "SUPPORTED"}, {"code": "A", "support_status": "SUPPORTED"}],
               [{"code": "OUT_OF_SCOPE", "support_status": "SUPPORTED"}], [{"code": 1, "support_status": "SUPPORTED"}], ["x"]]
        for catalog in bad:
            with self.assertRaises(schemas.CatalogInvalid, msg=str(catalog)):
                schemas.classify_intent_schema(catalog)

    def test_vi_du_few_shot_cua_07_prompts_hop_schema(self):
        s = schemas.classify_intent_schema(CATALOG)
        for ex in ('{"intent":"WORK_CONFIRMATION","secondary_intent":null,"confidence":"high","retrieval_query":null}',
                   '{"intent":"INTRODUCTION_LETTER","secondary_intent":"ROOM_BOOKING","confidence":"high","retrieval_query":null}'):
            self.assertEqual(validate(s, json.loads(ex)), [], ex)

    def test_retrieval_query_toi_da_200(self):
        s = schemas.classify_intent_schema(CATALOG)
        base = {"intent": "OUT_OF_SCOPE", "secondary_intent": None, "confidence": "low"}
        self.assertEqual(validate(s, {**base, "retrieval_query": "x" * 200}), [])
        self.assertEqual(validate(s, {**base, "retrieval_query": "x" * 201}), [Violation("retrieval_query", "MAX_LENGTH")])


class SchemaP2P4(unittest.TestCase):
    def test_few_shot_p2_hop_schema(self):
        ex = {"slots": [{"slot_name": "recipient_org", "value": "Công ty ABC", "evidence_span": [8, 19], "evidence_quote": "Công ty ABC"},
                        {"slot_name": "purpose", "value": "bổ sung hồ sơ vay vốn", "evidence_span": [30, 52], "evidence_quote": "bổ sung hồ sơ vay vốn"}]}
        self.assertEqual(validate(schemas.extract_slots_schema(), ex), [])

    def test_p2_toi_da_8_slot_va_quote_300(self):
        s = schemas.extract_slots_schema()
        slot = {"slot_name": "a", "value": None, "evidence_span": [0, 1], "evidence_quote": "q"}
        self.assertEqual(validate(s, {"slots": [slot] * 8}), [])
        self.assertEqual(validate(s, {"slots": [slot] * 9}), [Violation("slots", "MAX_ITEMS")])
        self.assertEqual(validate(s, {"slots": [{**slot, "evidence_quote": "q" * 301}]}), [Violation("slots[0].evidence_quote", "MAX_LENGTH")])

    def test_p4_bien_va_do_dai_sinh_luc_goi(self):
        s = schemas.draft_content_schema("purpose_statement", 120)
        good = {"variable_name": "purpose_statement", "body": "Bổ sung hồ sơ vay vốn tại Ngân hàng X theo yêu cầu của đơn vị tiếp nhận."}
        self.assertEqual(validate(s, good), [])
        self.assertEqual(validate(s, {**good, "variable_name": "work_content_statement"}), [Violation("variable_name", "CONST")])
        self.assertEqual(validate(s, {**good, "body": "ngắn"}), [Violation("body", "MIN_LENGTH")])
        self.assertEqual(validate(s, {**good, "body": "x" * 121}), [Violation("body", "MAX_LENGTH")])
        self.assertEqual(validate(schemas.draft_content_schema("work_content_statement", 500), {**good, "variable_name": "work_content_statement"}), [])


class DieuKienStrict(unittest.TestCase):
    """Groq `strict: true`: mọi property nằm trong `required`, mọi đối tượng đóng (docs/reference/llm-groq.md mục 3)."""

    def walk(self, node, where="$"):
        if isinstance(node, dict):
            if "properties" in node:
                self.assertEqual(sorted(node["required"]), sorted(node["properties"]), where)
                self.assertIs(node.get("additionalProperties"), False, where)
                for k, v in node["properties"].items():
                    self.walk(v, f"{where}.{k}")
            if "items" in node:
                self.walk(node["items"], where + "[]")

    def test_ca_ba_schema(self):
        for s in (schemas.classify_intent_schema(CATALOG), schemas.extract_slots_schema(), schemas.draft_content_schema("v", 50)):
            self.assertEqual(s["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.walk(s)
            assert_supported(s)
            json.dumps(s)  # gửi đi được


if __name__ == "__main__":
    unittest.main()
