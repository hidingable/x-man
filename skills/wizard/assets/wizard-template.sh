#!/bin/bash
# Reusable template: Bash 3.2+ and Python 3. Fill wizard_main before delivery.
set +x
set -euo pipefail

WIZARD_INITIALIZED=0
WIZARD_DRY_RUN=0

wizard_init() {
  set +x
  WIZARD_INITIALIZED=0
  WIZARD_DRY_RUN=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --dry-run) WIZARD_DRY_RUN=1 ;;
      *) printf '%s\n' 'wizard: unsupported argument' >&2; return 64 ;;
    esac
    shift
  done
  WIZARD_INITIALIZED=1
}

_wizard_ready() {
  if [ "${WIZARD_INITIALIZED:-0}" != 1 ]; then
    printf '%s\n' 'wizard: call wizard_init first' >&2
    return 64
  fi
}

_wizard_variable() {
  case "${1:-}" in
    ''|[0-9]*|*[!a-zA-Z0-9_]*|_wizard_*|WIZARD_*) return 64 ;;
  esac
}

confirm() {
  local _wizard_reply
  _wizard_ready || return $?
  [ "$#" -eq 1 ] || return 64
  [ "$WIZARD_DRY_RUN" -eq 0 ] || return 1
  printf '%s [y/N]: ' "$1" >&2
  if ! IFS= read -r _wizard_reply; then
    printf '\n%s\n' 'wizard: no confirmation received' >&2
    return 1
  fi
  case "$_wizard_reply" in
    y|Y|yes|YES|Yes) return 0 ;;
    *) return 1 ;;
  esac
}

_wizard_read() {
  set +x
  local _wizard_target="$1" _wizard_prompt="$2" _wizard_secret="$3"
  local _wizard_answer
  _wizard_ready || return $?
  _wizard_variable "$_wizard_target" || return $?
  [ "$WIZARD_DRY_RUN" -eq 0 ] || return 0
  printf -v "$_wizard_target" '%s' '' || return $?
  printf '%s: ' "$_wizard_prompt" >&2
  if [ "$_wizard_secret" -eq 1 ]; then
    if ! IFS= read -r -s _wizard_answer; then
      printf '\n%s\n' 'wizard: input ended before a value was received' >&2
      return 1
    fi
    printf '\n' >&2
  elif ! IFS= read -r _wizard_answer; then
    printf '\n%s\n' 'wizard: input ended before a value was received' >&2
    return 1
  fi
  printf -v "$_wizard_target" '%s' "$_wizard_answer"
}

ask() {
  [ "$#" -eq 2 ] || return 64
  _wizard_read "$1" "$2" 0
}

ask_secret() {
  set +x
  [ "$#" -eq 2 ] || return 64
  _wizard_read "$1" "$2" 1
}

open_url() {
  local _wizard_url _wizard_host
  _wizard_ready || return $?
  [ "$#" -eq 1 ] || return 64
  _wizard_url="$1"
  case "$_wizard_url" in
    http://?*|https://?*) ;;
    *) printf '%s\n' 'wizard: an explicit HTTP(S) URL is required' >&2; return 64 ;;
  esac
  case "$_wizard_url" in
    *[$'\r\n\t ']*|http:///*|https:///*) return 64 ;;
  esac
  _wizard_host="${_wizard_url#*://}"
  _wizard_host="${_wizard_host%%[/?#]*}"
  case "$_wizard_host" in ''|*@*) return 64 ;; esac
  if [ "$WIZARD_DRY_RUN" -eq 1 ]; then
    printf '%s\n' '[dry-run] open the specified page'
    return 0
  fi
  if command -v open >/dev/null 2>&1; then
    open "$_wizard_url"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$_wizard_url"
  else
    printf '%s\n' 'wizard: no browser opener found; open the documented URL manually' >&2
    return 69
  fi
}

# Values travel in the environment, not argv. Output uses shell assignment syntax.
write_env() {
  set +x
  local _wizard_path _wizard_key _wizard_source
  _wizard_ready || return $?
  [ "$#" -eq 3 ] || return 64
  _wizard_path="$1" _wizard_key="$2" _wizard_source="$3"
  case "$_wizard_key" in
    ''|[0-9]*|*[!a-zA-Z0-9_]*) return 64 ;;
  esac
  _wizard_variable "$_wizard_source" || return $?
  if [ "$WIZARD_DRY_RUN" -eq 1 ]; then
    printf '%s\n' '[dry-run] update the specified configuration entry'
    return 0
  fi
  if [ "${!_wizard_source+x}" != x ]; then
    printf '%s\n' 'wizard: configuration value variable is unset' >&2
    return 64
  fi
  WIZARD_ENV_VALUE="${!_wizard_source}" python3 - "$_wizard_path" "$_wizard_key" <<'PY'
import os
import re
import secrets
import shlex
import stat
import sys

