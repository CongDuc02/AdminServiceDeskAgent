# Nghị định 30/2020/NĐ-CP — Phụ lục I: thể thức và kỹ thuật trình bày văn bản hành chính (cho mẫu giấy xác nhận công tác, M1.1)

- **Lấy bằng `curl` ngày 2026-10-21**, không qua công cụ tóm tắt web; nguồn đã ghi ở `nghi-dinh-30-2020-phong-chu-va-pham-vi.md`: PDF Công báo số 283 + 284 (17-3-2020), 82 trang, **có lớp chữ**, URL `https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2020/3/30858/30246-1-2020283-28430-2020-nd-cp.pdf`, **sha256 `698e45e0aae921a20c0e31ffa87c50fd0324f640e70a6eca8d49e4f51045c7bb`** — tải lại lần này, khớp.
- **Cách trích:** `pypdf` 4.3.1 đọc lớp chữ. Lớp chữ có khoảng trắng thừa giữa các chữ ("Tiêu ng ữ", "n ăm"); các trích dẫn dưới đây **gộp khoảng trắng thừa, không đổi chữ nào**. Số trang là số trang in của Công báo. Hình minh họa vị trí các ô (Phần I mục IV) là **hình, không có lớp chữ** — chưa đối chiếu.
- **Phạm vi:** chỉ những thành phần mà mẫu `tpl_work_confirmation.docx` dùng. Phụ lục III (27 loại văn bản) không có "Giấy xác nhận" — xem `nghi-dinh-30-2020-so-ky-hieu-van-ban.md`.

## Phần I, mục I. Quy định chung (Công báo, trang 22)

> 1. Khổ giấy: Khổ A4 (210 mm x 297 mm).
> […]
> 3. Định lề trang: Cách mép trên và mép dưới 20 - 25 mm, cách mép trái 30 - 35 mm, cách mép phải 15 - 20 mm.
> 4. Phông chữ: Phông chữ tiếng Việt Times New Roman, bộ mã ký tự Unicode theo Tiêu chuẩn Việt Nam TCVN 6909:2001, màu đen.
> 5. Cỡ chữ và kiểu chữ: Theo quy định cụ thể cho từng yếu tố thể thức.
> 6. Vị trí trình bày các thành phần thể thức: Được thực hiện theo Mục IV Phần I Phụ lục này.
> 7. Số trang văn bản: Được đánh từ số 1, bằng chữ số Ả Rập, cỡ chữ 13 đến 14, kiểu chữ đứng, được đặt canh giữa theo chiều ngang trong phần lề trên của văn bản, không hiển thị số trang thứ nhất.

## Phần I, mục II. Các thành phần thể thức chính

**1. Quốc hiệu và Tiêu ngữ** (trang 22–23)

> a) Quốc hiệu "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM": Được trình bày bằng chữ in hoa, cỡ chữ từ 12 đến 13, kiểu chữ đứng, đậm và ở phía trên cùng, bên phải trang đầu tiên của văn bản.
> b) Tiêu ngữ "Độc lập - Tự do - Hạnh phúc": Được trình bày bằng chữ in thường, cỡ chữ từ 13 đến 14, kiểu chữ đứng, đậm và được canh giữa dưới Quốc hiệu; chữ cái đầu của các cụm từ được viết hoa, giữa các cụm từ có gạch nối (-), có cách chữ; phía dưới có đường kẻ ngang, nét liền, có độ dài bằng độ dài của dòng chữ.
> c) Quốc hiệu và Tiêu ngữ được trình bày tại ô số 1 Mục IV Phần I Phụ lục này. Hai dòng chữ Quốc hiệu và Tiêu ngữ được trình bày cách nhau dòng đơn.

**2. Tên cơ quan, tổ chức ban hành văn bản** (trang 23)

> b) Tên cơ quan, tổ chức ban hành văn bản được trình bày bằng chữ in hoa, cỡ chữ từ 12 đến 13, kiểu chữ đứng, đậm, được đặt canh giữa dưới tên cơ quan, tổ chức chủ quản trực tiếp; phía dưới có đường kẻ ngang, nét liền, có độ dài bằng từ 1/3 đến 1/2 độ dài của dòng chữ và đặt cân đối so với dòng chữ.
> […]
> c) Tên cơ quan, tổ chức ban hành văn bản được trình bày tại ô số 2 Mục IV Phần I Phụ lục này.

**3. Số, ký hiệu của văn bản** (trang 23–24)

