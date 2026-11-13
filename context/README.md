# Context 子系统

项目上下文管理子系统，负责项目元信息的初始化、存储约定和校验。

## 职责

- 定义项目上下文的 schema（`schema/project-context.md`）
- 提供初始化模板（`templates/project-context-template.md`）
- 用户授权维护工程规范时，可参考 `templates/project-engineering-spec-template.md`；项目按已有文档结构采用，不自动生成分类规范。
- 集中管理产物存储路径约定，以及全仓共享的表达与命名约定（`conventions.md`）

## 与 Skill 的关系

- Skill 通过 front-matter 中的 `requires_context: [project]` 声明对项目上下文的依赖
- 产出需求链产物的 skill 通过 `requires_task` 声明 task 绑定方式（见 `docs/SKILL-SPEC.md`）
- Skill 不应在 body 中包含 context 检查逻辑，也不应硬编码产物路径

## conventions.md 如何抵达业务项目

母仓的 `context/conventions.md` 是**唯一事实源**，但业务项目里没有 `context/` 目录——`xman install` 只软链 skill，不搬运 context。因此 skill body 引用的是**项目内**路径 `.ai-configs/conventions.md`，由 `xman context init` 建立：

| 模式 | 形态 | 适用场景 |
|---|---|---|
| 默认 | 项目内真实文件 | 可提交，适用于本机、同事和 CI |
| `--link` | 软链 → 母仓 `context/conventions.md` | 仅母仓维护者本机调试，不可提交 |

真实文件不会自动跟随母仓更新，需重跑 `xman context init` 刷新。

**这条链路断了会静默出错**：skill 读不到约定 → 产物照样落盘，但 task-id 前缀和 slug 复用规则失效 → 同一需求的产物永远关联不上。`xman context check` 会把它当硬失败（exit 1）拦下。

表达与命名约定走同一条链路，但降级方式不同：每个 skill 的 SKILL.md 里都留了一行核心禁令（用实际名称、不用代号），链路断了只损失细则和例外，不会整段消失。

## 自动探测与确认

`xman context init` 会扫描项目并预填 `project-context.md` 中能确定性判定的字段，填入值标 `⟨待确认⟩`，人工核对后 `xman context confirm` 清除标记。`--auto` 跳过确认环节（CI / 脚本场景）。

探测分工由 `scripts/detect-project.py`（读特征）和 `scripts/apply-context-fields.py`（写回）承担：

| 层次 | 字段 | 由谁完成 |
|---|---|---|
| Tier 1 | 语言、前后端框架、组件库、状态管理、数据库、构建工具、包管理器、代码风格、分支策略、提交规范、部署方式、测试栈、项目结构 | 脚本探测 |
| Tier 2 | 产品类型、核心业务、设计系统、主色调、字体 | 需读代码，留 `[待填写]` 交给 agent |
| Tier 3 | 目标用户、Review 流程 | 只能问人 |

**字段不是普适的**，所以引入 `[不适用]` 标记：形态为 backend/cli/library 时前端框架、主色调、响应式断点等自动标为不适用，frontend 则是后端框架、数据库。不再需要为了过门控填「N/A」。

**多工程同仓**：识别 `workspaces` / `pnpm-workspace.yaml` / `lerna.json` / `nx.json` / `turbo.json`，或直接扫出多个带构建清单的子目录，则形态判定为 `monorepo`——此时技术栈字段取各子工程的**并集**，另在「子工程」一节逐个列出路径、形态和各自的栈。monorepo 不做 `[不适用]` 标记（前后端都可能存在）。

## 命令

- `xman context init [DIR] [--auto|-y] [--link] [--legacy]` — 初始化 + 自动探测
- `xman context confirm [DIR]` — 确认探测结果，清除 `⟨待确认⟩` 标记
- `xman context status [DIR]` — 查看状态（conventions.md 形态 + 待填写/待确认/不适用计数）
- `xman context check [DIR]` — 校验完整性（conventions.md 不可达 exit 1；有待填写或未确认 exit 2）
