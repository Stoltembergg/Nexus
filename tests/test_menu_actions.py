"""Offline checks of the host-side tray menu actions.

Two parts are covered: the native module that decides which menu entries the
host owns, and the helper that performs the action. Neither part touches a
desktop, a client process or the real session bus.
"""
import ctypes
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / 'tools/riot-menu-action.py'


def load_action():
    """Load the action helper, whose file name is not an importable name."""
    source = ACTION.read_text().replace('@PROJECT_ROOT@', str(ROOT))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader('riot_menu_action', loader=None))
    module.__file__ = str(ACTION)
    exec(compile(source, str(ACTION), 'exec'), module.__dict__)
    return module


class NativeMenuActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all(shutil.which(name) for name in ('cc', 'pkg-config')):
            raise unittest.SkipTest('the native build tools are not installed')
        if subprocess.run(['pkg-config', '--exists', 'gio-2.0']).returncode:
            raise unittest.SkipTest('gio-2.0 development files are not installed')
        cls.directory = tempfile.TemporaryDirectory(prefix='menu-actions-')
        cls.addClassCleanup(cls.directory.cleanup)
        cls.check = Path(cls.directory.name) / 'menu-actions-check'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-I' + str(ROOT / 'tools'),
                        str(ROOT / 'tests/fixtures/menu-actions-check.c'),
                        str(ROOT / 'tools/darling-menu-actions.c'),
                        '-o', str(cls.check),
                        *subprocess.check_output(['pkg-config', '--cflags', '--libs', 'gio-2.0'],
                                                 text=True).split()],
                       check=True, capture_output=True, text=True)

    def observe(self, mode):
        result = subprocess.run([str(self.check), mode], capture_output=True, text=True,
                                timeout=30, check=True)
        values = {}
        entries = []
        for line in result.stdout.splitlines():
            key, _, value = line.partition('=')
            if key == 'entry':
                identifier, parent, flags, label = value.split(':', 3)
                entries.append((int(identifier), int(parent), int(flags), label))
            else:
                values[key] = value
        return values, entries

    def test_disabled_without_a_helper(self):
        values, entries = self.observe('disabled')
        self.assertEqual(values['enabled'], '0')
        self.assertEqual(values['quit'], '0')
        self.assertEqual(values['reopen'], '0')
        self.assertEqual(values['written'], '0')
        self.assertEqual(entries, [])

    def test_enabled_adds_the_two_actions(self):
        values, entries = self.observe('enabled')
        self.assertEqual(values['enabled'], '1')
        self.assertEqual(values['quit'], '1')
        self.assertEqual(values['reopen'], '2')
        self.assertEqual(values['other'], '0')
        self.assertEqual(values['quit_label'], 'Sair')
        self.assertEqual(values['reopen_label'], 'Riot Games')
        self.assertEqual(values['written'], '3')
        self.assertEqual(entries[0], (1000000, 0, 4, ''))
        self.assertEqual(entries[1], (1000001, 0, 3, 'Sair'))
        self.assertEqual(entries[2], (1000002, 0, 3, 'Riot Games'))

    def test_a_guest_entry_is_not_duplicated(self):
        values, entries = self.observe('guest-has-quit')
        self.assertEqual(values['written'], '2')
        self.assertEqual(entries[0][0], 1000000)
        self.assertEqual(entries[1], (1000002, 0, 3, 'Riot Games'))

    def test_nothing_is_added_when_the_guest_has_both(self):
        values, entries = self.observe('guest-has-both')
        self.assertEqual(values['written'], '0')
        self.assertEqual(entries, [])

    def test_the_labels_can_be_changed(self):
        values, entries = self.observe('custom-labels')
        self.assertEqual(values['custom_quit'], '1')
        self.assertEqual(values['custom_reopen'], '2')
        self.assertEqual(values['quit'], '0')
        self.assertEqual(values['reopen'], '0')
        self.assertEqual(entries[1][3], 'Encerrar')
        self.assertEqual(entries[2][3], 'Abrir Riot')


