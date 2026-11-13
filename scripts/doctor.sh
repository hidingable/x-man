#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== x-mansion 环境检查 ==="
echo ""

pass=0
fail=0

check_cmd() {
  local name="$1"
  local cmd="$2"
  if command -v "${cmd}" &>/dev/null; then
    local ver
    # Consume all output before selecting its first line; head can SIGPIPE the producer.
    ver="$("${cmd}" --version 2>&1)"
    ver="${ver%%$'\n'*}"
    echo "  ✓ ${name}: ${ver}"
    pass=$((pass + 1))
  else
    echo "  ✗ ${name}: 未安装"
    fail=$((fail + 1))
  fi
}

check_python() {
  if ! command -v python3 &>/dev/null; then
    echo "  ✗ python3: 未安装（需要 Python >= 3.9）"
    fail=$((fail + 1))
    return
  fi

  local version
  version="$(python3 --version 2>&1)"
  version="${version%%$'\n'*}"
  if python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
    echo "  ✓ python3: ${version}（满足 Python >= 3.9）"
    pass=$((pass + 1))
  else
    echo "  ✗ python3: ${version}（需要 Python >= 3.9）"
    fail=$((fail + 1))
  fi
}

check_pyyaml() {
  local version
  if command -v python3 &>/dev/null && version="$(python3 -c 'import yaml; print(yaml.__version__)' 2>/dev/null)"; then
    echo "  ✓ PyYAML: ${version}（当前 python3 可用）"
    pass=$((pass + 1))
  else
    echo "  ✗ PyYAML: 当前 python3 无法加载；运行 python3 -m pip install PyYAML 后重试"
    fail=$((fail + 1))
  fi
}

echo "必需依赖:"
check_cmd "bash" "bash"
check_python
check_pyyaml
check_cmd "git" "git"
check_cmd "rsync" "rsync"
if command -v shasum &>/dev/null; then
  shasum_version="$(shasum --version 2>&1)" || shasum_version='已安装'
  echo "  ✓ shasum: ${shasum_version%%$'\n'*}"
  pass=$((pass + 1))
else
  echo "  ✗ shasum: 未安装"
  fail=$((fail + 1))
fi
echo ""

echo "可选工具:"
if command -v shellcheck &>/dev/null; then
  echo "  ✓ shellcheck: $(shellcheck --version 2>&1 | grep '^version:' || echo '已安装')"
else
  echo "  - shellcheck: 未安装（可选，用于脚本质量检查）"
fi
echo ""

echo "仓库环境:"
if git -C "${REPO_ROOT}" rev-parse --is-inside-work-tree &>/dev/null; then
  local_remote="$(git -C "${REPO_ROOT}" remote get-url github 2>/dev/null || echo '无 github remote')"
  echo "  ✓ Git 仓库: ${local_remote}"
  pass=$((pass + 1))
else
  echo "  ✗ 不在 Git 仓库中"
  fail=$((fail + 1))
fi

for f in governance/skills-registry.csv docs/SKILL-SPEC.md README.md; do
  if [ -f "${REPO_ROOT}/${f}" ]; then
    echo "  ✓ ${f}"
    pass=$((pass + 1))
  else
    echo "  ✗ ${f} 缺失"
    fail=$((fail + 1))
  fi
done
echo ""

echo "=== 结果: 通过 ${pass} / 失败 ${fail} ==="

if [ "${fail}" -gt 0 ]; then
  echo ""
  echo "请安装缺失的依赖后重试。"
  echo "  macOS: brew install python3 rsync shellcheck"
  exit 1
else
  echo ""
  echo "✅ 环境就绪"
fi
