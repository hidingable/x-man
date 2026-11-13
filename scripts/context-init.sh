#!/bin/bash
set -euo pipefail

# context-init.sh — 项目上下文初始化
# 用法：
#   context-init.sh [PROJECT_DIR] [--auto|-y] [--check] [--status]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEMPLATE="${REPO_ROOT}/context/templates/project-context-template.md"
CONVENTIONS_SRC="${REPO_ROOT}/context/conventions.md"
DETECTOR="${SCRIPT_DIR}/detect-project.py"
APPLIER="${SCRIPT_DIR}/apply-context-fields.py"
CONFIRM_MARK="⟨待确认⟩"

# Defaults
PROJECT_DIR="."
MODE="init"  # init | check | status
AUTO_MODE="false"
LEGACY_MODE="false"  # 若为 true，不生成 tasks/ 和 workspace/ 骨架
LINK_MODE="false"    # 若为 true，conventions.md 软链到母仓而非落真实文件
REFRESH_CONVENTIONS="false"  # 若为 true，用母仓那份覆盖项目里已有的 conventions.md

# Parse args
while [ "$#" -gt 0 ]; do
  case "$1" in
    --auto|-y) AUTO_MODE="true"; shift ;;
    --legacy) LEGACY_MODE="true"; shift ;;
    --copy) shift ;;   # 兼容旧参数：复制已是默认行为
    --link) LINK_MODE="true"; shift ;;
    --refresh-conventions) REFRESH_CONVENTIONS="true"; shift ;;
    --check) MODE="check"; shift ;;
    --status) MODE="status"; shift ;;
    --confirm) MODE="confirm"; shift ;;
    --help)
      cat <<'EOF'
用法: context-init.sh [PROJECT_DIR] [--auto|-y] [--link] [--legacy]
                      [--refresh-conventions]
                      [--check] [--status] [--confirm]

模式:
  (default)    初始化项目上下文（创建 .ai-configs/、project-context.md、conventions.md）
               并自动探测项目特征，填入的值标 ⟨待确认⟩ 等人工核对
  --check      校验上下文完整性（exit: 0=完整, 1=缺失/不可达, 2=不完整或未确认）
  --status     显示 .ai-configs/ 目录状态
  --confirm    清除所有 ⟨待确认⟩ 标记，确认探测结果

参数:
  PROJECT_DIR  项目目录（默认当前目录）
  --auto, -y   免确认，探测结果直接落定（CI / 脚本场景）
  --legacy     不生成 tasks/ 和 workspace/ 骨架（仅 ad-hoc 模式）
  --refresh-conventions
               用母仓那份覆盖项目里已有的 conventions.md。默认不覆盖：项目里
               已经有一份就以它为准，因为它可能由别的工具落地或被本项目改过
  --link       conventions.md 软链到母仓而非落真实文件。软链是本机绝对路径，
               同事和 CI clone 下来即断链，因此只适合母仓维护者本人在本机
               调试约定改动的场景，不要用在要提交的项目上
               （--copy 保留为兼容参数，复制已是默认行为）

探测覆盖语言/框架/组件库/状态管理/数据库/构建工具/包管理器/代码风格/
分支策略/提交规范/部署方式/测试栈，并识别 monorepo 逐个子工程列出技术栈。
产品类型、核心业务、目标用户这类语义字段不猜，留 [待填写]。
EOF
      exit 0
      ;;
    -*) echo "未知参数: $1" >&2; exit 1 ;;
    *) PROJECT_DIR="$1"; shift ;;
  esac
done

CONTEXT_FILE="${PROJECT_DIR}/.ai-configs/project-context.md"
AI_CONFIGS_DIR="${PROJECT_DIR}/.ai-configs"
CONVENTIONS_DST="${AI_CONFIGS_DIR}/conventions.md"