class ActionHelperTests(unittest.TestCase):
    def setUp(self):
        self.module = load_action()
        self.temp = tempfile.TemporaryDirectory(prefix='riot-menu-action-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.prefix = self.base / '.darling'
        self.prefix.mkdir()
        self.socket = self.prefix / '.darlingserver.sock'
        # The helper writes its own log; keep it out of the checkout.
        self.module.LOG_FILE = self.base / 'riot-menu-action.log'

    def fake_process(self, root, pid, executable, socket=None, nspid=None):
        proc = root / str(pid)
        proc.mkdir(parents=True)
        (proc / 'cmdline').write_bytes(executable.encode() + b'\0')
        environment = {}
        if socket is not None:
            environment[self.module.SOCK_VARIABLE] = socket
        (proc / 'environ').write_bytes(b'\0'.join(
            key + b'=' + os.fsencode(value) for key, value in environment.items()))
        (proc / 'status').write_text('Name:\tprocess\n' +
                                     (f'NSpid:\t{pid}\t{nspid}\n' if nspid else ''))
        return proc

    def test_the_prefix_comes_from_the_environment(self):
        os.environ['DPREFIX'] = str(self.prefix)
        self.addCleanup(os.environ.pop, 'DPREFIX', None)
        self.assertEqual(self.module.session_prefix(), self.prefix.resolve())

    def test_a_relative_prefix_is_refused(self):
        os.environ['DPREFIX'] = 'relative/path'
        self.addCleanup(os.environ.pop, 'DPREFIX', None)
        with self.assertRaises(SystemExit):
            self.module.session_prefix()

    def test_dedicated_prefix_and_conflicts(self):
        key = 'DARLING_STATUS_MENU_PREFIX'
        socket_key = os.fsdecode(self.module.SOCK_VARIABLE)
        with patch.dict(os.environ, {key: str(self.prefix), 'HOME': '/guest/home'}, clear=True):
            self.assertEqual(self.module.session_prefix(), self.prefix.resolve())
            os.environ['DPREFIX'] = str(self.prefix / '..' / self.prefix.name)
            os.environ[socket_key] = str(self.socket)
            self.assertEqual(self.module.session_prefix(), self.prefix.resolve())
            os.environ['DPREFIX'] = str(self.base / 'other')
            with self.assertRaises(SystemExit):
                self.module.session_prefix()
            os.environ['DPREFIX'] = str(self.prefix)
            os.environ[socket_key] = str(self.base / 'other' / '.darlingserver.sock')
            with self.assertRaises(SystemExit):
                self.module.session_prefix()
        for invalid in ('', 'relative/path'):
            with self.subTest(invalid=invalid), patch.dict(os.environ, {key: invalid}, clear=True):
                with self.assertRaises(SystemExit):
                    self.module.session_prefix()

    def test_launcher_exports_dedicated_prefix_after_runtime_paths(self):
        source = (ROOT / 'tools/run-riot-client.sh').read_text()
        runtime = '. "$runner_dir/runtime-paths.sh"'
        export = 'export DARLING_STATUS_MENU_PREFIX="$prefix_dir"'
        self.assertIn(export, source)
        self.assertLess(source.index(runtime), source.index(export))

    def test_prefix_from_inherited_loader_socket(self):
        socket_key = os.fsdecode(self.module.SOCK_VARIABLE)
        with patch.dict(os.environ, {socket_key: str(self.socket), 'HOME': '/guest/home'}, clear=True):
            self.assertEqual(self.module.session_prefix(), self.prefix.resolve())
            os.environ['DPREFIX'] = str(self.prefix)
            self.assertEqual(self.module.session_prefix(), self.prefix.resolve())
            os.environ['DPREFIX'] = str(self.base / 'another-prefix')
            with self.assertRaises(SystemExit):
                self.module.session_prefix()

    def test_prefix_rejects_invalid_socket_and_missing_identity(self):
        socket_key = os.fsdecode(self.module.SOCK_VARIABLE)
        for socket in ('relative/.darlingserver.sock', str(self.prefix / 'wrong.sock'),
                       str(self.socket) + '/', ''):
            with self.subTest(socket=socket), patch.dict(os.environ, {
                    socket_key: socket, 'DPREFIX': str(self.prefix)}, clear=True):
                with self.assertRaises(SystemExit):
                    self.module.session_prefix()
        with patch.dict(os.environ, {'HOME': str(self.base)}, clear=True):
            with self.assertRaises(SystemExit):
                self.module.session_prefix()
        with patch.dict(os.environ, {'DPREFIX': str(self.prefix)}, clear=True):
            self.assertEqual(self.module.session_prefix(), self.prefix.resolve())

    def test_parent_socket_fallback_and_conflicts(self):
        root = self.base / 'proc'
        proc = self.fake_process(root, 42, 'guest', str(self.socket))
        with patch.dict(os.environ, {'HOME': '/guest/home'}, clear=True), \
                patch.object(self.module.os, 'getppid', return_value=42):
            self.assertEqual(self.module.session_prefix(root), self.prefix.resolve())
            for extra in (b'\0DPREFIX=/other', b'\0__mldr_sockpath=/other/.darlingserver.sock'):
                (proc / 'environ').write_bytes(b'__mldr_sockpath=' + os.fsencode(self.socket) + extra)
                with self.assertRaises(SystemExit):
                    self.module.session_prefix(root)
            for socket in (b'relative/.darlingserver.sock', b'/tmp/wrong.sock',
                           os.fsencode(self.socket) + b'/'):
                (proc / 'environ').write_bytes(b'__mldr_sockpath=' + socket)
                with self.assertRaises(SystemExit):
                    self.module.session_prefix(root)

    def test_parent_fallback_fails_closed(self):
        root = self.base / 'proc'
        proc = self.fake_process(root, 42, 'guest', str(self.socket))
        with patch.dict(os.environ, {'HOME': str(self.prefix)}, clear=True):
            with patch.object(self.module.os, 'getppid', return_value=42), \
                    patch.object(self.module.os, 'getuid', return_value=os.getuid() + 1):
                with self.assertRaises(SystemExit):
                    self.module.session_prefix(root)
            with patch.object(self.module.os, 'getppid', side_effect=[42, 43]):
                with self.assertRaises(SystemExit):
                    self.module.session_prefix(root)
            (proc / 'environ').unlink()
            with patch.object(self.module.os, 'getppid', return_value=42):
                with self.assertRaises(SystemExit):
                    self.module.session_prefix(root)
            shutil.rmtree(proc)
            with patch.object(self.module.os, 'getppid', return_value=42):
                with self.assertRaises(SystemExit):
                    self.module.session_prefix(root)

    def test_a_match_of_this_prefix_is_detected(self):
        proc_root = self.base / 'proc'
        proc_root.mkdir()
        self.fake_process(proc_root, 42, '/prefix/Applications/LeagueofLegends',
                          socket=str(self.socket))
        self.assertTrue(self.module.game_running(self.prefix, proc_root))

    def test_a_match_of_another_prefix_is_ignored(self):
        proc_root = self.base / 'proc'
        proc_root.mkdir()
        other = self.base / 'other'
        other.mkdir()
        self.fake_process(proc_root, 42, '/prefix/Applications/LeagueofLegends',
                          socket=str(other / '.darlingserver.sock'))
        self.assertFalse(self.module.game_running(self.prefix, proc_root))

    def test_match_inspection_is_conservative(self):
        root = self.base / 'proc'
        root.mkdir()
        proc = self.fake_process(root, 42, '/games/LeagueofLegends', socket=self.socket)
        (proc / 'environ').unlink()
        self.assertIsNone(self.module.game_running(self.prefix, root))
        (proc / 'cmdline').unlink()
        self.assertIsNone(self.module.game_running(self.prefix, root))
        self.assertIsNone(self.module.game_running(self.prefix, root / 'missing'))
        self.module.game_running = lambda prefix: None
        self.module.confirm = lambda *args: None
        self.module.stop_session = lambda prefix: self.fail('unknown match must not stop without confirmation')
        self.module.notify = lambda *args: None
        self.assertEqual(self.module.quit_action(self.prefix), 1)

    def test_session_process_scan_scopes_and_fails_closed(self):
        root = self.base / 'proc'
        root.mkdir()
        other = self.base / 'other'
        other.mkdir()
        proc = self.fake_process(root, 42, '/client', socket=other / '.darlingserver.sock')
        scan = lambda: self.module.session_processes_running(self.prefix, root)
        self.assertIs(scan(), False)
        (proc / 'environ').write_bytes(b'__mldr_sockpath=' + os.fsencode(self.socket))
        self.assertIs(scan(), True)
        (proc / 'environ').write_bytes(b'DPREFIX=' + os.fsencode(self.prefix))
        self.assertIs(scan(), True)
        (proc / 'environ').write_bytes(b'')
        (proc / 'cmdline').write_bytes(b'/bin/darlingserver\0' + os.fsencode(self.prefix) + b'\0')
        self.assertIs(scan(), True)
        (proc / 'environ').unlink()
        self.assertIsNone(scan())
        (proc / 'cmdline').unlink()
        self.assertIsNone(scan())
        self.assertIsNone(self.module.session_processes_running(self.prefix, root / 'missing'))

    def test_shutdown_requires_success_and_proof(self):
        root = self.base / 'proc'
        root.mkdir()
        proc = self.fake_process(root, 42, '/client', socket=self.socket)
        self.module.STOP_WAIT_SECONDS = 0
        with patch.object(self.module.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.assertFalse(self.module.stop_session(self.prefix, root))
            (proc / 'environ').unlink()
            self.assertFalse(self.module.stop_session(self.prefix, root))
            proc.rename(root / 'gone')
            self.assertTrue(self.module.stop_session(self.prefix, root))
            self.assertEqual(run.call_args.kwargs['env']['DPREFIX'], str(self.prefix))
            run.return_value.returncode = 1
            self.assertFalse(self.module.stop_session(self.prefix, root))
            run.side_effect = subprocess.TimeoutExpired('darling', 60)
            self.assertFalse(self.module.stop_session(self.prefix, root))

    def test_permission_and_race_do_not_prove_absence(self):
        root = self.base / 'proc'
        root.mkdir()
        proc = self.fake_process(root, 42, '/client', socket=self.socket)
        original = Path.read_bytes
        for error in (PermissionError('denied'), FileNotFoundError('gone')):
            def read_bytes(path):
                if path == proc / 'cmdline':
                    raise error
                return original(path)
            with self.subTest(error=error), patch.object(Path, 'read_bytes', read_bytes):
                self.assertIsNone(self.module.game_running(self.prefix, root))
                self.assertIsNone(self.module.session_processes_running(self.prefix, root))

    def test_the_client_window_is_found_and_scoped(self):
        proc_root = self.base / 'proc'
        proc_root.mkdir()
        self.fake_process(proc_root, 4242, '/prefix/Applications/Riot Client',
                          socket=str(self.socket), nspid=4242)
        windows = {'0x3200007': 'WM_CLASS(STRING) = "riot client", "Riot Client"'}
        pid_value = '_NET_WM_PID(CARDINAL) = 4242'

        def fake_capture(command, timeout=5):
            if command[:2] == ['xprop', '-root']:
                return '_NET_CLIENT_LIST(WINDOW) = window id # 0x3200007\n'
            if command[0] == 'xwininfo':
                return ('xwininfo: Window id: 0x3200007 "Riot Client"\n'
                        '  Width: 1200\n  Height: 800\n  Override Redirect State: no\n')
            if command[1] == '-id':
                if command[3] == '_NET_WM_PID':
                    return pid_value
                return windows[command[2]]
            return ''

        self.module.capture = fake_capture
        self.assertEqual(self.module.client_windows(self.prefix, proc_root, xres=type("Resolver", (), {"window_pid": lambda self, window: 4242})()), ['0x3200007'])

    def test_a_window_of_another_prefix_is_not_touched(self):
        proc_root = self.base / 'proc'
        proc_root.mkdir()
        other = self.base / 'other'
        other.mkdir()
        self.fake_process(proc_root, 4242, '/prefix/Applications/Riot Client',
                          socket=str(other / '.darlingserver.sock'), nspid=4242)

        def fake_capture(command, timeout=5):
            if command[:2] == ['xprop', '-root']:
                return '_NET_CLIENT_LIST(WINDOW) = window id # 0x3200007\n'
            if command[1] == '-id':
                if command[3] == '_NET_WM_PID':
                    return '_NET_WM_PID(CARDINAL) = 4242'
                return 'WM_CLASS(STRING) = "riot client", "Riot Client"'
            return ''

        self.module.capture = fake_capture
        self.assertEqual(self.module.client_windows(self.prefix, proc_root, xres=type("Resolver", (), {"window_pid": lambda self, window: 4242})()), [])

    def test_window_identity_requires_exact_socket_and_uid(self):
        proc_root = self.base / 'proc'
        proc_root.mkdir()
        proc = self.fake_process(proc_root, 42, '/client', socket=str(self.socket))
        resolver = type('Resolver', (), {'window_pid': lambda self, window: 42})()
        belongs = lambda: self.module.belongs_to_prefix('0x123', self.prefix, proc_root, resolver)
        self.assertTrue(belongs())
        (proc / 'environ').write_bytes(b'__mldr_sockpath=' + os.fsencode(self.prefix / 'other.sock'))
        self.assertFalse(belongs())
        (proc / 'environ').write_bytes(b'__mldr_sockpath=' + os.fsencode(self.socket))
        with patch.object(self.module.os, 'getuid', return_value=os.getuid() + 1):
            self.assertFalse(belongs())
        (proc / 'environ').unlink()
        self.assertFalse(belongs())
        self.assertFalse(self.module.belongs_to_prefix('0x123', self.prefix, proc_root))

    def test_auxiliary_withdrawn_window_is_not_reopened(self):
        proc_root = self.base / 'proc'
        proc_root.mkdir()
        self.fake_process(proc_root, 42, '/client', socket=str(self.socket))
        resolver = type('Resolver', (), {'window_pid': lambda self, window: 42})()
        def capture(command, timeout=5):
            if command[:2] == ['xwininfo', '-root']:
                return '  0x100003c (has no name): ("Riot Client" "Riot Client")  20x20+0+1060\n'
            if command[:2] == ['xwininfo', '-id']:
                return ('xwininfo: Window id: 0x100003c (has no name)\n'
                        '  Width: 20\n  Height: 20\n  Map State: IsUnMapped\n'
                        '  Override Redirect State: yes\n')
            return '_NET_CLIENT_LIST(WINDOW): window id # '
        self.module.capture = capture
        self.assertEqual(self.module.client_windows(self.prefix, proc_root, resolver), [])
        self.module.XRes = lambda: resolver
        resolver.close = lambda: None
        original = self.module.client_windows
        self.module.client_windows = lambda prefix, xres=None: original(prefix, proc_root, xres)
        self.module.X11 = lambda: self.fail('auxiliary window must not be mapped')
        messages = []
        self.module.notify = lambda summary, body: messages.append(body)
        self.assertEqual(self.module.reopen_action(self.prefix), 1)
        self.assertNotIn('foi aberto', messages[0])

    def test_window_inspection_fails_closed(self):
        valid = ('xwininfo: Window id: 0x123 "Riot Client"\n'
                 '  Width: 1200\n  Height: 800\n  Override Redirect State: no\n')
        for info, expected in [(valid, True), ('', False),
                               (valid.replace('State: no', 'State: yes'), False),
                               (valid.replace('Width: 1200', 'Width: 20'), False),
                               (valid.replace('"Riot Client"', '(has no name)'), False)]:
            with self.subTest(info=info):
                self.module.capture = lambda command, timeout=5: info
                self.assertEqual(self.module.plausible_client_window('0x123'), expected)

    def test_xres_zero_status_and_ambiguous_results(self):
        module = self.module
        xres = module.XRes.__new__(module.XRes)
        xres.display = 1
        pid_value = ctypes.c_uint32(42)
        values = (module.XResClientIdValue * 2)()
        for value in values:
            value.spec.mask = 2
            value.length = 4
            value.value = ctypes.cast(ctypes.pointer(pid_value), ctypes.c_void_p)
        class FakeRes:
            count = 1
            freed = []
            def XResQueryClientIds(self, display, n, spec, count, result):
                ctypes.cast(count, ctypes.POINTER(ctypes.c_long))[0] = self.count
                ctypes.cast(result, ctypes.POINTER(ctypes.POINTER(module.XResClientIdValue)))[0] = ctypes.cast(values, ctypes.POINTER(module.XResClientIdValue))
                return 0
            def XResGetClientPid(self, value):
                return 42
            def XResClientIdsDestroy(self, count, result):
                self.freed.append(count)
        xres.res = FakeRes()
        self.assertEqual(xres.window_pid('0x123'), 42)
        xres.res.count = 2
        self.assertIsNone(xres.window_pid('0x123'))
        self.assertEqual(xres.res.freed, [1, 2])
        self.assertIsNone(xres.window_pid('invalid'))

    def test_reopen_fails_closed_when_xres_unavailable(self):
        def unavailable():
            raise OSError('missing library')
        self.module.XRes = unavailable
        self.module.notify = lambda *args: None
        self.assertEqual(self.module.reopen_action(self.prefix), 1)

    def test_quit_asks_before_a_match_ends(self):
        asked = []
        self.module.game_running = lambda prefix, proc_root=None: True
        self.module.confirm = lambda summary, body: asked.append(summary) or False
        self.module.stop_session = lambda prefix: True
        self.module.notify = lambda summary, body: None
        self.assertEqual(self.module.quit_action(self.prefix), 1)
        self.assertTrue(asked)

    def test_quit_without_a_dialog_leaves_the_session_running(self):
        stopped = []
        self.module.game_running = lambda prefix, proc_root=None: True
        self.module.confirm = lambda summary, body: None
        self.module.stop_session = lambda prefix: stopped.append(prefix) or True
        self.module.notify = lambda summary, body: None
        self.assertEqual(self.module.quit_action(self.prefix), 1)
        self.assertEqual(stopped, [])

    def test_quit_ends_the_session_when_it_is_confirmed(self):
        stopped = []
        self.module.game_running = lambda prefix, proc_root=None: True
        self.module.confirm = lambda summary, body: True
        self.module.stop_session = lambda prefix: stopped.append(prefix) or True
        self.module.notify = lambda summary, body: None
        self.assertEqual(self.module.quit_action(self.prefix), 0)
        self.assertEqual(stopped, [self.prefix])

    def test_quit_without_a_match_does_not_ask(self):
        asked = []
        self.module.game_running = lambda prefix, proc_root=None: False
        self.module.confirm = lambda summary, body: asked.append(summary) or True
        self.module.stop_session = lambda prefix: True
        self.module.notify = lambda summary, body: None
        self.assertEqual(self.module.quit_action(self.prefix), 0)
        self.assertEqual(asked, [])

    def test_reopen_reports_when_no_window_exists(self):
        self.module.client_windows = lambda prefix, proc_root=None, xres=None: []
        self.module.XRes = lambda: type("Resolver", (), {"close": lambda self: None})()
        messages = []
        self.module.notify = lambda summary, body: messages.append(body)
        self.assertEqual(self.module.reopen_action(self.prefix), 1)
        self.assertTrue(messages)

    def test_the_helper_never_restarts_the_session(self):
        source = ACTION.read_text()
        self.assertNotIn('darling run', source)
        self.assertNotIn('recover-hidden-riot-client', source)


class MenuActionBusTests(unittest.TestCase):
    """The whole host path on a private bus: layout, click and helper."""

    @classmethod
    def setUpClass(cls):
        if not all(shutil.which(name) for name in
                   ('cc', 'pkg-config', 'dbus-run-session', 'gdbus')):
            raise unittest.SkipTest('the private bus test tools are not installed')
        if subprocess.run(['pkg-config', '--exists', 'gio-2.0']).returncode:
            raise unittest.SkipTest('gio-2.0 development files are not installed')
        cls.directory = tempfile.TemporaryDirectory(prefix='menu-actions-bus-')
        cls.addClassCleanup(cls.directory.cleanup)
        cls.library = Path(cls.directory.name) / 'status.so'
        subprocess.run([sys.executable, str(ROOT / 'tools/build-status-notifier.py'),
                        '--output', str(cls.library)], check=True, capture_output=True, text=True)
        # The helper records what it was asked to do.
        cls.record = Path(cls.directory.name) / 'actions.txt'
        cls.helper = Path(cls.directory.name) / 'helper.sh'
        cls.helper.write_text(f'#!/bin/sh\necho "$1" >> "{cls.record}"\n')
        cls.helper.chmod(0o755)

    def test_the_actions_are_in_the_menu_and_do_not_reach_the_guest(self):
        result = subprocess.run(['dbus-run-session', '--', sys.executable,
                                 str(ROOT / 'tests/fixtures/menu-actions-probe.py'),
                                 str(self.library), str(self.helper)],
                                text=True, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        layout = values.get('LAYOUT', '')
        self.assertIn('Sair', layout)
        self.assertIn('Riot Games', layout)
        self.assertIn('Configuracoes', layout)
        # The guest already had a "Sair" entry, so the project did not add a
        # second one with the same name.
        self.assertEqual(layout.count('Sair'), 1)
        self.assertEqual(values.get('EVENT_OK'), 'True')
        self.assertEqual(values.get('GUEST_EVENT_OK'), 'True')
        self.assertEqual(values.get('ORDINARY_EVENT_OK'), 'True')
        # Only the ordinary entry reached the guest: the host owns the two
        # actions. DARLING_STATUS_MENU_CLICK is 5.
        kinds = [kind for kind in values.get('EVENTS', '').split(',') if kind]
        self.assertEqual(kinds, ['5'])
        self.assertTrue(self.record.is_file())
        self.assertEqual(self.record.read_text().split(), ['reopen', 'quit'])


if __name__ == '__main__':
    unittest.main()
