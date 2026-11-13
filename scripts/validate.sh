#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKILLS_ROOT="${REPO_ROOT}/skills"
AGENTS_ROOT="${REPO_ROOT}/agents"
TEAM_ROOT="${REPO_ROOT}/team/skills"
PLUGINS_ROOT="${REPO_ROOT}/plugins"
REGISTRY_FILE="${REPO_ROOT}/governance/skills-registry.csv"
SOURCES_ROOT="${REPO_ROOT}/governance/sources"

FIX_MODE="false"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --fix) FIX_MODE="true"; shift ;;
    --help)
      echo "用法: validate.sh [--fix]"
      echo "  --fix  自动修复可修复的问题（team 软链、CSV 排序）"
      exit 0
      ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

pass=0
fail=0
warnings=0

pass_msg() {
  echo "  ✓ $1"
  pass=$((pass + 1))
}

fail_msg() {
  echo "  ✗ $1"
  fail=$((fail + 1))
}

warn_msg() {
  echo "  ⚠ $1"
  warnings=$((warnings + 1))
}

# agent 定义必须是扁平的 agents/<name>.md：埋成 agents/<name>/AGENT.md 时，
# plugin 的组件清单一条都收不到，这个 agent 通过 plugin 分发时等于不存在，
# 而安装过程不会报任何错。判据要求首行是 ---，且 name: 在 front-matter 块内，
# 否则 README.md 代码示例里的 name: 会被误判成 agent。
is_agent_definition() {
  local file="$1"
  [ -f "${file}" ] || return 1
  [ "$(head -1 "${file}")" = "---" ] || return 1
  awk 'NR==1{next} /^---[[:space:]]*$/{exit 1} /^name:/{exit 0}' "${file}"
}

agent_names() {
  [ -d "${AGENTS_ROOT}" ] || return 0
  find "${AGENTS_ROOT}" -mindepth 1 -maxdepth 1 -name '*.md' -print \
    | while IFS= read -r f; do
        is_agent_definition "${f}" || continue
        basename "${f}" .md
      done | sort
}

echo "=== x-mansion Skill 仓库校验 ==="
echo ""

# ─── 1. 检查每个 skill 和 agent 定义都存在 ───
echo "1. Skill / Agent 定义存在性检查"
for skill_dir in "${SKILLS_ROOT}"/*/; do
  skill_name="$(basename "${skill_dir}")"
  if [ -f "${skill_dir}/SKILL.md" ]; then
    pass_msg "${skill_name}/SKILL.md"
  else
    fail_msg "${skill_name}/SKILL.md 不存在"
  fi
done
if [ -d "${AGENTS_ROOT}" ]; then
  while IFS= read -r agent_name; do
    [ -n "${agent_name}" ] || continue
    pass_msg "agents/${agent_name}.md"
  done < <(agent_names)
  # 埋在目录里的定义收不到，必须挡住
  while IFS= read -r buried; do
    [ -n "${buried}" ] || continue
    fail_msg "${buried#${REPO_ROOT}/} 埋在目录里，plugin 分发时收不到；应移到 agents/<name>.md"
  done < <(find "${AGENTS_ROOT}" -mindepth 2 -maxdepth 2 -name 'AGENT.md' 2>/dev/null)
fi
echo ""

# ─── 2. 检查 front-matter 必填字段 ───
echo "2. Front-matter 必填字段检查 (name, description)"

check_frontmatter() {
  local md_file="$1" label="$2"
  [ -f "${md_file}" ] || return

  local has_name=false has_desc=false in_frontmatter=false
  while IFS= read -r line; do
    if [ "${line}" = "---" ]; then
      if [ "${in_frontmatter}" = "true" ]; then break; else in_frontmatter=true; continue; fi
    fi
    if [ "${in_frontmatter}" = "true" ]; then
      case "${line}" in
        name:*) has_name=true ;;
        description:*) has_desc=true ;;
      esac
    fi
  done < "${md_file}"

  if [ "${has_name}" = "true" ] && [ "${has_desc}" = "true" ]; then
    pass_msg "${label}: name + description"
  else
    [ "${has_name}" = "false" ] && fail_msg "${label}: 缺少 name"
    [ "${has_desc}" = "false" ] && fail_msg "${label}: 缺少 description"
  fi
}

for skill_dir in "${SKILLS_ROOT}"/*/; do
  check_frontmatter "${skill_dir}/SKILL.md" "$(basename "${skill_dir}")"
