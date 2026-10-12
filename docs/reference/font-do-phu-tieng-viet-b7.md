# Độ phủ tiếng Việt và số đo so với Times New Roman — Liberation Serif 2.1.5, Tinos 1.340 (cổng 1.6, đo 2026-10-12)

- **Cách đo:** đọc bảng `cmap`, `hmtx`, `hhea`, `OS/2`, `name` của **chính file font** bằng `fontTools` 4.53.1, trong container dùng một lần (image `bo19-b3`), file font gắn chỉ đọc. Không lấy từ tài liệu hay trí nhớ.
- **Tập ký tự:** 186 chữ cái — 12 nguyên âm gốc tiếng Việt × 6 thanh (kể cả không dấu) × hoa/thường dạng dựng sẵn NFC, cộng `đ`/`Đ` và 52 chữ Latin cơ bản; 8 dấu tổ hợp cho văn bản NFD (U+0300, U+0301, U+0303, U+0309, U+0323, U+0302, U+0306, U+031B); 37 dấu câu, chữ số và ký hiệu thường gặp.
- **Times New Roman để so:** bản cài sẵn của Windows trên máy người triển khai (`C:\Windows\Fonts\times*.ttf`, `Version 7.12`) — **chỉ đọc để đo**, không chép vào repo hay image.
- sha256 của ba script đo: `check_vi.py` `ea50b3b118cb3615334b31f12763d442fbdf0d99569bc5afb2b397403a4361b8`, `compare.py` `e2fa5b00a7bf543165dc68351e0be668fb6d156e3a87cb645afff48235b54e76`, `vmetrics.py` `35264b0d31bf6d477551480eb7091a0b198a02a2e0e98346306582a2e5850c7c` — giữ ở scratchpad của phiên, không vào repo.

## Độ phủ tiếng Việt

| File | Phiên bản (`name` id 5) | Chữ cái thiếu / 186 | Dấu tổ hợp thiếu | Dấu câu thiếu | Giấy phép (`name` id 13) | `fsType` |
|---|---|---|---|---|---|---|
| `Tinos-Regular.ttf` | Version 1.340; ttfautohint (v1.8.4.16-eb64) | 0 | 0 | 0 | This Font Software is licensed under the SIL Open Font License, Versio… | 0 |
| `Tinos-Bold.ttf` | Version 1.340; ttfautohint (v1.8.4.16-eb64) | 0 | 0 | 0 | This Font Software is licensed under the SIL Open Font License, Versio… | 0 |
| `Tinos-Italic.ttf` | Version 1.340; ttfautohint (v1.8.4.16-eb64) | 0 | 0 | 0 | This Font Software is licensed under the SIL Open Font License, Versio… | 0 |
| `Tinos-BoldItalic.ttf` | Version 1.340; ttfautohint (v1.8.4.16-eb64) | 0 | 0 | 0 | This Font Software is licensed under the SIL Open Font License, Versio… | 0 |
| `LiberationSerif-Regular.ttf` | Version 2.1.5 | 0 | 0 | 0 | Licensed under the SIL Open Font License, Version 1.1… | 0 |
| `LiberationSerif-Bold.ttf` | Version 2.1.5 | 0 | 0 | 0 | Licensed under the SIL Open Font License, Version 1.1… | 0 |
| `LiberationSerif-Italic.ttf` | Version 2.1.5 | 0 | 0 | 0 | Licensed under the SIL Open Font License, Version 1.1… | 0 |
| `LiberationSerif-BoldItalic.ttf` | Version 2.1.5 | 0 | 0 | 0 | Licensed under the SIL Open Font License, Version 1.1… | 0 |

## Độ rộng ký tự so với Times New Roman

| Times New Roman | Font thay thế | `unitsPerEm` | Ký tự so | Lệch độ rộng |
|---|---|---|---|---|
| `times.ttf` (Version 7.12) | `LiberationSerif-Regular.ttf` | 2048 / 2048 | 223 | **0** |
| `times.ttf` (Version 7.12) | `Tinos-Regular.ttf` | 2048 / 2048 | 223 | **0** |
| `timesbd.ttf` (Version 7.12) | `LiberationSerif-Bold.ttf` | 2048 / 2048 | 223 | **0** |
| `timesbd.ttf` (Version 7.12) | `Tinos-Bold.ttf` | 2048 / 2048 | 223 | **0** |
| `timesi.ttf` (Version 7.12) | `LiberationSerif-Italic.ttf` | 2048 / 2048 | 223 | **0** |
| `timesi.ttf` (Version 7.12) | `Tinos-Italic.ttf` | 2048 / 2048 | 223 | **0** |
| `timesbi.ttf` (Version 7.12) | `LiberationSerif-BoldItalic.ttf` | 2048 / 2048 | 223 | **0** |
| `timesbi.ttf` (Version 7.12) | `Tinos-BoldItalic.ttf` | 2048 / 2048 | 223 | **0** |

## Số đo chiều dọc (chiều cao dòng)

Regular và Bold của cả ba họ: `hhea` ascent/descent/lineGap = 1825 / −443 / 87; `OS/2` typo = 1420 / −442 / 307 (Regular), 1387 / −442 / 307 (Bold); win = 1825 / 443; bit `USE_TYPO_METRICS` tắt — **trùng nhau từng số**.

## Chưa đo, nói thẳng

- **Kerning và bảng `GPOS`/`kern`** — chưa so; ngắt dòng có thể lệch ở văn bản bật kerning.
- **Hình chữ** — khác nhau theo thiết kế; không có phép đo nào ở đây nói chúng "giống" Times New Roman.
- **Render thật qua `soffice`** — chưa chạy; thuộc B8b, sau khi PO chọn font.
