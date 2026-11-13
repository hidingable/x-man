#!/bin/bash
# 生成给 Claude Code / Codex 用的本地 plugin。
#
# plugin 包含 registry 中全部未废弃的 skill 和 agent，单装就是完整的一套。
# release 列不再过滤：它只标出哪个发行版也发了同名的一份，两个 plugin 同时启用时
# 由 plugin-overlap.py 按 x-mansion 优先处理。
# 明确不入仓且本机未提供的个人 skill 可缺省；现存个人 skill 照常交付。
# dist/ 是本地构建产物，首次 clone 运行 xman setup 生成。
#
# 用法: build-plugin.sh [--check]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# 允许用夹具 registry 跑 --check：回归测试需要构造当前数据里不存在的状态，
# 又不能去改真的 registry。默认值不变。
REGISTRY="${XMAN_REGISTRY:-${REPO_ROOT}/governance/skills-registry.csv}"
SKILLS_ROOT="${REPO_ROOT}/skills"
AGENTS_ROOT="${REPO_ROOT}/agents"
PLUGIN_NAME="x-mansion"
PLUGIN_ROOT="${REPO_ROOT}/dist/plugin/${PLUGIN_NAME}"
SKILL_DIR="${PLUGIN_ROOT}/skills"
AGENT_DIR="${PLUGIN_ROOT}/agents"
AGENT_RESOURCE_DIR="${PLUGIN_ROOT}/agent-resources"
MCP_CONFIG="${PLUGIN_ROOT}/.mcp.json"

CHECK_ONLY="false"
[ "${1:-}" = "--check" ] && CHECK_ONLY="true"

WANTED_RAW="$(python3 - "${REGISTRY}" "${REPO_ROOT}" <<'PY'
import csv
import pathlib
import sys

repo = pathlib.Path(sys.argv[2])
sys.path.insert(0, str(repo / "scripts"))
from registry_scope import optional_missing_skills

with pathlib.Path(sys.argv[1]).open(newline="", encoding="utf-8") as fh:
    rows = list(csv.DictReader(fh))

missing_local = optional_missing_skills(repo, rows)
for row in rows:
    item_type = (row.get("type") or "skill").strip()
    if item_type == "deprecated":
        continue
    if row["skill"] in missing_local:
        print(f"跳过未提供的本地个人 skill: {row['skill']}", file=sys.stderr)
        continue
    print(f"{'agent' if item_type == 'agent' else 'skill'}\t{row['skill']}")
PY
)"

WANTED_SKILLS=()
WANTED_AGENTS=()
while IFS=$'\t' read -r item_type item_name; do
  [ -n "${item_name}" ] || continue
  if [ "${item_type}" = "agent" ]; then
    WANTED_AGENTS+=("${item_name}")
  else
    WANTED_SKILLS+=("${item_name}")
  fi
done <<< "${WANTED_RAW}"

RSYNC_ARGS=(-aL --exclude '.git' --exclude '.DS_Store' --exclude '__pycache__' --exclude 'node_modules'
  --exclude '/scripts/llm-commit.env')

sorted_skill_names() {
  [ -d "$1" ] || return 0
  find "$1" -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null \
    | xargs -I{} basename "{}" | sort
}

sorted_agent_files() {
  [ -d "$1" ] || return 0
  find "$1" -mindepth 1 -maxdepth 1 -type f -name '*.md' -print 2>/dev/null \
    | xargs -I{} basename "{}" | sort
}

sorted_agent_dirs() {
  [ -d "$1" ] || return 0
  find "$1" -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null \
    | xargs -I{} basename "{}" | sort
}

normalize_skill_for_plugin() {
  # disable-model-invocation 是 Claude 专属元数据；Codex plugin 校验拒绝 true。
  # 只改生成副本，母仓源文件和 xman 直接安装保持原语义。
  python3 - "$1" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = re.sub(
    r"(?m)^disable-model-invocation:[ \t]*true[ \t]*$",
    "disable-model-invocation: false",
    text,
)
path.write_text(text, encoding="utf-8")
PY
}

