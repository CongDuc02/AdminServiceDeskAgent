"""Che định danh trước khi một thân response của provider vào `docs/reference/` (repo public) — yêu cầu của PO, 2026-10-05.

Che: mã tổ chức, request id, mọi chuỗi có tiền tố định danh (`org_`, `req_`, `chatcmpl-`, `gsk_`, `sk-`, …), UUID, email, IPv4, chuỗi hex dài, và **mọi chuỗi giống định danh**
(từ 20 ký tự trở lên gồm cả chữ lẫn số) cùng chính giá trị khoá API nếu được truyền vào. Thay bằng `<masked>`.

`self_check` quét LẠI văn bản đã che bằng bộ dò chặt hơn và trả danh sách vấn đề — rỗng nghĩa là **đạt**. Tool chỉ ghi file khi `self_check` đạt.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

MASK = "<masked>"

_PREFIXED = re.compile(r"\b(?:org|req|request|user|key|proj|project|chatcmpl|msg|resp|run|acct|account|batch|file|gsk|sk|pk|tok|token|id)[_-][A-Za-z0-9][A-Za-z0-9_-]{5,}", re.I)
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_HEX = re.compile(r"\b[0-9a-f]{16,}\b", re.I)
_IDENTLIKE = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])")  # kiểm tra mức chuỗi; điều kiện chữ + số xét ở `_looks_like_id`
_ORG_WORDS = re.compile(r"(?i)\borganization\s+[`'\"]?([A-Za-z0-9_-]{6,})[`'\"]?")


def _mixed(seg: str) -> bool:
    return any(c.isdigit() for c in seg) and any(c.isalpha() for c in seg)


def _looks_like_id(token: str) -> bool:
    """Giống định danh: một đoạn (tách ở `-` và `_`) dài từ 12 ký tự gồm cả chữ lẫn số, hoặc cả chuỗi có từ 6 chữ số trở lên và có chữ.
    Nhãn như `E6-STRONG-include_reasoning-false` có chữ số nhưng mỗi đoạn ngắn — không bị che."""
    segs = re.split(r"[-_]", token)
    return any(len(seg) >= 12 and _mixed(seg) for seg in segs) or (sum(c.isdigit() for c in token) >= 6 and any(c.isalpha() for c in token))


def mask(text: str, secrets: Iterable[str] = ()) -> str:
    """Che định danh trong `text`. `secrets` — giá trị nhất định phải biến mất (khoá API); cả giá trị đầy đủ lẫn đoạn đầu 8 ký tự."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, MASK)
            if len(secret) >= 12:
                text = text.replace(secret[:8], MASK)
    text = _ORG_WORDS.sub(lambda m: m.group(0).replace(m.group(1), MASK), text)
    for pattern in (_PREFIXED, _UUID, _EMAIL, _IPV4, _HEX):
        text = pattern.sub(MASK, text)
    return _IDENTLIKE.sub(lambda m: MASK if _looks_like_id(m.group(0)) else m.group(0), text)


def self_check(text: str, secrets: Iterable[str] = ()) -> list[str]:
    """Rỗng = đạt. Mỗi vấn đề là một mã ngắn, không chép lại phần nghi ngờ (chính nó có thể là định danh)."""
    problems: list[str] = []
    for secret in secrets:
        if secret and (secret in text or (len(secret) >= 12 and secret[:8] in text)):
            problems.append("SECRET_PRESENT")
    probe = text.replace(MASK, "")
    for name, pattern in (("PREFIXED_ID", _PREFIXED), ("UUID", _UUID), ("EMAIL", _EMAIL), ("IPV4", _IPV4), ("HEX_LONG", _HEX)):
        if pattern.search(probe):
            problems.append(name)
    if any(_looks_like_id(m.group(0)) for m in _IDENTLIKE.finditer(probe)):
        problems.append("IDENT_LIKE")
    if re.search(r"(?i)\b(?:authorization|bearer)\b\s*[:=]?\s*[A-Za-z0-9._-]{8,}", probe):
        problems.append("AUTH_HEADER")
    return problems
