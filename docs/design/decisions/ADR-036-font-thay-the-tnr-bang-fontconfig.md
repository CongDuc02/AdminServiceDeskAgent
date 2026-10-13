# ADR-036 — Font trong image: Liberation Serif, và `.docx` giữ nguyên "Times New Roman" qua quy tắc fontconfig tường minh

**Trạng thái:** Accepted **cho giai đoạn thử nghiệm (watermark)**; điều kiện trước production ở mục Consequences · **Duyệt:** PO, 2026-10-13 · **Ngày:** 2026-10-13 · **Quyết định tại:** BUILD MODE, cổng 1.6 (B7) · **Liên quan:** A-058, A-018, D-009, ADR-001, ADR-015 (bổ sung bên dưới đổi cách hiểu "có mặt" của chốt 3), `proposals/cong-1-6-font.md` · **Nguồn:** `docs/reference/font-liberation-serif-license.md`, `docs/reference/font-do-phu-tieng-viet-b7.md`, `docs/reference/nghi-dinh-30-2020-phong-chu-va-pham-vi.md`

---

## Context

- ADR-015 dựng ba chốt để thiếu font thành lỗi có tiếng, với nguyên tắc "có mặt" = **khớp chính xác tên họ font** và "không để bộ chuyển đổi tự thay font".
- Times New Roman là font thương mại; **không có giấy phép nào trong `docs/reference/` cho phép phân phối nó trong image**, nên coi là không được phân phối (A-058).
- Phụ lục I của Nghị định 30/2020/NĐ-CP quy định đích danh phông "Times New Roman" cho văn bản hành chính theo Nghị định đó; Nghị định áp dụng cho cơ quan, tổ chức nhà nước và doanh nghiệp nhà nước (Điều 2), **không nêu doanh nghiệp tư nhân** — xem file tham chiếu. Tổ chức của dự án thuộc nhóm nào: **PO xác nhận 2026-10-13: doanh nghiệp tư nhân** (xác nhận của PO, không phải kết luận pháp lý của người triển khai).
- Mẫu `.docx` thật (mốc M1.1) sẽ do PO soạn bằng Word với Times New Roman. Bản `.docx` giao cho người nhận được mở trên Windows, nơi font có sẵn.
- Liberation Serif 2.1.5 (SIL OFL 1.1): đủ 186/186 chữ cái tiếng Việt; 0 lệch độ rộng so với Times New Roman 7.12 trên 223 ký tự × 4 kiểu chữ; số đo chiều dọc trùng (`font-do-phu-tieng-viet-b7.md`). Chưa đo kerning và render thật.

## Options

- **A — Đổi tên font trong mẫu sang "Liberation Serif"** (đường (a) của đề xuất B7).
- **B — Giữ "Times New Roman" trong `.docx`; image có quy tắc fontconfig tường minh ánh xạ "Times New Roman" → Liberation Serif; bước kiểm khởi động xác nhận ánh xạ.**
- **C — Cài Times New Roman vào image.** Không có giấy phép.
- **D — Để fontconfig tự chọn font thay thế**, không quy tắc riêng, không kiểm.

## Decision

**Chọn B.** PO, 2026-10-13.

