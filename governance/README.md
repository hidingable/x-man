# Governance

这个目录放中心 skill 仓库的治理元数据。

## skills-registry.csv

`skills-registry.csv` 是当前唯一的状态登记表，字段如下：

- `skill`：原子 skill 名称，必须和 `skills/<name>/` 一致
- `status`：治理状态，活着的条目只允许以下三种
  - `team-shared`：团队默认可复用，允许进入标准同步集合
  - `personal-only`：强依赖个人环境、个人账号、个人服务器或个人偏好
  - `experimental`：尚未沉淀稳定工作流，保留试验和观察空间

  另有 `deprecated`，**仅用于墓碑行**：skill 已经移除或被别的东西取代，留一行记着它去哪了，
  免得有人再加回来。这类行的 `type` 也必须是 `deprecated`，且 `skills/` 下不该再有同名目录。
- `source`：当前事实来源，便于后续回溯
- `note`：补充说明，解释为什么这么标
- `source_type`：来源类型，当前约定 `local` / `external`
- `source_key`：当 `source_type=external` 时，对应 `governance/sources/<source_key>.json`
- `type`：条目类型，当前约定 `skill` / `agent` / `deprecated`
- `release`：实验场 plugin 构建时的过滤字段；非空项不打包进 plugin，不表示源码归属，也不影响 `xman install` 的完整安装

## governance/sources/*.json

外部来源的同步规则不直接塞进 CSV，而是单独放在 `governance/sources/`：

- CSV 只回答“这个 skill 是否外部、对应哪个 source manifest”
- manifest 负责定义“从哪个 repo、哪个 ref、哪些路径映射到本地哪些文件”

典型字段：

- `repo`：上游仓库地址
- `ref`：跟踪的分支或 tag
- `mappings[]`：同步映射
  - `type=file|dir`
  - `from`：上游相对路径
  - `to`：本仓库相对路径
  - `optional`：上游缺失时是否允许跳过
- `update_policy`：默认为 `mapped`；`manual-release` 用于 Git 仅维护源码、运行包需另外构建或获取的来源。
  此类映射供巡检与只读预览，不能把源码差异直接当作运行包升级。只要 `--apply` 批次包含此类来源，
  工具会在任何 clone 或目标写入前整批拒绝，并提示单独迁移已构建发行包；其余来源可用 `--skill` 单独选择。

当前 `codex-security` 属于 `manual-release`：上游公开源码已迁到 `plugins/codex-security`，
旧 `sdk/typescript/_bundled_plugin` 是生成目录，不再提交到 Git。映射同时观察 SDK 运行时及打包输入；
本地运行包取自 manifest 记录的发行资产。升级时核对 MCP、native 资源和本地防御性入口；构建 x-mansion 插件时从嵌套的运行包生成外层 Codex MCP 配置。

## 建议治理规则

1. 新增 skill 时，必须同步补 `skills-registry.csv`
2. `plugins/<name>/` 负责按职能分组；`status` 负责治理状态；`release` 只负责 plugin 构建时的过滤
3. 要给团队大面积开放之前，先从 `experimental` 升级到 `team-shared`
4. 任何带具体机器、账号、内网、服务器指向的 skill，默认先标 `personal-only`
5. 已归档或不建议继续扩散的 skill，不要直接放 `team-shared`
6. 外部 skill 必须补 `source_type=external + source_key`，并提供对应 manifest，避免“知道是外部的，但不知道怎么更新”

## 公开 checkout 与本机个人 skill

`xman setup`、plugin 构建和仓库校验共用以下缺省规则：条目必须是 `type=skill`、
`status=personal-only`，根 `.gitignore` 中明确列有 `skills/<name>/` 或 `/skills/<name>/`，
整个源目录节点缺失，且 Git 索引中没有该目录的已跟踪文件。无 `.git` 的源码包使用同一根目录声明。

