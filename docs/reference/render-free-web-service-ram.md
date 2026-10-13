# Render — RAM của Web Service gói Free (B8b)

- **Nguồn:** `https://render.com/docs/free.md` và `https://render.com/docs/compute-plans.md`, lấy bằng `curl` (Render phục vụ bản markdown của trang). Bản gốc lưu nguyên văn ở `render-docs-raw/free-20261013.md` (sha256 `4275ccede46bdab6537396e25b4c1268ab18200c40ab068b126c7252dd2c03b8`) và `render-docs-raw/compute-plans-20261013.md` (sha256 `960ee1c719b931354ab5a66854ab308a5a67361a035d9f85927cba567699fb07`).
- **Ngày lấy:** 2026-10-13. Tài liệu của dịch vụ, không số phiên bản; Render có thể đổi sau ngày này.
- **Dùng cho:** B8b — đo bộ nhớ của `soffice` và tiến trình `worker` trên mức giới hạn của gói Free; Q4 (trần kích thước file tải × số tải đồng thời); `docs/design/proposals/b8b-ke-hoach.md`.

## Câu chữ nguyên văn

`free.md`, mục `compute plan`:

> Specifies the CPU and RAM available to your service's *instances*.
> Common compute plans for a new web service include:
> - *`free`*: 0.1 CPU / 512 MB RAM
> - *`0.5c-512mb`*: 0.5 CPU / 512 MB RAM
> - *`1c-2g`*: 1 CPU / 2 GB RAM

`compute-plans.md`, bảng cho web service:

> | 0.1 CPU | 512 MB | [*`free`*](free) |  |

## Điều rút ra, và điều không rút ra

- **Giới hạn dùng để đo: 512 MB RAM, 0,1 CPU**, cho **mỗi instance** của một Web Service Free. Đây là con số duy nhất tài liệu nêu cho gói Free.
- Tài liệu **không** nói con số đó tính cho riêng tiến trình hay cho cả container (gồm tiến trình con như `soffice`) — người đo coi là **cả container** (bi quan), vì cgroup của container áp cho mọi tiến trình trong nó. Điều này là suy luận, không phải câu của nguồn.
- Tài liệu (hai trang đã lấy) **không** mô tả điều gì xảy ra khi vượt (OOM kill hay khởi động lại) — `[CẦN XÁC MINH]`, không đoán.
- Tài liệu **không** nêu số CPU theo giây hay giới hạn băng thông của gói Free ngoài "0.1 CPU": thời gian chuyển đổi đo trên máy phát triển không đại diện — một lý do đo CPU bị bóp (`docker run --cpus=0.1`) được ghi riêng ở báo cáo B8b.
