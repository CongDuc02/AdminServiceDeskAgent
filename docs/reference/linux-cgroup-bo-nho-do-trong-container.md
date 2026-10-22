# Linux cgroup — file bộ nhớ để đọc dùng hiện tại, đỉnh, giới hạn và `oom_kill` trong container (log `MEM_INFO`, A-095)

- **Lấy bằng `curl` ngày 2026-10-22** (07:53 UTC), không qua công cụ tóm tắt web; chữ đọc từ file HTML đã tải (bỏ thẻ, giải mã thực thể), các trích dẫn dưới đây **không đổi chữ nào** (chỉ gộp xuống dòng).

| Tài liệu | URL | sha256 (file HTML đã tải) |
|---|---|---|
| Control Group v2 — Linux kernel documentation | `https://docs.kernel.org/admin-guide/cgroup-v2.html` | `b478c1bae99899df476d6b4989cbb516f7ca93c5f009cdff64b802bbc24f3d4b` |
| Memory Resource Controller (cgroup v1) — Linux kernel documentation | `https://docs.kernel.org/admin-guide/cgroup-v1/memory.html` | `ec631bc47a0a36df246ed4285e0dbc025cd8200f691221085ee1e5eec6e198e3` |

**Phạm vi:** chỉ năm điều cần cho dòng log quan sát. Tài liệu này là bản "docs của kernel đang phát hành" tại ngày lấy — **không** nói kernel của Render Free là phiên bản nào (xem "Giới hạn" cuối). Không kết luận gì về mức dùng bộ nhớ của ứng dụng.

## cgroup v2 (`/sys/fs/cgroup/…` trong cgroup của container, file nằm ở thư mục của chính cgroup)

> **memory.current** — A read-only single value file which exists on non-root cgroups. The total amount of memory currently being used by the cgroup and its descendants.

> **memory.peak** — A read-write single value file which exists on non-root cgroups. The max memory usage recorded for the cgroup and its descendants since either the creation of the cgroup or the most recent reset for that FD. A write of any non-empty string to this file resets it to the current memory usage for subsequent reads through the same file descriptor.

> **memory.max** — A read-write single value file which exists on non-root cgroups. The default is "max". Memory usage hard limit. This is the main mechanism to limit memory usage of a cgroup. If a cgroup's memory usage reaches this limit and can't be reduced, the OOM killer is invoked in the cgroup. Under certain circumstances, the usage may go over the limit temporarily.

> **memory.events** — A read-only flat-keyed file which exists on non-root cgroups. […] **oom_kill** — The number of processes belonging to this cgroup killed by any kind of OOM killer.

Đọc ra: `memory.current`, `memory.peak`, `memory.max` là **một giá trị** (byte; `memory.max` có thể là chữ `max`); `memory.events` là các dòng `khoá số` (ví dụ `oom_kill 0`). Bản đọc không ghi vào `memory.peak` (ghi sẽ đặt lại đỉnh cho cùng file descriptor — nên dòng log **không** ghi vào file này).

**Dùng "memory.current" nói gì:** nó là **tổng bộ nhớ cgroup đang dùng** theo chữ của tài liệu; tài liệu ở đoạn trích **không** nói riêng việc có gồm bộ nhớ đệm trang (page cache) của file hay không (mô tả chi tiết ở `memory.stat`, chưa trích). Vì vậy dòng log chỉ gọi nó là "dùng hiện tại của cgroup".

## cgroup v1 (`/sys/fs/cgroup/memory/…`)

> **memory.usage_in_bytes** — show current usage for memory (See 5.5 for details)
> **memory.limit_in_bytes** — set/show limit of memory usage
> **memory.max_usage_in_bytes** — show max memory usage recorded
> **oom_kill** (đọc từ `memory.oom_control`) — oom_kill integer counter. The number of processes belonging to this cgroup killed by any kind of OOM killer.

## Giới hạn nói thẳng

- Không biết kernel và phiên bản cgroup của Render Free trước khi đọc ở đó. Dòng log tự chọn v2 nếu có `memory.current`, ngược lại v1; trường nào không đọc được ghi `null` — **không bịa số**.
- `memory.peak` (v2) tài liệu hiện tại mô tả kèm cơ chế đặt lại theo file descriptor; kernel cũ hơn có thể không có file này. Khi không có, dòng log vẫn có **đỉnh đo bằng lấy mẫu** (mỗi 1 s), vốn **có thể bỏ sót đỉnh ngắn hơn 1 s**.
- "Đỉnh trong job" của dòng log là đỉnh lấy mẫu trong thời gian job; `peak` của cgroup là đỉnh **từ lúc cgroup được tạo** (không phải riêng job).
