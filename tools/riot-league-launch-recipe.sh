#!/bin/bash
# darling-lol M632: deterministic League launch recipe (external POST path).
# Boot assumed done (runner started). Steps: context -> attempts -> patch -> launch.
set -u
cd "$(dirname "$0")/.."
EP=""
for i in $(seq 1 60); do
  EP=$(for p in /proc/[0-9]*; do
         if grep -aq 'app-port=' "$p/cmdline" 2>/dev/null && grep -aq 'remoting-auth-token' "$p/cmdline" 2>/dev/null; then
           basename "$p"; break; fi; done | head -1)
  [ -n "$EP" ] && break
  sleep 5
done
[ -z "$EP" ] && { echo "electron main not found"; exit 1; }
P=$(tr '\0' '\n' < "/proc/$EP/cmdline" | grep -o 'app-port=[0-9]*' | cut -d= -f2)
T=$(tr '\0' '\n' < "/proc/$EP/cmdline" | grep -o 'remoting-auth-token=[^ ]*' | cut -d= -f2)
echo "electron=$EP port=$P"
req() { timeout "$3" curl -sk --http1.1 -m "$3" -u "riot:$T" "$@" 2>/dev/null; }
echo "context:  $(req -X PUT -H 'Content-Type: application/json' -d '{"productContext":{"productId":"league_of_legends","patchlineId":"live"}}' -o /dev/null -w '%{http_code}\n' "https://127.0.0.1:$P/player-session-lifecycle/v1/product-context")"
echo "attempts: $(req -X POST -H 'Content-Type: application/json' -d '0' -o /dev/null -w '%{http_code}\n' "https://127.0.0.1:$P/data-store/v1/install-settings/riot-client-app-command/upgrade_attempts")"
# Patch state probe (background; endpoints not responsive while in flight)
ST=$(req "https://127.0.0.1:$P/patch/v1/installs/league_of_legends.live.game_patch" 10 | python3 -c "import json,sys; print(json.load(sys.stdin)['status']['patch']['state'])" 2>/dev/null)
echo "game_patch: $ST"
if [ "$ST" = "out_of_date" ]; then
  ( req -X PUT -H 'Content-Type: application/json' \
      -d '{"url":"https://lol.secure.dyn.riotcdn.net/channels/public/releases/BAA127646F53294E.manifest","headers":{},"tags":["en_GB"],"repair":false,"delete_foreign_paths":false,"max_download_speed":0}' \
      -o /tmp/league-patch-final.out -w '%{http_code}\n' \
      "https://127.0.0.1:$P/patch/v1/installs/league_of_legends.live.game_patch/requests/patch" ) &
fi
echo "launch: $(req -X POST -H 'Content-Type: application/json' -d '{}' -o /tmp/league-launch-final.out -w '%{http_code}\n' "https://127.0.0.1:$P/product-launcher/v1/products/league_of_legends/patchlines/live")"
echo "(long-running: watch the Riot Client log for 'Stopping all patching jobs' then 'Created product session')"
