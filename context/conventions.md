<!-- xman-conventions: 3 -->
# 产物与表达约定

所有 AI skill 产生的项目文档统一存储在 `.ai-configs/` 下。此文件是**产物路径**、**表达与命名**和**工程约束**的唯一事实源。

x-mansion 支持两套并存的产物组织形态：

- **Task 模式**（推荐用于中等及以上需求）：产物聚合在 `tasks/<task-id>/` 目录内
- **Ad-hoc 模式**（简单需求或无 task 时的 fallback）：产物按类型分目录按月归档

两套结构按工作规模并存，skill body **不得**内联门控判断（禁止写 `if 存在 X then Y`），而是通过引用本文件的决策树让产物落到正确位置。

两套形态共享同一个 **join key**（见下节），因此无论产物落在哪里，同一需求的全部产物都能被一次检索捞出。

## Join key：task-id

`task-id` 是贯穿两套形态的唯一关联键，格式恒为 `YYYY-MM-{slug}`：

- `YYYY-MM` 取需求**发起**当月（不是产物生成当月，跨月需求不改 id）
- `slug` 强制字符集 `[a-z0-9-]`，取自需求主题的英文/拼音短名（中文标题另存，见各模式说明）

**两种模式下的含义**：

| 模式 | task-id 的体现 |
|---|---|
| Task 模式 | 目录名即 task-id，产物文件名不再重复带前缀 |
| Ad-hoc 模式 | 仅作**文件名前缀**，不创建 `tasks/` 目录 |

**slug 复用规则（关键）**：一条需求链上的所有产物必须共用同一个 slug。skill 生成产物前，先按本文件的路径约定检索是否已有同主题产物：

- 检索到 → 沿用其 task-id，不得另起新 slug
- 未检索到 → 由当前 skill 生成 slug，后续 skill 一律继承

这条规则是整套约定成立的前提。slug 漂移（同一需求出现 `login-refactor` 和 `login-rework` 两个前缀）会直接让检索失效。

**检索方式**：

```bash
xman task find <关键词>          # 同时搜 task 目录、meta.yml、ad-hoc 产物
rg -l '2026-08-login-refactor' .ai-configs   # 已知 task-id 时直接捞全链产物
```

**存量文件**：本约定生效前的旧命名产物不强制迁移，按需手工重命名即可。

## 产物路径决策树

Skill 决定产物路径时，按以下优先级解析「当前 task」：

1. CLI 显式传入 `--task <id>`
2. 环境变量 `XMAN_TASK=<id>`
3. 文件 `.ai-configs/.current-task`（单 terminal 默认值）
4. 以上都没有 → 视为无 task

**跨项目隔离（强制校验）**：任一优先级解析出的 task-id，必须在**当前项目**的 `.ai-configs/tasks/` 下真实存在，否则一律视为无 task。

这道校验不能省。`XMAN_TASK` 是终端级环境变量，在项目 A 里 export 之后 cd 到项目 B 依然生效；`.current-task` 也可能指向已废弃（mv 到 `.abandoned/`）或已删除的 task。跳过校验，B 项目的产物就会落进一个以 A 项目 task-id 命名的幽灵目录，两个项目的上下文就此串号。

`xman task current` 已内置该校验：解析不到有效 task 时回显空串并向 stderr 提示原因。

**路径决定规则**：

已有有效 Task 或唯一同主题产物时沿用其身份。没有现成关联时，短修复和单份文档默认 Ad-hoc；确需跨阶段、跨会话聚合与状态跟踪时，可在已授权范围内创建 Task。选择本地组织方式不增加一次确认；只有多个真实不同需求的关联无法查证且会混合内容时才澄清。同一需求选定后保持 task-id 不变，不能在两种模式间自动迁移或覆盖旧产物。

| 是否有当前 task | 产物落点 |
|---|---|
| 有（任一优先级解析到有效 task-id） | `.ai-configs/tasks/<task-id>/<artifact>.md` |
| 无 | `.ai-configs/<type>/YYYY/MM/{task-id}-{需求名称}-<suffix>.md`（ad-hoc fallback，见下方 ad-hoc 路径表） |

Skill body 统一用描述性引用表达，例如：
> "按 `.ai-configs/conventions.md` 的产物路径约定保存 PRD 文档"

