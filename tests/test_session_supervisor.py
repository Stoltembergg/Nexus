"""Session supervisor: attribution, idle decisions and scoped cleanup."""
import errno
import importlib.util
import io
import os
from pathlib import Path
import signal
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'session_supervisor', ROOT / 'tools/session-supervisor.py')
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


def fake_process(root, pid, ppid=1, state='S', comm='mldr', environ=b'', ns=None,
                 uid=None):
    proc = root / str(pid)
    (proc / 'ns').mkdir(parents=True)
    fields = [state, str(ppid)] + ['0'] * 17 + ['100']
    (proc / 'stat').write_text('%d (%s) %s\n' % (pid, comm, ' '.join(fields)))
    (proc / 'comm').write_text(comm + '\n')
    (proc / 'cmdline').write_bytes(comm.encode() + b'\0')
    if environ is not None:
        (proc / 'environ').write_bytes(environ)
    if ns is not None:
        os.symlink(ns, proc / 'ns/pid')
    return proc


def set_start_ticks(proc, start_ticks):
    stat = (proc / 'stat').read_text()
    prefix, fields_text = stat.rsplit(')', 1)
    fields = fields_text.split()
    fields[19] = str(start_ticks)
    (proc / 'stat').write_text('%s) %s\n' % (prefix, ' '.join(fields)))


class FakePidfds:
    def __init__(self, on_open=None, on_signal=None):
        self.opened = []
        self.signals = []
        self.signals_by_fd = []
        self.closed = []
        self.fd_to_pid = {}
        self.on_open = on_open
        self.on_signal = on_signal
        self.next_fd = 10000

    def open(self, pid, flags):
        fd = self.next_fd
        self.next_fd += 1
        self.opened.append((pid, flags, fd))
        self.fd_to_pid[fd] = pid
        if self.on_open:
            self.on_open(pid)
        return fd

    def send(self, fd, signum, _siginfo=None, _flags=0):
        pid = self.fd_to_pid[fd]
        self.signals.append((pid, signum))
        self.signals_by_fd.append((fd, signum))
        if self.on_signal:
            self.on_signal(pid, signum)

    def close(self, fd):
        self.closed.append(fd)

    def options(self):
        return dict(pidfd_open=self.open, pidfd_send_signal=self.send,
                    close_pidfd=self.close)


class AttributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / '.darling'
        self.socket = self.prefix / '.darlingserver.sock'
        self.ns = 'pid:[4026532000]'

    def process(self, pid, **kwargs):
        return fake_process(self.root, pid, ns=kwargs.pop('ns', self.ns), **kwargs)

    def process_info_with_ticks(self, proc, ticks):
        original = supervisor.process_info
        sequence = iter(ticks)

        def read_info(candidate):
            info = original(candidate)
            if candidate == proc and info is not None:
                try:
                    return info[0], info[1], next(sequence)
                except StopIteration:
                    pass
            return info

        supervisor.process_info = read_info
        self.addCleanup(setattr, supervisor, 'process_info', original)

    def test_socket_names_the_owner_prefix(self):
        proc = self.process(10, comm='RiotClientServices',
                            environ=b'__mldr_sockpath=%s\0' % os.fsencode(self.socket))
        self.assertEqual(supervisor.socket_prefix(proc), self.prefix.resolve())
        self.assertEqual(supervisor.prefix_namespace(self.prefix, self.root), self.ns)

    def test_another_prefix_is_not_owned(self):
        proc = self.process(10, comm='RiotClientServices',
                            environ=b'__mldr_sockpath=/elsewhere/.darlingserver.sock\0')
        self.assertFalse(supervisor.owned_by_prefix(proc, self.prefix.resolve()))

    def test_relative_socket_path_is_not_attributed(self):
        proc = self.process(10, comm='RiotClientServices',
                            environ=b'__mldr_sockpath=.darlingserver.sock\0')
        self.assertIsNone(supervisor.socket_prefix(proc))
        self.assertFalse(supervisor.owned_by_prefix(proc, self.prefix.resolve()))

    def test_duplicate_socket_markers_are_not_attributed(self):
        proc = self.process(
            10, comm='RiotClientServices',
            environ=(b'__mldr_sockpath=%s\0__mldr_sockpath=/elsewhere/.darlingserver.sock\0'
                     % os.fsencode(self.socket)))
        self.assertIsNone(supervisor.socket_prefix(proc))
        self.assertFalse(supervisor.owned_by_prefix(proc, self.prefix.resolve()))

    def test_own_namespace_is_refused(self):
        proc = self.process(10)
        self.assertEqual(
            supervisor.namespace_members(self.ns, self.root, own_namespace=self.ns), [])
        self.assertEqual(
            [pid for pid, _proc, _ticks in supervisor.namespace_members(
                self.ns, self.root, 'pid:[1]')], [10])

    def test_unreadable_environ_is_not_owned(self):
        proc = self.process(10, environ=None)
        self.assertFalse(supervisor.owned_by_prefix(proc, self.prefix.resolve()))

    def test_namespace_member_snapshot_rejects_changed_identity(self):
        proc = self.process(10)
        self.process_info_with_ticks(proc, [100, 200])
        self.assertEqual(
            supervisor.namespace_members(self.ns, self.root, 'pid:[1]'), [])

    def test_prefix_only_snapshot_rejects_changed_identity(self):
        proc = self.process(
            10, environ=b'__mldr_sockpath=%s\0' % os.fsencode(self.socket))
        self.process_info_with_ticks(proc, [100, 200])
        self.assertEqual(supervisor.prefix_only(self.prefix.resolve(), self.root), [])

    def test_prefix_namespace_snapshot_rejects_changed_identity(self):
        proc = self.process(
            10, environ=b'__mldr_sockpath=%s\0' % os.fsencode(self.socket))
        # Ownership is consistent, but the PID changes identity before the
        # namespace link has been fully attributed to that owner.
        self.process_info_with_ticks(proc, [100, 100, 200])
        self.assertIsNone(supervisor.prefix_namespace(self.prefix, self.root))

    def test_game_is_matched_through_the_prefix_socket(self):
        proc = self.process(10, comm='LeagueofLegends',
                            environ=b'__mldr_sockpath=%s\0' % os.fsencode(self.socket))
        (proc / 'cmdline').write_bytes(b'/Applications/LeagueofLegends\0')
        self.assertTrue(supervisor.game_running(self.prefix, self.root))
        other = self.root / 'other'
        other.mkdir()
        self.assertFalse(supervisor.game_running(other, self.root))

    def game_process(self, environ=None, state='S'):
        proc = self.process(10, comm='LeagueofLegends', environ=environ, state=state)
        (proc / 'cmdline').write_bytes(b'/Applications/LeagueofLegends\0')
        return proc

    def test_unreadable_game_command_is_unknown(self):
        self.game_process()
        with patch.object(supervisor, '_read_command', return_value=None):
            self.assertIsNone(supervisor.game_running(self.prefix, self.root))

    def test_unreadable_game_ownership_is_unknown(self):
        self.game_process()
        with patch.object(supervisor, '_read_environ', return_value=None):
            self.assertIsNone(supervisor.game_running(self.prefix, self.root))

    def test_relative_game_socket_path_is_unknown_and_blocks_stop(self):
        self.game_process(b'__mldr_sockpath=.darlingserver.sock\0')
        self.assertIsNone(supervisor.game_running(self.prefix, self.root))
        self.assertFalse(supervisor.safe_to_stop(
            self.prefix, self.root, window_probe=lambda: False))

    def test_game_command_change_during_inspection_is_unknown(self):
        proc = self.game_process(
            b'__mldr_sockpath=%s\0' % os.fsencode(self.socket))
        original = supervisor._read_command
        reads = [original(proc), b'/Applications/Other\0']
        with patch.object(supervisor, '_read_command', side_effect=reads):
            self.assertIsNone(supervisor.game_running(self.prefix, self.root))

    def test_game_ownership_change_during_inspection_is_unknown(self):
        self.game_process(b'__mldr_sockpath=%s\0' % os.fsencode(self.socket))
        with patch.object(supervisor, '_read_environ', side_effect=[
                b'__mldr_sockpath=%s\0' % os.fsencode(self.socket),
                b'__mldr_sockpath=/elsewhere/.darlingserver.sock\0']):
            self.assertIsNone(supervisor.game_running(self.prefix, self.root))

    def test_game_identity_change_during_inspection_is_unknown(self):
        proc = self.game_process(
            b'__mldr_sockpath=%s\0' % os.fsencode(self.socket))
        original = supervisor._read_environ
        changed = [False]

        def read_environ(candidate):
            if candidate == proc and not changed[0]:
                changed[0] = True
                set_start_ticks(proc, 200)
            return original(candidate)

        with patch.object(supervisor, '_read_environ', side_effect=read_environ):
            self.assertIsNone(supervisor.game_running(self.prefix, self.root))

    def test_disappearing_game_process_is_ignored(self):
        import shutil
        proc = self.game_process()
        original = supervisor._read_command

        def read_then_disappear(candidate):
            result = original(candidate)
            shutil.rmtree(proc)
            return result

        with patch.object(supervisor, '_read_command', side_effect=read_then_disappear):
            self.assertFalse(supervisor.game_running(self.prefix, self.root))

    def test_zombie_game_process_is_ignored(self):
        self.game_process(state='Z')
        self.assertFalse(supervisor.game_running(self.prefix, self.root))

    def test_unrelated_unreadable_environment_does_not_poison_probe(self):
        self.process(10, comm='mldr', environ=None)
        self.assertFalse(supervisor.game_running(self.prefix, self.root))

    def test_live_mldr_with_empty_command_is_unknown(self):
        proc = self.process(10, comm='mldr', environ=None)
        (proc / 'cmdline').write_bytes(b'')
        self.assertIsNone(supervisor.game_running(self.prefix, self.root))

    def test_live_mldr_with_all_nul_command_is_unknown(self):
        proc = self.process(10, comm='mldr', environ=None)
        (proc / 'cmdline').write_bytes(b'\0\0\0')
        self.assertIsNone(supervisor.game_running(self.prefix, self.root))

    def unrelated_process(self):
        proc = self.process(10, comm='python', environ=None)
        (proc / 'cmdline').write_bytes(b'python\0')
        return proc

    def test_unrelated_command_change_during_scan_is_unknown(self):
        proc = self.unrelated_process()
        reads = iter((b'python\0', b'/Applications/LeagueofLegends\0'))
        with patch.object(supervisor, '_read_command', side_effect=lambda _proc: next(reads)), \
                patch.object(supervisor, '_read_environ',
                             side_effect=AssertionError('unrelated environ was inspected')):
            self.assertIsNone(supervisor.game_running(self.prefix, self.root))

    def test_unrelated_start_identity_change_during_scan_is_unknown(self):
        proc = self.unrelated_process()
        original = supervisor._read_command
        calls = [0]

        def read_command(candidate):
            calls[0] += 1
            if calls[0] == 2:
                set_start_ticks(proc, 200)
            return original(candidate)

        with patch.object(supervisor, '_read_command', side_effect=read_command):
            self.assertIsNone(supervisor.game_running(self.prefix, self.root))

    def test_unrelated_comm_change_during_scan_is_unknown(self):
        proc = self.unrelated_process()
        original = supervisor._read_command
        calls = [0]

        def read_command(candidate):
            calls[0] += 1
            if calls[0] == 2:
                stat = (proc / 'stat').read_text().replace('(python)', '(LeagueofLegends)')
                (proc / 'stat').write_text(stat)
            return original(candidate)

        with patch.object(supervisor, '_read_command', side_effect=read_command):
            self.assertIsNone(supervisor.game_running(self.prefix, self.root))

    def test_proc_enumeration_error_is_unknown(self):
        class BrokenProcRoot:
            def iterdir(self):
                raise PermissionError('synthetic procfs failure')

        self.assertIsNone(supervisor.game_running(self.prefix, BrokenProcRoot()))


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / '.darling'
        self.ns = 'pid:[4026532000]'
        self.own = 'pid:[4026531000]'
        self.output = io.StringIO()

    def process(self, pid, ppid=1):
        return fake_process(self.root, pid, ppid=ppid, ns=self.ns)

    def test_cleanup_shuts_down_then_terminates_namespace_members(self):
        self.process(10)
        self.process(11, ppid=10)
        calls = []

        def run(command, **_kwargs):
            calls.append(command)

        def signaled(pid, signum):
            if signum == supervisor.signal.SIGTERM:
                import shutil
                shutil.rmtree(self.root / str(pid))

        pidfds = FakePidfds(on_signal=signaled)
        remaining = supervisor.cleanup(
            self.prefix, '/usr/bin/darling', self.ns, proc_root=self.root,
            run=run, **pidfds.options(), sleep=lambda _seconds: None, out=self.output,
            own_namespace=self.own, term_grace=0, kill_grace=0,
            safety_check=lambda: True)
        self.assertEqual(remaining, [])
        self.assertEqual(calls, [['/usr/bin/darling', 'shutdown']])
        # Deepest process first: the child (11) before its parent (10).
        self.assertEqual(pidfds.signals, [(11, supervisor.signal.SIGTERM),
                                          (10, supervisor.signal.SIGTERM)])
        self.assertEqual([pid for pid, _flags, _fd in pidfds.opened], [11, 10])
        self.assertCountEqual(pidfds.closed, [fd for _pid, _flags, fd in pidfds.opened])
        self.assertIn('guest session stopped', self.output.getvalue())

    def test_cleanup_does_nothing_without_attribution(self):
        output = io.StringIO()
        remaining = supervisor.cleanup(
            self.prefix, '/usr/bin/darling', None, proc_root=self.root,
            run=lambda *_a, **_k: self.fail('must not run darling shutdown'),
            sleep=lambda _s: None,
            out=output, own_namespace=self.own, term_grace=0, kill_grace=0,
            safety_check=lambda: True)
        self.assertEqual(remaining, [])
        self.assertIn('gone', output.getvalue())

    def test_live_survivor_is_reported(self):
        self.process(10)
        output = io.StringIO()
        pidfds = FakePidfds()
        remaining = supervisor.cleanup(
            self.prefix, None, self.ns, proc_root=self.root,
            run=lambda *_a, **_k: None, **pidfds.options(),
            sleep=lambda _s: None, out=output, own_namespace=self.own, term_grace=0,
            kill_grace=0, safety_check=lambda: True)
        self.assertEqual([pid for pid, _proc, _ticks in remaining], [10])
        self.assertIn('still present: 10', output.getvalue())

    def test_cleanup_vetoes_before_darling_shutdown(self):
        self.process(10)
        shutdown = []
        remaining = supervisor.cleanup(
            self.prefix, '/usr/bin/darling', self.ns, proc_root=self.root,
            run=lambda command, **_kwargs: shutdown.append(command),
            sleep=lambda _seconds: None, out=self.output, own_namespace=self.own,
            safety_check=lambda: False)
        self.assertIsNone(remaining)
        self.assertEqual(shutdown, [])

    def test_state_change_before_shutdown_vetoes_cleanup(self):
        self.process(10)
        checks = iter((True, False))
        shutdown = []
        remaining = supervisor.cleanup(
            self.prefix, '/usr/bin/darling', self.ns, proc_root=self.root,
            run=lambda command, **_kwargs: shutdown.append(command),
            sleep=lambda _seconds: None, out=self.output, own_namespace=self.own,
            safety_check=lambda: next(checks))
        self.assertIsNone(remaining)
        self.assertEqual(shutdown, [])

    def test_state_change_before_guest_term_vetoes_cleanup(self):
        self.process(10)
        checks = iter((True, False))
        pidfds = FakePidfds()
        remaining = supervisor.cleanup(
            self.prefix, None, self.ns, proc_root=self.root,
            run=lambda *_args, **_kwargs: self.fail('must not shut down'),
            **pidfds.options(),
            sleep=lambda _seconds: None, out=self.output, own_namespace=self.own,
            term_grace=0, kill_grace=0, safety_check=lambda: next(checks))
        self.assertIsNone(remaining)
        self.assertEqual(pidfds.signals, [])
        self.assertEqual(pidfds.opened, [])

    def test_state_change_before_guest_kill_aborts_remaining_cleanup(self):
        self.process(10)
        checks = iter((True, True, True, False))
        pidfds = FakePidfds()
        remaining = supervisor.cleanup(
            self.prefix, None, self.ns, proc_root=self.root,
            run=lambda *_args, **_kwargs: self.fail('must not shut down'),
            **pidfds.options(),
            sleep=lambda _seconds: None, out=self.output, own_namespace=self.own,
            term_grace=0, kill_grace=0, safety_check=lambda: next(checks))
        self.assertIsNone(remaining)
        self.assertEqual(pidfds.signals, [(10, signal.SIGTERM)])
        self.assertEqual(pidfds.closed, [pidfds.opened[0][2]])

    def test_reused_pid_after_snapshot_is_not_signaled(self):
        proc = self.process(10)
        members = supervisor.namespace_members(self.ns, self.root, self.own)
        set_start_ticks(proc, 200)
        pidfds = FakePidfds()

        remaining = supervisor.stop_processes(
            members, **pidfds.options(),
            sleep=lambda _seconds: None, proc_root=self.root,
            term_grace=0, kill_grace=0, safety_check=lambda: True)
        self.assertEqual(pidfds.signals, [])
        self.assertEqual(pidfds.opened, [])
        self.assertEqual(remaining, [])

    def test_reused_pid_during_pidfd_open_is_not_signaled(self):
        proc = self.process(10)
        members = supervisor.namespace_members(self.ns, self.root, self.own)
        pidfds = FakePidfds(on_open=lambda _pid: set_start_ticks(proc, 200))

        remaining = supervisor.stop_processes(
            members, **pidfds.options(), sleep=lambda _seconds: None,
            proc_root=self.root, term_grace=0, kill_grace=0,
            safety_check=lambda: True)
        self.assertEqual(pidfds.signals, [])
        self.assertEqual(len(pidfds.opened), 1)
        self.assertEqual(pidfds.closed, [pidfds.opened[0][2]])
        self.assertEqual(remaining, [])

    def test_missing_pidfd_api_fails_closed_and_reports_survivor(self):
        for module, name in ((supervisor.os, 'pidfd_open'),
                             (supervisor.signal, 'pidfd_send_signal')):
            with self.subTest(api=name):
                proc = self.process(10)
                members = supervisor.namespace_members(self.ns, self.root, self.own)
                output = io.StringIO()
                with patch.object(module, name, None, create=True):
                    remaining = supervisor.stop_processes(
                        members, sleep=lambda _seconds: None, proc_root=self.root,
                        out=output, term_grace=0, kill_grace=0,
                        safety_check=lambda: True)
                self.assertEqual([pid for pid, _proc, _ticks in remaining], [10])
                self.assertIn('pidfd signaling is unavailable', output.getvalue())
                shutil.rmtree(proc)

    def test_pidfd_open_error_closes_acquired_fds_without_signaling(self):
        self.process(10)
        self.process(11, ppid=10)
        members = supervisor.namespace_members(self.ns, self.root, self.own)
        pidfds = FakePidfds()

        def open_pidfd(pid, flags):
            if pid == 10:
                raise OSError(errno.ENOSYS, 'pidfd_open unavailable')
            return pidfds.open(pid, flags)

        remaining = supervisor.stop_processes(
            members, pidfd_open=open_pidfd, pidfd_send_signal=pidfds.send,
            close_pidfd=pidfds.close, sleep=lambda _seconds: None,
            proc_root=self.root, term_grace=0, kill_grace=0,
            safety_check=lambda: True)
        self.assertCountEqual([pid for pid, _proc, _ticks in remaining], [10, 11])
        self.assertEqual(pidfds.signals, [])
        self.assertEqual(len(pidfds.opened), 1)
        self.assertEqual(pidfds.closed, [pidfds.opened[0][2]])

    def test_pidfd_send_error_fails_closed_without_numeric_fallback(self):
        self.process(10)
        members = supervisor.namespace_members(self.ns, self.root, self.own)
        pidfds = FakePidfds()
        output = io.StringIO()

        def unsupported(*_args):
            raise OSError(errno.ENOSYS, 'pidfd_send_signal unavailable')

        with patch.object(supervisor.os, 'kill', side_effect=AssertionError('unsafe fallback')):
            remaining = supervisor.stop_processes(
                members, pidfd_open=pidfds.open, pidfd_send_signal=unsupported,
                close_pidfd=pidfds.close, sleep=lambda _seconds: None,
                proc_root=self.root, out=output, term_grace=0, kill_grace=0,
                safety_check=lambda: True)
        self.assertEqual([pid for pid, _proc, _ticks in remaining], [10])
        self.assertIn('refusing further cleanup', output.getvalue())
        self.assertEqual(pidfds.closed, [pidfds.opened[0][2]])

    def test_esrch_from_pidfd_suppresses_escalation(self):
        self.process(10)
        members = supervisor.namespace_members(self.ns, self.root, self.own)
        pidfds = FakePidfds()
        attempted = []

        def gone(fd, signum, _siginfo, _flags):
            attempted.append((fd, signum))
            raise OSError(errno.ESRCH, 'target exited')

        remaining = supervisor.stop_processes(
            members, pidfd_open=pidfds.open, pidfd_send_signal=gone,
            close_pidfd=pidfds.close, sleep=lambda _seconds: None,
            proc_root=self.root, term_grace=0, kill_grace=0,
            safety_check=lambda: True)
        self.assertEqual(len(attempted), 1)
        self.assertEqual(attempted[0][1], signal.SIGTERM)
        self.assertEqual(remaining, [])
        self.assertEqual(pidfds.closed, [pidfds.opened[0][2]])

    def test_safety_veto_closes_already_opened_pidfds(self):
        self.process(10)
        self.process(11, ppid=10)
        members = supervisor.namespace_members(self.ns, self.root, self.own)
        pidfds = FakePidfds()
        checks = iter((True, False))

        remaining = supervisor.stop_processes(
            members, **pidfds.options(), sleep=lambda _seconds: None,
            proc_root=self.root, term_grace=0, kill_grace=0,
            safety_check=lambda: next(checks))
        self.assertIsNone(remaining)
        self.assertEqual([pid for pid, _flags, _fd in pidfds.opened], [11])
        self.assertEqual(pidfds.signals, [])
        self.assertEqual(pidfds.closed, [pidfds.opened[0][2]])

    def test_unexpected_signal_exception_closes_pidfd(self):
        self.process(10)
        members = supervisor.namespace_members(self.ns, self.root, self.own)
        pidfds = FakePidfds()

        def broken_signal(*_args):
            raise RuntimeError('synthetic failure')

        with self.assertRaisesRegex(RuntimeError, 'synthetic failure'):
            supervisor.stop_processes(
                members, pidfd_open=pidfds.open, pidfd_send_signal=broken_signal,
                close_pidfd=pidfds.close, sleep=lambda _seconds: None,
                proc_root=self.root, term_grace=0, kill_grace=0,
                safety_check=lambda: True)
        self.assertEqual(pidfds.closed, [pidfds.opened[0][2]])

    def test_reused_pid_between_term_and_kill_is_not_signaled_again(self):
        proc = self.process(10)
        members = supervisor.namespace_members(self.ns, self.root, self.own)
        pidfds = FakePidfds(on_signal=lambda pid, signum:
                            set_start_ticks(proc, 200) if signum == signal.SIGTERM else None)

        remaining = supervisor.stop_processes(
            members, **pidfds.options(), sleep=lambda _seconds: None,
            proc_root=self.root, term_grace=0, kill_grace=0,
            safety_check=lambda: True)
        self.assertEqual(pidfds.signals, [(10, signal.SIGTERM)])
        self.assertEqual(remaining, [])

    def test_reused_pid_during_term_wait_is_not_escalated(self):
        proc = self.process(10)
        members = supervisor.namespace_members(self.ns, self.root, self.own)
        pidfds = FakePidfds()
        now = [0]

        def sleep(_seconds):
            set_start_ticks(proc, 200)
            now[0] += 1

        remaining = supervisor.stop_processes(
            members, **pidfds.options(),
            sleep=sleep, proc_root=self.root, term_grace=1, kill_grace=0,
            clock=lambda: now[0], safety_check=lambda: True)
        self.assertEqual(pidfds.signals, [(10, signal.SIGTERM)])
        self.assertEqual(remaining, [])

    def test_reused_pid_during_kill_wait_is_not_returned(self):
        proc = self.process(10)
        members = supervisor.namespace_members(self.ns, self.root, self.own)
        pidfds = FakePidfds()
        now = [0]

        def sleep(_seconds):
            set_start_ticks(proc, 200)
            now[0] += 1

        remaining = supervisor.stop_processes(
            members, **pidfds.options(),
            sleep=sleep, proc_root=self.root, term_grace=0, kill_grace=1,
            clock=lambda: now[0], safety_check=lambda: True)
        self.assertEqual(pidfds.signals, [(10, signal.SIGTERM), (10, signal.SIGKILL)])
        self.assertEqual(remaining, [])

    def test_live_process_gets_term_then_kill_escalation(self):
        self.process(10)
        members = supervisor.namespace_members(self.ns, self.root, self.own)
        pidfds = FakePidfds()

        remaining = supervisor.stop_processes(
            members, **pidfds.options(),
            sleep=lambda _seconds: None, proc_root=self.root,
            term_grace=0, kill_grace=0, safety_check=lambda: True)
        self.assertEqual(pidfds.signals, [(10, signal.SIGTERM), (10, signal.SIGKILL)])
        self.assertEqual(pidfds.signals_by_fd[0][0], pidfds.signals_by_fd[1][0])
        self.assertEqual(len(pidfds.closed), 1)
        self.assertEqual([pid for pid, _proc, _ticks in remaining], [10])


class RuntimeMarkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        self.prefix = self.root / '.darling'
        self.prefix.mkdir()

    def server(self, pid=10, argv=None, state='S'):
        proc = fake_process(self.proc, pid, state=state, comm='darlingserver')
        (proc / 'cmdline').write_bytes(
            b'\0'.join(os.fsencode(part) for part in
                       (argv or ['/usr/libexec/darlingserver', str(self.prefix)])) + b'\0')
        (self.prefix / '.init.pid').write_text('%d\n' % pid)
        return proc

    def test_live_server_of_this_prefix_is_recognised(self):
        self.server()
        self.assertTrue(supervisor.runtime_alive(self.prefix, self.proc))

    def test_missing_marker_is_not_a_runtime(self):
        self.assertFalse(supervisor.runtime_alive(self.prefix, self.proc))

    def test_reused_pid_is_not_a_runtime(self):
        self.server()
        proc = self.proc / '10'
        (proc / 'cmdline').write_bytes(b'/usr/bin/other\0\0')
        self.assertFalse(supervisor.runtime_alive(self.prefix, self.proc))

    def test_other_prefix_is_not_ours(self):
        self.server(argv=['/usr/libexec/darlingserver', '/elsewhere/.darling'])
        self.assertFalse(supervisor.runtime_alive(self.prefix, self.proc))

    def test_zombie_server_is_not_a_runtime(self):
        self.server(state='Z')
        self.assertFalse(supervisor.runtime_alive(self.prefix, self.proc))


