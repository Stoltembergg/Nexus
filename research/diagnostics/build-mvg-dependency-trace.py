#!/usr/bin/env python3
"""Build the DIAGNOSTIC-ONLY MVG dependency trace (research/diagnostics).

Never use with a real/main account or with the game connected to live servers.
Not part of any install, build or launch path; refuses to run without
NEXUS_DIAG_ALLOW_INTERPOSE=1.
"""
from pathlib import Path
import os
import sys

if os.environ.get('NEXUS_DIAG_ALLOW_INTERPOSE') != '1':
    sys.exit('refused: diagnostic only; set NEXUS_DIAG_ALLOW_INTERPOSE=1 on a throwaway test setup')
import shlex
import subprocess

root = Path(__file__).resolve().parents[2]
flags_file = root / 'build/darling-src/build/src/external/security/trust/trustd/CMakeFiles/trustd.dir/flags.make'
flags = {}
for line in flags_file.read_text().splitlines():
    if line.startswith('C_') and ' = ' in line:
        name, value = line.split(' = ', 1)
        flags[name] = shlex.split(value)
(root / 'build/diagnostics').mkdir(parents=True, exist_ok=True)
obj = root / 'build/diagnostics/riot-mvg-dependency-trace.o'
subprocess.run(['clang', *flags['C_DEFINES'], *flags['C_INCLUDES'], *flags['C_FLAGS'],
                '-c', str(root / 'research/diagnostics/riot-mvg-dependency-trace.c'), '-o', str(obj)], check=True)
subprocess.run(['clang', '-target', 'x86_64-apple-macosx11.0', '-fuse-ld=lld', '-nostdlib',
                '-dynamiclib', '-isysroot', '@DARLING_SDK@', str(obj), '-lSystem',
                '-framework', 'Security', '-framework', 'CoreFoundation',
                '-framework', 'IOKit', '-o', str(root / 'build/diagnostics/libRiotMvgDependencyTrace.dylib')], check=True)
