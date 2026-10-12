#!/usr/bin/env bash
# Build + install upstream Darling (M0). Run AFTER build/darling-src clone completes.
# Usage: ./tools/build-darling.sh [cmake-extra-args...]
set -euo pipefail
SRC="$(dirname "$0")/../build/darling-src"
[ -d "$SRC/.git" ] || { echo "FAIL: $SRC not cloned yet (clone still running?)"; exit 1; }
cd "$SRC"
./tools/uninstall || true
mkdir -p build && cd build
# 64-bit only (LoL is 64-bit; skips multilib pain). Drop the flag if you need i386.
cmake .. -DTARGET_i386=OFF "$@" 2>&1 | tail -5
make -j"$(nproc)" 2>&1 | tail -5
echo "=== installing (needs sudo; run manually if this fails) ==="
sudo make install
darling --version || true
echo "M0 gate: try 'darling shell uname -a' and 'darling shell sw_vers'"
