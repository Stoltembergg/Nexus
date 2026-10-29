#!/usr/bin/env python3
"""Run only under dbus-run-session: validate the real owned AppKit producer."""
import json
import os
from pathlib import Path
import re
import select
import subprocess
import tempfile
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from probe_prefix import ProbePrefix
config = json.loads((ROOT / 'build/config.json').read_text())
owner = ProbePrefix(ROOT, 'sg-')
base = owner.base
prefix = owner.prefix
log = base / 'guest.log'
guest = '/Volumes/SystemRoot'
home = Path(config['prefix']) / config['guest_home'].lstrip('/')
env = dict(os.environ, DPREFIX=str(prefix))
assert os.environ.get('DBUS_SESSION_BUS_ADDRESS'), 'run only under dbus-run-session'
command = ['darling', 'shell', 'env',
    'DBUS_SESSION_BUS_ADDRESS=' + os.environ['DBUS_SESSION_BUS_ADDRESS'],
    'DYLD_FRAMEWORK_PATH=' + guest + str(ROOT / 'build/status-count-title-diagnostic') + ':' + guest + str(home / 'RuntimeFrameworks'),
    'DYLD_LIBRARY_PATH=' + guest + str(home / 'RuntimeLibraries'),
    'DARLING_STATUS_NOTIFIER_LIBRARY=' + guest + str(ROOT / 'build/libDarlingStatusNotifier.dylib'),
    'SEQUENCE_TEST_SECONDS=14', guest + str(ROOT / 'build/status-sequence-probe/probe')]
monitor = None
try:
    with log.open('w') as output:
        os.chmod(log, 0o600)
        process = subprocess.Popen(command, env=env, stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 25
            while True:
                text = log.read_text(errors='replace')
                match = re.search(r'^SEQUENCE_INITIAL bus=(:\d+\.\d+) count=4$', text, re.M)
                if match: break
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('guest did not start: ' + text)
                time.sleep(0.05)
            name = match.group(1)
            def call(path, method, *args):
                return subprocess.check_output(['gdbus', 'call', '--session', '--dest', name,
                    '--object-path', path, '--method', method, '--', *args], text=True, timeout=5)
            def menu(method, *args):
                return call('/Menu', 'com.canonical.dbusmenu.' + method, *args)
            before = menu('GetLayout', '0', '-1', '[]')
            ids_before = re.findall(r'<\((?:int32 )?(\d+),', before)
            assert len(ids_before) == 4 and len(set(ids_before)) == 4, before
            for ident in ids_before:
                assert menu('GetProperty', ident, 'label') == "(<''>,)\n"
                for prop in ('enabled', 'visible'):
                    assert menu('GetProperty', ident, prop) == '(<false>,)\n'
            monitor = subprocess.Popen(['gdbus', 'monitor', '--session', '--dest', name], stdout=subprocess.PIPE, bufsize=0)
            assert select.select([monitor.stdout], [], [], 5)[0]
            assert b'Monitoring signals' in monitor.stdout.readline()
            observed = b''
            end = time.monotonic() + 12
            while b'.LayoutUpdated ' not in observed:
                assert time.monotonic() < end, observed
                if select.select([monitor.stdout], [], [], 1)[0]:
                    observed += os.read(monitor.stdout.fileno(), 4096)
            after = menu('GetLayout', '0', '-1', '[]')
            assert all(label in after for label in ('Primeiro teste', 'Segundo teste', 'Terceiro teste')), after
            ids = re.findall(r'<\((?:int32 )?(\d+),', after)
            assert ids == ids_before, (before, after)
            for ident in ids:
                for prop in ('enabled', 'visible'):
                    assert menu('GetProperty', ident, prop) == '(<true>,)\n'
            assert "<''>" in menu('GetProperty', ids[-1], 'label')
            time.sleep(1)
            assert menu('GetLayout', '0', '-1', '[]') == after
            assert process.wait(timeout=20) == 0, log.read_text(errors='replace')
            assert 'SEQUENCE_POPULATED count=4' in log.read_text(errors='replace')
            print('GUEST_SEQUENCE_PASS stable_ids=' + ','.join(ids) + ' hidden_empty_disabled=1 visible_enabled=1 three_titles=1 signals=1 static=1 prefix=' + str(prefix))
        finally:
            if monitor:
                monitor.terminate()
                monitor.communicate(timeout=5)
            if process.poll() is None:
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    print('WARNING: owned guest wrapper did not exit; retained prefix: ' + str(prefix))
finally:
    owner.cleanup()
