"""Mask log kỹ thuật theo `slot_sensitivity` — mục Mask trong log kỹ thuật của 09-security.md (NFR-05).

| `slot_sensitivity` | Trong log |
|---|---|
| `INT` | giữ nguyên |
| `PER` | `[PER]` — không log độ dài, không log ký tự đầu/cuối |
| `RES` | `[RES]` |

Input không phải slot mà có thể mang `RES` thì mask như `RES` (mục Allowlist input của 03-agents.md): `Sensitive.unclassified`.
Tên trường giữ nguyên — nó là metadata cấu trúc; chỉ giá trị bị thay.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bo19.domain.sensitivity import SlotSensitivity

MASKS: Mapping[SlotSensitivity, str | None] = {SlotSensitivity.INT: None, SlotSensitivity.PER: "[PER]", SlotSensitivity.RES: "[RES]"}


class Sensitive:
    """Giá trị slot kèm độ nhạy — hình thức duy nhất để đưa giá trị slot vào log (06-structure.md, mục Nghĩa vụ kế thừa).
    `repr` và `str` không bao giờ chứa giá trị, kể cả với `INT`: một lần `str()` nhầm không làm lộ gì."""

    __slots__ = ("_value", "sensitivity")

    def __init__(self, value: object, sensitivity: SlotSensitivity) -> None:
        if not isinstance(sensitivity, SlotSensitivity):
            raise TypeError("sensitivity phải là SlotSensitivity")
        self._value = value
        self.sensitivity = sensitivity

    @classmethod
    def unclassified(cls, value: object) -> "Sensitive":
        """Input không phải slot, có thể mang RES — mask như RES."""
        return cls(value, SlotSensitivity.RES)

    def masked(self) -> Any:
        mask = MASKS[self.sensitivity]
        return self._value if mask is None else mask

    def __repr__(self) -> str:
        return f"Sensitive(<{self.sensitivity.value}>)"

    __str__ = __repr__


def mask_value(value: object) -> Any:
    return value.masked() if isinstance(value, Sensitive) else value


def mask_fields(_logger: object, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Bước mask trong chuỗi processor của `log.py`, chạy trước bước chuyển cho handler (ADR-029)."""
    return {k: mask_value(v) for k, v in event_dict.items()}
