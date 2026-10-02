# GitHub Models — đã ngừng hoạt động

- **Nguồn — lấy bằng `curl`, ngày 2026-10-02:**
  - `https://docs.github.com/en/github-models` — sha256 của bản đã lấy `f5a981a38473eeb625e2627f4fccc760d3249de445c5583862f5b55cf99fa3d1`
- **Cách tách:** bỏ `<script>`, `<style>`, `<svg>`; thẻ tiêu đề thành `##`, thẻ khối thành xuống dòng; câu chữ giữ nguyên. Trang tài liệu sống — có thể đổi sau ngày lấy.
- **Dùng cho:** ADR-032, A-026 — cổng 1.5 của `12-roadmap.md`; danh sách ngắn của PO ngày 2026-10-02. Hồ sơ đánh số theo mục Options của ADR-032: 1 điều khoản dữ liệu · 3 structured output · 4 giá · 5 giới hạn. Ứng viên dự phòng của PO.

---

Các đường dẫn tài liệu cũ — prototyping, responsible use, billing — đều chuyển hướng về trang dưới. Trích nguyên văn:

> GitHub Models has been retired.
>
> As of July 30, 2026, GitHub Models has been fully retired. The playground, model catalog, inference API, and bring your own key (BYOK) are no longer available to any customer.
>
> GitHub Models was a separate service from GitHub Copilot and is unrelated to GitHub Copilot services.
>
> ## Where to go next
>
> For new and existing projects that need AI model access, Azure AI Foundry offers a broad model catalog.
>
> To build AI-powered workflows directly on GitHub, you can use GitHub Copilot, which gives you access to a range of models. For more information, see GitHub Copilot documentation.

**Kết luận cho BO-19:** loại khỏi danh sách ngắn — dịch vụ không còn.
