#!/bin/sh
# Create/update the GNOME desktop entries and the launcher icons.
#
# This installs one entry per client window class (launcher, Riot Client,
# League client and in-game match), each with its own icon, and refreshes
# the desktop and icon caches. It never asks the user to edit a file.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo"
python3 scripts/configure.py >/dev/null
python3 build/runtime/tools/desktop-entry.py