done
if [ -d "${AGENTS_ROOT}" ]; then
  while IFS= read -r agent_name; do
    [ -n "${agent_name}" ] || continue
    check_frontmatter "${AGENTS_ROOT}/${agent_name}.md" "agents/${agent_name}.md"
  done < <(agent_names)
fi
echo ""

# ─── 3. CSV ↔ skills/ + agents/ 双向一致性 ───
echo "3. CSV ↔ skills/ + agents/ 双向一致性"
optional_missing_skills=""
if [ ! -f "${REGISTRY_FILE}" ]; then
  fail_msg "skills-registry.csv 不存在"
else
  optional_missing_skills="$(python3 - "${REPO_ROOT}" "${REGISTRY_FILE}" <<'PY'
import csv
from pathlib import Path
import sys

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "scripts"))
from registry_scope import optional_missing_skills

with Path(sys.argv[2]).open(newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
print("\n".join(sorted(optional_missing_skills(repo, rows))))
PY
)"
  # 从 CSV 获取 type=skill（或空）的条目名
  csv_skills="$(tail -n +2 "${REGISTRY_FILE}" | awk -F',' '$7=="" || $7=="skill" {print $1}' | sort)"
  # 从 CSV 获取 type=agent 的条目名
  csv_agents="$(tail -n +2 "${REGISTRY_FILE}" | awk -F',' '$7=="agent" {print $1}' | sort)"
  # 从 CSV 获取 type=deprecated 的条目名（跳过存在性检查）
  csv_deprecated="$(tail -n +2 "${REGISTRY_FILE}" | awk -F',' '$7=="deprecated" {print $1}' | sort)"

  # 从 skills/ 获取所有目录名
  dir_skills="$(find "${SKILLS_ROOT}" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)"

  # 从 agents/ 获取所有目录名
  dir_agents="$(agent_names)"

  # Skill: 在 CSV 中但不在 skills/ 中
  while IFS= read -r skill; do
    [ -n "${skill}" ] || continue
    if printf '%s\n' "${optional_missing_skills}" | grep -Fxq -- "${skill}"; then
      pass_msg "本地个人 skill '${skill}' 未提供，按根 .gitignore 声明允许缺省"
    else
      fail_msg "CSV 中有 '${skill}' (type=skill) 但 skills/ 中不存在"
    fi
  done < <(comm -23 <(echo "${csv_skills}") <(echo "${dir_skills}"))

  # Skill: 在 skills/ 中但不在 CSV 中
  while IFS= read -r skill; do
    [ -n "${skill}" ] || continue
    fail_msg "skills/ 中有 '${skill}' 但 CSV 中未注册"
  done < <(comm -13 <(echo "${csv_skills}") <(echo "${dir_skills}"))

  # Skill 一致的
  consistent="$(comm -12 <(echo "${csv_skills}") <(echo "${dir_skills}") | wc -l | tr -d ' ')"
  [ "${consistent}" -gt 0 ] && pass_msg "${consistent} 个 skill CSV 与目录一致"

  # Agent: 在 CSV 中但不在 agents/ 中
  while IFS= read -r agent; do
    [ -n "${agent}" ] || continue
    fail_msg "CSV 中有 '${agent}' (type=agent) 但 agents/ 中不存在"
  done < <(comm -23 <(echo "${csv_agents}") <(echo "${dir_agents}"))

  # Agent: 在 agents/ 中但不在 CSV 中
  while IFS= read -r agent; do
    [ -n "${agent}" ] || continue
    fail_msg "agents/ 中有 '${agent}' 但 CSV 中未注册为 agent"
  done < <(comm -13 <(echo "${csv_agents}") <(echo "${dir_agents}"))

  # Agent 一致的
  if [ -n "${dir_agents}" ]; then
    consistent_agents="$(comm -12 <(echo "${csv_agents}") <(echo "${dir_agents}") | wc -l | tr -d ' ')"
    [ "${consistent_agents}" -gt 0 ] && pass_msg "${consistent_agents} 个 agent CSV 与目录一致"
  fi

  # Deprecated 提示
  if [ -n "${csv_deprecated}" ]; then
    dep_count="$(echo "${csv_deprecated}" | wc -l | tr -d ' ')"
    pass_msg "${dep_count} 个 deprecated 条目已跳过检查"
  fi
