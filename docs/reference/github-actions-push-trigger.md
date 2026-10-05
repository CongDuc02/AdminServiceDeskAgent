# GitHub Actions — trigger `push` có lọc `paths`, `concurrency`, thời lượng job, secret, `actions/checkout`

- **Nguồn — lấy bằng `curl`, ngày 2026-10-04** (tài liệu sống, không số phiên bản; GitHub có thể đổi sau ngày lấy):
  - `https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows` — sha256 `10ff4a55f35f8cbb491eb9a666274438b209e1a6d72cd00279c5f4281583473f` (cùng bản đã ghi ở `github-actions-workflow-dispatch.md`)
  - `https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax` — sha256 `9bba4d2eabc7197eda43fcc9d9976d4521f99aa2d5ead4ff2e8e0466f5229bd6`
  - `https://docs.github.com/en/actions/reference/limits` — sha256 `07787e38fe813bd89e6c06b5546cf9965b778147f6c7a470eb68361db032202b`
  - `https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency` — sha256 `262b93aacc47b9d5964169b6e0c3d417ba2e0019a19300c3892b5f7c3b30b4e3`
  - `https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions` — sha256 `945c60b3c725c9c37de1fe463dc58010699b870ce6f6a5494725fb382fd77a5c`
  - `https://raw.githubusercontent.com/actions/checkout/main/README.md` — sha256 `3df94d90d0df6df603a549cc779bc6cab4b21f8deef82eb6fef1f4d88b788174`
  - `https://api.github.com/repos/actions/checkout/git/ref/tags/v7` — trả `{'sha': '3d3c42e5aac5ba805825da76410c181273ba90b1', 'type': 'commit'}`
- **Cách tách:** bỏ thẻ HTML, giữ câu chữ nguyên văn.
- **Dùng cho:** workflow của S3 (A-050) — chạy `probe.py` từ runner GitHub Actions bằng trigger `push`, thay `workflow_dispatch` (`github-actions-workflow-dispatch.md`).

---

## 1. Nguyên văn

**`push` — chạy cả workflow chưa vào nhánh mặc định:**

> Runs your workflow when you push a commit or tag, or when you create a repository from a template. This includes workflows that are not merged into the default branch.

Bảng của mục `push` ghi `GITHUB_SHA` là "Tip commit pushed to the ref" và `GITHUB_REF` là "Updated ref".

**`paths` — lọc theo file đổi:**

> If you define both branches/branches-ignore and paths/paths-ignore, the workflow will only run when both filters are satisfied.

> The filter determines if a workflow should run by evaluating the changed files and running them against the paths-ignore or paths list. If there are no files changed, the workflow will not run.
> GitHub generates the list of changed files using two-dot diffs for pushes and three-dot diffs for pull requests:
> Pushes to existing branches: A two-dot diff compares the head and base SHAs directly with each other.
> Pushes to new branches: A two-dot diff against the parent of the ancestor of the deepest commit pushed.
> If a push contains more than 1,000 commits, the workflow will always run.
> If generating the diff times out, the workflow will always run.

**`concurrency`:**

> This means that there can be at most one running job or workflow in a concurrency group at any time. When a concurrent job or workflow is queued, if another job or workflow using the same concurrency group in the repository is in progress, the queued job or workflow will be pending. By default, any existing pending job or workflow in the same concurrency group will be canceled and the new queued job or workflow will take its place.

**Thời lượng job:**

> jobs.<job_id>.timeout-minutes — The maximum number of minutes to let a job run before GitHub automatically cancels it. Default: 360

Trang Limits, dòng "All GitHub-hosted runners | Job execution time | 6 hours": "Each job in a workflow can run for up to 6 hours of execution time. If a job reaches this limit, the job is terminated and fails."

**Secret:**

> With the exception of GITHUB_TOKEN, secrets are not passed to the runner when a workflow is triggered from a forked repository.

**`actions/checkout`:** README ghi mẫu `uses: actions/checkout@v7`. Tag `v7` trỏ tới commit `3d3c42e5aac5ba805825da76410c181273ba90b1` (lightweight tag, `type: commit`) — workflow ghim theo sha này.

## 2. Đọc — điều tài liệu **không** nói thẳng

| Câu hỏi | Theo nguồn |
|---|---|
| Workflow chạy theo file ở **chính commit được push** | Tài liệu nói `push` chạy cả workflow chưa vào nhánh mặc định và `GITHUB_SHA` là commit đỉnh được push. **Không có câu nói thẳng** file nào được đọc. Kiểm bằng lần chạy thật — `docs/design/CHANGELOG.md`, mục S3 |
| Secret của repo dùng được khi `push` lên nhánh của chính repo | Tài liệu chỉ nói secret **không** được truyền khi chạy từ **fork**. Không có câu khẳng định trường hợp nhánh của chính repo. Kiểm bằng lần chạy thật |
| Hàng đợi `concurrency` mặc định chỉ chứa **một** lượt đang chờ | Có — lượt chờ cũ bị huỷ khi có lượt mới. Hai push `run.json` sát nhau thì lượt giữa có thể bị huỷ; chờ lượt trước xong rồi mới push |
