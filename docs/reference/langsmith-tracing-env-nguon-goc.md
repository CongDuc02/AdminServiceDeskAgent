# LangSmith — tên biến môi trường liên quan tới tracing, lấy từ nguồn gốc bằng `curl` (đúng bản lock)

- **Ngày lấy:** 2026-10-05. **Cách lấy:** `curl -sS -L` — không công cụ tóm tắt web (`CLAUDE.md`, mục Luật thao tác). Excerpt dưới đây chép bằng script từ file đã tải; dòng là dòng của file nguồn.
- **Vì sao có file này, thêm vào `langsmith-tracing-env.md`:** file đó lấy từ **wheel PyPI** bằng `pip download`, ở bản `langsmith` 0.14.1 / `langchain-core` 1.6.5, và tự ghi *"Phải đối chiếu lại khi lockfile chốt bản"*. `backend/requirements-linux.lock` chốt **`langsmith==0.14.3`** và **`langchain-core==1.6.6`**. B2 (bước kiểm khởi động #19) dùng file này làm căn cứ cho danh sách tên biến mà test phủ — PO, 2026-10-05: tên lấy từ tài liệu gốc, không từ trí nhớ.
- **Đối chiếu với bản 0.14.1:** thân hàm `tracing_is_enabled` (mục 1 dưới đây) **không đổi** giữa 0.14.1 và 0.14.3 — cùng hai lần `get_env_var`, cùng điều kiện `== "true"`.

## 0. Nguồn đã tải

| # | URL | Kích thước (byte) | sha256 |
|---|---|---|---|
| N1 | `https://raw.githubusercontent.com/langchain-ai/langsmith-sdk/v0.14.3/python/langsmith/utils.py` | 30448 | `3ae4af00e0456bafbc8329b8f50854e8f20b8db2b44254825af2395f73d8cc5c` |
| N2 | `https://raw.githubusercontent.com/langchain-ai/langsmith-sdk/v0.14.3/python/langsmith/client.py` | 476255 | `39519717f7d4e2ab349ceb567ecb47daf9d20b9daa7047d6f2eee46f11ebc730` |
| N3 | `https://raw.githubusercontent.com/langchain-ai/langsmith-sdk/v0.14.3/python/langsmith/_internal/_context.py` | 2110 | `efa94baa75fd55b73a9cc06095bde00164cda6ca2c190ecf9276737db0e38c30` |
| N4 | `https://raw.githubusercontent.com/langchain-ai/langchain/langchain-core%3D%3D1.6.6/libs/core/langchain_core/tracers/context.py` | 6226 | `149a9f5b662baec09d1a41555c60ed005b9d65d29d015bd1dae82a3c7be05dab` |
| N5 | `https://docs.langchain.com/langsmith/trace-with-langchain` (trang HTML) | 1476356 | `e5966d515b62b3d5f42a95fef5fda64d6f9cf4e5282934a2bdb609981983d416` |
| N6 | `https://docs.langchain.com/langsmith/env-var` (trang HTML) | 854742 | `8d5f909d5b0369520786b83c8dff0efeb55ed8146cc1bcb61f2cd3974fd4387f` |

N1 được giữ nguyên văn ở `docs/reference/langsmith-nguon/langsmith-0.14.3-utils.py.txt` (30 KB). N2 (476 KB) và hai trang HTML (đều trên 800 KB) **không** commit nguyên file — chỉ sha256 ở trên và các đoạn chép nguyên văn dưới đây; lấy lại bằng đúng URL rồi so sha256 (nội dung trang tài liệu có thể đổi theo thời gian — khi đó sha256 lệch, và chỉ các đoạn trích dưới đây là bằng chứng của ngày lấy). N3 và N4 đã tải để kiểm: không đọc biến môi trường nào có tên chứa `TRACING` hay bắt đầu bằng `LANGSMITH_`/`LANGCHAIN_` (chỉ gọi `ls_utils.tracing_is_enabled()` — N4 dòng 132–135).

## 1. Tên bật tracing — N1, `langsmith/utils.py`, dòng 121–143

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

`get_env_var` — N1, dòng 420–444:

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

Hệ quả, chỉ đọc từ hai đoạn trên: `get_env_var(name)` thử `LANGSMITH_<name>` rồi `LANGCHAIN_<name>`; giá trị rỗng hay chỉ có khoảng trắng coi như không đặt. `tracing_is_enabled` đọc `<name>` = `TRACING_V2`, rồi `TRACING`. Tracing bật khi giá trị tìm được **đúng bằng** `"true"`. Vậy **bốn tên** có thể bật tracing:

| Tên | Căn cứ |
|---|---|
| `LANGSMITH_TRACING_V2` | N1 dòng 141, tiền tố `LANGSMITH` (N1 dòng 425) |
| `LANGCHAIN_TRACING_V2` | N1 dòng 141, tiền tố `LANGCHAIN` (N1 dòng 425) |
| `LANGSMITH_TRACING` | N1 dòng 141 (đối số `default`), tiền tố `LANGSMITH` |
| `LANGCHAIN_TRACING` | N1 dòng 141 (đối số `default`), tiền tố `LANGCHAIN` |

## 2. Tên bật tracing — tài liệu sản phẩm

N5 (`trace-with-langchain`), bước *Configure your environment*, văn bản trang sau khi bỏ thẻ HTML:

> i @langchain/core Quick start 1. Configure your environment export LANGSMITH_TRACING = true export LANGSMITH_API_KEY =< your-api-key > # This example uses OpenAI, but you can use any LLM provider of choice export OPENAI_API_KEY =< your-openai-api-key > # For LangSmith API keys linked to multiple workspaces, set the LANGSMITH_WORKSPACE_ID environment variable to specify which workspace to

N6 (`env-var`), mục `LANGSMITH_TRACING`:

> ngoDB connection URI via LS_MONGODB_URI . LANGSMITH_TRACING Set LANGSMITH_TRACING to false to disable tracing to LangSmith. For selective tracing control based on runtime conditions (such as per-client requirements or data sensitivity), see Conditional tracing . Defaults to true . LOG_COLOR This is mainly relevant in the context of using the dev server via the langgraph dev command. Set 

Tài liệu nêu **một** tên: `LANGSMITH_TRACING`. Nó nằm trong bốn tên của mục 1.

## 3. Tên có chữ `TRACING` nhưng không tự bật tracing — N2, `langsmith/client.py`

Tất cả đọc qua `ls_utils.get_env_var(<name>)` với tiền tố mặc định `LANGSMITH`, `LANGCHAIN` (N1 dòng 425) — nên mỗi tên có **hai** dạng tiền tố.

```python
# N2 dòng 246–258
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

# N2 dòng 807
        sampling_rate_str = ls_utils.get_env_var("TRACING_SAMPLING_RATE")
# N2 dòng 1447
            queue_maxsize_str = ls_utils.get_env_var("TRACING_QUEUE_MAX_SIZE")
```

| Tên (hai tiền tố) | Việc |
|---|---|
| `LANGSMITH_TRACING_MODE`, `LANGCHAIN_TRACING_MODE` | Chọn nơi gửi khi tracing đã bật (N2 dòng 246–258) |
| `LANGSMITH_TRACING_SAMPLING_RATE`, `LANGCHAIN_TRACING_SAMPLING_RATE` | Tỉ lệ lấy mẫu (N2 dòng 807) |
| `LANGSMITH_TRACING_QUEUE_MAX_SIZE`, `LANGCHAIN_TRACING_QUEUE_MAX_SIZE` | Kích thước hàng đợi (N2 dòng 1447) |

Mẫu của #19 (tên bắt đầu bằng `LANGSMITH_`/`LANGCHAIN_` **và** chứa `TRACING`, bất kể giá trị) **bắt cả sáu tên này** — rộng hơn bốn tên bật thật. Đó là hành vi của đặc tả đã duyệt (A-082, 2026-09-27), không phải sơ suất: một biến cấu hình tracing có mặt thì không có lý do chính đáng nào ở nơi không được bật tracing.

## 4. Tên liên quan OpenTelemetry — không chứa `TRACING`, không tự bật tracing

```python
# N2 dòng 303–306
    if ls_utils.is_env_var_truish(otel_only_envvar_name):
        return "otel"
    if ls_utils.is_env_var_truish("OTEL_ENABLED"):
        return "hybrid"
```

`LANGSMITH_OTEL_ENABLED` và `LANGSMITH_OTEL_ONLY` (cùng dạng `LANGCHAIN_`) chỉ chọn nơi gửi — mục 3 của `langsmith-tracing-env.md` đã thử: đặt `LANGSMITH_OTEL_ENABLED=true` mà không bật tracing thì không có kết nối đi ra. Mẫu của #19 **không** bắt hai tên này, và test của B2 ghi đúng điều đó (một test riêng, nhãn rõ) — để ai muốn bắt thêm phải sửa mẫu ở đặc tả #19 trước, rồi sửa test.

## 5. Điều chưa xác minh bằng nguồn gốc

- `LANGCHAIN_TRACING` kiểu cũ (v1) và `LANGCHAIN_HANDLER` gây `RuntimeError` ở `langchain-core` 1.6.5 — `langsmith-tracing-env.md` mục 1, đã thử chạy. Ở 1.6.6 (N4) file `tracers/context.py` **không** còn đọc hai tên đó; chưa tải file khác của `langchain-core` 1.6.6 để kiểm chỗ khác. Không ảnh hưởng #19: `LANGCHAIN_TRACING` đã nằm trong bốn tên ở mục 1, `LANGCHAIN_HANDLER` không chứa `TRACING` — nếu gặp lại thì đó là mục để mở A-082.
- Chưa có bản `langchain` / `langgraph` nào khác đọc thêm tên tracing: `langgraph` 1.2.11 chỉ chuyển context (`langsmith-tracing-env.md` mục 1). Đối chiếu lại khi lock đổi bản (A-081).