directory_fd = None
temporary_name = None
temporary_created = False
try:
    path, key = sys.argv[1:]
    value = os.environ['WIZARD_ENV_VALUE']
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
        raise ValueError('invalid key')
    if '\n' in value or '\r' in value:
        raise ValueError('multiline values are unsupported')
    parent, name = os.path.split(os.path.abspath(path))
    if not name:
        raise ValueError('missing file name')
    directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)

    def current_stat():
        try:
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('destination must be a regular file')
        return info

    def identity(info):
        if info is None:
            return None
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                info.st_ctime_ns, info.st_mode)

    before = current_stat()
    old = b''
    if before is not None:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory_fd)
        with os.fdopen(descriptor, 'rb') as stream:
            if identity(os.fstat(stream.fileno())) != identity(before):
                raise RuntimeError('file changed during read')
            old = stream.read()
    pattern = re.compile(r'^[ \t]*(?P<export>export[ \t]+)?' + re.escape(key) + r'[ \t]*=')
    old_lines = old.decode('utf-8').splitlines(keepends=True)
    # Only edit standalone physical lines. Validate every line before matching
    # keys: a target-looking line can belong to another variable's quoted value.
    # Removing line endings also makes escaped-newline continuations fail closed.
    for line in old_lines:
        lexer = shlex.shlex(line.rstrip('\r\n'), posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        for token in lexer:
            if token and all(character in '();<>|&' for character in token):
                raise ValueError('shell control syntax is unsupported')
    exported = any(match is not None and match.group('export') is not None
                   for match in map(pattern.match, old_lines))
    assignment = ('export ' if exported else '') + key + '=' + shlex.quote(value) + '\n'
    lines = []
    found = False
    for line in old_lines:
        match = pattern.match(line)
        if match:
            if not found:
                lines.append(assignment)
                found = True
        else:
            lines.append(line)
    if not found:
        if lines and not lines[-1].endswith(('\n', '\r')):
            lines[-1] += '\n'
        lines.append(assignment)
    updated = ''.join(lines).encode('utf-8')
    if identity(current_stat()) != identity(before):
        raise RuntimeError('file changed during update')
    if before is not None and updated == old and stat.S_IMODE(before.st_mode) == 0o600:
        sys.exit(0)
    temporary_name = '.wizard-' + secrets.token_hex(12)
    descriptor = os.open(temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                         0o600, dir_fd=directory_fd)
    temporary_created = True
    with os.fdopen(descriptor, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(updated)
        stream.flush()
        os.fsync(stream.fileno())
    if identity(current_stat()) != identity(before):
        raise RuntimeError('file changed before replacement')
    os.replace(temporary_name, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    temporary_name = None
except Exception:
    # Do not print values, exception messages, or source lines containing secrets.
    print('wizard: configuration read/write failed; file was not replaced', file=sys.stderr)
    sys.exit(1)
finally:
    if temporary_created and temporary_name is not None and directory_fd is not None:
        os.unlink(temporary_name, dir_fd=directory_fd)
    if directory_fd is not None:
        os.close(directory_fd)
PY
}

_wizard_callback() (
  # A fresh shell preserves errexit even when run_stage is called inside `if`.
  local _wizard_function
  while IFS= read -r _wizard_function; do
    export -f "$_wizard_function"
  done < <(compgen -A function)
  export WIZARD_INITIALIZED WIZARD_DRY_RUN
  "$BASH" -e -u -o pipefail -c '"$1"' wizard-callback "$1"
)

run_stage() {
  # Probe callbacks must map file/API failures (including exit 1) to a code > 1.
  # Reserve exit 1 for an observed, recoverable "not configured yet" state.
  local _wizard_title _wizard_probe _wizard_action _wizard_verify _wizard_status
  _wizard_ready || return $?
  [ "$#" -eq 4 ] || return 64
  _wizard_title="$1" _wizard_probe="$2" _wizard_action="$3" _wizard_verify="$4"
  for _wizard_status in "$_wizard_probe" "$_wizard_action" "$_wizard_verify"; do
    if [ "$(type -t "$_wizard_status" || true)" != function ]; then
      printf '%s\n' 'wizard: every stage requires probe, action and verification functions' >&2
      return 64
    fi
  done
  if [ "$WIZARD_DRY_RUN" -eq 1 ]; then
    printf '[dry-run] %s\n' "$_wizard_title"
    return 0
  fi
  if _wizard_callback "$_wizard_probe"; then
    printf 'Already complete: %s\n' "$_wizard_title"
    return 0
  else
    _wizard_status=$?
    if [ "$_wizard_status" -ne 1 ]; then
      printf 'Probe failed (%s): %s\n' "$_wizard_status" "$_wizard_title" >&2
      return "$_wizard_status"
    fi
  fi
  if ! confirm "Execute: $_wizard_title"; then
    printf 'Cancelled: %s\n' "$_wizard_title" >&2
    return 1
  fi
  if _wizard_callback "$_wizard_action"; then
    :
  else
    _wizard_status=$?
    printf 'Action failed (%s): %s\n' "$_wizard_status" "$_wizard_title" >&2
    return "$_wizard_status"
  fi
  if _wizard_callback "$_wizard_verify"; then
    printf 'Verified: %s\n' "$_wizard_title"
  else
    _wizard_status=$?
    printf 'Verification failed (%s): %s\n' "$_wizard_status" "$_wizard_title" >&2
    return "$_wizard_status"
  fi
}

wizard_main() {
  wizard_init "$@" || return $?
  printf '%s\n' 'wizard: no steps configured; fill and test wizard_main before running' >&2
  return 64
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  wizard_main "$@"
fi