normalize_agent_for_plugin() {
  python3 - "$1" "$2" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
agent = sys.argv[2]
text = path.read_text(encoding="utf-8")
text = re.sub(
    rf"(?<![\w./\\:-]){re.escape(agent)}/",
    lambda match: f"${{CLAUDE_PLUGIN_ROOT}}/agent-resources/{agent}/",
    text,
)
text = text.replace("`context/conventions.md`", "`${CLAUDE_PLUGIN_ROOT}/conventions.md`")
path.write_text(text, encoding="utf-8")
PY
}

# Codex reads the root plugin manifest and starts the launcher from that root.
# Rebase the nested command so it resolves from the installed plugin directory.
codex_security_mcp_config() {
  python3 - "${SKILL_DIR}" "${MCP_CONFIG}" "$1" <<'PY'
import json
import pathlib
import sys

skills_dir, output = map(pathlib.Path, sys.argv[1:3])
mode = sys.argv[3]
root = skills_dir / "codex-security"
if root.is_dir():
    config = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    server = config["mcpServers"]["codex-security"]
    command = pathlib.Path("skills/codex-security") / server["cwd"] / server["command"]
    server["command"] = f"./{command.as_posix()}"
    server["cwd"] = "."
    config_text = json.dumps(config, indent=2) + "\n"
    if mode == "check":
        if not output.is_file() or output.read_text(encoding="utf-8") != config_text:
            sys.exit("Codex Security MCP 配置与运行包不一致")
    else:
        output.write_text(config_text, encoding="utf-8")
elif mode == "check":
    if output.exists():
        sys.exit("插件缺少 Codex Security skill，但仍有 MCP 配置")
else:
    output.unlink(missing_ok=True)
PY
}

if [ "${CHECK_ONLY}" = "true" ]; then
  # dist/ 不入库，新 clone 上必然缺失。不早退的话下面会为每个 skill 各刷两行
  # 漂移报错，把「还没构建过」这件事淹没在 90 多行里。
  if [ ! -d "${PLUGIN_ROOT}" ]; then
    echo "FAIL	plugin 产物不存在（dist/ 不入库），请运行 ./xman plugin build"
    exit 1
  fi

  check_failed="false"
  actual_skills="$(sorted_skill_names "${SKILL_DIR}")"
  expected_skills="$(printf '%s\n' "${WANTED_SKILLS[@]}" | sort)"
  actual_agents="$(sorted_agent_files "${AGENT_DIR}")"
  expected_agents="$(printf '%s.md\n' "${WANTED_AGENTS[@]}" | sort)"

  expected_resource_dirs=""
  for agent in "${WANTED_AGENTS[@]}"; do
    [ -d "${AGENTS_ROOT}/${agent}" ] && expected_resource_dirs="${expected_resource_dirs}${agent}"$'\n'
  done
  expected_resource_dirs="$(printf '%s' "${expected_resource_dirs}" | sed '/^$/d' | sort)"
  actual_agent_dirs="$(sorted_agent_dirs "${AGENT_DIR}")"
  actual_resource_dirs="$(sorted_agent_dirs "${AGENT_RESOURCE_DIR}")"

  if [ "${actual_skills}" != "${expected_skills}" ]; then
    echo "FAIL	plugin skill 清单与 registry 不一致"
    check_failed="true"
  fi
  if [ "${actual_agents}" != "${expected_agents}" ] || [ -n "${actual_agent_dirs}" ] || [ "${actual_resource_dirs}" != "${expected_resource_dirs}" ]; then
    echo "FAIL	plugin agent 清单与 registry 不一致"
    check_failed="true"
  fi

  for skill in "${WANTED_SKILLS[@]}"; do
    if [ -e "${SKILL_DIR}/${skill}/scripts/llm-commit.env" ] || [ -L "${SKILL_DIR}/${skill}/scripts/llm-commit.env" ]; then
      echo "FAIL\tplugin 含本机配置: ${skill}/scripts/llm-commit.env"
      check_failed="true"
    fi
    drift="$(rsync -aniL --delete --exclude 'SKILL.md' "${RSYNC_ARGS[@]:1}" "${SKILLS_ROOT}/${skill}/" "${SKILL_DIR}/${skill}/" 2>/dev/null || true)"
    if [ ! -d "${SKILL_DIR}/${skill}" ] || [ -n "${drift}" ]; then
      echo "FAIL	plugin skill 内容已漂移: ${skill}"
      check_failed="true"
    fi
    if ! python3 - "${SKILLS_ROOT}/${skill}/SKILL.md" "${SKILL_DIR}/${skill}/SKILL.md" <<'PY'