禁止出现 `if exist`、路径字面量 `.ai-configs/...`、或任何条件判断式。

## Task 模式

### task-id 规则

- 格式与 slug 规则见上方「Join key：task-id」
- 中文标题放 `meta.yml.title`
- 目录名即 id，无独立注册表

### 目录结构

```
.ai-configs/tasks/
├── 2026-04-login-refactor/
│   ├── meta.yml
│   ├── analysis.md     # 按需生成
│   ├── prd.md
│   ├── design.md
│   ├── plan.md
│   ├── progress.md
│   └── review.md
└── .abandoned/          # 废弃 task 整目录 mv 至此
```

### meta.yml schema（最小集）

```yaml
title: 中文标题
stage: in_progress    # in_progress | done | abandoned
tags: [tag1, tag2]
links:
  pr: null
  issue: null
```

未列出的字段（id / created_at / updated_at / artifacts / owner）一律不存——均可从目录名和 git 推导。

### 产物文件名映射

Skill 在 task 模式下写入 `tasks/<id>/<artifact>.md`，`<artifact>` 对应如下：

| 产物类型 | 文件名 |
|---|---|
| 脑暴记录 | `brainstorm.md` |
| 需求分析 | `analysis.md` |
| 研究报告 | `research.md` |
| PRD 文档 | `prd.md` |
| 设计方案 | `design.md` |
| 编码计划 | `plan.md` |
| 执行进度 | `progress.md` |
| 代码审查 | `review.md` |
| 验证报告 | `harness.md` |
| 完成声明验证 | `verification.md` |
| 经验教训 | `lessons.md` |
| 通用说明与人工向导 | `doc.md` |
| 可点击原型 | `prototype.html` |

## Ad-hoc 模式（无 task 时的 fallback）

无当前 task 时，产物按类型分目录按月归档，文件名统一以 `{task-id}-{需求名称}` 为前缀。

`{需求名称}` 是人类可读短名（中文标题，词间用 `-` 连接），与 task-id 的 slug 并存：task-id 保证机器检索稳定，需求名称保证人肉浏览目录时一眼可辨主题。不允许省略需求名称只留 slug——纯 slug 文件名在目录列表里无法快速辨认。

### 需求链产物（带 join key）

这类产物归属于某条具体需求，文件名**必须**带 `{task-id}-{需求名称}` 前缀：

| 产物类型 | 路径 pattern | 示例 |
|---|---|---|
| 脑暴记录 | `.ai-configs/brainstorm/YYYY/MM/{task-id}-{需求名称}-脑暴.md` | `2026/08/2026-08-login-refactor-登录重构-脑暴.md` |
| 需求分析 | `.ai-configs/analysis/YYYY/MM/{task-id}-{需求名称}-需求分析.md` | `2026/08/2026-08-login-refactor-登录重构-需求分析.md` |
| 研究报告 | `.ai-configs/research/YYYY/MM/{task-id}-{需求名称}-研究报告.md` | `2026/08/2026-08-hermes-agent-Hermes调研-研究报告.md` |
| PRD 文档 | `.ai-configs/prd/YYYY/MM/{task-id}-{需求名称}.md` | `2026/08/2026-08-login-refactor-登录重构.md` |
| 设计方案 | `.ai-configs/design/YYYY/MM/{task-id}-{需求名称}-设计方案.md` | `2026/08/2026-08-login-refactor-登录重构-设计方案.md` |
| 编码计划 | `.ai-configs/plan/YYYY/MM/{task-id}-{需求名称}-编码计划.md` | `2026/08/2026-08-login-refactor-登录重构-编码计划.md` |
| 执行进度 | `.ai-configs/progress/YYYY/MM/{task-id}-{需求名称}-执行进度.md` | `2026/08/2026-08-login-refactor-登录重构-执行进度.md` |
| 代码审查 | `.ai-configs/review/YYYY/MM/{task-id}-{需求名称}-代码审查.md` | `2026/08/2026-08-login-refactor-登录重构-代码审查.md` |
| 验证报告 | `.ai-configs/harness/YYYY/MM/{task-id}-{需求名称}-验证报告.md` | `2026/08/2026-08-login-refactor-登录重构-验证报告.md` |
| 完成声明验证 | `.ai-configs/verification/YYYY/MM/{task-id}-{需求名称}-完成验证.md` | `2026/08/2026-08-login-refactor-登录重构-完成验证.md` |
| 经验教训 | `.ai-configs/lessons/YYYY/MM/{task-id}-{需求名称}-复盘.md` | `2026/08/2026-08-login-refactor-登录重构-复盘.md` |
| 通用说明与人工向导 | `.ai-configs/docs/YYYY/MM/{task-id}-{需求名称}-文档.md` | `2026/09/2026-09-service-setup-服务接入-文档.md` |
| 可点击原型 | `.ai-configs/prototype/YYYY/MM/{task-id}-{需求名称}-原型.html` | `2026/09/2026-09-onboarding-入职-原型.html` |

