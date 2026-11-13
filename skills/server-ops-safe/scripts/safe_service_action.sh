#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
用法:
  safe_service_action.sh <ssh_target> <service|container> <target_name> <status|logs|health-check|restart> [health_check_command]

说明:
  仅支持受控动作。执行 restart 前必须由调用方先获得用户明确确认。
EOF
}

if [[ $# -lt 4 || $# -gt 5 ]]; then
  usage
  exit 1
fi

ssh_target="$1"
target_type="$2"
target_name="$3"
action="$4"
health_check_command="${5:-}"

quote_remote() {
  printf "%q" "$1"
}

run_remote() {
  local command="$1"
  ssh -o ConnectTimeout=15 "$ssh_target" "$command"
}

target_q="$(quote_remote "$target_name")"

case "$target_type" in
  service)
    case "$action" in
      status)
        run_remote "systemctl status $target_q --no-pager"
        ;;
      logs)
        run_remote "journalctl -u $target_q -n 200 --no-pager"
        ;;
      health-check)
        if [[ -z "$health_check_command" ]]; then
          echo "health-check 动作需要提供第 5 个参数 health_check_command" >&2
          exit 1
        fi
        run_remote "$health_check_command"
        ;;
      restart)
        run_remote "sudo systemctl restart $target_q && systemctl status $target_q --no-pager"
        ;;
      *)
        usage
        exit 1
        ;;
    esac
    ;;
  container)
    case "$action" in
      status)
        run_remote "docker ps -a --filter name=$target_q"
        ;;
      logs)
        run_remote "docker logs --tail 200 $target_q"
        ;;
      health-check)
        if [[ -z "$health_check_command" ]]; then
          echo "health-check 动作需要提供第 5 个参数 health_check_command" >&2
          exit 1
        fi
        run_remote "$health_check_command"
        ;;
      restart)
        run_remote "docker restart $target_q && docker ps -a --filter name=$target_q"
        ;;
      *)
        usage
        exit 1
        ;;
    esac
    ;;
  *)
    usage
    exit 1
    ;;
esac
