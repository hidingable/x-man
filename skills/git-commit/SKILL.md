---
name: git-commit
disable-model-invocation: true
description: "分析当前改动，生成 Conventional Commits 提交信息并提交；也可以按当前改动写 PR / MR 描述。"
metadata:
  category: engineering
  tags: [coding, git, workflow]
  dependencies: []
---

# Git Commit

仅通过 Git 分析改动并自动生成 Conventional Commits 提交信息（可选 emoji）；必要时建议拆分提交，默认运行本地 Git 钩子。

## 写 PR / MR 描述

用户要的是 PR 或 MR 描述时，读 `references/pr-description.md`，按它输出描述文本，不暂存也不提交。创建或更新 PR / MR 要用户明确要求才做。

## 选项

- `--no-verify`：跳过本地 Git 钩子
- `--all`：暂存区为空时自动 `git add -A`
- `--amend`：修补上一次提交
- `--signoff`：附加 `Signed-off-by` 行
- `--emoji`：提交信息包含 emoji 前缀
- `--scope <scope>`：指定作用域（如 `ui`、`docs`、`api`）
- `--type <type>`：强制提交类型，覆盖自动推断

## 工作流程

### 1. 仓库校验

- `git rev-parse --is-inside-work-tree` 确认位于 Git 仓库
- 读取当前分支/HEAD 状态；rebase/merge 冲突时提示先处理冲突

### 2. 改动检测

- `git status --porcelain` + `git diff` 获取已暂存与未暂存改动
- `git submodule status` 检测 submodule 状态（前缀 `+` 表示指针变更，`-` 未初始化，空格正常）
- `git diff --submodule=short` 获取 submodule 指针变更详情（旧 commit → 新 commit）
- 已暂存为空时：
  - 传入 `--all` → `git add -A`
  - 否则提示用户选择：分析未暂存改动给出建议，或手动暂存后再执行

### 2.1 Submodule 处理

检测到 submodule 变更时按以下策略处理：

**指针变更（submodule 内已提交，父仓指针待更新）：**
- `git diff --cached --submodule=log` 获取 submodule 内的 commit 摘要
- 将 submodule 更新视为独立变更组，建议与父仓其他改动分开提交
- 生成信息时包含 submodule 名称和方向（升级/回退/切换分支）

**脏 submodule（submodule 内有未提交改动）：**
- `git status --porcelain` 中标记为 dirty 的 submodule，**不自动暂存**
- 提示用户先进入 submodule 完成提交，再回到父仓提交指针变更
- 若用户明确要求忽略脏状态，使用 `git add <submodule-path>` 仅暂存指针

**多 submodule 批量更新：**
- 多个 submodule 同时更新时，判断是否属于同一目的（如依赖统一升级）
- 相关联的 submodule 更新可合并为一次提交；不相关的建议拆分

### 3. 拆分建议

按以下维度聚类，检测到多组独立变更时建议拆分并给出 pathspec：

- **关注点**：互不相关的功能/模块
- **类型**：不混合 `feat`/`fix`/`refactor`
- **文件模式**：源代码 vs 文档/测试/配置
- **规模阈值**：>300 行或跨多个顶级目录
- **可回滚性**：每个提交可独立回退
- **Submodule 边界**：submodule 指针变更与父仓代码改动分属不同提交

每组拆分使用它实际完成的事情作为标题，并同时给出 pathspec 和候选提交信息。例如「修复登录状态校验」「补充登录回归测试」。需要说明顺序时，直接写依赖关系，例如“先提交公共类型，再提交调用方”。

### 3.1 不确定时确认

先用 Git 历史、状态和差异自行判断。以下情况仍不明确时，停止暂存或提交，按 `.ai-configs/conventions.md`〈表达与命名〉的提问规则确认：

- 哪些文件属于本次提交，尤其是未跟踪文件或用户原有改动。
- 多组改动应该合并还是拆分，且不同选择会影响独立回退或审查。
- 是否允许 `--amend`、`--no-verify`、签名或包含 submodule 指针变化。
- 提交信息应描述哪个实际目的，现有差异无法支持唯一判断。

确认时列出完整文件范围、推荐做法和不同选择的影响，不让用户回复“提交一”“第二批”或字母代号。用户已经明确给出范围和选项时不重复询问。

### 4. 生成提交信息

格式：`[<emoji>] <type>(<scope>)?: <subject>`

**4.0 外部模型生成（可选）**

优先尝试通过外部模型生成消息（脚本：本 skill 目录下 `scripts/llm-commit.sh`）：