fi
echo ""

# ─── 3.5. CSV 字母排序检查 ───
echo "3.5. CSV skill 字段字母排序检查"
if [ -f "${REGISTRY_FILE}" ]; then
  if tail -n +2 "${REGISTRY_FILE}" | cut -d',' -f1 | sort -c 2>/dev/null; then
    pass_msg "CSV 按字母排序"
  else
    fail_msg "CSV 未按字母排序"
    if [ "${FIX_MODE}" = "true" ]; then
      python3 - "${REGISTRY_FILE}" <<'PY'
import csv, pathlib, sys
path = pathlib.Path(sys.argv[1])
with path.open(newline="") as fh:
    reader = csv.DictReader(fh)
    fieldnames = reader.fieldnames
    rows = sorted(reader, key=lambda r: r["skill"])
with path.open("w", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
PY
      echo "  → 已重排 CSV"
    fi
  fi
fi
echo ""

# ─── 3.55. release 列（晋升到发行版）检查 ───
echo "3.55. 发行版晋升标记检查"
if [ -f "${REGISTRY_FILE}" ]; then
  release_report="$(python3 - "${REGISTRY_FILE}" <<'PY'
import csv, pathlib, sys

ALLOWED = {"", "release-dist"}
path = pathlib.Path(sys.argv[1])
with path.open(newline="", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))

if "release" not in (rows[0].keys() if rows else {}):
    print("FAIL\tregistry 缺少 release 列")
    raise SystemExit(0)

bad = [r["skill"] for r in rows if (r.get("release") or "").strip() not in ALLOWED]
for skill in bad:
    print(f"FAIL\t{skill}: release 取值非法（只能为空或 release-dist）")

# 已废弃的 skill 不该还挂在发行版上：使用者会继续拿到它
zombie = [r["skill"] for r in rows
          if (r.get("release") or "").strip() and r.get("status") == "deprecated"]
for skill in zombie:
    print(f"FAIL\t{skill}: 已 deprecated 却仍标记为已晋升发行版")

released = [r for r in rows if (r.get("release") or "").strip()]
print(f"OK\t{len(released)} 个 skill 在发行版里有同名的一份，双装 plugin 时用 ./xman plugin takeover 统一到本仓")
PY
)"
  while IFS=$'\t' read -r verdict message; do
    [ -n "${verdict}" ] || continue
    if [ "${verdict}" = "OK" ]; then pass_msg "${message}"; else fail_msg "${message}"; fi
  done <<< "${release_report}"
fi
echo ""

# ─── 3.6. 外部来源 manifest 检查 ───
echo "3.6. 外部来源 manifest 检查"
manifest_check_output=""
if [ -f "${REGISTRY_FILE}" ]; then
  manifest_check_output="$(python3 - "${REGISTRY_FILE}" "${SOURCES_ROOT}" <<'PY'
import csv
import json
import pathlib
import sys

registry = pathlib.Path(sys.argv[1])
sources_root = pathlib.Path(sys.argv[2])
failures = []
passes = []

with registry.open(newline="", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))

