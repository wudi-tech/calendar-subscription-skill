# 接入、更新与排查

## 1. 复用已有日历，或建立新 feed

已经订阅时先找到其实际 HTTPS 地址、生成入口和发布仓库。普通 GitHub 文件预览页不是 ICS 地址。不要反复下载、导入同一个日历来“刷新”。

新建时确定日程来源、时区、是否允许公开、客户端与提醒要求。公共 Pages 不适合放入账号、联系方式、会议密码或敏感个人行程。随机文件名不会让公开文件变成私密文件；删除文件也不会自动抹去 Git 历史。

以下示例用于新建独立 feed，使用 `my-calendar-feed` 作为可替换的仓库名。不要把正式个人日程直接提交进 skill 源码仓库。

## 2. 准备输入

复制 [events.example.json](../assets/events.example.json) 为本地 `events.json`，替换合成内容。生成器需要 Python 3.10+，无额外依赖。

| 字段 | 规则 |
|---|---|
| `feed_id` | 一个 feed 的永久标识，不随显示名称改变 |
| `calendar_name` | 客户端显示名 |
| `events` | 独立事件数组；同一 feed 内 `id` 唯一 |
| `id` | 同一事件的永久标识，标题/改期时保持不变 |
| `title`、`start`、`end` | 标题及带 UTC 偏移的 ISO 时间，例如 `2030-01-08T09:00:00+08:00` |
| `updated_at` | 此事件最后实际修改时间，带偏移、精确到秒；无修改就保留 |
| `sequence` | 初始 0，每次修改递增；生成器不会替你自动计数 |
| `description`、`location` | 可选文字；内容会随 feed 公开 |
| `alarm_minutes` | 可选，提前 1–40320 分钟；省略或 null 不写提醒 |
| `status` | 默认 `CONFIRMED`；也可 `TENTATIVE` 或 `CANCELLED` |

生成器用 UTC 输出事件时刻，因此不会依赖电脑默认时区；客户端按其日历时区显示。它不推断夏令时：应先按事件所在地规则求出正确偏移，再输入。全天、RRULE 和周期例外不属于此示例支持范围。未知字段会报错，不会被悄悄丢弃；`uid` 覆盖也未实现，不能通过添加此字段完成旧 UID 迁移。

在 skill 仓库根目录运行：

```powershell
python skills/publish-calendar-feed/scripts/build_feed.py --input events.json --check
python skills/publish-calendar-feed/scripts/build_feed.py --input events.json --output output/study-plan.ics
```

检查事件数、UTC 换算、中文、UID、版本和 VALARM。相同输入重复运行应显示 `Unchanged`。生成器先完整验证，再原子替换，校验失败不会覆盖既有输出。

## 3. 建立专用发布仓库

已有仓库直接复用并检查 `git remote -v`、分支和 Pages 来源。新仓库可在网页创建；也可在已登录 GitHub CLI 的终端运行：

```powershell
gh repo create my-calendar-feed --public --clone
Set-Location my-calendar-feed
New-Item -ItemType File -Name .nojekyll
Set-Content -LiteralPath .gitattributes -Value '*.ics -text' -Encoding ascii
git add -- .nojekyll .gitattributes
git commit -m "Initialize calendar feed"
git branch -M main
git push -u origin main
```

这些命令会创建公开仓库，只有在发布范围已获授权时执行。不要将现有私有仓库改为公开以便继续。

GitHub 仓库 **Settings → Pages → Build and deployment → Source → Deploy from a branch → main / (root) → Save**。沿用已有自定义域名或发布来源时，按实际配置调整。[GitHub 官方步骤](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)

## 4. 发布

