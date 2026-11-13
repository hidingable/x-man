# 路径绑定的项目 Spec

这个目录只维护“哪些现有规范约束哪些代码路径”的索引，不复制规范正文，也不接管 PRD、设计、计划或 Task 流程。

## 事实源

`index.json` 是路径绑定关系的唯一事实源。每条记录包含：

- `id`：稳定且唯一的规则标识
- `source`：仓库内已有规范文件
- `description`：为什么修改目标路径前需要读取该规范
- `paths`：相对项目根目录的 glob；MVP 只支持 `*`、`**`、`?`，字符类和花括号会被 validator 拒绝

正式规范正文继续维护在 `context/`、`docs/` 和 `governance/` 的原文件中。

## 命令

```bash
./xman spec init --project /path/to/project
./xman spec validate
./xman spec list
./xman spec match "skills/review/SKILL.md"
```

项目需要启用写前门禁时，显式安装对应平台 Hook：

```bash
./xman spec install-hooks claude --project /path/to/project --dry-run
./xman spec install-hooks claude --project /path/to/project
./xman spec install-hooks codex --project /path/to/project
```

`--project` 表示准确的项目根目录，该目录自身必须存在 `.ai-configs/specs/index.json`，不会向父目录回退。不传时才从当前目录向上发现，并且不会跨越最近的 Git 仓库边界。

`init` 会在目标项目创建空的 `.ai-configs/specs/index.json` 和本地说明，不生成或复制规范正文，也不覆盖现有索引。登记项目已有规范后再运行 `validate`。

安装命令会保留已有 JSON 配置，追加写前 `PreToolUse` 规则，并把 Hook 与匹配运行库复制到项目的平台 Hook 目录。副本不依赖母仓绝对路径，可以随项目迁移或提交给团队；遇到用户自有同名文件、其他软链或非法 JSON 时拒绝覆盖。旧版指向当前母仓脚本的软链会自动迁移为项目内副本。

安装时会报告本机检测到的平台 CLI 路径和版本。检测到可执行文件只证明具备宿主命令，不证明 Hook 已执行；最终仍以 Claude/Codex 的真实写操作为准。

Codex 写入配置后还不会自动启用：必须在 Codex 中运行 `/hooks`，审核并信任新增 Hook。未完成信任前，写前门禁不会执行。

运行 `xman` 和 Spec Hook 需要 Python 3.9 或更高版本，`xman doctor` 会在安装前校验。

## 运行行为

当写入路径第一次命中某条 Spec，Hook 会阻断本次写入并返回一条带当前 session 的读取确认命令；该命令输出规范正文并记录已读状态，同一会话重试时放行。规范正文变化后会重新阻断并要求读取新内容。

会话内已交付记录保存在 `.ai-configs/runtime/spec-cache/`，属于本地运行态，不进入 Git。

## MVP 边界

- 门禁只覆盖 Claude `Write|Edit|MultiEdit` 和 Codex `apply_patch|Edit|Write` 等结构化写工具。
- Bash、重定向、格式化器、代码生成器和任意脚本产生的文件修改不在当前门禁内。
- 缓存与 Agent 使用同一 OS 用户权限，本机制用于减少遗漏，不是不可绕过的安全或合规强制边界。
