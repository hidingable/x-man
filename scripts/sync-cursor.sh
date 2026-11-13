#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/sync-common.sh"

run_sync ".cursor/skills" "${HOME}/.cursor/skills" ".cursor/agents" "${HOME}/.cursor/agents" "$@"
