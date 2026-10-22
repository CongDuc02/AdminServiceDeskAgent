"""Giá trị của các biến `SYSTEM` *điền sau duyệt* ở bản `FINAL` (B9b2, ADR-041 mục 4). Hàm thuần, không IO.

Bản nháp hiện dấu giữ chỗ cho các biến này (`domain.provisional`); bản `FINAL` thay đúng bằng giá trị thật, theo **tên biến**:

- `document_number` — chuỗi số đã định dạng của dòng sổ;
- `issued_date` — ngày cấp số theo múi giờ tổ chức, `dd/mm/yyyy` (A-098);
- `signer_title` — CHỨC VỤ của người đã ký, IN HOA (PO, 2026-10-22, A-100: khối ký ba tầng theo Phụ lục I — chức vụ in hoa đậm, khoảng trống ký và đóng dấu, họ tên đậm; ngoài ra không dấu phẩy nối);
- `signer_name` — HỌ TÊN của người đã ký (viết như trong hồ sơ nhân sự, không học hàm, không mã nhân viên);
- `signer_user_id` — (bản một dòng, giữ cho mẫu cũ) `"<họ tên>, <chức danh>"` của người đã ký (PO, 2026-10-20: in họ tên và chức danh, không in mã nhân viên). Tên biến là tên cũ của slot; giá trị là tên và chức danh. Dấu phân cách là mặc định làm việc (A-100).

Biến điền-sau-duyệt mang tên khác thì **không có nguồn** — trả về trong `unresolved` để người gọi dừng (`RENDER_INPUT_INVALID`), không điền bừa.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

DOCUMENT_NUMBER = "document_number"
ISSUED_DATE = "issued_date"
SIGNER = "signer_user_id"
SIGNER_TITLE = "signer_title"
SIGNER_NAME = "signer_name"
RESOLVABLE = frozenset({DOCUMENT_NUMBER, ISSUED_DATE, SIGNER, SIGNER_TITLE, SIGNER_NAME})


def signer_line(full_name: str, job_title: str) -> str:
    return f"{full_name}, {job_title}"


@dataclass(frozen=True)
class FinalSystemValues:
    values: dict[str, str]
    unresolved: tuple[str, ...]  # tên biến điền-sau-duyệt không có nguồn

    def __repr__(self) -> str:
        return f"FinalSystemValues(variables={sorted(self.values)}, unresolved={list(self.unresolved)})"


def system_values(fill_after_approval: Iterable[str], *, formatted_number: str, issued_date: dt.date, signer: str, signer_name: str | None = None,
                  signer_title: str | None = None) -> FinalSystemValues:
    """`signer_name`, `signer_title` (chưa viết hoa) có thì mới có nguồn cho `signer_name` / `signer_title`; `signer_title` được viết HOA ở đây (một chỗ duy nhất)."""
    source: dict[str, str] = {DOCUMENT_NUMBER: formatted_number, ISSUED_DATE: issued_date.strftime("%d/%m/%Y"), SIGNER: signer}
    if signer_name is not None:
        source[SIGNER_NAME] = signer_name
    if signer_title is not None:
        source[SIGNER_TITLE] = signer_title.upper()
    names = sorted(set(fill_after_approval))
    return FinalSystemValues({n: source[n] for n in names if n in source}, tuple(n for n in names if n not in source))