import pathlib
import re
import sys

target = pathlib.Path(sys.argv[2])
if not target.is_file():
    raise SystemExit(1)

source = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
actual = target.read_text(encoding="utf-8")
expected = re.sub(
    r"(?m)^disable-model-invocation:[ \t]*true[ \t]*$",
    "disable-model-invocation: false",
    source,
)
raise SystemExit(0 if actual == expected else 1)
PY
    then
      echo "FAIL	plugin skill 定义已漂移: ${skill}/SKILL.md"
      check_failed="true"
    fi
  done
  for agent in "${WANTED_AGENTS[@]}"; do
    if ! python3 - "${AGENTS_ROOT}/${agent}.md" "${AGENT_DIR}/${agent}.md" "${agent}" <<'PY'
import pathlib
import re
import sys

target = pathlib.Path(sys.argv[2])
if not target.is_file():
    raise SystemExit(1)

source = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
actual = target.read_text(encoding="utf-8")
agent = sys.argv[3]
expected = re.sub(
    rf"(?<![\w./\\:-]){re.escape(agent)}/",
    lambda match: f"${{CLAUDE_PLUGIN_ROOT}}/agent-resources/{agent}/",
    source,
)
expected = expected.replace("`context/conventions.md`", "`${CLAUDE_PLUGIN_ROOT}/conventions.md`")
if "`context/conventions.md`" in source:
    conventions = pathlib.Path(sys.argv[1]).resolve().parent.parent / "context" / "conventions.md"
    bundled = target.parent.parent / "conventions.md"
    if not bundled.is_file() or bundled.read_bytes() != conventions.read_bytes():
        raise SystemExit(1)
raise SystemExit(0 if actual == expected else 1)
PY
    then
      echo "FAIL	plugin agent 定义已漂移: ${agent}.md"
      check_failed="true"
    fi
    if [ -d "${AGENTS_ROOT}/${agent}" ]; then
      drift="$(rsync -aniL --delete "${RSYNC_ARGS[@]:1}" "${AGENTS_ROOT}/${agent}/" "${AGENT_RESOURCE_DIR}/${agent}/" 2>/dev/null || true)"
      if [ ! -d "${AGENT_RESOURCE_DIR}/${agent}" ] || [ -n "${drift}" ]; then
        echo "FAIL	plugin agent 伴随文件已漂移: ${agent}/"
        check_failed="true"
      fi
    fi
  done

  if ! python3 - "${PLUGIN_ROOT}" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
