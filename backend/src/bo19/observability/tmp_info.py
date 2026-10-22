"""Quan sát `/tmp` lúc khởi động: nó là đĩa hay bộ nhớ, và còn bao nhiêu chỗ (A-095; PO 2026-10-21 cho phép, chỉ quan sát).

Lý do: `soffice` ghi hồ sơ người dùng và file trung gian vào `/tmp` (`rendering/convert.py`). Nếu `/tmp` của Render Free là `tmpfs` thì mọi byte ghi vào đó tính vào bộ nhớ của instance (512 MB) —
ngân sách ở A-095 không thấy phần đó. Gói Free không có shell, nên cách duy nhất để biết là để chính tiến trình nói ra.

Một dòng log `TMP_INFO` mang **loại hệ thống file, điểm gắn và hai con số** (tổng, còn trống, MiB) — không đường dẫn của người dùng, không nội dung. Không đổi hành vi, không phải bước kiểm khởi động,
không bao giờ ném: mọi lỗi thành `TMP_INFO_SKIPPED` kèm lý do. Gọi sau `configure_logging()`.
"""
from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass

from bo19.observability.log import get_logger

log = get_logger("bo19.tmp_info")
MOUNTINFO = "/proc/self/mountinfo"
TMP = "/tmp"
_MIB = 1024 * 1024


@dataclass(frozen=True)
class TmpInfo:
    fstype: str
    mount_point: str
    total_mib: int
    free_mib: int


def _unescape(field: str) -> str:
    """`mountinfo` mã hoá khoảng trắng và vài ký tự thành `\\040`…"""
    out, i = [], 0
    while i < len(field):
        if field[i] == "\\" and i + 4 <= len(field) and field[i + 1 : i + 4].isdigit():
            out.append(chr(int(field[i + 1 : i + 4], 8)))
            i += 4
        else:
            out.append(field[i])
            i += 1
    return "".join(out)


def _contains(mount_point: str, path: str) -> bool:
    return path == mount_point or path.startswith(mount_point.rstrip("/") + "/")


def mount_of(path: str, mountinfo_text: str) -> tuple[str, str] | None:
    """(điểm gắn, loại hệ thống file) của điểm gắn dài nhất chứa `path`; `None` nếu không đọc ra."""
    best: tuple[str, str] | None = None
    for line in mountinfo_text.splitlines():
        head, sep, tail = line.partition(" - ")
        fields, rest = head.split(), tail.split()
        if not sep or len(fields) < 5 or not rest:
            continue
        mount_point = _unescape(fields[4])
        if _contains(mount_point, path) and (best is None or len(mount_point) >= len(best[0])):
            best = (mount_point, rest[0])
    return best


def read_tmp_info(*, path: str = TMP, mountinfo: str = MOUNTINFO, disk_usage: Callable[[str], tuple[int, int, int]] = shutil.disk_usage) -> TmpInfo | None:
    try:
        with open(mountinfo, encoding="utf-8") as f:
            mount = mount_of(os.path.realpath(path), f.read())
        if mount is None:
            return None
        total, _used, free = disk_usage(path)
        return TmpInfo(fstype=mount[1], mount_point=mount[0], total_mib=total // _MIB, free_mib=free // _MIB)
    except OSError:
        return None


def log_tmp_info(**kwargs) -> TmpInfo | None:
    try:
        info = read_tmp_info(**kwargs)
    except Exception as e:  # noqa: BLE001 — quan sát không bao giờ làm hỏng khởi động
        log.warning("TMP_INFO_SKIPPED", reason="ERROR", exc=e)
        return None
    if info is None:
        log.info("TMP_INFO_SKIPPED", reason="UNREADABLE")
        return None
    log.info("TMP_INFO", fstype=info.fstype, mount_point=info.mount_point, total_mib=info.total_mib, free_mib=info.free_mib)
    return info
