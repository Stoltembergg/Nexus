"""Offline checks of the host-side tray menu actions.

Two parts are covered: the native module that decides which menu entries the
host owns, and the helper that performs the action. Neither part touches a
desktop, a client process or the real session bus.
"""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

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
            if command[1] == '-id':
                if command[3] == '_NET_WM_PID':
                    return pid_value
                return windows[command[2]]
            return ''

        self.module.capture = fake_capture
        self.assertEqual(self.module.client_windows(self.prefix, proc_root), ['0x3200007'])

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
        self.assertEqual(self.module.client_windows(self.prefix, proc_root), [])

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
        self.module.client_windows = lambda prefix, proc_root=None: []
        messages = []
        self.module.notify = lambda summary, body: messages.append(body)
        self.assertEqual(self.module.reopen_action(self.prefix), 1)
        self.assertTrue(messages)

    def test_the_helper_never_restarts_the_session(self):
        source = ACTION.read_text()
        self.assertNotIn('darling run', source)
        self.assertNotIn('recover-hidden-riot-client', source)


if __name__ == '__main__':
    unittest.main()
