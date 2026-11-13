# x-mansion — 中心化 AI Skill 母仓库

这个仓库是 AI skill 的中心管理仓库，通过 `xman` CLI 管理 skill、agent 和项目上下文。

## 核心概念

- 三层架构：`skills/`（知识模板）、`agents/`（编排器）、`context/`（项目上下文基础设施）
- `skills/` 是 skill 唯一事实源，`agents/` 是 agent 唯一事实源
- Agent 定义是扁平的 `agents/<name>.md`，同名目录只放伴随文件；埋成 `<name>/AGENT.md` 会让它在 plugin 分发时静默消失
- 安装通过软链实现，不复制文件，本地修改即时生效
- `governance/skills-registry.csv` 管理状态和类型（type 列区分 skill / agent / deprecated）
- `release` 列标出发行版里也有同名一份的条目；plugin 和 `xman install` 都发完整的一套。Codex 里两个 plugin 同时启用时，`./xman plugin takeover` 停用发行版那个，同名 skill 统一用本仓的
- `team/skills/` 和 `plugins/*/` 是软链视图，不要直接编辑
- `context/conventions.md` 是所有产物路径的单一事实源
- 每个本仓维护的 skill 都要声明调用方式：会写文档、改代码、动 git 或部署的写 `disable-model-invocation: true`，并在 `agents/openai.yaml` 写 `policy.allow_implicit_invocation: false`；只读检查和参考指南写 `false`。`tests/test_skill_lint.py` 校验两处一致
- 新增、改名或删除人触发的 skill 时，同步更新路由 `skills/ask-xman/SKILL.md`；`tests/test_skill_lint.py` 会检查覆盖
- 新建或修改 skill 前，调用 Skill 工具（参数为 `writing-for-agents`）；考虑过但决定不做的事记在 `.out-of-scope/`

## 安装 skill

```bash
# 安装到全局
./xman install claude --status team-shared
./xman install codex --status team-shared
./xman install cursor --status team-shared
./xman install gemini --status team-shared
./xman install all --status team-shared

# 安装到项目根目录
./xman install claude --project /path/to/project
./xman install codex --project /path/to/project

# 安装单个 skill
./xman install claude --skill bug-fix
./xman install claude --skill bug-fix --project /path/to/project

# 安装某个分组
./xman install claude --plugin engineering

# 直接安装始终保持完整，不依赖另一个 plugin 是否已安装
./xman install claude --status team-shared
```

## 常用命令

```bash
./xman setup                    # 首次设置（检查依赖 + 构建 plugin + 校验）
./xman plugin build             # 重建本地 plugin
./xman plugin takeover          # Codex 双装时停用发行版 plugin，同名 skill 用本仓的（restore 恢复）
./xman plugin check             # 检查 plugin 是否与源文件一致
./xman list                     # 列出所有 skill
./xman list --status team-shared  # 只看团队共享的
./xman validate                 # 校验仓库一致性
./xman validate --fix           # 自动修复（team 软链 + CSV 排序）
./xman new <name> --plugin <p>  # 创建新 skill 脚手架
./xman doctor                   # 检查运行环境依赖

# 上下文管理
./xman context init [DIR]       # 初始化项目上下文（替代旧 /init-context skill）
./xman context status [DIR]     # 查看上下文状态
./xman context check [DIR]      # 校验上下文完整性

# Agent 管理
./xman agent list               # 列出所有 agent
```

## 项目约定

- Git remote 使用 `github` 别名（不是默认的 `origin`）
- 新增 skill 后必须同步更新 `governance/skills-registry.csv`
- CSV 按 skill 字段字母升序排列
- 新 skill 默认状态为 `experimental`，稳定后升级为 `team-shared`
- 不要直接修改 `team/skills/` 或 `plugins/*/` 中的内容，只改 `skills/` 本体
- Skill body 中不应包含门控逻辑（如检查 project-context.md 是否存在），改用 front-matter `requires_context` 声明
- Skill body 中不应硬编码产物路径，引用 `.ai-configs/conventions.md`（skill 运行侧落地路径；母仓事实源为 `context/conventions.md`）

## 不要做的事

- 不要修改 `skills/` 下的 SKILL.md 内容，除非用户明确要求
- 不要手动创建软链，用 `./xman new` 或 `./xman validate --fix`
- 不要在 CSV 中手动插入不排序的行
- 不要在 skill body 中内联门控逻辑（检查 project-context.md），用 `requires_context: [project]` 声明
- 不要把编排类能力放在 `skills/`，编排器属于 `agents/`
