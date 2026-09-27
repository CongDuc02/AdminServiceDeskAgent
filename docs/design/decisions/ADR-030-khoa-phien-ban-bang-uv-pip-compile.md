# ADR-030 — Khoá phiên bản phụ thuộc Python bằng `uv pip compile`, image cài bằng `pip` thường

**Trạng thái:** Accepted · **Ngày:** 2026-09-27 · **Duyệt:** PO, 2026-09-27 — `Proposed` → `Accepted`, kèm bước CI ở mục Decision · **Quyết định tại:** A-081 (cổng 1.12 của `12-roadmap.md`) · **Liên quan:** A-045 (checkpointer đã xác minh), A-082 (`langsmith`), ADR-015 (một image cho mọi tiến trình), mục Đặc tả `Dockerfile` và mục Xác minh contract của `06-structure.md`, `backend/pyproject.toml`

---

## Context

`backend/pyproject.toml` là nguồn phụ thuộc duy nhất, ghim 17 phụ thuộc trực tiếp (AUD-25). Phụ thuộc bắc cầu không được ghim và trôi theo ngày cài: lần cài thử 2026-09-26 ra `langgraph-checkpoint` 4.2.0, `langchain-core` 1.6.5, `langsmith` 0.14.1 (A-081). A-045 đã xác minh checkpointer với `langgraph-checkpoint` 4.2.0; bản khác có thể đổi bảng hay hành vi `setup()`.

Ba ràng buộc của dự án quyết định lựa chọn:

1. **Máy khoá khác máy chạy.** Người triển khai làm việc trên Windows. Image chạy trên Render là Linux (ADR-015, mục Đặc tả `Dockerfile` của `06-structure.md`). Docker Desktop trên máy người triển khai không khởi động được (mục Xác minh contract của `06-structure.md`), nên không khoá được "bên trong image" ở local.
2. **Phụ thuộc có điều kiện theo nền tảng là có thật trong cây này.** Theo `Requires-Dist` trong `METADATA` của wheel `uvicorn` 0.34.2, extra `standard` kéo `uvloop` khi `sys_platform != 'win32'` (và không phải `cygwin`, không phải PyPy), còn kéo `colorama` khi `sys_platform == 'win32'`. Một lock khoá theo nền tảng của máy khoá sẽ sai trên nền tảng của image.
3. **Image cài được mà không cần thêm công cụ.** Mục Đặc tả `Dockerfile` chỉ đòi "cài phụ thuộc Python đúng theo lockfile, không có phụ thuộc dev".

## Options

- **A — `uv pip compile`**, đích là nền tảng và phiên bản Python của image, sinh file dạng requirements có hash cho mọi gói. Image cài bằng `pip install --require-hashes --no-deps -r <lock>` — `uv` không vào image.
- **B — `pip-compile` của `pip-tools`**, cùng định dạng file.
- **C — `uv lock` sinh `uv.lock`**, image cài bằng `uv sync`.
- **D — `pip freeze`** từ một venv đã cài chạy được.

### Đã thử — 2026-09-27, trong scratchpad, không file nào vào repo

Công cụ cài bằng `pip` vào một venv Python 3.11.9 trên Windows: `uv` **0.12.19**, `pip-tools` **7.6.1** — phiên bản đọc từ metadata của gói đã cài, không ghi từ trí nhớ.

| Phép thử | Kết quả |
|---|---|
| A: `uv pip compile pyproject.toml -c constraints.txt --python-platform x86_64-unknown-linux-gnu --python-version 3.11 --generate-hashes` — `constraints.txt` chỉ có `langgraph-checkpoint==4.2.0` | Thành công. **71 gói, 1570 hash.** Có `uvloop` 0.22.1 (chỉ Linux), không có `colorama`. `langgraph-checkpoint` 4.2.0, `langgraph-checkpoint-postgres` 3.1.2, `psycopg-binary` 3.3.5, `langsmith` 0.14.1 |
| A, cài thử: `pip install --dry-run --require-hashes --no-deps --only-binary=:all: --platform manylinux_2_28_x86_64 --python-version 3.11` trên chính file đó | Thành công — `pip` thường tải đủ **71** wheel Linux, **mọi hash khớp** |
| B: `pip-compile --help` | **Không có tuỳ chọn chọn nền tảng hay phiên bản Python đích** — chỉ có `--pip-args`. Khoá theo máy đang chạy |
| B: `pip-compile pyproject.toml -c constraints.txt --generate-hashes` trên Windows | Bắt đầu 20:49; tới 21:09 — lúc ghi ADR này — chưa xong, mạng chậm. Kết quả không đổi kết luận: không có tuỳ chọn đích, nên đích là Windows |
| C, D | **Không thử** |

