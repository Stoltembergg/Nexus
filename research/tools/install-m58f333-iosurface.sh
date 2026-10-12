#!/bin/sh
# Install the paired IOSurface transport override after isolated validation.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
guest_home=${RIOT_GUEST_HOME:-$HOME/.darling@GUEST_HOME@}
python3 "$project_dir/tools/build-m58f333-iosurface.py"
python3 "$project_dir/tools/build-m58f327-opengl.py"
python3 "$project_dir/tools/build-m58f336-quartzcore.py"
darling shutdown
for name in IOSurface OpenGL QuartzCore; do
 framework="$guest_home/RuntimeFrameworks/$name.framework"
 if [ ! -d "$framework" ]; then
  cp -a "@DARLING_SDK@/System/Library/Frameworks/$name.framework" "$framework"
 fi
 binary="$framework/Versions/A/$name"
 if [ ! -f "$binary.before-m333" ]; then cp -p "$binary" "$binary.before-m333"; fi
 case "$name" in
  IOSurface) source="$project_dir/build/m333-IOSurface";;
  OpenGL) source="$project_dir/build/m327-OpenGL";;
  QuartzCore) source="$project_dir/build/m336-QuartzCore";;
 esac
 install -m755 "$source" "$binary.next"
 mv "$binary.next" "$binary"
done
