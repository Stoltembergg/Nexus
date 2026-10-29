#!/usr/bin/env python3
"""Isolated A/B artifacts and opt-in neutral probe; never installs anything."""
import argparse
import hashlib
import ast
import json
import os
from pathlib import Path
import re
import select
import shlex
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'build/dbusmenu-properties-experiment/ab'
CONFIG = json.loads((ROOT / 'build/config.json').read_text())
GUEST = '/Volumes/SystemRoot'
sys.path.insert(0, str(ROOT / 'tools'))
from probe_prefix import ProbePrefix


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'gio-2.0'], text=True))
    for name, menu in [('control', ROOT / 'tools/darling-dbus-menu.c'),
                       ('corrected', ROOT / 'experimental/dbusmenu-properties/darling-dbus-menu.c')]:
        folder = OUT / name
        folder.mkdir(exist_ok=True)
        host = folder / 'libdarling-status-notifier.so'
        subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fPIC', '-shared', '-pthread',
                        '-I' + str(ROOT / 'tools'), str(ROOT / 'tools/darling-status-notifier.c'), str(menu),
                        str(ROOT / 'tools/darling-menu-actions.c'),
                        '-o', str(host), *flags], check=True)
        subprocess.run(['clang', '-target', 'x86_64-apple-macosx11.0', '-fuse-ld=lld', '-dynamiclib',
                        '-nostdlib', '-O2', '-Wall', '-Wextra', '-Werror', '-isysroot', CONFIG['sdk'],
                        '-I' + str(ROOT / 'build/darling-src/src/startup/mldr/elfcalls'),
                        '-DDARLING_STATUS_HOST_LIBRARY="' + str(host) + '"', '-Wl,-undefined,dynamic_lookup',
                        '-Wl,-install_name,@rpath/libDarlingStatusNotifier.dylib',
                        str(ROOT / 'tools/status-notifier-native-wrapper.c'), '-o', str(folder / 'wrapper.dylib')], check=True)
    make = ROOT / 'build/darling-src/build/src/external/cocotron/AppKit/CMakeFiles/AppKit.dir/flags.make'
    defs = {}
    for line in make.read_text().splitlines():
        if line.startswith('C_') and ' = ' in line:
            key, value = line.split(' = ', 1)
            defs[key] = shlex.split(value)
    subprocess.run(['clang', *defs['C_DEFINES'], *defs['C_INCLUDES'], *defs['C_FLAGS'], '-UNDEBUG',
                    '-Wno-macro-redefined', '-c', str(ROOT / 'experimental/dbusmenu-properties/ab-probe.m'),
                    '-o', str(OUT / 'probe.o')], check=True)
    subprocess.run(['clang', '-target', 'x86_64-apple-macosx11.0', '-fuse-ld=lld', '-nostdlib',
                    '-isysroot', CONFIG['sdk'], str(OUT / 'probe.o'), '-lSystem', '-lobjc',
                    '-framework', 'AppKit', '-framework', 'Foundation', '-o', str(OUT / 'probe')], check=True)
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    str(ROOT / 'experimental/dbusmenu-properties/ab-watcher.c'), '-o', str(OUT / 'watcher'), *flags], check=True)
    print('BUILD_OK isolated_control_corrected_probe_watcher=1')


def guest_command(variant, seconds, bus, owner):
    stage = ROOT / 'build/status-count-title-diagnostic'
    home = Path(CONFIG['prefix']) / CONFIG['guest_home'].lstrip('/')
    wrapper = OUT / variant / 'wrapper.dylib'
    for p in (stage / 'AppKit.framework/Versions/C/AppKit', wrapper, OUT / 'probe', OUT / variant / 'libdarling-status-notifier.so'):
        if not p.is_file():
            raise RuntimeError('missing artifact; run build first')
    prefix = owner.prefix
    if len(os.fsencode(str(prefix / 'var/run/shellspawn.sock'))) >= 108:
        raise RuntimeError('private prefix socket path too long')
    env = dict(os.environ, DPREFIX=str(prefix))
    command = ['darling', 'shell', 'env', 'DBUS_SESSION_BUS_ADDRESS=' + bus,
               'DYLD_FRAMEWORK_PATH=' + GUEST + str(stage) + ':' + GUEST + str(home / 'RuntimeFrameworks'),
               'DYLD_LIBRARY_PATH=' + GUEST + str(home / 'RuntimeLibraries'),
               'DARLING_STATUS_NOTIFIER_LIBRARY=' + GUEST + str(wrapper),
               'SEQUENCE_VARIANT=' + variant,
               'SEQUENCE_TEST_SECONDS=' + str(seconds), GUEST + str(OUT / 'probe')]
    return command, env


def read_line(pipe, seconds):
    if not select.select([pipe], [], [], seconds)[0]:
        raise RuntimeError('private watcher timed out')
    line = pipe.readline().decode(errors='replace').strip()
    if not line:
        raise RuntimeError('private watcher exited')
    return line


def initial_name(text):
    matches = re.findall(r'^SEQUENCE_INITIAL bus=(:[0-9]+\.[0-9]+) count=4$', text, re.M)
    return matches[0] if len(matches) == 1 else None