# ─── conventions.md 落地（幂等） ───
# 默认落真实文件：产物路径约定是 skill 的运行时事实源，必须随项目走。
# 软链指向本机绝对路径，同事和 CI clone 下来即断链，届时所有 skill 失去路径约定。
ensure_conventions() {
  if [ ! -f "${CONVENTIONS_SRC}" ]; then
    echo "  ⚠️  母仓 conventions.md 不存在: ${CONVENTIONS_SRC}" >&2
    echo "     产物路径约定将无法在本项目解析" >&2
    return
  fi

  if [ "${LINK_MODE}" = "true" ]; then
    if [ -L "${CONVENTIONS_DST}" ] && [ "$(readlink "${CONVENTIONS_DST}")" = "${CONVENTIONS_SRC}" ]; then
      echo "  ✓ conventions.md 软链已就绪（--link，勿提交）"
      return
    fi
    rm -f "${CONVENTIONS_DST}"
    ln -s "${CONVENTIONS_SRC}" "${CONVENTIONS_DST}"
    echo "  ✓ conventions.md 已软链到母仓（--link，勿提交）"
    ignore_symlink
    return
  fi

  # 历史软链就地换成真实文件，并把 .gitignore 里为软链加的豁免撤掉
  if [ -L "${CONVENTIONS_DST}" ]; then
    rm -f "${CONVENTIONS_DST}"
    cp "${CONVENTIONS_SRC}" "${CONVENTIONS_DST}"
    unignore_conventions
    echo "  ✓ conventions.md 已由软链换成真实文件（现在可以提交，同事和 CI 都读得到）"
    return
  fi

  # 项目里已经有一份就以它为准。它可能由别的工具落地，也可能被本项目改过；
  # 无条件覆盖会把这些静默冲掉，而"谁最后跑谁说了算"不是一个能解释的规则。
  if [ -f "${CONVENTIONS_DST}" ]; then
    if [ "${REFRESH_CONVENTIONS}" = "true" ]; then
      report_conventions_diff "将被丢弃的差异"
      cp "${CONVENTIONS_SRC}" "${CONVENTIONS_DST}"
      unignore_conventions
      echo "  ✓ conventions.md 已用母仓那份覆盖（--refresh-conventions）"
    else
      echo "  ⏭  conventions.md 已存在，保持不变（要用母仓那份覆盖：--refresh-conventions）"
      local src_ver dst_ver
      src_ver="$(head -n 1 "${CONVENTIONS_SRC}" | sed -n 's/^<!-- xman-conventions: \([0-9]*\) -->$/\1/p')"
      dst_ver="$(head -n 1 "${CONVENTIONS_DST}" | sed -n 's/^<!-- xman-conventions: \([0-9]*\) -->$/\1/p')"
      if [ -n "${src_ver}" ] && [ "${src_ver}" != "${dst_ver}" ]; then
        echo "  ⚠️  项目里的 conventions.md 版本是 ${dst_ver:-未标记}，母仓是 ${src_ver}：skill 引用的章节可能已经搬走，建议加 --refresh-conventions 刷新"
      fi
      report_conventions_diff "与母仓版本的差异"
    fi
    return
  fi

  cp "${CONVENTIONS_SRC}" "${CONVENTIONS_DST}"
  unignore_conventions
  echo "  ✓ conventions.md 已落地（真实文件，请提交进版本库）"
}

