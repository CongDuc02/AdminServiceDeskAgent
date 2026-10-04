# Render — biến môi trường: ba cách lưu; Manual Deploy

- **Nguồn — lấy bằng `curl`, ngày 2026-10-04:**
  - `https://render.com/docs/configure-environment-variables` — sha256 `21f9ef0ff5c2d66f8e4f0cc76805e94c20d42194f8bd087b467111ea45485e19`
  - `https://render.com/docs/deploys` — sha256 `17898cb38e57dd4d2200d738fc18c47cb1d7923f7e33cc5b223a9ca0f7b739a4`
- **Cách tách:** bỏ thẻ HTML, giữ câu chữ; xuống dòng do thẻ được nối lại. Tài liệu sống — có thể đổi sau ngày lấy.
- **Dùng cho:** deploy B, C của S2 (`docs/reference/render-web-service-s2.md`).

## 1. Lưu biến môi trường

> Save your changes. You can select one of three options from the dropdown:
>
> Save, rebuild, and deploy: Render triggers a new build for your service and deploys it with the new environment variables.
>
> Save and deploy: Render redeploys your service's existing build with the new environment variables.
>
> Save only: Render saves the new environment variables without triggering a deploy. Your service will not use the new variables until its next deploy.
>
> That's it! Render saves your environment variables and then kicks off a deploy (unless you selected Save only).

## 2. Manual Deploy

> From your service's Deploys page in the Render Dashboard, open the Manual Deploy dropdown: Select a deploy option:
>
> Deploy latest commit — Deploys the most recent commit on your service's linked branch.
>
> Deploy a specific commit — Deploys a specific commit from your service's linked repo. Specify a commit by its SHA, or by selecting it from a list of recent commits. This disables automatic deploys for the service. This is because an automatic deploy might reintroduce commits you wanted to exclude from this deploy.
>
> Clear build cache & deploy — Similar to Deploy latest commit, but first clears the service's build cache. This way, the new deploy doesn't reuse any artifacts generated during a previous build.
>
> Restart service — Deploys the same commit that's currently deployed for the service, with the same values for user-defined environment variables.

> On Render, a service restart is actually a special form of manual deploy: Like any other deploy, Render creates a completely new instance of your service and swaps over to it when it's ready.
