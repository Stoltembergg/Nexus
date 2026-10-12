#!/bin/sh
# darling-lol M57bl: is the browser's rw-s mapping actually the same pages as the
# memfd? For each darling-mementry mapping in the browser, read the SAME offsets
# twice: once via /proc/<pid>/maps-backed /proc/<pid>/mem and once via the
# memfd (/proc/<pid>/fd/<n>), and compare.
set -u

out=/tmp/opencode/m57-alias.log
seconds=${1:-40}
: > "$out"
start=$(date +%s)

while [ $(( $(date +%s) - start )) -lt "$seconds" ]; do
    for p in $(pgrep -u "$(id -u)" 2>/dev/null); do
        [ -r "/proc/$p/maps" ] || continue
        case "$(cat /proc/$p/comm 2>/dev/null)" in
            CrBrowserMain|Electron|darlingserver|CrGpuMain|CrRendererMain) ;;
            *) continue ;;
        esac
        grep "memfd:darling-mementry" "/proc/$p/maps" 2>/dev/null | while read -r rng perms o1 o2 ino rest; do
            start_h=${rng%%-*}
            s=$((16#$start_h))
            # Read the process's own mapping (first 4 KiB of the range).
            pm=$(dd if="/proc/$p/mem" bs=4096 skip=$((s/4096)) count=1 2>/dev/null | tr -d '\0' | wc -c)
            # Find the fd in this process with that inode and read the same offset.
            fdm=""
            for fd in $(ls "/proc/$p/fd" 2>/dev/null); do
                if [ "$(stat -Lc %i "/proc/$p/fd/$fd" 2>/dev/null)" = "$ino" ]; then fdm="$fd"; break; fi
            done
            if [ -n "$fdm" ]; then
                fm=$(head -c 4096 "/proc/$p/fd/$fdm" 2>/dev/null | tr -d '\0' | wc -c)
            else
                fm="?"
            fi
            printf 'pid=%s comm=%s ino=%s perms=%s mem_nonzero=%s fd=%s memfd_nonzero=%s\n' \
                "$p" "$(cat /proc/$p/comm 2>/dev/null)" "$ino" "$perms" "$pm" "$fdm" "$fm" >> "$out"
        done
    done
    sleep 0.4
done

echo "=== distinct observations ==="
sort -u "$out" | sed 's/^.*comm=//' | sort -u
