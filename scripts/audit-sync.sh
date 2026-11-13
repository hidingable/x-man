#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/sync-common.sh"

usage() {
  cat <<'EOF'
用法：
  audit-sync.sh [--platform codex|claude|cursor]... [--plugin NAME]... [--skill NAME]... [--status STATUS]... [--target PATH] [--verbose]

参数：
  --platform NAME  指定对账平台，可重复。默认同时检查 codex、claude、cursor
  --plugin NAME    只检查某个 plugin 中列出的 skill，可重复
  --skill NAME     只检查指定 skill，可重复
  --status STATUS  只检查指定状态的 skill，可重复
  --target PATH    覆盖单个平台的目标目录。仅在只传一个 --platform 时允许使用
  --verbose        输出同名 skill 的差异文件清单
  --help           显示帮助

输出：
  1. 中心仓库缺失/目标缺失/目标额外存在
  2. 同名 skill 的内容是否漂移
EOF
}

platform_default_target() {
  case "$1" in
    codex) echo "${HOME}/.codex/skills" ;;
    claude) echo "${HOME}/.claude/skills" ;;
    cursor) echo "${HOME}/.cursor/skills" ;;
    *)
      echo "未知平台: $1" >&2
      return 1
      ;;
  esac
}

list_skill_dirs() {
  local root="$1"
  if [ ! -d "${root}" ]; then
    return 0
  fi
  find "${root}" -mindepth 1 -maxdepth 1 \( -type d -o -type l \) -print | xargs -I{} basename "{}" | sort -u
}

skill_signature() {
  local skill_dir="$1"
  if [ ! -d "${skill_dir}" ] && [ ! -L "${skill_dir}" ]; then
    return 0
  fi
  find -L "${skill_dir}" -type f -print | sort | while IFS= read -r file; do
    local rel
    rel="${file#${skill_dir}/}"
    shasum_output="$(shasum "${file}")"
    printf '%s  %s\n' "${shasum_output%% *}" "${rel}"
  done
}

audit_platform() {
  local platform="$1"
  local target="$2"
  local verbose="$3"
  shift 3
  local selected_skills=("$@")

  echo
  echo "=== ${platform} ==="
  echo "目标目录: ${target}"

  if [ ! -d "${target}" ]; then
    echo "状态: 目标目录不存在"
    return 0
  fi

  local -a target_skills=()
  while IFS= read -r line; do
    [ -n "${line}" ] || continue
    target_skills+=("${line}")
  done < <(list_skill_dirs "${target}")

  local skill
  local missing_count=0
  for skill in "${selected_skills[@]}"; do
    if [ ! -d "${target}/${skill}" ]; then
      if [ "${missing_count}" -eq 0 ]; then
        echo "目标缺失:"
      fi
      echo "  - ${skill}"
      missing_count=$((missing_count + 1))
    fi
  done
  if [ "${missing_count}" -eq 0 ]; then
    echo "目标缺失: 无"
  fi

  local extra_count=0
  local existing
  for existing in "${target_skills[@]}"; do
    if ! printf '%s\n' "${selected_skills[@]}" | grep -Fxq "${existing}"; then
      if [ "${extra_count}" -eq 0 ]; then
        echo "目标额外存在:"
      fi
      echo "  - ${existing}"
      extra_count=$((extra_count + 1))
    fi
  done
  if [ "${extra_count}" -eq 0 ]; then
    echo "目标额外存在: 无"
  fi

  local drift_count=0
  for skill in "${selected_skills[@]}"; do
    if [ ! -d "${target}/${skill}" ]; then
      continue
    fi
    if ! diff -q <(skill_signature "${SKILLS_ROOT}/${skill}") <(skill_signature "${target}/${skill}") >/dev/null 2>&1; then
      if [ "${drift_count}" -eq 0 ]; then
        echo "内容漂移:"
      fi
      echo "  - ${skill}"
      drift_count=$((drift_count + 1))
      if [ "${verbose}" = "true" ]; then
        diff -u <(skill_signature "${SKILLS_ROOT}/${skill}") <(skill_signature "${target}/${skill}") | sed '1,2d; s/^/    /'
      fi
    fi
  done
  if [ "${drift_count}" -eq 0 ]; then
    echo "内容漂移: 无"
  fi
}

main() {
  local -a platforms=()
  local -a plugins=()
  local -a direct_skills=()
  local -a statuses=()
  local custom_target=""
  local verbose="false"

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --platform)
        platforms+=("$2")
        shift 2
        ;;
      --plugin)
        plugins+=("$2")
        shift 2
        ;;
      --skill)
        direct_skills+=("$2")
        shift 2
        ;;
      --status)
        statuses+=("$2")
        shift 2
        ;;
      --target)
        custom_target="$2"
        shift 2
        ;;
      --verbose)
        verbose="true"
        shift
        ;;
      --help)
        usage
        return 0
        ;;
      *)
        echo "未知参数: $1" >&2
        usage >&2
        return 1
        ;;
    esac
  done

  if [ "${#platforms[@]}" -eq 0 ]; then
    platforms=(codex claude cursor)
  fi

  if [ -n "${custom_target}" ] && [ "${#platforms[@]}" -ne 1 ]; then
    echo "--target 只能在单个平台模式下使用" >&2
    return 1
  fi

  SYNC_PLUGINS=()
  SYNC_DIRECT_SKILLS=()
  SYNC_STATUSES=()
  if [ "${#plugins[@]}" -gt 0 ]; then
    SYNC_PLUGINS=("${plugins[@]}")
  fi
  if [ "${#direct_skills[@]}" -gt 0 ]; then
    SYNC_DIRECT_SKILLS=("${direct_skills[@]}")
  fi
  if [ "${#statuses[@]}" -gt 0 ]; then
    SYNC_STATUSES=("${statuses[@]}")
  fi
  local selection_output
  selection_output="$(resolve_selection)"
  local -a selection=()
  while IFS= read -r line; do
    [ -n "${line}" ] || continue
    selection+=("${line}")
  done <<< "${selection_output}"

  echo "仓库根目录: ${REPO_ROOT}"
  echo "对账 skill:"
  printf '  - %s\n' "${selection[@]}"

  local platform
  for platform in "${platforms[@]}"; do
    local target
    target="$(platform_default_target "${platform}")"
    if [ -n "${custom_target}" ]; then
      target="${custom_target}"
    fi
    audit_platform "${platform}" "${target}" "${verbose}" "${selection[@]}"
  done
}

main "$@"
