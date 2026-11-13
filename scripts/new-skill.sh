#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKILLS_ROOT="${REPO_ROOT}/skills"
TEAM_ROOT="${REPO_ROOT}/team/skills"
PLUGINS_ROOT="${REPO_ROOT}/plugins"
REGISTRY_FILE="${REPO_ROOT}/governance/skills-registry.csv"

usage() {
  cat <<'EOF'
用法：
  new-skill.sh <skill-name> [--status STATUS] [--plugin PLUGIN] [--category CATEGORY]

参数：
  skill-name       skill 名称（小写字母+连字符）
  --status STATUS  治理状态，默认 experimental
  --plugin PLUGIN  所属 plugin 分组（product/design/engineering/general）
  --category CAT   metadata.category，默认从 plugin 推导
  --help           显示帮助

说明：
  1. 创建 skills/<name>/ 目录和 SKILL.md 模板
  2. 追加 CSV 记录（保持字母排序）
  3. 根据 status 决定是否创建 team/skills 软链
  4. 根据 plugin 创建 plugins/<plugin>/ 软链
  5. 运行 validate.sh 确认一致性
EOF
}

skill_name=""
status="experimental"
plugin=""
category=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --status) status="$2"; shift 2 ;;
    --plugin) plugin="$2"; shift 2 ;;
    --category) category="$2"; shift 2 ;;
    --help) usage; exit 0 ;;
    -*)
      echo "未知参数: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      if [ -z "${skill_name}" ]; then
        skill_name="$1"
      else
        echo "多余的参数: $1" >&2
        usage >&2
        exit 1
      fi
      shift
      ;;
  esac
done

if [ -z "${skill_name}" ]; then
  echo "必须提供 skill 名称" >&2
  usage >&2
  exit 1
fi

# 校验名称格式
if ! echo "${skill_name}" | grep -qE '^[a-z][a-z0-9-]*$'; then
  echo "skill 名称只能包含小写字母、数字和连字符，且以字母开头: ${skill_name}" >&2
  exit 1
fi

if [ "${#skill_name}" -gt 64 ]; then
  echo "skill 名称最长 64 字符: ${skill_name}" >&2
  exit 1
fi

# 检查是否已存在
if [ -d "${SKILLS_ROOT}/${skill_name}" ]; then
  echo "skill 目录已存在: ${SKILLS_ROOT}/${skill_name}" >&2
  exit 1
fi

# 从 plugin 推导 category
if [ -z "${category}" ] && [ -n "${plugin}" ]; then
  category="${plugin}"
fi

# 交互提示 plugin
if [ -z "${plugin}" ]; then
  echo "可用的 plugin 分组:"
  echo "  1. product"
  echo "  2. design"
  echo "  3. engineering"
  echo "  4. general"
  echo ""
  printf "选择 plugin (1-4，留空跳过): "
  read -r choice
  case "${choice}" in
    1) plugin="product" ;;
    2) plugin="design" ;;
    3) plugin="engineering" ;;
    4) plugin="general" ;;
    "") echo "跳过 plugin 分配" ;;
    *) echo "无效选择: ${choice}" >&2; exit 1 ;;
  esac
  if [ -z "${category}" ] && [ -n "${plugin}" ]; then
    category="${plugin}"
  fi
fi

# 校验 plugin 存在
if [ -n "${plugin}" ] && [ ! -d "${PLUGINS_ROOT}/${plugin}" ]; then
  echo "plugin 目录不存在: ${PLUGINS_ROOT}/${plugin}" >&2
  exit 1
fi

# 校验 status
case "${status}" in
  team-shared|personal-only|experimental) ;;
  *) echo "无效的 status: ${status}（允许: team-shared, personal-only, experimental）" >&2; exit 1 ;;
esac

echo "创建 skill: ${skill_name}"
echo "  状态: ${status}"
echo "  plugin: ${plugin:-无}"
echo "  category: ${category:-无}"
echo ""

# 1. 创建目录结构
mkdir -p "${SKILLS_ROOT}/${skill_name}/references"
mkdir -p "${SKILLS_ROOT}/${skill_name}/assets/templates"
echo "  ✓ 创建目录: skills/${skill_name}/"

# 2. 生成 SKILL.md
cat > "${SKILLS_ROOT}/${skill_name}/SKILL.md" <<SKILLEOF
---
name: ${skill_name}
description: "<请补充一句话描述 + 使用场景 + 触发词>"
${category:+
metadata:
  category: ${category}
  tags: []
  dependencies: []}
---

# ${skill_name}

## 概述

<请补充 skill 概述>

## 使用场景

<请补充使用场景>

## 工作流程

<请补充工作流程>
SKILLEOF
echo "  ✓ 生成: skills/${skill_name}/SKILL.md"

# 3. 追加 CSV（保持字母排序）
python3 - "${REGISTRY_FILE}" "${skill_name}" "${status}" <<'PY'
import csv
import pathlib
import sys

registry = pathlib.Path(sys.argv[1])
new_skill = sys.argv[2]
new_status = sys.argv[3]

with registry.open(newline="") as fh:
    reader = csv.DictReader(fh)
    fieldnames = reader.fieldnames
    rows = list(reader)

# 检查重复
for row in rows:
    if row["skill"] == new_skill:
        print(f"CSV 中已存在: {new_skill}", file=sys.stderr)
        sys.exit(1)

rows.append({
    "skill": new_skill,
    "status": new_status,
    "source": "local",
    "note": "新建 skill，待补充说明",
    "source_type": "local",
    "source_key": "",
    "type": "skill"
})
rows.sort(key=lambda r: r["skill"])

with registry.open("w", newline="") as fh:
    # lineterminator 必须显式指定，csv 模块默认写 \r\n，会让 validate.sh 的 awk -F',' $7 取到 "skill\r"
    writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
PY
echo "  ✓ 追加 CSV 记录（已排序）"

# 4. team 软链（仅 team-shared）
if [ "${status}" = "team-shared" ]; then
  mkdir -p "${TEAM_ROOT}"
  ln -s "../../skills/${skill_name}" "${TEAM_ROOT}/${skill_name}"
  echo "  ✓ 创建 team 软链: team/skills/${skill_name}"
fi

# 5. plugin 软链
if [ -n "${plugin}" ]; then
  ln -s "../../skills/${skill_name}" "${PLUGINS_ROOT}/${plugin}/${skill_name}"
  echo "  ✓ 创建 plugin 软链: plugins/${plugin}/${skill_name}"
fi

echo ""
echo "✅ skill '${skill_name}' 创建完成"
echo ""
echo "下一步："
echo "  1. 编辑 skills/${skill_name}/SKILL.md 补充 description 和工作流程"
echo "  2. 运行 ./scripts/validate.sh 确认一致性"
echo "  3. 运行 ./xman install claude 同步到本机"
