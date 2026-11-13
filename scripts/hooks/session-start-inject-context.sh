#!/bin/bash
set -euo pipefail

# session-start-inject-context.sh — SessionStart hook
# 进入带 .ai-configs/ 的项目时自动输出：
#   1. project-context.md 全文
#   2. 当前 task 的 meta.yml（如有）
#   3. workspace/journal.md 末尾 2KB
#
# 注册方式（在 .claude/settings.json 或宿主配置中）：
#   { "hooks": { "SessionStart": [{ "command": "path/to/session-start-inject-context.sh" }] } }

# ─── CI 守卫：不在 CI 环境触发 ───
if [ -n "${CI:-}" ] || [ -n "${GITHUB_ACTIONS:-}" ] || [ -n "${GITLAB_CI:-}" ]; then
  exit 0
fi

# ─── 定位项目根 ───
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
AI_CONFIGS="${PROJECT_DIR}/.ai-configs"

# ─── 检测 .ai-configs 存在性 ───
[ -d "${AI_CONFIGS}" ] || exit 0

echo "=== Session Context (auto-injected) ==="
echo ""

# ─── 1. project-context.md ───
CONTEXT_FILE="${AI_CONFIGS}/project-context.md"
if [ -f "${CONTEXT_FILE}" ]; then
  echo "## project-context.md"
  echo ""
  cat "${CONTEXT_FILE}"
  echo ""
fi

# ─── 2. 当前 task meta ───
CURRENT_TASK=""
if [ -n "${XMAN_TASK:-}" ]; then
  CURRENT_TASK="${XMAN_TASK}"
elif [ -f "${AI_CONFIGS}/.current-task" ]; then
  CURRENT_TASK=$(cat "${AI_CONFIGS}/.current-task")
fi

if [ -n "${CURRENT_TASK}" ]; then
  META="${AI_CONFIGS}/tasks/${CURRENT_TASK}/meta.yml"
  if [ -f "${META}" ]; then
    echo "## current task: ${CURRENT_TASK}"
    echo ""
    cat "${META}"
    echo ""
    # 列出 task 下已有产物
    echo "产物文件:"
    find "${AI_CONFIGS}/tasks/${CURRENT_TASK}" -maxdepth 1 -type f -name '*.md' 2>/dev/null | sed 's|.*/|  - |'
    echo ""
  fi
fi

# ─── 3. workspace/journal.md 末尾 2KB ───
JOURNAL="${AI_CONFIGS}/workspace/journal.md"
if [ -f "${JOURNAL}" ]; then
  echo "## workspace/journal.md (末尾 2KB)"
  echo ""
  tail -c 2048 "${JOURNAL}"
  echo ""
fi

echo "=== End Session Context ==="
