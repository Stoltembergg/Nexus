#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
out=build/dbusmenu-properties-experiment
mkdir -p "$out"
flags=$(pkg-config --cflags --libs gio-2.0)
cc -std=c11 -O2 -Wall -Wextra -Werror -fPIC -shared -pthread -Itools \
  tools/darling-status-notifier.c experimental/dbusmenu-properties/darling-dbus-menu.c \
  tools/darling-menu-actions.c \
  -o "$out/libdarling-status-notifier.so" $flags
cc -std=c11 -O2 -Wall -Wextra -Werror -Itools \
  experimental/dbusmenu-properties/test.c tools/darling-menu-actions.c \
  -o "$out/test" $flags
G_DEBUG=fatal-warnings "$out/test"
python3 experimental/dbusmenu-properties/probe.py
printf '%s\n' "PASS: $out/libdarling-status-notifier.so"
