# LangSmith — khi nào tracing bật, và tên các biến môi trường

- **Nguồn:** mã nguồn trong wheel chính thức trên PyPI, tải bằng `pip download --no-deps`:
  - `langsmith-0.14.1-py3-none-any.whl` — sha256 `dcfd8a25ba72d8663024bd87df02e372e470f43e18f4a726f37fbacc772c0193`
  - `langchain_core-1.6.5-py3-none-any.whl` — sha256 `54c7b0e9314b9084fb04405bb33dc5d32986d512d92b7b8863899cd5f6267556`
  - `langgraph-1.2.11-py3-none-any.whl` — sha256 `8bab70de7b2d00b5300fb289bcf38d8b241400f3184c1e95e8ce706fb0e8686b`
- **Ngày lấy:** 2026-09-27.
- **Phiên bản mà nguồn mô tả:** `langsmith` **0.14.1**, `langchain-core` **1.6.5**, `langgraph` **1.2.11** — đúng các bản của lần cài thử `backend/pyproject.toml` ngày 2026-09-26 (mục ngày đó của `docs/design/CHANGELOG.md`). `langsmith` và `langchain-core` là phụ thuộc bắc cầu, **chưa ghim**.
- **Dùng cho:** A-082. Mọi trích dẫn mã là nguyên văn, chép bằng script từ file trong wheel.
- **Phải đối chiếu lại khi lockfile chốt bản (A-081, ADR-030).** Lock chốt bản khác 0.14.1 / 1.6.5 thì lấy lại đúng các file dưới đây từ wheel của bản đó và so từng đoạn — tên biến và điều kiện bật có thể đổi giữa các bản.

---

## 1. Điều kiện bật tracing — `langsmith`

`langsmith/utils.py`, dòng 121–142:

```python
def tracing_is_enabled(ctx: Optional[dict] = None) -> Union[bool, Literal["local"]]:
    """Return True if tracing is enabled."""
    # Access global fallbacks via context module to avoid stale references.
    import langsmith._internal._context as _context
    from langsmith.run_helpers import get_current_run_tree, get_tracing_context

    tc = ctx or get_tracing_context()
    # You can manually override the environment using context vars.
    # Check that first.
    # Doing this before checking the run tree lets us
    # disable a branch within a trace.
    if tc["enabled"] is not None:
        return tc["enabled"]
    # Next check if we're mid-trace
    if get_current_run_tree():
        return True
    # If a global fallback was configured, use it next.
    if _context._GLOBAL_TRACING_ENABLED is not None:
        return _context._GLOBAL_TRACING_ENABLED
    # Finally, check the global environment
    var_result = get_env_var("TRACING_V2", default=get_env_var("TRACING", default=""))
    return var_result == "true"
```

Thứ tự: cờ trong context → đang ở giữa một trace → cấu hình toàn cục do mã gọi `configure(enabled=…)` → **biến môi trường**. Nhánh biến môi trường chỉ trả `True` khi giá trị **đúng bằng chuỗi `"true"`**.

`langsmith/utils.py`, dòng 418–442:

```python
@functools.lru_cache(maxsize=100)
def get_env_var(
    name: str,
    default: Optional[str] = None,
    *,
    namespaces: tuple = ("LANGSMITH", "LANGCHAIN"),
) -> Optional[str]:
    """Retrieve an environment variable from a list of namespaces.

    Args:
        name: The name of the environment variable.
        default: The default value to return if the environment variable is not found.
        namespaces: A tuple of namespaces to search for the environment variable.

            Defaults to `('LANGSMITH', 'LANGCHAINs')`.

    Returns:
        The value of the environment variable if found, otherwise the default value.
    """
    names = [f"{namespace}_{name}" for namespace in namespaces]
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip() != "":
            return value
    return default
```

Mỗi tên được tìm với hai tiền tố, `LANGSMITH_` trước, `LANGCHAIN_` sau. Giá trị rỗng hoặc chỉ có khoảng trắng coi như không đặt. Vì `TRACING_V2` được đọc trước và `TRACING` chỉ là giá trị mặc định của nó, **`*_TRACING_V2` đặt khác rỗng thì thắng `*_TRACING`**.

Địa chỉ gửi trace khi bật:

`langsmith/utils.py`, dòng 879–890:

```python
def get_api_url(api_url: Optional[str]) -> str:
    """Get the LangSmith API URL from the environment or the given value."""
    _api_url = api_url or cast(
        str,
        get_env_var(
            "ENDPOINT",
            default="https://api.smith.langchain.com",
        ),
    )
    if not _api_url.strip():
        raise LangSmithUserError("LangSmith API URL cannot be empty")
    return _api_url.strip().strip('"').strip("'").rstrip("/")
```

## 2. Chế độ gửi — `langsmith`

`langsmith/client.py`, dòng 240–305:

