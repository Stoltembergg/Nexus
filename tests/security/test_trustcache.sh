#!/bin/sh
# M6 acceptance: local Ed25519 trust store, add/remove, tamper and rollback.
# Runs as root because adding entries requires root-equivalent policy.

set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/../.." && pwd)
RCODESIGN=${RCODESIGN:-$(command -v rcodesign 2>/dev/null || true)}
if [ -z "$RCODESIGN" ] && [ -x "${HOME:-/nonexistent}/.local/bin/rcodesign" ]; then
	RCODESIGN="$HOME/.local/bin/rcodesign"
fi
DARLING=${DARLING:-$(command -v darling 2>/dev/null || true)}
DCC=${DCC:-$repo/tools/dc-codesign/dc-codesign}
TC=${TC:-$repo/tools/dc-trustcache.py}
SDK=${DARLING_SDK_HEADERS:-$repo/build/darling-src/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk}
if [ ! -f "$SDK/usr/include/stdio.h" ]; then
	SDK=${DARLING_SDK:-/usr/local/libexec/darling}
fi
prefix=${DPREFIX:-${HOME:-/root}/.darling}
store=$prefix/var/db/darling/trustcache

pass=0; fail=0; skip=0
ok()   { printf 'PASS  %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf 'FAIL  %s\n' "$1"; fail=$((fail+1)); }
miss() { printf 'SKIP  %s\n' "$1"; skip=$((skip+1)); }
finish() { printf -- '----\n'; printf 'pass=%d fail=%d skip=%d\n' "$pass" "$fail" "$skip"; [ "$fail" -eq 0 ]; }

if [ "$(id -u)" -ne 0 ]; then
	miss "trust-store acceptance requires root"
	finish
	exit $?
fi
for tool in "$RCODESIGN" "$DARLING" "$DCC" "$TC"; do
	if [ -z "$tool" ] || [ ! -x "$tool" ]; then
		miss "required tool not found: ${tool:-unknown}"
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
backup=
if [ -e "$prefix/var/db/darling" ]; then
	backup=$tmp/darling-db
	cp -a "$prefix/var/db/darling" "$backup"
fi
started=0
if ! pgrep -x darlingserver >/dev/null 2>&1; then
	started=1
fi
cleanup() {
	if [ "$started" -eq 1 ]; then
		timeout 30 "$DARLING" shutdown >/dev/null 2>&1 || true
	fi
	rm -rf "$prefix/var/db/darling"
	if [ -n "$backup" ]; then
		mkdir -p "$prefix/var/db"
		cp -a "$backup" "$prefix/var/db/darling"
	fi
	rm -rf "$tmp"
}
trap cleanup EXIT HUP INT TERM

# Start from a clean namespace and store so the server's rollback cache is
# deterministic.
timeout 30 "$DARLING" shutdown >/dev/null 2>&1 || true
started=1
rm -rf "$prefix/var/db/darling"
sleep 1

build() { # source output extra...
	src=$1; out=$2; shift 2
	clang -target x86_64-apple-macosx11.0 -DPLATFORM_MacOSX -D_DARWIN_C_SOURCE \
	    -fuse-ld=lld -nostdlib -isysroot "$SDK" "$src" "$@" -lSystem -o "$out"
}

main=$tmp/main
target=$tmp/target.dylib
if ! build "$here/test_lv_runtime.c" "$main" || \
   ! build "$here/test_lv_target.c" "$target" -dynamiclib; then
	miss "failed to build the trust-store fixtures"
	finish
	exit $?
fi
if ! "$RCODESIGN" generate-self-signed-certificate --person-name "Darling TC" \
    --pem-filename "$tmp/cert" >/dev/null 2>&1; then
	miss "could not generate a self-signed certificate"
	finish
	exit $?
fi
if ! "$RCODESIGN" sign --pem-source "$tmp/cert.crt" --pem-source "$tmp/cert.key" \
    --team-name TEAMA --binary-identifier tc-main \
    --code-signature-flags runtime --code-signature-flags library "$main" >/dev/null 2>&1 || \
   ! "$RCODESIGN" sign --pem-source "$tmp/cert.crt" --pem-source "$tmp/cert.key" \
    --team-name TEAMB --binary-identifier tc-target "$target" >/dev/null 2>&1; then
	miss "failed to sign the trust-store fixtures"
	finish
	exit $?
fi

target_hash=$("$DCC" cdhash "$target") || {
	miss "dc-codesign could not read the target cdhash"
	finish
	exit $?
}

guest_root=/Volumes/SystemRoot
run() {
	outfile=$tmp/out
	# Restart the namespace so the server sees the latest store file and
	# exercises the persisted generation anchor.
	timeout 30 "$DARLING" shutdown >/dev/null 2>&1 || true
	sleep 1
	DARLING_CODESIGN_ENFORCE=enforce timeout 120 "$DARLING" shell \
	    "$guest_root$main" "$guest_root$target" >"$outfile" 2>&1
	cat "$outfile"
}

"$TC" init "$store" >/dev/null || { miss "trust-store init failed"; finish; exit $?; }
"$TC" add "$store" "$target_hash" >/dev/null || { miss "trust-store add failed"; finish; exit $?; }

out=$(run)
case "$out" in
*"DLOPEN_OK"*) ok "signed entry allows a different-team dylib" ;;
*) bad "entry was not honored: $out" ;;
esac

cp "$store" "$tmp/gen2"
"$TC" add "$store" 0000000000000000000000000000000000000000 >/dev/null 2>&1 || true
cp "$store" "$tmp/gen3"
out=$(run)
case "$out" in
*"DLOPEN_OK"*) ok "higher-generation store is still accepted" ;;
*) bad "higher-generation store was rejected: $out" ;;
esac

cp "$tmp/gen2" "$store"
out=$(run)
case "$out" in
*"different team ID"*) ok "generation rollback is rejected" ;;
*) bad "generation rollback was accepted: $out" ;;
esac

# Tamper a valid generation-3 entry byte.
cp "$tmp/gen3" "$store"
python3 - "$store" <<'PY'
import sys
path = sys.argv[1]
data = bytearray(open(path, 'rb').read())
if len(data) < 53:
    raise SystemExit(1)
data[52] ^= 1
open(path, 'wb').write(data)
PY
if "$TC" verify "$store" >/dev/null 2>&1; then
	bad "tampered trust store verifies"
else
	ok "tampered trust store is rejected by the CLI"
fi
out=$(run)
case "$out" in
*"different team ID"*) ok "tampered trust store is ignored by the server" ;;
*) bad "tampered trust store was accepted: $out" ;;
esac

# Remove the signature entirely.
cp "$tmp/gen3" "$store"
python3 - "$store" <<'PY'
import sys
path = sys.argv[1]
data = open(path, 'rb').read()
open(path, 'wb').write(data[:-68])
PY
if "$TC" verify "$store" >/dev/null 2>&1; then
	bad "store without a signature verifies"
else
	ok "store without a signature fails closed"
fi

finish
