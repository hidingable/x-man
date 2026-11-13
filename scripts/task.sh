#!/bin/bash
set -euo pipefail

# task.sh — xman task 子命令实现
# 用法：
#   task.sh new <slug> [--title T] [--tag t1,t2]
#   task.sh list
#   task.sh use <id>
#   task.sh current          (打印当前 task id，无则空)

# 向上查找最近的 .ai-configs 父目录，避免在子目录跑命令时建错位置
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
  # 找不到则退回 cwd（首次创建场景）
  pwd
}

# shellcheck source=./json-common.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/json-common.sh"

PROJECT_ROOT="$(find_project_root)"
AI_CONFIGS="${PROJECT_ROOT}/.ai-configs"
TASKS_DIR="${AI_CONFIGS}/tasks"
CURRENT_FILE="${AI_CONFIGS}/.current-task"

# ─── helper：解析当前 task ───
# 优先级：$1 (CLI) > $XMAN_TASK > .current-task 文件 > 空
#
# 解析出的 id 必须在**当前项目**的 tasks/ 下真实存在，否则一律视为无 task。
# 这道校验防的是跨项目混用：XMAN_TASK 是终端级环境变量，在项目 A 里 export
# 之后 cd 到项目 B 依然生效；.current-task 也可能指向已被 mv 到 .abandoned
# 或直接删掉的 task。不校验的话，B 项目的 skill 会拿着 A 项目的 task-id 落盘，
# 凭空建出一个同名幽灵 task，两个项目的产物就串了。
xman_current_task() {
  local id="" origin=""
  if [ "${1:-}" != "" ]; then
    id="$1"; origin="--task 参数"
  elif [ "${XMAN_TASK:-}" != "" ]; then
    id="${XMAN_TASK}"; origin="XMAN_TASK 环境变量"
  elif [ -f "${CURRENT_FILE}" ]; then
    id="$(cat "${CURRENT_FILE}" 2>/dev/null || true)"; origin=".current-task"
  fi

  if [ -z "${id}" ]; then echo ""; return 0; fi

  if [ ! -d "${TASKS_DIR}/${id}" ]; then
    echo "⚠️  ${origin} 指向的 task 在本项目不存在，已忽略: ${id}" >&2
    echo "    项目: ${PROJECT_ROOT}" >&2
    if [ -d "${TASKS_DIR}/.abandoned/${id}" ]; then
      echo "    （该 task 已被废弃到 .abandoned/）" >&2
    elif [ "${origin}" = "XMAN_TASK 环境变量" ]; then
      echo "    （多半是在别的项目 export 后带过来的，unset XMAN_TASK 或重新 xman task use）" >&2
    fi
    echo ""
    return 0
  fi

  echo "${id}"
}

# ─── 校验 slug 字符集 ───
validate_slug() {
  local slug="$1"
  if ! echo "${slug}" | grep -Eq '^[a-z0-9-]+$'; then
    echo "❌ slug 必须匹配 [a-z0-9-]+：${slug}" >&2
    exit 1
  fi
}

# ─── task new ───
cmd_new() {
  if [ "$#" -eq 0 ]; then
    echo "用法: xman task new <slug> [--title T] [--tag t1,t2]" >&2
    exit 1
  fi

  local slug="$1"; shift
  validate_slug "${slug}"

  local title="${slug}"
  local tags=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --title) title="$2"; shift 2 ;;
      --tag|--tags) tags="$2"; shift 2 ;;
      *) echo "未知参数: $1" >&2; exit 1 ;;
    esac
  done

  if [ ! -d "${TASKS_DIR}" ]; then
    echo "❌ ${TASKS_DIR} 不存在，先运行 'xman context init'" >&2
    exit 1
  fi

  local ym
  ym=$(date +%Y-%m)
  local id="${ym}-${slug}"
  local dir="${TASKS_DIR}/${id}"

  if [ -d "${dir}" ]; then
    echo "❌ task 已存在: ${id}" >&2
    exit 1
  fi

  mkdir -p "${dir}"

  # 生成 tags 的 YAML 数组表达
  local tags_yaml="[]"
  if [ -n "${tags}" ]; then
    tags_yaml="[$(echo "${tags}" | sed 's/,/, /g')]"
  fi

  cat > "${dir}/meta.yml" <<META_EOF
title: ${title}
stage: in_progress
tags: ${tags_yaml}
links:
  pr: null
  issue: null
META_EOF

  echo "✅ 已创建 task: ${id}"
  echo "   目录: ${dir}"
  echo ""
  echo "下一步: xman task use ${id}"
}

# ─── 读取 meta.yml 字段 ───
# 必须永远返回 0 并在无值时回显空串：调用方用 $(meta_field ...) 取值，
# 脚本开了 set -euo pipefail，非零返回会让整条命令静默中止。
# meta.yml 缺失、或缺某个 key（如老 task 没有 tags）都属于正常情况。
meta_field() {
  local meta="$1" key="$2"
  [ -f "${meta}" ] || { echo ""; return 0; }
  grep -E "^${key}:" "${meta}" 2>/dev/null | head -1 | sed "s/^${key}: *//" || true
}

