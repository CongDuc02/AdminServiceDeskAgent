"""Từ vựng `slot_definition.validation_rules` v1 — hàm thuần, không IO (A-093, O1-14; `docs/design/proposals/validation-rules-vocabulary.md`, PO duyệt 2026-10-09).

`validation_rules` là một đối tượng JSON **khoá theo kiểu rule**. Năm kiểu, đóng, chạy theo thứ tự cố định dưới đây; rule đầu tiên hỏng quyết mã trả về:

1. `non_blank: true` — sau NFC và cắt khoảng trắng hai đầu, còn ít nhất một ký tự thuộc nhóm chữ (`L*`) hoặc chữ số (`N*`). `STRING`, `TEXT`.
2. `min_tokens: N` — số đơn vị cách nhau bởi khoảng trắng (sau NFC) ≥ N. **Với tiếng Việt đây là đếm TIẾNG (âm tiết), không phải đếm từ:** "xin visa" = 2. `STRING`, `TEXT`.
3. `int_range: {"min": a, "max": b}` — mỗi khoá tuỳ chọn, có ít nhất một. `INT`; `bool` không phải số nguyên.
4. `one_of: [..]` — giá trị bằng đúng một phần tử (phân biệt hoa thường). `ENUM`.
5. `not_in_future: true` — ngày không sau NGÀY HÔM NAY theo múi giờ của tổ chức (A-041). `DATE`. **Kiểu duy nhất đọc đồng hồ** (PO duyệt 2026-10-21: ngày nghỉ việc ở tương lai làm thể thức "đã từng công tác" sai); `check_value(..., today=)` tiêm được để test không phụ thuộc đồng hồ.

Trước các rule có kiểm `data_type` (mã `RULE_TYPE`). Mã kết quả: `RULE_TYPE`, `RULE_NON_BLANK`, `RULE_MIN_TOKENS`, `RULE_INT_RANGE`, `RULE_ONE_OF`, `RULE_NOT_IN_FUTURE` — **chỉ mã, không bao giờ giá trị**
(`purpose` là `RES`). Kiểu rule lạ, tham số sai kiểu hay kiểu rule không hợp `data_type` là **cấu hình không hợp lệ** (`validate_config`) — fail-closed, không bị bỏ qua.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
import zoneinfo
from typing import Any

ORG_TIMEZONE = "Asia/Ho_Chi_Minh"  # A-041 `Đã chốt` — như `numbering.ORG_TIMEZONE`; bước kiểm khởi động #13 chặn giá trị khác

DATA_TYPES = ("STRING", "TEXT", "INT", "DATE", "TIMESTAMP", "ENUM", "LIST", "BOOL", "FILE")
KINDS = ("non_blank", "min_tokens", "int_range", "one_of", "not_in_future")  # thứ tự đánh giá
KIND_DATA_TYPES: dict[str, frozenset[str]] = {
    "non_blank": frozenset({"STRING", "TEXT"}),
    "min_tokens": frozenset({"STRING", "TEXT"}),
    "int_range": frozenset({"INT"}),
    "one_of": frozenset({"ENUM"}),
    "not_in_future": frozenset({"DATE"}),
}
CODES = {"type": "RULE_TYPE", "non_blank": "RULE_NON_BLANK", "min_tokens": "RULE_MIN_TOKENS", "int_range": "RULE_INT_RANGE", "one_of": "RULE_ONE_OF", "not_in_future": "RULE_NOT_IN_FUTURE"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_config(data_type: str, rules: Any) -> list[str]:
    """Lỗi của một `validation_rules` đã khai (rỗng = hợp lệ). Mã chỉ mang tên kiểu rule, không mang giá trị tham số."""
    if data_type not in DATA_TYPES:
        return [f"DATA_TYPE_UNKNOWN:{str(data_type)[:20]}"]
    if not isinstance(rules, dict):
        return ["RULES_NOT_OBJECT"]
    errors: list[str] = []
    for kind, param in rules.items():
        if kind not in KINDS:
            errors.append(f"RULE_KIND_UNKNOWN:{str(kind)[:30]}")
            continue
        if data_type not in KIND_DATA_TYPES[kind]:
            errors.append(f"RULE_KIND_DATA_TYPE:{kind}")
            continue
        if not _param_ok(kind, param):
            errors.append(f"RULE_PARAM_INVALID:{kind}")
    return errors


def _param_ok(kind: str, param: Any) -> bool:
    if kind in ("non_blank", "not_in_future"):
        return param is True
    if kind == "min_tokens":
        return _is_int(param) and param >= 1
    if kind == "int_range":
        if not isinstance(param, dict) or not param or not set(param) <= {"min", "max"} or not all(_is_int(v) for v in param.values()):
            return False
        return "min" not in param or "max" not in param or param["min"] <= param["max"]
    if kind == "one_of":
        return isinstance(param, list) and bool(param) and all(isinstance(v, str) and v for v in param) and len(set(param)) == len(param)
    return False


def _type_ok(data_type: str, value: Any) -> bool:
    if data_type in ("STRING", "TEXT", "ENUM"):
        return isinstance(value, str)
    if data_type == "INT":
        return _is_int(value)
    if data_type == "DATE":
        if not isinstance(value, str) or not _ISO_DATE.match(value):
            return False
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            return False
        return True
    if data_type == "TIMESTAMP":
        if not isinstance(value, str):
            return False
        try:
            dt.datetime.fromisoformat(value)
        except ValueError:
            return False
        return True
    if data_type == "BOOL":
        return isinstance(value, bool)
    if data_type == "LIST":
        return isinstance(value, list)
    return False  # FILE: không bao giờ là giá trị do người gõ


def tokens(text: str) -> int:
    """Số đơn vị cách nhau bởi khoảng trắng Unicode sau NFC (tiếng Việt: số tiếng)."""
    return len(unicodedata.normalize("NFC", text).split())


def _non_blank(text: str) -> bool:
    return any(unicodedata.category(ch)[0] in ("L", "N") for ch in unicodedata.normalize("NFC", text).strip())


def org_today() -> dt.date:
    """Ngày hôm nay theo múi giờ của tổ chức (A-041) — nguồn đồng hồ duy nhất của từ vựng rule."""
    return dt.datetime.now(zoneinfo.ZoneInfo(ORG_TIMEZONE)).date()


def check_value(data_type: str, rules: dict[str, Any], value: Any, *, today: dt.date | None = None) -> tuple[str, ...]:
    """Mã hỏng của `value` (rỗng = đạt): tối đa một mã — kiểu dữ liệu trước, rồi rule đầu tiên hỏng theo thứ tự `KINDS`. `rules` phải đã qua `validate_config`."""
    if not _type_ok(data_type, value):
        return (CODES["type"],)
    for kind in KINDS:
        if kind not in rules:
            continue
        param = rules[kind]
        if kind == "non_blank":
            ok = _non_blank(value)
        elif kind == "min_tokens":
            ok = tokens(value) >= param
        elif kind == "int_range":
            ok = value >= param.get("min", value) and value <= param.get("max", value)
        elif kind == "not_in_future":
            ok = dt.date.fromisoformat(value) <= (today or org_today())
        else:
            ok = value in param
        if not ok:
            return (CODES[kind],)
    return ()