> c) Số, ký hiệu của văn bản được đặt canh giữa dưới tên cơ quan, tổ chức ban hành văn bản. Từ "Số" được trình bày bằng chữ in thường, cỡ chữ 13, kiểu chữ đứng; sau từ "Số" có dấu hai chấm (:); với những số nhỏ hơn 10 phải ghi thêm số 0 phía trước. Ký hiệu của văn bản được trình bày bằng chữ in hoa, cỡ chữ 13, kiểu chữ đứng. Giữa số và ký hiệu văn bản có dấu gạch chéo (/), giữa các nhóm chữ viết tắt trong ký hiệu văn bản có dấu gạch nối (-), không cách chữ.
> d) Số, ký hiệu của văn bản được trình bày tại ô số 3 Mục IV Phần I Phụ lục này.

**4. Địa danh và thời gian ban hành văn bản** (trang 24–25)

> b) Thời gian ban hành văn bản là ngày, tháng, năm văn bản được ban hành. Thời gian ban hành văn bản phải được viết đầy đủ; các số thể hiện ngày, tháng, năm dùng chữ số Ả Rập; đối với những số thể hiện ngày nhỏ hơn 10 và tháng 1, 2 phải ghi thêm số 0 phía trước.
> c) Địa danh và thời gian ban hành văn bản được trình bày trên cùng một dòng với số, ký hiệu văn bản, tại ô số 4 Mục IV Phần I Phụ lục này, bằng chữ in thường, cỡ chữ từ 13 đến 14, kiểu chữ nghiêng; các chữ cái đầu của địa danh phải viết hoa; sau địa danh có dấu phẩy (,); địa danh và ngày, tháng, năm được đặt dưới, canh giữa so với Quốc hiệu và Tiêu ngữ.

**5. Tên loại và trích yếu nội dung văn bản** (trang 25)

> b) Tên loại và trích yếu nội dung văn bản được trình bày tại ô số 5a Mục IV Phần I Phụ lục này, đặt canh giữa theo chiều ngang văn bản. Tên loại văn bản được trình bày bằng chữ in hoa, cỡ chữ từ 13 đến 14, kiểu chữ đứng, đậm. Trích yếu nội dung văn bản được đặt ngay dưới tên loại văn bản, trình bày bằng chữ in thường, cỡ chữ từ 13 đến 14, kiểu chữ đứng, đậm. Bên dưới trích yếu nội dung văn bản có đường kẻ ngang, nét liền, có độ dài bằng từ 1/3 đến 1/2 độ dài của dòng chữ và đặt cân đối so với dòng chữ.

**6. Nội dung văn bản** (trang 27)

> e) Nội dung văn bản được trình bày bằng chữ in thường, được canh đều cả hai lề, kiểu chữ đứng; cỡ chữ từ 13 đến 14; khi xuống dòng, chữ đầu dòng lùi vào 1 cm hoặc 1,27 cm; khoảng cách giữa các đoạn văn tối thiểu là 6pt; khoảng cách giữa các dòng tối thiểu là dòng đơn, tối đa là 1,5 lines.

**7. Chức vụ, họ tên và chữ ký của người có thẩm quyền** (trang 27–28)

> c) […] Họ và tên người ký văn bản bao gồm họ, tên đệm (nếu có) và tên của người ký văn bản. Trước họ tên của người ký, không ghi học hàm, học vị và các danh hiệu danh dự khác. […]
> đ) Quyền hạn, chức vụ của người ký được trình bày tại ô số 7a Mục IV Phần I Phụ lục này; chức vụ khác của người ký được trình bày tại ô số 7b Mục IV Phần I Phụ lục này, phía trên họ tên của người ký văn bản; các chữ viết tắt quyền hạn như: "TM.", "Q.", "KT.", "TL.", "TUQ." và quyền hạn chức vụ của người ký được trình bày bằng chữ in hoa, cỡ chữ từ 13 đến 14, kiểu chữ đứng, đậm. Chữ ký của người có thẩm quyền được trình bày tại ô số 7c Mục IV Phần I Phụ lục này. Họ và tên của người ký văn bản được trình bày tại ô số 7b Mục IV Phần I Phụ lục này, bằng chữ in thường, cỡ chữ từ 13 đến 14, kiểu chữ đứng, đậm, được đặt canh giữa quyền hạn, chức vụ của người ký.

**9. Nơi nhận** (trang 29–30)