```python
def _resolve_tracing_mode(
    tracing_mode: Optional[TracingMode],
    *,
    otel_enabled: Optional[bool] = None,
) -> TracingMode:
    """Resolve the effective tracing mode from the constructor arg and env vars.

    Priority: explicit ``tracing_mode`` argument >
    deprecated ``otel_enabled`` argument >
    ``LANGSMITH_TRACING_MODE`` env var >
    legacy ``OTEL_ENABLED`` / ``OTEL_ONLY`` env vars >
    default ``"langsmith"``.
    """
    mode_envvar_name = "TRACING_MODE"
    otel_enabled_envvar_name = "OTEL_ENABLED"
    otel_only_envvar_name = "OTEL_ONLY"

    env_mode = ls_utils.get_env_var(mode_envvar_name)

    if tracing_mode is not None:
        tracing_mode = tracing_mode.lower()  # type: ignore[assignment]
        if tracing_mode not in _VALID_TRACING_MODES:
            raise ls_utils.LangSmithUserError(
                f"Invalid tracing_mode={tracing_mode!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_TRACING_MODES))}"
            )
        return tracing_mode  # type: ignore[return-value]

    if otel_enabled is not None:
        warnings.warn(
            "The 'otel_enabled' parameter is deprecated and will be removed "
            "in the next minor version. Use 'tracing_mode' instead, e.g. "
            'Client(tracing_mode="hybrid") or Client(tracing_mode="otel").',
            FutureWarning,
            stacklevel=3,
        )
        if otel_enabled:
            if ls_utils.is_env_var_truish(otel_only_envvar_name):
                return "otel"
            return "hybrid"
        return "langsmith"

    if env_mode is not None:
        env_mode = env_mode.lower()
        if env_mode not in _VALID_TRACING_MODES:
            raise ls_utils.LangSmithUserError(
                f"Invalid LANGSMITH_TRACING_MODE={env_mode!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_TRACING_MODES))}"
            )
        legacy_otel = ls_utils.is_env_var_truish(otel_enabled_envvar_name)
        legacy_only = ls_utils.is_env_var_truish(otel_only_envvar_name)
        if legacy_otel or legacy_only:
            warnings.warn(
                f"Both LANGSMITH_{mode_envvar_name} and the legacy "
                f"LANGSMITH_{otel_enabled_envvar_name} / "
                f"LANGSMITH_{otel_only_envvar_name} env vars are set. "
                f"LANGSMITH_{mode_envvar_name} takes precedence.",
                stacklevel=3,
            )
        return env_mode  # type: ignore[return-value]

    # Fall back to legacy env vars
    if ls_utils.is_env_var_truish(otel_only_envvar_name):
        return "otel"
    if ls_utils.is_env_var_truish("OTEL_ENABLED"):
        return "hybrid"
```

`TRACING_MODE`, `OTEL_ENABLED`, `OTEL_ONLY` chọn **nơi gửi** — LangSmith, OpenTelemetry, hay cả hai — **khi tracing đã bật**. Chúng không tự bật tracing. Chế độ OpenTelemetry đọc thêm `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_SERVICE_NAME` trong `langsmith/_internal/otel/_otel_client.py`.

## 3. `langchain-core` gắn tracer theo đúng điều kiện đó

`langchain_core/tracers/context.py`, dòng 132–135:

```python
def _tracing_v2_is_enabled() -> bool | Literal["local"]:
    if tracing_v2_callback_var.get() is not None:
        return True
    return ls_utils.tracing_is_enabled()
```

`langchain_core/callbacks/manager.py`, dòng 2492–2506:

```python
    v1_tracing_enabled_ = env_var_is_set("LANGCHAIN_TRACING") or env_var_is_set(
        "LANGCHAIN_HANDLER"
    )

    tracer_v2 = tracing_v2_callback_var.get()
    tracing_v2_enabled_ = _tracing_v2_is_enabled()

    if v1_tracing_enabled_ and not tracing_v2_enabled_:
        # if both are enabled, can silently ignore the v1 tracer
        msg = (
            "Tracing using LangChainTracerV1 is no longer supported. "
            "Please set the LANGCHAIN_TRACING_V2 environment variable to enable "
            "tracing instead."
        )
        raise RuntimeError(msg)
```

`langchain_core/utils/env.py`, dòng 9–23:

```python
def env_var_is_set(env_var: str) -> bool:
    """Check if an environment variable is set.

    Args:
        env_var: The name of the environment variable.

    Returns:
        `True` if the environment variable is set, `False` otherwise.
    """
    return env_var in os.environ and os.environ[env_var] not in {
        "",
        "0",
        "false",
        "False",
    }
```

Biến kiểu cũ `LANGCHAIN_TRACING` hay `LANGCHAIN_HANDLER` đặt khác `""`, `"0"`, `"false"`, `"False"` mà tracing kiểu mới không bật thì **`RuntimeError`** — tiến trình hỏng ở lần gọi đầu, không gửi gì.

`langgraph` 1.2.11 chỉ dùng `langsmith` để truyền context tracing (`langgraph/_internal/_runnable.py`) và nhãn `langsmith:hidden` (`langgraph/constants.py`); không có đường bật tracing riêng. Đã tìm bằng `grep -rn langsmith` trong wheel.

## 4. Phép thử hành vi