try:
    codex_data = json.loads((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    claude_data = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)
if codex_data.get("name") != "x-mansion" or codex_data.get("skills") != "./skills/":
    raise SystemExit(1)
expected_mcp = "./.mcp.json" if (root / "skills" / "codex-security").is_dir() else None
if codex_data.get("mcpServers") != expected_mcp:
    raise SystemExit(1)
if codex_data.get("version") != claude_data.get("version"):
    raise SystemExit(1)
if "agents" in claude_data:
    raise SystemExit(1)
PY
  then
    echo "FAIL	plugin manifest 缺失、非法或两端版本不一致"
    check_failed="true"
  fi

  if ! codex_security_mcp_config check; then
    check_failed="true"
  fi

  if [ "${check_failed}" = "true" ]; then
    echo "FAIL	plugin 产物不完整，请运行 ./xman plugin build"
    exit 1
  fi
  echo "OK	plugin 产物与源文件一致（${#WANTED_SKILLS[@]} 个 skill，${#WANTED_AGENTS[@]} 个 agent）"
  exit 0
fi

for skill in "${WANTED_SKILLS[@]}"; do
  [ -f "${SKILLS_ROOT}/${skill}/SKILL.md" ] || { echo "缺少 skill 源文件: skills/${skill}/SKILL.md" >&2; exit 1; }
done
for agent in "${WANTED_AGENTS[@]}"; do
  [ -f "${AGENTS_ROOT}/${agent}.md" ] || { echo "缺少 agent 源文件: agents/${agent}.md" >&2; exit 1; }
done

rm -rf "${SKILL_DIR}" "${AGENT_DIR}" "${AGENT_RESOURCE_DIR}"
mkdir -p "${SKILL_DIR}" "${AGENT_DIR}" "${AGENT_RESOURCE_DIR}"

for skill in "${WANTED_SKILLS[@]}"; do
  rsync "${RSYNC_ARGS[@]}" "${SKILLS_ROOT}/${skill}/" "${SKILL_DIR}/${skill}/"
  normalize_skill_for_plugin "${SKILL_DIR}/${skill}/SKILL.md"
done
for agent in "${WANTED_AGENTS[@]}"; do
  rsync -aL "${AGENTS_ROOT}/${agent}.md" "${AGENT_DIR}/${agent}.md"
  normalize_agent_for_plugin "${AGENT_DIR}/${agent}.md" "${agent}"
  if [ -d "${AGENTS_ROOT}/${agent}" ]; then
    rsync "${RSYNC_ARGS[@]}" "${AGENTS_ROOT}/${agent}/" "${AGENT_RESOURCE_DIR}/${agent}/"
  fi
done

PLUGIN_VERSION="1.0.0+codex.local-$(date -u +%Y%m%d-%H%M%S)"
mkdir -p "${PLUGIN_ROOT}/.codex-plugin" "${PLUGIN_ROOT}/.claude-plugin"
codex_security_mcp_config write
MCP_MANIFEST_ENTRY=""
if [ -f "${MCP_CONFIG}" ]; then
  MCP_MANIFEST_ENTRY='  "mcpServers": "./.mcp.json",'
fi
if [ -f "${REPO_ROOT}/context/conventions.md" ]; then
  cp "${REPO_ROOT}/context/conventions.md" "${PLUGIN_ROOT}/conventions.md"
fi
if [ -f "${REPO_ROOT}/LICENSE" ]; then
  cp "${REPO_ROOT}/LICENSE" "${PLUGIN_ROOT}/LICENSE"
fi
cat > "${PLUGIN_ROOT}/.codex-plugin/plugin.json" <<JSON
{
  "name": "${PLUGIN_NAME}",
  "version": "${PLUGIN_VERSION}",
  "description": "Skill 研发母仓：产品到研发全流程 skill，加实验性与本地维护的 skill",
  "author": {
    "name": "x-mansion"
  },
  "license": "MIT",
  "skills": "./skills/",
${MCP_MANIFEST_ENTRY}
  "interface": {
    "displayName": "x-mansion",
    "shortDescription": "全流程 Skill 与实验性 Skill 的完整一套",
    "longDescription": "从 x-mansion 母仓加载全部 Skill，单独安装即可完整使用。",
    "developerName": "x-mansion",
    "category": "Developer Tools",
    "capabilities": ["Read", "Write"],
    "defaultPrompt": ["使用 x-mansion 中合适的 Skill 完成当前任务。"]
  }
}
JSON
cat > "${PLUGIN_ROOT}/.claude-plugin/plugin.json" <<JSON
{
  "name": "${PLUGIN_NAME}",
  "version": "${PLUGIN_VERSION}",
  "description": "Skill 研发母仓：产品到研发全流程 skill 和 agent，加实验性与本地维护的 skill",
  "author": {
    "name": "x-mansion"
  },
  "license": "MIT"
}
JSON

"${BASH_SOURCE[0]}" --check
echo "✅ ${PLUGIN_NAME} plugin 已生成：${#WANTED_SKILLS[@]} 个 skill，${#WANTED_AGENTS[@]} 个 agent"
echo "   ${PLUGIN_ROOT#${REPO_ROOT}/}/  （$(du -sh "${PLUGIN_ROOT}" | cut -f1)，dist/ 不入库）"
echo "   新版本需重新安装，并在新会话中生效"
# 夹具仓库里没有这个脚本；没有重名 plugin 时它零输出
if [ -f "${SCRIPT_DIR}/plugin-overlap.py" ]; then
  python3 "${SCRIPT_DIR}/plugin-overlap.py" report || true
fi
