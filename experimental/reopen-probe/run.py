#!/usr/bin/env python3
"""Run only in a fresh ProbePrefix; never use or shut down the user's prefix."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
probe = root / 'build/reopen-probe/probe'
if not probe.is_file():
    sys.exit('Build first with python3 experimental/reopen-probe/build.py')
sys.path.insert(0, str(root / 'tools'))
from probe_prefix import ProbePrefix

owner = ProbePrefix(root, 'reopen-')
timed_out = False
try:
    command = ['darling', 'shell', '/Volumes/SystemRoot' + str(probe)]
    process = subprocess.Popen(command, env=dict(os.environ, DPREFIX=str(owner.prefix)))
    try:
        result = process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        timed_out = True
        raise RuntimeError('guest timed out; process not killed; prefix retained at ' + str(owner.prefix))
    if result:
        raise RuntimeError('guest probe failed: exit ' + str(result))
finally:
    if not timed_out and not owner.cleanup():
        raise RuntimeError('private prefix cleanup not verified; retained at ' + str(owner.prefix))