def watcher_registered(text, name):
    match = re.fullmatch(r'\s*\(<\s*(?:@as\s+)?(\[.*\])\s*>,\s*\)\s*', text, re.S)
    try:
        items = ast.literal_eval(match.group(1)) if match else None
    except (ValueError, SyntaxError):
        items = None
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise ValueError('invalid watcher response')
    return name + '@/StatusNotifierItem' in items


def opaque_pixmap(text):
    # SNI pixmaps are width, height and ARGB bytes; only alpha bytes prove opacity.
    images = re.findall(r'\((?:int32\s+)?(\d+),\s*(?:int32\s+)?(\d+),\s*\[([^\]]*)\]\)', text)
    for width, height, data in images:
        tokens = [token.strip() for token in data.split(',') if token.strip()]
        if not all(re.fullmatch(r'(?:byte\s+)?0x[0-9a-fA-F]{2}', token) for token in tokens):
            continue
        pixels = [int(token[-2:], 16) for token in tokens]
        if int(width) > 0 and int(height) > 0 and len(pixels) == int(width) * int(height) * 4:
            if any(alpha == 255 for alpha in pixels[::4]):
                return True
    return False


def desktop_checks(name, call):
    results = dict(watcher_registered=False, status_active=False, icon_opaque=False)
    try:
        watcher = call('org.kde.StatusNotifierWatcher', '/StatusNotifierWatcher',
                       'org.kde.StatusNotifierWatcher', 'RegisteredStatusNotifierItems')
        results['watcher_registered'] = watcher_registered(watcher, name)
        if not results['watcher_registered']:
            return results
        status = call(name, '/StatusNotifierItem', 'org.kde.StatusNotifierItem', 'Status')
        results['status_active'] = bool(re.fullmatch(r"\s*\(<\s*'Active'\s*>,\s*\)\s*", status))
        pixmap = call(name, '/StatusNotifierItem', 'org.kde.StatusNotifierItem', 'IconPixmap')
        results['icon_opaque'] = opaque_pixmap(pixmap)
    except (ValueError, OSError, subprocess.SubprocessError):
        pass
    return results


def _desktop(variant, seconds, bus, owner):
    cmd, env = guest_command(variant, seconds, bus, owner)
    flags = dict(initial=False, watcher_registered=False, status_active=False,
                 icon_opaque=False, populated=False, done=False, exit_ok=False)
    def call(dest, path, interface, prop):
        return subprocess.check_output(['gdbus', 'call', '--session', '--dest', dest,
            '--object-path', path, '--method', 'org.freedesktop.DBus.Properties.Get',
            '--', interface, prop], text=True, timeout=5, stderr=subprocess.DEVNULL)
    with tempfile.TemporaryFile(mode='w+t') as log:
        process = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
        end = time.monotonic() + seconds + 15
        deadline = time.monotonic() + min(seconds, 10)
        while process.poll() is None and time.monotonic() < deadline:
            text = os.pread(log.fileno(), 1024 * 1024, 0).decode(errors='replace')
            name = initial_name(text)
            if name:
                flags['initial'] = True
                flags.update(desktop_checks(name, call))
                break
            time.sleep(.05)
        try:
            result = process.wait(timeout=max(0, end - time.monotonic()))
        except subprocess.TimeoutExpired:
            result = None  # Leave the owned guest and its private prefix intact.
        text = os.pread(log.fileno(), 1024 * 1024, 0).decode(errors='replace')
        flags['populated'] = bool(re.search(r'^SEQUENCE_POPULATED\b', text, re.M))
        flags['done'] = bool(re.search(r'^SEQUENCE_DONE\b', text, re.M))
        flags['exit_ok'] = result == 0
    print('DESKTOP_RESULT ' + ' '.join(k + '=' + str(int(v)) for k, v in flags.items()))
    return all(flags.values())


