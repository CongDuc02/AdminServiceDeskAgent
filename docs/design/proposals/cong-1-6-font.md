# Đề xuất cổng 1.6 — bộ font trong image và quyền phân phối (A-058)

**Trạng thái:** ✅ **PO quyết 2026-10-13 — "Đạt cho giai đoạn thử nghiệm (watermark)"; điều kiện trước production ở ADR-036** — — Q1 Liberation Serif; Q2 **khác mặc định**: giữ "Times New Roman" trong `.docx`, ánh xạ bằng fontconfig tường minh trong image, bước kiểm khởi động xác nhận bằng `fc-match` (lý do: mẫu thật soạn bằng Word với Times New Roman; `.docx` giao người nhận mở trên Windows vẫn đúng font) — **ADR-036**; Q3 lấy Nghị định 30/2020 — **đã lấy**, `docs/reference/nghi-dinh-30-2020-phong-chu-va-pham-vi.md`. Phần dưới giữ nguyên bản đề xuất; mục 4 điểm 3 đường (b) và mục 5 dòng "Mẫu … khai `required_fonts = [\"Liberation Serif\"]`" **bị thay** bởi ADR-036 · **Ngày:** 2026-10-12 · **Người đề xuất:** người triển khai · **Nguồn yêu cầu:** PO, duyệt kế hoạch B7 (2026-10-12) — docs-only, song song B7 · **Cần trước:** B8b (`soffice` và font vào image), S5 của Spike 1 · **Tài liệu gốc:** `docs/reference/font-liberation-serif-license.md`, `docs/reference/font-tinos-license.md`, `docs/reference/font-do-phu-tieng-viet-b7.md`

## 1. Thiết kế đang giả định font gì

- **Không giả định font cụ thể nào.** Thiết kế chỉ có cơ chế: `template_version.required_fonts` là manifest tên họ font của từng phiên bản template; ba chốt của ADR-015 — tải lên, kích hoạt, bước kiểm khởi động #7 — đòi mọi font trong manifest có mặt trong image và mọi font file `.docx` khai dùng nằm trong manifest. `fonts/README.md` chỉ ghi luật "mỗi font kèm file giấy phép, COPY vào `/usr/local/share/fonts/bo19/`" — thư mục chưa có font nào.
- **Chưa có mẫu `.docx` nào:** mẫu thật là mốc M1.1; mẫu giữ chỗ người triển khai dựng ở B8b. Khuôn trả lời của chat là văn bản thuần, không dính font.
- **Nghị định 30/2020/NĐ-CP** — *cập nhật 2026-10-13:* văn bản gốc đã vào `docs/reference/nghi-dinh-30-2020-phong-chu-va-pham-vi.md`. Phụ lục I, Phần I, mục I.4 quy định đích danh "Phông chữ tiếng Việt Times New Roman"; Điều 2 áp dụng cho cơ quan, tổ chức nhà nước và doanh nghiệp nhà nước và **không nêu doanh nghiệp tư nhân**. Tổ chức của dự án có thuộc phạm vi hay không: `[CẦN XÁC MINH]`, báo PO trước M1.1. (Đoạn gốc của đề xuất, ghi trước khi lấy văn bản: tên phông và điều khoản `[CẦN XÁC MINH]`.)

## 2. Các phương án

Số đo ở mục này đọc từ **chính file font** — `docs/reference/font-do-phu-tieng-viet-b7.md`; giấy phép chép nguyên văn ở hai file giấy phép.

| | A. Times New Roman bản gốc | B. Liberation Serif 2.1.5 | C. Tinos 1.340 |
|---|---|---|---|
| Nguồn | Font thương mại cài cùng Windows | Bản phát hành `2.1.5` của `liberationfonts/liberation-fonts` (2021-09-30) | `google/fonts`, commit `ba95515…` (2026-04-27); nguồn `googlefonts/tinos` |
| Giấy phép | **`[CẦN XÁC MINH]`** — không có văn bản giấy phép nào trong `docs/reference/`. Coi là **không được phân phối** trong image cho tới khi tổ chức đưa giấy phép cho phép điều đó | SIL OFL 1.1 — `LICENSE` trong cùng tarball với font | SIL OFL 1.1 — `OFL.txt` của kho nguồn, bảng `name` của font. **Mâu thuẫn trong nguồn:** `DESCRIPTION.en_us.html` còn ghi "Apache 2.0" — văn bản cũ, ghi rõ ở file giấy phép |
| Tên dành riêng (OFL) | — | "Liberation"; "Arimo, Tinos and Cousine" | Không ghi tên dành riêng trong thông báo bản quyền |
| Độ phủ tiếng Việt | Không đo — không phải ứng viên phân phối | **186/186** chữ cái, 8/8 dấu tổ hợp, 37/37 dấu câu — cả bốn kiểu chữ | **186/186**, 8/8, 37/37 — cả bốn kiểu chữ |
| Độ rộng so với Times New Roman 7.12 | — | **0 lệch** / 223 ký tự × 4 kiểu chữ | **0 lệch** / 223 ký tự × 4 kiểu chữ |
| Số đo chiều dọc | — | Trùng từng số (Regular, Bold) | Trùng từng số (Regular, Bold) |
| Bảo trì | — | Bản mới nhất là 2021 | Commit gần nhất 2026-04 |

