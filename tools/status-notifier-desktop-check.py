#!/usr/bin/env python3
"""Opt-in real-session DBusMenu -> guest AppKit integration check (no Riot)."""
import argparse
import ast
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
READY = re.compile(r'^STATUS_DESKTOP_READY bus=(:[0-9]+\.[0-9]+) click=([1-9][0-9]*) '
                   r'blocked=([1-9][0-9]*) finish=([1-9][0-9]*)$', re.MULTILINE)


def parse_ready(text):
    match = READY.search(text)
    if not match:
        return None
    name, *ids = match.groups()
    if len(set(ids)) != 3 or any(int(value) > 2147483647 for value in ids):
        raise ValueError('invalid probe menu IDs')
    return name, *ids


def manual_outcome(text):
    """Do not turn a missed time window or an unperformed click into a pass."""
    match = re.search(r'^STATUS_DESKTOP_DONE finished=([01]) clicks=([0-9]+) pass=([01])$',
                      text, re.MULTILINE)
    if not match:
        return 'missing_guest_result'
    finished, clicks, passed = map(int, match.groups())
    if finished and clicks == 1 and passed:
        return 'passed'
    if not finished:
        return 'deadline_reached'
    if not clicks:
        return 'finished_without_confirming'
    return 'unexpected_action_count'


def watcher_items(text):
    """Parse the gdbus Properties.Get result as an array of exact strings."""
    match = re.fullmatch(r'\s*\(<\s*(?:@as\s+)?(\[.*\])\s*>,\s*\)\s*', text, re.DOTALL)
    try:
        items = ast.literal_eval(match.group(1)) if match else None
    except (ValueError, SyntaxError):
        items = None
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise RuntimeError('unexpected RegisteredStatusNotifierItems: ' + repr(text))
    return items


def watcher_contains(text, name):
    # Zorin's local AppIndicator uses busName@objectPath; KDE uses concatenation.
    return any(item in (name + '/StatusNotifierItem', name + '@/StatusNotifierItem')
               for item in watcher_items(text))


def cleanup(process, completed, binary, previous):
    if process is not None and process.poll() is None:
        try:
            process.kill()
            process.wait(timeout=3)
        except PermissionError as error:
            print('probe cleanup permission denied: ' + str(error), file=sys.stderr)
    if process is not None and not completed:
        for pid, identity in owned_guests(binary).items():
            if pid not in previous and owned_guests(binary).get(pid) == identity:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError as error:
                    print('probe cleanup permission denied: ' + str(error), file=sys.stderr)