class SupervisorModeTests(unittest.TestCase):
    """run_supervised must not end a runtime that another session started."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / '.darling'
        self.prefix.mkdir()
        self.proc = self.root / 'proc'
        self.proc.mkdir()

    def run_supervisor(self):
        output = io.StringIO()
        code = supervisor.run_supervised(
            ['true'], self.prefix, None, proc_root=self.proc, poll=0,
            run=lambda *_a, **_k: None,
            sleep=lambda _s: None, out=output, window_probe=lambda: False)
        self.assertEqual(code, 0)
        return output.getvalue()

    def test_own_session_is_cleaned_up(self):
        self.assertIn('gone', self.run_supervisor())

    def test_attached_session_is_left_running(self):
        proc = fake_process(self.proc, 10, comm='darlingserver')
        (proc / 'cmdline').write_bytes(
            b'/usr/libexec/darlingserver\0' + os.fsencode(self.prefix) + b'\0')
        (self.prefix / '.init.pid').write_text('10\n')
        output = self.run_supervisor()
        self.assertIn('another session owns this runtime', output)
        self.assertNotIn('guest session stopped', output)


class ExitStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / '.darling'
        self.prefix.mkdir()
        self.proc = self.root / 'proc'
        self.proc.mkdir()

    def run_supervisor(self, command, remaining):
        previous = supervisor.cleanup
        supervisor.cleanup = lambda *_a, **_k: remaining
        self.addCleanup(setattr, supervisor, 'cleanup', previous)
        return supervisor.run_supervised(
            command, self.prefix, None, proc_root=self.proc, poll=0,
            run=lambda *_a, **_k: None,
            sleep=lambda _s: None, out=io.StringIO())

    def test_child_status_is_kept_when_cleanup_is_clean(self):
        self.assertEqual(self.run_supervisor(['sh', '-c', 'exit 3'], []), 3)

    def test_surviving_processes_force_a_failure_status(self):
        self.assertEqual(self.run_supervisor(['true'], [1234]), 1)

    def test_a_failed_child_stays_failed_with_survivors(self):
        self.assertEqual(self.run_supervisor(['sh', '-c', 'exit 3'], [1234]), 3)


class SafetyMatrixTests(unittest.TestCase):
    def test_stop_requires_both_probes_to_be_explicitly_false(self):
        for game in (False, True, None):
            for windows in (False, True, None):
                with self.subTest(game=game, windows=windows), \
                        patch.object(supervisor, 'game_running', return_value=game), \
                        patch.object(supervisor, 'client_windows_present',
                                     return_value=windows):
                    self.assertEqual(
                        supervisor.safe_to_stop(Path('/prefix'), Path('/proc')),
                        game is False and windows is False)


class FakeChild:
    def __init__(self, pid=12345):
        self.pid = pid
        self.live = True
        self.status = -signal.SIGTERM
        self.wait_calls = 0

    def poll(self):
        return None if self.live else self.status

    def wait(self):
        self.wait_calls += 1
        return self.status


class MainCleanupPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.prefix = Path(self.temp.name) / '.darling'

    def invoke(self, cleanup_value=None, extra_args=()):
        env = {}
        if cleanup_value is not None:
            env['RCLOL_CLEAN_ON_EXIT'] = cleanup_value
        with patch.dict(os.environ, env, clear=True), \
                patch.object(supervisor, 'run_supervised', return_value=0) as run:
            result = supervisor.main([
                '--prefix', str(self.prefix), *extra_args, '--', 'fixture'])
        self.assertEqual(result, 0)
        return run.call_args.kwargs['clean']

    def test_cleanup_is_disabled_by_default(self):
        self.assertFalse(self.invoke())

    def test_exact_one_enables_cleanup(self):
        self.assertTrue(self.invoke('1'))

    def test_no_clean_overrides_opt_in(self):
        self.assertFalse(self.invoke('1', ('--no-clean',)))

    def test_unrecognized_values_leave_cleanup_disabled(self):
        for value in ('0', 'true', '01', ' 1 '):
            with self.subTest(value=value):
                self.assertFalse(self.invoke(value))


class SupervisedSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / '.darling'
        self.prefix.mkdir()
        self.proc = self.root / 'proc'
        self.proc.mkdir()

    def run_fake(self, child, **kwargs):
        handlers = {}

        def register(signum, handler):
            if handler is not None:
                handlers[signum] = handler
            return None

        defaults = dict(
            proc_root=self.proc, poll=0, popen=lambda *_a, **_k: child,
            register_signal=register, window_probe=lambda: False,
            sleep=lambda _seconds: None, out=io.StringIO())
        defaults.update(kwargs)
        code = supervisor.run_supervised(['fixture'], self.prefix, None, **defaults)
        return code, handlers

    def test_signal_handler_only_records_first_signal(self):
        child = FakeChild()
        group_signals = []
        observed_in_handler = []
        calls = [0]
        handlers = {}

        def register(signum, handler):
            if handler is not None:
                handlers[signum] = handler
            return None

        def killpg(pid, signum):
            group_signals.append((pid, signum))
            child.status = -signum
            child.live = False

        def sleep(_seconds):
            calls[0] += 1
            if calls[0] == 1:
                handler = handlers[signal.SIGTERM]
                handler(signal.SIGTERM, None)
                handler(signal.SIGINT, None)
                observed_in_handler.append(list(group_signals))

        with patch.object(supervisor, 'cleanup', return_value=[]), \
                patch.object(supervisor, 'safe_to_stop', return_value=True):
            code = supervisor.run_supervised(
                ['fixture'], self.prefix, None, proc_root=self.proc, poll=0,
                popen=lambda *_a, **_k: child, killpg=killpg,
                register_signal=register, window_probe=lambda: False,
                sleep=sleep, out=io.StringIO())
        self.assertEqual(observed_in_handler, [[]])
        self.assertEqual(group_signals, [(child.pid, signal.SIGTERM)])
        self.assertEqual(code, 143)
        self.assertEqual(child.wait_calls, 1)

    def test_cleanup_off_stays_supervised_and_detaches_on_signal(self):
        child = FakeChild()
        handlers = {}
        probes = []
        group_signals = []

        def register(signum, handler):
            if handler is not None:
                handlers[signum] = handler
            return None

        def window_probe():
            probes.append('window')
            return False

        def sleep(_seconds):
            handlers[signal.SIGTERM](signal.SIGTERM, None)

        popen_calls = []
        with patch.object(supervisor, 'runtime_alive', return_value=False), \
                patch.object(supervisor, 'game_running', return_value=None) as game_probe, \
                patch.object(supervisor, 'cleanup') as cleanup:
            code = supervisor.run_supervised(
                ['fixture'], self.prefix, None, clean=False, stop_after=30,
                proc_root=self.proc, poll=0,
                popen=lambda *args, **kwargs: (popen_calls.append((args, kwargs)) or child),
                killpg=lambda *args: group_signals.append(args),
                register_signal=register, window_probe=window_probe,
                sleep=sleep, out=io.StringIO())
        self.assertEqual(code, 128 + signal.SIGTERM)
        self.assertEqual(len(popen_calls), 1)
        self.assertTrue(popen_calls[0][1]['start_new_session'])
        self.assertEqual(group_signals, [])
        self.assertEqual(child.wait_calls, 0)
        self.assertEqual(probes, ['window'])
        game_probe.assert_called_once()
        cleanup.assert_not_called()

    def test_cleanup_off_natural_exit_skips_guest_cleanup(self):
        child = FakeChild()
        child.live = False
        child.status = 0
        with patch.object(supervisor, 'runtime_alive', return_value=False), \
                patch.object(supervisor, 'cleanup') as cleanup:
            code = supervisor.run_supervised(
                ['fixture'], self.prefix, None, clean=False,
                proc_root=self.proc, poll=0,
                popen=lambda *_args, **_kwargs: child,
                register_signal=lambda *_args: None,
                window_probe=lambda: self.fail('idle probing is disabled'),
                sleep=lambda _seconds: None, out=io.StringIO())
        self.assertEqual(code, 0)
        self.assertEqual(child.wait_calls, 1)
        cleanup.assert_not_called()

    def test_cleanup_off_does_not_apply_idle_kill(self):
        child = FakeChild()
        sleeps = [0]
        group_signals = []

        def sleep(_seconds):
            sleeps[0] += 1
            if sleeps[0] == 4:
                child.live = False
                child.status = 0

        with patch.object(supervisor, 'runtime_alive', return_value=False), \
                patch.object(supervisor, 'game_running', return_value=False) as game_probe, \
                patch.object(supervisor, 'cleanup') as cleanup:
            code = supervisor.run_supervised(
                ['fixture'], self.prefix, None, clean=False, stop_after=1,
                proc_root=self.proc, popen=lambda *_args, **_kwargs: child,
                register_signal=lambda *_args: None,
                window_probe=lambda: self.fail('idle window probe must be disabled'),
                killpg=lambda *args: group_signals.append(args), sleep=sleep,
                poll=0, clock=lambda: sleeps[0] * 2.0, out=io.StringIO())
        self.assertEqual(code, 0)
        self.assertEqual(group_signals, [])
        self.assertEqual(child.wait_calls, 1)
        # Cleanup-off still consults the game probe after loader exit so the
        # supervisor can preserve a match, but does not probe idle windows.
        game_probe.assert_called_once()
        cleanup.assert_not_called()

    def test_protected_signal_detaches_without_signal_wait_or_cleanup(self):
        for signum, game, windows in (
                (signal.SIGINT, True, False),
                (signal.SIGTERM, False, True),
                (signal.SIGTERM, None, False),
                (signal.SIGTERM, False, None)):
            with self.subTest(signum=signum, game=game, windows=windows):
                child = FakeChild()
                handlers = {}
                group_signals = []

                def register(sig, handler):
                    if handler is not None:
                        handlers[sig] = handler
                    return None

                def sleep(_seconds):
                    handlers[signum](signum, None)

                with patch.object(supervisor, 'game_running', return_value=game), \
                        patch.object(supervisor, 'client_windows_present',
                                     return_value=windows), \
                        patch.object(supervisor, 'cleanup') as cleanup:
                    code = supervisor.run_supervised(
                        ['fixture'], self.prefix, None, proc_root=self.proc,
                        popen=lambda *_a, **_k: child, killpg=lambda *args:
                        group_signals.append(args), register_signal=register,
                        sleep=sleep, poll=0, out=io.StringIO())
                self.assertEqual(code, 128 + signum)
                self.assertEqual(group_signals, [])
                self.assertEqual(child.wait_calls, 0)
                cleanup.assert_not_called()

    def test_unowned_runtime_signal_detaches_without_actions(self):
        child = FakeChild()
        handlers = {}
        group_signals = []

        def register(signum, handler):
            if handler is not None:
                handlers[signum] = handler
            return None

        def sleep(_seconds):
            handlers[signal.SIGTERM](signal.SIGTERM, None)

        with patch.object(supervisor, 'runtime_alive', return_value=True), \
                patch.object(supervisor, 'cleanup') as cleanup, \
                patch.object(supervisor, 'safe_to_stop', return_value=True):
            code = supervisor.run_supervised(
                ['fixture'], self.prefix, None, proc_root=self.proc,
                popen=lambda *_a, **_k: child, killpg=lambda *args:
                group_signals.append(args), register_signal=register,
                sleep=sleep, poll=0, out=io.StringIO())
        self.assertEqual(code, 143)
        self.assertEqual(group_signals, [])
        self.assertEqual(child.wait_calls, 0)
        cleanup.assert_not_called()

    def test_safe_signal_terms_then_rechecks_before_group_kill(self):
        child = FakeChild()
        group_signals = []
        handlers = {}
        ticks = [0]
        sleeps = [0]

        def register(signum, handler):
            if handler is not None:
                handlers[signum] = handler
            return None

        def sleep(_seconds):
            sleeps[0] += 1
            ticks[0] += 1
            if sleeps[0] == 1:
                handlers[signal.SIGTERM](signal.SIGTERM, None)

        def killpg(pid, signum):
            group_signals.append((pid, signum))
            if signum == signal.SIGKILL:
                child.status = -signal.SIGKILL
                child.live = False

        with patch.object(supervisor, 'cleanup', return_value=[]), \
                patch.object(supervisor, 'safe_to_stop', side_effect=(True, True)), \
                patch.object(supervisor, 'TERM_GRACE', 1.0):
            code, _handlers = self.run_fake(
                child, killpg=killpg, register_signal=register, sleep=sleep,
                clock=lambda: ticks[0])
        self.assertEqual(group_signals, [(child.pid, signal.SIGTERM),
                                         (child.pid, signal.SIGKILL)])
        self.assertEqual(code, 137)
        self.assertEqual(child.wait_calls, 1)

    def test_safety_veto_after_term_skips_kill_wait_and_cleanup(self):
        child = FakeChild()
        group_signals = []
        handlers = {}

        def register(signum, handler):
            if handler is not None:
                handlers[signum] = handler
            return None

        def sleep(_seconds):
            handlers[signal.SIGTERM](signal.SIGTERM, None)

        with patch.object(supervisor, 'cleanup') as cleanup, \
                patch.object(supervisor, 'safe_to_stop', side_effect=(True, False)), \
                patch.object(supervisor, 'TERM_GRACE', 0):
            code, _handlers = self.run_fake(
                child, killpg=lambda pid, sig: group_signals.append((pid, sig)),
                register_signal=register, sleep=sleep)
        self.assertEqual(code, 143)
        self.assertEqual(group_signals, [(child.pid, signal.SIGTERM)])
        self.assertEqual(child.wait_calls, 0)
        cleanup.assert_not_called()

    def test_dead_group_leader_is_not_signaled(self):
        child = FakeChild()
        handlers = {}
        group_signals = []

        def register(signum, handler):
            if handler is not None:
                handlers[signum] = handler
            return None

        def sleep(_seconds):
            handlers[signal.SIGTERM](signal.SIGTERM, None)

        def safe_state(*_args):
            child.live = False
            child.status = 0
            return True

        with patch.object(supervisor, 'cleanup', return_value=[]), \
                patch.object(supervisor, 'safe_to_stop', side_effect=safe_state):
            code, _handlers = self.run_fake(
                child, killpg=lambda pid, sig: group_signals.append((pid, sig)),
                register_signal=register, sleep=sleep)
        self.assertEqual(code, 0)
        self.assertEqual(group_signals, [])
        self.assertEqual(child.wait_calls, 1)

    def test_dead_group_leader_is_not_escalated(self):
        child = FakeChild()
        handlers = {}
        group_signals = []
        checks = [0]

        def register(signum, handler):
            if handler is not None:
                handlers[signum] = handler
            return None

        def sleep(_seconds):
            handlers[signal.SIGTERM](signal.SIGTERM, None)

        def safe_state(*_args):
            checks[0] += 1
            if checks[0] == 2:
                child.live = False
                child.status = 0
            return True

        with patch.object(supervisor, 'cleanup', return_value=[]), \
                patch.object(supervisor, 'safe_to_stop', side_effect=safe_state), \
                patch.object(supervisor, 'TERM_GRACE', 0):
            code, _handlers = self.run_fake(
                child, killpg=lambda pid, sig: group_signals.append((pid, sig)),
                register_signal=register, sleep=sleep)
        self.assertEqual(code, 0)
        self.assertEqual(group_signals, [(child.pid, signal.SIGTERM)])
        self.assertEqual(child.wait_calls, 1)

    def test_idle_safety_veto_resets_timer_and_keeps_supervising(self):
        child = FakeChild()
        windows = iter((True, False, False, False))
        sleeps = [0]
        group_signals = []

        def sleep(_seconds):
            sleeps[0] += 1
            if sleeps[0] == 4:
                child.live = False
                child.status = 0

        with patch.object(supervisor, 'game_running', return_value=False), \
                patch.object(supervisor, 'safe_to_stop', return_value=False) as safety, \
                patch.object(supervisor, 'cleanup', return_value=[]):
            code = supervisor.run_supervised(
                ['fixture'], self.prefix, None, stop_after=1,
                proc_root=self.proc, popen=lambda *_a, **_k: child,
                window_probe=lambda: next(windows), killpg=lambda *args:
                group_signals.append(args), sleep=sleep, poll=0,
                clock=lambda: sleeps[0] * 10.0, out=io.StringIO())
        self.assertEqual(code, 0)
        self.assertEqual(group_signals, [])
        safety.assert_called_once()

    def test_idle_stop_is_disabled_for_unowned_runtime(self):
        child = FakeChild()
        sleeps = [0]
        group_signals = []

        def sleep(_seconds):
            sleeps[0] += 1
            if sleeps[0] == 2:
                child.live = False
                child.status = 0

        with patch.object(supervisor, 'runtime_alive', return_value=True), \
                patch.object(supervisor, 'cleanup') as cleanup:
            code = supervisor.run_supervised(
                ['fixture'], self.prefix, None, stop_after=1,
                proc_root=self.proc, popen=lambda *_a, **_k: child,
                window_probe=lambda: self.fail('unowned idle stop must be skipped'),
                killpg=lambda *args: group_signals.append(args), sleep=sleep,
                poll=0, out=io.StringIO())
        self.assertEqual(code, 0)
        self.assertEqual(group_signals, [])
        cleanup.assert_not_called()


class SignalEscalationTests(unittest.TestCase):
    """A signal must start the TERM grace period, then kill the whole group."""

    CHILD = (
        "import os, signal, subprocess, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "worker = subprocess.Popen([sys.executable, '-c', "
        "'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(3)'])\n"
        "with open(sys.argv[1], 'w') as handle:\n"
        "    handle.write('%d %d' % (os.getpid(), worker.pid))\n"
        "time.sleep(3)\n"
    )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / '.darling'
        self.prefix.mkdir()
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        self.pids = self.root / 'pids'
        self.script = self.root / 'ignore-term.py'
        self.script.write_text(self.CHILD)
        previous = supervisor.TERM_GRACE
        supervisor.TERM_GRACE = 0.2
        self.addCleanup(setattr, supervisor, 'TERM_GRACE', previous)

    def wait_dead(self, pid, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                state = Path('/proc/%d/stat' % pid).read_text().rsplit(')', 1)[1].split()[0]
            except (OSError, IndexError):
                return True
            if state == 'Z':
                return True
            time.sleep(0.02)
        return False

    def interrupt_when_ready(self):
        deadline = time.monotonic() + 20
        while not self.pids.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        os.kill(os.getpid(), signal.SIGTERM)

    def test_sigterm_reaches_the_grace_period_and_the_group_is_killed(self):
        thread = threading.Thread(target=self.interrupt_when_ready, daemon=True)
        thread.start()
        output = io.StringIO()
        try:
            code = supervisor.run_supervised(
                [sys.executable, str(self.script), str(self.pids)], self.prefix, None,
                proc_root=self.proc, poll=0, run=lambda *_a, **_k: None,
                sleep=lambda _s: time.sleep(0.01), out=output,
                window_probe=lambda: False)
        finally:
            thread.join(timeout=5)
        parent, worker = (int(part) for part in self.pids.read_text().split())
        self.assertEqual(code, 137)
        self.assertTrue(self.wait_dead(parent), 'the loader survived the escalation')
        self.assertTrue(self.wait_dead(worker), 'the descendant survived the escalation')
        self.assertIn('interrupted by signal 15', output.getvalue())


class IdleEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.previous = os.environ.get('RCLOL_STOP_AFTER_CLIENT_SECONDS')
        self.addCleanup(self.restore)

    def restore(self):
        if self.previous is None:
            os.environ.pop('RCLOL_STOP_AFTER_CLIENT_SECONDS', None)
        else:
            os.environ['RCLOL_STOP_AFTER_CLIENT_SECONDS'] = self.previous

    def test_absent_value_disables_the_idle_stop(self):
        os.environ.pop('RCLOL_STOP_AFTER_CLIENT_SECONDS', None)
        self.assertEqual(supervisor.env_seconds('RCLOL_STOP_AFTER_CLIENT_SECONDS'), 0)

    def test_valid_value_is_used(self):
        os.environ['RCLOL_STOP_AFTER_CLIENT_SECONDS'] = ' 120 '
        self.assertEqual(supervisor.env_seconds('RCLOL_STOP_AFTER_CLIENT_SECONDS'), 120)

    def test_invalid_value_warns_and_disables_the_idle_stop(self):
        os.environ['RCLOL_STOP_AFTER_CLIENT_SECONDS'] = '5m'
        output = io.StringIO()
        self.assertEqual(supervisor.env_seconds('RCLOL_STOP_AFTER_CLIENT_SECONDS', output), 0)
        self.assertIn("ignoring invalid RCLOL_STOP_AFTER_CLIENT_SECONDS='5m'", output.getvalue())

    def test_empty_value_disables_the_idle_stop(self):
        os.environ['RCLOL_STOP_AFTER_CLIENT_SECONDS'] = ''
        self.assertEqual(supervisor.env_seconds('RCLOL_STOP_AFTER_CLIENT_SECONDS'), 0)


class IdleDecisionTests(unittest.TestCase):
    def test_window_present_resets_the_timer(self):
        self.assertEqual(supervisor.idle_decision(True, 100.0, 200.0, True, False, 60),
                         (True, None, False))

    def test_window_gone_starts_and_then_fires(self):
        seen, since, stop = supervisor.idle_decision(True, None, 100.0, False, False, 60)
        self.assertEqual((seen, since, stop), (True, 100.0, False))
        self.assertEqual(supervisor.idle_decision(True, since, 150.0, False, False, 60),
                         (True, 100.0, False))
        self.assertEqual(supervisor.idle_decision(True, since, 161.0, False, False, 60),
                         (True, 100.0, True))

    def test_game_resets_the_timer(self):
        self.assertEqual(supervisor.idle_decision(True, 100.0, 200.0, False, True, 60),
                         (True, None, False))

    def test_unknown_window_state_never_stops(self):
        self.assertEqual(supervisor.idle_decision(True, 100.0, 200.0, None, False, 60),
                         (True, None, False))

    def test_client_that_was_never_seen_never_stops(self):
        self.assertEqual(supervisor.idle_decision(False, None, 200.0, False, False, 60),
                         (False, None, False))

    def test_disabled_never_stops(self):
        self.assertEqual(supervisor.idle_decision(True, 100.0, 999.0, False, False, 0),
                         (True, None, False))


class ManagedWindowTests(unittest.TestCase):
    @staticmethod
    def x11_environment():
        return patch.dict(os.environ, {
            'XDG_CURRENT_DESKTOP': 'GNOME',
            'XDG_SESSION_TYPE': 'x11',
            'DISPLAY': ':fixture',
        }, clear=True)

    def test_client_class_is_detected(self):
        def run(command, **_kwargs):
            output = ('_NET_CLIENT_LIST(WINDOW): window id # 0x1' if '_NET_CLIENT_LIST' in command
                      else 'WM_CLASS(STRING) = "riot client", "Riot Client"')

            class Result:
                stdout = output
            return Result()

        with self.x11_environment():
            self.assertTrue(supervisor.managed_client_window(run))

    def test_missing_property_is_unknown(self):
        def run(_command, **_kwargs):
            class Result:
                stdout = 'not found'
            return Result()

        with self.x11_environment():
            self.assertIsNone(supervisor.managed_client_window(run))


if __name__ == '__main__':
    unittest.main()


class MatchProtectionTests(unittest.TestCase):
    """Closing the Riot Client in game must not end the match."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / '.darling'
        self.prefix.mkdir()
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        self.ns = 'pid:[4026532000]'
        sock = os.fsencode(self.prefix / '.darlingserver.sock')
        self.game = fake_process(self.proc, 20, comm='LeagueofLegends', ns=self.ns,
                                 environ=b'__mldr_sockpath=%s\0' % sock)

    def test_cleanup_waits_for_the_running_game(self):
        import shutil
        polls = []
        order = []
        output = io.StringIO()

        def sleep(_seconds):
            # The loader ('true') has exited; end the game a few polls later.
            if 'waiting for the game' in output.getvalue():
                polls.append(1)
            else:
                time.sleep(0.01)
            if len(polls) == 3 and self.game.exists():
                shutil.rmtree(self.game)
                order.append('game ended')

        previous = supervisor.cleanup

        def cleanup(*_a, **_k):
            order.append('cleanup')
            return []
        supervisor.cleanup = cleanup
        self.addCleanup(setattr, supervisor, 'cleanup', previous)
        code = supervisor.run_supervised(
            ['true'], self.prefix, None, proc_root=self.proc, poll=0,
            run=lambda *_a, **_k: None, sleep=sleep, out=output)
        self.assertEqual(code, 0)
        self.assertEqual(order, ['game ended', 'cleanup'])
        self.assertIn('waiting for the game to end', output.getvalue())