# ─── 差异摘要 ───
# 只报"有几处不同、集中在哪些章节"，不替用户判断谁对。
report_conventions_diff() {
  local label="$1"
  python3 - "${CONVENTIONS_SRC}" "${CONVENTIONS_DST}" "${label}" <<'PY'
import difflib
import pathlib
import sys

src, dst, label = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
a = src.read_text(encoding="utf-8").splitlines()
b = dst.read_text(encoding="utf-8").splitlines()
if a == b:
    print("     内容与母仓一致")
    raise SystemExit(0)

sections, current, changed = [], "（文件开头）", []
line_no = 0
for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
    if tag == "equal":
        continue
    changed.append((tag, j1, j2, i1, i2))

# 用项目那份的标题定位差异落在哪些章节
heads = []
for idx, line in enumerate(b):
    if line.startswith("#"):
        heads.append((idx, line.lstrip("# ").strip()))

def section_of(idx):
    name = "（文件开头）"
    for h_idx, h in heads:
        if h_idx <= idx:
            name = h
        else:
            break
    return name

hit = []
count = 0
for tag, j1, j2, i1, i2 in changed:
    count += max(j2 - j1, i2 - i1)
    name = section_of(j1)
    if name not in hit:
        hit.append(name)

print(f"     {label}：{len(changed)} 处、约 {count} 行，落在 {len(hit)} 个章节")
for name in hit[:5]:
    print(f"       · {name}")
if len(hit) > 5:
    print(f"       · …另有 {len(hit) - 5} 个章节")
PY
}

# ─── 撤掉当初为软链加的 .gitignore 豁免 ───
# 真实文件必须提交：不提交的话同事和 CI 仍然读不到产物路径约定，
# 等于换了种方式回到断链那个状态。
unignore_conventions() {
  local gi="${PROJECT_DIR}/.gitignore"
  [ -f "${gi}" ] || return 0
  grep -qxF ".ai-configs/conventions.md" "${gi}" 2>/dev/null || return 0

  # 用 awk 一次过滤完，不用 grep 管道：过滤后可能一行不剩，grep 此时返回 1，
  # 配合本脚本的 set -euo pipefail 会让整个 init 在这里静默中断，
  # 后面的 project-context.md、tasks/、workspace/ 全都不会生成。
  # 写回用重定向而不是 mv：mv 会把 mktemp 的 0600 权限一起带给 .gitignore。
  local tmp
  tmp=$(mktemp)
  awk '
    $0 == ".ai-configs/conventions.md" { next }
    $0 == "# 指向 x-mansion 母仓的本机绝对路径软链，不可提交" { next }
    { print }
  ' "${gi}" > "${tmp}"
  cat "${tmp}" > "${gi}"
  rm -f "${tmp}"
  echo "  ✓ 已从 .gitignore 移除 .ai-configs/conventions.md（真实文件应当提交）"
}

# ─── 软链必须进 .gitignore ───
# 软链指向本机的母仓绝对路径。.ai-configs/ 在业务项目里是要提交的，
# 若把软链一起提交，同事或 CI clone 下来就是断链——按 cmd_check 的判定
# 这是硬失败，且所有 skill 会失去产物路径约定。
ignore_symlink() {
  local gi="${PROJECT_DIR}/.gitignore"
  local entry=".ai-configs/conventions.md"

  # 已经被忽略就不重复写（含通过通配规则忽略的情况）
  if git -C "${PROJECT_DIR}" check-ignore -q "${entry}" 2>/dev/null; then
    return
  fi

  if [ -f "${gi}" ] && grep -qxF "${entry}" "${gi}" 2>/dev/null; then
    return
  fi

  if [ -f "${gi}" ] && [ -n "$(tail -c 1 "${gi}" 2>/dev/null)" ]; then
    echo "" >> "${gi}"
  fi
  {
    echo "# 指向 x-mansion 母仓的本机绝对路径软链，不可提交"
    echo "${entry}"
  } >> "${gi}"
  echo "  ✓ 已将 ${entry} 加入 .gitignore（软链是本机路径，不能提交）"
}

