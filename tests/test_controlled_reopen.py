import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('controlled', ROOT / 'experimental/reopen-probe/controlled.py')
controlled = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controlled)


class ControlledTests(unittest.TestCase):
    def test_disjoint(self):
        self.assertFalse(controlled._disjoint(Path('/a'), Path('/a/b')))
        self.assertFalse(controlled._disjoint(Path('/a'), Path('/a')))
        self.assertTrue(controlled._disjoint(Path('/a'), Path('/b')))

    def test_reopen_refuses_without_new_user_close(self):
        probe = controlled.ControlledProbe('/other')
        probe.state = 'running'
        probe.prefix = Path('/retained')
        probe.observe = mock.Mock(return_value={'map_state': 'IsUnMapped', 'log': 'CLOSED_BY_USER\n'})
        probe.close_count = 1
        with self.assertRaisesRegex(controlled.ProbeError, '/retained'):
            probe.reopen()
        self.assertEqual(probe.state, 'failed')

    def test_reopen_uses_command_after_close(self):
        probe = controlled.ControlledProbe('/other')
        probe.state = 'running'
        probe.xid = 42
        probe.observe = mock.Mock(side_effect=[{'map_state': 'IsUnMapped', 'log': 'CLOSED_BY_USER\n'},
                                              {'map_state': 'IsViewable', 'xid': 42}])
        probe._command = mock.Mock(return_value='REOPEN_CALLBACK\nACK 1 reopen\n')
        probe.reopen()
        probe._command.assert_called_once_with('reopen')

    def test_reopen_requires_exact_callback_and_viewable(self):
        for log, state, xid in [('ACK 1 reopen\n', 'IsViewable', 42),
                                ('REOPEN_CALLBACK\nREOPEN_CALLBACK\n', 'IsViewable', 42),
                                ('REOPEN_CALLBACK\n', 'IsUnMapped', 42),
                                ('REOPEN_CALLBACK\n', 'IsViewable', 43)]:
            with self.subTest(log=log, state=state, xid=xid):
                probe = controlled.ControlledProbe('/other')
                probe.state, probe.prefix, probe.xid = 'running', Path('/retained'), 42
                probe.observe = mock.Mock(side_effect=[{'map_state': 'IsUnMapped', 'log': 'CLOSED_BY_USER\n'},
                                                      {'map_state': state, 'xid': xid}])
                probe._command = mock.Mock(return_value=log)
                with self.assertRaisesRegex(controlled.ProbeError, '/retained'):
                    probe.reopen()

    def test_secure_runtime_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.assertEqual(controlled._secure_base(base), base)
            base.chmod(0o775)
            with self.assertRaises(ValueError):
                controlled._secure_base(base)

    def test_fallback_uses_secure_runtime_and_sanitizes_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            fixture = runtime / 'fixture'
            fixture.touch()
            probe = controlled.ControlledProbe('/unrelated')
            process = mock.Mock()
            with mock.patch.object(controlled, 'BASE', runtime / 'missing'), \
                 mock.patch.object(controlled, 'FIXTURE', fixture), \
                 mock.patch.dict(os.environ, {'DISPLAY': ':1', 'XDG_RUNTIME_DIR': directory,
                                             'SECRET': 'not inherited'}, clear=True), \
                 mock.patch.object(controlled.subprocess, 'Popen', return_value=process) as popen, \
                 mock.patch.object(probe, '_wait_log', return_value=mock.Mock(group=lambda _: '42')), \
                 mock.patch.object(probe, 'observe', return_value={'map_state': 'IsViewable'}):
                probe.start()
            self.assertEqual(probe.prefix.parent, runtime)
            self.assertTrue(probe.prefix.name.startswith('rp-'))
            self.assertEqual(probe.prefix.stat().st_mode & 0o777, 0o700)
            self.assertNotIn('SECRET', popen.call_args.kwargs['env'])

    def test_start_rejects_overlapping_configured_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            with mock.patch.object(controlled, 'BASE', base), mock.patch.dict(os.environ, {'DISPLAY': ':1'}, clear=True):
                probe = controlled.ControlledProbe(base)
                with self.assertRaisesRegex(controlled.ProbeError, 'overlaps.*not created'):
                    probe.start()
                self.assertIsNone(probe.prefix)

    def test_no_new_privs_fails_closed(self):
        probe = controlled.ControlledProbe('/other')
        with mock.patch.object(Path, 'read_text', return_value='NoNewPrivs:\t1\n'):
            with self.assertRaisesRegex(controlled.ProbeError, 'NoNewPrivs'):
                probe.start()
        self.assertIsNone(probe.prefix)

    def test_timeout_never_kills(self):
        probe = controlled.ControlledProbe('/other', timeout=0)
        probe.prefix = Path('/retained')
        probe.process = mock.Mock()
        with self.assertRaisesRegex(controlled.ProbeError, '/retained'):
            probe._wait_log('anything', 0)
        probe.process.kill.assert_not_called()
        probe.process.terminate.assert_not_called()

    def test_shellspawn_failure_beats_ready_and_redacts_log(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = controlled.ControlledProbe('/other', timeout=15)
            probe.prefix = Path(directory)
            probe.log = probe.prefix / 'log'
            probe.log.write_text('Error connecting to shellspawn in the container (/secret/socket): No such file or directory\nREADY 42\n')
            probe.process = mock.Mock()
            probe.process.poll.return_value = None
            with mock.patch.object(controlled.time, 'sleep') as sleep:
                with self.assertRaises(controlled.ProbeError) as error:
                    probe._wait_log(r'^READY ([1-9][0-9]*)$', 0)
            self.assertIn('shellspawn connection failed (No such file or directory)', str(error.exception))
            self.assertIn('prefix retained: ' + directory, str(error.exception))
            self.assertNotIn('/secret/socket', str(error.exception))
            self.assertEqual(probe.state, 'failed')
            sleep.assert_not_called()
            probe.process.kill.assert_not_called()
            probe.process.terminate.assert_not_called()

    def test_failed_reopen_then_cooperative_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = controlled.ControlledProbe('/other')
            probe.prefix = Path(directory)
            probe.log = probe.prefix / 'log'
            probe.log.write_text('')
            probe.control = probe.prefix / 'control'
            probe.nonce = 'nonce'
            probe.state = 'running'
            probe.process = mock.Mock()
            probe.process.poll.return_value = None
            probe.process.wait.return_value = 0
            probe.observe = mock.Mock(return_value={'map_state': 'IsViewable', 'log': ''})
            with self.assertRaises(controlled.ProbeError):
                probe.reopen()
            with mock.patch.object(probe, '_wait_log'):
                result = probe.stop()
            self.assertEqual(probe.control.read_text(), 'nonce 1 stop')
            self.assertEqual(probe.state, 'stopped')
            self.assertFalse(result['server_shutdown_requested'])
            probe.process.kill.assert_not_called()
            probe.process.terminate.assert_not_called()

    def test_start_failure_after_spawn_can_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            fixture = runtime / 'fixture'
            fixture.touch()
            probe = controlled.ControlledProbe('/unrelated')
            process = mock.Mock()
            process.poll.return_value = None
            process.wait.return_value = 0
            with mock.patch.object(controlled, 'BASE', runtime), \
                 mock.patch.object(controlled, 'FIXTURE', fixture), \
                 mock.patch.dict(os.environ, {'DISPLAY': ':1'}, clear=True), \
                 mock.patch.object(controlled.subprocess, 'Popen', return_value=process), \
                 mock.patch.object(probe, '_wait_log', side_effect=lambda *args: probe._error('timeout')):
                with self.assertRaises(controlled.ProbeError):
                    probe.start()
            with mock.patch.object(probe, '_wait_log'):
                probe.stop()
            self.assertEqual(probe.state, 'stopped')
            self.assertEqual(probe.control.read_text(), f'{probe.nonce} 1 stop')
            process.kill.assert_not_called()

    def test_failure_before_spawn_stop_is_refused(self):
        probe = controlled.ControlledProbe('/other')
        with mock.patch.object(Path, 'read_text', return_value='NoNewPrivs:\t1\n'):
            with self.assertRaises(controlled.ProbeError):
                probe.start()
        with self.assertRaisesRegex(controlled.ProbeError, 'controllable fixture'):
            probe.stop()
        self.assertIsNone(probe.prefix)

    def test_stop_skips_unacknowledged_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = controlled.ControlledProbe('/other')
            probe.prefix = Path(directory)
            probe.log = probe.prefix / 'log'
            probe.log.touch()
            probe.control = probe.prefix / 'control'
            probe.nonce, probe.sequence, probe.state = 'nonce', 1, 'failed'
            probe.process = mock.Mock()
            probe.process.poll.return_value = None
            probe.process.wait.return_value = 0
            with mock.patch.object(probe, '_wait_log'):
                probe.stop()
            self.assertEqual(probe.control.read_text(), 'nonce 2 stop')


if __name__ == '__main__':
    unittest.main()