目录里的 `YYYY/MM` 仍按**产物生成月份**归档；`{task-id}` 里的 `YYYY-MM` 是**需求发起月份**。跨月需求两者会不一致，这是预期行为——归档看目录，关联看前缀。

### 全局产物（不带 join key）

这类产物不属于单条需求，保持原命名：

| 产物类型 | 路径 pattern | 示例 |
|---|---|---|
| 项目上下文 | `.ai-configs/project-context.md` | — |
| 决策日志 | `.ai-configs/decisions/YYYY-MM-DD-{slug}.yaml` | `2026-08-11-login-refactor.yaml` |
| 技术备忘 | `.ai-configs/memos/{name}.md` | `auth-library-comparison.md` |
| 错误进化事件 | `.ai-configs/evolution/YYYY/MM/YYYYMMDD-HHMMSS-{slug}.md` | `20260811-153012-误判路径.md` |
| 错误进化模式 | `.ai-configs/evolution/patterns/{slug}.md` | `avoid-hardcoded-platform-paths.md` |

Ad-hoc 模式是一等公民，不会被废弃。简单需求、临时修复、无需跨产物聚合的任务应直接走这条路径——加了 join key 之后，它同样具备全链检索能力。

### 主产物与伴随文件

`metadata.outputs.type` 对应 `context/naming-contract.json` 已登记的类型；这份 JSON 与本文件共同校验，不能只在 skill 里发明一个类型。需求链类型须同时有 Task 和 Ad-hoc 落点；`decisions` 等项目级记录使用 `global` 落点。

用户已指定目标文件或项目已有明确文档位置时沿用该位置。使用默认落点时，人工向导先按 `doc` 确定说明文件，脚本放在同目录，沿用主名并改为 `.sh`。架构扫描的 HTML 沿用 `analysis` 的目录与主名；同类型的其他格式只改变扩展名，不新造需求身份。原型条款、覆盖账本等伴随文件放在主原型的同目录，名称由该流程已有契约决定。

短任务只在需要交付文件时落档；阶段校验可复用当前产物和新鲜命令结果，不为一次检查额外创建报告。现役文件名保持稳定，替换旧版本前按已有回退规则归档，不能让下游继续读取已被推翻的版本。

## 人读产物的 HTML

md 是唯一事实源，下游 skill 和 agent 只读 md。给人看的产物在 md 旁边另生成一份同名 `.html`，方便直接用浏览器打开；HTML 离线可用，不引用任何外部资源，跟着 `.ai-configs/` 一起提交。可点击原型本身就是 HTML，不在此列。

| 写完 md 后生成 HTML | 只留 md |
|---|---|
| 脑暴记录、需求分析、研究报告、PRD 文档、设计方案、代码审查、验证报告、完成声明验证、经验教训、通用说明与人工向导 | 编码计划、执行进度，以及全局产物（项目上下文、决策日志、技术备忘、journal 等） |

- 左列类型的 md 每次落档或更新后，运行 `node <当前 skill 目录>/../html-view/scripts/render.mjs <md 路径>`（html-view 和当前 skill 装在同一个 skills 目录下，直接拼这个路径，不在磁盘上搜索），在同目录生成同名 `.html`；一次落多份时把路径一起传。
- HTML 由脚本整份重写，修改只改 md 再重新生成。
- 本机没有 Node.js 或脚本运行失败时，md 照常交付，在回复里用一句话说明没生成 HTML 和原因。
- 只在对话里输出、不落文件的结果不生成 HTML。用户要求把其他 md 也生成 HTML 时，调用 `html-view`。