# ─── 骨架创建（幂等） ───
ensure_skeleton() {
  local CURRENT_YEAR CURRENT_MONTH
  CURRENT_YEAR=$(date +%Y)
  CURRENT_MONTH=$(date +%m)

  echo "确保 .ai-configs/ 骨架（幂等）..."
  mkdir -p "${AI_CONFIGS_DIR}/brainstorm/${CURRENT_YEAR}/${CURRENT_MONTH}"
  mkdir -p "${AI_CONFIGS_DIR}/analysis/${CURRENT_YEAR}/${CURRENT_MONTH}"
  mkdir -p "${AI_CONFIGS_DIR}/prd/${CURRENT_YEAR}/${CURRENT_MONTH}"
  mkdir -p "${AI_CONFIGS_DIR}/design/${CURRENT_YEAR}/${CURRENT_MONTH}"
  mkdir -p "${AI_CONFIGS_DIR}/plan/${CURRENT_YEAR}/${CURRENT_MONTH}"
  mkdir -p "${AI_CONFIGS_DIR}/progress/${CURRENT_YEAR}/${CURRENT_MONTH}"
  echo "  ✓ ad-hoc 目录就绪"

  ensure_conventions

  if [ "${LEGACY_MODE}" = "false" ]; then
    mkdir -p "${AI_CONFIGS_DIR}/tasks/.abandoned"
    [ -f "${AI_CONFIGS_DIR}/tasks/.gitkeep" ] || touch "${AI_CONFIGS_DIR}/tasks/.gitkeep"
    [ -f "${AI_CONFIGS_DIR}/tasks/.abandoned/.gitkeep" ] || touch "${AI_CONFIGS_DIR}/tasks/.abandoned/.gitkeep"

    mkdir -p "${AI_CONFIGS_DIR}/workspace"
    if [ ! -f "${AI_CONFIGS_DIR}/workspace/journal.md" ]; then
      cat > "${AI_CONFIGS_DIR}/workspace/journal.md" <<'JOURNAL_EOF'
# Workspace Journal

跨会话的项目记忆。正序追加，新内容写底部。格式参见 `.ai-configs/conventions.md`。

JOURNAL_EOF
    fi
    echo "  ✓ task 模式骨架就绪（tasks/ + workspace/journal.md）"
  else
    echo "  ⏭  跳过 task 模式骨架（--legacy）"
  fi
}

# ─── 标记计数 ───
# 模板头部的说明是 markdown 引言（以 > 开头），里面字面写了这三种标记，
# 必须排除，否则永远多算一项、confirm 还会把说明本身改掉。
# 统计真实标记数。必须排除两类说明性文本，它们会字面提到这些标记：
#   1. > 开头的引言块（模板头部的标记说明）
#   2. <!-- --> 注释块（跨行，所以不能用 grep 逐行过滤）
# 用 python 而不是 grep：既要剥跨行注释，又要按字面量而非正则匹配
# （"[待填写]" 在正则里是字符类，会匹配任何含 待/填/写 的行）。
count_mark() {
  local file="$1" pat="$2"
  [ -f "${file}" ] || { echo 0; return; }
  MARK_FILE="${file}" MARK_PAT="${pat}" python3 - <<'PY'
import os, re
text = open(os.environ["MARK_FILE"], encoding="utf-8").read()
text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
lines = [l for l in text.split("\n") if not l.startswith(">")]
print(sum(l.count(os.environ["MARK_PAT"]) for l in lines))
PY
}

# ─── conventions.md 可达性判定 ───
# 回显: ok-link | ok-copy | broken | missing
conventions_state() {
  if [ -L "${CONVENTIONS_DST}" ]; then
    [ -r "${CONVENTIONS_DST}" ] && echo "ok-link" || echo "broken"
  elif [ -f "${CONVENTIONS_DST}" ]; then
    echo "ok-copy"
  else
    echo "missing"
  fi
}