- 执行 `bash <skill 目录>/scripts/llm-commit.sh [--type <t>] [--scope <s>] [--emoji] [--lang zh|en]`，透传用户选项
- 退出码 `0`：stdout 即候选消息，进入把关清单
- 退出码 `2`（未配置外部模型）/ `3`（API 失败）/ `5`（diff 含疑似密钥已拒发）：静默回退到下方本地生成流程，`5` 时需向用户说明原因
- 把关清单（任一不过则重试脚本 1 次，再不过本地重写）：
  1. type 属于合法集合（feat/fix/docs/style/refactor/perf/test/chore/ci/revert）
  2. 首行 ≤ 72 字符，祈使语气
  3. 语言与仓库提交历史一致
  4. emoji 出现与否和 `--emoji` 选项一致

外部模型配置见 `scripts/llm-commit.env.example`（复制为 `llm-commit.env` 填写，不入库；shell 环境变量同名优先）。

**4.1 本地生成（默认/回退路径）**

- 自动推断 `type` 和 `scope`（`--type`/`--scope` 可覆盖）
- 首行 ≤ 72 字符，祈使语气
- 生成消息体：动机、实现要点、影响范围、BREAKING CHANGE（如有）
- 用字面、具体的语言描述改动
- 仅 `--emoji` 时包含 emoji
- 语言选择：检查 `git log -n 50 --pretty=%s` 判断中英文，无法判断时回退英文

**4.2 落盘**

- 将最终消息写入 `.git/COMMIT_EDITMSG`

### 5. 执行提交

- 单提交：`git commit [-S] [--no-verify] [-s] -F .git/COMMIT_EDITMSG`
- 多提交（接受拆分）：逐一执行 `git add <paths> && git commit ...`

### 6. 安全回滚

误暂存时用 `git restore --staged <paths>` 撤回（不修改文件内容）

## Type 与 Emoji 映射

| Emoji | Type | 说明 |
|-------|------|------|
| ✨ | `feat` | 新增功能 |
| 🐛 | `fix` | 缺陷修复 |
| 🔥 | `fix` | 删除代码/文件 |
| 🚑️ | `fix` | 紧急修复 |
| 🔒️ | `fix` | 安全修复 |
| 🚨 | `fix` | 解决告警 |
| 💚 | `fix` | 修复 CI |
| 👽️ | `fix` | 适配外部 API 变更 |
| 📝 | `docs` | 文档与注释 |
| 🎨 | `style` | 风格/格式（不改语义） |
| ♻️ | `refactor` | 重构 |
| ⚡️ | `perf` | 性能优化 |
| ✅ | `test` | 新增/修复测试 |
| 🔧 | `chore` | 构建/工具/杂务 |
| 👷 | `ci` | CI/CD 配置与脚本 |
| ⏪️ | `revert` | 回滚提交 |
| 💥 | `feat` | 破坏性变更（需 `BREAKING CHANGE:` 段） |
| ⬆️ | `chore` | 升级 submodule/依赖 |
| ⬇️ | `chore` | 回退 submodule/依赖 |

## 核心原则

- **仅使用 Git**：不调用任何包管理器/构建命令（外部模型脚本仅产文本，不执行任何 git 写操作）
- **生成可外包，把关执行不外包**：提交信息可委托外部模型生成，但格式把关与 git 执行始终本地完成；外部不可用时静默回退，不打断流程
- **尊重钩子**：默认执行本地 Git 钩子；`--no-verify` 可跳过
- **不改源码**：只读写 `.git/COMMIT_EDITMSG` 与暂存区
- **单一目的**：一次提交只完成一件能够独立理解和回退的事情
- **清晰主题**：首行 ≤ 72 字符，祈使语气
- **说清提交目的**：拆分建议和提交说明都用实际改动命名，不用“第一刀/第二刀”“第一批/第二批”或“提交 1/提交 2”代替含义

## 示例

**使用 --emoji：**

- ✨ feat(ui): add user authentication flow
- 🐛 fix(api): handle token refresh race condition
- 📝 docs: update API usage examples
- ♻️ refactor(core): extract retry logic into helper

**不使用 --emoji：**

- feat(ui): add user authentication flow
- fix(api): handle token refresh race condition
- docs: update API usage examples
- refactor(core): extract retry logic into helper

**按改动目的拆分：**

- **新增支付方式类型**：`feat(types): add payment method types`
- **更新支付方式文档**：`docs: document payment method types`
- **补充支付方式测试**：`test: cover payment method types`
- **修复新增文件告警**：`fix: resolve lint warnings in payment files`

**Submodule 示例：**

- `chore(deps): update lib-auth to v2.3.0`
- `chore(deps): upgrade shared-utils (a1b2c3f..d4e5f6a)`
- `chore: update submodules for release 1.5`
- `fix(deps): pin lib-config to stable commit (revert broken HEAD)`
