# Debian 13 (trixie) — gói LibreOffice Writer không giao diện, fontconfig, poppler-utils (B8b)

- **Nguồn:** kho gói chính thức của Debian, truy vấn **bằng `apt-get update` và `apt-cache show` bên trong đúng image nền của dự án** `python:3.11-slim@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b` (Debian GNU/Linux 13 trixie; nguồn apt của image: `deb.debian.org/debian` suites `trixie trixie-updates` và `deb.debian.org/debian-security` suite `trixie-security`). Trang `packages.debian.org` trả trang kiểm tra bot cho `curl` — không dùng.
- **Ngày lấy:** 2026-10-13 (04:55 UTC). Kho gói thay đổi theo thời gian (bản cập nhật bảo mật thay bản cũ): **số phiên bản dưới đây là mốc ngày lấy, không phải phiên bản được ghim** — `Dockerfile` ghim image nền theo digest nhưng **không** ghim phiên bản gói apt (bản cũ biến mất khỏi kho khi có bản bảo mật); rủi ro ghi ở báo cáo B8b.
- **Dùng cho:** `Dockerfile` (ADR-015, ADR-036); đặc tả `Dockerfile` ở mục 6.2 của `docs/design/06-structure.md` (tên gói trước đó `[CẦN XÁC MINH]`).

## Kết quả `apt-cache show` (trích các trường)

| Gói | Version | Installed-Size (KiB) | Size tải (byte) | SHA256 của `.deb` |
|---|---|---|---|---|
| `libreoffice-writer-nogui` | `4:25.2.3-2+deb13u8` | 30171 | 9147984 | `294bf603202fa154c5fc73eccaa6ee25d045e2d6a61ebc3b894f324591f0ddd5` |
| `libreoffice-writer` (bản có phần giao diện — **không dùng**) | `4:25.2.3-2+deb13u8` | 32652 | 9859736 | `db71b19e2919d217f075c7f3633f3e25b229e79cee43b901644ba570028310e4` |
| `libreoffice-core-nogui` (phụ thuộc của `libreoffice-writer-nogui`) | `4:25.2.3-2+deb13u8` | 107346 | 28230200 | `aedaa4eb84de742e121658520f2aaf40599dd8d7f0ee43aee2a756019ce88ce4` |
| `fontconfig` | `2.15.0-2.3` | 681 | 463312 | `09794b188e042c90b4a89fcb5afeb276bc231b74ddf8a3efbbc7dfb6f0eac4cb` |
| `poppler-utils` (`pdftotext`, `pdffonts` — **chỉ target `test`**) | `25.03.0-5+deb13u4` | 723 | 213460 | `7b5bb3607e7fa078e002420d4e5129d7b83c5684ca6f88d229a40af3e76a7b02` |

`libreoffice-writer-nogui` có `Depends` trên `libreoffice-core-nogui` (hoặc `libreoffice-core`) và `libreoffice-base-core`; `libreoffice-core-nogui` có `Depends: fontconfig, fonts-opensymbol, …`. Gói chuyển đổi `.docx` → `.pdf` bằng `soffice --headless --convert-to pdf` cần phần Writer; không cần gói giao diện.