# ─── 自动探测 + 写入（默认标 ⟨待确认⟩，--auto 直接落定） ───
run_detection() {
  # 两个脚本缺任何一个都跳过——不能建完骨架再中途炸掉
  if [ ! -f "${DETECTOR}" ] || [ ! -f "${APPLIER}" ]; then
    echo ""
    echo "⚠️  探测脚本缺失（${DETECTOR} / ${APPLIER}），跳过自动探测" >&2
    return
  fi

  echo ""
  echo "探测项目特征..."

  local tsv
  tsv=$(mktemp)
  if ! python3 "${DETECTOR}" "${PROJECT_DIR}" > "${tsv}" 2>/dev/null; then
    echo "  ⚠️  探测失败，跳过（可手工填写 ${CONTEXT_FILE}）" >&2
    rm -f "${tsv}"
    return
  fi

  local archetype
  archetype=$(grep '^__archetype__' "${tsv}" | cut -f2)
  echo "  📐 项目形态: ${archetype:-unknown}"

  # 形态 → 不适用字段（避免让后端项目填主色调、前端项目填数据库）
  local na_fields=""
  case "${archetype}" in
    backend|cli|library)
      na_fields="前端框架,UI 组件库,状态管理,设计系统,主色调,字体,响应式断点" ;;
    frontend)
      na_fields="后端框架,数据库" ;;
    mobile)
      na_fields="后端框架,数据库,响应式断点" ;;
    *)
      na_fields="" ;;
  esac

  local mark=""
  [ "${AUTO_MODE}" = "false" ] && mark="${CONFIRM_MARK}"

  # 回写失败不应让整个 init 挂掉（骨架和 conventions.md 已经建好了）
  if ! CONTEXT_FILE="${CONTEXT_FILE}" NA_FIELDS="${na_fields}" MARK="${mark}" \
       python3 "${APPLIER}" "${tsv}"; then
    echo "  ⚠️  回写失败，字段保持 [待填写]（可手工编辑 ${CONTEXT_FILE}）" >&2
  fi

  rm -f "${tsv}"
}

# ─── confirm 模式：清除 ⟨待确认⟩ 标记 ───
cmd_confirm() {
  if [ ! -f "${CONTEXT_FILE}" ]; then
    echo "❌ project-context.md 不存在，先运行 'xman context init'" >&2
    exit 1
  fi

  local n
  n=$(count_mark "${CONTEXT_FILE}" "${CONFIRM_MARK}")
  if [ "${n}" -eq 0 ]; then
    echo "✅ 无待确认字段"
    exit 0
  fi

  # 用 python 做替换，避免 ⟨⟩ 在 sed 里的编码问题。
  # 跳过 > 开头的引言行——那是模板说明，字面提到标记本身，不能被改掉。
  CONTEXT_FILE="${CONTEXT_FILE}" MARK="${CONFIRM_MARK}" python3 - <<'PY'
import os
path = os.environ["CONTEXT_FILE"]
mark = os.environ["MARK"]
with open(path, encoding="utf-8") as fh:
    lines = fh.readlines()
out = []
for line in lines:
    if not line.startswith(">"):
        line = line.replace(" " + mark, "").replace(mark, "")
    out.append(line)
with open(path, "w", encoding="utf-8") as fh:
    fh.writelines(out)
PY

  echo "✅ 已确认 ${n} 项探测结果"
  local left
  left=$(count_mark "${CONTEXT_FILE}" "[待填写]")
  [ "${left}" -gt 0 ] && echo "   仍有 ${left} 个 [待填写] 字段需要补齐"
  exit 0
}

