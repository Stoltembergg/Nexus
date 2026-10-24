#!/bin/sh
# Ad-hoc sign a Darling runtime tree so the M2 loader gate can enforce.
#
# Usage:
#   sign-darling-runtime.sh [options] [DIR...]
#
#   --sdk             add /usr/local/libexec/darling (needs root)
#   --prefix          add the per-user prefix overlays (RuntimeLibraries,
#                     RuntimeFrameworks) under ~/.darling
#   --dry-run         list what would be signed
#   --force           re-sign files that already have a signature
#   --verify          verify after signing (default)
#   --no-verify       skip the post-signing dc-codesign verify
#   --allow-running   permit signing while darlingserver is running
#   --quiet           only print the summary
#
# With no DIR and no --sdk/--prefix, both defaults are used.
#
# Idempotent: files that already carry a CodeDirectory are skipped unless
# --force. Fat binaries are skipped (the guest target is thin x86-64).
#
# Exit: 0 all good, 1 some file failed, 2 usage/setup error.

set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DCC=${DCC:-$here/dc-codesign/dc-codesign}
RCODESIGN=${RCODESIGN:-$(command -v rcodesign 2>/dev/null || true)}
if [ -z "$RCODESIGN" ] && [ -x "${HOME:-/nonexistent}/.local/bin/rcodesign" ]; then
	RCODESIGN="$HOME/.local/bin/rcodesign"
fi

dry=0
force=0
verify=1
allow_running=0
quiet=0
roots=""
explicit=0

usage() {
	sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
	exit 2
}

while [ $# -gt 0 ]; do
	case "$1" in
	--sdk) roots="$roots /usr/local/libexec/darling"; explicit=1 ;;
	--prefix)
		for d in "$HOME"/.darling/Users/*/RuntimeLibraries "$HOME"/.darling/Users/*/RuntimeFrameworks; do
			[ -d "$d" ] && roots="$roots $d"
		done
		explicit=1 ;;
	--dry-run) dry=1 ;;
	--force) force=1 ;;
	--verify) verify=1 ;;
	--no-verify) verify=0 ;;
	--allow-running) allow_running=1 ;;
	--quiet) quiet=1 ;;
	-h|--help) usage ;;
	-*) echo "sign-darling-runtime.sh: unknown option $1" >&2; usage ;;
	*) roots="$roots $1"; explicit=1 ;;
	esac
	shift
done

if [ "$explicit" -eq 0 ]; then
	roots="/usr/local/libexec/darling"
	for d in "$HOME"/.darling/Users/*/RuntimeLibraries "$HOME"/.darling/Users/*/RuntimeFrameworks; do
		[ -d "$d" ] && roots="$roots $d"
	done
fi

if [ ! -f "$DCC" ] || [ ! -x "$DCC" ]; then
	echo "sign-darling-runtime.sh: dc-codesign not built at $DCC" >&2
	echo "  run: make -C $here" >&2
	exit 2
fi
if [ -z "$RCODESIGN" ] || [ ! -x "$RCODESIGN" ]; then
	echo "sign-darling-runtime.sh: rcodesign not found (install apple-codesign)" >&2
	exit 2
fi

if [ "$allow_running" -eq 0 ] && [ "$dry" -eq 0 ] && pgrep -x darlingserver >/dev/null 2>&1; then
	echo "sign-darling-runtime.sh: darlingserver is running; run 'darling shutdown' first" >&2
	echo "  (or pass --allow-running if you know the tree is not in use)" >&2
	exit 2
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

is_macho() { # path -> prints thin|fat|no
	magic=$(od -An -tx1 -N4 "$1" 2>/dev/null | tr -d ' \n')
	case "$magic" in
	cffaedfe|feedfacf|cefaedfe|feedface) echo thin ;;
	cafebabe|bebafeca|bebafeca) echo fat ;;
	*) echo no ;;
	esac
}

signed=0; skipped=0; failed=0; fat=0; total=0

for root in $roots; do
	if [ ! -d "$root" ]; then
		echo "sign-darling-runtime.sh: not a directory: $root" >&2
		failed=$((failed + 1))
		continue
	fi
	[ "$quiet" -eq 1 ] || echo "== $root =="
	find "$root" -type f > "$tmp/files" 2>/dev/null || true
	while IFS= read -r f; do
		kind=$(is_macho "$f")
		[ "$kind" = no ] && continue
		total=$((total + 1))
		if [ "$kind" = fat ]; then
			fat=$((fat + 1))
			[ "$quiet" -eq 1 ] || echo "skip fat: $f"
			continue
		fi
		if [ "$force" -eq 0 ] && "$DCC" info "$f" >/dev/null 2>&1; then
			skipped=$((skipped + 1))
			continue
		fi
		if [ "$dry" -eq 1 ]; then
			echo "would sign: $f"
			signed=$((signed + 1))
			continue
		fi
		if "$RCODESIGN" sign --binary-identifier "$(basename "$f")" "$f" >/dev/null 2>&1; then
			if [ "$verify" -eq 1 ] && ! "$DCC" verify "$f" >/dev/null 2>&1; then
				echo "verify FAILED: $f" >&2
				failed=$((failed + 1))
				continue
			fi
			signed=$((signed + 1))
			[ "$quiet" -eq 1 ] || echo "signed: $f"
		else
			echo "sign FAILED: $f" >&2
			failed=$((failed + 1))
		fi
	done < "$tmp/files"
done

printf -- '----\n'
printf 'total=%d signed=%d skipped=%d fat=%d failed=%d%s\n' \
	"$total" "$signed" "$skipped" "$fat" "$failed" \
	"$([ "$dry" -eq 1 ] && echo ' (dry-run)')"
[ "$failed" -eq 0 ]
