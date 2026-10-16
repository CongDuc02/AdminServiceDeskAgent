"""Chuyển `.docx` sang `.pdf` bằng LibreOffice headless — **một tiến trình `soffice` riêng cho mỗi lần chuyển đổi** (ADR-015; `docs/reference/libreoffice-headless-convert.md`).

Tham số có nguyên văn trong nguồn đã ghim: `--headless`, `--norestore`, `--nolockcheck`, `-env:UserInstallation=file://<hồ sơ tạm>` (hồ sơ RIÊNG cho lần đó — hai lần chuyển đổi đồng thời không dùng chung
trạng thái), `--convert-to pdf`, `--outdir <thư mục tạm của lần đó>`. Không shell: danh sách đối số. `HOME` của tiến trình con là thư mục tạm của lần đó (user `bo19` không có thư mục nhà).

**Hết thời gian** (`timeout_s`, WV-23): giết cả **nhóm tiến trình** (`soffice` sinh `soffice.bin`), xoá thư mục tạm, `ConversionTimeout`. Mọi lỗi khác — mã thoát khác 0, không có file ra, file ra không phải PDF —
là `ConversionFailed`. **Lỗi chỉ mang mã**: đầu ra của `soffice` có thể chứa tên file, đường dẫn, đoạn văn bản — không bao giờ vào thông điệp, log hay `audit_event`.

Không giả định PDF tất định theo byte (ADR-015): thứ tự "chuyển đổi xong rồi mới giành khoá" của tool `pdf_export` là chỗ chịu tính không tất định đó.

**Tắt tiến trình (B9a2; ADR-033):** `abort_all()` giết NGAY nhóm tiến trình của mọi chuyển đổi đang chạy và chặn chuyển đổi mới (`ConversionAborted`, mã `JOB_CANCELLED` — lỗi tạm, job được `release` chứ không tiêu lượt thử).
Gọi nó từ composition root khi drain hết hạn, để `SIGTERM` lúc `soffice` đang chạy (một chuyển đổi mất 32–88 s ở 0,1 CPU) không để lại `soffice` mồ côi và tiến trình thoát trong ≈ 5 s của Render.
`live_pids()` trả PID các tiến trình con còn sống mà chủ của chúng sẽ tự `wait` — bộ dọn zombie của PID 1 (`observability.reaper`) không được đụng vào chúng.
"""
from __future__ import annotations

import io
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path

from bo19.tool_layer.tools._common import ToolError

SOFFICE = "soffice"
_LIVE: set[int] = set()
_LOCK = threading.Lock()
ABORT = threading.Event()  # đặt khi tiến trình đang tắt; một chiều (trừ `reset_abort` của test)


class ConversionFailed(ToolError):
    code = "CONVERSION_FAILED"


class ConversionTimeout(ToolError):
    code = "TIMEOUT"


class ConversionAborted(ToolError):
    code = "JOB_CANCELLED"  # tiến trình đang tắt: chuyển đổi bị giết hay không được bắt đầu — không phải lỗi của tài liệu


class VersionFailed(ToolError):
    code = "SOFFICE_VERSION_FAILED"  # `soffice --headless --version` không chạy được, thoát mã khác 0, hoặc không in dòng phiên bản


def live_pids() -> set[int]:
    with _LOCK:
        return set(_LIVE)


def abort_all() -> int:
    """Chặn chuyển đổi mới và `SIGKILL` nhóm tiến trình của mọi chuyển đổi đang chạy. Trả số nhóm đã giết. Chủ của mỗi chuyển đổi (luồng đang `wait`) tự thu xác con trực tiếp và dọn thư mục tạm."""
    ABORT.set()
    with _LOCK:
        pids = list(_LIVE)
    for pid in pids:
        try:
            os.killpg(pid, signal.SIGKILL)  # `start_new_session=True`: pgid == pid
        except ProcessLookupError:
            pass
    return len(pids)