def owned_guests(binary):
    found = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.joinpath('exe').readlink().name != 'mldr':
                continue
            if str(binary) not in entry.joinpath('maps').read_text():
                continue
            fields = entry.joinpath('stat').read_text().rsplit(')', 1)[1].split()
            found[int(entry.name)] = fields[19]
        except OSError:
            pass
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop', action='store_true',
                        help='allow a temporary neutral tray item on the real desktop bus')
    parser.add_argument('--manual', action='store_true',
                        help='wait up to 3 minutes for real user clicks; do not synthesize menu events')
    parser.add_argument('--manual-timeout', type=int, metavar='SECONDS',
                        help='manual guest deadline, 30..900 seconds (default 180)')
    args = parser.parse_args(argv)
    if not args.desktop:
        parser.error('requires --desktop; this check uses the real session bus')
    if args.manual_timeout is not None and (not args.manual or not 30 <= args.manual_timeout <= 900):
        parser.error('--manual-timeout requires --manual and must be 30..900 seconds')
    manual_timeout = args.manual_timeout if args.manual_timeout is not None else 180
    config = json.loads((ROOT / 'build/config.json').read_text())
    binary = ROOT / 'build/status-notifier-appkit-check'
    framework = ROOT / 'build/darling-src/build/src/external/cocotron/AppKit/AppKit'
    wrapper = ROOT / 'build/libDarlingStatusNotifier.dylib'
    native = ROOT / 'build/libdarling-status-notifier.so'
    for artifact in (binary, framework, wrapper, native):
        if not artifact.is_file():
            parser.error('build artifact is missing: ' + str(artifact))
    darling = shutil.which('darling')
    if not darling:
        parser.error('darling is not installed')
    # Staging only: never write to the prefix's framework overlay.
    stage = ROOT / 'build/status-notifier-stage'
    destination = stage / 'AppKit.framework'
    if not destination.exists():
        shutil.copytree(Path(config['prefix']) / config['guest_home'].lstrip('/') /
                        'RuntimeFrameworks/AppKit.framework', destination, symlinks=True)
    shutil.copy2(framework, destination / 'Versions/C/AppKit')
    log = ROOT / 'build/status-notifier-desktop-check.log'
    guest_root = '/Volumes/SystemRoot' + str(ROOT)
    environment = dict(os.environ, DPREFIX=config['prefix'])
    previous = owned_guests(binary)
    if previous:
        parser.error('this probe is already running')

    def call(destination, path, method, *values, check=True):
        return subprocess.run(['gdbus', 'call', '--session', '--dest', destination,
                               '--object-path', path, '--method', method, '--', *values],
                              text=True, capture_output=True, timeout=5, check=check)

    def eventually(predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.05)
        raise RuntimeError('probe timed out; see ' + str(log))

    # Ensure a real indicator host exists before registering anything.
    host = call('org.kde.StatusNotifierWatcher', '/StatusNotifierWatcher',
         'org.freedesktop.DBus.Properties.Get', 'org.kde.StatusNotifierWatcher',
         'IsStatusNotifierHostRegistered')
    if 'true' not in host.stdout:
        parser.error('no registered StatusNotifier host on this session bus')
    process = None
    completed = False
    try:
        with log.open('w') as output:
            process = subprocess.Popen([
                darling, 'shell', 'env',
                'DYLD_FRAMEWORK_PATH=' + guest_root + '/build/status-notifier-stage:' +
                config['guest_home'] + '/RuntimeFrameworks',
                'DYLD_LIBRARY_PATH=' + config['guest_home'] + '/RuntimeLibraries',
                'DARLING_STATUS_NOTIFIER_LIBRARY=' + guest_root + '/build/libDarlingStatusNotifier.dylib',
                'STATUS_CHECK_DESKTOP=1',
                *(['STATUS_CHECK_MANUAL=1', 'STATUS_CHECK_MANUAL_SECONDS=' + str(manual_timeout)]
                  if args.manual else []),
                guest_root + '/build/status-notifier-appkit-check',
            ], env=environment, stdout=output, stderr=subprocess.STDOUT)
            name, click, blocked, finish = eventually(
                lambda: parse_ready(log.read_text(errors='replace')), timeout=15)

            def item_property(key):
                return call(name, '/StatusNotifierItem', 'org.freedesktop.DBus.Properties.Get',
                            'org.kde.StatusNotifierItem', key).stdout

            # Resolving the probe's unique name and title on this bus proves
            # that the guest bridge selected the host session we are testing.
            if 'Darling tray desktop probe' not in item_property('Title'):
                raise RuntimeError('probe identity/bus mismatch')
            if "'/Menu'" not in item_property('Menu'):
                raise RuntimeError('probe did not export its menu')
            if "<''>" not in item_property('IconName'):
                raise RuntimeError('theme icon would mask the probe pixel data')
            if '(22, 22,' not in item_property('IconPixmap'):
                raise RuntimeError('probe image was not exported as a 22x22 pixmap')
            observed = None
            def registered():
                nonlocal observed
                observed = call('org.kde.StatusNotifierWatcher', '/StatusNotifierWatcher',
                    'org.freedesktop.DBus.Properties.Get', 'org.kde.StatusNotifierWatcher',
                    'RegisteredStatusNotifierItems').stdout
                return watcher_contains(observed, name)

            try:
                eventually(registered)
            except RuntimeError as error:
                raise RuntimeError(f'{error}; RegisteredStatusNotifierItems observed: {observed!r}') from error

            def menu(method, *values):
                return call(name, '/Menu', 'com.canonical.dbusmenu.' + method, *values).stdout

            layout = menu('GetLayout', '0', '-1', '[]')
            if 'Confirmar ação de teste' not in layout:
                raise RuntimeError('guest menu not visible on host bus')
            if args.manual:
                print('STATUS_DESKTOP_MANUAL_READY: ícone temporário de teste registrado no KDE.', flush=True)
                print('Abra o menu com o botão direito; clique UMA VEZ em "Confirmar ação de teste".', flush=True)
                print('Reabra o menu: confira "Ação confirmada" e o item desabilitado em cinza.', flush=True)
                print('Depois clique em "Finalizar teste". Limite: ' + str(manual_timeout) + ' segundos.', flush=True)
            else:
                current = re.search(r'Atualização dinâmica ([0-9]+)', layout)
                if not current:
                    raise RuntimeError('dynamic delegate label not exported')
                menu('AboutToShow', '0')
                def refreshed():
                    value = re.search(r'Atualização dinâmica ([0-9]+)',
                                      menu('GetLayout', '0', '-1', '[]'))
                    return value and int(value.group(1)) > int(current.group(1))
                eventually(refreshed)
                menu('Event', blocked, 'clicked', '<0>', '0')
                menu('Event', click, 'clicked', '<0>', '0')
                eventually(lambda: 'Ação confirmada' in menu('GetLayout', '0', '-1', '[]'))
                menu('Event', finish, 'clicked', '<0>', '0')
            result = process.wait(timeout=manual_timeout + 15 if args.manual else 8)
            text = log.read_text(errors='replace')
            outcome = manual_outcome(text) if args.manual else None
            if (not args.manual and (result or 'STATUS_DESKTOP_DONE finished=1 clicks=1 pass=1' not in text)) or \
                    (args.manual and (outcome == 'missing_guest_result' or (outcome == 'passed' and result))):
                raise RuntimeError('guest action/run-loop test failed; see ' + str(log))
            eventually(lambda: 'false' in call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                'org.freedesktop.DBus.NameHasOwner', name).stdout)
            try:
                eventually(lambda: not registered())
            except RuntimeError as error:
                raise RuntimeError(f'{error}; RegisteredStatusNotifierItems observed: {observed!r}') from error
            completed = True
            if args.manual:
                if outcome != 'passed':
                    print('STATUS_DESKTOP_MANUAL_INCOMPLETE reason=' + outcome + ' removal=1')
                    print('Verificação manual incompleta; não foi marcada como aprovada. Log: ' + str(log))
                    return 2
                print('STATUS_DESKTOP_MANUAL_CHECK bus=1 kde_registration=1 user_action=1 main_thread=1 removal=1')
            else:
                print('STATUS_DESKTOP_CHECK bus=1 kde_registration=1 dbus_to_guest=1 '
                      'main_thread=1 about_to_show=1 menu_update=1 removal=1')
    finally:
        cleanup(process, completed, binary, previous)
        # Deliberately never shut down a shared Darling session here.


if __name__ == '__main__':
    raise SystemExit(main())