# ─── task list ───
cmd_list() {
  local f_month="" f_stage="" f_tag="" as_json=false
  # 取值型参数必须先判断有没有下一个词，否则 set -u 下会以
  # "$2: unbound variable" 崩掉，而不是给出用法提示
  need_value() {
    [ "$#" -ge 2 ] && [ -n "${2:-}" ] || {
      echo "❌ $1 需要一个值（用法: --month YYYY-MM | --stage S | --tag T）" >&2
      exit 1
    }
  }
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --month) need_value "$@"; f_month="$2"; shift 2 ;;
      --stage) need_value "$@"; f_stage="$2"; shift 2 ;;
      --tag)   need_value "$@"; f_tag="$2"; shift 2 ;;
      --json)  as_json=true; shift ;;
      *) echo "未知参数: $1（支持 --month YYYY-MM | --stage S | --tag T | --json）" >&2; exit 1 ;;
    esac
  done

  if [ ! -d "${TASKS_DIR}" ]; then
    if [ "${as_json}" = "true" ]; then
      printf '' | json_wrap tasks id stage title current
    else
      echo "${TASKS_DIR} 不存在"
    fi
    return
  fi

  local current
  current=$(xman_current_task "")

  if [ "${as_json}" = "false" ]; then
    echo "=== Task 列表 ==="
    local filters=""
    [ -n "${f_month}" ] && filters="${filters} month=${f_month}"
    [ -n "${f_stage}" ] && filters="${filters} stage=${f_stage}"
    [ -n "${f_tag}" ] && filters="${filters} tag=${f_tag}"
    [ -n "${filters}" ] && echo "过滤条件:${filters}"
    echo ""
    printf "  %-2s %-30s %-14s %s\n" "" "ID" "STAGE" "TITLE"
  fi

  local found=false
  local rows=""
  for dir in "${TASKS_DIR}"/*/; do
    [ -d "${dir}" ] || continue
    local name
    name=$(basename "${dir}")
    [ "${name}" = ".abandoned" ] && continue
    [ "${name}" = "*" ] && continue

    local meta="${dir}meta.yml"
    local title stage tags
    title=$(meta_field "${meta}" title)
    stage=$(meta_field "${meta}" stage)
    tags=$(meta_field "${meta}" tags)
    [ -n "${title}" ] || title="(无 meta.yml)"
    [ -n "${stage}" ] || stage="?"

    # 过滤：month 匹配 task-id 的 YYYY-MM 前缀
    [ -n "${f_month}" ] && case "${name}" in "${f_month}"-*) ;; *) continue ;; esac
    [ -n "${f_stage}" ] && [ "${stage}" != "${f_stage}" ] && continue
    if [ -n "${f_tag}" ]; then
      echo "${tags}" | grep -qw -- "${f_tag}" || continue
    fi

    found=true
    if [ "${as_json}" = "true" ]; then
      local is_current="false"
      [ "${name}" = "${current}" ] && is_current="true"
      rows="${rows}$(tsv_safe "${name}")"$'\t'"$(tsv_safe "${stage}")"$'\t'"$(tsv_safe "${title}")"$'\t'"${is_current}"$'\n' 
      continue
    fi

    local marker="  "
    [ "${name}" = "${current}" ] && marker="★ "
    printf "  %s %-30s %-14s %s\n" "${marker}" "${name}" "${stage}" "${title}"
  done

  if [ "${as_json}" = "true" ]; then
    printf '%s' "${rows}" | json_wrap tasks id stage title current
    return
  fi

  if [ "${found}" = "false" ]; then
    echo "  （无匹配 task）"
  fi
  echo ""
  [ -n "${current}" ] && echo "当前 task: ${current}" || echo "当前 task: (未设置)"
}

# ─── task find ───
# 跨两套形态检索：task 目录名 / meta.yml / ad-hoc 产物文件名与正文
cmd_find() {
  if [ "$#" -eq 0 ]; then
    echo "用法: xman task find <关键词>" >&2
    exit 1
  fi
  local kw="$1"; shift
  local as_json=false
  [ "${1:-}" = "--json" ] && as_json=true

  if [ ! -d "${AI_CONFIGS}" ]; then
    echo "${AI_CONFIGS} 不存在，先运行 'xman context init'" >&2
    exit 1
  fi

  # 优先用 rg，回退 grep
  local grep_cmd
  if command -v rg >/dev/null 2>&1; then
    grep_cmd="rg -il --no-messages"
  else
    grep_cmd="grep -ril"
  fi

  if [ "${as_json}" = "false" ]; then
    echo "=== 检索: ${kw} ==="
    echo ""
    echo "── Task ──"
  fi

  # 1. task 目录（目录名或 meta.yml 命中）
  local hit=false
  local task_rows=""
  if [ -d "${TASKS_DIR}" ]; then
    for dir in "${TASKS_DIR}"/*/; do
      [ -d "${dir}" ] || continue
      local name
      name=$(basename "${dir}")
      [ "${name}" = ".abandoned" ] && continue
      [ "${name}" = "*" ] && continue

      local meta="${dir}meta.yml"
      local matched=false
      echo "${name}" | grep -qi -- "${kw}" && matched=true
      if [ "${matched}" = "false" ] && [ -f "${meta}" ]; then
        grep -qi -- "${kw}" "${meta}" && matched=true
      fi

      if [ "${matched}" = "true" ]; then
        hit=true
        local title stage
        title=$(meta_field "${meta}" title)
        stage=$(meta_field "${meta}" stage)
        if [ "${as_json}" = "true" ]; then
          local arts=""
          for f in "${dir}"*.md; do
            [ -f "${f}" ] && arts="${arts}$(basename "${f}"),"
          done
          task_rows="${task_rows}$(tsv_safe "${name}")"$'\t'"$(tsv_safe "${stage:-?}")"$'\t'"$(tsv_safe "${title}")"$'\t'"${arts%,}"$'\n' 
        else
          printf "  %-30s %-14s %s\n" "${name}" "${stage:-?}" "${title}"
          for f in "${dir}"*.md; do
            [ -f "${f}" ] && echo "      └─ $(basename "${f}")"
          done
        fi
      fi
    done
  fi
  if [ "${as_json}" = "false" ]; then
    [ "${hit}" = "false" ] && echo "  （无匹配）"
    echo ""
    echo "── Ad-hoc 产物 ──"
  fi

  # 2. ad-hoc 产物（文件名或正文命中）
  local results
  results=$(
    {
      find "${AI_CONFIGS}" -type f \( -name '*.md' -o -name '*.yaml' \) \
        -not -path "${TASKS_DIR}/*" -iname "*${kw}*" 2>/dev/null
      ${grep_cmd} -- "${kw}" "${AI_CONFIGS}" 2>/dev/null \
        | grep -v "^${TASKS_DIR}/" || true
    } | sort -u
  )

  if [ "${as_json}" = "true" ]; then
    python3 -c '
