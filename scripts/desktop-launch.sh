#!/bin/sh
set -eu

repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
state_dir=${XDG_STATE_HOME:-"$HOME/.local/state"}/darling-lol
mkdir -p "$state_dir"
log_file=$state_dir/launcher.log

# Keep the launcher log bounded. Retain one previous log so a failing startup
# still has useful context without growing indefinitely.
max_log_bytes=5242880
if [ -f "$log_file" ]; then
  log_bytes=$(wc -c <"$log_file")
  if [ "$log_bytes" -ge "$max_log_bytes" ]; then
    mv -f "$log_file" "$log_file.1"
  fi
fi

{
  printf '\n[%s] Starting League of Legends\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"
} >>"$log_file"
exec >>"$log_file" 2>&1
if [ "${1:-}" = --riot-client ]; then
  export RCLOL_LAUNCH_PRODUCT=
fi
exec "$repo/scripts/run.sh"