- **B và C gần như một:** cùng độ rộng, cùng số đo dọc; thông báo bản quyền của Liberation ghi "Digitized data copyright (c) 2010 Google Corporation with Reserved Font Arimo, Tinos and Cousine". Chọn **một** họ, không cả hai.
- **Font khác:** họ không tương thích số đo — ví dụ một serif OFL bất kỳ có tiếng Việt — đổi ngắt dòng và ngắt trang của mẫu; không đề xuất. Các họ Times-compatible khác (nhóm URW Nimbus Roman, TeX Gyre Termes) **chưa tải, chưa đo** — lấy về đo nếu PO muốn thêm ứng viên.

## 3. Quyền phân phối trong image — theo nguyên văn OFL 1.1

Không phải phán quyết pháp lý; chỉ đọc điều khoản của giấy phép đã tải về.

- **Điều 2:** font "may be bundled, redistributed and/or sold with any software, provided that each copy contains the above copyright notice and this license" — image phải mang file giấy phép cạnh font. `fonts/README.md` đã đòi đúng việc này.
- **Điều 1:** font không được bán riêng — không liên quan.
- **Điều 3:** chỉ ràng buộc **bản sửa đổi** dùng tên dành riêng. Dự án không sửa font.
- **Điều 5:** "The requirement for fonts to remain under this license does not apply to any document created using the Font Software" — PDF hệ thống sinh ra không mang ràng buộc OFL.
- **Repo là nơi phân phối:** commit file font vào `fonts/` là phân phối lại; điều 2 vẫn thoả khi giấy phép nằm cùng thư mục.

## 4. Rủi ro khi dùng font thay thế cho văn bản của tổ chức

1. **Thể thức** — rủi ro lớn nhất. Nếu Nghị định 30/2020 gọi đích danh một phông, văn bản dùng phông thay thế có thể **sai thể thức**, và sai thể thức là văn bản vô hiệu (mục Bối cảnh đề tài của `CLAUDE.md`). Chưa biết vì Nghị định chưa có bản gốc — Q3. Không ai trong tổ chức nghiệm thu thể thức (A-018, D-009). Ở `NON_PRODUCTION`, bản `FINAL` mang watermark thử nghiệm (AC-1.3) nên rủi ro này **không chặn Sprint 1–4**; nó chặn lúc tháo chế độ phi sản xuất.
2. **Tương thích số đo không phải là giống nhau** (A-058). Bề rộng trùng nên ngắt dòng giữ được; hình chữ khác. Người nhận so với văn bản cũ của tổ chức có thể thấy khác. Thuộc tính PDF ghi tên font thật — người nhận đọc được.
3. **Mẫu `.docx` của tổ chức khai "Times New Roman"** — tình huống dễ gặp nhất ở M1.1. Chốt tải lên của ADR-015 so tên họ khai trong file với `required_fonts` và với font có trong image: "Times New Roman" không có trong image thì `TEMPLATE_FONTS_INVALID`. Hai đường:
   - (a) **Mẫu đổi font trong file sang họ đã chọn** — tên font trong file, trong manifest và trong image là một; không có thay thế ngầm.
   - (b) Cấu hình bí danh trong image, "Times New Roman" trỏ sang họ thay thế — chốt "có mặt trong image" vẫn qua, nhưng đó **chính là thay font im lặng** mà ADR-015 dựng ba chốt để chặn. Không đề xuất.
4. **Chưa đo:** kerning (`GPOS`/`kern`), và render thật qua `soffice` — thuộc B8b, sau khi chọn font.
5. **Lệch phiên bản:** bước kiểm #7 so **tên họ**, không so phiên bản. Đổi bản font mà giữ tên thì không chốt nào bắt được. Ghim bằng sha256 khi COPY vào image — một test ở B8b.

## 5. Đề xuất mặc định

- **Liberation Serif 2.1.5**, bốn kiểu chữ, COPY từ `fonts/` vào image kèm `LICENSE`, ghim sha256 — đúng các file ở `docs/reference/font-liberation-serif-license.md`. Lý do chọn hơn Tinos: font và giấy phép nằm trong **cùng một** bản phát hành có checksum, và không có metadata mâu thuẫn. Tinos tương đương về số đo — chọn Tinos nếu PO ưu tiên nguồn còn bảo trì.
- Mẫu giữ chỗ ở B8b và mẫu thật ở M1.1 khai `required_fonts = ["Liberation Serif"]` và dùng chính tên đó trong file — đường (a).
- Khi PO chọn: ADR-036 ghi quyết định, A-058 ghi họ font và giấy phép, cổng 1.6 thành **Đạt** với tên người quyết. Phần còn mở chuyển sang Q3 và lúc tháo chế độ phi sản xuất.

## 6. Câu hỏi cho PO — kèm mặc định

| # | Câu hỏi | Mặc định |
|---|---|---|
| Q1 | Họ font đóng vào image | **Liberation Serif 2.1.5** |
| Q2 | Mẫu khai "Times New Roman": đổi font trong mẫu, hay bí danh trong image | **Đổi trong mẫu** — đường (a) |
| Q3 | Lấy bản gốc Nghị định 30/2020/NĐ-CP vào `docs/reference/` để đọc quy định về phông chữ | **Có, trước M1.1** — từ nguồn chính thức PO chỉ định; người triển khai lấy bằng `curl`, ghi URL, ngày, sha256 |
