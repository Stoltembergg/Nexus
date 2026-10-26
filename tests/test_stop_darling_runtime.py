"""Exercise the shutdown script without stopping the host's Darling session."""
import errno
import io
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/stop-darling-runtime.py'


class StopRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        self.prefix = self.root / 'prefix'
        self.prefix.mkdir()
        self.calls = []
        self.signals = []
        self.signal_start_ticks = []
        self.clock = 0
        self.status_error = None
        self.window_state = False
        self.window_states = []
        self.window_checks = 0
        self.window_backend = 'x11'
        self.on_window_check = lambda owner, count: None
        self.shutdown = lambda: None
        self.on_signal = lambda pid, sig: self.status(pid, 'Z')

    def process(self, pid, *, state='S', parent=1, riot=False, children=(),
                comm=None, cmdline=None, environ=None):
        folder = self.proc / str(pid)
        folder.mkdir()
        self.status(pid, state)
        (folder / 'stat').write_text(f'{pid} (test process) ' + ' '.join(
            [state, str(parent)] + ['0'] * 17 + ['12345']))
        (folder / 'comm').write_text(
            comm if comm is not None else 'darlingserver' if pid == 100 else 'helper')
        (folder / 'maps').write_text(
            str(self.prefix / 'Applications/Riot Client.app/helper') if riot else '')
        if cmdline is not None:
            (folder / 'cmdline').write_bytes(cmdline)
        if environ is not None:
            (folder / 'environ').write_bytes(environ)
        task = folder / 'task' / str(pid)
        task.mkdir(parents=True)
        (task / 'children').write_text(' '.join(map(str, children)))

    def status(self, pid, state):
        (self.proc / str(pid) / 'status').write_text(f'State:\t{state} (test)\n')

    def server(self, **kwargs):
        (self.prefix / '.init.pid').write_text('100')
        self.process(100, **kwargs)

    def game(self, pid, *, socket_prefix=None, include_socket=True, state='S'):
        environment = b''
        if include_socket:
            owner = self.prefix if socket_prefix is None else socket_prefix
            environment = (b'__mldr_sockpath=' +
                           os.fsencode(owner / '.darlingserver.sock') + b'\0')
        self.process(pid, state=state, comm='LeagueofLegends',
                     cmdline=b'/LeagueofLegends\0', environ=environment)

    def run_script(self):
        proc = self.proc
        original_read = Path.read_text
        owner = self

        class RuntimePath(type(Path())):
            def __new__(cls, *parts, **kwargs):
                if parts and str(parts[0]) == '/proc':
                    parts = (proc, *parts[1:])
                return super().__new__(cls, *parts, **kwargs)

            def __init__(self, *parts, **kwargs):
                if parts and str(parts[0]) == '/proc':
                    parts = (proc, *parts[1:])
                super().__init__(*parts, **kwargs)

            def read_text(self, *args, **kwargs):
                if self.name == 'status' and owner.status_error is not None:
                    raise owner.status_error
                return original_read(self, *args, **kwargs)

        def run(command, **kwargs):
            self.calls.append((command, kwargs))
            if command == ['darling', 'shutdown']:
                self.shutdown()
            return subprocess.CompletedProcess(command, 0)

        def kill(pid, sig):
            self.signals.append((pid, sig))
            stat = self.proc / str(pid) / 'stat'
            self.signal_start_ticks.append(stat.read_text().rsplit(')', 1)[1].split()[19])
            self.on_signal(pid, sig)

        def monotonic():
            self.clock += 1
            return self.clock

        def window_check(check_output=None):
            self.window_checks += 1
            self.on_window_check(self, self.window_checks)
            if self.window_states:
                return self.window_states.pop(0)
            return self.window_state

        client_window_module = types.SimpleNamespace(
            client_windows_present=window_check,
            backend=lambda: self.window_backend)

        with patch.dict(sys.modules, {'pathlib': types.SimpleNamespace(Path=RuntimePath)}), \
                patch.dict(sys.modules, {'client_window_state': client_window_module}), \
                patch.dict(os.environ, {'DPREFIX': str(self.prefix)}), \
                patch('subprocess.run', side_effect=run), \
                patch('os.kill', side_effect=kill), \
                patch('time.monotonic', side_effect=monotonic), \
                patch('time.sleep'):
            runpy.run_path(str(SCRIPT), run_name='__main__')

    def assert_finished(self):
        self.assertEqual(self.calls[0][0], ['darling', 'shutdown'])
        self.assertEqual(self.calls[-1], (
            [sys.executable, str(SCRIPT.with_name('ensure-darling-runtime.py'))],
            {'check': True}))

    def test_process_disappears_during_status_read(self):
        self.server()
        self.status_error = ProcessLookupError(errno.ESRCH, 'No such process')
        self.run_script()
        self.assert_finished()

    def test_missing_process(self):
        (self.prefix / '.init.pid').write_text('100')
        self.run_script()
        self.assert_finished()

    def test_no_marker(self):
        self.run_script()
        self.assert_finished()

    def test_invalid_marker(self):
        (self.prefix / '.init.pid').write_text('invalid')
        self.run_script()
        self.assert_finished()

    def test_zombie_server(self):
        self.server(state='Z')
        self.run_script()
        self.assert_finished()

    def test_server_exits_after_shutdown(self):
        self.server()
        self.shutdown = lambda: self.status(100, 'Z')
        self.run_script()
        self.assert_finished()

    def test_live_server_blocks_runtime_changes(self):
        self.server()
        with self.assertRaisesRegex(SystemExit, 'runtime remains untouched'):
            self.run_script()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.signals, [])

    def test_selected_prefix_game_blocks_before_shutdown(self):
        self.game(101)
        with self.assertRaisesRegex(SystemExit, 'League game process'):
            self.run_script()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.signals, [])

    def test_game_from_another_prefix_does_not_block(self):
        other_prefix = self.root / 'other-prefix'
        other_prefix.mkdir()
        self.game(101, socket_prefix=other_prefix)
        self.run_script()
        self.assert_finished()

    def test_unrelated_host_process_does_not_block(self):
        self.process(101, comm='python3', cmdline=b'/usr/bin/python3\0worker\0')
        self.run_script()
        self.assert_finished()

    def test_unowned_game_candidate_blocks_as_unknown(self):
        self.game(101, include_socket=False)
        with self.assertRaisesRegex(SystemExit, 'League game process'):
            self.run_script()
        self.assertEqual(self.calls, [])

    def test_mldr_without_command_line_is_unknown(self):
        self.process(101, comm='mldr')
        with self.assertRaisesRegex(SystemExit, 'process inventory unknown'):
            self.run_script()
        self.assertEqual(self.calls, [])

    def test_mldr_with_empty_argv_is_unknown(self):
        self.process(101, comm='mldr', cmdline=b'\0')
        with self.assertRaisesRegex(SystemExit, 'process inventory unknown'):
            self.run_script()
        self.assertEqual(self.calls, [])

    def test_prefix_owner_without_command_line_is_unknown(self):
        owner = b'__mldr_sockpath=' + os.fsencode(
            self.prefix / '.darlingserver.sock') + b'\0'
        self.process(101, comm='guest-helper', environ=owner)
        with self.assertRaisesRegex(SystemExit, 'process inventory unknown'):
            self.run_script()
        self.assertEqual(self.calls, [])

    def test_client_window_blocks_before_shutdown(self):
        self.window_state = True
        with self.assertRaisesRegex(SystemExit, 'client window'):
            self.run_script()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.signals, [])

    def test_unknown_window_state_blocks_before_shutdown(self):
        self.window_state = None
        with self.assertRaisesRegex(SystemExit, 'window state unknown'):
            self.run_script()
        self.assertEqual(self.calls, [])

    def test_xprop_failure_refusal_identifies_backend_and_dependency(self):
        # The mocked tri-state API reports unknown, as it does when xprop fails.
        self.window_state = None
        diagnostic = io.StringIO()
        with patch('sys.stderr', diagnostic), \
                self.assertRaisesRegex(SystemExit, 'window state unknown'):
            self.run_script()
        self.assertIn('backend x11 is unknown', diagnostic.getvalue())
        self.assertIn('DISPLAY', diagnostic.getvalue())
        self.assertIn('xprop', diagnostic.getvalue())
        self.assertEqual(self.calls, [])

    def test_native_wayland_without_xwayland_is_explicitly_blocked(self):
        self.window_state = None
        self.window_backend = 'unsupported-wayland'
        diagnostic = io.StringIO()
        with patch('sys.stderr', diagnostic), \
                self.assertRaisesRegex(SystemExit, 'window state unknown'):
            self.run_script()
        self.assertIn('Native Wayland without Xwayland DISPLAY is unsupported',
                      diagnostic.getvalue())
        self.assertIn('no override', diagnostic.getvalue())
        self.assertEqual(self.calls, [])

    def test_non_boolean_false_window_state_blocks(self):
        self.window_state = 0
        with self.assertRaisesRegex(SystemExit, 'window state unknown'):
            self.run_script()
        self.assertEqual(self.calls, [])

    def test_unreadable_process_inventory_blocks_before_shutdown(self):
        self.proc.rmdir()
        with self.assertRaisesRegex(SystemExit, 'process inventory unknown'):
            self.run_script()
        self.assertEqual(self.calls, [])

    def test_game_appearing_during_shutdown_blocks_before_signal(self):
        self.server(children=(101,))
        self.process(101, parent=100, riot=True)

        def shutdown():
            self.status(100, 'Z')
            self.game(102)

        self.shutdown = shutdown
        with self.assertRaisesRegex(SystemExit, 'League game process'):
            self.run_script()
        self.assertEqual(self.signals, [])
        self.assertEqual(len(self.calls), 1)

    def test_permission_error_is_not_treated_as_exit(self):
        self.server()
        self.status_error = PermissionError(errno.EACCES, 'Permission denied')
        with self.assertRaises(PermissionError):
            self.run_script()
        self.assertEqual(len(self.calls), 1)

    def test_descendant_gets_sigterm(self):
        self.server(children=(101,))
        self.process(101, parent=100, riot=True)
        self.shutdown = lambda: self.status(100, 'Z')
        self.run_script()
        self.assertEqual(self.signals, [(101, signal.SIGTERM)])
        self.assert_finished()

    def test_sigterm_guard_precedes_identity_check(self):
        self.server(children=(101,))
        self.process(101, parent=100, riot=True)
        self.shutdown = lambda: self.status(100, 'Z')

        def replace_during_signal_guard(owner, checks):
            if checks == 3:
                stat = owner.proc / '101/stat'
                stat.write_text(stat.read_text().replace('12345', '54321'))

        self.on_window_check = replace_during_signal_guard
        self.run_script()
        self.assertEqual(self.signals, [])
        self.assertNotIn('54321', self.signal_start_ticks)
        self.assert_finished()

    def test_stubborn_orphan_gets_sigkill(self):
        self.process(101, riot=True)
        self.on_signal = lambda pid, sig: (
            self.status(pid, 'Z') if sig == signal.SIGKILL else None)
        self.run_script()
        self.assertEqual(self.signals, [(101, signal.SIGTERM), (101, signal.SIGKILL)])
        self.assert_finished()

    def test_sigkill_guard_precedes_identity_check(self):
        self.process(101, riot=True)
        self.on_signal = lambda pid, sig: None

        def replace_during_kill_guard(owner, checks):
            if checks == 5:
                stat = owner.proc / '101/stat'
                stat.write_text(stat.read_text().replace('12345', '54321'))

        self.on_window_check = replace_during_kill_guard
        self.run_script()
        self.assertEqual(self.signals, [(101, signal.SIGTERM)])
        self.assertNotIn('54321', self.signal_start_ticks)
        self.assert_finished()

    def test_surviving_helper_blocks_runtime_changes(self):
        self.process(101, riot=True)
        self.on_signal = lambda pid, sig: None
        with self.assertRaisesRegex(SystemExit, 'Old Riot helpers remain alive'):
            self.run_script()
        self.assertEqual(len(self.calls), 1)

    def test_reused_pid_is_not_signalled(self):
        self.server(children=(101,))
        self.process(101, parent=100, riot=True)

        def shutdown():
            self.status(100, 'Z')
            stat = self.proc / '101/stat'
            stat.write_text(stat.read_text().replace('12345', '54321'))

        self.shutdown = shutdown
        self.run_script()
        self.assertEqual(self.signals, [])
        self.assert_finished()


if __name__ == '__main__':
    unittest.main()