def wait_idle(timeout_s: float) -> bool:
    """Chờ tới khi không còn chuyển đổi nào đang chạy (chủ của chúng đã thu xác con trực tiếp). `True` nếu rỗng trong hạn."""
    import time
    deadline = time.monotonic() + timeout_s
    while live_pids():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)
    return True


def reset_abort() -> None:
    ABORT.clear()


def _track(proc: subprocess.Popen) -> None:
    with _LOCK:
        _LIVE.add(proc.pid)


def _untrack(proc: subprocess.Popen) -> None:
    with _LOCK:
        _LIVE.discard(proc.pid)


def available() -> bool:
    return shutil.which(SOFFICE) is not None


def soffice_version(*, timeout_s: float) -> str:
    """Chạy `soffice --headless --version` (B8c, O1-19): kiểm nhẹ rằng LibreOffice chạy được, trả dòng phiên bản (vd. `LibreOffice 25.2.3.2 520(Build:2)`) để log lúc khởi động (A-094). Không mở tài liệu, không chuyển đổi.
    Quá hạn thì giết cả nhóm tiến trình và `ConversionTimeout`. Đầu ra của `soffice` ngoài dòng phiên bản bị bỏ — không vào thông điệp lỗi."""
    try:
        proc = subprocess.Popen([SOFFICE, "--headless", "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, start_new_session=True)
    except OSError:
        raise VersionFailed from None
    _track(proc)
    try:
        out, _ = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        proc.stdout.close()
        raise ConversionTimeout from None
    except BaseException:
        _kill_group(proc)
        proc.stdout.close()
        raise
    finally:
        _untrack(proc)
    line = next((l.strip() for l in out.splitlines() if l.strip().startswith("LibreOffice")), None)
    if proc.returncode != 0 or line is None:
        raise VersionFailed
    return line[:100]


def soffice_command(workdir: Path, source: Path) -> list[str]:
    return [SOFFICE, "--headless", "--norestore", "--nolockcheck", f"-env:UserInstallation={(workdir / 'profile').as_uri()}",
            "--convert-to", "pdf", "--outdir", str(workdir / "out"), str(source)]


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # `start_new_session=True`: pgid == pid
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:  # không còn gì để làm — tiến trình không chết khi SIGKILL; bỏ, thư mục tạm vẫn được dọn
        pass


def _looks_like_docx(data: bytes) -> bool:
    """`soffice` nhận bất kỳ byte nào mang đuôi `.docx` và dựng PDF từ nó như văn bản thô (đo ở B8b): kiểm trước rằng đây là một gói OOXML có `word/document.xml`."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return "word/document.xml" in zf.namelist()
    except zipfile.BadZipFile:
        return False


def convert_to_pdf(docx: bytes, *, timeout_s: float, tmp_root: str | None = None) -> bytes:
    if not _looks_like_docx(docx):
        raise ConversionFailed
    if ABORT.is_set():
        raise ConversionAborted
    workdir = Path(tempfile.mkdtemp(prefix="bo19-convert-", dir=tmp_root))
    try:
        (workdir / "out").mkdir()
        source = workdir / "input.docx"
        source.write_bytes(docx)
        env = {**os.environ, "HOME": str(workdir)}
        try:
            proc = subprocess.Popen(soffice_command(workdir, source), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, start_new_session=True)
        except OSError:
            raise ConversionFailed from None
        _track(proc)
        if ABORT.is_set():  # `abort_all` chạy giữa `Popen` và `_track`: nó không thấy nhóm này
            _kill_group(proc)
            _untrack(proc)
            raise ConversionAborted
        try:
            code = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            raise ConversionTimeout from None
        except BaseException:
            _kill_group(proc)  # bị ngắt giữa chừng (tắt êm, cờ huỷ): không để lại tiến trình mồ côi
            raise
        finally:
            _untrack(proc)
        _kill_group(proc)  # tiến trình con còn sót (soffice.bin) thì dọn nốt; nhóm đã chết thì không làm gì
        if ABORT.is_set():
            raise ConversionAborted
        out = workdir / "out" / "input.pdf"
        if code != 0 or not out.is_file():
            raise ConversionFailed
        data = out.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise ConversionFailed
        return data
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