# ─── check 模式 ───
cmd_check() {
  local rc=0

  # conventions.md 可达性 —— 不可达则产物路径约定无从解析，视为硬失败
  case "$(conventions_state)" in
    ok-copy) echo "✅ conventions.md 可达（项目内真实文件）" ;;
    ok-link) echo "⚠️  conventions.md 可达，但是软链 → 母仓；同事和 CI clone 下来会断链，建议重跑 xman context init 换成真实文件" ;;
    broken)
      echo "❌ conventions.md 软链已断（指向 $(readlink "${CONVENTIONS_DST}")）"
      echo "   产物路径约定无法解析，skill 将各自为政落盘"
      echo "   若本机有 x-mansion：xman context init ${PROJECT_DIR}"
      echo "   重跑 xman context init ${PROJECT_DIR} 即可落一份真实文件"
      rc=1
      ;;
    missing)
      echo "❌ conventions.md 不存在"
      echo "   产物路径约定无法解析，skill 将各自为政落盘"
      echo "   修复: xman context init ${PROJECT_DIR}"
      rc=1
      ;;
  esac

  if [ ! -f "${CONTEXT_FILE}" ]; then
    echo "❌ project-context.md 不存在"
    echo "   运行 'xman context init' 初始化"
    exit 1
  fi

  local pending
  pending=$(count_mark "${CONTEXT_FILE}" "${CONFIRM_MARK}")

  if [ "$(count_mark "${CONTEXT_FILE}" "[待填写]")" -gt 0 ]; then
    local count
    count=$(count_mark "${CONTEXT_FILE}" "[待填写]")
    echo "⚠️  project-context.md 不完整（${count} 个待填写字段）"
    [ "${pending}" -gt 0 ] && echo "   另有 ${pending} 项探测结果待确认"
    [ "${rc}" -eq 0 ] && exit 2 || exit 1
  fi

  if [ "${pending}" -gt 0 ]; then
    echo "⚠️  ${pending} 项自动探测结果未确认"
    echo "   核对后运行 'xman context confirm ${PROJECT_DIR}'"
    [ "${rc}" -eq 0 ] && exit 2 || exit 1
  fi

  echo "✅ project-context.md 已完整"
  exit "${rc}"
}

# ─── status 模式 ───
cmd_status() {
  echo "=== 项目上下文状态 ==="
  echo ""

  if [ ! -d "${AI_CONFIGS_DIR}" ]; then
    echo "❌ .ai-configs/ 目录不存在"
    echo "   运行 'xman context init' 初始化"
    return
  fi

  # conventions.md 状态
  case "$(conventions_state)" in
    ok-copy) echo "📐 conventions.md:   ✅ 项目内真实文件（母仓更新后重跑 init 刷新）" ;;
    ok-link) echo "📐 conventions.md:   ⚠️  软链 → $(readlink "${CONVENTIONS_DST}")（本机路径，不可提交）" ;;
    broken)  echo "📐 conventions.md:   ❌ 软链已断 → $(readlink "${CONVENTIONS_DST}")" ;;
    missing) echo "📐 conventions.md:   ❌ 不存在（产物路径约定无法解析）" ;;
  esac

  # project-context.md 状态
  if [ ! -f "${CONTEXT_FILE}" ]; then
    echo "📋 project-context.md: ❌ 不存在"
  else
    local todo pending na
    todo=$(count_mark "${CONTEXT_FILE}" "[待填写]")
    pending=$(count_mark "${CONTEXT_FILE}" "${CONFIRM_MARK}")
    na=$(count_mark "${CONTEXT_FILE}" "[不适用]")
    if [ "${todo}" -gt 0 ] || [ "${pending}" -gt 0 ]; then
      echo "📋 project-context.md: ⚠️  待填写 ${todo} / 待确认 ${pending} / 不适用 ${na}"
    else
      echo "📋 project-context.md: ✅ 完整（不适用 ${na} 项）"
    fi
  fi

  echo ""
  echo "📁 产物目录:"

  local dirs=("brainstorm" "analysis" "prd" "design" "plan" "progress")
  for dir in "${dirs[@]}"; do
    local full_path="${AI_CONFIGS_DIR}/${dir}"
    if [ -d "${full_path}" ]; then
      local count
      count=$(find "${full_path}" -name "*.md" -type f 2>/dev/null | wc -l | tr -d ' ')
      echo "   ${dir}/: ${count} 个文档"
    else
      echo "   ${dir}/: (未创建)"
    fi
  done

  echo ""
  echo "🎯 Task 模式:"
  local tasks_dir="${AI_CONFIGS_DIR}/tasks"
  if [ -d "${tasks_dir}" ]; then
    local task_count
    task_count=$(find "${tasks_dir}" -mindepth 1 -maxdepth 1 -type d ! -name '.abandoned' 2>/dev/null | wc -l | tr -d ' ')
    echo "   tasks/: ${task_count} 个 task"
    if [ -d "${tasks_dir}/.abandoned" ]; then
      local abandoned_count
      abandoned_count=$(find "${tasks_dir}/.abandoned" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
      echo "   tasks/.abandoned/: ${abandoned_count} 个废弃"
    fi
  else
    echo "   tasks/: (未创建，运行 'xman context init' 补骨架)"
  fi

  local current_file="${AI_CONFIGS_DIR}/.current-task"
  if [ -f "${current_file}" ]; then
    local current
    current=$(cat "${current_file}")
    echo "   当前 task: ${current}"
  else
    echo "   当前 task: (未设置)"
  fi

  echo ""
  echo "📓 Workspace:"
  local journal="${AI_CONFIGS_DIR}/workspace/journal.md"
  if [ -f "${journal}" ]; then
    local lines
    lines=$(wc -l < "${journal}" | tr -d ' ')
    echo "   journal.md: ${lines} 行"
  else
    echo "   journal.md: (未创建)"
  fi
}

