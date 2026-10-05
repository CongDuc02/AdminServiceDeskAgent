"""Hash và verify mật khẩu bằng `argon2id` — ADR-021, ADR-034; tham số WV-16, trần verify đồng thời WV-16b.

Một module duy nhất gọi `argon2-cffi`: `api` gọi `verify`, thao tác vận hành seed (`tools/seed-dev/`) gọi `hash`.
Tham số đọc từ cấu hình (`config.settings`), không viết cứng; bước kiểm khởi động #20 từ chối tham số thấp hơn WV-16. Test cần nhanh tự dựng
`PasswordVerifier` riêng với tham số rẻ — không hạ cấu hình của ứng dụng.

**Trần verify đồng thời (WV-16b, ADR-034):** một semaphore của tiến trình bọc quanh mỗi lần verify; lần thứ năm chờ tới khi có chỗ. Bộ nhớ đỉnh dành cho
verify bị chặn ở 4 × `memory_cost` bất kể tải. Thư viện không có cơ chế này; dự án tự làm.

**Một lần verify cho mọi ca (09-security.md, mục AuthN):** khi không có hash hợp lệ để so — mã nhân viên không tồn tại, nhân viên không còn hoạt động, thiếu
credential, hash hỏng — `verify` so mật khẩu với một hash giả dựng lúc khởi động, cùng tham số, để thời gian phản hồi của hai ca sai không phân biệt được.
"""
from __future__ import annotations

import secrets
import threading

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from bo19.config import working_values as wv

ALGORITHM = "argon2id"  # giá trị của cột `employee_credential.hash_algorithm`


class PasswordVerifier:
    def __init__(self, *, time_cost: int, memory_cost_kib: int, parallelism: int, max_concurrent: int = wv.ARGON2_MAX_CONCURRENT_VERIFY) -> None:
        self._ph = PasswordHasher(time_cost=time_cost, memory_cost=memory_cost_kib, parallelism=parallelism, type=Type.ID)
        self._slots = threading.BoundedSemaphore(max_concurrent)
        self._dummy_hash = self._ph.hash(secrets.token_urlsafe(24))  # mật khẩu ngẫu nhiên vứt đi — chỉ để có một hash cùng tham số

    @classmethod
    def from_settings(cls, settings) -> "PasswordVerifier":
        return cls(time_cost=settings.argon2_time_cost, memory_cost_kib=settings.argon2_memory_cost_kib, parallelism=settings.argon2_parallelism)

    def hash(self, password: str) -> str:
        with self._slots:  # cùng trần với verify: hash cũng tốn bộ nhớ như nhau
            return self._ph.hash(password)

    def _argon_verify(self, stored_hash: str, password: str) -> bool:
        """Đúng một lần gọi `argon2-cffi`, trong trần đồng thời. Test đếm lời gọi ở đây."""
        with self._slots:
            try:
                return bool(self._ph.verify(stored_hash, password))
            except VerifyMismatchError:
                return False

    def verify(self, stored_hash: str | None, password: str) -> bool:
        """`True` chỉ khi `stored_hash` là hash argon2id hợp lệ của `password`. `None` — không có hash để so — luôn trả `False` sau một lần verify giả."""
        if stored_hash is not None:
            try:
                return self._argon_verify(stored_hash, password)
            except (InvalidHashError, VerificationError):
                pass  # hash hỏng hay thuật toán lạ: coi như không có hash — rơi xuống lần verify giả
        self._argon_verify(self._dummy_hash, password)
        return False
