# 可选 GitHub Actions 云端发布

适合来源已同步到 GitHub、需要电脑关机后仍能定时生成的情况。它与多来源选项独立：同一个模板支持单条来源清单，也支持多个来源合并。原来的单 JSON、本机发布仍可继续使用。

模板文件：[publish-calendar.yml](../assets/github-actions/publish-calendar.yml)。它放在 skill 的 assets 内，不会因安装 skill 自动运行。

## 云端能读取什么

模板读取仓库 checkout 中的清单、JSON 和 ICS。它不访问电脑磁盘，不自动抓聊天记录或 Obsidian，不会自动知道导师或老师修改了安排。本地源发生变化后，维护对话必须把获授权的变更提交并推送。需要联网获取数据时，应另建有明确权限的来源更新步骤，再交给统一生成器。

GitHub Pages 的最终 feed 仍公开。将私有源放进公开仓库也会使源公开；仅使用 Secrets 保存认证信息并不能隐藏已发布的日程内容。此模板不要求新的 PAT，不上传凭证，也不会修改仓库可见性。

## 一次配置

在实际 feed 仓库按以下映射放置文件。已有同名文件先检查、合并配置，不直接覆盖。需要使用全部脚本时，可从已验证的 skill 版本复制，并记录版本。

| skill 包内文件 | feed 仓库目标 |
|---|---|
| `scripts/build_feed.py` | `tools/calendar/build_feed.py` |
| `scripts/build_calendar.py` | `tools/calendar/build_calendar.py` |
| `requirements-merge.txt` | `tools/calendar/requirements-merge.txt` |
| 本地已验证的清单 | `calendar.json` |
| 清单引用的全部已授权来源 | `sources/...`，保持相对路径 |
| `assets/github-actions/publish-calendar.yml` | `.github/workflows/publish-calendar.yml` |

1. 在本地安装合并依赖，使用复制后的脚本生成并校验：

   ```powershell
   python tools/calendar/build_calendar.py --manifest calendar.json --check
   python tools/calendar/build_calendar.py --manifest calendar.json --output output/study-plan.ics
   ```

2. 保留 `.gitattributes` 的 `*.ics -text`。确认旧事件与 UID 全部保留，且可公开内容范围正确；提交上述文件。不要把预览输出、日志、虚拟环境或本机凭证一起提交。
3. 仓库 **Settings → Pages → Source** 选择 **GitHub Actions**。已有订阅应使用原 feed 仓库及原文件名；切换前检查自定义域名与发布路径，保持原订阅 URL。[官方配置说明](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
4. 在 **Settings → Secrets and variables → Actions → Variables** 添加 `CALENDAR_CLOUD_PUBLISH=true`。没有这个明确开关，模板的构建和部署均不会执行。
5. 如果默认分支不是 `main`，修改模板 `push.branches`。模板还会检查运行分支等于仓库默认分支，避免手动从测试分支发布。
6. 可选变量 `CALENDAR_MANIFEST` 指定其他清单路径，默认 `calendar.json`。模板监听默认分支上的全部推送，不会因改了清单路径而漏触发。
7. 在 Actions 页面手动运行 **Publish calendar subscription**。生成失败会阻止上传和部署，线上保留上一次成功部署；检查日志和 Pages 状态后，读取真实 HTTPS feed 核验内容。

源文件本身不出现在部署 artifact 中；模板在 runner 临时目录中按本次 run/attempt 建立独立站点目录，只放生成的 `study-plan.ics` 和 `source-commit.txt`，不会顺带上传 checkout 内已有的 `_site` 文件。源文件若存入公开仓库，仍可从仓库访问。

## 运行方式与边界

- 模板支持推送触发、手动触发和示例定时：每天 `00:17 UTC`，即中国时间 `08:17`。它是可替换的示例，不是用户当前已启用的提醒时间。
- GitHub 的定时运行依赖默认分支，可能延迟；公开仓库长期没有活动时也可能停用定时工作流。不能用它承诺精确到分钟的提醒。[GitHub 定时说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- 构建 checkout 默认分支最新来源，不回写生成文件，也不制造自动提交。每次使用同样的来源仍生成相同日历。
- 部署等待构建成功，并使用 `github-pages` 环境。构建只有仓库读取权限，部署 job 才有 Pages 与 OIDC 权限；并发组避免部署互相打断。
- `source-commit.txt` 用于核对实际生成版本。Git push 成功、Actions 成功、远程 ICS 正确和手机已刷新仍是不同证据。

## 切换、停用与回退

切换正式订阅前，先完成多来源本地核验，再按用户选择停用旧本机发布入口，使云端成为唯一发布者；不能让旧脚本继续用不含新来源的文件覆盖同一 URL。依赖本机产生的来源仍需有单独的源更新流程，云端只替代生成与发布部分。

停用时删除或设 `CALENDAR_CLOUD_PUBLISH=false`，并检查是否有正在进行的部署；变量只影响后续 run。不要据此删除用户订阅。回退本机发布时，先从同一清单生成完整结果，再按实际 Pages 设置切回分支发布并验证原 URL。保留来源文件和最后一次正确输出以便恢复。

本技能仓库自身的 `Validate calendar skill` 只是合成数据 CI，不是实际日历云端发布。真实 Pages 部署必须在所选 feed 仓库显式接入；不能把合成 CI 通过报告为用户日历已迁移。
