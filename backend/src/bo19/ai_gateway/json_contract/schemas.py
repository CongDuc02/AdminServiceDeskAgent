"""Dựng output schema lúc gọi — mục Output contract của 07-prompts.md; ADR-025.

Enum của P1 sinh từ **chính** `request_type_catalog` đã nạp làm input của lời gọi (không có khoảng hở giữa loại model được thấy và loại model được phép trả);
`variable_name` và `maxLength` của P4 sinh từ danh mục biến của đúng phiên bản template. Mọi property nằm trong `required` và `null` nghĩa là "không có" — điều kiện
`strict` của Groq (`docs/reference/llm-groq.md` mục 3), đúng cho mọi nhánh ép JSON.
"""
from __future__ import annotations

from typing import Any

from bo19.ai_gateway.json_contract.validator import assert_supported

DRAFT = "https://json-schema.org/draft/2020-12/schema"
OUT_OF_SCOPE, NEED_CLARIFICATION = "OUT_OF_SCOPE", "NEED_CLARIFICATION"
INTENT_STATUSES = frozenset({"SUPPORTED", "KNOWN_UNSUPPORTED"})


class CatalogInvalid(Exception):
    code = "CATALOG_INVALID"


def intent_codes(catalog: list[dict[str, Any]]) -> list[str]:
    """Mã của loại `SUPPORTED` và `KNOWN_UNSUPPORTED`, giữ thứ tự của catalog."""
    codes: list[str] = []
    for entry in catalog:
        if not isinstance(entry, dict) or not isinstance(entry.get("code"), str) or entry.get("support_status") not in INTENT_STATUSES:
            raise CatalogInvalid
        codes.append(entry["code"])
    if not codes or len(set(codes)) != len(codes) or {OUT_OF_SCOPE, NEED_CLARIFICATION} & set(codes):
        raise CatalogInvalid
    return codes


def classify_intent_schema(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    codes = intent_codes(catalog)
    schema = {
        "$schema": DRAFT,
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "intent": {"type": "string", "enum": [*codes, OUT_OF_SCOPE, NEED_CLARIFICATION]},
            "secondary_intent": {"type": ["string", "null"], "enum": [*codes, OUT_OF_SCOPE, None]},  # bỏ NEED_CLARIFICATION, cộng null
            "confidence": {"type": "string", "enum": ["high", "low"]},
            "retrieval_query": {"type": ["string", "null"], "maxLength": 200},
        },
        "required": ["intent", "secondary_intent", "confidence", "retrieval_query"],
    }
    assert_supported(schema)
    return schema


def extract_slots_schema() -> dict[str, Any]:
    schema = {
        "$schema": DRAFT,
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "slots": {
                "type": "array",
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "slot_name": {"type": "string"},
                        "value": {"type": ["string", "number", "boolean", "null", "array"], "items": {"type": "string", "minLength": 1}},
                        "evidence_span": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                        "evidence_quote": {"type": "string", "maxLength": 300},
                    },
                    "required": ["slot_name", "value", "evidence_span", "evidence_quote"],
                },
            }
        },
        "required": ["slots"],
    }
    assert_supported(schema)
    return schema


def draft_content_schema(variable_name: str, max_length: int) -> dict[str, Any]:
    schema = {
        "$schema": DRAFT,
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "variable_name": {"type": "string", "const": variable_name},  # đúng một biến mỗi lời gọi (ADR-009)
            "body": {"type": "string", "minLength": 10, "maxLength": max_length},
        },
        "required": ["variable_name", "body"],
    }
    assert_supported(schema)
    return schema
