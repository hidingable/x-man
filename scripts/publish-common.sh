#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/sync-common.sh"

usage_publish_common() {
  cat <<'EOF'
用法：
  publish-*.sh --target PATH [--plugin NAME]... [--skill NAME]... [--status STATUS]... [--dry-run] [--clean]

参数：
  --target PATH    导出目标仓库根目录
  --plugin NAME    限制导出的 plugin，可重复
  --skill NAME     限制导出的 skill，可重复
  --status STATUS  限制导出的状态，可重复
  --dry-run        仅预览，不实际写入
  --clean          清理目标仓库中已不再导出的内容
  --help           显示帮助

说明：
  1. publish-team.sh 默认导出 team-shared
  2. publish-personal.sh 默认导出 personal-only + experimental
  3. 目标目录会生成一个可独立使用的 skill 仓库子集
EOF
}

render_filtered_registry() {
  local target_file="$1"
  shift
  local skills=("$@")
  ensure_registry_exists

  python3 - "${REGISTRY_FILE}" "${target_file}" "${skills[@]}" <<'PY'
import csv
import pathlib
import sys

registry = pathlib.Path(sys.argv[1])
target = pathlib.Path(sys.argv[2])
selected = set(sys.argv[3:])

with registry.open(newline="") as fh:
    rows = list(csv.DictReader(fh))

fieldnames = rows[0].keys() if rows else ["skill", "plugin", "status", "source", "note"]
target.parent.mkdir(parents=True, exist_ok=True)
with target.open("w", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        if row["skill"] in selected:
            writer.writerow(row)
PY
}

reset_directory_contents() {
  local dir="$1"
  mkdir -p "${dir}"
  find "${dir}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
}

render_plugin_symlinks() {
  local target_root="$1"
  shift
  local skills=("$@")
  local plugin_dir
  for plugin_dir in "${PLUGINS_ROOT}"/*; do
    [ -d "${plugin_dir}" ] || continue
    local plugin_name
    plugin_name="$(basename "${plugin_dir}")"
    local target_plugin_dir="${target_root}/plugins/${plugin_name}"
    reset_directory_contents "${target_plugin_dir}"

    local linked_skill
    while IFS= read -r linked_skill; do
      [ -n "${linked_skill}" ] || continue
      if printf '%s\n' "${skills[@]}" | grep -Fxq "${linked_skill}"; then
        ln -s "../../skills/${linked_skill}" "${target_plugin_dir}/${linked_skill}"
      fi
    done < <(skills_from_group_dir "${plugin_dir}")
  done
}

render_team_symlinks() {
  local target_root="$1"
  shift
  local skills=("$@")
  local target_team_dir="${target_root}/team/skills"
  reset_directory_contents "${target_team_dir}"

  if [ ! -d "${TEAM_ROOT}/skills" ]; then
    return 0
  fi

  local linked_skill
  while IFS= read -r linked_skill; do
    [ -n "${linked_skill}" ] || continue
    if printf '%s\n' "${skills[@]}" | grep -Fxq "${linked_skill}"; then
      ln -s "../../skills/${linked_skill}" "${target_team_dir}/${linked_skill}"
    fi
  done < <(skills_from_group_dir "${TEAM_ROOT}/skills")
}

copy_static_repo_files() {
  local target_root="$1"
  local dry_run="$2"

  mkdir -p "${target_root}"

  if [ "${dry_run}" = "true" ]; then
    echo "复制 Skill Bundle README 和治理说明 -> ${target_root}"
    echo "复制脚本目录 -> ${target_root}/scripts"
    echo "生成 team/skills 和 plugins/* 软链视图"
    return 0
  fi

  cp "${REPO_ROOT}/context/templates/published-skill-bundle-readme.md" "${target_root}/README.md"
  if [ ! -e "${target_root}/LICENSE" ] && [ ! -L "${target_root}/LICENSE" ]; then
    cp "${REPO_ROOT}/LICENSE" "${target_root}/LICENSE"
  fi
  mkdir -p "${target_root}/governance"
  cp "${GOVERNANCE_ROOT}/README.md" "${target_root}/governance/README.md"
  mkdir -p "${target_root}/scripts"
  mkdir -p "${target_root}/team/skills"
  mkdir -p "${target_root}/plugins"

  local script
  for script in \
    sync-common.sh \
    sync-codex.sh \
    sync-claude.sh \
    sync-cursor.sh \
    audit-sync.sh
  do
    cp "${SCRIPT_DIR}/${script}" "${target_root}/scripts/${script}"
    chmod +x "${target_root}/scripts/${script}"
  done
}

clean_publish_target() {
  local target_root="$1"
  local -a selected_skills=("${@:2}")

  [ -d "${target_root}/skills" ] || return 0
  local existing
  while IFS= read -r existing; do
    [ -n "${existing}" ] || continue
    if ! printf '%s\n' "${selected_skills[@]}" | grep -Fxq "${existing}"; then
      rm -rf "${target_root}/skills/${existing}"
    fi
  done < <(find "${target_root}/skills" -mindepth 1 -maxdepth 1 -type d -print | xargs -I{} basename "{}" | sort)
}

run_publish() {
  local default_statuses_csv="$1"
  shift

  local target=""
  local dry_run="false"
  local clean="false"
  local -a plugins=()
  local -a direct_skills=()
  local -a statuses=()

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --target)
        target="$2"
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
      --dry-run)
        dry_run="true"
        shift
        ;;
      --clean)
        clean="true"
        shift
        ;;
      --help)
        usage_publish_common
        return 0
        ;;
      *)
        echo "未知参数: $1" >&2
        usage_publish_common >&2
        return 1
        ;;
    esac
  done

  if [ -z "${target}" ]; then
    echo "必须提供 --target PATH" >&2
    return 1
  fi

  if [ "${#statuses[@]}" -eq 0 ]; then
    IFS=',' read -r -a statuses <<< "${default_statuses_csv}"
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

  local private_config="${target}/skills/git-commit/scripts/llm-commit.env"
  if [ -e "${private_config}" ] || [ -L "${private_config}" ]; then
    echo "发布目标已有本机配置，请先移出该文件或使用新目录: ${private_config}" >&2
    return 1
  fi

  echo "仓库根目录: ${REPO_ROOT}"
  echo "发布目标: ${target}"
  echo "发布 skill:"
  printf '  - %s\n' "${selection[@]}"

  copy_static_repo_files "${target}" "${dry_run}"

  if [ "${dry_run}" = "true" ]; then
    local skill
    for skill in "${selection[@]}"; do
      echo "将复制 ${skill} -> ${target}/skills/${skill}"
    done
    echo "将生成裁剪后的 plugins 和 governance 清单"
    if [ "${clean}" = "true" ]; then
      echo "将清理 ${target}/skills 中未选中的 skill"
    fi
    return 0
  fi

  mkdir -p "${target}/skills"
  local skill
  for skill in "${selection[@]}"; do
    mkdir -p "${target}/skills/${skill}"
    rsync -a --exclude '/scripts/llm-commit.env' "${SKILLS_ROOT}/${skill}/" "${target}/skills/${skill}/"
  done

  render_plugin_symlinks "${target}" "${selection[@]}"
  render_team_symlinks "${target}" "${selection[@]}"
  render_filtered_registry "${target}/governance/skills-registry.csv" "${selection[@]}"

  if [ "${clean}" = "true" ]; then
    clean_publish_target "${target}" "${selection[@]}"
  fi
}
