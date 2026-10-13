# Kế hoạch B8c — tải file qua tệp tạm, bước kiểm #6 nhẹ, watermark chéo

**Trạng thái:** ⏳ **Chờ PO duyệt** · **Ngày:** 2026-10-13 · **Người đề xuất:** người triển khai · **Nhánh:** `build/b8c-tai-file-kiem-nhe-watermark` (tách từ `main` sau merge B8b `ec60902`; chỉ có tài liệu cho tới khi duyệt) · **Vị trí:** lát nhỏ giữa B8b và B9a (PO, 2026-10-13) · **Nguồn quyết định:** PO 2026-10-13 — O1-18 (ghi tạm ra đĩa, semaphore mặc định 4), O1-19 (#6 kiểm nhẹ, log phiên bản LibreOffice), watermark chéo nếu thiết kế không cấm, A-094 hoãn tới trước `PRODUCTION`, bốn diễn giải của B8b chấp nhận (`read_assigned` rà lại ở B9b)

## 1. Kiểm thiết kế: có quy định gì về hình thức watermark không?

Đã đọc `00-domain.md` (mục chế độ phi sản xuất, dòng 1; D-009), `01-prd.md` (NFR-03 điều 1; M5), `03-agents.md` (dòng `docx_render`), `12-roadmap.md` (AC-1.3), `06-structure.md`. Quy định có đúng bốn ý:

| Ý | Nguồn |
|---|---|
| Nguyên văn `BẢN THỬ NGHIỆM — KHÔNG CÓ GIÁ TRỊ PHÁP LÝ` | NFR-03, AC-1.3 |
| **Trong bản render**, không phải lớp hiển thị của giao diện | 00-domain, NFR-03 điều 1, AC-1.3 |
| "Không gỡ được": **không có tham số nào tắt nó** ở `NON_PRODUCTION`; tool đọc chế độ từ `document` | 00-domain, 03-agents |
| Mọi văn bản, kiểm được trên dữ liệu sau UAT (M5) | PRD M5 |

**Không có điều nào quy định vị trí, góc, cỡ chữ hay cách dựng** — dòng chữ ở tiêu đề của B8b là lựa chọn của người triển khai, không phải yêu cầu. Vậy thiết kế **không cản** watermark chéo. Nói thẳng một giới hạn đã có từ trước: "không gỡ được" theo thiết kế nghĩa là không có tham số tắt; người nhận `.docx` vẫn xoá được shape ở tiêu đề trong Word. PDF thì khó gỡ hơn nhưng cũng không bất khả. B8c không đổi nghĩa đó.

## 2. Watermark chéo (mục tiêu 3 — **làm đầu tiên, có cổng dừng**)

- **Hình thức đề xuất:** đúng kiểu "Watermark" của Word — một shape chữ **neo trong tiêu đề** (`<v:shape type="#_x0000_t136" id="PowerPlusWaterMarkObject…">` với `<v:textpath string="BẢN THỬ NGHIỆM — …">`), xoay −45°, **căn giữa thân trang cả hai chiều**, nằm **sau** chữ (`z-index` âm), tô xám nhạt bán trong suốt, không viền, rộng gần hết chiều chéo của trang. Một shape mỗi loại tiêu đề (mặc định, trang đầu, trang chẵn), cùng luật kế thừa phần của `add_watermark` hiện nay. Tiêu đề của mẫu giữ nguyên nội dung (không còn chèn dòng chữ). Tool vẫn không có tham số tắt.
- **Rủi ro cần chứng minh trước, không tin:** LibreOffice phải nhập shape VML này và xuất ra PDF đúng (xoay, căn giữa, nằm sau chữ, nhạt). **Bước 1 của B8c là một spike:** dựng hai biến thể — (A) VML WordArt như Word, (B) DrawingML (`wps:txbx` xoay, `behindDoc`) — render bằng `soffice` trong image, chuyển trang PDF sang PNG bằng `pdftoppm` (đã có ở target `test`), **xem ảnh**. Biến thể nào render đúng thì chọn; cả hai hỏng thì **dừng và báo**, không tự đổi hướng.
- **Bằng chứng trong test (ảnh trang PDF):** test dựng PNG của trang rồi kiểm bằng pixel — (1) có pixel màu watermark ở **hai góc đối nhau của đường chéo** (trên-trái và dưới-phải của thân trang) và **không có** ở hai góc kia (không phải dòng ngang ở đầu trang); (2) trang không watermark thì không có các pixel đó; (3) chữ thân văn bản vẫn đọc được: `pdftotext` ra đủ chữ, và số pixel đậm của thân trang không giảm đáng kể so với bản không watermark; (4) đủ mọi trang của văn bản nhiều trang; (5) `PRODUCTION` không có. Kèm **một ảnh mẫu** commit vào `docs/design/proposals/` để anh xem bằng mắt.
- **Kiểm "chữ trong file" (M5):** tiêu đề `.docx` chứa đúng một shape với `textpath string` đúng nguyên văn — kiểm trong test thay cho kiểm đoạn chữ cũ; `pdftotext` có ra chữ hay không phụ thuộc cách LibreOffice xuất shape (đo ở spike, ghi lại).
- **Tài liệu:** dòng `docx_render` của `03-agents.md`, docstring `docx_fill`, AC-1.3 ở `12-roadmap.md`, `CHANGELOG.md`. Không cần ADR (chưa có quyết định kiến trúc; hình thức không do thiết kế quy định).

## 3. O1-18 — tải file qua tệp tạm (mục tiêu 1)

- **`tool_layer.storage.fetch_verified(...)`** (mới; `fetch` trong bộ nhớ giữ cho worker — `docx_render`, `pdf_export` cần byte, và bị chặn bởi trần WV-24): tải object theo **khối** (WV-26, mặc định 256 KiB) vào `tempfile.TemporaryFile()` — tệp **vô danh, đã xoá tên ngay lúc tạo** (Linux) nên đóng là biến mất, kể cả khi tiến trình bị `SIGKILL`; **băm SHA-256 khi tải**; xong so với `stored_object_commit` (checksum, độ dài; quá trần `FILE_FETCH_MAX_BYTES` thì dừng ngay giữa chừng). **Lệch thì đóng tệp, không gửi byte nào**; khớp thì trả đối tượng tệp đã tua về đầu. Bộ nhớ cố định theo kích thước khối, không theo kích thước file.
- **`ObjectStorage`** thêm `get_chunks(key, chunk_size)` (đọc từng khối từ body của `boto3`); lỗi vẫn chỉ mang mã.
- **Endpoint:** `StreamingResponse` đọc từng khối từ tệp tạm; `finally` đóng tệp và nhả semaphore — chạy cả khi lỗi giữa chừng và khi client ngắt (generator bị đóng). Quyền, `audit_event`, `FILE_UNAVAILABLE` gộp, header giữ nguyên B8b; `Content-Length` đặt theo kích thước đã commit.
- **Semaphore** (WV-27, **mặc định 4, chưa hiệu chỉnh** — PO): `threading.BoundedSemaphore` một cho cả tiến trình `api`, **giữ suốt lượt tải** (tải vào tệp tạm cộng stream) nên chặn cả số kết nối tới storage, CPU băm ở 0,1 CPU và dung lượng tệp tạm (≤ 4 × 8 MiB). Hết chỗ thì **chờ tối đa WV-28** rồi trả `FILE_UNAVAILABLE` (xem Q1).
- **Phép tính mới** (ghi vào `proposals/b8b-ke-hoach.md` mục 9.4 và O1-18): mỗi lượt giữ ≈ 2 × khối ≈ 0,5 MiB bộ nhớ (+ đệm của `boto3`, đo) ⇒ 4 lượt ≈ 2–4 MiB, **không phụ thuộc kích thước file**; so với phần còn lại 80–104 MiB — vừa, dư. Số đo thật thay cho ước tính: RSS đỉnh khi tải file 8 MiB và 64 MiB phải **bằng nhau** (trong sai số), và tải 64 MiB trong container `--memory=128m` phải qua (đệm toàn bộ cần ≈ 147 MiB — sẽ bị OOM-kill nếu còn đệm).
- **Test:** (1) RSS tăng khi tải 8 MiB và 64 MiB chênh nhau dưới 2 MiB (không tăng theo kích thước file); (2) **không còn tệp tạm và không rò file descriptor** sau: thành công, checksum lệch, object mất, quá trần, storage không với tới, lỗi giữa chừng, client ngắt giữa stream; (3) không byte nào ra khi checksum lệch (như B8b); (4) semaphore: 12 luồng, số lượt tải đồng thời quan sát được ≤ 4; nhả ở mọi lối thoát (kể cả client ngắt); hết chờ thì `FILE_UNAVAILABLE`; (5) chạy lại các test ma trận quyền và `audit_event` của B8b không đổi. **Đột biến** dự kiến 15–20 mẫu: bỏ băm, bỏ so checksum, gửi trước khi kiểm, không đóng tệp ở nhánh lỗi, không nhả semaphore ở `finally`, bỏ trần giữa chừng, `Semaphore(1000)`, khối bằng kích thước file…
- **Còn chưa biết, nói thẳng:** Render docs không nói `/tmp` của gói Free nằm trên đĩa hay trên bộ nhớ, cũng không nói dung lượng (`render-free-tier.md`: chỉ "ephemeral filesystem") — `[CẦN XÁC MINH]`. Nếu `/tmp` là tmpfs thì tệp tạm vẫn tính vào 512 MB (4 × 8 MiB = 32 MiB, vẫn vừa phần còn lại). Ghi thành mục kiểm ở cổng 2.x đầu tiên có Render thật (A-095).

## 4. O1-19 — bước kiểm #6 nhẹ (mục tiêu 2)

- **#6 = `soffice --headless --version` chạy được, thoát mã 0, trả trong hạn WV-25** (đổi nghĩa; mặc định **20 s**, "vài giây" — đo: 0,2–3 s ở CPU đầy đủ, 1,8–2,6 s ở `--cpus=0.1`) **cộng** `fc-list`/`fc-match` chạy được như B8b. **Bỏ** phép chuyển đổi `.docx` thật khỏi khởi động (47 s ở 0,1 CPU, người đầu chờ ≈ 70 s). Mã mới: `STARTUP_06_VERSION_FAILED`, `STARTUP_06_VERSION_TIMEOUT`; `STARTUP_06_CONVERT_*` bỏ.
- **Log phiên bản thật ở khởi động** (cho A-094): trường `libreoffice` (đầu ra `--version`, cắt gọn) trong `STARTUP_CHECK_INFO` của bước #6 — ghi mỗi lần `worker` khởi động.
- **Phép chuyển đổi thật chỉ còn ở CI, trong image** (không đổi: `test_convert.py`, `test_render_tools.py`, `test_checks_render.py` chạy thật nhờ `BO19_REQUIRE_SOFFICE=1`). Thêm test khoá "#6 không chuyển đổi" (`convert_to_pdf` bị chặn thì #6 vẫn qua) và đột biến "#6 lại chuyển đổi" phải đỏ.
- **Tài liệu:** hàng #6 của `06-structure.md`, WV-25, O1-19 đóng, `CHANGELOG.md`; A-094 ghi "PO hoãn tới trước `PRODUCTION`; từ B8c phiên bản LibreOffice được log mỗi lần khởi động".

## 5. Việc ghi cho lát dựng `combined_main` (PO, 2026-10-13)

Ghi vào `12-roadmap.md` (O1-6) và A-095, **không làm ở B8c:** khi dựng `combined_main`, **đo một lượt chat giả trong lúc `soffice` đang chuyển đổi, dưới `--cpus=0.1`**, so với hạn chót lượt WV-02 (và biên WV-03). Lý do: một chuyển đổi mất 32–88 s ở 0,1 CPU trong cùng container với `api`; chưa biết lượt chat có còn kịp hạn chót.

## 6. Không làm ở B8c

`combined_main`, handler `render_document` và `document_graph` (B9a), `GET /documents/{id}`, trần số dòng của giá trị `FREE_CONTENT` (thời lượng chuyển đổi tăng nhanh hơn tuyến tính theo số dòng ngắt — ghi ở O1-19, thuộc B9a khi có `max_length` thật), ghim phiên bản apt (A-094 hoãn), tải file nhiều phần (`Range`), tệp tạm cho đường worker (`fetch` trong bộ nhớ giữ nguyên).

## 7. Câu hỏi cho PO (kèm mặc định)

| # | Câu hỏi | Mặc định |
|---|---|---|
| Q1 | Semaphore hết chỗ thì thế nào? | Chờ tối đa **WV-28 = 15 s** (chưa hiệu chỉnh), rồi `FILE_UNAVAILABLE` 503 + log `BUSY`. Không thêm mã lỗi mới vào `05-api.md` |
| Q2 | Giữ semaphore suốt lượt (tải + stream) hay chỉ lúc tải? | Suốt lượt: bộ nhớ đã cố định, nhưng đĩa, kết nối storage và băm ở 0,1 CPU cần chặn cả hai pha |
| Q3 | Watermark: nếu spike cho thấy chỉ DrawingML (B) render đúng? | Dùng B; nếu cả hai hỏng thì dừng, báo — không tự đổi hướng |
| Q4 | Màu và độ mờ watermark | Xám nhạt bán trong suốt (chữ thân văn bản đen vẫn đọc rõ); anh xem ảnh mẫu rồi chỉnh |

Thứ tự làm: tài liệu → (1) spike watermark, ảnh mẫu → (2) O1-18 → (3) O1-19 → đột biến → CI → báo cáo. Gặp gì ngoài kế hoạch thì dừng và hỏi.