## Workspace 跨会话记忆

`.ai-configs/workspace/journal.md` 是跨会话的项目记忆层，**单文件、正序追加**（新内容在底部、append-only、git diff 干净）。

### 写入格式

每条一行，用约定前缀区分类型：

```
[YYYY-MM-DD] task=<id|null> 做了什么/下一步
[YYYY-MM-DD] DECISION task=<id> 选型/权衡/理由
[YYYY-MM-DD] LESSON task=<id> 教训/坑/反模式
[YYYY-MM-DD] REMINDER 未来需要回头看的事项
```

### 写入时机

- xman-flow agent 切换阶段时自动追加一行
- 用户手动 `xman journal add "msg"`
- SessionStart/SessionEnd hook（可选）

### 归档

`journal.md` 超过 2000 行时手动 `mv` 到 `workspace/journal/YYYY-Q{N}.md`。不自动化。

## Spec 查询

项目可在 `.ai-configs/specs/index.json` 登记「现有规范约束哪些项目路径」。需要确认某些路径适用哪些规范时，调用 Skill 工具，参数为 `spec-query`；各阶段什么时候查、查不到怎么记录，写在 `spec-query` 的 `SKILL.md` 里。

## Feature Map

`.ai-configs/features/` 记的是**这个应用有哪些功能、从用户视角怎么到达、怎么用工具驱动它**。
它不是任务产物，不按月归档，跟 `project-context.md` 一样是项目级常驻文件。

- `README.md` 是索引，每条功能一个 `<slug>.md`
- 每条固定五段：是什么 / 子功能 / 从用户视角怎么到达 / 怎么用工具驱动它 / 坑
- 用 `xman features init | new | list | check` 维护；`check` 只查结构，查不出内容对不对

**为什么要有它**：agent 每次验证界面改动都要把应用重新摸一遍，摸一遍烧掉一大块上下文，
而且每次摸的结果还不一样。写下来就是一份大家共用的地图，查表代替探索。

**它会过期**。改了功能顺手改这里；发现地图和实际对不上，以实际为准并当场改地图，
不要绕过它继续摸。

## Skill body 引用规范

Skill 中提到产物路径时：

✅ **正确**：
- "按 `.ai-configs/conventions.md` 的产物路径约定保存"
- "输出到约定的 analysis 产物路径"
- "写入 PRD 产物（遵循 conventions.md）"

❌ **错误**：
- "保存到 `.ai-configs/prd/YYYY/MM/...`"（硬编码路径）
- "如果存在 current-task 则写入 tasks/... 否则写入 ..."（内联门控）
- "检查 .ai-configs/.current-task 文件"（实现细节泄露）

## 阶段职责与证据复用

每次调用先回答四件事：本阶段还有什么问题没解决、已有哪些决定和产物、哪些证据可以直接用、本阶段要交出什么。已有材料已经解决了这个问题，核对适用范围后直接用，不为了凑齐阶段名称重新调查或重写文档。

| skill | 解决什么问题 | 交出什么 |
|---|---|---|
| req-analyze | 用户问题、目标、范围或关键前提不清 | 诊断结论、依据与真实未决事项 |
| bug-fix | 已报告异常的机制与修复尚未确认 | 症状反馈、根因、最小完整修复与回归 |
| prd | 产品规则、状态或验收尚未明确 | 可观察行为、失败恢复及验收依据 |
| design / architect | 用户交互或技术契约需要设计 | 各自负责的设计内容，由整合者维护主产物 |
| create-plan | 必要修改链路、依赖或验证安排不清 | 按完整行为组织的实施任务 |
| code-by-plan | 已确定行为尚未实现 | 实现、必要配套与本次验证 |
| review | 实现中是否有缺陷或违背规格 | 独立核对后的问题、证据与影响 |
| harness | 目标、回归和范围是否满足交付要求；或某个完成声明能否被证据支持 | 对当前对象的可交付判断；只核对声明时交出声明与证据的对应及未覆盖范围 |

可复用的证据要能定位到：执行的命令或操作、对象版本和文件范围（Git 项目区分基准提交和工作区改动，含未跟踪文件）、关键输入和环境、实际结果。只有一句「通过」的转述不算证据。

