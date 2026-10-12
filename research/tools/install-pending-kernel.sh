#!/bin/sh
# Install build/riot-libsystem_kernel.dylib into the guest runtime. Refuses while a match is running; stops the runtime first
# (files replaced under ~/.darling while it is up are not reliably seen by the guest).
cd "$(dirname "$0")/.."
for p in /proc/[0-9]*; do
  a0=$(tr '\0' '\n' < "$p/cmdline" 2>/dev/null | head -1)
  case "$a0" in */Game/LeagueOfLegends.app/Contents/MacOS/LeagueofLegends) echo "a match is running (pid ${p#/proc/}): finish it first" >&2; exit 1;; esac
done
unset ELECTRON_RUN_AS_NODE
python3 -I tools/stop-darling-runtime.py </dev/null 2>&1 | tail -1
pgrep -x darlingserver >/dev/null && { echo "darlingserver is still up" >&2; exit 1; }
kern=$HOME/.darling@GUEST_HOME@/RuntimeLibraries/libsystem_kernel.dylib
cp -p "$kern" "$kern.before-$(date +%Y%m%d-%H%M%S)"
install -m755 build/riot-libsystem_kernel.dylib "$kern.next" && mv "$kern.next" "$kern" && cmp build/riot-libsystem_kernel.dylib "$kern" && echo "installed: $kern"
