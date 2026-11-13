#!/bin/bash

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly SKILLS_ROOT="${REPO_ROOT}/skills"
readonly AGENTS_ROOT="${REPO_ROOT}/agents"
readonly PLUGINS_ROOT="${REPO_ROOT}/plugins"
readonly TEAM_ROOT="${REPO_ROOT}/team"
readonly GOVERNANCE_ROOT="${REPO_ROOT}/governance"
readonly REGISTRY_FILE="${GOVERNANCE_ROOT}/skills-registry.csv"
SYNC_PLUGINS=()
SYNC_DIRECT_SKILLS=()
SYNC_DIRECT_AGENTS=()
SYNC_STATUSES=()
SYNC_NO_AGENTS="false"
SYNC_AGENT_FORMAT="${SYNC_AGENT_FORMAT:-markdown}"

usage_sync_common() {
  cat <<'EOF'
用法：
  sync-*.sh [PROJECT_DIR] [--plugin NAME]... [--skill NAME]... [--agent NAME]... [--status STATUS]... [--target PATH] [--dry-run] [--clean] [--no-agents]

参数：
  PROJECT_DIR     可选的项目目录，同步到 PROJECT_DIR/<平台子目录>/
  --plugin NAME   只同步某个 plugin 中列出的 skill，可重复传入
  --skill NAME    只同步指定 skill，可重复传入
  --agent NAME    只同步指定 agent，可重复传入
  --status STATUS 只同步指定状态的 skill/agent，可重复传入
  --target PATH   覆盖默认目标目录（优先级高于 PROJECT_DIR）
  --no-agents     跳过 agent 安装
  --dry-run       仅预览，不实际写入
  --clean         删除目标目录中不在本次同步集合中的旧软链
  --help          显示帮助

说明：
  1. 默认同步 skills/ 下全部 skill + agents/ 下全部 agent。
  2. 如果指定了 --skill 或 --plugin，只同步对应 skill，不自动包含 agent。
  3. 如果指定了 --agent，只同步对应 agent，不自动包含 skill。
  4. 可同时指定 --skill/--plugin 和 --agent 来安装两者。
  5. plugin 通过 plugins/<name>/ 下的软链解析。
  6. status 来自 governance/skills-registry.csv，可用值：team-shared / personal-only / experimental
  6.1 registry 的 release 列只标出发行版也有的同名条目；plugin 和 xman 直接安装都是完整的一套。
  7. 同步模式为软链：在目标目录下创建指向中心仓库的符号链接。
  8. 默认是增量同步，不删除目标中其他条目；只有显式传 --clean 才会清理。
EOF
}

normalize_list_file() {
  local file="$1"
  sed 's/#.*$//' "$file" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' | sed '/^$/d'
}

all_skills() {
  find "${SKILLS_ROOT}" -mindepth 1 -maxdepth 1 -type d -print | xargs -I{} basename "{}" | sort
}

skills_from_group_dir() {
  local dir="$1"
  [ -d "${dir}" ] || return 0
  find "${dir}" -mindepth 1 -maxdepth 1 \( -type l -o -type d \) -print | xargs -I{} basename "{}" | sort -u
}

skills_from_plugins() {
  local plugin
  for plugin in "$@"; do
    local plugin_dir="${PLUGINS_ROOT}/${plugin}"
    if [ ! -d "${plugin_dir}" ]; then
      echo "未找到 plugin 目录: ${plugin_dir}" >&2
      return 1
    fi
    skills_from_group_dir "${plugin_dir}"
  done | sort -u
}

ensure_skill_exists() {
  local skill="$1"
  local skill_dir="${SKILLS_ROOT}/${skill}"
  if [ ! -d "${skill_dir}" ]; then
    echo "skill 目录不存在: ${skill_dir}" >&2
    return 1
  fi
  if [ ! -f "${skill_dir}/SKILL.md" ]; then
    echo "缺少 SKILL.md: ${skill_dir}/SKILL.md" >&2
    return 1
  fi
}