- 对象、输入和环境都没变，并且覆盖当前问题，才复用；代码或关键条件变了，补跑受影响的检查。
- 结果不稳定的检查，写清条件、运行次数和实际结果；只跑过一次就写「跑过一次通过」。
- 复用证据不代替独立判断：接手的人自己核对规格符合、遗漏和风险。报告里分清本次运行的、复用的和没跑的。

## 授权、实现判断与验证

用户的目标、已授权范围和已确认的决定持续有效。要求实施时，必要的调查、保存计划、范围内修改和相关验证都在授权内；要求只分析、只审查或停在计划时，就停在那里。进入阶段、保存本地产物、阶段衔接都直接做。

- **事实先查。** 已确认的决定直接用；新证据和它冲突时，只问受影响的那个决定，其他工作继续。
- **局部细节自己定。** 不改变业务行为、公共契约、数据含义、权限或范围的可逆细节，依据代码和最小相关验证自己决定，简短记下理由。没有先例也照样可以定。
- **边界问题才问。** 目标或业务行为有多种合理理解、要改公共契约、数据、安全或交付范围，或用户说过要自己定的，按〈表达与命名〉的提问规则问。没人回答等于还没定。
- **范围外的念头记下来。** 顺手重构、顺手修别的 bug、加计划外的功能、改看不顺眼的命名，都记进「本次不做」，写清位置和现象，本次不改。完成当前目标必需的调用方、配套和回归保护属于范围内。
- **副作用按实际授权。** 生成问卷、向导或报告，不包含发送、运行真实系统操作、提交、发布或删除；这些动作要有明确授权才做。
- **结论落到证据。** 用测试、复现、差异检查和适用的构建或运行验证支撑结论，按风险选最小充分的验证；失败先定位原因，断言保持原有严格程度。默认继承会话模型。

完成声明只覆盖本次证据证明了的部分，没能执行的验证逐项列出。

## 表达与命名

对所有 skill 和 agent 生效，产物文档和对话回复都适用。skill 只写自己特有的要求，本节内容用这个标题引用，不复制。新建或修改 skill 时，写法按 `writing-for-agents` skill。

### 用实际名称，不用代号

标题、条目和引用写真实含义：文件名、符号名、行为、页面、问题或任务的名字。判据是读者要不要翻回去查对照表才知道说的是什么，要查就是代号，比如 `A1`、`FR01`、`P0`、`方案 A`、`Phase 1`、`步骤 1.1`，改成实际名称。只有作者懂的比喻（「先打一刀」「三层跑一遍」）同理，直接说改了什么。

编号只表示先后顺序，引用另一条时写它的名字。内部 stage 码、复杂度代码只用于 hook、状态文件和路由判断，展示给用户时换成完整含义。

### 向用户提问

- 能自己查到的事实（代码、文档、数据、已有结论）先查完再问。调查还在进行时，只有依赖它的问题等结果，其他工作照常推进。
- 只在答案会改变方向或结论时才问。
- 同一个决定需要的几个事实一次问完；彼此依赖的决定一个一个问，后一个的选项取决于前一个的答案。
- 提问时给出：已查到的事实、还缺什么、几种选择各自的影响、你的建议。环境有 `AskUserQuestion` 之类的结构化提问工具就用它；选项写完整含义，让用户直接选，不用回字母或数字。
- 需要和用户多轮追问才能定下来的事，按 skill 安装目录里的 `req-analyze/references/grilling.md` 的追问方法进行。

### 输出

- 第一行写读者能直接做的事：命令、文件路径或改动点；没有要做的事，第一行写结论。
- 先写结论，再写支撑它的依据；已有文档用路径或标题引用。
- 只留会改变判断、验证或后续维护的信息，空的分组整段删掉。
- 不确定时写清缺哪条证据。
- 多步工作写编号列表，每步是一个有边界的动作，用能跑通的最少步数；有任务或计划工具时由它承担状态。跨轮工作只同步有变化的进度、阻塞和下一步。
- 报错用陈述语气写现象、原因和修法。
- 结尾：还有未完成的事，指出一件读者能具体做的事；没有就直接结束。

发送前检查：只看第一行和最后一行，读者能不能知道刚才发生了什么、接下来做什么。答不出来就重写这两行。
