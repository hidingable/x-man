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

