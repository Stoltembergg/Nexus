#!/bin/bash
# tools/darling-clean.sh — reclaim a wedged Darling container.
# Background: timeout(1) cannot kill Darling payloads; orphaned payloads
# and their containers wedge all future sessions (silent exit-1 failures).
# This kills payloads first, then container inits, then verifies.
# Usage: ./tools/darling-clean.sh [pattern]  (default pattern: Riot|League|mldr)
PAT="${1:-Riot|League|mldr}"
echo "--- payloads ($PAT) ---"
for p in $(ps -eo pid,args | grep -E "$PAT" | grep -v grep | awk '{print $1}'); do
    kill -9 $p 2>/dev/null && echo "killed $p"
done
sleep 2
echo "--- container inits ---"
for p in $(ps -eo pid,args | grep -E "/sbin/launchd|/usr/libexec/shellspawn" | grep -v grep | awk '{print $1}'); do
    kill -9 $p 2>/dev/null && echo "killed $p"
done
sleep 2
LEFT=$(ps -eo pid,args | grep -iE "launchd|shellspawn|RiotClient|LeagueClient|mldr" | grep -v grep | wc -l)
echo "leftovers: $LEFT"
echo "--- stale member check ---"
MPID=$(cat ~/.darling/var/run/memberd.pid 2>/dev/null)
if [ -n "$MPID" ]; then
    if ! ps -o args -p "$MPID" 2>/dev/null | grep -qiE "launchd|darling|mldr"; then
        echo "STALE memberd.pid=$MPID ($(ps -o comm= -p $MPID 2>/dev/null)); removing runtime files"
        rm -f ~/.darling/var/run/memberd.pid ~/.darling/var/run/.systemStarterRunning ~/.darling/var/run/utmpx ~/.darling/var/run/shellspawn.sock
    else
        echo "memberd.pid=$MPID looks valid"
    fi
fi
# darling-lol: stale .init.pid (prefix ROOT, not var/run) poisons every new
# session with "Cannot open mnt namespace file" — joinNamespace on a dead
# pid; the PID is often recycled by an unrelated process so kill(0) passes
# and the wrapper proceeds anyway. Always purge it (M14j lesson 2026-09-16).
if [ -f ~/.darling/.init.pid ]; then
    echo "removing stale .init.pid=$(cat ~/.darling/.init.pid 2>/dev/null)"
    rm -f ~/.darling/.init.pid
fi
echo "--- verify ---"
timeout -k 5 25 darling shell /bin/echo DARLING-CLEAN-OK < /dev/null 2>&1 | grep -a "DARLING-CLEAN-OK" && echo VERIFIED || echo STILL-BROKEN
