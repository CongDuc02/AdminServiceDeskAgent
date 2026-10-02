# OWASP Password Storage Cheat Sheet — mục Argon2id

- **Nguồn:** `https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/cheatsheets/Password_Storage_Cheat_Sheet.md`, lấy bằng `curl`. Commit cuối của file theo GitHub API: `1a3f58ed2714f258a1d713966457f1a0f426e841`, ngày `2026-09-05T09:06:09Z`. sha256 của bản đã lấy: `b50179b7557bc1062ec79b01310fe9b32231aa5c5ba3b704b98f422e501f3683`.
- **Ngày lấy:** 2026-09-27.
- **Phiên bản:** tài liệu sống, không số phiên bản — commit ở trên là mốc.
- **Dùng cho:** A-048 — "không dưới mức tối thiểu OWASP" (quyết định của PO, 2026-09-27); `docs/design/proposals/sprint1-working-values-a031-a048.md`, WV-16.

---

## Trích nguyên văn — từ tiêu đề `### Argon2id` tới trước `### scrypt`

> ### Argon2id
>
> [Argon2](https://en.wikipedia.org/wiki/Argon2) was the winner of the 2015 [Password Hashing Competition](https://en.wikipedia.org/wiki/Password_Hashing_Competition). Out of the three Argon2 versions, use the  Argon2id variant since it provides a balanced approach to resisting both side-channel and GPU-based attacks.
>
> Rather than a simple work factor like other algorithms, Argon2id has three different parameters that can be configured: the base minimum of the minimum memory size (m), the minimum number of iterations (t), and the degree of parallelism (p). We recommend the following configuration settings:
>
> These parameters control how computationally expensive it is to compute a password hash.
> Increasing memory usage, iteration count, or parallelism makes password cracking attempts significantly slower and more costly for attackers, while still remaining practical for legitimate authentication requests when tuned appropriately.
>
> - m=47104 (46 MiB), t=1, p=1 (Do not use with Argon2i)
> - m=19456 (19 MiB), t=2, p=1 (Do not use with Argon2i)
> - m=12288 (12 MiB), t=3, p=1
> - m=9216 (9 MiB), t=4, p=1
> - m=7168 (7 MiB), t=5, p=1
>
> These configuration settings provide an equal level of defense, and the only difference is a trade off between CPU and RAM usage.

## Đọc cho BO-19

- Tài liệu **không** nêu một "mức tối thiểu" duy nhất. Nó nêu năm cấu hình và nói chúng "provide an equal level of defense", khác nhau ở cân bằng CPU với RAM. Thiết kế đọc "không dưới mức tối thiểu OWASP" là: **chọn một trong năm cấu hình, hoặc một cấu hình trội hơn nó ở cả `m` lẫn `t`**.
- Cả năm cấu hình đều có `p=1`.
- Hai cấu hình đầu ghi "Do not use with Argon2i". BO-19 dùng `argon2id` (ADR-021).
