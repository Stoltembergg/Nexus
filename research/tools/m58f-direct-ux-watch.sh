#!/usr/bin/env bash
# darling-lol M58f round 2: capture the B1 SIGTRAP (sig=5 code=128) specifically.
# Fixes vs m58f-run.sh: only sig=5 stops the loop (the sig=6 CrUtilityMain abort
# and sig=4 aborts are logged but don't count), wedged rounds get SIGKILLed via
# `timeout -k`, and dserver health is reported per round.
set -u
runs=${M58F_ROUNDS:-6}
work=/tmp/opencode/m58f
mapdir=$work/maps
mkdir -p "$mapdir"   # keep round-1 maps; rm -rf only the per-round logs below

(
    while [ ! -e /tmp/opencode/m58f-sampler.die ]; do
        for p in $(pgrep -x mldr); do
            if grep -qa "Electron" "/proc/$p/cmdline" 2>/dev/null; then
                cp "/proc/$p/maps" "$mapdir/${p}_$(date +%s%N)" 2>/dev/null
            fi
        done
        ls -1t "$mapdir"/* 2>/dev/null | tail -n +301 | xargs -r rm -f
        sleep 0.2
    done
) &
sampler=$!
trap 'kill $sampler 2>/dev/null; rm -f /tmp/opencode/m58f-sampler.die' EXIT
rm -f /tmp/opencode/m58f-sampler.die

b1=0
for i in $(seq 1 "$runs"); do
    echo "=== round $i $(date -Is)"
    /tmp/opencode/cleandarling.sh
    rm -f /dev/shm/*darling-ca* /dev/shm/m58c-* /dev/shm/*cvlink* /tmp/opencode/cvpump.log
    # M58f2: NEVER wrap the launcher in GNU timeout — it TERMs the whole
    # process group (darlingserver + guests die; looks exactly like a
    # container bug). Instead: own session via setsid, and on expiry kill
    # ONLY the launcher pid, then clean the container.
    setsid env -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM DISPLAY=:1 M58_PRES_TRACE=1 \
        darling \
        '@DPREFIX@/Applications/Riot Client.app/Contents/Frameworks/Riot Client.app/Contents/MacOS/Riot Client' \
        --app-port=39061 --remoting-auth-token=DARLINGTEST --app-pid=1 --inspect=9229 \
        '--log-dir=@GUEST_HOME@/Library/Logs/Riot Games/Riot Client' \
        --app-root='/Applications/Riot Client.app' > "$work/r$i.log" 2>&1 &
    lpid=$!
    lend=$((SECONDS + 110))
    # M58f3: liveness via /proc — kill -0 gets EPERM while the setuid
    # launcher holds effective root (it does so for the WHOLE run, so
    # our TERM/KILL bounce too). Cap the round, kill the user-owned
    # guests, and give the launcher a bounded window to fall over.
    while [ -d "/proc/$lpid" ] && [ $SECONDS -lt $lend ]; do sleep 1; done
    if [ -d "/proc/$lpid" ]; then
        kill -TERM $lpid 2>/dev/null
        sleep 5
        pkill -9 -x mldr 2>/dev/null
        pkill -9 -x darlingserver 2>/dev/null
        pkill -9 -x launchd 2>/dev/null
        n=0
        while [ -d "/proc/$lpid" ] && [ $n -lt 15 ]; do sleep 1; n=$((n+1)); done
        [ -d "/proc/$lpid" ] && echo "  (launcher $lpid lingered; continuing)"
        kill -KILL $lpid 2>/dev/null
    fi
    /tmp/opencode/cleandarling.sh
    sleep 1; /tmp/opencode/cleandarling.sh
    modrefs=$(grep -a -c 'MachPortTraits' "$work/r$i.log" || true)
    badsend=$(grep -a -c 'BAD SEND' "$work/r$i.log" || true)
    echo "round $i: MachPortTraits=$modrefs BAD_SEND=$badsend dserver=$(pgrep -c -x darlingserver || true)"
    if grep -a -q 'LOLSIGFAIL .* sig=5 ' "$work/r$i.log"; then
        b1=$((b1+1))
        echo "*** B1 SIGTRAP captured in round $i ***"
        grep -a -A9 'LOLSIGFAIL .* sig=5 ' "$work/r$i.log" | head -20
        grep -a 'LOLSIGFAIL .* sig=5 \|LOLSIGFRAME\|LOLSIGNAME' "$work/r$i.log" > "$work/b1.log"
        python3 @PROJECT_ROOT@/tools/m58e-symbolize.py "$mapdir" "$work/b1.log" | head -80
        break
    fi
    grep -a 'LOLSIGFAIL' "$work/r$i.log" | head -3 || true
done
touch /tmp/opencode/m58f-sampler.die
echo "rounds done: b1=$b1"
