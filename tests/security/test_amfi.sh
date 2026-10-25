#!/bin/sh
# M8 acceptance: unknown AMFI calls fail closed; a non-entitled process
# cannot attach with ptrace. Requires a working Darling installation.

set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/../.." && pwd)
RCODESIGN=${RCODESIGN:-$(command -v rcodesign 2>/dev/null || true)}
if [ -z "$RCODESIGN" ] && [ -x "${HOME:-/nonexistent}/.local/bin/rcodesign" ]; then
	RCODESIGN="$HOME/.local/bin/rcodesign"
fi
DARLING=${DARLING:-$(command -v darling 2>/dev/null || true)}
SDK=${DARLING_SDK_HEADERS:-$repo/build/darling-src/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk}
if [ ! -f "$SDK/usr/include/stdio.h" ]; then
	SDK=${DARLING_SDK:-/usr/local/libexec/darling}
fi

pass=0; fail=0; skip=0
ok()   { printf 'PASS  %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf 'FAIL  %s\n' "$1"; fail=$((fail+1)); }
miss() { printf 'SKIP  %s\n' "$1"; skip=$((skip+1)); }
finish() { printf -- '----\n'; printf 'pass=%d fail=%d skip=%d\n' "$pass" "$fail" "$skip"; [ "$fail" -eq 0 ]; }

for tool in "$RCODESIGN" "$DARLING"; do
	if [ -z "$tool" ] || [ ! -x "$tool" ]; then
		miss "required tool not found: ${tool:-darling}"
		finish
		exit $?
	fi
done
if ! command -v clang >/dev/null 2>&1 || [ ! -f "$SDK/usr/include/stdio.h" ]; then
	miss "clang or SDK headers not found"
	finish
	exit $?
fi

tmp=$(mktemp -d)
started=0
if ! pgrep -x darlingserver >/dev/null 2>&1; then
	started=1
fi
cleanup() {
	rm -rf "$tmp"
	if [ "$started" -eq 1 ]; then
		started=0
		timeout 30 "$DARLING" shutdown >/dev/null 2>&1 || true
	fi
}
trap cleanup EXIT HUP INT TERM

probe=$tmp/test_amfi
if ! clang -target x86_64-apple-macosx11.0 -DPLATFORM_MacOSX -D_DARWIN_C_SOURCE \
    -fuse-ld=lld -nostdlib -isysroot "$SDK" "$here/test_amfi.c" -lSystem -o "$probe"; then
	miss "failed to build the AMFI probe"
	finish
	exit $?
fi
if ! "$RCODESIGN" sign --binary-identifier amfi-probe "$probe" >/dev/null 2>&1; then
	miss "failed to sign the AMFI probe"
	finish
	exit $?
fi

guest_root=/Volumes/SystemRoot
outfile=$tmp/out
DARLING_CODESIGN_ENFORCE=enforce timeout 120 "$DARLING" shell \
    "$guest_root$probe" >"$outfile" 2>&1
out=$(cat "$outfile")

case "$out" in
*"AMFI_OK"*)
	ok "unknown AMFI call is ENOTSUP and non-entitled ptrace is EPERM" ;;
*)
	bad "M8 probe failed: $out" ;;
esac

finish
