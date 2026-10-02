# Render — loại instance cho Services & Workers: CPU và RAM

- **Nguồn:** `https://render.com/pricing`, lấy bằng `curl`; sha256 của HTML đã lấy: `e41ef9e2f446f7a95a7b3912340fd79356e739889db6f93eb3d29be0d92bb439`.
- **Ngày lấy:** 2026-09-27. Trang giá thay đổi theo thời gian; ngày lấy là mốc duy nhất.
- **Cách tách:** bỏ `<script>`, `<style>`, thay thẻ HTML bằng `|`, lấy đoạn từ `Services & Workers` tới `Expand|compute table`. Bảng dưới dựng lại từ chuỗi đó bằng script; thứ tự ô trong chuỗi là: CPU · giá · RAM · mã instance.
- **Dùng cho:** A-048, WV-16 — RAM của instance chạy `api` đặt cạnh bộ nhớ mỗi lần verify `argon2id`. **Không** chọn gói ở đây: gói của từng môi trường vẫn là A-002.
- **Giá chỉ chép theo nguồn**, không dùng làm căn cứ định cỡ chi phí ở đâu khác — mô hình chi phí ở `11-ops.md` vẫn thuần biến số.

---

## Chuỗi đã tách, nguyên văn

```text
Services & Workers|Scale up to|12|CPU and|96|GB of RAM|Private services|Web services with HTTP/2 and full TLS|Background workers|Node, Python, Go, Rust, Ruby, and Elixir|Custom Docker containers|SSDs|for $0.25/GB per month|Free|(|limitations apply|)|$0/month|512 MB RAM|free|Less than 1 CPU|$7/month|512 MB RAM|0.5c-512mb|1 CPU|$25/month|2 GB RAM|1c-2g|2 CPU|$85/month|4 GB RAM|2c-4g|2 CPU|$135/month|8 GB RAM|2c-8g|2 CPU|$200/month|16 GB RAM|2c-16g|4 CPU|$175/month|8 GB RAM|4c-8g|4 CPU|$225/month|16 GB RAM|4c-16g|4 CPU|$350/month|32 GB RAM|4c-32g|8 CPU|$300/month|16 GB RAM|8c-16g|8 CPU|$450/month|32 GB RAM|8c-32g|8 CPU|$1,000/month|64 GB RAM|8c-64g|12 CPU|$450/month|24 GB RAM|12c-24g|12 CPU|$800/month|48 GB RAM|12c-48g|12 CPU|$1,500/month|96 GB RAM|12c-96g|
```

## Dựng thành bảng

| Mã instance | CPU | RAM | Giá |
|---|---|---|---|
| `free` | — (không in) | 512 MB RAM | $0/month |
| `0.5c-512mb` | Less than 1 CPU | 512 MB RAM | $7/month |
| `1c-2g` | 1 CPU | 2 GB RAM | $25/month |
| `2c-4g` | 2 CPU | 4 GB RAM | $85/month |
| `2c-8g` | 2 CPU | 8 GB RAM | $135/month |
| `2c-16g` | 2 CPU | 16 GB RAM | $200/month |
| `4c-8g` | 4 CPU | 8 GB RAM | $175/month |
| `4c-16g` | 4 CPU | 16 GB RAM | $225/month |
| `4c-32g` | 4 CPU | 32 GB RAM | $350/month |
| `8c-16g` | 8 CPU | 16 GB RAM | $300/month |
| `8c-32g` | 8 CPU | 32 GB RAM | $450/month |
| `8c-64g` | 8 CPU | 64 GB RAM | $1,000/month |
| `12c-24g` | 12 CPU | 24 GB RAM | $450/month |
| `12c-48g` | 12 CPU | 48 GB RAM | $800/month |
| `12c-96g` | 12 CPU | 96 GB RAM | $1,500/month |

Dòng `free`: chuỗi không có ô CPU đứng trước giá `$0/month`, nên để trống. Ô "Less than 1 CPU" đứng ngay sau mã `free` và trước giá `$7/month`, nên thuộc về `0.5c-512mb` — khớp với phần `0.5c` của chính mã đó.
