---
name: publish-calendar-feed
description: Use when a user wants schedules maintained in an ICS subscription, several chats or projects contributing to one calendar, or optional local and GitHub Actions publication. Also applies to migrating or troubleshooting an existing GitHub Pages calendar.
---

# 发布可持续更新的日历订阅

把日程来源转换为 ICS，发布到固定 HTTPS 地址，让手机订阅并拉取更新。适合课程、复习计划和公开活动。此路线是单向订阅；首次订阅通常需要用户在设备上操作。

## 选择可组合的选项

| 选择 | 入口 | 何时使用 |
|---|---|---|
| 单来源（原方式） | `build_feed.py --input` | 一个 JSON 源；无额外 Python 依赖 |
| 多来源（可选） | `build_calendar.py --manifest` | 多个对话各维护一份 JSON，或保留现存 ICS 后添加新来源 |
| 本机发布（原方式） | `Publish-Feed.ps1` | 本机生成、提交目标 ICS、推送 |
| 云端发布（可选） | GitHub Actions 模板 | 已授权的来源已同步到仓库，需要脱离本机定时生成 |

来源和发布位置是两个独立选择，可以组合成四种模式。保留已有模式，除非用户要求切换。只要求提供选项时，交付实现与模板，不自动启用真实订阅的云端定时或恢复旧任务。

## 先识别已有路线

读取实际生成脚本、发布仓库、订阅地址及任务状态。优先复用已经订阅的 URL；不要把旧配置当作当前运行的证据。历史路线与迁移注意事项见 [implementation.md](references/implementation.md)。

若用户明确选择其他日历服务，尊重该选择；私密数据或需要即时、双向编辑时，先发现适用的已连接日历工具，不擅自改成公开订阅。只需要聊天内提醒时，使用当前环境的提醒工具，无需建立 ICS 仓库。

## 执行流程

1. 从现有资料取得日期、起止时间、时区、重复规则及提醒偏好；相对日期按用户所在地换算。只询问无法推断且影响执行的信息，不凭空设定课程时长或重复规则。
2. 检查发布范围。公开 Pages 会公开 ICS 中的标题、描述、地点和时间；仅发布用户授权公开的内容，示例用合成数据，凭证留在本地。
3. 建立稳定的事件身份。新增事件分配永久 `id`；修改标题、时间或提醒时保留 `feed_id` 和 `id`，递增 `sequence`，更新 `updated_at`。无变化时保留版本和时间戳。
4. 单 JSON 的字段见 [setup.md](references/setup.md)。多来源时读 [multi-source.md](references/multi-source.md)，各对话只维护分配的源文件；每个 JSON 源的永久 `feed_id` 唯一，不能仅把同名 id 的数组拼在一起。把旧订阅作为 ICS 来源保留，不重建其 UID。清单重排不改变输出；冲突或来源缺失停止构建。先 `--check`，再生成并核对时间、事件身份、事件数与提醒。
5. 本机使用 [Publish-Feed.ps1](scripts/Publish-Feed.ps1)，选择 `-InputPath` 或 `-ManifestPath`，二者互斥；默认只生成，`-Publish` 才提交推送。云端按 [cloud-publishing.md](references/cloud-publishing.md) 安装模板并显式启用。云端只能读取已同步的源，不会自动读取聊天记录、本地 Obsidian 或电脑文件。只设置一个发布者，避免旧脚本覆盖合并结果。
6. 核对远程实际返回的 ICS 内容与本地结果。HTTP 成功但返回登录页、旧版本或 HTML 不算通过；Git 提交成功也不能证明 Pages 已部署。
7. 已有订阅无需重新导入。首次接入按 [setup.md](references/setup.md) 在客户端添加订阅地址。客户端刷新与通知能力需要设备端确认；不承诺即时刷新或弹窗已送达。
8. 用户要求持续运行时才配置触发器。复用已有任务并检查是否暂停；Windows 或 Codex 自动化路线见 [automation.md](references/automation.md)。生成脚本不会自动获知老师改课，必须有可读取的日程来源。

## 更新与提醒

| 情况 | 处理 |
|---|---|
| 改时间后出现重复日程 | 检查 UID 是否跟随内容变化；先保留旧 UID，再修改版本 |
| 取消独立事件 | 保留同一身份，更新版本，设 `status: CANCELLED`；确认客户端结果后再决定清理 |
| 原 feed 有周期系列或全天事件 | 作为 ICS 来源保留 UID、周期、例外、时区和提醒；JSON 新建仍只支持有起止时间的独立事件 |
| 提前提醒 | 经用户要求设置 `alarm_minutes`，检查生成的 VALARM 和客户端通知开关 |
| 发布了但手机没更新 | 分开检查生成、推送、Pages、订阅地址、客户端刷新；不反复导入文件 |

## 交付

说明已完成哪几层：本地生成、远程文件验证、定时任务验证、设备显示或提醒验证。给固定订阅地址和维护入口，明确尚未验证的层级。原文件没有 VALARM、任务暂停或时间范围已经过期时，如实说明。不要把“已发布”称作“已写入私人日历账户”。
