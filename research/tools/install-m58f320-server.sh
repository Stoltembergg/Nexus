#!/bin/sh
# Install the built logging correction atomically; leave the live session running.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
candidate="$project_dir/build/darling-src/build/src/external/darlingserver/darlingserver"
target=/usr/local/bin/darlingserver
if [ "$(id -u)" != 0 ]; then
  echo "Run this installer with sudo; $target is root-owned." >&2
  exit 1
fi
test -x "$candidate"
if [ ! -f "$target.before-m320" ]; then
  cp -p "$target" "$target.before-m320"
fi
install -m755 "$candidate" "$target.m320-next"
mv -f "$target.m320-next" "$target"
echo "Server correction installed. The running session is unchanged until Darling restarts."