## Decision

**Đề xuất A.**

- **Công cụ khoá:** `uv pip compile`, chạy ở máy người triển khai hoặc ở CI, đích là **nền tảng và phiên bản Python của image nền** — Linux x86_64, phiên bản Python chốt cùng lúc chọn image nền ở BUILD MODE. Phiên bản của chính `uv` ghi trong dòng đầu file lock.
- **File lock:** định dạng requirements, `--generate-hashes`, đặt cạnh `backend/pyproject.toml`. Tên file và vị trí chốt ở BUILD MODE.
- **Ghim bắt buộc qua constraint:** `langgraph-checkpoint==4.2.0` — bản đã chạy thật trong bộ kiểm của A-045. Đổi bản này thì chạy lại phép xác minh của A-045.
- **Image cài bằng `pip` thường:** `pip install --require-hashes --no-deps -r <lock>`. `uv` không vào image.
- **Bước CI, BUILD MODE — theo yêu cầu của PO khi duyệt:** một job chạy **trên runner Linux**, ở mọi thay đổi chạm `backend/pyproject.toml`, file lock hay file constraint:
  1. Cài đúng phiên bản `uv` ghi ở dòng đầu file lock.
  2. Sinh lại lock bằng **đúng lệnh** ghi ở dòng đầu file lock — cùng đích nền tảng, phiên bản Python, constraint và `--generate-hashes` — ra một file tạm.
  3. So file tạm với file đã commit. **Lệch một byte là job fail**, và merge bị chặn. Không tự sửa file đã commit trong CI.
  4. Cùng job, `pip install --require-hashes --no-deps -r <lock>` vào một venv sạch để chứng minh lock cài được trên Linux.

  Cùng khuôn với bước so type sinh từ `openapi.yaml` (mục Đặc tả `Dockerfile` của `06-structure.md`): cái sinh ra từ nguồn phải trùng cái đã commit. Chạy trên Linux vì đó là nền tảng của image — lệnh khoá đã nhắm Linux, nhưng phép so trên chính nền tảng đích loại thêm mọi khác biệt do máy chạy lệnh.
- **Sinh lock thật là việc của BUILD MODE** — sau cổng 1.1. ADR này chỉ chốt cách làm.

## Consequences

**Tích cực**

- Khoá được cho Linux từ máy Windows — không phụ thuộc Docker ở local.
- Hash của mọi gói: image không cài được gói nào khác bản đã khoá.
- Runtime không thêm công cụ: `pip` có sẵn trong image Python.
- Phụ thuộc bắc cầu hiện rõ trong một file đọc được — `langsmith` (A-082) nằm ngay trong đó.

**Tiêu cực và cái phải chấp nhận**

- Thêm một công cụ vào môi trường người triển khai và CI.
- Lock chỉ đúng cho một nền tảng. Người triển khai chạy local trên Windows không cài bằng lock này — cài từ `pyproject.toml`, hoặc sinh một lock thứ hai cho Windows. Test local và image có thể lệch nhau ở phụ thuộc có điều kiện theo nền tảng (`uvloop`, `colorama`).
- Kiến trúc CPU của instance Render — x86_64 hay khác — `[CẦN XÁC MINH]` theo tài liệu Render. Phép thử ở trên giả định x86_64.

**Điều kiện đảo ngược**

- Cần image cho hơn một nền tảng — xét C, vì một lock cho nhiều nền tảng là việc của định dạng đó; cần thử trước.
- `uv` không còn phát hành bản dùng được — lock đã sinh vẫn cài được bằng `pip`, chỉ phải đổi công cụ sinh lock.

## Rejected alternatives

**B — `pip-compile`.** Không có tuỳ chọn chọn nền tảng đích (`pip-compile --help`, bản 7.6.1). Muốn đúng cho Linux thì phải chạy trên Linux: ở CI thì người triển khai không tái lập được lock ở local, vì Docker Desktop không chạy được trên máy họ. Chạy trên Windows thì lock đúng cho Windows — thiếu `uvloop`, thừa `colorama`.

**C — `uv lock` và `uv sync`.** Không thử, nên không kết luận về năng lực. Loại theo ràng buộc 3: phải đưa `uv` vào image, trong khi A giữ image chỉ cần `pip`. Là hướng đảo ngược đầu tiên.

**D — `pip freeze`.** Chụp đúng môi trường của máy chạy lệnh, nên cùng vấn đề nền tảng như B. Không có hash nếu không thêm bước khác, và kéo theo cả gói không thuộc cây phụ thuộc nếu venv không sạch.
