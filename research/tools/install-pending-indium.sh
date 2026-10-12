#!/bin/sh
# Install build/riot-libindium.dylib into the guest runtime. Refuses while a match is running; stops the runtime first.
cd "$(dirname "$0")/.."
for p in /proc/[0-9]*; do
  a0=$(tr '\0' '\n' < "$p/cmdline" 2>/dev/null | head -1)
  case "$a0" in */Game/LeagueOfLegends.app/Contents/MacOS/LeagueofLegends) echo "a match is running (pid ${p#/proc/}): finish it first" >&2; exit 1;; esac
done
unset ELECTRON_RUN_AS_NODE
python3 -I tools/stop-darling-runtime.py </dev/null 2>&1 | tail -1
pgrep -x darlingserver >/dev/null && { echo "darlingserver is still up" >&2; exit 1; }
lib=$HOME/.darling@GUEST_HOME@/RuntimeLibraries/libindium.dylib
cp -p "$lib" "$lib.before-$(date +%Y%m%d-%H%M%S)"
install -m755 build/riot-libindium.dylib "$lib.next" && mv "$lib.next" "$lib" && cmp build/riot-libindium.dylib "$lib" && echo "installed: $lib"
rm -f "$HOME/.darling/tmp/metal-sync-uploads"
