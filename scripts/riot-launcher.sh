#!/bin/bash
# Start, stop and inspect the Riot Client session running under Darling.
#
# Usage: scripts/riot-launcher.sh [start|stop|restart|status]
#
# The launcher only ever touches the Darling prefix it owns
# ($HOME/.darling). It never kills processes by name and never interrupts a
# session that is already running.
set -euo pipefail

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
LOG_FILE="$REPO_ROOT/build/riot-launcher.log"
PREFIX="${DPREFIX:-$HOME/.darling}"

mkdir -p "$REPO_ROOT/build"

export DPREFIX="$PREFIX"
export RCLOL_GAMEMODE="${RCLOL_GAMEMODE:-0}"
export RCLOL_REGION="${RCLOL_REGION:-BR}"
export RCLOL_LOCALE="${RCLOL_LOCALE:-pt_BR}"
export RCLOL_CLEAN_ON_EXIT="${RCLOL_CLEAN_ON_EXIT:-0}"
export RCLOL_RECOVER_STALE_CLIENT="${RCLOL_RECOVER_STALE_CLIENT:-0}"
export RCLOL_RECOVER_HIDDEN_CLIENT="${RCLOL_RECOVER_HIDDEN_CLIENT:-0}"
export RCLOL_CLEAN_STALE_HELPERS="${RCLOL_CLEAN_STALE_HELPERS:-0}"
export RCLOL_CLOSE_CLIENT_IN_GAME="${RCLOL_CLOSE_CLIENT_IN_GAME:-0}"
export RCLOL_HIDE_CLIENT_IN_GAME="${RCLOL_HIDE_CLIENT_IN_GAME:-0}"
export PATH="$REPO_ROOT/usr-local/bin:/usr/local/bin:$PATH"

log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*" | tee -a "$LOG_FILE"; }

# Identify this prefix's server by its recorded PID and verified argv, never
# by a broad process-name match.
prefix_server_pid() {
    python3 - "$REPO_ROOT" "$PREFIX" <<'PYCODE'
import importlib.util
import os
from pathlib import Path
import sys

repo = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("nix_stop", repo / "scripts/nix-stop.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
pid = module.prefix_server(Path(sys.argv[2]).resolve())
print(pid if pid else "")
PYCODE
}

server_running() {
    local pid
    pid="$(prefix_server_pid)"
    [ -n "$pid" ]
}

stop_darling() {
    if ! server_running; then
        log "No Darling server is running for this prefix."
        return 0
    fi
    log "Stopping the Darling session of $PREFIX..."
    if ! darling shutdown; then
        log "The shutdown request failed."
        return 1
    fi
    local i
    for ((i = 0; i < 15; i++)); do
        if ! server_running; then
            log "The session has stopped."
            return 0
        fi
        sleep 1
    done
    log "The session is still running; no process was killed by force."
    return 1
}

start_client() {
    if server_running; then
        log "A session is already running; it was not interrupted."
        return 1
    fi
    log "Starting the Riot Client..."
    cd "$REPO_ROOT"
    nohup sh scripts/run.sh >> "$REPO_ROOT/build/riot-runtime.log" 2>&1 &
    local pid=$!
    log "Launcher process started (PID $pid)."
    local i
    for ((i = 0; i < 30; i++)); do
        if server_running; then
            log "Darling is up. The client window appears on its own."
            return 0
        fi
        if ! kill -0 "$pid" 2>/dev/null; then
            log "The launcher exited before the server started; see build/riot-runtime.log."
            return 1
        fi
        sleep 1
    done
    log "The server did not appear in time; see build/riot-runtime.log."
    return 1
}

status_client() {
    echo "=== Status ==="
    echo "Prefix: $PREFIX"
    if server_running; then
        echo "Darling server: RUNNING"
        echo "Riot Client: UNKNOWN"
        echo ""
        echo "The server alone does not prove that the client window is open."
    else
        echo "Darling server: STOPPED"
        echo "Riot Client: STOPPED"
    fi
    return 0
}

case "${1:-}" in
    start)
        start_client
        ;;
    stop)
        stop_darling
        ;;
    restart)
        stop_darling
        sleep 2
        start_client
        ;;
    status)
        status_client
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        echo ""
        echo "  start    - Starts the client without interrupting a running session"
        echo "  stop     - Ends the Darling session of this prefix"
        echo "  restart  - Stops and starts the session again"
        echo "  status   - Shows the state of the session"
        exit 1
        ;;
esac
