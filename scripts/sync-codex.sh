#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_AGENT_FORMAT="codex-toml"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/sync-common.sh"

# 两层的落点不一样，依据是 codex debug prompt-input 报出的扫描根：
#   项目级只扫 <project>/.agents/skills，不扫 <project>/.codex/skills
#   全局级 ~/.codex/skills 和 ~/.agents/skills 都扫
# 所以项目级必须用 .agents/skills；全局级留在 ~/.codex/skills，不去和发行版的
# ~/.agents/skills 抢地盘。agent 两层都走 .codex/agents/*.toml，那是官方 Agent 配置。
run_sync ".agents/skills" "${HOME}/.codex/skills" ".codex/agents" "${HOME}/.codex/agents" "$@"