Venv Python 3.11.9, cài `langsmith==0.14.1 langchain-core==1.6.5`. Mỗi ca: một tiến trình con, **xoá mọi biến `LANGSMITH_*`, `LANGCHAIN_*`** rồi đặt đúng biến của ca, chạy một `RunnableLambda`, chờ tracer, rồi đếm số lần `socket.connect` — hàm này bị vá để ghi địa chỉ và từ chối kết nối, nên không gì rời máy. Ca có bật tracing đặt kèm một `LANGSMITH_API_KEY` giả.

```text
không đặt biến nào                                      -> {"langsmith.tracing_is_enabled": false, "langchain_core._tracing_v2_is_enabled": false, "invoke": 2, "connect_attempts": 0, "targets": []}
LANGSMITH_TRACING=true                                  -> {"langsmith.tracing_is_enabled": true, "langchain_core._tracing_v2_is_enabled": true, "invoke": 2, "connect_attempts": 16, "targets": ["('34.8.121.39', 443)"]}
LANGCHAIN_TRACING_V2=true                               -> {"langsmith.tracing_is_enabled": true, "langchain_core._tracing_v2_is_enabled": true, "invoke": 2, "connect_attempts": 16, "targets": ["('34.8.121.39', 443)"]}
LANGSMITH_TRACING_V2=true                               -> {"langsmith.tracing_is_enabled": true, "langchain_core._tracing_v2_is_enabled": true, "invoke": 2, "connect_attempts": 16, "targets": ["('34.8.121.39', 443)"]}
LANGSMITH_TRACING=True (hoa)                            -> {"langsmith.tracing_is_enabled": false, "langchain_core._tracing_v2_is_enabled": false, "invoke": 2, "connect_attempts": 0, "targets": []}
LANGSMITH_TRACING=1                                     -> {"langsmith.tracing_is_enabled": false, "langchain_core._tracing_v2_is_enabled": false, "invoke": 2, "connect_attempts": 0, "targets": []}
LANGSMITH_TRACING_V2=false + LANGSMITH_TRACING=true     -> {"langsmith.tracing_is_enabled": false, "langchain_core._tracing_v2_is_enabled": false, "invoke": 2, "connect_attempts": 0, "targets": []}
LANGSMITH_OTEL_ENABLED=true, không bật tracing          -> {"langsmith.tracing_is_enabled": false, "langchain_core._tracing_v2_is_enabled": false, "invoke": 2, "connect_attempts": 0, "targets": []}
LANGSMITH_API_KEY đặt, không bật tracing                -> {"langsmith.tracing_is_enabled": false, "langchain_core._tracing_v2_is_enabled": false, "invoke": 2, "connect_attempts": 0, "targets": []}
LANGCHAIN_TRACING=1 (v1)                                -> {"langsmith.tracing_is_enabled": false, "langchain_core._tracing_v2_is_enabled": false, "error": "RuntimeError: Tracing using LangChainTracerV1 is no longer supported. Please set the LANGCHAIN_TRACING_V2 environment variable to enable tracing instead.", "connect_attempts": 0, "targets": []}
```

## 5. Kết luận cho A-082 — với đúng các bản trên

| Câu hỏi | Trả lời | Căn cứ |
|---|---|---|
| Không đặt biến nào thì có gửi gì ra ngoài không | **Không** — 0 lần kết nối | Mục 4, ca đầu |
| Biến nào bật tracing | `LANGSMITH_TRACING_V2`, `LANGCHAIN_TRACING_V2`, `LANGSMITH_TRACING`, `LANGCHAIN_TRACING` — giá trị **đúng bằng `"true"`** | Mục 1; mục 4 |
| Có bật bằng `True`, `1` không | Không — so khớp chính xác chữ thường | Mục 1; mục 4 |
| `*_TRACING_V2=false` và `*_TRACING=true` cùng lúc | Không bật — `TRACING_V2` được đọc trước | Mục 1; mục 4 |
| Chỉ đặt `LANGSMITH_API_KEY`, hay chỉ `LANGSMITH_OTEL_ENABLED` | Không bật | Mục 2; mục 4 |
| Khi bật thì gửi đi đâu | `LANGSMITH_ENDPOINT` / `LANGCHAIN_ENDPOINT`, mặc định `https://api.smith.langchain.com`; hoặc OpenTelemetry theo `*_TRACING_MODE`, `*_OTEL_*` | Mục 1; mục 2 |
| Mã gọi có tự bật được không | Có — `configure(enabled=True)`, context manager, hay decorator của `langsmith`. Dự án không gọi các API đó; luật import của `06-structure.md` là chỗ chặn | Mục 1 |

**Đầu vào cho bước kiểm khởi động của A-082** — đề xuất, chưa áp vào `06-structure.md`: từ chối khởi động khi **bất kỳ** biến nào trong `LANGSMITH_TRACING`, `LANGSMITH_TRACING_V2`, `LANGCHAIN_TRACING`, `LANGCHAIN_TRACING_V2` được đặt **khác rỗng — bất kể giá trị**. Chặt hơn điều kiện thật của thư viện (chỉ `"true"`), để không phụ thuộc cách một bản sau đọc giá trị.
