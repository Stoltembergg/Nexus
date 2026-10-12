#!/bin/sh
# Install the framework fixes from an already configured Darling build.
# Start a fresh Darling container afterwards: running containers retain old files.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_dir="$project_dir/build/darling-src/build"
# The helper below installs darlingserver; rebuild its scheduling fixes first.
make -C "$build_dir/src/external/darlingserver" darlingserver -j12
for component in \
    src/external/xnu/darling/src/libsystem_kernel \
    src/external/dyld \
    src/startup/mldr \
    src/external/Libinfo \
    src/external/corefoundation \
    src/external/compiler-rt/lib/builtins \
    src/frameworks/IOSurface \
    src/frameworks/OpenGL \
    src/frameworks/AVFoundation \
    src/frameworks/CoreServices/src/CarbonCore \
    src/frameworks/Carbon/HIToolbox \
    src/CoreAudio/AudioToolbox \
    src/external/cocotron/Onyx2D \
    src/external/cocotron/CoreGraphics \
    src/external/cocotron/CoreText \
    src/external/cocotron/QuartzCore \
    src/external/cocotron/AppKit
do
    sudo -n /usr/bin/make -C "$build_dir/$component" install -j12
done
sudo -n /usr/local/sbin/darling-lol-install