1. **Bộ font trong image:** Liberation Serif 2.1.5, bốn kiểu chữ (Regular, Bold, Italic, Bold Italic), đúng các file có sha256 ở `docs/reference/font-liberation-serif-license.md`, kèm `LICENSE` của bản phát hành, đặt trong `fonts/` rồi COPY vào image (`fonts/README.md`). Việc đưa file vào repo và image là việc của B8b; cổng 1.6 chốt **bộ font và quyền phân phối**.
2. **`.docx` giữ "Times New Roman".** `template_version.required_fonts` của mẫu chứa `"Times New Roman"` — tên mà file khai và mà người nhận thấy. Lý do (PO): mẫu thật soạn bằng Word với Times New Roman; bản `.docx` giao cho người nhận mở trên Windows vẫn đúng font. Đổi tên font trong mẫu (phương án A) sẽ làm file người nhận mở ra khai một font mà máy họ có thể không có.
3. **Ánh xạ nằm trong image, tường minh, một chỗ:** một file cấu hình fontconfig do dự án viết (cùng thư mục `fonts/`), COPY vào thư mục cấu hình của image, ánh xạ "Times New Roman" → "Liberation Serif". Không dựa vào quy tắc thay thế có sẵn của hệ điều hành hay của fontconfig. Cú pháp và vị trí cấu hình `[CẦN XÁC MINH]`: chưa có tài liệu fontconfig trong `docs/reference/` — lấy bằng `curl` vào đó trước khi viết file, kiểm bằng chạy thật trong image ở B8b.
4. **Bước kiểm khởi động (gộp vào #6 và #7 của mục Bước kiểm khởi động của `06-structure.md`):** với mỗi họ font trong `required_fonts` đã cấu hình ánh xạ, `fc-match "<họ>"` phải ra họ đích đã chốt (với "Times New Roman": **Liberation Serif**); lệch hoặc ra một họ khác thì **không khởi động**. Họ font không có ánh xạ vẫn theo luật cũ: khớp chính xác tên họ có trong image. Bước kiểm này là thứ biến "thay font" từ im lặng thành tường minh.
5. **Hệ quả cho chốt 1 và 2 của ADR-015:** "mọi font file khai dùng nằm trong `required_fonts`" giữ nguyên; "mọi font trong `required_fonts` có mặt trong image" nay nghĩa là **có mặt hoặc có ánh xạ đã được xác nhận** ở điểm 4.

## Consequences

**Tích cực**

- File `.docx` giao cho người nhận không bị đổi font; mẫu thật của PO dùng được nguyên trạng.
- Không phân phối font không có giấy phép. Quyền phân phối Liberation Serif theo nguyên văn OFL 1.1: kèm thông báo bản quyền và giấy phép với mỗi bản sao (điều 2 của giấy phép).
- Thay font là hành vi có tên, có cấu hình trong repo và có kiểm khi khởi động — không phải hành vi ngầm của bộ chuyển đổi.

**Tiêu cực và cái phải chấp nhận, nói thẳng**

- **PDF không dùng Times New Roman.** Bản PDF do `soffice` xuất nhúng Liberation Serif, còn `.docx` khai Times New Roman: hai file của cùng một văn bản mang hai họ font. Độ rộng ký tự trùng nên ngắt dòng và ngắt trang giữ được; hình chữ khác. Thuộc tính PDF ghi tên font thật.
- **Nếu Nghị định 30/2020 áp dụng cho tổ chức của dự án**, PDF dùng font thay thế không đúng chữ của Phụ lục I ("Times New Roman"). Rủi ro này không chặn Sprint 1–4 vì mọi bản `FINAL` mang watermark thử nghiệm (AC-1.3) và hệ thống chỉ chạy `NON_PRODUCTION`; nó chặn lúc tháo chế độ phi sản xuất. Việc xác định tổ chức có thuộc Điều 2 hay không chưa làm — PO nhận báo cáo trước M1.1.
- Không ai nghiệm thu sự khác biệt hình chữ (A-018, D-009).
- Bản `.docx` mở trên máy không có Times New Roman (Linux, một số máy Mac cấu hình tối giản) sẽ do máy đó tự thay font — ngoài tầm kiểm soát của hệ thống.
- Chưa đo: kerning (`GPOS`/`kern`) và render thật — đo ở B8b trên image thật, trước khi kết luận "ngắt dòng giữ được".
- **Lệch phiên bản:** bước kiểm so họ font, không so phiên bản. Ghim bằng sha256 khi COPY vào image — một test ở B8b.

**Điều kiện trước production (PO, 2026-10-13):** Nghị định 30/2020 gọi đích danh Times New Roman. Tổ chức thuộc phạm vi Điều 2 (**PO xác nhận riêng** — 2026-10-13: doanh nghiệp tư nhân, nên điều kiện này hiện **không kích hoạt**; mở lại nếu tình trạng tổ chức đổi hoặc văn bản phải theo Nghị định vì lý do khác) thì phải có **giấy phép Times New Roman cho server** hoặc **một cách render khác** trước khi tháo chế độ phi sản xuất. Trước M1.1: kiểm Nghị định có bị sửa đổi hay thay thế sau 2020 không, từ nguồn chính thức.

**Điều kiện đảo ngược**

- Tổ chức xác định chịu Nghị định 30/2020 và PDF phải mang đúng Times New Roman → có giấy phép phân phối Times New Roman cho image (phương án C), hoặc đổi tiêu chí chấp nhận PDF. Quyết định của PO.
- `fc-match` trong image thật không ra Liberation Serif dù đã có quy tắc → xét lại cách cấu hình, hoặc phương án A.

## Kết quả thực hiện ở B8b (2026-10-13)

- **Quy tắc fontconfig** `fonts/50-bo19-times-new-roman.conf` (`<match target="pattern">` + `<edit mode="assign" binding="same">`, cú pháp theo `docs/reference/fontconfig-debian-trixie.md`), COPY vào `/etc/fonts/conf.d/`. **Phát hiện:** image Debian 13 có sẵn `30-metric-aliases.conf` cũng ánh xạ "Times New Roman" → Liberation Serif, nên `fc-match` trong image ra Liberation Serif **dù không có quy tắc của dự án**; quy tắc của dự án vì thế là sự tường minh (không phụ thuộc quy tắc có sẵn), không phải thứ duy nhất làm nó chạy. `tests/test_fonts.py` chứng minh riêng file của dự án bằng cấu hình fontconfig cô lập (không có `30-metric-aliases`): có file thì ra Liberation Serif, đổi họ đích hay bỏ file thì không.
- **PDF nhúng Liberation Serif** khi `.docx` khai "Times New Roman" (`pdffonts`: bốn kiểu `LiberationSerif*`, không DejaVu).
- **Đo còn nợ — ngắt dòng và ngắt trang** (`tools/font-probe/compare_linebreaks.py`, sha256 `5dd2157550dd1600ba470fcfb5f60127098801ac6a486e7560dac0f65a84d927`): cùng một `.docx` khai "Times New Roman" dựng hai lần bằng `soffice` trong image — (A) với Times New Roman 7.12 thật (bản cài của Windows trên máy người triển khai, gắn chỉ đọc, không vào repo hay image), (B) với Liberation Serif và quy tắc của dự án. Bốn cấu hình (12 pt và 13 pt, canh đều và canh trái), mỗi cấu hình bốn kiểu chữ × tám đoạn tiếng Việt đủ dấu: **829 dòng, 26 trang: 0 dòng khác nhau, số trang và số dòng mỗi trang bằng nhau.** Phạm vi của phép đo: Writer của LibreOffice 25.2.3, văn bản giả này; **không** đo Word, không đo font khác, và không nói gì về hình chữ (A-018).

## Rejected alternatives

**A — Đổi tên font trong mẫu.** Loại theo quyết định của PO: file `.docx` giao người nhận sẽ khai Liberation Serif — font phần lớn máy Windows không có.

**C — Cài Times New Roman.** Loại: không có giấy phép phân phối trong `docs/reference/`.

**D — Để fontconfig tự chọn, không kiểm.** Loại: đúng cái hỏng im lặng mà ADR-015 dựng ba chốt để chặn; kết quả phụ thuộc cấu hình hệ điều hành của image nền.

**Tinos 1.340** (cùng độ phủ, cùng số đo): không chọn. Nguồn có mâu thuẫn nội bộ (file mô tả ghi Apache 2.0, giấy phép hiện hành OFL 1.1); Liberation Serif có font và giấy phép trong cùng một bản phát hành. Tinos là phương án dự phòng nếu Liberation Serif có vấn đề.
