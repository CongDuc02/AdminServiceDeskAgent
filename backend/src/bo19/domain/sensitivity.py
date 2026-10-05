"""`slot_sensitivity` — độ nhạy của dữ liệu trong một slot (GLOSSARY.md, mục Enum khác). Không IO."""
from __future__ import annotations

import enum


class SlotSensitivity(str, enum.Enum):
    INT = "INT"  # INTERNAL — dữ liệu tổ chức hoặc tham chiếu
    PER = "PER"  # PERSONAL — nhận dạng một cá nhân cụ thể
    RES = "RES"  # RESTRICTED — định danh pháp lý, hoặc suy ra được tình trạng sức khoẻ, pháp lý, tài chính
