# 规则文件和记忆的平台路径

平台机制会变。涉及写入或体量上限时，以当前平台的官方文档或诊断命令（如 Claude Code 的 `/memory`）为准，这张表只用来知道去哪找。

## 先分三类

发现的每个知识文件归入一类，三类的写入规则不同：

1. **人工维护的规则**：`CLAUDE.md`、`AGENTS.md`、`.cursor/rules/`、`GEMINI.md` 等。可以按授权修改。
2. **agent 自动记忆**：宿主为 agent 维护、允许按平台规则整理的记忆，比如 Claude Code 的自动记忆目录。用户要求或项目规则授权时才改。
3. **机器生成的历史或索引**：由宿主管线生成的摘要、索引。只读；要更正时走宿主提供的入口。

归不了类的按第三类处理。`MEMORY.md` 只是文件名，不同平台含义不同，体量上限要和平台绑定。

## Claude Code

| 用途 | 路径 |
|---|---|
| 用户规则 | `~/.claude/CLAUDE.md` |
| 项目规则 | `./CLAUDE.md`、`./.claude/CLAUDE.md`、`CLAUDE.local.md` |
| 按路径生效的规则 | `.claude/rules/**/*.md` |
| 自动记忆 | `~/.claude/projects/<project>/memory/`，索引是其中的 `MEMORY.md` |

`CLAUDE.md` 全量加载，建议控制在约 200 行以内，越长遵守度越低。自动记忆的 `MEMORY.md` 启动时只加载前 200 行或 25KB，主题文件按需读取。已有 `AGENTS.md` 的项目可以用导入或软链与 `CLAUDE.md` 同源，方向按项目规则。

## Codex

| 用途 | 路径 |
|---|---|
| 全局规则 | `$CODEX_HOME/AGENTS.override.md`，没有时读 `AGENTS.md`（默认 `~/.codex`） |
| 项目规则 | 从项目根到当前目录逐级找 `AGENTS.override.md`、`AGENTS.md` 和配置的备用文件名 |

项目规则链合并后默认上限 32KiB（`project_doc_max_bytes`），越靠近当前目录的越晚加载。`~/.codex/memories/` 一类文件通常由宿主生成，属于第三类。

## Cursor 和 Gemini CLI

Cursor 读 `.cursor/rules/` 和项目根的 `AGENTS.md`；Gemini CLI 读 `GEMINI.md`。实际加载哪份，以平台文档和设置里的项目指令为准。

## 同一 skill 装了多份

列出各平台目录里同名 skill 的实际路径，确认是软链到同一份、各自复制，还是被更高优先级的版本覆盖。只改真正的那一份；复制安装要有明确的同步方式。验证时看平台实际加载了什么，而不只是文件存在。
