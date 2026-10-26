#!/bin/sh
# Install the graphics libraries already built for the Riot runtime (Metal, QuartzCore,
# libGL, libindium, libiridium) at their normal system locations inside the Darling
# prefix, so they load as Darling's own system libraries instead of only through
# DYLD_LIBRARY_PATH / DYLD_FRAMEWORK_PATH. The bytes are copied unchanged from the
# RuntimeFrameworks / RuntimeLibraries copies installed by install-riot-gpu-runtime.sh;
# nothing is rebuilt, patched or signed here, and nothing about the reported hardware changes.
# The launcher overrides stay in place for now (run-riot-client.sh is untouched).
# The first install backs the prefix files up; repeating it never overwrites a backup.
# --restore puts the backed-up stock files back (files that did not exist are removed).
# Exit the game and both clients first; activate with `darling shutdown`.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$project_dir/tools/runtime-paths.sh"
backups="$prefix_dir/var/db/nexus-lol/graphics-system-backups"
frameworks=System/Library/Frameworks

# source (relative to the guest home) | destination (relative to the prefix)
pairs="RuntimeFrameworks/Metal.framework/Versions/A/Metal|$frameworks/Metal.framework/Versions/A/Metal
RuntimeFrameworks/QuartzCore.framework/Versions/A/QuartzCore|$frameworks/QuartzCore.framework/Versions/A/QuartzCore
RuntimeFrameworks/OpenGL.framework/Versions/A/Libraries/libGL.dylib|$frameworks/OpenGL.framework/Versions/A/Libraries/libGL.dylib
RuntimeLibraries/libindium.dylib|usr/lib/darling/libindium.dylib
RuntimeLibraries/libiridium.dylib|usr/lib/darling/libiridium.dylib"

mode=install
case "${1:-}" in
 "") ;;
 --restore) mode=restore ;;
 *) echo "usage: $0 [--restore]" >&2; exit 2 ;;
esac

if [ "$mode" = install ]; then
 # Refuse a partial install: every source must exist before anything is replaced.
 printf '%s\n' "$pairs" | while IFS='|' read -r source destination; do
  [ -s "$guest_home/$source" ] || { echo "missing $guest_home/$source (run install-riot-gpu-runtime.sh first)" >&2; exit 1; }
 done
fi
python3 "$project_dir/tools/stop-darling-runtime.py"

printf '%s\n' "$pairs" | while IFS='|' read -r source destination; do
 target="$prefix_dir/$destination"
 backup="$backups/$destination"
 if [ "$mode" = restore ]; then
  if [ -f "$backup" ]; then
   install -m755 "$backup" "$target.next" && mv "$target.next" "$target"
  elif [ -f "$backup.absent" ]; then
   rm -f "$target"
  fi
  continue
 fi
 mkdir -p "$(dirname "$target")" "$(dirname "$backup")"
 # Back up the stock file once; a repeated install must not back up its own output.
 if [ ! -f "$backup" ] && [ ! -f "$backup.absent" ]; then
  if [ -f "$target" ]; then cp -p "$target" "$backup"; else : > "$backup.absent"; fi
 fi
 if ! cmp -s "$guest_home/$source" "$target"; then
  install -m755 "$guest_home/$source" "$target.next" && mv "$target.next" "$target"
 fi
done
[ "$mode" = install ] && echo "Graphics libraries installed in $prefix_dir (backups: $backups)" || echo "Stock graphics libraries restored in $prefix_dir"
