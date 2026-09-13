# LibreOffice — tham số dòng lệnh cho chuyển đổi không giao diện

- **Nguồn:** `https://help.libreoffice.org/latest/en-US/text/shared/guide/start_parameters.html` — trang "Starting LibreOffice Software With Parameters".
- **Ngày lấy:** 2026-09-13, bằng `curl`. Văn bản HTML được tách thẻ; câu chữ giữ nguyên.
- **Phiên bản mà nguồn mô tả:** trang ghi "LibreOffice 26.8 Help". Đường dẫn `latest` trỏ tới bản mới nhất lúc lấy; bản cài trong image có thể khác — `[CẦN XÁC MINH]` khi chốt image.
- **Dùng cho:** ADR-015, A-032.

---

> --headless
> Starts in "headless mode" which allows using the application without user interface.
> This special mode can be used when the application is controlled by external clients via the API.

> --convert-to OutputFileExtension[:OutputFilterName[:OutputFilterParams[,param]]] [--outdir output_dir]
> If --convert-to is used more than once, last value of OutputFileExtension[:OutputFilterName[:OutputFilterParams]] is effective. If --outdir is used more than once, only its last value is effective. In absence of --outdir, current working directory is used for the result. For example:
> --convert-to pdf *.doc
> --convert-to pdf:writer_pdf_Export --outdir /home/user *.doc

> -env:VAR[=VALUE]
> Set a bootstrap variable. For example, to set a non-default user profile path:
>  soffice -env:UserInstallation=file:///tmp/test

> --norestore
> Disables restart and file recovery after a system crash.

> --nolockcheck
> Disables check for remote instances using the installation.

---

## Nguồn này **không** nói

Mọi điều sau đây nằm ngoài trang và giữ `[CẦN XÁC MINH]`: giấy phép của LibreOffice và điều khoản phân phối nó trong một image; cách LibreOffice chọn font thay thế khi font được yêu cầu không có; PDF xuất ra có tất định theo byte hay không, và có tham số nào cố định thời điểm tạo, producer hay định danh tài liệu hay không; mức bộ nhớ và thời lượng một lần chuyển đổi; hành vi khi nhiều tiến trình dùng chung một hồ sơ người dùng.
