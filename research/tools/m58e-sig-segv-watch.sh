#!/usr/bin/env bash
# darling-lol M58e: catch + symbolize the intermittent startup SIGSEGV.
# Runs the stock repro repeatedly while sampling /proc/<mldr>/maps from the
# HOST (the LOLSIGFAIL rip is a host address); on LOLSIGFAIL, matches
# rip/ret0 against the newest sample and prints module+offset.
set -u
runs=${M58E_ROUNDS:-8}
work=/tmp/opencode/m58e
mapdir=$work/maps
rm -rf "$work" && mkdir -p "$mapdir"

# continuous sampler
(
    while [ ! -e /tmp/opencode/m58e-sampler.die ]; do
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
trap 'kill $sampler 2>/dev/null; rm -f /tmp/opencode/m58e-sampler.die /tmp/opencode/m58e-sampler.alive' EXIT
rm -f /tmp/opencode/m58e-sampler.die
touch /tmp/opencode/m58e-sampler.alive

caught=0
log="/tmp/opencode/riot-run2/uxd.log"
repro=${M58E_USE_REPRO:-0}
for i in $(seq 1 "$runs"); do
    echo "=== round $i"
    /tmp/opencode/cleandarling.sh
    rm -f /dev/shm/*darling-ca* /dev/shm/m58c-* /dev/shm/*cvlink* /tmp/opencode/cvpump.log
    if [ "${M58E_USE_REPRO:-0}" = "1" ]; then
        DISPLAY=:1 M58_PRES_TRACE=1 M57_REPRO_SECONDS=25 \
            @PROJECT_ROOT@/tools/run-m57-electron-frame-repro.sh \
            >"$work/round$i.log" 2>&1 || true
      else
        env -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM DISPLAY=:1 M58_PRES_TRACE=1 \
            timeout 110 darling \
            '@DPREFIX@/Applications/Riot Client.app/Contents/Frameworks/Riot Client.app/Contents/MacOS/Riot Client' \
            --app-port=39061 --remoting-auth-token=DARLINGTEST --app-pid=1 --inspect=9229 \
            '--log-dir=@GUEST_HOME@/Library/Logs/Riot Games/Riot Client' \
            --app-root='/Applications/Riot Client.app' > "$work/round$i.log" 2>&1 || true
    fi
    if grep -a LOLSIGFAIL /tmp/opencode/riot-run2/uxd.log > /tmp/opencode/m58e-lol.log 2>/dev/null; then
        caught=$((caught+1))
        echo "CRASH in round $i:"
        cat /tmp/opencode/m58e-lol.log
        python3 @PROJECT_ROOT@/tools/m58e-symbolize.py "$mapdir" /tmp/opencode/m58e-lol.log
        [ "$caught" -ge 1 ] && break
    else
        echo "no crash in round $i"
    fi
done
echo "rounds done: crashes=$caught"
