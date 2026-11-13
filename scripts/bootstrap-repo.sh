#!/bin/bash

set -euo pipefail

usage() {
  cat <<'EOF'
用法：
  bootstrap-repo.sh TARGET_DIR

说明：
  创建一个中心化 skill 仓库骨架，不覆盖已有文件。
EOF
}

if [ "$#" -ne 1 ]; then
  usage >&2
  exit 1
fi

TARGET_DIR="$1"

mkdir -p "${TARGET_DIR}/skills"
mkdir -p "${TARGET_DIR}/team/skills"
mkdir -p "${TARGET_DIR}/plugins/product"
mkdir -p "${TARGET_DIR}/plugins/design"
mkdir -p "${TARGET_DIR}/plugins/engineering"
mkdir -p "${TARGET_DIR}/plugins/general"
mkdir -p "${TARGET_DIR}/governance"
mkdir -p "${TARGET_DIR}/scripts"
mkdir -p "${TARGET_DIR}/context/templates"

copy_if_missing() {
  local src="$1"
  local dst="$2"
  if [ -e "${dst}" ]; then
    echo "跳过已存在文件: ${dst}"
  else
    cp "${src}" "${dst}"
    echo "已创建: ${dst}"
  fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

copy_if_missing "${TEMPLATE_ROOT}/README.md" "${TARGET_DIR}/README.md"
copy_if_missing "${TEMPLATE_ROOT}/LICENSE" "${TARGET_DIR}/LICENSE"
copy_if_missing "${TEMPLATE_ROOT}/governance/README.md" "${TARGET_DIR}/governance/README.md"
copy_if_missing "${TEMPLATE_ROOT}/governance/skills-registry.csv" "${TARGET_DIR}/governance/skills-registry.csv"
copy_if_missing "${TEMPLATE_ROOT}/context/templates/published-skill-bundle-readme.md" "${TARGET_DIR}/context/templates/published-skill-bundle-readme.md"
copy_if_missing "${TEMPLATE_ROOT}/scripts/sync-common.sh" "${TARGET_DIR}/scripts/sync-common.sh"
copy_if_missing "${TEMPLATE_ROOT}/scripts/sync-codex.sh" "${TARGET_DIR}/scripts/sync-codex.sh"
copy_if_missing "${TEMPLATE_ROOT}/scripts/sync-claude.sh" "${TARGET_DIR}/scripts/sync-claude.sh"
copy_if_missing "${TEMPLATE_ROOT}/scripts/sync-cursor.sh" "${TARGET_DIR}/scripts/sync-cursor.sh"
copy_if_missing "${TEMPLATE_ROOT}/scripts/audit-sync.sh" "${TARGET_DIR}/scripts/audit-sync.sh"
copy_if_missing "${TEMPLATE_ROOT}/scripts/check-team-links.sh" "${TARGET_DIR}/scripts/check-team-links.sh"
copy_if_missing "${TEMPLATE_ROOT}/scripts/publish-common.sh" "${TARGET_DIR}/scripts/publish-common.sh"
copy_if_missing "${TEMPLATE_ROOT}/scripts/publish-team.sh" "${TARGET_DIR}/scripts/publish-team.sh"
copy_if_missing "${TEMPLATE_ROOT}/scripts/publish-personal.sh" "${TARGET_DIR}/scripts/publish-personal.sh"

touch "${TARGET_DIR}/skills/.gitkeep"

chmod +x \
  "${TARGET_DIR}/scripts/sync-common.sh" \
  "${TARGET_DIR}/scripts/audit-sync.sh" \
  "${TARGET_DIR}/scripts/check-team-links.sh" \
  "${TARGET_DIR}/scripts/publish-common.sh" \
  "${TARGET_DIR}/scripts/publish-team.sh" \
  "${TARGET_DIR}/scripts/publish-personal.sh" \
  "${TARGET_DIR}/scripts/sync-codex.sh" \
  "${TARGET_DIR}/scripts/sync-claude.sh" \
  "${TARGET_DIR}/scripts/sync-cursor.sh"

echo
echo "中心 skill 仓库骨架已初始化到: ${TARGET_DIR}"
echo "下一步："
echo "  1. 在 ${TARGET_DIR}/skills 下放入你的 skill 目录"
echo "  2. 在 ${TARGET_DIR}/team/skills 和 ${TARGET_DIR}/plugins/* 下创建软链"
echo "  3. 执行 scripts/sync-codex.sh 或 scripts/sync-cursor.sh"