all_agents() {
  [ -d "${AGENTS_ROOT}" ] || return 0
  # agent 的定义是扁平的 agents/<name>.md：埋成 agents/<name>/AGENT.md 时
  # plugin 的组件清单一条都收不到（实测 Agents(0)），等于这个 agent 没被分发。
  # 同名目录只放伴随文件（references/hooks/evals），README.md 之类没有 name
  # front-matter 的文档不算 agent。
  find "${AGENTS_ROOT}" -mindepth 1 -maxdepth 1 -name '*.md' -print \
    | while IFS= read -r f; do
        is_agent_definition "${f}" || continue
        basename "${f}" .md
      done | sort
}

# 判定一个 .md 是不是 agent 定义：首行是 ---，且 name: 出现在 front-matter 块内。
# 只查 '^name:' 会把 README.md 代码示例里的 name: agent-name 误判成 agent。
is_agent_definition() {
  local file="$1"
  [ -f "${file}" ] || return 1
  [ "$(head -1 "${file}")" = "---" ] || return 1
  awk 'NR==1{next} /^---[[:space:]]*$/{exit 1} /^name:/{exit 0}' "${file}"
}

ensure_agent_exists() {
  local agent="$1"
  if [ ! -f "${AGENTS_ROOT}/${agent}.md" ]; then
    echo "缺少 agent 定义: ${AGENTS_ROOT}/${agent}.md" >&2
    return 1
  fi
}

ensure_registry_exists() {
  if [ ! -f "${REGISTRY_FILE}" ]; then
    echo "缺少状态清单: ${REGISTRY_FILE}" >&2
    return 1
  fi
}

filter_selection_by_status() {
  ensure_registry_exists
  local registry="${REGISTRY_FILE}"
  local selected_input
  selected_input="$(cat)"
  SELECTED_SKILLS_INPUT="${selected_input}" python3 - "$registry" "$@" <<'PY'
import csv
import pathlib
import os
import sys

registry_path = pathlib.Path(sys.argv[1])
allowed_statuses = set(sys.argv[2:])
selected = [line.strip() for line in os.environ.get("SELECTED_SKILLS_INPUT", "").splitlines() if line.strip()]

with registry_path.open(newline="") as fh:
    rows = {row["skill"]: row["status"] for row in csv.DictReader(fh)}

missing = [skill for skill in selected if skill not in rows]
for skill in missing:
    print(f"状态清单缺少 skill: {skill}", file=sys.stderr)

for skill in selected:
    status = rows.get(skill)
    if status in allowed_statuses:
        print(skill)
PY
}

resolve_selection() {
  local -a selection=()
  if [ "${#SYNC_PLUGINS[@]}" -eq 0 ] && [ "${#SYNC_DIRECT_SKILLS[@]}" -eq 0 ]; then
    while IFS= read -r line; do
      [ -n "${line}" ] || continue
      selection+=("${line}")
    done < <(all_skills)
  else
    while IFS= read -r line; do
      [ -n "${line}" ] || continue
      selection+=("${line}")
    done < <(
      {
        if [ "${#SYNC_PLUGINS[@]}" -gt 0 ]; then
          skills_from_plugins "${SYNC_PLUGINS[@]}"
        fi
        if [ "${#SYNC_DIRECT_SKILLS[@]}" -gt 0 ]; then
          printf '%s\n' "${SYNC_DIRECT_SKILLS[@]}"
        fi
      } | sort -u
    )
  fi

  if [ "${#SYNC_STATUSES[@]}" -gt 0 ]; then
    local -a filtered=()
    while IFS= read -r line; do
      [ -n "${line}" ] || continue
      filtered+=("${line}")
    done < <(printf '%s\n' "${selection[@]}" | filter_selection_by_status "${SYNC_STATUSES[@]}")
    if [ "${#filtered[@]}" -gt 0 ]; then
      selection=("${filtered[@]}")
    else
      selection=()
    fi
  fi

  if [ "${#selection[@]}" -eq 0 ]; then
    echo "没有可处理的 skill。" >&2
    return 1
  fi

  local skill
  for skill in "${selection[@]}"; do
    ensure_skill_exists "${skill}"
  done

  printf '%s\n' "${selection[@]}"
}