def _private(variant, owner):
    # Only our own watcher and guest are launched; this bus is created by our parent.
    watcher = subprocess.Popen([str(OUT / 'watcher')], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    process = None
    try:
        assert read_line(watcher.stdout, 8) == 'READY'
        cmd, env = guest_command(variant, 14, os.environ['DBUS_SESSION_BUS_ADDRESS'], owner)
        with tempfile.TemporaryFile(mode='w+t') as log:
            process = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 25
            while True:
                text = os.pread(log.fileno(), 1024 * 1024, 0).decode(errors='replace')
                match = re.search(r'^SEQUENCE_INITIAL bus=(:\d+\.\d+) count=4$', text, re.M)
                if match:
                    break
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('guest did not initialize; raw output withheld')
                time.sleep(.05)
            name = match.group(1)
            assert read_line(watcher.stdout, 8) == 'REGISTER ' + name
            def call(path, method, *args):
                return subprocess.check_output(['gdbus', 'call', '--session', '--dest', name,
                    '--object-path', path, '--method', method, '--', *args], text=True, timeout=5, stderr=subprocess.DEVNULL)
            def menu(method, *args):
                return call('/Menu', 'com.canonical.dbusmenu.' + method, *args)
            def prop(key):
                return call('/StatusNotifierItem', 'org.freedesktop.DBus.Properties.Get', 'org.kde.StatusNotifierItem', key)
            assert "'Active'" in prop('Status')
            pixmap = prop('IconPixmap')
            assert re.search(r'\(22, 22,', pixmap), 'expected 22x22 pixmap'
            # Confirm payload is not entirely transparent; gdbus prints bytes as 0xNN.
            assert re.search(r'0x(?:ff|fe)', pixmap, re.I), 'no opaque pixel found'
            digest = hashlib.sha256(pixmap.encode()).hexdigest()
            expected_title = 'Neutral corrected probe' if variant == 'corrected' else 'Neutral control probe'
            assert expected_title in prop('Title')
            before = menu('GetLayout', '0', '-1', '[]')
            ids = re.findall(r'<\((?:int32 )?(\d+),', before)
            assert len(ids) == 4 and len(set(ids)) == 4
            for ident in ids:
                assert menu('GetProperty', ident, 'label') == "(<''>,)\n"
                assert menu('GetProperty', ident, 'visible') == '(<false>,)\n'
                assert menu('GetProperty', ident, 'enabled') == '(<false>,)\n'
            deadline = time.monotonic() + 12
            while True:
                after = menu('GetLayout', '0', '-1', '[]')
                if 'Primeiro teste' in after:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError('guest did not publish populated snapshot')
                time.sleep(.1)
            assert re.findall(r'<\((?:int32 )?(\d+),', after) == ids
            assert 'Segundo teste' in after and 'Terceiro teste' in after
            for ident in ids:
                assert menu('GetProperty', ident, 'visible') == '(<true>,)\n'
                assert menu('GetProperty', ident, 'enabled') == '(<true>,)\n'
            assert menu('GetProperty', ids[-1], 'label') == "(<''>,)\n"
            assert process.wait(timeout=20) == 0
            rest, _ = watcher.communicate(timeout=18)
            summary = re.search(rb'SIGNALS layouts=(\d+) updates=(\d+) enabled_visible=(\d+) labels=(\d+)', rest)
            assert summary, 'watcher signal summary missing'
            layouts, updates, changed_items, labels = map(int, summary.groups())
            assert layouts >= 2, 'expected initial and transition layout signals'
            assert updates == (0 if variant == 'control' else 2), 'unexpected property signal count'
            assert (changed_items, labels) == ((0, 0) if variant == 'control' else (4, 3)), 'unexpected property signal content'
            print('PRIVATE_PASS variant=' + variant + ' watcher_registered=1 status_active=1 icon_22x22_opaque=1 icon_sha256=' + digest +
                  ' stable_ids=1 hidden_to_visible=1 layouts=' + str(layouts) + ' property_updates=' + str(updates) +
                  ' changed_items=' + str(changed_items) + ' changed_labels=' + str(labels))
    finally:
        # The owned watcher has a 22-second self-expiry; do not stop processes.
        if watcher.poll() is None:
            watcher.communicate(timeout=28)
        if process and process.poll() is None:
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                print('WARNING owned guest still running; prefix retained')


def desktop(variant, seconds, bus):
    owner = ProbePrefix(ROOT, 'ab-')
    try:
        return _desktop(variant, seconds, bus, owner)
    finally:
        owner.cleanup()


def private(variant):
    owner = ProbePrefix(ROOT, 'ab-')
    try:
        return _private(variant, owner)
    finally:
        owner.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['build', 'private', 'desktop'])
    parser.add_argument('--variant', choices=['control', 'corrected', 'both'], default='control')
    parser.add_argument('--seconds', type=int, default=120)
    parser.add_argument('--desktop', action='store_true')
    args = parser.parse_args()
    if args.mode == 'build':
        build()
    elif args.mode == 'private':
        # Force a new session bus, never the user's bus.
        variants = ['control', 'corrected'] if args.variant == 'both' else [args.variant]
        digests = []
        for variant in variants:
            result = subprocess.run(['dbus-run-session', '--', sys.executable, __file__, '_private', variant],
                                    check=True, stdout=subprocess.PIPE, text=True)
            print(result.stdout, end='')
            match = re.search(r'icon_sha256=([0-9a-f]{64})', result.stdout)
            assert match, 'missing icon digest'
            digests.append(match.group(1))
        if len(digests) == 2:
            assert digests[0] != digests[1], 'IconPixmap must differ'
            print('PRIVATE_AB_PASS icon_pixmaps_differ=1')
    else:
        if not args.desktop or args.variant == 'both' or not 10 <= args.seconds <= 180:
            parser.error('desktop requires --desktop and --seconds 10..180')
        bus = os.environ.get('DBUS_SESSION_BUS_ADDRESS')
        if not bus:
            parser.error('desktop session bus not available')
        try:
            passed = desktop(args.variant, args.seconds, bus)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            print('DESKTOP_RESULT setup_ok=0')
            passed = False
        if not passed:
            raise SystemExit(1)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '_private':
        private(sys.argv[2])
    else:
        main()