for row in rows:
    skill = row["skill"]
    source_type = (row.get("source_type") or "local").strip() or "local"
    source_key = (row.get("source_key") or "").strip()

    if source_type not in {"local", "external"}:
      failures.append(f"{skill}: source_type 非法（{source_type}）")
      continue

    if source_type == "external":
      if not source_key:
        failures.append(f"{skill}: external 缺少 source_key")
        continue
      manifest = sources_root / f"{source_key}.json"
      if not manifest.exists():
        failures.append(f"{skill}: 缺少 manifest {manifest.name}")
        continue
      try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
      except json.JSONDecodeError as exc:
        failures.append(f"{skill}: manifest JSON 非法（{exc}）")
        continue
      if not data.get("repo"):
        failures.append(f"{skill}: manifest 缺少 repo")
        continue
      if not isinstance(data.get("mappings"), list) or not data["mappings"]:
        failures.append(f"{skill}: manifest 缺少 mappings")
        continue
      passes.append(f"{skill}: {manifest.name}")

if failures:
    for item in failures:
        print(f"FAIL::{item}")
else:
    for item in passes:
        print(f"PASS::{item}")
PY
)"
else
  manifest_check_output="FAIL::skills-registry.csv 不存在，无法校验外部来源"
fi
while IFS= read -r line; do
  case "${line}" in
    PASS::*)
      pass_msg "${line#PASS::}"
      ;;
    FAIL::*)
      fail_msg "${line#FAIL::}"
      ;;
  esac
done <<< "${manifest_check_output}"
echo ""

# ─── 4. team/skills/ 软链 vs CSV team-shared ───
echo "4. team/skills/ 软链 vs CSV team-shared 一致性"
if [ -d "${TEAM_ROOT}" ] && [ -f "${REGISTRY_FILE}" ]; then
  # 从 CSV 获取 team-shared skills
  csv_team="$(tail -n +2 "${REGISTRY_FILE}" | awk -F',' '$2=="team-shared" {print $1}' | sort)"
  # 从 team/skills/ 获取软链
  link_team="$(find "${TEAM_ROOT}" -mindepth 1 -maxdepth 1 \( -type l -o -type d \) -exec basename {} \; | sort)"

  # CSV team-shared 但没有软链
  while IFS= read -r skill; do
    [ -n "${skill}" ] || continue
    warn_msg "CSV team-shared '${skill}' 但 team/skills/ 中无软链"
  done < <(comm -23 <(echo "${csv_team}") <(echo "${link_team}"))

  # 有软链但不在 CSV team-shared 中
  while IFS= read -r skill; do
    [ -n "${skill}" ] || continue
    warn_msg "team/skills/ 有 '${skill}' 但 CSV 状态不是 team-shared"
  done < <(comm -13 <(echo "${csv_team}") <(echo "${link_team}"))

  consistent="$(comm -12 <(echo "${csv_team}") <(echo "${link_team}") | wc -l | tr -d ' ')"
  [ "${consistent}" -gt 0 ] && pass_msg "${consistent} 个 team 软链与 CSV 一致"

  # --fix: 自动修复 team 软链
  if [ "${FIX_MODE}" = "true" ]; then
    # 创建缺失的 team 软链
    while IFS= read -r skill; do
      [ -n "${skill}" ] || continue
      if [ -d "${SKILLS_ROOT}/${skill}" ] && [ ! -e "${TEAM_ROOT}/${skill}" ]; then
        ln -s "../../skills/${skill}" "${TEAM_ROOT}/${skill}"
        echo "  → 已创建 team 软链: ${skill}"
      fi
    done < <(comm -23 <(echo "${csv_team}") <(echo "${link_team}"))

    # 删除多余的 team 软链
    while IFS= read -r skill; do
      [ -n "${skill}" ] || continue
      if [ -L "${TEAM_ROOT}/${skill}" ]; then
        rm "${TEAM_ROOT}/${skill}"
        echo "  → 已删除多余 team 软链: ${skill}"
      fi
    done < <(comm -13 <(echo "${csv_team}") <(echo "${link_team}"))
  fi
