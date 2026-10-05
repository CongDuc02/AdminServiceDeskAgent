"""`rate_limit_window_increment` — tăng bộ đếm rate limit đăng nhập (mục Rate limit của 09-security.md; GLOSSARY.md, thao tác do endpoint gọi).

Sổ sách kỹ thuật: không `audit_event` (danh sách miễn của A-055), không tác nhân, không `status`, không enqueue — nên **không cần `tool_layer.kernel`**.
`api` không import `persistence.write` (contract `write-path`); nó gọi thao tác này, và thao tác này dùng `unit_of_work`.

Một câu `INSERT … ON CONFLICT (scope, window_start) DO UPDATE` — khoá chính làm một `scope` trong một cửa sổ chỉ có đúng một dòng, nên số dòng bị chặn trên
bởi (số `scope`) × (số cửa sổ chưa dọn), không bởi số lần thử (mục Rủi ro của việc ghi trước khi xác thực). Hai request đồng thời cùng `scope` xếp hàng
trên khoá dòng nên mỗi request nhận một số đếm riêng, không mất lần đếm nào.

Cửa sổ cố định tính theo đồng hồ của DB, không theo đồng hồ từng instance `api`: `window_start` là mốc làm tròn xuống bội của `window_seconds` tính từ epoch.
Giao dịch commit ngay khi hàm trả về — lần thử sai vẫn được đếm dù request sau đó thất bại.
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg

from bo19.persistence.write import unit_of_work

_INCREMENT = """
INSERT INTO rate_limit_window (scope, window_start, attempt_count)
VALUES (%(scope)s,
        to_timestamp(floor(extract(epoch FROM now()) / %(sec)s::double precision) * %(sec)s::double precision),
        1)
ON CONFLICT (scope, window_start) DO UPDATE SET attempt_count = rate_limit_window.attempt_count + 1
RETURNING attempt_count,
          GREATEST(1, ceil(extract(epoch FROM (window_start + make_interval(secs => %(sec)s::double precision) - now()))))::int
"""


@dataclass(frozen=True)
class WindowCount:
    attempt_count: int  # số lần thử trong cửa sổ hiện hành, đã gồm lần này
    retry_after_seconds: int  # từ giờ tới hết cửa sổ, tối thiểu 1


def rate_limit_window_increment(conn: psycopg.Connection, scope: str, *, window_seconds: int) -> WindowCount:
    with unit_of_work(conn):
        row = conn.execute(_INCREMENT, {"scope": scope, "sec": window_seconds}).fetchone()
    return WindowCount(row[0], row[1])
