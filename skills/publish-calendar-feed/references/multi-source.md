# 可选多来源合并

每个对话或项目维护自己的源文件，由一个入口生成同一个订阅。这里的“来源”是实际文件，不是自动读取聊天记录。所有来源采用同一清单，既可在本机生成，也可交给 [云端模板](cloud-publishing.md)。

## 文件与责任分配

```text
calendar-inputs/
  calendar.json
  sources/
    legacy.ics       已有订阅快照，或原生成器持续输出
    study.json       学习对话维护
    thesis.json      毕设对话维护
```

每个维护对话应记录：自己负责的源路径、永久 feed_id、统一清单路径、谁负责最终发布。只修改自己负责的文件；新增来源时再修改清单。多个本地对话共享一个 checkout 时，不要同时提交对方未完成的文件。多人或多 checkout 协作时，正常提交并合并来源变更；冲突由对应维护者解决，不强推。

## 清单

可直接查看合成 [calendar.json](../assets/multi-source/calendar.json) 和同目录 `sources`。清单内容：

```json
{
  "calendar_name": "学习与毕设",
  "sources": [
    {"id": "legacy", "path": "sources/legacy.ics", "format": "ics"},
    {"id": "study", "path": "sources/study.json", "format": "json"},
    {"id": "thesis", "path": "sources/thesis.json", "format": "json"}
  ]
}
```

`id` 是清单内唯一的来源名称；`path` 相对清单目录，解析后的路径必须仍在该目录内。不能填写网址、机器绝对路径或指向外部的符号链接。`format` 为 `json` 或 `ics`。可明确设置 `enabled: false` 停用来源；默认启用。停用会移除该来源在合并结果中的事件，执行前检查意图。

JSON 使用 [单来源字段](setup.md)，每个源的 `feed_id` 必须永久且互不相同，如 `study`、`thesis`。来源文件移位置或清单重排不改变身份。同一来源内 `id` 不能重复；不同源的同名 id 可共存。输出继续使用原单 JSON 生成器的 UID 算法，因此从单 JSON 改为同一 JSON 的合并输入不会重建身份。

## 合并与校验

先安装可选依赖（路径从 skill 根目录计算）：

```powershell
python -m pip install -r requirements-merge.txt
python scripts/build_calendar.py --manifest assets/multi-source/calendar.json --check
python scripts/build_calendar.py --manifest assets/multi-source/calendar.json --output output/study-plan.ics
```

正式运行时把清单和输出路径换成实际路径。校验任一来源失败就停止，既有输出不被覆盖；不会跳过缺失来源然后发布缩水日历。全空结果会被拒绝。相同输入输出字节不变，不每天改版本或时间戳。

ICS 来源保留原 VEVENT 的 UID、时刻、状态、周期、例外、全天字段和嵌套提醒，以及 VTIMEZONE。相同 UID 的周期主事件和不同 RECURRENCE-ID 例外可共存；重复的同一事件身份或冲突的同名时区定义会失败，不采用“最后来源覆盖前者”。相同的时区定义只保留一份。

只接受 VCALENDAR 2.0，其中顶层组件为 VEVENT 和 VTIMEZONE。遇到 VTODO、VJOURNAL 等其他组件会明确拒绝，不能假装完整保留。合并器不展开周期，不替来源修改版本，不重写成 JSON，也不消除时间上重叠的不同事件。

## 接入已有订阅

1. 保存当前 ICS、订阅 URL 和事件 UID 清单。只读验证源文件可解析；旧 Windows 重复回车会在读取时规范化，不修改来源文件。
2. 把当前 ICS 作为 `legacy.ics` 来源，新增对话源采用新的 feed_id。本地合并后，检查旧组件全部仍在，新增事件身份唯一，提醒和周期未丢失。
3. 保留原 URL 的文件名，例如 `study-plan.ics`，把完整合并结果交给唯一发布者。不能只把新增事件复制到发布文件末尾。
4. 原学习生成脚本若继续更新，应让它写 `sources/legacy.ics` 再触发合并；不要让它直接用旧的纯学习结果覆盖最终 feed。若使用快照，明确它不会自行变化，不能称为持续同步。
5. 日常取消新事件时更新同一 id 的 `status: CANCELLED`、sequence 和 updated_at。取消旧 ICS 事件应由该源的维护者在保留 UID 的前提下处理。

## 本机发布

本机方式通常把输入目录放在发布 checkout 之外，避免源文件编辑触发发布器的脏工作区保护：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\CalendarDemo\skill\scripts\Publish-Feed.ps1" -ManifestPath "C:\CalendarDemo\calendar-inputs\calendar.json" -PublishRepo "C:\CalendarDemo\calendar-publish" -Python "C:\CalendarDemo\venv\Scripts\python.exe" -Publish
```

示例路径均需替换；`-InputPath` 与 `-ManifestPath` 互斥。省略 `-Publish` 只生成，预览之后检查并处理产生的本地变更，再正式发布。旧的单来源调用方式保持兼容。

如果输入文件也保存在发布仓库内，先单独提交并推送已审阅的来源变更，使 checkout 恢复干净，再运行本机发布器。该脚本不会顺带提交来源，也不会推送混有无关文件的本地提交。若已选择云端发布，通常只推送来源变更，让云端成为唯一发布者。

单来源也能使用此入口：清单只留一个来源即可，示例见 [calendar.single.json](../assets/multi-source/calendar.single.json)。