Windows 完整示例（`C:\CalendarDemo` 是示例路径，执行时替换成实际绝对路径）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\CalendarDemo\calendar-subscription-skill\skills\publish-calendar-feed\scripts\Publish-Feed.ps1" -InputPath "C:\CalendarDemo\events.json" -PublishRepo "C:\CalendarDemo\my-calendar-feed" -Publish
```

`-Python` 可指定解释器绝对路径；`-FeedName` 默认为 `study-plan.ics`。省略 `-Publish` 只在发布目录生成文件，不暂存、提交或推送。**预览生成后目录会有变更**：再次正式运行时先人工检查并处理这些变更，或清理已审阅的预览文件；脚本不会自动丢弃。

正式发布要求：专用仓库根目录、已设置 upstream、干净工作区。脚本持有仓库内独占锁，只暂存目标 ICS。已有未推送提交只允许包含目标 feed；推送失败保留提交，处理网络或认证后可原样重跑。分支冲突或远端变化由用户审阅并正常合并，不自动强推、不循环重试。

`.gitattributes` 中的 `*.ics -text` 用于保留 RFC 所需的 CRLF 字节。发布脚本会停用暂存时的 `core.autocrlf` 自动转换；仓库显式设置 `*.ics text` 或 `auto` 时会停止，要求先处理属性，避免本地正确、远端换行已改变。

Linux/macOS 可运行同一 Python 生成器，再在干净的专用仓库内只 `git add -- study-plan.ics`、检查差异、提交和正常推送。仓库里即使没有内容变化，也要检查是否有待推送的旧提交。

## 5. 核验远程文件

从 Pages 设置取得真实站点地址。常见项目地址形状为 `https://OWNER.github.io/my-calendar-feed/study-plan.ics`；自定义域名时以实际结果为准。

不要仅检查 HTTP 200。读取响应正文或保存远程 ICS，与本地字节/哈希比对，并确认 `BEGIN:VCALENDAR`、预期事件和版本。可在确认 URL 后，用 PowerShell 做一次明确比对：

```powershell
$FeedUrl = Read-Host "粘贴已核实的 HTTPS 日历地址"
$LocalIcs = Read-Host "粘贴本地 ICS 的绝对路径"
$RemoteIcs = Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString() + ".ics")
Invoke-WebRequest -Uri $FeedUrl -OutFile $RemoteIcs
(Get-FileHash -LiteralPath $RemoteIcs).Hash -eq (Get-FileHash -LiteralPath $LocalIcs).Hash
```

结果为 `True` 才证明该次抓取与本地一致。构建或缓存尚未更新时先查看 Pages 部署状态，有限等待后重新检查；不能无期限轮询。

## 6. 手机首次订阅

iPhone 通常可在 **日历 App → 日历 → 添加日历 → 添加订阅日历** 中粘贴 HTTPS feed 地址，预览并订阅。菜单可能随系统版本变化，应以设备界面为准。[Apple 日历说明](https://support.apple.com/en-lamr/guide/iphone/-iph3d1110d4/ios)

`webcal://` 是某些客户端打开订阅界面的可选链接方式；保留 HTTPS 地址作为可核验入口。其他客户端使用“从 URL / 订阅日历”入口；下载 ICS 后“导入”通常会产生独立副本。

选择一条合成测试事件核对日期、时间、标题和显示的时区。用户要求提醒时再添加 VALARM，检查该订阅的事件提醒、系统通知权限和设备状态，实测一次接近当前时间的提醒；验证完取消或删除测试事件。客户端可能忽略、隐藏或限制订阅源里的提醒，不能只看文件就宣称手机会响。

## 7. 日常修改

- 新增：分配新的永久 `id`，填真实起止时间与修改时间。
- 改期/改标题/改提醒：保留 `feed_id` 和 `id`，`sequence + 1`，更新 `updated_at`，重新生成并发布同一文件。
- 取消：保留身份，更新版本，设 `status: CANCELLED`，暂时保留取消记录供客户端刷新。显示/移除行为需实测，没有跨客户端通用的等待时长保证。
- 无变化：不改时间戳或版本；输出相同、不新建提交。
- 周期系列：沿用原生成器或支持完整重复规则的库；针对单次改课应正确处理 `RECURRENCE-ID`，不能用一个新独立事件覆盖整个系列。

已有 feed 切换生成器前，先读 [迁移边界](implementation.md)。

## 故障定位

| 现象 | 先检查 |
|---|---|
| 地址 404 | Pages 是否启用、分支/目录/文件名是否一致、部署是否完成 |
| HTTP 200 但无日程 | 返回的是否是 HTML、登录页、下载跳转或空事件数组 |
| 手机仍是旧内容 | 远程字节是否更新、订阅是否为同一 URL、客户端是否已刷新 |
| 改期变成两条 | 是否重建 UID、重复订阅或做了多次导入 |
| 时间偏差 | 输入是否带明确偏移、跨夏令时是否重新计算、客户端显示时区 |
| 没有提醒 | 是否写 VALARM、是否允许订阅提醒和系统通知、客户端是否支持 |
| 定时不运行 | 任务是否暂停/禁用、电脑是否开机、任务账户是否能访问解释器和 Git 凭证 |
| Git 推送被拒 | 认证、upstream、分支保护或远端新提交；停止并保留本地结果 |