resolve_agent_selection() {
  if [ "${SYNC_NO_AGENTS}" = "true" ]; then
    return 0
  fi

  local -a selection=()

  if [ "${#SYNC_DIRECT_AGENTS[@]}" -gt 0 ]; then
    # 用户指定了具体 agent
    selection=("${SYNC_DIRECT_AGENTS[@]}")
  elif [ "${#SYNC_DIRECT_SKILLS[@]}" -eq 0 ] && [ "${#SYNC_PLUGINS[@]}" -eq 0 ]; then
    # 默认全量安装：包含所有 agent
    while IFS= read -r line; do
      [ -n "${line}" ] || continue
      selection+=("${line}")
    done < <(all_agents)
  else
    # 用户只指定了 --skill 或 --plugin，不自动包含 agent
    return 0
  fi

  if [ "${#selection[@]}" -eq 0 ]; then
    return 0
  fi

  # 按 status 过滤（复用同一个 CSV，agent 也在里面）
  if [ "${#SYNC_STATUSES[@]}" -gt 0 ]; then
    local -a filtered=()
    while IFS= read -r line; do
      [ -n "${line}" ] || continue
      filtered+=("${line}")
    done < <(printf '%s\n' "${selection[@]}" | filter_selection_by_status "${SYNC_STATUSES[@]}")
    if [ "${#filtered[@]}" -gt 0 ]; then
      selection=("${filtered[@]}")
    else
      return 0
    fi
  fi

  local agent
  for agent in "${selection[@]}"; do
    ensure_agent_exists "${agent}"
  done

  printf '%s\n' "${selection[@]}"
}

