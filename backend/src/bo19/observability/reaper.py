"""Dọn tiến trình zombie khi Python là PID 1 của container (B9a2; câu hỏi PID 1 từ B8; ADR-033).

Trong container, tiến trình chính là PID 1 và là **cha nuôi** của mọi tiến trình mồ côi. Python không tự `wait` chúng, nên mỗi tiến trình con của `soffice` mà cha của nó đã chết (đo ở B9a2, image `test`:
5 zombie `gpgconf`/`gpg`/`gpgsm` SAU MỖI lần chuyển đổi bình thường, thêm một `soffice.bin` khi chuyển đổi bị giết giữa chừng) nằm lại trong bảng tiến trình tới khi tiến trình thoát — chuyển đổi lặp lại thì bảng đầy.

`Reaper` chỉ dọn zombie **con trực tiếp của tiến trình này mà không do mã của ta sinh ra** — cụ thể: zombie không thuộc `protected()` (PID của các `Popen` còn sống mà chủ của chúng sẽ tự `wait`, xem `tool_layer.rendering.convert.live_pids`).
Một zombie phải được thấy ở **hai lần quét liên tiếp** mới bị dọn (trừ lần quét cuối khi thoát), nên một `Popen` vừa chết mà chủ chưa kịp `wait` không bị cướp mã thoát của nó.

Chỉ chạy khi `os.getpid() == 1` (hoặc `force=True` — cho test). Trên Linux; ngoài Linux không làm gì. Không giết tiến trình nào: chỉ `waitpid` zombie. Log chỉ mang số và tên `comm` của tiến trình (không đối số dòng lệnh).
"""
from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass

from bo19.observability.log import get_logger

log = get_logger("bo19.reaper")
PROC = "/proc"


@dataclass(frozen=True)
class Child:
    pid: int
    comm: str
    state: str  # ký tự trạng thái của /proc/<pid>/stat: R, S, D, Z, ...


def children(parent: int | None = None, proc: str = PROC) -> list[Child]:
    """Con trực tiếp của `parent` (mặc định: tiến trình này) theo `/proc`. Rỗng nếu không đọc được `/proc`."""
    parent = os.getpid() if parent is None else parent
    out: list[Child] = []
    try:
        names = os.listdir(proc)
    except OSError:
        return out
    for name in names:
        if not name.isdigit():
            continue
        try:
            with open(f"{proc}/{name}/stat", encoding="utf-8", errors="replace") as f:
                stat = f.read()
            comm = stat[stat.index("(") + 1: stat.rindex(")")]
            rest = stat[stat.rindex(")") + 2:].split()
            if int(rest[1]) == parent:
                out.append(Child(int(name), comm, rest[0]))
        except (OSError, ValueError, IndexError):
            continue
    return sorted(out, key=lambda c: c.pid)


class Reaper:
    def __init__(self, protected: Callable[[], set[int]] = lambda: set(), *, interval_s: float = 0.5, proc: str = PROC) -> None:
        self._protected, self._interval, self._proc = protected, interval_s, proc
        self._seen: set[int] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.reaped = 0

    def sweep(self, *, final: bool = False) -> int:
        """Một lần quét. `final`: dọn mọi zombie không được bảo vệ ngay, không đợi lần quét thứ hai. Trả số zombie đã dọn."""
        protected = self._protected()
        zombies = {c.pid for c in children(proc=self._proc) if c.state == "Z" and c.pid not in protected}
        due = zombies if final else zombies & self._seen
        done = 0
        for pid in sorted(due):
            try:
                os.waitpid(pid, os.WNOHANG)
                done += 1
            except ChildProcessError:  # chủ của nó đã `wait` trước — không sao
                pass
        self._seen = zombies - due  # cái vừa dọn không còn; cái mới thấy lần đầu chờ lần quét sau
        self.reaped += done
        return done

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.sweep()
            except Exception as e:  # noqa: BLE001 — bộ dọn không bao giờ làm sập tiến trình
                log.error("REAPER_SWEEP_ERROR", exc=e)

    def start(self) -> "Reaper":
        self._thread = threading.Thread(target=self._run, name="reaper", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        """Dừng luồng quét rồi quét lần cuối. Ghi `PROCESS_TABLE_AT_EXIT`: số con trực tiếp còn lại, số zombie, và tên các `comm` còn sống (để thấy `soffice` mồ côi)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.sweep(final=True)
        left = children(proc=self._proc)
        zombies = [c for c in left if c.state == "Z"]
        log.info("PROCESS_TABLE_AT_EXIT", children=len(left), zombies=len(zombies), reaped=self.reaped, alive=",".join(sorted({c.comm for c in left if c.state != "Z"})) or None)


def start_if_init(protected: Callable[[], set[int]] = lambda: set(), *, force: bool = False, **kw) -> Reaper | None:
    """Khởi động bộ dọn nếu tiến trình là PID 1 (hoặc `force`). `None` nếu không cần."""
    if not force and os.getpid() != 1:
        return None
    return Reaper(protected, **kw).start()
