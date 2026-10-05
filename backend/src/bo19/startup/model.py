"""Mô hình của bước kiểm khởi động — ma trận bước × entrypoint của mục Bước kiểm khởi động của 06-structure.md.

`MATRIX` chép từng dòng của bảng đó; `tests/test_startup_runner.py` đọc lại bảng trong tài liệu và đòi hai bên khớp từng dòng
(số bước, cột `api`/`worker`/cron, mức) — một bên đổi mà bên kia không đổi là test đỏ (CLAUDE.md, luật 5: nhất quán).
"""
from __future__ import annotations

import enum
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bo19.config.settings import Settings


class Entry(str, enum.Enum):
    API = "api"
    WORKER = "worker"
    CRON = "cron"
    COMBINED = "combined"  # `combined_main`: hợp mọi bước có ✔ ở bất kỳ cột nào, cộng bước #18 (ADR-033). Entrypoint chưa viết (O1-6).


class Level(str, enum.Enum):
    BLOCK = "BLOCK"  # Chặn — trượt thì ghi danh sách mã rồi thoát mã khác 0
    WARN = "WARN"    # Cảnh báo — chỉ ghi log
    LOG = "LOG"      # Ghi log — tự nó không chặn gì


@dataclass(frozen=True)
class Step:
    number: str  # "1", "2", "4a", ... "21" — đúng như cột # của bảng
    title: str
    entries: frozenset[Entry]
    level: Level
    needs_db: bool = False

    def applies(self, entry: Entry) -> bool:
        if entry is Entry.COMBINED:
            return bool(self.entries) or self.number == "18"
        return entry in self.entries


_A, _W, _C = Entry.API, Entry.WORKER, Entry.CRON
_AWC, _AW, _A_, _W_, _NONE = frozenset({_A, _W, _C}), frozenset({_A, _W}), frozenset({_A}), frozenset({_W}), frozenset()
B, W, L = Level.BLOCK, Level.WARN, Level.LOG

MATRIX: tuple[Step, ...] = (
    Step("1", "ledger migration", _AWC, B, needs_db=True),
    Step("2", "kiểm phủ định quyền của role runtime", _AWC, B, needs_db=True),
    Step("3", "checkpointer", _AW, B),
    Step("4a", "extension vector", _AW, B),
    Step("4b", "collection ACTIVE khớp cấu hình embedding", _AW, B),
    Step("4c", "không có collection ACTIVE", _AW, W),
    Step("5", "trần budget", _AW, B),
    Step("6", "soffice headless", _W_, B),
    Step("7", "font của template", _W_, B),
    Step("8", "bản build client", _A_, B),
    Step("9", "graph_thread khớp state_schema_version", _AW, B),
    Step("10", "root logger chỉ có handler mask", _AWC, B),
    Step("11", "ràng buộc cấu hình thời gian", _AW, B),
    Step("12", "secret ký bo19_session", _A_, B),
    Step("13", "múi giờ của tổ chức", _AWC, B),
    Step("14", "object_storage với tới được", _AW, W),
    Step("15", "operating_mode hiện hành", _AW, L, needs_db=True),
    Step("16", "BO19_ENVIRONMENT", _AWC, B),
    Step("17", "operating_mode khớp BO19_ENVIRONMENT", _AW, B, needs_db=True),
    Step("18", "combined_main chỉ ở dev", _NONE, B),
    Step("19", "không biến bật tracing của langsmith", _AWC, B),
    Step("20", "tham số argon2id không thấp hơn WV-16", _A_, B),
    Step("21", "hồ sơ model hợp schema", _AW, B),
    Step("22", "BO19_LLM_API_KEY có mặt (khi api bắt đầu gọi LLM)", _AW, B),
)


@dataclass
class Context:
    """Mọi thứ một bước kiểm cần. `conn` là None khi không nối được DB — bước `needs_db` khi đó bị bỏ qua, không tính là đạt."""
    entry: Entry
    settings: Settings
    env: Mapping[str, str]
    conn: Any  # psycopg.Connection | None
    migrations_root: Path
    cache: dict[str, Any] = field(default_factory=dict)  # giá trị đọc một lần, dùng chung giữa các bước (#15 và #17)


@dataclass(frozen=True)
class Result:
    codes: tuple[str, ...] = ()
    info: Mapping[str, Any] = field(default_factory=dict)  # trường log của bước (chỉ kiểu cơ bản)


Check = Callable[[Context], Result]


def code(step: str, tail: str) -> str:
    """`STARTUP_<nn>_<đuôi>` — hai chữ số cho bước số, giữ nguyên hậu tố a/b/c."""
    head = step.zfill(2) if step.isdigit() else step[:-1].zfill(2) + step[-1].upper()
    return f"STARTUP_{head}_{tail}"
