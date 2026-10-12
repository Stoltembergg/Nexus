#!/bin/sh
# Install the tested CGL bridge as a per-user framework override.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
guest_home=${RIOT_GUEST_HOME:-$HOME/.darling@GUEST_HOME@}
python3 "$project_dir/tools/build-m58f327-opengl.py"
darling shutdown
framework="$guest_home/RuntimeFrameworks/OpenGL.framework"
if [ ! -d "$framework" ]; then
    cp -a @DARLING_SDK@/System/Library/Frameworks/OpenGL.framework "$framework"
fi
binary="$framework/Versions/A/OpenGL"
if [ ! -f "$binary.before-m327" ]; then
    cp -p "$binary" "$binary.before-m327"
fi
install -m755 "$project_dir/build/m327-OpenGL" "$binary.next"
mv "$binary.next" "$binary"
