"""Validate JSON phía client theo một tập con JSON Schema — đúng các từ khoá mà `07-prompts.md` dùng (mục Triển khai ở B4 của 06-structure.md).

Không có `jsonschema` trong lock (ADR-030), nên `ai_gateway` tự validate: cả hai nhánh ép JSON đều qua đây (mục Chiến lược ép JSON và xử lý lỗi parse của `07-prompts.md`).

Tập từ khoá: `type`, `enum`, `const`, `properties`, `required`, `additionalProperties` (chỉ `false`), `items`, `minItems`, `maxItems`, `minLength`, `maxLength`.
Từ khoá chú thích (`$schema`, `description`, `title`) được bỏ qua. **Từ khoá lạ làm `assert_supported` ném lỗi** — fail-closed: một từ khoá không hiểu mà bị lờ đi
là một ràng buộc không được thi hành.

Kết quả là danh sách `Violation(path, code)` — đường dẫn tới trường và mã, **không bao giờ mang giá trị**: giá trị có thể là `RES`, và danh sách này đi vào log
và vào lời nhắn sửa parse.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ANNOTATIONS = frozenset({"$schema", "description", "title"})
SUPPORTED = frozenset({"type", "enum", "const", "properties", "required", "additionalProperties", "items", "minItems", "maxItems", "minLength", "maxLength"}) | ANNOTATIONS
TYPES = frozenset({"object", "array", "string", "number", "integer", "boolean", "null"})


class UnsupportedSchema(Exception):
    """Schema dùng từ khoá hay kiểu ngoài tập hỗ trợ. Mang mã, không mang nội dung schema."""

    code = "SCHEMA_UNSUPPORTED"


@dataclass(frozen=True)
class Violation:
    path: str  # ví dụ `slots[0].evidence_span` — chỉ tên trường và chỉ số
    code: str  # TYPE · ENUM · CONST · REQUIRED · EXTRA · MIN_ITEMS · MAX_ITEMS · MIN_LENGTH · MAX_LENGTH


def assert_supported(schema: Any) -> None:
    if not isinstance(schema, dict):
        raise UnsupportedSchema
    for key, sub in schema.items():
        if key not in SUPPORTED:
            raise UnsupportedSchema
        if key == "type":
            kinds = sub if isinstance(sub, list) else [sub]
            if not kinds or any(k not in TYPES for k in kinds):
                raise UnsupportedSchema
        elif key == "properties":
            if not isinstance(sub, dict):
                raise UnsupportedSchema
            for child in sub.values():
                assert_supported(child)
        elif key == "items":
            assert_supported(sub)
        elif key == "additionalProperties" and sub is not False:
            raise UnsupportedSchema  # chỉ có đối tượng đóng (mục Output contract của 07-prompts.md)
        elif key in ("minItems", "maxItems", "minLength", "maxLength") and (not isinstance(sub, int) or isinstance(sub, bool) or sub < 0):
            raise UnsupportedSchema
        elif key == "required" and (not isinstance(sub, list) or not all(isinstance(r, str) for r in sub)):
            raise UnsupportedSchema
        elif key == "enum" and not isinstance(sub, list):
            raise UnsupportedSchema


def _is(kind: str, value: Any) -> bool:
    if kind == "null":
        return value is None
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "string":
        return isinstance(value, str)
    if kind == "array":
        return isinstance(value, list)
    if kind == "object":
        return isinstance(value, dict)
    return False


def _same(a: Any, b: Any) -> bool:
    return type(a) is type(b) and a == b  # `True` không bằng `1`


def validate(schema: dict[str, Any], value: Any, path: str = "") -> list[Violation]:
    out: list[Violation] = []
    here = path or "$"
    if "type" in schema:
        kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is(k, value) for k in kinds):
            return [Violation(here, "TYPE")]  # sai kiểu thì các ràng buộc còn lại không còn nghĩa
    if "enum" in schema and not any(_same(value, e) for e in schema["enum"]):
        out.append(Violation(here, "ENUM"))
    if "const" in schema and not _same(value, schema["const"]):
        out.append(Violation(here, "CONST"))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            out.append(Violation(here, "MIN_LENGTH"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            out.append(Violation(here, "MAX_LENGTH"))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            out.append(Violation(here, "MIN_ITEMS"))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            out.append(Violation(here, "MAX_ITEMS"))
        if "items" in schema:
            for i, item in enumerate(value):
                out += validate(schema["items"], item, f"{path}[{i}]")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                out.append(Violation(f"{path}.{name}" if path else name, "REQUIRED"))
        for name, v in value.items():
            if name in props:
                out += validate(props[name], v, f"{path}.{name}" if path else name)
            elif schema.get("additionalProperties") is False:
                out.append(Violation(f"{path}.<trường lạ>" if path else "<trường lạ>", "EXTRA"))  # không ghi tên trường: tên do model đặt
    return out
