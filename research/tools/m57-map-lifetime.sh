#!/bin/sh
# darling-lol M57bk: map the lifetime of every darling-mementry region.
#
# Fast host-only sampling: for each darling-mementry memfd, record inode, size,
# non-zero byte count, and which processes have it mapped (and with what flags),
# so we can tell whether the region the consumer reads is the one the producer
# wrote. No guest-side instrumentation.
set -u

out=/tmp/opencode/m57-map-samples.log
seconds=${1:-30}
: > "$out"

start=$(date +%s)
while [ $(( $(date +%s) - start )) -lt "$seconds" ]; do
    # Memfds (holders + contents).
    for p in $(pgrep -u "$(id -u)" 2>/dev/null); do
        [ -d "/proc/$p/fd" ] || continue
        for fd in $(ls "/proc/$p/fd" 2>/dev/null); do
            tgt=$(readlink "/proc/$p/fd/$fd" 2>/dev/null) || continue
            case "$tgt" in
                *memfd:darling-mementry*)
                    ino=$(stat -Lc %i "/proc/$p/fd/$fd" 2>/dev/null) || continue
                    sz=$(stat -Lc %s "/proc/$p/fd/$fd" 2>/dev/null)
                    nz=$(head -c 262144 "/proc/$p/fd/$fd" 2>/dev/null | tr -d '\0' | wc -c)
                    printf 'FD ino=%s size=%s nonzero=%s holder=%s comm=%s\n' \
                        "$ino" "$sz" "$nz" "$p" "$(cat /proc/$p/comm 2>/dev/null)" >> "$out"
                    ;;
            esac
        done
    done
    # Mappings (which process mapped which inode, and how).
    for p in $(pgrep -u "$(id -u)" 2>/dev/null); do
        [ -r "/proc/$p/maps" ] || continue
        grep "memfd:darling-mementry" "/proc/$p/maps" 2>/dev/null | while read -r line; do
            ino=$(printf '%s' "$line" | awk '{print $5}')
            perms=$(printf '%s' "$line" | awk '{print $2}')
            printf 'MAP ino=%s perms=%s pid=%s comm=%s\n' \
                "$ino" "$perms" "$p" "$(cat /proc/$p/comm 2>/dev/null)" >> "$out"
        done
    done
    sleep 0.3
done

echo "=== FD observations (inode size nonzero) ==="
grep '^FD ' "$out" | awk '{print $2, $3, $4}' | sort -u
echo "=== MAP observations (inode perms) ==="
grep '^MAP ' "$out" | awk '{print $2, $3}' | sort -u