fi
echo ""

# ─── 5. plugins/ 软链有效性 ───
echo "5. plugins/ 软链有效性"
if [ -d "${PLUGINS_ROOT}" ]; then
  broken=0
  valid=0
  while IFS= read -r link; do
    if [ ! -e "${link}" ]; then
      if python3 - "${REPO_ROOT}" "${link}" "${optional_missing_skills}" <<'PY'
from pathlib import Path
import sys

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "scripts"))
from registry_scope import optional_missing_link

raise SystemExit(0 if optional_missing_link(repo, Path(sys.argv[2]), set(sys.argv[3].splitlines())) else 1)
PY
      then
        pass_msg "分类软链 ${link#${REPO_ROOT}/} 指向未提供的本地个人 skill，允许保留"
      else
        fail_msg "断链: ${link}"
        broken=$((broken + 1))
      fi
    else
      valid=$((valid + 1))
    fi
  done < <(find "${PLUGINS_ROOT}" -type l)
  [ "${valid}" -gt 0 ] && pass_msg "${valid} 个 plugin 软链有效"
fi
echo ""

# ─── 5.5. 新增 plugins/team 软链来源弱提醒 ───
echo "5.5. 新增 plugins/team 软链来源提示"
if command -v git >/dev/null 2>&1 && git -C "${REPO_ROOT}" rev-parse --git-dir >/dev/null 2>&1; then
  untracked_links="$(git -C "${REPO_ROOT}" status --porcelain 2>/dev/null \
    | { grep -E '^\?\? (plugins/[^/]+/[^/]+|team/skills/[^/]+)/?$' || true; } \
    | sed -E 's|^\?\? ||; s|/$||')"
  if [ -n "${untracked_links}" ]; then
    warn_msg "检测到未跟踪的 plugins/team 软链——若手动 ln -s 建议改用 ./xman new <name> --plugin <group>"
    echo "      参考: .ai-configs/evolution/patterns/skill-integration-symlink.md"
    while IFS= read -r link; do
      [ -n "${link}" ] || continue
      echo "        - ${link}"
    done <<< "${untracked_links}"
  else
    pass_msg "无新增软链待提示"
  fi
else
  pass_msg "非 git 仓库或 git 不可用，跳过"
fi
echo ""

# ─── 6. .ai-configs/tasks/ 结构校验（仅母仓库自检） ───
# 注意：此步只校验 x-mansion 母仓库自身的 .ai-configs/tasks/，
# 业务项目的 task 校验请用 'xman context check' / 'xman context status'
TASKS_DIR="${REPO_ROOT}/.ai-configs/tasks"
if [ -d "${TASKS_DIR}" ]; then
  echo "6. 母仓库自检：.ai-configs/tasks/ 结构"
  task_ok=0
  task_warn=0
  for task_dir in "${TASKS_DIR}"/*/; do
    [ -d "${task_dir}" ] || continue
    name=$(basename "${task_dir}")
    [ "${name}" = ".abandoned" ] && continue
    [ "${name}" = "*" ] && continue

    meta="${task_dir}meta.yml"
    if [ ! -f "${meta}" ]; then
      warn_msg "task ${name} 缺少 meta.yml"
      task_warn=$((task_warn + 1))
      continue
    fi
    # 校验 4 个必需字段
    missing=""
    for field in title stage tags links; do
      grep -qE "^${field}:" "${meta}" || missing="${missing} ${field}"
    done
    if [ -n "${missing}" ]; then
      warn_msg "task ${name} meta.yml 缺字段:${missing}"
      task_warn=$((task_warn + 1))
      continue
    fi
    # 校验 stage 合法值
    stage_val=$(grep -E '^stage:' "${meta}" | head -1 | sed 's/^stage: *//')
    case "${stage_val}" in
      in_progress|done|abandoned) task_ok=$((task_ok + 1)) ;;
      *) warn_msg "task ${name} stage 非法: ${stage_val} (允许: in_progress/done/abandoned)"; task_warn=$((task_warn + 1)) ;;
    esac
  done
  [ "${task_ok}" -gt 0 ] && pass_msg "${task_ok} 个 task 结构正确"
  echo ""
