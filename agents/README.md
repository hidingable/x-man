# Agent 子系统

Agent（编排器）定义目录。Agent 与 Skill 职责不同：

| 维度 | Skill | Agent |
|------|-------|-------|
| 定义文件 | `<name>/SKILL.md` | `<name>.md`（扁平，不是 `<name>/AGENT.md`） |
| 职责 | 纯知识模板——描述"如何完成某类工作" | 编排器/状态机——描述"如何组织多个 skill 协同推进一个目标" |
| 状态管理 | 无状态，不扫描项目产物 | 有状态，扫描 .ai-configs/ 判断项目阶段 |
| 示例 | brainstorm, req-analyze, prd | xman-flow（串联 brainstorm→req-analyze→prd→...） |

## 目录结构

```
agents/
├── README.md
├── <agent-name>.md       # Agent 定义（扁平文件）
└── <agent-name>/         # 同名伴随目录，可选
    ├── references/       # 参考文档
    └── evals/            # 评测用例
```

**定义文件必须扁平。** 埋成 `<agent-name>/AGENT.md` 时，plugin 的组件清单一条都收不到
（实测 `Agents (0)`），也就是说这个 agent 通过 plugin 分发时**根本不存在**，
而安装过程不报任何错。`xman validate` 会挡住这种写法。

Agent 的身份取自 front-matter 的 `name`，不取自文件名；正文里引用伴随文件时带上同名目录前缀，
例如 `xman-flow/references/stage-wakeup-template.md`。

伴随文档之间的引用相对于当前文档所在目录，例如同目录文件用 `./implementer-prompt.md`。
将这些路径交给子代理时，先解析为当前安装位置的绝对路径；不使用母仓的 `agents/` 路径代替安装路径。
项目自己的产物和其他 skill 的资源仍由各自上下文定位，不作为本 agent 的随包资源。

## Front-matter

```yaml
---
name: agent-name
type: agent
description: "..."
metadata:
  category: workflow
  tags: [orchestration, ...]
  requires_context: [project]
  orchestrates: [skill1, skill2, ...]    # 声明编排哪些 skill
---
```

## 命令

- `xman agent list` — 列出所有 agent
- `xman install <platform> --agent <name>` — 安装指定 agent 到平台
- `xman install <platform>` — 默认全量安装 skill 与 agent