# 母仓里的 agent 改名或删除后，平台目录里指向旧名字的软链会断在那里：安装新名字
# 不会碰它们，用户也看不出那是垃圾。只清判据明确的——软链、已断、且指向本母仓的
# agents/ 目录。别人建的链接和还能解析的链接一律不动。
prune_stale_agent_links() {
  local target="$1"
  local dry_run="$2"
  [ -d "${target}" ] || return 0

  local entry link_target pruned=0
  while IFS= read -r entry; do
    [ -n "${entry}" ] || continue
    [ -L "${entry}" ] || continue
    [ -e "${entry}" ] && continue
    link_target="$(readlink "${entry}")"
    case "${link_target}" in
      "${AGENTS_ROOT}"/*) ;;
      *) continue ;;
    esac
    echo "  清理失效软链: ${entry} -> ${link_target}"
    [ "${dry_run}" = "true" ] || rm -f "${entry}"
    pruned=$((pruned + 1))
  done < <(find "${target}" -mindepth 1 -maxdepth 1 -print 2>/dev/null)
  [ "${pruned}" -gt 0 ] && echo "  共清理 ${pruned} 个失效软链（母仓侧已改名或删除）"
  return 0
}

# Codex 的 .toml 是生成物不是软链，改名后旧文件仍能解析，只是指向的源已经不在。
# 判据同样明确：带我们的生成标记，且首行记录的 source 已不存在。
prune_stale_codex_agents() {
  local target="$1"
  local dry_run="$2"
  [ -d "${target}" ] || return 0

  local entry source_path pruned=0
  while IFS= read -r entry; do
    [ -n "${entry}" ] || continue
    head -1 "${entry}" | grep -q '^# Generated by x-mansion' || continue
    source_path="$(head -1 "${entry}" | sed -n 's/.*— source: //p')"
    [ -n "${source_path}" ] || continue
    [ -e "${source_path}" ] && continue
    echo "  清理失效 Codex Agent: ${entry}（源已不存在: ${source_path}）"
    [ "${dry_run}" = "true" ] || rm -f "${entry}"
    pruned=$((pruned + 1))
  done < <(find "${target}" -mindepth 1 -maxdepth 1 -type f -name '*.toml' -print 2>/dev/null)
  [ "${pruned}" -gt 0 ] && echo "  共清理 ${pruned} 个失效 Codex Agent（母仓侧已改名或删除）"
  return 0
}

# 平台目录里已存在的软链有三种来源，处理方式不同。原先只分两态：指向母仓的保留，
# 其余一律当"错误软链"删掉重建——这会把别人手工建的、或另一个工具装的链接无声顶掉。
#   ours    指向本母仓，我们自己装的，保持
#   release 指向项目的 .agents/ 锁定层，是发行版装的。同名条目按 x-mansion 优先接管，
#           但它不是错误，输出要如实说明来源
#   foreign 来源不明，不动，只报告
report_link_provenance() {
  local takeover="$1"
  local foreign="$2"
  [ "${takeover}" -gt 0 ] && echo "  已接管 ${takeover} 个由发行版提供的同名条目"
  [ "${foreign}" -gt 0 ] && echo "  跳过 ${foreign} 个来源不明的软链，未做改动" >&2
  return 0
}

classify_existing_link() {
  local target_path="$1"
  local source_realpath="$2"
  local resolved root
  resolved="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "${target_path}")"
  if [ "${resolved}" = "${source_realpath}" ]; then
    echo "ours"
    return 0
  fi
  # 平台目录形如 <root>/.claude/skills，上溯两级就是安装根
  root="$(python3 -c 'import os, sys; print(os.path.realpath(os.path.dirname(os.path.dirname(os.path.dirname(sys.argv[1])))))' "${target_path}")"
  case "${resolved}" in
    "${root}/.agents/"*) echo "release" ;;
    *) echo "foreign" ;;
  esac
}

sync_selected_agents() {
  local target="$1"
  local dry_run="$2"
  local clean="$3"
  shift 3
  local agents=("$@")

  if [ "${SYNC_AGENT_FORMAT}" = "codex-toml" ]; then
    sync_codex_agents "${target}" "${dry_run}" "${clean}" "${agents[@]}"
    return
  fi

  if [ "${dry_run}" != "true" ]; then
    mkdir -p "${target}"
  elif [ ! -d "${target}" ]; then
    echo "将创建目标目录: ${target}"
  fi

  local target_path=""
  local source_path=""
  local source_realpath=""
  local target_realpath=""
  prune_stale_agent_links "${target}" "${dry_run}"

  local agent part
  local takeover=0 foreign=0
  for agent in "${agents[@]}"; do
    ensure_agent_exists "${agent}"
    # agent = 一个扁平定义文件 + 一个可选的同名伴随目录，两者都要装过去。
    # 只装目录的话，平台侧收不到定义文件，这个 agent 等于不存在。
    for part in "${agent}.md" "${agent}"; do
    [ -e "${AGENTS_ROOT}/${part}" ] || continue
    source_path="${AGENTS_ROOT}/${part}"
    target_path="${target}/${part}"
    source_realpath="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "${source_path}")"

    if [ -L "${target_path}" ]; then
      case "$(classify_existing_link "${target_path}" "${source_realpath}")" in
        ours)
          echo "  已存在正确软链: ${target_path}"
          continue
          ;;
        release)
          echo "  接管发行版提供的同名条目: ${target_path}"
          takeover=$((takeover + 1))
          ;;
        *)
          echo "  跳过来源不明的软链: ${target_path} -> $(readlink "${target_path}")" >&2
          foreign=$((foreign + 1))
          continue
          ;;
      esac
      if [ "${dry_run}" != "true" ]; then
        rm -f "${target_path}"
        ln -s "${source_path}" "${target_path}"
      fi
      continue
    fi

    if [ -d "${target_path}" ]; then
      echo "  替换目录 ${part} -> 软链 ${source_path}"
      if [ "${dry_run}" != "true" ]; then
        rm -rf "${target_path}"
        ln -s "${source_path}" "${target_path}"
      fi
      continue
    fi

    echo "  链接 ${part} -> ${source_path}"
    if [ "${dry_run}" != "true" ]; then
      ln -s "${source_path}" "${target_path}"
    fi
    done
  done

  report_link_provenance "${takeover}" "${foreign}"

  if [ "${clean}" = "true" ]; then
    echo "清理目标目录中未选中的 agent..."
    local existing existing_agent
    while IFS= read -r existing; do
      [ -n "${existing}" ] || continue
      existing_agent="${existing%.md}"
      if ! printf '%s\n' "${agents[@]}" | grep -Fxq "${existing_agent}"; then
        if [ -L "${target}/${existing}" ]; then
          echo "  删除软链 ${target}/${existing}"
          if [ "${dry_run}" != "true" ]; then
            rm -f "${target}/${existing}"
          fi
          continue
        fi

        if [ -d "${target}/${existing}" ]; then
          echo "  跳过真实目录 ${target}/${existing}"
          continue
        fi
      fi
    done < <(find "${target}" -mindepth 1 -maxdepth 1 \( -type l -o -type d \) -print | xargs -I{} basename "{}" | sort -u)
  fi
}

sync_codex_agents() {
  local target="$1"
  local dry_run="$2"
  local clean="$3"
  shift 3
  local agents=("$@")
  local resource_root="$(dirname "${target}")/agent-resources"

  if [ "${dry_run}" != "true" ]; then
    mkdir -p "${target}" "${resource_root}"
  fi

  prune_stale_codex_agents "${target}" "${dry_run}"
  # 早期版本往 .codex/agents/ 里放的是 markdown 式软链，不是 toml。母仓侧改名后
  # 它们断在那儿，上面那条只清 toml，清不到。
  prune_stale_agent_links "${target}" "${dry_run}"
  prune_stale_agent_links "${resource_root}" "${dry_run}"

  local agent source_file target_file source_resources target_resources existing
  for agent in "${agents[@]}"; do
    ensure_agent_exists "${agent}"
    source_file="${AGENTS_ROOT}/${agent}.md"
    target_file="${target}/${agent}.toml"
    source_resources="${AGENTS_ROOT}/${agent}"
    target_resources="${resource_root}/${agent}"

    echo "  生成 ${agent}.toml -> ${target_file}"
    if [ "${dry_run}" = "true" ]; then
      continue
    fi

    if [ -f "${target_file}" ] && ! head -1 "${target_file}" | grep -q '^# Generated by x-mansion'; then
      echo "  跳过用户文件: ${target_file}" >&2
      continue
    fi

    for existing in "${target}/${agent}.md" "${target}/${agent}"; do
      [ -L "${existing}" ] && rm -f "${existing}"
    done

    if [ -d "${source_resources}" ]; then
      if [ -L "${target_resources}" ]; then
        rm -f "${target_resources}"
      elif [ -e "${target_resources}" ]; then
        echo "  使用已有资源目录: ${target_resources}" >&2
      fi
      [ -e "${target_resources}" ] || ln -s "${source_resources}" "${target_resources}"
    fi

    python3 "${SCRIPT_DIR}/sync-codex-agent.py" \
      --source "${source_file}" \
      --target "${target_file}" \
      --name "${agent}" \
      --resources "${target_resources}"
  done

  if [ "${clean}" = "true" ] && [ -d "${target}" ]; then
    while IFS= read -r existing; do
      [ -n "${existing}" ] || continue
      agent="$(basename "${existing}" .toml)"
      if ! printf '%s\n' "${agents[@]}" | grep -Fxq "${agent}" \
          && head -1 "${existing}" | grep -q '^# Generated by x-mansion'; then
        echo "  删除受管 Codex Agent: ${existing}"
        [ "${dry_run}" = "true" ] || rm -f "${existing}"
      fi
    done < <(find "${target}" -mindepth 1 -maxdepth 1 -type f -name '*.toml' -print)
  fi
}

CANONICAL_LAYER_NAME=".agents"

# 目标是否落在「随项目提交」的那一层：项目里的 .agents/ 下，且项目本身是 git 仓库。
# 全局层（HOME 下）不进版本库，不适用。
is_committable_layer() {
  local target="$1"
  case "${target}" in
    "${HOME}"/*) return 1 ;;
    */"${CANONICAL_LAYER_NAME}"/*) ;;
    *) return 1 ;;
  esac
  local project_root
  project_root="$(python3 -c 'import sys; print(sys.argv[1].split("/" + sys.argv[2] + "/")[0])' \
    "${target}" "${CANONICAL_LAYER_NAME}")"
  [ -d "${project_root}/.git" ]
}

# .agents/ 这一层在项目里可能是被要求提交进版本库的（Codex 读它，别的工具也可能
# 把真身放这儿）。而本仓的安装模型是软链到母仓——本机绝对路径，提交出去同事和 CI
# 全是断链。装完提醒一次，不替用户决定要不要提交。
warn_if_committable_target() {
  local target="$1"
  case "${target}" in
    */.agents/*) ;;
    *) return 0 ;;
  esac
  # 全局层（HOME 下）不存在提交问题
  case "${target}" in
    "${HOME}"/*) return 0 ;;
  esac

  local project_root
  project_root="$(python3 -c 'import os, sys; p = sys.argv[1]; print(p.split("/.agents/")[0])' "${target}")"
  [ -d "${project_root}/.git" ] || return 0

  local abs_links
  abs_links="$(find "${target}" -maxdepth 1 -type l -lname '/*' 2>/dev/null | wc -l | tr -d ' ')"
  [ "${abs_links}" -gt 0 ] || return 0

  echo ""
  echo "  ⚠ ${target} 下有 ${abs_links} 个指向母仓的绝对路径软链" >&2
  echo "    这一层若随项目提交，同事和 CI clone 下来全是断链。" >&2
  echo "    要么把它加进 .gitignore，要么在那些机器上同样安装本仓。" >&2
}

sync_selected_skills() {
  local target="$1"
  local dry_run="$2"
  local clean="$3"
  shift 3
  local skills=("$@")

  if [ "${dry_run}" != "true" ]; then
    mkdir -p "${target}"
  elif [ ! -d "${target}" ]; then
    echo "将创建目标目录: ${target}"
  fi

  local target_path=""
  local source_path=""
  local source_realpath=""
  local target_realpath=""
  local skill
  local takeover=0 foreign=0 kept=0
  for skill in "${skills[@]}"; do
    ensure_skill_exists "${skill}"
    source_path="${SKILLS_ROOT}/${skill}"
    target_path="${target}/${skill}"
    source_realpath="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "${source_path}")"

    if [ -L "${target_path}" ]; then
      case "$(classify_existing_link "${target_path}" "${source_realpath}")" in
        ours)
          echo "  已存在正确软链: ${target_path}"
          continue
          ;;
        release)
          echo "  接管发行版提供的同名条目: ${target_path}"
          takeover=$((takeover + 1))
          ;;
        *)
          echo "  跳过来源不明的软链: ${target_path} -> $(readlink "${target_path}")" >&2
          foreign=$((foreign + 1))
          continue
          ;;
      esac
      if [ "${dry_run}" != "true" ]; then
        rm -f "${target_path}"
        ln -s "${source_path}" "${target_path}"
      fi
      continue
    fi

    # .agents/ 这一层在项目里是要提交的：真实目录是别人放进版本库的真身，
    # 换成软链等于用一个提交不出去的东西替掉一个能提交的，同事 clone 下来就是断链。
    # 只在这一层例外，其余平台目录仍按 x-mansion 优先替换。
    if [ -d "${target_path}" ] && [ ! -L "${target_path}" ] \
        && is_committable_layer "${target}"; then
      echo "  保留已有真身 ${skill}（${CANONICAL_LAYER_NAME}/ 随项目提交，软链提交不出去）"
      kept=$((kept + 1))
      continue
    fi

    if [ -d "${target_path}" ]; then
      echo "  替换目录 ${skill} -> 软链 ${source_path}"
      if [ "${dry_run}" != "true" ]; then
        rm -rf "${target_path}"
        ln -s "${source_path}" "${target_path}"
      fi
      continue
    fi

    echo "  链接 ${skill} -> ${source_path}"
    if [ "${dry_run}" != "true" ]; then
      ln -s "${source_path}" "${target_path}"
    fi
  done

  report_link_provenance "${takeover}" "${foreign}"
  [ "${kept}" -gt 0 ] && echo "  保留 ${kept} 个已有真身（该层随项目提交）"
  warn_if_committable_target "${target}"

  if [ "${clean}" = "true" ]; then
    echo "清理目标目录中未选中的 skill..."
    local existing
    while IFS= read -r existing; do
      [ -n "${existing}" ] || continue
      if ! printf '%s\n' "${skills[@]}" | grep -Fxq "${existing}"; then
        if [ -L "${target}/${existing}" ]; then
          echo "  删除软链 ${target}/${existing}"
          if [ "${dry_run}" != "true" ]; then
            rm -f "${target}/${existing}"
          fi
          continue
        fi

        if [ -d "${target}/${existing}" ]; then
          echo "  跳过真实目录 ${target}/${existing}"
          continue
        fi
      fi
    done < <(find "${target}" -mindepth 1 -maxdepth 1 \( -type l -o -type d \) -print | xargs -I{} basename "{}" | sort -u)
  fi
}

run_sync() {
  local skill_subdir="$1"
  local default_skill_target="$2"
  local agent_subdir="$3"
  local default_agent_target="$4"
  shift 4

  local project_dir=""
  local skill_target=""
  local agent_target=""
  local dry_run="false"
  local clean="false"
  local no_agents="false"
  local -a plugins=()
  local -a direct_skills=()
  local -a direct_agents=()
  local -a statuses=()

  while [ "$#" -gt 0 ]; do
    case "$1" in
      --plugin)
        plugins+=("$2")
        shift 2
        ;;
      --skill)
        direct_skills+=("$2")
        shift 2
        ;;
      --agent)
        direct_agents+=("$2")
        shift 2
        ;;
      --status)
        statuses+=("$2")
        shift 2
        ;;
      --target)
        skill_target="$2"
        shift 2
        ;;
      --no-agents)
        no_agents="true"
        shift
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
        usage_sync_common
        return 0
        ;;
      -*)
        echo "未知参数: $1" >&2
        usage_sync_common >&2
        return 1
        ;;
      *)
        # 位置参数：项目目录
        if [ -z "${project_dir}" ]; then
          project_dir="$1"
        else
          echo "未知参数: $1" >&2
          usage_sync_common >&2
          return 1
        fi
        shift
        ;;
    esac
  done

  # 计算 skill 目标目录
  if [ -z "${skill_target}" ]; then
    if [ -n "${project_dir}" ]; then
      skill_target="${project_dir}/${skill_subdir}"
    else
      skill_target="${default_skill_target}"
    fi
  fi

  # 计算 agent 目标目录
  if [ -n "${project_dir}" ]; then
    agent_target="${project_dir}/${agent_subdir}"
  else
    agent_target="${default_agent_target}"
  fi

  SYNC_PLUGINS=()
  SYNC_DIRECT_SKILLS=()
  SYNC_DIRECT_AGENTS=()
  SYNC_STATUSES=()
  SYNC_NO_AGENTS="${no_agents}"
  if [ "${#plugins[@]}" -gt 0 ]; then
    SYNC_PLUGINS=("${plugins[@]}")
  fi
  if [ "${#direct_skills[@]}" -gt 0 ]; then
    SYNC_DIRECT_SKILLS=("${direct_skills[@]}")
  fi
  if [ "${#direct_agents[@]}" -gt 0 ]; then
    SYNC_DIRECT_AGENTS=("${direct_agents[@]}")
  fi
  if [ "${#statuses[@]}" -gt 0 ]; then
    SYNC_STATUSES=("${statuses[@]}")
  fi

  # ─── Skills ───
  # 如果只指定了 --agent 没有 --skill/--plugin，跳过 skill 安装
  local install_skills="true"
  if [ "${#direct_agents[@]}" -gt 0 ] && [ "${#direct_skills[@]}" -eq 0 ] && [ "${#plugins[@]}" -eq 0 ]; then
    install_skills="false"
  fi

  if [ "${install_skills}" = "true" ]; then
    local selection_output
    selection_output="$(resolve_selection)"
    local -a selection=()
    while IFS= read -r line; do
      [ -n "${line}" ] || continue
      selection+=("${line}")
    done <<< "${selection_output}"

    echo "仓库根目录: ${REPO_ROOT}"
    echo "Skill 目标目录: ${skill_target}"
    echo "选择的 skill:"
    printf '  - %s\n' "${selection[@]}"
    echo ""

    sync_selected_skills "${skill_target}" "${dry_run}" "${clean}" "${selection[@]}"
  fi

  # ─── Agents ───
  local agent_selection_output
  agent_selection_output="$(resolve_agent_selection)" || true
  local -a agent_selection=()
  if [ -n "${agent_selection_output}" ]; then
    while IFS= read -r line; do
      [ -n "${line}" ] || continue
      agent_selection+=("${line}")
    done <<< "${agent_selection_output}"
  fi

  if [ "${#agent_selection[@]}" -gt 0 ]; then
    echo ""
    echo "Agent 目标目录: ${agent_target}"
    echo "选择的 agent:"
    printf '  - %s\n' "${agent_selection[@]}"
    echo ""

    sync_selected_agents "${agent_target}" "${dry_run}" "${clean}" "${agent_selection[@]}"
  fi
}
