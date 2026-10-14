"""Kiểm nội dung tự do do LLM sinh — `validate_free_content` (mục Output validation trước khi render của 09-security.md; mục P4/P5 của 07-prompts.md; định nghĩa F2 của 01-prd.md) — thuần, không IO.

Hai nhóm, một hàm, một danh sách mã (không bao giờ mang nội dung):

- **chất lượng** — không rỗng; không placeholder (`N/A`, `...`, `[điền sau]`); không câu khung (`Kính gửi`, `Số:`, `Nơi nhận` — 07-prompts.md mục 3.4 và F2 "thêm dòng nơi nhận");
- **an ninh** — không thẻ HTML/XML; không cú pháp trường của template (`{{`, `}}`, `{%`, `%}`, `{#`, `#}`); không dài hơn `max_length`; không chứa **nguyên văn** giá trị của một slot `RES` ngoài input đã khai của biến.

Cùng các kiểm này dùng lại ở `review_readiness_check` (`PLACEHOLDER_VALUE`, `FRAME_TEXT_IN_VARIABLE`) trên **mọi** biến, nên chúng nằm một chỗ.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

EMPTY = "EMPTY"
PLACEHOLDER = "PLACEHOLDER"
FRAME_TEXT = "FRAME_TEXT"
TEMPLATE_SYNTAX = "TEMPLATE_SYNTAX"
MARKUP = "MARKUP"
TOO_LONG = "TOO_LONG"
CONTAINS_RES_VALUE = "CONTAINS_RES_VALUE"

# Cụm khung của văn bản hành chính mà biến nội dung tự do không được mang. So sánh sau khi chuẩn hoá dấu (NFC), không phân biệt hoa thường.
FRAME_PHRASES = ("kính gửi", "số:", "nơi nhận")
_PLACEHOLDER_WORDS = frozenset({"n/a", "na", "n.a", "tbd", "todo", "tba", "none", "null", "không có", "...", "…", "-", "--", "---", "[điền sau]", "[điền vào]", "xxx"})
_PLACEHOLDER_INSIDE = re.compile(r"\[\s*(điền|cập nhật|bổ sung|todo|tbd)[^\]]*\]|\.{3,}|…|\bn/a\b", re.IGNORECASE)
_TEMPLATE_SYNTAX = re.compile(r"\{\{|\}\}|\{%|%\}|\{#|#\}")
_MARKUP = re.compile(r"<\s*/?\s*[A-Za-z!?][^>]*>|&[A-Za-z#][A-Za-z0-9]{1,8};")
MIN_RES_LENGTH = 4  # chuỗi `RES` ngắn hơn thế (ví dụ "ABC") khớp ngẫu nhiên trong câu chữ thường — kiểm trùng nguyên văn chỉ có nghĩa với giá trị đủ dài


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def is_placeholder(text: str) -> bool:
    """Giá trị giữ chỗ: rỗng, chỉ dấu câu, một từ giữ chỗ, hoặc chứa cụm giữ chỗ (`...`, `[điền sau]`, `N/A`)."""
    t = normalize(text)
    if not t:
        return True
    low = t.lower()
    if low in _PLACEHOLDER_WORDS or not any(ch.isalnum() for ch in t):
        return True
    return bool(_PLACEHOLDER_INSIDE.search(t))


def frame_phrase_in(text: str) -> bool:
    low = normalize(text).lower()
    return any(p in low for p in FRAME_PHRASES)


def validate_body(body: str, *, max_length: int, forbidden_res_values: Iterable[str] = ()) -> list[str]:
    """Mã trượt của một biến nội dung tự do (rỗng = đạt). `forbidden_res_values`: giá trị slot `RES` KHÔNG thuộc input đã khai của biến này."""
    codes: list[str] = []
    text = normalize(body)
    if not text:
        return [EMPTY]
    if is_placeholder(body):
        codes.append(PLACEHOLDER)
    if frame_phrase_in(body):
        codes.append(FRAME_TEXT)
    if _TEMPLATE_SYNTAX.search(body):
        codes.append(TEMPLATE_SYNTAX)
    if _MARKUP.search(body):
        codes.append(MARKUP)
    if len(body) > max_length:
        codes.append(TOO_LONG)
    low = text.lower()
    for value in forbidden_res_values:
        v = normalize(str(value)).lower()
        if len(v) >= MIN_RES_LENGTH and v in low:
            codes.append(CONTAINS_RES_VALUE)
            break
    return codes