# ─── init 模式 ───
cmd_init() {
  echo "=== 初始化项目上下文 ==="
  echo ""

  # 检查模板
  if [ ! -f "${TEMPLATE}" ]; then
    echo "❌ 模板文件不存在: ${TEMPLATE}" >&2
    exit 1
  fi

  # 创建目录结构
  local CURRENT_YEAR CURRENT_MONTH
  CURRENT_YEAR=$(date +%Y)
  CURRENT_MONTH=$(date +%m)

  # 骨架创建是幂等的，无论 project-context.md 是否已存在都会执行
  # （让老项目跑 'xman context init' 也能补出 task/workspace 骨架）
  ensure_skeleton

  # 检查是否已存在
  if [ -f "${CONTEXT_FILE}" ]; then
    if [ "$(count_mark "${CONTEXT_FILE}" "[待填写]")" -gt 0 ]; then
      local count
      count=$(count_mark "${CONTEXT_FILE}" "[待填写]")
      echo ""
      echo "⚠️  project-context.md 已存在但不完整（${count} 个待填写字段）"
      echo "   尝试自动补全（只填 [待填写] 的字段，已填内容不覆盖）..."
    else
      echo ""
      echo "✅ project-context.md 已存在且完整（骨架已确保）"
      echo "   如需修改，直接编辑 ${CONTEXT_FILE}"
      return
    fi
  else
    echo ""
    echo "创建 project-context.md..."
    cp "${TEMPLATE}" "${CONTEXT_FILE}"
    echo "  ✓ 模板已复制"
  fi

  # ─── 自动探测（默认执行；--auto 表示免确认） ───
  run_detection

  echo ""
  echo "✅ 初始化完成"
  echo ""
  echo "下一步："
  local pending
  pending=$(count_mark "${CONTEXT_FILE}" "${CONFIRM_MARK}")
  if [ "${pending}" -gt 0 ]; then
    echo "  1. 核对上面 ${pending} 项探测结果（有错就直接编辑 ${CONTEXT_FILE}）"
    echo "  2. 确认无误后运行 'xman context confirm ${PROJECT_DIR}'"
    echo "  3. 补齐剩余 [待填写] 字段（语义类字段需读代码，脚本填不了）"
  else
    echo "  1. 补齐剩余 [待填写] 字段"
  fi
  echo "  运行 'xman context check' 校验完整性"
}

# ─── 主路由 ───
case "${MODE}" in
  check) cmd_check ;;
  status) cmd_status ;;
  confirm) cmd_confirm ;;
  init) cmd_init ;;
esac
