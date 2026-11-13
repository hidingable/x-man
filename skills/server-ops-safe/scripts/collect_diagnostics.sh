#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
用法:
  collect_diagnostics.sh <ssh_target> [service_name] [container_name]

说明:
  通过 SSH 登录目标主机，执行只读诊断命令。
  不会执行任何修改远端状态的操作。
EOF
}

if [[ $# -lt 1 || $# -gt 3 ]]; then
  usage
  exit 1
fi

ssh_target="$1"
service_name="${2:-}"
container_name="${3:-}"

quote_remote() {
  printf "%q" "$1"
}

run_remote() {
  local label="$1"
  local command="$2"

  printf '\n==== %s ====\n' "$label"
  ssh -o ConnectTimeout=15 "$ssh_target" "$command"
}

service_q="$(quote_remote "$service_name")"
container_q="$(quote_remote "$container_name")"

run_remote "identity" "hostname && whoami && date"
run_remote "uptime" "uptime"
run_remote "memory" "free -h"
run_remote "disk" "df -h"
run_remote "ports" "ss -ltnp || netstat -ltnp"
run_remote "docker ps" "docker ps -a"

if [[ -n "$service_name" ]]; then
  run_remote "systemd status: $service_name" "systemctl status $service_q --no-pager"
  run_remote "journalctl: $service_name" "journalctl -u $service_q -n 200 --no-pager"
fi

if [[ -n "$container_name" ]]; then
  run_remote "docker inspect: $container_name" "docker ps -a --filter name=$container_q"
  run_remote "docker logs: $container_name" "docker logs --tail 200 $container_q"
fi