满足这些条件的本地个人 skill 可以不随公开源码提供；构建会说明跳过项，正确指向它们的同名分类软链允许保留。
本机实际存在的个人 skill 继续完整校验和打包。普通 skill 缺失、已跟踪条目被误删、残缺目录、断开的源软链和指错位置的分类软链仍会失败。
共享判定在 `scripts/registry_scope.py`，不读取用户全局 ignore 或 `.git/info/exclude`。显式安装不存在的 skill 仍应报错。

## 排序约定

`skills-registry.csv` 的数据行必须按 `skill` 字段字母升序排列。
`validate.sh` 会自动检查排序，`validate.sh --fix` 可自动修正。

## 外部 Skill 更新通知

`.github/workflows/skill-updates.yml` 每天北京时间 09:17 运行只读上游巡检，也可以在
Actions 的 **External skill updates → Run workflow** 手动触发。手动运行默认 `dry_run=true`，
只输出检查结果；设为 `false` 才允许更新汇总 Issue。

来源仍由 registry 的 `source_type/source_key` 和 `sources/*.json` 决定。巡检按上游仓库
复用 API 请求，用各 manifest 的 `mappings` 和 `exclude` 筛选路径；它比较上次观察到的
上游版本，不拿本地中文入口或其他适配与上游比较。因此本地适配不会每天重复报更新。
固定 tag 的来源也会检查新正式 Release，`main` 等跟踪 ref 的相关内容变化同样会通知。
首次检查、新增来源或映射规则变动时先建立该来源的观察基线，不补发历史更新。

### 通知与去重

仓库 Actions 变量 `SKILL_UPDATE_NOTIFY` 填需要接收通知的 GitHub 登录名，多个用逗号分隔。
例如通过 CLI 设置：

```sh
gh variable set SKILL_UPDATE_NOTIFY --repo OWNER/REPO --body "your-github-login"
```

巡检维护一条带专用标记的汇总 Issue，保存上次成功观察的状态。配置的接收人会被指派，
有新变化时才新增一条汇总评论并 @ 接收人；评论包含受影响 Skill、旧新版本、路径和上游链接。
无新事件不新增评论，不自动重开已经关闭的 Issue。有新事件时会重开原汇总 Issue。
去重标记同时写入评论，避免评论成功但状态保存失败后再次通知。
标记区域以外的 Issue 正文保留；不要手工编辑标记内的机器状态。
GitHub 站内、邮件和手机推送的送达方式以接收人的 GitHub 通知设置为准。

某个上游请求失败时保留它的上次成功基线，其他来源继续检查；连续三次相同错误才发一次
故障评论，恢复后报告恢复。API 失败或不完整的 Git 树不会被当作“没有更新”。
检查结果和错误也会保留在 Actions 日志中。
局部来源失败但其余来源检查成功时，workflow 显示警告并继续维护汇总 Issue；
配置解析失败、Issue 写入失败或所有来源均失败时，workflow 失败。
命令行仍以非零退出码表示存在检查错误，不能把它解释为“无更新”。

### 权限与边界

工作流只有 `contents: read` 和 `issues: write`，不写仓库文件、不移动 ref、不执行上游代码、
不自动升级或提交 Skill。`xman update --apply` 仍是另一个需要明确执行的升级动作。
上游 API 只访问 GitHub；非 GitHub 来源会明确报告不支持，不会猜测其他平台的接口。

本地只读检查可运行：

```sh
python3 scripts/check-skill-updates.py --repo OWNER/REPO --json
```

可从 `GITHUB_TOKEN` 或 `GH_TOKEN` 提供令牌；令牌只用于 GitHub API，不输出到报告。
本地命令只用于预览；`--publish` 供 Actions 原生 `GITHUB_TOKEN` 使用，
汇总状态只识别 `github-actions[bot]` 创建的 Issue。需要初始化或更新通知时，
手动运行 workflow 并设 `dry_run=false`，不要用个人令牌在本地创建状态 Issue。

定时触发要求 workflow 已在默认分支；只推送到功能分支不会开启每天检查。
GitHub 调度可能延迟，公开仓库连续 60 天没有活动时也可能自动停用定时任务；
遇到停用需在 Actions 中重新启用。本巡检不通过制造无意义提交来维持调度。
