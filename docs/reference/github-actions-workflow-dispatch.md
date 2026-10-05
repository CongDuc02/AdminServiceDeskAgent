# GitHub Actions — `workflow_dispatch`: file workflow phải nằm ở nhánh nào

- **Nguồn — lấy bằng `curl`, ngày 2026-10-04** (tài liệu sống, không số phiên bản; GitHub có thể đổi sau ngày lấy):
  - `https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/manually-running-a-workflow` — sha256 `413e9df53fdb5d2adc771496d00326c467cdb0435cb87ebd80cb64a55a0fbbc0`
  - `https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows` — sha256 `10ff4a55f35f8cbb491eb9a666274438b209e1a6d72cd00279c5f4281583473f`
  - `https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow` — sha256 `69779729f29336e3f878604ee85fb3bb64588fe821c3137d53e565eed9eba94e`
- **Cách tách:** bỏ thẻ HTML, giữ câu chữ nguyên văn.
- **Dùng cho:** bước chạy `probe.py` từ runner GitHub Actions của S3 (A-050). Kế hoạch S3 dùng `workflow_dispatch`.

---

## 1. Nguyên văn

Trang "Manually running a workflow":

> To run a workflow manually, the workflow must be configured to run on the workflow_dispatch event.
> To trigger the workflow_dispatch event, your workflow must be in the default branch.

> To run a workflow on a branch other than the repository's default branch, use the --ref flag.
> `gh workflow run WORKFLOW --ref BRANCH`

Trang "Events that trigger workflows", mục `workflow_dispatch`:

> This event will only trigger a workflow run if the workflow file exists on the default branch.
> To enable a workflow to be triggered manually, you need to configure the workflow_dispatch event. On the GitHub UI, the "Run workflow" button will be present if the workflow file exists on the default branch. Once a workflow has run at least once, you can dispatch it against any branch or tag via the GitHub API or GitHub CLI.

Trang "Triggering a workflow", mục "Defining inputs for manually triggered workflows":

> This trigger only receives events when the workflow file is on the default branch.

## 2. Đọc

- Cả ba trang cùng nói: `workflow_dispatch` chỉ kích hoạt khi file workflow **đã có trên nhánh mặc định**.
- `--ref` chọn nhánh hoặc tag mà lần chạy dùng làm `GITHUB_REF`; trang không nói file workflow được đọc từ nhánh đó hay từ nhánh mặc định, và câu "Once a workflow has run at least once" cho thấy lần chạy đầu vẫn cần file ở nhánh mặc định.
- Tên nhánh mặc định của repo này **chưa xác minh** từ GitHub — `git symbolic-ref refs/remotes/origin/HEAD` ở local không đặt.
