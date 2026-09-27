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

**Không suy ra được thời lượng trên Render.** Một lần đo, 20 mẫu, trên máy tính cá nhân đang chạy việc khác. Số CPU và RAM của instance Render chưa biết (A-002), mà `parallelism = 4` nghĩa là bốn luồng tính song song.

## 5. Kết luận cho A-048 — với đúng bản trên

| Câu hỏi | Trả lời | Căn cứ |
|---|---|---|
| Mặc định của thư viện | `argon2id`, `time_cost=3`, `memory_cost=65536` KiB, `parallelism=4`, salt 16 byte, hash 32 byte | Mục 1, mục 2 |
| Chuỗi hash có mang tham số không | Có — `m=65536,t=3,p=4` nằm trong chuỗi mã hoá | Mục 4 |
| Đổi tham số có làm hash cũ hết verify được không | **Không.** Một `PasswordHasher(time_cost=2, memory_cost=32768, parallelism=1)` verify đúng hash tạo bằng `RFC_9106_LOW_MEMORY`; `check_needs_rehash` trả `True` | Mục 4b |
| Ứng dụng có hash lại được khi đăng nhập không | **Không**, vì `bo19_app` chỉ đọc `employee_credential`. Hash lại là thao tác vận hành, như đặt lại mật khẩu | A-048 H1; mục 3 |