> c) Đối với những văn bản khác, nơi nhận bao gồm từ "Nơi nhận" và phần liệt kê các cơ quan, tổ chức, đơn vị và cá nhân nhận văn bản.
> d) Nơi nhận được trình bày tại ô số 9a và 9b Mục IV Phần I Phụ lục này bao gồm:
> Phần nơi nhận tại ô số 9a (áp dụng đối với Tờ trình, Báo cáo của cơ quan, tổ chức cấp dưới gửi cơ quan, tổ chức cấp trên và Công văn): Từ "Kính gửi" và tên các cơ quan, tổ chức hoặc cá nhân nhận văn bản được trình bày bằng chữ in thường, cỡ chữ từ 13 đến 14, kiểu chữ đứng; sau từ "Kính gửi" có dấu hai chấm (:). […]
> Phần nơi nhận tại ô số 9b (áp dụng chung đối với các loại văn bản): Từ "Nơi nhận" được trình bày trên một dòng riêng (ngang hàng với dòng chữ "quyền hạn, chức vụ của người ký" và sát lề trái), sau có dấu hai chấm (:), bằng chữ in thường, cỡ chữ 12, kiểu chữ nghiêng, đậm; phần liệt kê các cơ quan, tổ chức, đơn vị và cá nhân nhận văn bản được trình bày bằng chữ in thường, cỡ chữ 11, kiểu chữ đứng; tên mỗi cơ quan, tổ chức, đơn vị và cá nhân hoặc mỗi nhóm cơ quan, tổ chức, đơn vị nhận văn bản được trình bày trên một dòng riêng, đầu dòng có gạch đầu dòng (-) sát lề trái, cuối dòng có dấu chấm phẩy (;), dòng cuối cùng bao gồm chữ "Lưu" sau có dấu hai chấm (:), tiếp theo là chữ viết tắt "VT", dấu phẩy (,), chữ viết tắt tên đơn vị (hoặc bộ phận) soạn thảo văn bản và số lượng bản lưu, cuối cùng là dấu chấm (.).

## Phần V. Mẫu chữ và chi tiết trình bày (Công báo, trang 34–35) — các dòng dùng cho mẫu

> Chú thích 1 của bảng: Cỡ chữ trong cùng một văn bản tăng, giảm phải thống nhất, ví dụ: Quốc hiệu cỡ chữ 13, Tiêu ngữ cỡ chữ 14, địa danh và ngày, tháng, năm văn bản cỡ chữ 14 hoặc Quốc hiệu cỡ chữ 12, Tiêu ngữ cỡ chữ 13, địa danh và ngày, tháng, năm văn bản cỡ chữ 13.

| Thành phần | Loại chữ | Cỡ chữ | Kiểu chữ | Ví dụ minh họa |
|---|---|---|---|---|
| Quốc hiệu | In hoa | 12 - 13 | Đứng, đậm | CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM (cỡ 12) |
| Tiêu ngữ | In thường | 13 - 14 | Đứng, đậm | Độc lập - Tự do - Hạnh phúc (cỡ 13) |
| Tên cơ quan, tổ chức ban hành văn bản | In hoa | 12 - 13 | Đứng, đậm | CỤC VĂN THƯ VÀ LƯU TRỮ NHÀ NƯỚC (cỡ 12) |
| Số, ký hiệu của văn bản | In thường | 13 | Đứng | Số: 15/QĐ-BNV; Số: 05/BNV-VP; Số: 12/UBND-VX (cỡ 13) |
| Địa danh và thời gian ban hành | In thường | 13 - 14 | Nghiêng | "Hà Nội, ngày 05 tháng 01 năm 2020"; "Thành phố Hồ Chí Minh, ngày 29 tháng 6 năm 2019" (cỡ 13) |
| Tên loại văn bản (có tên loại) | In hoa | 13 - 14 | Đứng, đậm | CHỈ THỊ (cỡ 14) |
| Nội dung văn bản | In thường | 13 - 14 | Đứng | "Trong công tác chỉ đạo…" (cỡ 14) |

**Nói thẳng:** ví dụ "Hà Nội, ngày 05 tháng 01 năm 2020" ghi số ngày có số 0 phía trước và chữ "ngày", "tháng", "năm" — dạng `dd/mm/yyyy` không phải dạng ví dụ của Nghị định. Mẫu tách `dd/mm/yyyy` thành "ngày dd tháng mm năm yyyy" bằng điều kiện trong mẫu.
