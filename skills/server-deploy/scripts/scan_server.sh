#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scan_server.sh <ssh_target>

Connects to the target server and collects deployment-relevant info:
  - Existing projects and their locations
  - Listening ports
  - Docker containers
  - systemd custom services
  - PM2 processes
  - System resources (CPU, memory, disk)
  - Language runtimes
  - cloudflared tunnel config (domain routing)
  - Git SSH access
EOF
}

if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi

ssh_target="$1"

run_remote() {
  local label="$1"
  local command="$2"
  printf '\n==== %s ====\n' "$label"
  ssh -o ConnectTimeout=15 "$ssh_target" "$command" || echo "(command failed or not available)"
}

run_remote "identity" "hostname && whoami && date"
run_remote "projects directory" "ls -la /opt/projects/ 2>/dev/null || echo '/opt/projects/ not found'"
run_remote "listening ports" "ss -tlnp | grep LISTEN"
run_remote "docker containers" "docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || echo 'docker not available'"
run_remote "systemd custom services" "ls /etc/systemd/system/*.service 2>/dev/null | grep -v -E 'dbus|syslog|snap|cloud|ssh' || echo 'none found'"
run_remote "pm2 processes" "pm2 list 2>/dev/null || echo 'pm2 not installed'"
run_remote "system resources" "echo 'CPU:' && nproc && echo 'Memory:' && free -h | head -3 && echo 'Disk:' && df -h / | tail -1"
run_remote "runtimes" "python3 --version 2>/dev/null; node --version 2>/dev/null; go version 2>/dev/null; echo done"
run_remote "cloudflared config" "cat /etc/cloudflared/config.yml 2>/dev/null || echo 'cloudflared not configured'"
run_remote "git ssh access" "ssh -o ConnectTimeout=5 -T git@github.com 2>&1 | head -3 || true"