import json, sys
kw, root = sys.argv[1], sys.argv[2]
task_tsv, adhoc = sys.argv[3], sys.argv[4]
tasks = []
for line in task_tsv.splitlines():
    if not line:
        continue
    parts = (line.split("\t") + [""] * 4)[:4]
    tasks.append({"id": parts[0], "stage": parts[1], "title": parts[2],
                  "artifacts": [a for a in parts[3].split(",") if a]})
files = [f[len(root) + 1:] if f.startswith(root + "/") else f
         for f in adhoc.splitlines() if f]
print(json.dumps({"keyword": kw, "tasks": tasks, "adhoc": files},
                 ensure_ascii=False, indent=2))
' "${kw}" "${PROJECT_ROOT}" "${task_rows}" "${results}"
    return
  fi

  if [ -z "${results}" ]; then
    echo "  （无匹配）"
  else
    echo "${results}" | while IFS= read -r f
    do
      [ -n "${f}" ] || continue
      echo "  ${f#"${PROJECT_ROOT}"/}"
    done
  fi
  echo ""
  echo "提示: 已知 task-id 时可直接 rg -l '<task-id>' ${AI_CONFIGS#"${PROJECT_ROOT}"/}"
}

# ─── task use ───
cmd_use() {
  if [ "$#" -eq 0 ]; then
    echo "用法: xman task use <id>" >&2
    exit 1
  fi
  local id="$1"
  local dir="${TASKS_DIR}/${id}"
  if [ ! -d "${dir}" ]; then
    echo "❌ task 不存在: ${id}" >&2
    exit 1
  fi
  mkdir -p "${AI_CONFIGS}"
  echo "${id}" > "${CURRENT_FILE}"
  echo "✅ 当前 task 已切换为: ${id}"
}

# ─── task current ───
cmd_current() {
  local c as_json=false
  [ "${1:-}" = "--json" ] && as_json=true
  c=$(xman_current_task "")
  if [ "${as_json}" = "true" ]; then
    json_object task "${c}"
    return
  fi
  [ -n "${c}" ] && echo "${c}" || true
}

# ─── 主路由 ───
if [ "$#" -eq 0 ]; then
  cat <<'USAGE_EOF'
用法: xman task <子命令> [参数...]

子命令:
  new <slug> [--title T] [--tag t1,t2]   创建新 task
  list [--month YYYY-MM] [--stage S] [--tag T] [--json]
                                          列出 task，可按月份/阶段/标签过滤
  find <关键词> [--json]                   跨 task 目录与 ad-hoc 产物检索
  use <id>                                切换当前 task
  current [--json]                        打印当前 task id

示例:
  xman task list --month 2026-08 --stage in_progress
  xman task list --tag auth
  xman task find 登录
  xman task list --json          # 机器可读，给 agent 用
USAGE_EOF
  exit 0
fi

sub="$1"; shift
case "${sub}" in
  new) cmd_new "$@" ;;
  list|ls) cmd_list "$@" ;;
  find|search) cmd_find "$@" ;;
  use) cmd_use "$@" ;;
  current) cmd_current "$@" ;;
  *) echo "未知 task 子命令: ${sub}" >&2; exit 1 ;;
esac