fi

# ─── 7. 平台专属路径硬编码审计 ───
echo "7. 平台路径硬编码审计"
platform_audit_output="$(python3 - "${REPO_ROOT}" <<'PY'
from __future__ import annotations

import pathlib
import re
import sys

repo = pathlib.Path(sys.argv[1])
patterns = [
    re.compile(r"~/\.claude/skills"),
    re.compile(r"~/\.claude/agents"),
    re.compile(r"~/\.claude-commands"),
    re.compile(r"\.claude/commands"),
    re.compile(r"~/\.codex/skills"),
    re.compile(r"~/\.codex/agents"),
    re.compile(r"~/\.cursor/skills"),
    re.compile(r"~/\.cursor/agents"),
    re.compile(r"~/\.gemini/skills"),
    re.compile(r"~/\.gemini/agents"),
]

allowed_exact = {
    "context/platforms.md",
    # 跨平台 agent/skill 路径速查表，用途即枚举各平台专属路径，等同 platforms.md
    "skills/neat-freak/references/agent-paths.md",
    # 外部 skill-creator 的评测器通过 claude -p 验证 Claude 触发行为，本身即平台适配器
    "skills/skill-creator/scripts/run_eval.py",
}

allowed_prefixes = (
    "archive/",
    "scripts/sync-",
    "scripts/audit-sync.sh",
    "scripts/validate.sh",
    "dev-flow-workspace/",
)

allowed_external_readmes = {
    # 上游仓库原版文档，按 context/platforms.md 允许保留原始平台路径
    "skills/web-access/README.md",
    "skills/web-access/references/cdp-api.md",
}

scan_roots = [
    repo / "README.md",
    repo / "QUICKSTART.md",
    repo / "docs",
    repo / "context",
    repo / "skills",
    repo / "agents",
    repo / "scripts",
]

def is_allowed(rel: str) -> bool:
    return (
        rel in allowed_exact
        or rel in allowed_external_readmes
        or any(rel.startswith(prefix) for prefix in allowed_prefixes)
    )

findings: list[str] = []
for root in scan_roots:
    if root.is_file():
        files = [root]
    elif root.is_dir():
        files = [path for path in root.rglob("*") if path.is_file()]
    else:
        continue

    for path in files:
        rel = path.relative_to(repo).as_posix()
        if is_allowed(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in patterns):
                findings.append(f"{rel}:{lineno}: {line.strip()}")

if findings:
    for finding in findings:
        print(f"FAIL::{finding}")
else:
    print("PASS::活跃文档未发现平台专属路径硬编码")
PY
)"
while IFS= read -r line; do
  case "${line}" in
    PASS::*)
      pass_msg "${line#PASS::}"
      ;;
    FAIL::*)
      fail_msg "平台路径硬编码: ${line#FAIL::}"
      ;;
  esac
done <<< "${platform_audit_output}"
echo ""

# ─── 8. Spec 索引契约 ───
echo "8. Spec 索引契约"
if spec_output="$(python3 "${SCRIPT_DIR}/spec.py" validate --project "${REPO_ROOT}" 2>&1)"; then
  pass_msg "${spec_output}"
else
  fail_msg "${spec_output}"
fi
if conventions_output="$(python3 "${SCRIPT_DIR}/check-conventions.py" 2>&1)"; then
  pass_msg "${conventions_output}"
else
  fail_msg "${conventions_output}"
fi
echo ""

# ─── 9. 本地 plugin 产物 ───
echo "9. 本地 plugin 产物"
if plugin_output="$("${SCRIPT_DIR}/build-plugin.sh" --check 2>&1)"; then
  pass_msg "${plugin_output}"
