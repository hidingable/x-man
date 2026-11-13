# Skill 编写规范

## 目录结构

```text
skills/<skill-name>/
├── SKILL.md              # 核心定义文件（必须）
├── assets/               # 模板和静态资源（可选）
│   └── templates/
│       └── *.md
└── references/           # 参考文档和详细指南（可选，注意复数）
    └── *.md
```

Agent 定义使用扁平文件，伴随资料放同名目录：

```text
agents/
├── <agent-name>.md
└── <agent-name>/
    ├── references/
    └── hooks/
```

`agents/<name>/AGENT.md` 不属于有效定义位置，plugin 宿主不会发现它。

## Front-matter Schema

兼容 [Agent Skills 官方规范](https://agentskills.io/specification)，自定义字段放在 `metadata` 下。

```yaml
---
# 必填（官方规范）
name: skill-name
description: "一句话定位与使用场景，必要时补充有区分度的触发语"

# 可选（官方规范）
license: "MIT"
compatibility: "Requires Python 3.10+"
# model: "<宿主支持的模型 ID>"  # 仅在显式指定时设置；默认继承当前会话

# 自定义扩展（放在 metadata 下）
metadata:
  category: engineering     # engineering | design | product | general
  tags: [coding, plan]      # 3-5 个标签，用于搜索发现
  dependencies: []          # 前置 skill 列表，如 [init-context]
  requires_context: [project]  # 声明需要的项目上下文（替代 dependencies: [init-context]）
  requires_task: prompt        # 声明 task 绑定方式：prompt（链条起点）| inherit（链条下游）
  outputs:                     # 声明产物信息
    type: analysis             # 产物类型，对应 context/conventions.md
  hooks:                       # Hook 声明（可选）
    pre: []                    # 前置 hook 列表（进入此 skill 对应阶段前执行）
    post: []                   # 后置 hook 列表（此 skill 对应阶段完成后执行）
  memory_artifacts: []         # 声明产出的可记忆化文件（供收尾类 skill 消费）
  harness:                     # 验证配置（可选）
    requires_tdd: false        # 是否强制 TDD
    validation_level: auto     # auto | full | minimal | skip
  version: "1.0.0"          # 仅外部引入时标记上游版本
  source: "https://..."     # 外部 skill 的原始仓库地址
---
```

### 字段说明

| 字段 | 位置 | 必要性 | 说明 |
|------|------|--------|------|
| `name` | 顶层 | 必填 | 与目录名一致，仅小写字母+连字符，最长 64 字符 |
| `description` | 顶层 | 必填 | 最长 1024 字符，说明用途和适用场景；触发语按下方调用规则选用 |
| `license` | 顶层 | 可选 | 许可证名称或引用 |
| `compatibility` | 顶层 | 可选 | 环境要求（如需要的工具、网络等） |
| `model` | 顶层 | 可选 | 显式指定该 skill 的执行模型；不写则继承当前会话。见「模型继承与职责边界」 |
| `metadata.category` | metadata | 推荐 | 对应 `plugins/` 下的主分类 |
| `metadata.tags` | metadata | 推荐 | 自由标签，用于 `find-skills` 搜索 |
| `metadata.dependencies` | metadata | 推荐 | 前置 skill，研发流程类通常依赖 `init-context` |
| `metadata.requires_context` | metadata | 可选 | 声明需要的项目上下文，`[project]` 表示需要完整的 project-context.md |
| `metadata.requires_task` | metadata | 可选 | 声明 task 绑定方式，`prompt`（链条起点，解析或建立任务身份）/ `inherit`（链条下游，静默继承） |
| `metadata.outputs` | metadata | 可选 | 产物信息，`type` 对应 `context/conventions.md` 中的产物类型 |
| `metadata.hooks` | metadata | 可选 | Hook 声明，`pre`/`post` 分别为前置/后置 hook 列表 |
| `metadata.memory_artifacts` | metadata | 可选 | 声明产出的可被收尾类 skill 消费的文件类型 |
| `metadata.harness` | metadata | 可选 | 验证配置，`requires_tdd` 控制 TDD，`validation_level` 控制验证强度 |
| `metadata.version` | metadata | 可选 | 外部引入时标记上游版本 |
| `metadata.source` | metadata | 可选 | 外部 skill 的原始仓库地址 |

### 模型继承与职责边界

默认继承当前会话模型，只有用户或明确运行配置指定模型时才覆盖；现有 skill 的显式模型偏好按其配置处理。职责分工用于控制范围和风险，不按模型强弱禁止执行者判断。

| 职责 | 示例 | 默认模型 | 该承担什么 |
|---|---|---|---|
| 诊断与规划 | `req-analyze` `prd` `design` `create-plan` | 继承会话 | 核实事实、明确目标和边界、写清产品与契约决定 |
| 实施与验证 | `code-by-plan` `bug-fix` | 继承会话 | 核对当前事实，完成最小完整实现及必要验证 |
| 版本管理 | `git-commit` | 继承会话 | 分析实际差异，按已有授权处理提交 |

授权、实施判断和验证的统一规则位于 `context/conventions.md`〈授权、实现判断与验证〉；运行侧引用 `.ai-configs/conventions.md` 的同名小节，skill 不重复定义相互冲突的审批门槛。

产出计划、PRD、设计的 skill 应检查交接缺口：影响产品行为、公共契约和数据含义的决定写清依据，仍未决时按统一规则处理。局部实现细节写清约束和通过标准，执行者查证后可以自主完成，无需把每行代码预先定死。

实施 skill 保留事实核对、脏工作区保护、最小完整修复和实际验证；测试预期来自需求、契约、复现或其他独立事实源。判据是交接产物及其引用足以确定目标、边界、必要链路和通过标准，不要求执行者绕开上游事实源。

## 工程规范与交接

领域、技术设计、utils 和组件的通用检查问题以 `skills/create-plan/references/engineering-checks.md` 为准，其他 skill 按路径引用。Skill 提供核对方法，项目 Spec 承载已采用的具体规则；不把通用示例或分析建议自动升级成项目规范。

分析区分用户决定、事实、判断与假设；PRD 和 design 的关键行为注明来源和决定状态。草案格式完整不代表其中建议已经获认可，已有明确决定不重复审批。plan 保留必要的文件、契约、依赖、失败处理与验证细节，区分已确认决定、规范约束与执行者可自主处理的局部细节；未决项只阻塞依赖任务。

单阶段请求止于本阶段授权范围。编排交接复用已确定内容与有效证据，不因为存在文档就把未决项当作已确认；阶段 skill 合法的对话输出可由编排器记录到已有 journal/progress 的可定位条目，不强制造独立报告。记录完整性与业务正确性分别验证。

### 标签体系

- **用途**：`coding` `planning` `design` `review` `deploy` `ops` `docs` `testing` `workflow` `validation` `memory` `retrospective`
- **阶段**：`ideation` `analysis` `implementation` `qa` `maintenance` `harness` `reflection`
- **技术**：`react` `server` `cloudflare` `mcp` `apple` `docx` `tdd`

## Description 写法

description 说明能力与适用场景，让人和模型都能区分相近入口；触发语只保留能帮助选择的部分。

1. **一句话定位**：这个 skill 做什么
2. **使用场景**：什么时候该用它
3. **触发语**：用户可能的表达方式；不为数量堆关键词。明确仅供用户手动调用的入口可用简洁用途摘要。

```yaml
# 好的 description
description: "需求分析 skill。深度分析需求、探索代码库、评估可行性。当收到新需求或功能请求时使用。触发词：分析需求、需求分析、可行性评估、影响分析。"

# 不好的 description
description: "需求分析"  # 太简短，缺少使用场景和触发词
```

## 调用方式与授权

| 对象 | 本仓规则 |
|---|---|
| 阶段 skill，例如 req-analyze、prd、create-plan、review | 保持可发现，在用户已授权范围内组合使用；阶段衔接不重复征求许可，单阶段请求按原范围完成 |
| 流程 agent，例如 xman-flow | 按用户当前目标启动；明确实施任务可包含必要计划和验证，单纯咨询或单阶段请求不启动完整交付 |
| 用户明确要求仅手动调用的 skill | 使用宿主原生策略，并分别验证各安装通道；不能只改 description 就声称宿主已强制限制 |
| 生成问卷、向导或只读扫描报告 | 生成产物不等于授权发送、运行脚本、重构或发布；后续动作依用户实际指令 |

默认保留自动发现，不把“工作流重”一概映射成仅手动调用，也不禁止已授权编排器调用阶段 skill。
需要仅显式调用时，Claude 使用 `disable-model-invocation: true`，Codex 使用 `agents/openai.yaml` 的 `policy.allow_implicit_invocation: false`；这是 skill 策略，不能套在 agent 上。
当前 plugin 构建会规范化 Claude 字段，原生仅显式调用要连同构建映射验证后才能交付。本轮不新增一层重复的 invocation metadata，也不改变现有宿主字段。

## 研发类 Skill 前置检查

声明了 `requires_context: [project]` 的 skill，在执行前需要：

1. 读取 `.ai-configs/project-context.md` 和 `.ai-configs/conventions.md`，分别取得项目事实和产物约定。
2. 文件缺失、不可读或软链失效时，说明缺少哪一份并指向 `xman context init`；项目事实仍有待填写项时，明确列出影响当前工作的缺口。安装 skill 本身不会初始化项目上下文。
3. 已有 conventions 以项目版本为准，不为通过检查自动覆盖；`xman context init` 默认保留现有文件，刷新须由用户明确要求。
4. 两份文件可读且当前任务所需信息充分后，作为后续步骤的依据；可用 `xman context check` 核对完整性。

前置检查通过 `requires_context` 元数据声明。Skill body 中不应包含重复的检查逻辑。

注意：旧格式使用 `dependencies: [init-context]`，新格式使用 `requires_context: [project]`。两者均可工作，但新 skill 应使用 `requires_context`。

## 需求链 Skill 的 task 绑定

产出需求链产物（见 `context/conventions.md` 的 join key 定义）的 skill，通过 `requires_task` 声明如何取得 task-id。同样是**声明式**的——skill body 中不写检查逻辑。

### `requires_task: prompt`（链条起点）

适用于可能第一个被调用的 skill（`brainstorm` / `req-analyze` / `prd` / `hv-analysis`）。执行前：

1. 执行 `xman task current` 解析当前 task
2. 解析到 → 直接使用，不打扰用户
3. 未解析到 → 先用 `xman task find <需求关键词>` 检索当前项目是否已有同主题产物
   - 唯一同主题任务或上游产物及复用边界明确 → 沿用 task-id，简短说明，slug 不漂移
   - 归属或复用边界仍不明确且会改变结果 → 按统一规则确认，只暂停依赖项
   - 未命中 → 按已有用户偏好或运行模式建立本地 task，或使用 ad-hoc；本地组织方式可自主选择，不增加三选一门槛
     - 建新 task：`xman task new <slug> --title "..."` + `xman task use <id>`
     - 走 ad-hoc：不建目录，但仍需**确定 task-id 与需求名称作为文件名前缀**（`{task-id}-{需求名称}`）并在本次产物中沿用

**不得**强迫用户创建 task——ad-hoc 是一等公民。但无论走哪条，都必须产出一个 task-id。
Task 的创建、切换和产物组织遵循已有授权，不构成新的业务决定；`prompt` 字段保留兼容，不代表每次必须向用户提问。
任务身份和产物复用保持项目隔离，不从其他项目借用同名 task-id。

### `requires_task: inherit`（链条下游）

适用于总是接在他人后面的 skill（`design` / `create-plan` / `code-by-plan` / `harness` / `reflect`）。执行前：

1. 执行 `xman task current`；解析到则直接使用
2. 未解析到 → 从上游产物反推 task-id（读取所依赖的 plan / prd / analysis 文件名前缀或所在 task 目录名）
3. 两者都拿不到 → 退化为 `prompt` 行为

下游 skill **不得**自行生成新 slug。slug 漂移会让同一需求的产物失去关联。

## 多平台路径规范

x-mansion 支持 Claude / Codex / Cursor / Gemini。平台安装目录的单一事实源是 `context/platforms.md`。

通用 skill 文档必须使用平台中立表达：

1. 安装说明写 `./xman install <platform>`，不要写死某个平台目录。
2. 调用本 skill 的脚本时，写“从当前 skill 目录解析 `scripts/...`”。
3. 不在通用 `SKILL.md` / `AGENT.md` 中使用平台专属安装目录或旧命令目录。
4. 外部上游 README 可以保留原文路径，但本仓适配说明必须提供平台中立入口。

## 质量 Checklist

- [ ] SKILL.md 存在且 front-matter 有 `name` 和 `description`
- [ ] `description` 准确描述用途与适用场景，触发语和调用方式一致，不堆关键词
- [ ] `category` 已设置且与 `plugins/` 分类一致
- [ ] `tags` 已设置（3-5 个）
- [ ] 研发类 skill 声明 `requires_context: [project]`
- [ ] 产出需求链产物的 skill 声明 `requires_task`（`prompt` 或 `inherit`）
- [ ] 有至少一个输出模板或使用示例
- [ ] 规划产物写清影响结果的决定、依据、必要链路与通过标准；实施 skill 按统一规则处理局部细节和未决事项
- [ ] skill 引用统一授权规则，不因摘要、保存、定稿或阶段衔接增加重复确认，也不绕过用户保留的审批
- [ ] 子目录使用标准命名（`references/` 复数，`assets/`）
- [ ] 已在 `governance/skills-registry.csv` 中注册
- [ ] 已在 `plugins/` 和 `team/skills/`（如适用）中创建软链
- [ ] Agent 定义位于 `agents/<name>.md`，front-matter 是合法 YAML

## 参考范本

- **结构清晰**：`skills/brainstorm/` — 完整的前置检查、核心流程、输出模板
- **流程完整**：`skills/code-by-plan/` — 详细的步骤定义和输出契约
- **知识库型**：`skills/ui-ux-pro-max/` — 大量参考数据的组织方式
