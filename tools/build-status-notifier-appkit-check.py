#!/usr/bin/env python3
"""Build the owned AppKit lifecycle probe against the experimental headers."""
import json
from pathlib import Path
import shlex
import subprocess

root = Path(__file__).resolve().parents[1]
folder = root / 'build/darling-src/build/src/external/cocotron/AppKit'
flags = {}
for line in (folder / 'CMakeFiles/AppKit.dir/flags.make').read_text().splitlines():
    if line.startswith('C_') and ' = ' in line:
        name, value = line.split(' = ', 1)
        flags[name] = shlex.split(value)
sdk = json.loads((root / 'build/config.json').read_text())['sdk']
obj = root / 'build/status-notifier-appkit-check.o'
subprocess.run(['clang', *flags['C_DEFINES'], *flags['C_INCLUDES'], *flags['C_FLAGS'],
                '-UNDEBUG', '-Wno-macro-redefined', '-c',
                str(root / 'tools/status-notifier-appkit-check.m'), '-o', str(obj)], check=True)
subprocess.run(['clang', '-target', 'x86_64-apple-macosx11.0', '-fuse-ld=lld',
                '-nostdlib', '-isysroot', sdk, str(obj), '-lSystem', '-lobjc',
                '-framework', 'AppKit', '-framework', 'Foundation',
                '-o', str(root / 'build/status-notifier-appkit-check')], check=True)
