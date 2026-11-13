#!/bin/bash
set -euo pipefail

# journal.sh — xman journal 子命令实现
# 用法：
#   journal.sh add "msg" [--task <id>]
#   journal.sh tail [-n N]

# 向上查找最近的 .ai-configs 父目录，避免在子目录跑命令时写错位置
find_project_root() {
  local dir
  dir=$(pwd)
  while [ "${dir}" != "/" ]; do
    if [ -d "${dir}/.ai-configs" ]; then
      echo "${dir}"
      return
    fi
    dir=$(dirname "${dir}")
  done
  pwd
}

PROJECT_ROOT="$(find_project_root)"
AI_CONFIGS="${PROJECT_ROOT}/.ai-configs"
JOURNAL="${AI_CONFIGS}/workspace/journal.md"
CURRENT_FILE="${AI_CONFIGS}/.current-task"

resolve_task() {
  if [ "${1:-}" != "" ]; then echo "$1"; return; fi
  if [ "${XMAN_TASK:-}" != "" ]; then echo "${XMAN_TASK}"; return; fi
  if [ -f "${CURRENT_FILE}" ]; then cat "${CURRENT_FILE}"; return; fi
  echo "null"
}

cmd_add() {
  if [ "$#" -eq 0 ]; then
    echo "用法: xman journal add \"msg\" [--task <id>]" >&2
    exit 1
  fi

  local msg=""
  local task_override=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --task) task_override="$2"; shift 2 ;;
      *)
        if [ -z "${msg}" ]; then msg="$1"; else msg="${msg} $1"; fi
        shift
        ;;
    esac
  done

  if [ -z "${msg}" ]; then
    echo "❌ 消息不能为空" >&2
    exit 1
  fi

  local task
  task=$(resolve_task "${task_override}")
  local date
  date=$(date +%Y-%m-%d)

  mkdir -p "$(dirname "${JOURNAL}")"
  [ -f "${JOURNAL}" ] || printf '# Workspace Journal\n\n' > "${JOURNAL}"

  echo "[${date}] task=${task} ${msg}" >> "${JOURNAL}"
  echo "✅ 已追加到 ${JOURNAL}"
}

cmd_tail() {
  local n=10
  if [ "${1:-}" = "-n" ]; then n="$2"; fi
  [ -f "${JOURNAL}" ] || { echo "${JOURNAL} 不存在"; return; }
  tail -n "${n}" "${JOURNAL}"
}

if [ "$#" -eq 0 ]; then
  cat <<'USAGE_EOF'
用法: xman journal <子命令> [参数...]

子命令:
  add "msg" [--task <id>]    追加一条 journal
  tail [-n N]                查看最近 N 条
USAGE_EOF
  exit 0
fi

sub="$1"; shift
case "${sub}" in
  add) cmd_add "$@" ;;
  tail) cmd_tail "$@" ;;
  *) echo "未知 journal 子命令: ${sub}" >&2; exit 1 ;;
esac
