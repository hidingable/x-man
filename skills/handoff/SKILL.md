---
name: handoff
disable-model-invocation: true
description: "把当前会话写成交接文档，让另一个会话、另一个工具或同事接着做。"
metadata:
  category: workflow
  tags: [handoff, session, context]
  dependencies: []
  requires_context: []
---

# 交接

把当前会话整理成一份交接文档，存到系统临时目录（不放进当前项目），并把路径告诉用户。

- 写清：目标、已经做完的、还没做的、已定的决定和理由、卡住的地方、下一步。
- 已经写进其他产物的内容（计划、PRD、提交、diff、issue）只给路径或链接，不复述。
- 加一节「建议使用的 skill」，写下一个会话该用哪些命令。
- 脱敏：密钥、密码、token、个人身份信息替换成 `<REDACTED>`。
- 用户说明了下一个会话要做什么时，按那个重点组织文档。

适合用在：换工具（比如从 Claude 换到 Codex）、换仓库或目录、交给同事、中途分出一个旁支任务。还在同一个工具、同一个目录里继续时，直接继续或压缩上下文更省事。
