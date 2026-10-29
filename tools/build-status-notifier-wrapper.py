#!/usr/bin/env python3
"""Build the opt-in Mach-O/ELF tray bridge, without installing or stopping apps."""
import json
from pathlib import Path
import subprocess


def build():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / 'build/config.json').read_text())
    output = root / 'build/libDarlingStatusNotifier.dylib'
    subprocess.run([
        'clang', '-target', 'x86_64-apple-macosx11.0', '-fuse-ld=lld',
        '-dynamiclib', '-nostdlib', '-O2', '-Wall', '-Wextra', '-Werror',
        '-isysroot', config['sdk'],
        '-I' + str(root / 'build/darling-src/src/startup/mldr/elfcalls'),
        '-DDARLING_STATUS_HOST_LIBRARY="' + str(root / 'build/libdarling-status-notifier.so') + '"',
        '-Wl,-undefined,dynamic_lookup',
        '-Wl,-install_name,@rpath/libDarlingStatusNotifier.dylib',
        str(root / 'tools/status-notifier-native-wrapper.c'), '-o', str(output),
    ], check=True)
    return output


if __name__ == '__main__':
    print(build())
