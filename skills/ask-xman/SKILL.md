---
name: ask-xman
disable-model-invocation: true
description: "不知道该用哪个命令时问它：描述你的处境，它告诉你用哪个 skill、主流程怎么走。只推荐，不执行。"
metadata:
  category: workflow
  tags: [router, help, workflow]
  dependencies: []
  requires_context: []
---

# 该用哪个命令

听用户描述处境，回答该用哪个命令、为什么、下一步大概是什么。只推荐，不替用户执行。回答控制在三四句话：推荐的命令、理由、做完之后通常接什么。

## 主流程：从想法到上线

1. **方向还没想清楚** → `/brainstorm`
2. **需求要分析清楚**（谁卡住了、根因是什么、做到什么程度算完）→ `/req-analyze`；只想把一个想法或方案磨清楚、不要文档 → `/req-analyze` 并说「只追问」
3. **产品规则要写成文档** → `/prd`；前面已经讨论清楚，直接说「整理成 PRD」；需求变了 → 还是 `/prd`，说「更新 PRD」
4. **涉及界面和交互** → `/design`；接口、类型和模块边界要先定 → `/architect`
5. **写编码计划** → `/create-plan`；计划要改 → 还是 `/create-plan`，说「更新计划」
6. **按计划写代码** → `/code-by-plan`
7. **提交、写 PR / MR 描述** → `/git-commit`

不想一步步敲命令，想把整条链路交出去 → 用 `xman-flow` agent，它会按复杂度选出需要的阶段。

## 不用敲命令，直接说就行

这几个 skill 模型会在合适的时候自己调用：

- 报 bug、贴报错 → 修复（bug-fix）
- 「review 一下这次改动」「审查这个模块」→ 代码审查（review）
- 「上线前检查一下」→ 交付验收（harness）；说「做完了」之前核对证据 → 还是 harness
- 「用 TDD 做」→ 测试先行（tdd-guard）
- 业务名称说法打架 → 术语核对（domain-terms）
- 「帮我理解这个需求」「同事发来的这份 AI 计划看不懂」「画个图讲讲」→ 讲明白（explain）
- 查某个路径受哪些规范约束 → spec-query；画文字线框图 → ascii-card；写或改 skill → writing-for-agents

## 其他场景

- 需要人去登录后台、拿凭据、改外部配置的接入任务 → `/wizard`
- 有问题自己答不了，要发给懂的人填 → `/to-questionnaire`
- 换工具、换仓库、交给同事、分出旁支任务 → `/handoff`
- 没看懂刚才的回复 → `/human-speak`
- 想把某份 md 产物重新生成 HTML → `/html-view`
- 不想让 agent 执行 `git push`、`reset --hard` 这类命令 → `/guardrails`
- 新项目第一次用 → 运行 `xman context init`（命令，不是 skill）
- merge、rebase 或 cherry-pick 卡在冲突上 → `/resolving-merge-conflicts`
- 写 README、教程、接口文档 → `/technical-writing`
- 只读扫描架构，找重构机会 → `/improve-codebase-architecture`
- 部署到服务器 → `/server-deploy`；登录服务器排障 → `/server-ops-safe`

## 收尾（按需）

- 复盘这次哪里多付了代价 → `/reflect`；只想记下一次具体失误、下次别再犯 → 还是 `/reflect`，说「记一次失误」
- 改完之后同步项目文档、规则文件、.ai-configs 产物和记忆，清点会话残留 → `/neat-freak`
