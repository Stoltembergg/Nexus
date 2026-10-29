#!/usr/bin/env python3
"""Validate the combined stage on an owned bus and owned Darling prefix only."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tools'))
from probe_prefix import ProbePrefix

spec = importlib.util.spec_from_file_location('ab', root / 'experimental/dbusmenu-properties/ab.py')
ab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ab)
stage = root / 'build/tray-jp2-experiment'
home = Path(ab.CONFIG['prefix']) / ab.CONFIG['guest_home'].lstrip('/')
guest = '/Volumes/SystemRoot'
frameworks = guest + str(stage) + ':' + guest + str(home / 'RuntimeFrameworks')
libraries = guest + str(stage) + ':' + guest + str(home / 'RuntimeLibraries')
owner = ProbePrefix(root, 'cj-')

def command(variant, seconds, bus, owned):
    return (['darling', 'shell', 'env', 'DBUS_SESSION_BUS_ADDRESS=' + bus,
             'DYLD_FRAMEWORK_PATH=' + frameworks, 'DYLD_LIBRARY_PATH=' + libraries,
             'DARLING_STATUS_NOTIFIER_LIBRARY=' + guest + str(stage / 'libDarlingStatusNotifier.dylib'),
             'DARLING_STATUS_MENU_COUNT_TRACE=1', 'SEQUENCE_VARIANT=corrected',
             'SEQUENCE_TEST_SECONDS=' + str(seconds), guest + str(ab.OUT / 'probe')],
            dict(os.environ, DPREFIX=str(owned.prefix)))

try:
    ab.guest_command = command
    ab._private('corrected', owner)
    appkit = subprocess.run(['darling', 'shell', 'env', 'DYLD_PRINT_LIBRARIES=1',
        'DYLD_FRAMEWORK_PATH=' + frameworks, 'DYLD_LIBRARY_PATH=' + libraries,
        'DARLING_STATUS_NOTIFIER_LIBRARY=' + guest + str(stage / 'libDarlingStatusNotifier.dylib'),
        'DARLING_STATUS_MENU_COUNT_TRACE=1', guest + str(root / 'build/status-notifier-appkit-check')],
        env=dict(os.environ, DPREFIX=str(owner.prefix)), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, timeout=60)
    if appkit.returncode or str(stage / 'AppKit.framework') not in appkit.stdout or 'SMCOUNT ' not in appkit.stdout:
        raise RuntimeError('staged AppKit diagnostic probe failed: ' + appkit.stdout[-4000:])
    jp = root / 'build/openjpeg-compat-check'
    cmd = ['darling', 'shell', 'env', 'DYLD_PRINT_LIBRARIES=1',
           'DYLD_FRAMEWORK_PATH=' + frameworks, 'DYLD_LIBRARY_PATH=' + libraries,
           *[guest + str(jp / p) for p in ('icns-probe', 'rgb.icns', 'rgba.icns', 'bad.icns')]]
    result = subprocess.run(cmd, env=dict(os.environ, DPREFIX=str(owner.prefix)),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
    text = result.stdout
    for required in (str(stage / 'Onyx2D.framework'), str(stage / 'libopenjp2.dylib')):
        if required not in text:
            raise RuntimeError('dyld did not confirm staged dependency: ' + required)
    if result.returncode:
        raise RuntimeError('ICNS probe failed: ' + text[-4000:])
    print('COMBINED_ICNS_PASS staged_appkit=1 staged_onyx=1 staged_openjpeg=1')
finally:
    if not owner.cleanup():
        raise RuntimeError('owned namespace cleanup failed')
