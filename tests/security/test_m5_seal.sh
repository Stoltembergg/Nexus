#!/bin/sh
# M5 acceptance: main and dlopen()ed __TEXT ranges are sealed against
# mprotect(PROT_WRITE). Requires the Linux mseal(2) syscall (>= 6.10).

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

finish() {
	printf -- '----\n'
	printf 'pass=%d fail=%d skip=%d\n' "$pass" "$fail" "$skip"
	[ "$fail" -eq 0 ]
}

for tool in "$RCODESIGN" "$DARLING"; do
	if [ -z "$tool" ] || [ ! -x "$tool" ]; then
		miss "required tool not found: ${tool:-darling}"
		finish
		exit $?
	fi
done
if ! command -v clang >/dev/null 2>&1; then
	miss "clang not found"
	finish
	exit $?
fi
if [ ! -f "$SDK/usr/include/stdio.h" ]; then
	miss "no SDK headers under $SDK"
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

build() { # source output extra...
	src=$1; out=$2; shift 2
	clang -target x86_64-apple-macosx11.0 -DPLATFORM_MacOSX -D_DARWIN_C_SOURCE \
	    -fuse-ld=lld -nostdlib -isysroot "$SDK" "$src" "$@" -lSystem -o "$out"
}

main=$tmp/test_m5_seal
target=$tmp/libtarget.dylib
if ! build "$here/test_m5_seal.c" "$main"; then
	miss "failed to build the M5 probe"
	finish
	exit $?
fi
if ! build "$here/test_lv_target.c" "$target" -dynamiclib; then
	miss "failed to build the M5 target dylib"
	finish
	exit $?
fi
if ! "$RCODESIGN" sign --binary-identifier m5-probe "$main" >/dev/null 2>&1; then
	miss "failed to sign the M5 probe"
	finish
	exit $?
fi
if ! "$RCODESIGN" sign --binary-identifier m5-target "$target" >/dev/null 2>&1; then
	miss "failed to sign the M5 target"
	finish
	exit $?
fi

guest_root=/Volumes/SystemRoot
outfile=$tmp/out
DARLING_CODESIGN_ENFORCE=enforce timeout 120 "$DARLING" shell \
    "$guest_root$main" "$guest_root$target" >"$outfile" 2>&1
out=$(cat "$outfile")

case "$out" in
*"SEAL_OK"*)
	ok "main and library __TEXT ranges reject mprotect(PROT_WRITE)" ;;
*"main mprotect r=0"*|*"library mprotect r=0"*)
	miss "mseal(2) is not enforced by this kernel: $out" ;;
*)
	bad "M5 probe failed: $out" ;;
esac

finish
