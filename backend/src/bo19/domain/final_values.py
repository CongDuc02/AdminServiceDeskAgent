"""Giá trị của các biến `SYSTEM` *điền sau duyệt* ở bản `FINAL` (B9b2, ADR-041 mục 4). Hàm thuần, không IO.

Bản nháp hiện dấu giữ chỗ cho các biến này (`domain.provisional`); bản `FINAL` thay đúng bằng giá trị thật, theo **tên biến**:

- `document_number` — chuỗi số đã định dạng của dòng sổ;
- `issued_date` — ngày cấp số theo múi giờ tổ chức, `dd/mm/yyyy` (A-098);
- `signer_user_id` — `"<họ tên>, <chức danh>"` của người đã ký (PO, 2026-10-20: in họ tên và chức danh, không in mã nhân viên). Tên biến là tên cũ của slot; giá trị là tên và chức danh. Dấu phân cách là mặc định làm việc (A-100).

Biến điền-sau-duyệt mang tên khác thì **không có nguồn** — trả về trong `unresolved` để người gọi dừng (`RENDER_INPUT_INVALID`), không điền bừa.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

DOCUMENT_NUMBER = "document_number"
ISSUED_DATE = "issued_date"
SIGNER = "signer_user_id"
RESOLVABLE = frozenset({DOCUMENT_NUMBER, ISSUED_DATE, SIGNER})


def signer_line(full_name: str, job_title: str) -> str:
    return f"{full_name}, {job_title}"


@dataclass(frozen=True)
class FinalSystemValues:
    values: dict[str, str]
    unresolved: tuple[str, ...]  # tên biến điền-sau-duyệt không có nguồn

    def __repr__(self) -> str:
        return f"FinalSystemValues(variables={sorted(self.values)}, unresolved={list(self.unresolved)})"


def system_values(fill_after_approval: Iterable[str], *, formatted_number: str, issued_date: dt.date, signer: str) -> FinalSystemValues:
    source: Mapping[str, str] = {DOCUMENT_NUMBER: formatted_number, ISSUED_DATE: issued_date.strftime("%d/%m/%Y"), SIGNER: signer}
    names = sorted(set(fill_after_approval))
    return FinalSystemValues({n: source[n] for n in names if n in source}, tuple(n for n in names if n not in source))
