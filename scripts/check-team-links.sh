#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/sync-common.sh"

usage() {
  cat <<'EOF'
用法：
  check-team-links.sh [--verbose]

说明：
  对比 team/skills 软链集合 与 skills-registry.csv 中 status=team-shared 的集合。
  只输出差异，不自动修复。
EOF
}

verbose="false"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --verbose)
      verbose="true"
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

ensure_registry_exists
mkdir -p "${TEAM_ROOT}/skills"

expected="$(python3 - "${REGISTRY_FILE}" <<'PY'
import csv, pathlib, sys
path = pathlib.Path(sys.argv[1])
with path.open(newline="") as fh:
    for row in csv.DictReader(fh):
        if row["status"] == "team-shared":
            print(row["skill"])
PY
)"

actual="$(skills_from_group_dir "${TEAM_ROOT}/skills" || true)"

missing="$(comm -23 <(printf '%s\n' "${expected}" | sed '/^$/d' | sort) <(printf '%s\n' "${actual}" | sed '/^$/d' | sort))"
extra="$(comm -13 <(printf '%s\n' "${expected}" | sed '/^$/d' | sort) <(printf '%s\n' "${actual}" | sed '/^$/d' | sort))"

echo "team 视图目录: ${TEAM_ROOT}/skills"
echo "状态来源: ${REGISTRY_FILE}"

if [ -z "${missing}" ] && [ -z "${extra}" ]; then
  echo "结果: 一致"
  exit 0
fi

echo "结果: 不一致"

if [ -n "${missing}" ]; then
  echo "team/skills 缺少:"
  printf '  - %s\n' ${missing}
fi

if [ -n "${extra}" ]; then
  echo "team/skills 多出:"
  printf '  - %s\n' ${extra}
fi

if [ "${verbose}" = "true" ]; then
  echo "期望集合:"
  printf '  - %s\n' ${expected}
  echo "实际集合:"
  printf '  - %s\n' ${actual}
fi

exit 1
