# 平台路径约定

x-mansion 的 skill / agent 源文件只维护在本仓库：

- `skills/`
- `agents/`

各平台安装目录只是软链目标，不是内容事实源。安装路径由 `xman install <platform>` 和 `scripts/sync-*.sh` 决定。
`xman install` 始终安装用户选中的完整集合，不假设目标环境已经装有其他 plugin；
`release` 字段只在构建 x-mansion 实验场 plugin 时用于排除条目，不影响直接安装。

## 支持平台

| 平台 | 全局 skill 目录 | 项目 skill 目录 | 全局 agent 目录 | 项目 agent 目录 |
|---|---|---|---|---|
| Claude | `~/.claude/skills` | `<project>/.claude/skills` | `~/.claude/agents` | `<project>/.claude/agents` |
| Codex | `~/.codex/skills` | `<project>/.agents/skills` | `~/.codex/agents` | `<project>/.codex/agents` |
| Cursor | `~/.cursor/skills` | `<project>/.cursor/skills` | `~/.cursor/agents` | `<project>/.cursor/agents` |
| Gemini | `~/.gemini/skills` | `<project>/.gemini/skills` | `~/.gemini/agents` | `<project>/.gemini/agents` |

Codex 两层的 skill 落点不同，依据是 `codex debug prompt-input` 报出的扫描根：项目级只扫
`<project>/.agents/skills`（不扫 `<project>/.codex/skills`），全局级 `~/.codex/skills` 与
`~/.agents/skills` 都扫。所以项目级用 `.agents/skills`，全局级留在 `~/.codex/skills`，
不占用其他工具也可能使用的 `~/.agents/skills`。agent 两层都落 `.codex/agents/*.toml`。

Agent 源文件统一维护为 `agents/<name>.md`，安装时按宿主适配：Claude / Cursor / Gemini
继续使用 Markdown；Codex 由 `sync-codex-agent.py` 转成官方要求的 `<name>.toml`，伴随文件链接到
`.codex/agent-resources/<name>/`。

## 编写约定

Skill 和 agent 文档默认使用平台中立表达：

- 安装使用 `./xman install <platform>`。
- 单独使用 skill 内脚本时，从当前 skill 目录解析 `scripts/...`。
- 不在通用 `SKILL.md` / `AGENT.md` 中写死 `~/.claude/skills`、`.claude/commands`、`~/.claude-commands` 等平台专属路径。
- 平台专属路径只允许出现在本文件、`scripts/sync-*.sh`、平台审计脚本、归档文档或明确标记的平台专属说明中。

外部引入的上游 README 可以保留原始平台路径，但本仓适配层必须提供平台中立入口。

## Spec 写前 Hook

路径绑定 Spec 的匹配、读取确认和会话缓存由 `scripts/hooks/spec-pre-tool-use.py` 统一实现；平台配置只负责把写操作路由到该脚本：

- Claude：项目 `.claude/settings.json` 的 `PreToolUse`，匹配 `Write|Edit|MultiEdit`
- Codex：项目 `.codex/hooks.json` 的 `PreToolUse`，匹配 `apply_patch|Edit|Write`

使用 `xman spec install-hooks <claude|codex> --project <path>` 显式安装。安装会把受管 Hook 和匹配运行库复制到项目的平台 Hook 目录，不依赖母仓绝对路径，可以随项目迁移。用户自有同名文件不会被覆盖。

安装器会报告对应平台 CLI 是否存在，但配置和运行库写入成功不等于 Hook 已实际执行；平台兼容性仍以真实结构化写操作验证为准。

Codex 项目 Hook 写入配置后必须由用户在 `/hooks` 中审核并信任，否则 Codex 会跳过执行。配置写入成功不得表述为 Hook 已生效。

当前 Hook 只约束上方列出的结构化写工具，不处理 Bash、重定向、格式化器、代码生成器或任意脚本造成的文件修改。运行态缓存与 Agent 处于同一 OS 用户权限下，因此它是防遗漏护栏，不是安全或合规强制边界。
