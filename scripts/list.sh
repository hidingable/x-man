#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKILLS_ROOT="${REPO_ROOT}/skills"
PLUGINS_ROOT="${REPO_ROOT}/plugins"
REGISTRY_FILE="${REPO_ROOT}/governance/skills-registry.csv"

usage() {
  cat <<'EOF'
用法：
  list.sh [--status STATUS] [--plugin NAME] [--group-by status|plugin] [--compact]

参数：
  --status STATUS   只列出指定状态的 skill
  --plugin NAME     只列出指定 plugin 下的 skill
  --group-by MODE   分组显示（status 或 plugin），默认 status
  --compact         紧凑格式，只输出 skill 名（适合管道）
  --json            机器可读输出（给 agent 用，description 不截断）
  --help            显示帮助
EOF
}

filter_status=""
filter_plugin=""
group_by="status"
compact="false"
as_json="false"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --status) filter_status="$2"; shift 2 ;;
    --plugin) filter_plugin="$2"; shift 2 ;;
    --group-by) group_by="$2"; shift 2 ;;
    --compact) compact="true"; shift ;;
    --json) as_json="true"; shift ;;
    --help) usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [ ! -f "${REGISTRY_FILE}" ]; then
  echo "缺少 ${REGISTRY_FILE}" >&2
  exit 1
fi

# 用 python3 处理全部逻辑（避免 bash 3.2 不支持关联数组）
python3 - "${SKILLS_ROOT}" "${PLUGINS_ROOT}" "${REGISTRY_FILE}" \
  "${filter_status}" "${filter_plugin}" "${group_by}" "${compact}" "${as_json}" <<'PY'
import csv
import json
import os
import pathlib
import sys

skills_root = pathlib.Path(sys.argv[1])
plugins_root = pathlib.Path(sys.argv[2])
registry_file = pathlib.Path(sys.argv[3])
filter_status = sys.argv[4] or None
filter_plugin = sys.argv[5] or None
group_by = sys.argv[6]
compact = sys.argv[7] == "true"
as_json = sys.argv[8] == "true"

# 读取 CSV
skill_data = {}
with registry_file.open(newline="") as fh:
    for row in csv.DictReader(fh):
        skill_data[row["skill"]] = {
            "status": row["status"],
            "note": row.get("note", "").strip('"'),
        }

# 构建 plugin 映射
skill_plugins = {}
if plugins_root.is_dir():
    for plugin_dir in sorted(plugins_root.iterdir()):
        if not plugin_dir.is_dir():
            continue
        pname = plugin_dir.name
        for entry in sorted(plugin_dir.iterdir()):
            sname = entry.name
            skill_plugins.setdefault(sname, []).append(pname)

# 从 SKILL.md 提取 description 全文
def get_full_desc(skill_dir):
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return ""
    in_fm = False
    lines = skill_md.read_text(errors="replace").splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "---":
            if in_fm:
                break
            in_fm = True
            continue
        if in_fm and line.startswith("description:"):
            desc = line[len("description:"):].strip()
            # description 可能折行（`description:` 后换行缩进续写）
            for cont in lines[i + 1:]:
                if not cont.startswith((" ", "\t")) or cont.strip() == "---":
                    break
                desc += " " + cont.strip()
            return desc.strip().strip('"').strip("'")
    return ""


# 从 SKILL.md 提取 description 首句
def get_short_desc(skill_dir):
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return ""
    in_fm = False
    for line in skill_md.read_text(errors="replace").splitlines():
        if line.strip() == "---":
            if in_fm:
                break
            in_fm = True
            continue
        if in_fm and line.startswith("description:"):
            desc = line[len("description:"):].strip().strip('"').strip("'")
            # 取第一句
            for sep in ["。", ".", "；"]:
                if sep in desc:
                    desc = desc[:desc.index(sep)]
                    break
            if len(desc) > 45:
                desc = desc[:42] + "..."
            return desc
    return ""

# 收集所有 skill 目录
all_skills = sorted(
    d.name for d in skills_root.iterdir()
    if d.is_dir() and not d.name.startswith(".")
)

# 过滤
filtered = []
for sname in all_skills:
    if filter_status and skill_data.get(sname, {}).get("status") != filter_status:
        continue
    if filter_plugin and not (plugins_root / filter_plugin / sname).exists():
        continue
    filtered.append(sname)

if as_json:
    print(json.dumps({"skills": [{
        "name": sname,
        "status": skill_data.get(sname, {}).get("status", "unknown"),
        "plugins": skill_plugins.get(sname, []),
        "note": skill_data.get(sname, {}).get("note", ""),
        "description": get_full_desc(skills_root / sname),
    } for sname in filtered]}, ensure_ascii=False, indent=2))
    sys.exit(0)

if compact:
    for sname in filtered:
        print(sname)
    sys.exit(0)

# 分组输出
if group_by == "plugin":
    if not plugins_root.is_dir():
        print("plugins/ 目录不存在", file=sys.stderr)
        sys.exit(1)
    for plugin_dir in sorted(plugins_root.iterdir()):
        if not plugin_dir.is_dir():
            continue
        pname = plugin_dir.name
        group = [s for s in filtered if (plugins_root / pname / s).exists()]
        if not group:
            continue
        print(f"=== {pname} ({len(group)}) ===")
        for sname in group:
            status = skill_data.get(sname, {}).get("status", "unknown")
            desc = get_short_desc(skills_root / sname)
            print(f"  {sname:<32s} [{status:<14s}] {desc}")
        print()
else:
    for status_val in ["team-shared", "experimental", "personal-only"]:
        group = [s for s in filtered if skill_data.get(s, {}).get("status") == status_val]
        if not group:
            continue
        print(f"=== {status_val} ({len(group)}) ===")
        for sname in group:
            plugins_str = ",".join(skill_plugins.get(sname, []))
            if plugins_str:
                plugins_str = f"[{plugins_str}]"
            desc = get_short_desc(skills_root / sname)
            print(f"  {sname:<32s} {plugins_str:<22s} {desc}")
        print()

print(f"合计: {len(filtered)} 个 skill")
PY
