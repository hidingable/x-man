---
name: guardrails
disable-model-invocation: true
description: "给 Claude Code 装上拦截危险 git 命令的 hook：push、reset --hard、clean -f、branch -D、checkout .、restore .。"
metadata:
  category: engineering
  tags: [safety, git, hooks, claude-code]
  dependencies: []
  requires_context: []
---

# 危险 git 命令拦截

规则写在文档里，模型可能照做也可能不照做；hook 由 Claude Code 在执行命令前强制检查，不依赖模型自觉。本 skill 装一个 PreToolUse hook，模型试图执行下面这些命令时直接拦下，并告诉它这类命令需要用户亲自执行：

- `git push`（含 `--force`）
- `git reset --hard`
- `git clean -f` / `git clean -fd`
- `git branch -D`
- `git checkout .` / `git restore .`

只对 Claude Code 生效。Codex、Cursor、Gemini CLI 没有同样的 hook 机制。

## 步骤

1. **问安装范围**：只装到当前项目（`.claude/settings.json`），还是装到全局（`~/.claude/settings.json`，所有项目都生效）。
2. **预览**：运行 `node <本 skill 目录>/scripts/install.mjs --scope <project|global> --dry-run`，把将要做的改动给用户看。
3. **安装**：用户确认后去掉 `--dry-run` 再运行一次。脚本把 hook 复制到对应的 `.claude/hooks/`，并在 `settings.json` 里合并一条配置；已有的其他设置保持不变，重复运行不会重复添加。`settings.json` 不是合法 JSON 时脚本会停下，先修好再装。
4. **验证**：运行 `echo '{"tool_input":{"command":"git push"}}' | node <hook 文件路径>`，退出码是 2 并输出「已拦截」就说明生效。新会话里 hook 才会加载。

卸载：同样的命令加 `--uninstall`。

项目级安装时，`.claude/settings.json` 和 `.claude/hooks/` 可以提交进仓库，同事拉下来就一起生效。
