#!/bin/sh
# Run stock Electron 22 (Chromium 108) against a local self-signed TLS server.
# Usage: run-riot-chromium108-tls-repro.sh <0|1 ignore-certificate-errors> [extra Electron args]
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ignore=${1:-1}; shift || true
work=/tmp/riot-tls-repro; mkdir -p "$work"
[ -f "$work/c.pem" ] || openssl req -x509 -newkey rsa:2048 -nodes -keyout "$work/k.pem" -out "$work/c.pem" \
    -days 30 -subj "/CN=rclient" -addext "subjectAltName=IP:127.0.0.1" 2>/dev/null
port=47311
python3 "$root/tools/riot-chromium108-tls-server.py" "$work/c.pem" "$work/k.pem" "$port" > "$work/server.log" 2>&1 &
server=$!
trap 'kill $server 2>/dev/null || true' EXIT
rm -f "$work/netlog.json"
env -u ELECTRON_RUN_AS_NODE DYLD_INSERT_LIBRARIES="${TLS_REPRO_INSERT-}" EGL_PLATFORM=x11 DISPLAY="${DISPLAY:-:1}" \
    DYLD_LIBRARY_PATH=@GUEST_HOME@/RuntimeLibraries DYLD_FRAMEWORK_PATH=@GUEST_HOME@/RuntimeFrameworks \
    TLS_REPRO_PORT=$port TLS_REPRO_IGNORE=$ignore \
    timeout -k 3 60 darling "$HOME/.darling/Applications/Electron.app/Contents/MacOS/Electron" \
    "/Volumes/SystemRoot$root/tools/riot-chromium108-tls-repro" \
    "--log-net-log=/Volumes/SystemRoot$work/netlog.json" "$@" > "$work/electron.log" 2>&1 < /dev/null || true
grep -a "TLSREPRO" "$work/electron.log" || true
cat "$work/server.log"