else
  fail_msg "${plugin_output}"
fi
echo ""

# ─── 10. 跨仓流程骨架漂移（仅在本机配置了发行版仓库时运行）───
# 未配置时整节不输出：本仓不假设另一个仓库存在，连"未检测到"这类反向暗示也不打。
# 两份编排器绑定不同运行时，内容本来就该不同，所以这里是警告不是失败——
# 每条差异该由哪边跟进，需要人工判断。
if drift_output="$(python3 "${SCRIPT_DIR}/check-flow-drift.py" 2>&1)" && [ -z "${drift_output}" ]; then
  :
else
  echo "10. 跨仓流程骨架漂移"
  if [ -z "${drift_output}" ]; then
    :
  else
    # 首行形如 "OK<TAB>…" 或 "DRIFT<TAB>…"，判定标记交给 pass_msg / warn_msg 去渲染
    drift_verdict="${drift_output%%$'\t'*}"
    drift_body="$(printf '%s' "${drift_output}" | sed "1s/^[A-Z]*$(printf '\t')//")"
    if [ "${drift_verdict}" = "OK" ]; then
      pass_msg "${drift_body}"
    else
      warn_msg "${drift_body}"
    fi
  fi
  echo ""
fi

# ─── 11. 跨仓同名 skill 漂移（仅在本机配置了发行版仓库时运行）───
# 同上：未配置时整节不输出。同名 skill 是同一能力的两份文本，判据类改动必须两边都落，
# 但宿主绑定的差异（命令名、约定兜底段落）是有意的，已记进 skill-drift-baseline.tsv。
if skill_drift_output="$(python3 "${SCRIPT_DIR}/check-skill-drift.py" 2>&1)" && [ -z "${skill_drift_output}" ]; then
  :
else
  echo "11. 跨仓同名 skill 漂移"
  if [ -z "${skill_drift_output}" ]; then
    :
  else
    skill_drift_verdict="${skill_drift_output%%$'\t'*}"
    skill_drift_body="$(printf '%s' "${skill_drift_output}" | sed "1s/^[A-Z]*$(printf '\t')//")"
    if [ "${skill_drift_verdict}" = "OK" ]; then
      pass_msg "${skill_drift_body}"
    else
      warn_msg "${skill_drift_body}"
    fi
  fi
  echo ""
fi

# ─── 12. 面向人的产物文风（conventions.md〈输出〉）───
# 只报告不阻断：判定文风是主观的，接成红灯会逼着人改写措辞来骗过校验，规则反而失效。
# 首行形如 "OK<TAB>…" 或 "WARN<TAB>…"，判定标记交给 pass_msg / warn_msg 渲染。
echo "12. 面向人的产物文风（conventions.md〈输出〉）"
if prose_output="$(python3 "${SCRIPT_DIR}/check-prose.py" 2>&1)"; then
  prose_head="${prose_output%%$'\n'*}"
  prose_verdict="${prose_head%%$'\t'*}"
  prose_body="$(printf '%s' "${prose_head}" | sed "1s/^[A-Z]*$(printf '\t')//")"
  if [ "${prose_verdict}" = "OK" ]; then
    pass_msg "${prose_body}"
  else
    warn_msg "${prose_body}"
    printf '%s\n' "${prose_output}" | tail -n +2 | sed 's/^/    /'
  fi
else
  fail_msg "check-prose.py 执行失败"
  printf '%s\n' "${prose_output}" | sed 's/^/    /'
fi
echo ""

# ─── 汇总 ───
echo "=== 汇总 ==="
echo "  通过: ${pass}"
echo "  失败: ${fail}"
echo "  警告: ${warnings}"

if [ "${fail}" -gt 0 ]; then
  echo ""
  echo "❌ 校验未通过"
  exit 1
else
  echo ""
  echo "✅ 校验通过"
  exit 0
fi
