# `argon2-cffi` — tham số mặc định, và thời lượng verify đo trên máy người triển khai

- **Nguồn:** mã nguồn trong wheel chính thức trên PyPI, tải bằng `pip download --no-deps argon2-cffi`: `argon2_cffi-25.1.0-py3-none-any.whl` — sha256 `fdc8b074db390fccb6eb4a3604ae7231f219aa669a2652e0f20e16ba513d5741`.
- **Ngày lấy:** 2026-09-27.
- **Phiên bản mà nguồn mô tả:** `argon2-cffi` **25.1.0**; khi đo, `argon2-cffi-bindings` **26.1.0** — đọc từ metadata gói đã cài.
- **Dùng cho:** A-048 — đề xuất giá trị làm việc cho tham số `argon2id` (`docs/design/proposals/sprint1-working-values-a031-a048.md`).
- **Không phải quyết định chọn thư viện.** ADR-021 để tên và phiên bản thư viện hash cho BUILD MODE (`[CẦN XÁC MINH]` ở `backend/pyproject.toml`). `argon2-cffi` ở đây là **ứng viên**. Chọn thư viện khác thì tài liệu này không còn là căn cứ.
- **Về RFC 9106:** chú thích trong mã gọi hai bộ tham số là khuyến nghị "per RFC 9106". Đó là lời của thư viện. Bản gốc RFC chưa có trong `docs/reference/`, nên thiết kế **không** trích RFC — nội dung khuyến nghị của RFC `[CẦN XÁC MINH]`.

---

## 1. Bộ tham số có tên

`argon2/profiles.py`, dòng 20–57:

```python
def get_default_parameters() -> Parameters:
    """
    Create default parameters for current platform.

    Returns:
        Default, compatible, parameters for current platform.

    .. versionadded:: 25.1.0
    """
    params = RFC_9106_LOW_MEMORY

    if _is_wasm():
        params = dataclasses.replace(params, parallelism=1)

    return params


# FIRST RECOMMENDED option per RFC 9106.
RFC_9106_HIGH_MEMORY = Parameters(
    type=Type.ID,
    version=19,
    salt_len=16,
    hash_len=32,
    time_cost=1,
    memory_cost=2097152,  # 2 GiB
    parallelism=4,
)

# SECOND RECOMMENDED option per RFC 9106.
RFC_9106_LOW_MEMORY = Parameters(
    type=Type.ID,
    version=19,
    salt_len=16,
    hash_len=32,
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
)
```

`memory_cost` tính bằng KiB — chú thích cùng dòng ghi `64 MiB` cho `65536`.

## 2. Tham số mặc định của `PasswordHasher`

`argon2/_password_hasher.py`, dòng 22–26:

```python
DEFAULT_RANDOM_SALT_LENGTH = default_params.salt_len
DEFAULT_HASH_LENGTH = default_params.hash_len
DEFAULT_TIME_COST = default_params.time_cost
DEFAULT_MEMORY_COST = default_params.memory_cost
DEFAULT_PARALLELISM = default_params.parallelism
```

`default_params` là kết quả của `get_default_parameters()` ở mục 1. Không chạy trên WebAssembly thì đó chính là `RFC_9106_LOW_MEMORY`.

## 3. Đổi tham số về sau — thư viện đòi ghi lại hash

`argon2/_password_hasher.py`, dòng 262–283:

```python
    def check_needs_rehash(self, hash: str | bytes) -> bool:
        """
        Check whether *hash* was created using the instance's parameters.

        Whenever your Argon2 parameters -- or *argon2-cffi*'s defaults! --
        change, you should rehash your passwords at the next opportunity.  The
        common approach is to do that whenever a user logs in, since that
        should be the only time when you have access to the cleartext
        password.

        Therefore it's best practice to check -- and if necessary rehash --
        passwords after each successful authentication.

        Args:
            hash: An encoded Argon2 password hash.

        Returns:
            Whether *hash* was created using the instance's parameters.

        .. versionadded:: 18.2.0
        .. versionchanged:: 24.1.0 Accepts bytes for *hash*.
        """
```

**Va chạm với thiết kế:** thư viện khuyên hash lại mật khẩu ngay sau lần đăng nhập thành công. Ở BO-19, `bo19_app` **chỉ đọc** `employee_credential` (A-048, H1), nên ứng dụng không làm được việc đó. Hệ quả ở mục 5.

## 4. Phép đo

Venv Python 3.11.9 trên Windows 11 của người triển khai. CPU theo `platform.processor()`: `AMD64 Family 23 Model 96 Stepping 1, AuthenticAMD`, 12 CPU logic. Script:

```python
import time, statistics, argon2, platform, os
from argon2 import PasswordHasher, profiles
from importlib.metadata import version
ph = PasswordHasher.from_parameters(profiles.RFC_9106_LOW_MEMORY)
h = ph.hash("mat-khau-thu-nghiem")
ts = []
for _ in range(20):
    t = time.perf_counter(); ph.verify(h, "mat-khau-thu-nghiem"); ts.append(time.perf_counter() - t)
ts.sort()
print("argon2-cffi", version("argon2-cffi"), "argon2-cffi-bindings", version("argon2-cffi-bindings"))
print("cpu", platform.processor(), "logical cpus", os.cpu_count())
print("hash:", h.split("$")[1:4])
print("verify ms: min %.1f median %.1f max %.1f (n=20)" % (ts[0]*1000, statistics.median(ts)*1000, ts[-1]*1000))
```

Kết quả:

```text
argon2-cffi 25.1.0 argon2-cffi-bindings 26.1.0
cpu AMD64 Family 23 Model 96 Stepping 1, AuthenticAMD logical cpus 12
hash: ['argon2id', 'v=19', 'm=65536,t=3,p=4']
verify ms: min 250.2 median 424.5 max 605.0 (n=20)
```

### 4b. Đổi tham số — hash cũ còn verify được không

```python
from argon2 import PasswordHasher, profiles
old = PasswordHasher.from_parameters(profiles.RFC_9106_LOW_MEMORY)
h = old.hash("mk")
new = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=1)
print("hash cu:", h.split("$")[3])
print("hasher moi verify hash cu:", new.verify(h, "mk"))
print("check_needs_rehash:", new.check_needs_rehash(h))
```

```text
hash cu: m=65536,t=3,p=4
hasher moi verify hash cu: True
check_needs_rehash: True
```

### 4c. Bộ nhớ đỉnh và thời lượng khi verify đồng thời

Mỗi cấu hình một tiến trình con: hash một lần, đọc `PeakWorkingSetSize` (`K32GetProcessMemoryInfo`), rồi chạy N lần verify **đồng thời** trên N luồng, đọc lại. Sáu cấu hình: mặc định của thư viện và năm cấu hình OWASP (`docs/reference/owasp-password-storage-argon2id.md`). Script:

```python
"""Đo bộ nhớ đỉnh và thời lượng khi N lần verify argon2id chạy đồng thời, mỗi cấu hình một tiến trình con."""
import ctypes, ctypes.wintypes as wt, json, statistics, subprocess, sys, threading, time

def peak_ws_mib():
    class PMC(ctypes.Structure):
        _fields_ = [('cb', wt.DWORD), ('PageFaultCount', wt.DWORD), ('PeakWorkingSetSize', ctypes.c_size_t),
                    ('WorkingSetSize', ctypes.c_size_t), ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaPagedPoolUsage', ctypes.c_size_t), ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                    ('QuotaNonPagedPoolUsage', ctypes.c_size_t), ('PagefileUsage', ctypes.c_size_t),
                    ('PeakPagefileUsage', ctypes.c_size_t)]
    c = PMC(); c.cb = ctypes.sizeof(PMC)
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.GetCurrentProcess.restype = wt.HANDLE
    k.K32GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
    k.K32GetProcessMemoryInfo.restype = wt.BOOL
    assert k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.PeakWorkingSetSize / 2**20

if len(sys.argv) > 1:
    t, m, p, n = map(int, sys.argv[1:5])
    from argon2 import PasswordHasher
    ph = PasswordHasher(time_cost=t, memory_cost=m, parallelism=p)
    h = ph.hash("mk")
    base = peak_ws_mib()
    durs = []
    def w():
        s = time.perf_counter(); ph.verify(h, "mk"); durs.append(time.perf_counter() - s)
    th = [threading.Thread(target=w) for _ in range(n)]
    s0 = time.perf_counter(); [x.start() for x in th]; [x.join() for x in th]; wall = time.perf_counter() - s0
    print(json.dumps({'t': t, 'm_KiB': m, 'p': p, 'dong_thoi': n, 'peak_truoc_MiB': round(base, 1),
                      'peak_sau_MiB': round(peak_ws_mib(), 1), 'wall_ms': round(wall * 1000),
                      'verify_ms_max': round(max(durs) * 1000)}))
    sys.exit()

cfgs = [(3, 65536, 4), (1, 47104, 1), (2, 19456, 1), (3, 12288, 1), (4, 9216, 1), (5, 7168, 1)]
for t, m, p in cfgs:
    for n in (1, 4):
        print(subprocess.run([sys.executable, __file__, str(t), str(m), str(p), str(n)], capture_output=True, text=True).stdout.strip())
```

Kết quả:

```text
{"t": 3, "m_KiB": 65536, "p": 4, "dong_thoi": 1, "peak_truoc_MiB": 82.8, "peak_sau_MiB": 82.8, "wall_ms": 226, "verify_ms_max": 224}
{"t": 3, "m_KiB": 65536, "p": 4, "dong_thoi": 4, "peak_truoc_MiB": 82.6, "peak_sau_MiB": 274.9, "wall_ms": 879, "verify_ms_max": 866}
{"t": 1, "m_KiB": 47104, "p": 1, "dong_thoi": 1, "peak_truoc_MiB": 64.4, "peak_sau_MiB": 64.6, "wall_ms": 215, "verify_ms_max": 210}
{"t": 1, "m_KiB": 47104, "p": 1, "dong_thoi": 4, "peak_truoc_MiB": 64.5, "peak_sau_MiB": 199.4, "wall_ms": 413, "verify_ms_max": 408}
{"t": 2, "m_KiB": 19456, "p": 1, "dong_thoi": 1, "peak_truoc_MiB": 37.5, "peak_sau_MiB": 37.7, "wall_ms": 114, "verify_ms_max": 110}
{"t": 2, "m_KiB": 19456, "p": 1, "dong_thoi": 4, "peak_truoc_MiB": 37.5, "peak_sau_MiB": 94.8, "wall_ms": 245, "verify_ms_max": 230}
{"t": 3, "m_KiB": 12288, "p": 1, "dong_thoi": 1, "peak_truoc_MiB": 30.5, "peak_sau_MiB": 30.6, "wall_ms": 56, "verify_ms_max": 53}
{"t": 3, "m_KiB": 12288, "p": 1, "dong_thoi": 4, "peak_truoc_MiB": 30.6, "peak_sau_MiB": 66.8, "wall_ms": 135, "verify_ms_max": 131}
{"t": 4, "m_KiB": 9216, "p": 1, "dong_thoi": 1, "peak_truoc_MiB": 27.5, "peak_sau_MiB": 27.7, "wall_ms": 54, "verify_ms_max": 51}
{"t": 4, "m_KiB": 9216, "p": 1, "dong_thoi": 4, "peak_truoc_MiB": 27.4, "peak_sau_MiB": 54.7, "wall_ms": 122, "verify_ms_max": 116}
{"t": 5, "m_KiB": 7168, "p": 1, "dong_thoi": 1, "peak_truoc_MiB": 25.5, "peak_sau_MiB": 25.7, "wall_ms": 55, "verify_ms_max": 52}
{"t": 5, "m_KiB": 7168, "p": 1, "dong_thoi": 4, "peak_truoc_MiB": 25.6, "peak_sau_MiB": 46.9, "wall_ms": 121, "verify_ms_max": 117}
```

Cách đọc: `peak_truoc_MiB` đã gồm một lần hash, nên với N = 4, `peak_sau − peak_truoc` là **ba** lần verify chồng lên lần đã tính. Ví dụ mặc định: 274,9 − 82,8 = 192,1 MiB ≈ 3 × 64 MiB. **Bộ nhớ đỉnh tăng xấp xỉ `m` cho mỗi lần verify đang chạy.** Bốn lần verify chạy chồng nhau thật: nếu tuần tự, đỉnh đã không tăng.

**Không suy ra được thời lượng trên Render.** Một lần đo, 20 mẫu, trên máy tính cá nhân đang chạy việc khác. Số CPU và RAM của instance Render chưa biết (A-002), mà `parallelism = 4` nghĩa là bốn luồng tính song song.

## 5. Kết luận cho A-048 — với đúng bản trên

| Câu hỏi | Trả lời | Căn cứ |
|---|---|---|
| Mặc định của thư viện | `argon2id`, `time_cost=3`, `memory_cost=65536` KiB, `parallelism=4`, salt 16 byte, hash 32 byte | Mục 1, mục 2 |
| Chuỗi hash có mang tham số không | Có — `m=65536,t=3,p=4` nằm trong chuỗi mã hoá | Mục 4 |
| Đổi tham số có làm hash cũ hết verify được không | **Không.** Một `PasswordHasher(time_cost=2, memory_cost=32768, parallelism=1)` verify đúng hash tạo bằng `RFC_9106_LOW_MEMORY`; `check_needs_rehash` trả `True` | Mục 4b |
| Bộ nhớ một lần verify đang chạy | Xấp xỉ `m`. Mặc định, 4 lần đồng thời: đỉnh 274,9 MiB; nền ước tính 82,8 − 64 = 18,8 MiB, nên phần của verify khoảng 256 MiB | Mục 4c |
| Ứng dụng có hash lại được khi đăng nhập không | **Không**, vì `bo19_app` chỉ đọc `employee_credential`. Hash lại là thao tác vận hành, như đặt lại mật khẩu | A-048 H1; mục 3 |
