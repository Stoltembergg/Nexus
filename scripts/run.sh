#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo"
python3 scripts/configure.py >/dev/null
if [ -d build/venv/bin ]; then PATH="$repo/build/venv/bin:$PATH"; export PATH; fi
if [ -n "${DISPLAY:-}" ] && command -v xprop >/dev/null 2>&1; then
  python3 "$repo/tools/set-riot-window-icon.py" \
    "$repo/assets/icons/darling-lol-riot-client.png" &
fi
exec sh build/runtime/tools/run-riot-client.sh
